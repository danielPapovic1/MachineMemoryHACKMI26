from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import re
from typing import Any

from .dashboard_data import load_maintenance_logs
from .machine_store import DATA_DIR, load_machines


UPLOAD_LOGS_FILE = DATA_DIR / "upload-logs.json"
DEFAULT_LIMIT = 25
MAX_LIMIT = 500


def create_upload_id(file_name: str, uploaded_at: str | None = None) -> str:
    timestamp = uploaded_at or datetime.now(timezone.utc).isoformat()
    safe_name = re.sub(r"[^0-9A-Za-z]+", "-", file_name.rsplit(".", 1)[0]).strip("-").lower() or "upload"
    safe_timestamp = re.sub(r"[^0-9A-Za-z]+", "", timestamp)
    return f"upload-{safe_name}-{safe_timestamp}"


def record_upload_log(entry: dict[str, Any]) -> None:
    uploads = _read_upload_log_entries()
    upload_id = entry.get("uploadId")
    if not upload_id:
        return

    kept = [upload for upload in uploads if upload.get("uploadId") != upload_id]
    kept.append(entry)
    _write_upload_log_entries(kept)


def record_failed_upload(
    file_name: str,
    upload_type: str,
    error_message: str,
    uploaded_at: str | None = None,
) -> str:
    received_at = uploaded_at or datetime.now(timezone.utc).isoformat()
    upload_id = create_upload_id(file_name, received_at)
    record_upload_log(
        {
            "uploadId": upload_id,
            "fileName": file_name,
            "uploadedAt": received_at,
            "uploadType": upload_type,
            "status": "failed",
            "machineCount": 0,
            "rowsStored": 0,
            "insertedRows": 0,
            "updatedRows": 0,
            "errorRows": 1,
            "affectedMachineIds": [],
            "warnings": [error_message],
        }
    )
    return upload_id


def get_upload_logs_page(
    date_from: str | None = None,
    date_to: str | None = None,
    upload_type: str | None = None,
    status: str | None = None,
    machine_id: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    uploads = _combined_uploads()
    filtered = _filter_uploads(
        uploads=uploads,
        date_from=date_from,
        date_to=date_to,
        upload_type=upload_type,
        status=status,
        machine_id=machine_id,
    )
    sorted_uploads = sorted(filtered, key=lambda upload: str(upload.get("uploadedAt") or ""), reverse=True)
    safe_offset = max(offset or 0, 0)
    safe_limit = _safe_limit(limit)
    paged_uploads = sorted_uploads[safe_offset : safe_offset + safe_limit]

    return {
        "summary": _summary(sorted_uploads),
        "uploads": paged_uploads,
        "filters": _filter_options(uploads),
        "pagination": {
            "limit": safe_limit,
            "offset": safe_offset,
            "total": len(sorted_uploads),
        },
    }


def get_upload_log_detail(upload_id: str, limit: int | None = None, offset: int | None = None) -> dict[str, Any] | None:
    upload = next((item for item in _combined_uploads() if item.get("uploadId") == upload_id), None)
    if upload is None:
        return None

    all_rows = _rows_for_upload(upload)
    safe_offset = max(offset or 0, 0)
    safe_limit = _safe_limit(limit, default=100)
    paged_rows = all_rows[safe_offset : safe_offset + safe_limit]

    return {
        "overview": {
            "uploadId": upload.get("uploadId"),
            "fileName": upload.get("fileName"),
            "uploadedAt": upload.get("uploadedAt"),
            "uploadType": upload.get("uploadType"),
            "status": upload.get("status"),
            "machineCount": upload.get("machineCount") or 0,
            "rowsStored": upload.get("rowsStored") or 0,
            "warnings": upload.get("warnings") or [],
        },
        "affectedMachines": _affected_machine_details(upload.get("affectedMachineIds") or []),
        "rowSummary": {
            "totalRows": len(all_rows),
            "inserted": upload.get("insertedRows") or 0,
            "updated": upload.get("updatedRows") or 0,
            "errors": upload.get("errorRows") or 0,
            "returned": len(paged_rows),
            "limit": safe_limit,
            "offset": safe_offset,
        },
        "rows": paged_rows,
    }


def _combined_uploads() -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for upload in _uploads_from_maintenance_logs():
        by_id[str(upload["uploadId"])] = upload

    for upload in _read_upload_log_entries():
        upload_id = upload.get("uploadId")
        if upload_id:
            base = by_id.get(str(upload_id), {})
            by_id[str(upload_id)] = _clean_upload_summary({**base, **upload})

    return list(by_id.values())


def _uploads_from_maintenance_logs() -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for log in load_maintenance_logs():
        upload_id = log.get("upload_id")
        if not upload_id:
            upload_id = create_upload_id(str(log.get("source") or "maintenance-upload"), str(log.get("ingested_at") or ""))
        grouped[str(upload_id)].append(log)

    return [_upload_from_logs(upload_id, logs) for upload_id, logs in grouped.items()]


def _upload_from_logs(upload_id: str, logs: list[dict[str, Any]]) -> dict[str, Any]:
    first = logs[0] if logs else {}
    affected = sorted({str(log.get("machine_id")) for log in logs if log.get("machine_id")})
    warnings = [
        f"{sum(1 for log in logs if not log.get('matched_machine'))} rows did not match the machine registry"
    ] if any(not log.get("matched_machine") for log in logs) else []

    return _clean_upload_summary(
        {
            "uploadId": upload_id,
            "fileName": first.get("source") or "maintenance-upload.csv",
            "uploadedAt": first.get("ingested_at") or first.get("timestamp_opened"),
            "uploadType": "maintenance",
            "status": "needs_review" if warnings else "processed",
            "machineCount": len(affected),
            "rowsStored": len(logs),
            "insertedRows": len(logs),
            "updatedRows": 0,
            "errorRows": 0,
            "affectedMachineIds": affected,
            "warnings": warnings,
        }
    )


def _rows_for_upload(upload: dict[str, Any]) -> list[dict[str, Any]]:
    upload_id = upload.get("uploadId")
    file_name = upload.get("fileName")
    uploaded_at = upload.get("uploadedAt")
    logs = [
        log
        for log in load_maintenance_logs()
        if log.get("upload_id") == upload_id
        or (
            not log.get("upload_id")
            and create_upload_id(str(log.get("source") or "maintenance-upload"), str(log.get("ingested_at") or "")) == upload_id
        )
    ]

    rows = [_log_to_table_row(log) for log in sorted(logs, key=_log_sort_key)]
    display_rows = upload.get("displayRows")
    if isinstance(display_rows, list):
        rows.extend(row for row in display_rows if isinstance(row, dict))

    if rows:
        return rows

    if upload.get("status") == "failed":
        return [
            {
                "machineId": None,
                "machineName": None,
                "field": "Upload Error",
                "value": "; ".join(str(item) for item in upload.get("warnings") or []) or "Upload failed",
                "timestamp": uploaded_at,
                "status": "failed",
                "sourceFile": file_name,
                "sourceRowNumber": None,
                "severity": None,
                "downtimeMinutes": None,
                "laborHours": None,
                "operatorNote": None,
                "resolutionNote": None,
            }
        ]

    return []


def _log_to_table_row(log: dict[str, Any]) -> dict[str, Any]:
    return {
        "machineId": log.get("machine_id"),
        "machineName": log.get("machine_name"),
        "field": _display_field(log),
        "value": _display_value(log),
        "timestamp": log.get("timestamp_opened") or log.get("timestamp") or log.get("ingested_at"),
        "status": log.get("status") or "stored",
        "sourceFile": log.get("source"),
        "sourceRowNumber": log.get("source_row_number"),
        "severity": log.get("severity"),
        "downtimeMinutes": log.get("downtime_minutes"),
        "laborHours": log.get("labor_hours"),
        "operatorNote": log.get("operator_note"),
        "resolutionNote": log.get("resolution_note"),
    }


def _display_field(log: dict[str, Any]) -> str:
    if log.get("issue"):
        return "Issue"
    if log.get("operator_note"):
        return "Operator Note"
    if log.get("resolution_note"):
        return "Resolution"
    if log.get("severity"):
        return "Severity"
    return "Maintenance Record"


def _display_value(log: dict[str, Any]) -> Any:
    for key in ("issue", "operator_note", "resolution_note", "severity", "source_record_id"):
        value = log.get(key)
        if value not in (None, "", "unknown"):
            return value
    return "Stored maintenance row"


def _affected_machine_details(machine_ids: list[str]) -> list[dict[str, Any]]:
    registry = {
        str(machine.get("machine_id")).upper(): machine
        for machine in load_machines()
        if machine.get("machine_id")
    }
    return [
        {
            "machineId": machine_id,
            "name": registry.get(str(machine_id).upper(), {}).get("name"),
            "zone": registry.get(str(machine_id).upper(), {}).get("zone"),
            "matchedMachine": str(machine_id).upper() in registry,
        }
        for machine_id in machine_ids
    ]


def _filter_uploads(
    uploads: list[dict[str, Any]],
    date_from: str | None,
    date_to: str | None,
    upload_type: str | None,
    status: str | None,
    machine_id: str | None,
) -> list[dict[str, Any]]:
    result = uploads
    if date_from:
        result = [upload for upload in result if str(upload.get("uploadedAt") or "") >= _date_floor(date_from)]
    if date_to:
        result = [upload for upload in result if str(upload.get("uploadedAt") or "") <= _date_ceiling(date_to)]
    if upload_type:
        result = [upload for upload in result if str(upload.get("uploadType") or "").lower() == upload_type.lower()]
    if status:
        result = [upload for upload in result if str(upload.get("status") or "").lower() == status.lower()]
    if machine_id:
        target = machine_id.upper()
        result = [
            upload
            for upload in result
            if target in {str(item).upper() for item in upload.get("affectedMachineIds") or []}
        ]
    return result


def _date_floor(value: str) -> str:
    return f"{value}T00:00:00" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else value


def _date_ceiling(value: str) -> str:
    return f"{value}T23:59:59.999999" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else value


def _summary(uploads: list[dict[str, Any]]) -> dict[str, Any]:
    last_upload = uploads[0] if uploads else None
    affected_machines = {
        str(machine_id).upper()
        for upload in uploads
        for machine_id in upload.get("affectedMachineIds") or []
        if machine_id
    }
    return {
        "totalUploads": len(uploads),
        "lastUpload": {
            "uploadedAt": last_upload.get("uploadedAt"),
            "fileName": last_upload.get("fileName"),
        } if last_upload else None,
        "rowsStored": sum(_int_value(upload.get("rowsStored")) for upload in uploads),
        "machinesUpdated": len(affected_machines),
        "insertedRows": sum(_int_value(upload.get("insertedRows")) for upload in uploads),
        "updatedRows": sum(_int_value(upload.get("updatedRows")) for upload in uploads),
        "errorRows": sum(_int_value(upload.get("errorRows")) for upload in uploads),
    }


def _filter_options(uploads: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "uploadTypes": sorted({str(upload.get("uploadType")) for upload in uploads if upload.get("uploadType")}),
        "statuses": sorted({str(upload.get("status")) for upload in uploads if upload.get("status")}),
        "machineIds": sorted(
            {
                str(machine_id)
                for upload in uploads
                for machine_id in upload.get("affectedMachineIds") or []
                if machine_id
            }
        ),
    }


def _clean_upload_summary(upload: dict[str, Any]) -> dict[str, Any]:
    affected = sorted({str(item) for item in upload.get("affectedMachineIds") or [] if item})
    rows_stored = _int_value(upload.get("rowsStored"))
    return {
        **upload,
        "status": upload.get("status") or ("processed" if rows_stored else "failed"),
        "machineCount": _int_value(upload.get("machineCount"), len(affected)),
        "rowsStored": rows_stored,
        "insertedRows": _int_value(upload.get("insertedRows"), rows_stored),
        "updatedRows": _int_value(upload.get("updatedRows")),
        "errorRows": _int_value(upload.get("errorRows")),
        "affectedMachineIds": affected,
        "warnings": upload.get("warnings") or [],
    }


def _safe_limit(limit: int | None, default: int = DEFAULT_LIMIT) -> int:
    if limit is None:
        return default
    return min(max(limit, 1), MAX_LIMIT)


def _log_sort_key(log: dict[str, Any]) -> tuple[str, int]:
    timestamp = str(log.get("timestamp_opened") or log.get("timestamp") or log.get("ingested_at") or "")
    row_number = _int_value(log.get("source_row_number"))
    return timestamp, row_number


def _int_value(value: Any, fallback: int = 0) -> int:
    if value in (None, ""):
        return fallback

    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _read_upload_log_entries() -> list[dict[str, Any]]:
    if not UPLOAD_LOGS_FILE.exists():
        return []

    text = UPLOAD_LOGS_FILE.read_text(encoding="utf-8").strip()
    if not text:
        return []

    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("upload-logs.json must contain a JSON list")

    return [item for item in data if isinstance(item, dict)]


def _write_upload_log_entries(entries: list[dict[str, Any]]) -> None:
    UPLOAD_LOGS_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")
