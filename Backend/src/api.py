import csv
import io
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .ai_insights import AIInsightsError, get_ai_insights_page, get_machine_ai_insights
from .cue_bank import normalize_column_name
from .csv_normalizer import normalize_csv_rows
from .dashboard_data import (
    append_maintenance_logs,
    get_dashboard_summary,
    get_factory_map,
    get_machines as get_dashboard_machines,
    get_recent_alerts,
    get_recent_logs,
    get_upload_preview,
    save_uploaded_machine_dataset,
)
from .deep_review import (
    DeepReviewError,
    DeepReviewMachineNotFound,
    DeepReviewRequestError,
    run_machine_deep_review,
)
from .machine_analysis import MachineAnalysisError, MachineNotFoundError, analyze_selected_machine
from .machine_csv_normalizer import normalize_machine_csv_rows
from .machines_page import get_machines_page_profile
from .machine_store import load_machines
from .upload_logs import (
    create_upload_id,
    get_upload_log_detail,
    get_upload_logs_page,
    record_failed_upload,
    record_upload_log,
)


MACHINE_UPLOAD_CUES = {
    "machine type",
    "asset type",
    "equipment type",
    "production line",
    "line",
    "temperature",
    "temp",
    "vibration",
    "pressure",
    "runtime hours",
    "run hours",
    "operating hours",
    "error count",
    "fault count",
    "alarm count",
    "last maintenance",
    "next maintenance",
    "downtime cost per minute",
    "cost per minute",
    "map x",
    "map y",
    "x",
    "y",
    "manufacturer",
    "model",
    "installed date",
    "energy usage",
    "throughput",
}

MAINTENANCE_UPLOAD_CUES = {
    "work order id",
    "work order",
    "ticket no",
    "ticket",
    "date opened",
    "opened",
    "created on",
    "date closed",
    "closed",
    "problem",
    "issue",
    "failure desc",
    "failure description",
    "tech notes",
    "operator comment",
    "repair notes",
    "action taken",
    "corrective action",
    "downtime minutes",
    "time lost",
    "stopped minutes",
    "labor hours",
    "technician",
}


app = FastAPI(title="Machine Memory API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "machine-memory-api"}


@app.get("/api/machines")
def get_machines() -> dict[str, object]:
    try:
        machines = get_dashboard_machines()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"machines": machines}


@app.get("/api/factory-map")
def read_factory_map() -> dict[str, Any]:
    try:
        return get_factory_map()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/dashboard-summary")
def read_dashboard_summary() -> dict[str, Any]:
    try:
        return get_dashboard_summary()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/maintenance-logs/recent")
def read_recent_maintenance_logs() -> dict[str, Any]:
    try:
        return {"logs": get_recent_logs()}
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/alerts/recent")
def read_recent_alerts() -> dict[str, Any]:
    try:
        return {"alerts": get_recent_alerts()}
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/uploads/preview")
def read_upload_preview() -> dict[str, Any]:
    return get_upload_preview()


@app.get("/api/upload-logs")
def read_upload_logs(
    dateFrom: str | None = None,
    dateTo: str | None = None,
    uploadType: str | None = None,
    status: str | None = None,
    machineId: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    try:
        return get_upload_logs_page(
            date_from=dateFrom,
            date_to=dateTo,
            upload_type=uploadType,
            status=status,
            machine_id=machineId,
            limit=limit,
            offset=offset,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/upload-logs/{upload_id}")
def read_upload_log_detail(upload_id: str, limit: int | None = None, offset: int | None = None) -> dict[str, Any]:
    try:
        detail = get_upload_log_detail(upload_id, limit=limit, offset=offset)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if detail is None:
        raise HTTPException(status_code=404, detail=f"Upload not found: {upload_id}")

    return detail


@app.get("/api/ai-insights")
def read_ai_insights(
    ai_type: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    try:
        return get_ai_insights_page(ai_type=ai_type, limit=limit, offset=offset)
    except AIInsightsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ai-insights/{machine_id}")
def read_machine_ai_insights(
    machine_id: str,
    ai_type: str,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    try:
        return get_machine_ai_insights(machine_id=machine_id, ai_type=ai_type, limit=limit, offset=offset)
    except AIInsightsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/uploads/csv")
async def upload_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    source_name = file.filename or "uploaded.csv"
    try:
        source_name, headers, rows, parse_warnings = await _read_uploaded_csv(file, "uploaded.csv")
    except HTTPException as exc:
        record_failed_upload(source_name, "unknown", str(exc.detail))
        raise

    upload_type = _classify_upload(headers)

    if upload_type == "machine":
        result = _process_machine_csv(source_name, headers, rows, parse_warnings)
        result["upload_type"] = "machine"
        return result

    if upload_type == "mixed":
        ingested_at = datetime.now(timezone.utc).isoformat()
        upload_id = create_upload_id(source_name, ingested_at)
        machine_result = _process_machine_csv(
            source_name,
            headers,
            rows,
            parse_warnings,
            upload_type="mixed",
            record_upload=False,
            upload_id=upload_id,
            uploaded_at=ingested_at,
        )
        maintenance_result = _process_maintenance_csv(
            source_name,
            headers,
            rows,
            [],
            allow_empty=True,
            upload_type="mixed",
            record_upload=False,
            upload_id=upload_id,
            ingested_at=ingested_at,
        )
        warnings = [
            *machine_result.get("warnings", []),
            *maintenance_result.get("warnings", []),
            "Detected mixed machine-state and maintenance-history columns",
        ]
        affected_machine_ids = sorted(
            {
                str(machine.get("id") or machine.get("machine_id"))
                for machine in machine_result.get("normalized_machines", [])
                if machine.get("id") or machine.get("machine_id")
            }.union(
                {
                    str(record.get("machine_id"))
                    for record in maintenance_result.get("normalized_records", [])
                    if record.get("machine_id")
                }
            )
        )
        mixed_rows_stored = machine_result.get("normalized_count", 0) + maintenance_result.get("saved_count", 0)
        record_upload_log(
            {
                "uploadId": upload_id,
                "fileName": source_name,
                "uploadedAt": ingested_at,
                "uploadType": "mixed",
                "status": _upload_status(mixed_rows_stored, warnings),
                "machineCount": len(affected_machine_ids),
                "rowsStored": mixed_rows_stored,
                "insertedRows": mixed_rows_stored,
                "updatedRows": 0,
                "errorRows": len(machine_result.get("skipped_rows", [])) + len(maintenance_result.get("skipped_rows", [])),
                "affectedMachineIds": affected_machine_ids,
                "warnings": warnings,
                "displayRows": _machine_display_rows(machine_result.get("normalized_machines", []), source_name, ingested_at),
            }
        )

        return {
            **machine_result,
            "upload_type": "mixed",
            "upload_id": upload_id,
            "maintenance_result": maintenance_result,
            "normalized_records": maintenance_result.get("normalized_records", []),
            "saved_count": maintenance_result.get("saved_count", 0),
            "total_history_count": maintenance_result.get("total_history_count"),
            "warnings": warnings,
        }

    result = _process_maintenance_csv(source_name, headers, rows, parse_warnings, allow_empty=False)
    result["upload_type"] = "maintenance"
    return result


@app.post("/api/machines/upload-csv")
async def upload_machine_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    source_name = file.filename or "uploaded-machines.csv"
    try:
        source_name, headers, rows, parse_warnings = await _read_uploaded_csv(file, "uploaded-machines.csv")
    except HTTPException as exc:
        record_failed_upload(source_name, "machine", str(exc.detail))
        raise

    return _process_machine_csv(source_name, headers, rows, parse_warnings)


def _process_machine_csv(
    source_name: str,
    headers: list[str],
    rows: list[dict[str, str | None]],
    parse_warnings: list[str],
    upload_type: str = "machine",
    record_upload: bool = True,
    upload_id: str | None = None,
    uploaded_at: str | None = None,
) -> dict[str, Any]:
    result = normalize_machine_csv_rows(
        headers=headers,
        rows=rows,
        source=source_name,
    )
    warnings = parse_warnings + result["warnings"]
    upload_time = uploaded_at or datetime.now(timezone.utc).isoformat()
    current_upload_id = upload_id or create_upload_id(source_name, upload_time)
    upload_preview = {
        "detectedColumnMappings": result["detected_column_mappings"],
        "lastUpload": {
            "uploadedAt": upload_time,
            "fileName": source_name,
            "normalizedCount": result["normalized_count"],
        },
        "warnings": warnings,
        "skippedRows": result["skipped_rows"],
        "unmappedColumns": result["unmapped_columns"],
    }

    try:
        save_uploaded_machine_dataset(
            machines=result["normalized_machines"],
            summary=result["dashboard_summary"],
            upload_preview=upload_preview,
        )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to save normalized machine data: {exc}") from exc

    affected_machine_ids = sorted(
        {
            str(machine.get("id") or machine.get("machine_id"))
            for machine in result["normalized_machines"]
            if machine.get("id") or machine.get("machine_id")
        }
    )
    if record_upload:
        record_upload_log(
            {
                "uploadId": current_upload_id,
                "fileName": source_name,
                "uploadedAt": upload_time,
                "uploadType": upload_type,
                "status": _upload_status(result["normalized_count"], warnings),
                "machineCount": len(affected_machine_ids),
                "rowsStored": result["normalized_count"],
                "insertedRows": result["normalized_count"],
                "updatedRows": 0,
                "errorRows": len(result["skipped_rows"]),
                "affectedMachineIds": affected_machine_ids,
                "warnings": warnings,
                "displayRows": _machine_display_rows(result["normalized_machines"], source_name, upload_time),
            }
        )

    return {
        "upload_id": current_upload_id,
        "source": source_name,
        "row_count": result["row_count"],
        "normalized_count": result["normalized_count"],
        "detected_column_mappings": result["detected_column_mappings"],
        "normalized_machines": result["normalized_machines"],
        "dashboard_summary": result["dashboard_summary"],
        "uploadPreview": upload_preview,
        "unmapped_columns": result["unmapped_columns"],
        "warnings": warnings,
        "skipped_rows": result["skipped_rows"],
    }


@app.post("/api/machines/{machine_id}/analyze")
def analyze_machine(machine_id: str) -> dict[str, Any]:
    try:
        return analyze_selected_machine(machine_id)
    except MachineNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MachineAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/machines/{machine_id}/deep-review")
def deep_review_machine(machine_id: str, payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    try:
        return run_machine_deep_review(machine_id, payload)
    except DeepReviewMachineNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeepReviewRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DeepReviewError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/machines/{machine_id}")
def read_machine_detail(machine_id: str) -> dict[str, Any]:
    try:
        detail = get_machines_page_profile(machine_id)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if detail is None:
        raise HTTPException(status_code=404, detail=f"Machine not found: {machine_id}")

    return detail


@app.post("/api/maintenance-logs/upload-csv")
async def upload_maintenance_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    source_name = file.filename or "uploaded.csv"
    try:
        source_name, headers, rows, parse_warnings = await _read_uploaded_csv(file, "uploaded.csv")
    except HTTPException as exc:
        record_failed_upload(source_name, "maintenance", str(exc.detail))
        raise

    return _process_maintenance_csv(source_name, headers, rows, parse_warnings, allow_empty=False)


async def _read_uploaded_csv(
    file: UploadFile,
    default_name: str,
) -> tuple[str, list[str], list[dict[str, str | None]], list[str]]:
    source_name = file.filename or default_name
    uploaded_bytes = await file.read()

    if not uploaded_bytes:
        raise HTTPException(status_code=400, detail="Uploaded CSV file is empty")

    try:
        csv_text = uploaded_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Uploaded CSV must be UTF-8 encoded") from exc

    try:
        headers, rows, parse_warnings = _parse_csv_text(csv_text)
    except csv.Error as exc:
        raise HTTPException(status_code=400, detail=f"Unable to parse CSV: {exc}") from exc

    if not headers:
        raise HTTPException(status_code=400, detail="Uploaded CSV must include a header row")

    return source_name, headers, rows, parse_warnings


def _process_maintenance_csv(
    source_name: str,
    headers: list[str],
    rows: list[dict[str, str | None]],
    parse_warnings: list[str],
    allow_empty: bool,
    upload_type: str = "maintenance",
    record_upload: bool = True,
    upload_id: str | None = None,
    ingested_at: str | None = None,
) -> dict[str, Any]:
    try:
        machines = load_machines()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    known_machine_ids = {
        str(machine["machine_id"])
        for machine in machines
        if machine.get("machine_id")
    }
    result = normalize_csv_rows(
        headers=headers,
        rows=rows,
        source=source_name,
        known_machine_ids=known_machine_ids,
    )
    ingested_at = ingested_at or datetime.now(timezone.utc).isoformat()
    current_upload_id = upload_id or create_upload_id(source_name, ingested_at)
    normalized_records = [
        {
            **record,
            "upload_id": current_upload_id,
            "source_row_number": index,
            "ingested_at": ingested_at,
            "ai_analysis": record.get("ai_analysis"),
        }
        for index, record in enumerate(result["normalized_records"], start=1)
        if _is_valid_maintenance_record(record)
    ]
    warnings = parse_warnings + result["warnings"]
    dropped_count = result["normalized_count"] - len(normalized_records)
    if dropped_count:
        warnings.append(f"Skipped {dropped_count} rows without enough maintenance-history fields")

    if not normalized_records and not allow_empty:
        warnings.append("No maintenance-history rows were saved from this upload")

    upload_preview = {
        "detectedColumnMappings": result["detected_column_mappings"],
        "lastUpload": {
            "uploadedAt": ingested_at,
            "fileName": source_name,
            "normalizedCount": len(normalized_records),
        },
        "warnings": warnings,
        "skippedRows": result["skipped_rows"],
        "unmappedColumns": result["unmapped_columns"],
    }

    try:
        total_history_count = append_maintenance_logs(
            records=normalized_records,
            upload_preview=upload_preview,
        )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to save normalized maintenance logs: {exc}") from exc

    affected_machine_ids = sorted({str(record.get("machine_id")) for record in normalized_records if record.get("machine_id")})
    if record_upload:
        record_upload_log(
            {
                "uploadId": current_upload_id,
                "fileName": source_name,
                "uploadedAt": ingested_at,
                "uploadType": upload_type,
                "status": _upload_status(len(normalized_records), warnings),
                "machineCount": len(affected_machine_ids),
                "rowsStored": len(normalized_records),
                "insertedRows": len(normalized_records),
                "updatedRows": 0,
                "errorRows": len(result["skipped_rows"]) + dropped_count,
                "affectedMachineIds": affected_machine_ids,
                "warnings": warnings,
            }
        )

    return {
        "upload_id": current_upload_id,
        "source": source_name,
        "row_count": result["row_count"],
        "normalized_count": len(normalized_records),
        "saved_count": len(normalized_records),
        "total_history_count": total_history_count,
        "detected_column_mappings": result["detected_column_mappings"],
        "normalized_records": normalized_records,
        "uploadPreview": upload_preview,
        "unmapped_columns": result["unmapped_columns"],
        "warnings": warnings,
        "skipped_rows": result["skipped_rows"],
    }


def _classify_upload(headers: list[str]) -> str:
    normalized_headers = {normalize_column_name(header) for header in headers}
    machine_score = sum(1 for header in normalized_headers if header in MACHINE_UPLOAD_CUES)
    maintenance_score = sum(1 for header in normalized_headers if header in MAINTENANCE_UPLOAD_CUES)

    if machine_score >= 3 and maintenance_score >= 3:
        return "mixed"
    if machine_score >= 3:
        return "machine"
    return "maintenance"


def _upload_status(saved_count: int, warnings: list[str]) -> str:
    if saved_count <= 0:
        return "failed"
    return "needs_review" if warnings else "processed"


def _machine_display_rows(
    machines: list[dict[str, Any]],
    source_name: str,
    uploaded_at: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for machine in machines:
        machine_id = machine.get("id") or machine.get("machine_id")
        value = machine.get("status") or machine.get("operatorNotes") or machine.get("type") or "Stored machine row"
        rows.append(
            {
                "machineId": machine_id,
                "machineName": machine.get("name"),
                "field": "Machine State",
                "value": value,
                "timestamp": uploaded_at,
                "status": machine.get("status") or "stored",
                "sourceFile": source_name,
                "sourceRowNumber": None,
                "severity": None,
                "downtimeMinutes": None,
                "laborHours": None,
                "operatorNote": machine.get("operatorNotes"),
                "resolutionNote": None,
            }
        )
    return rows


def _is_valid_maintenance_record(record: dict[str, Any]) -> bool:
    if not record.get("machine_id"):
        return False

    maintenance_evidence = [
        record.get("source_record_id"),
        record.get("timestamp_opened"),
        record.get("timestamp_closed"),
        record.get("issue"),
        record.get("resolution_note"),
        record.get("technician"),
    ]
    return any(value not in (None, "", "unknown") for value in maintenance_evidence)


def _parse_csv_text(csv_text: str) -> tuple[list[str], list[dict[str, str | None]], list[str]]:
    if not csv_text.strip():
        raise HTTPException(status_code=400, detail="Uploaded CSV file is empty")

    csv_file = io.StringIO(csv_text)
    reader = csv.DictReader(csv_file, skipinitialspace=True)

    if reader.fieldnames is None:
        return [], [], []

    headers: list[str] = []
    seen_headers: set[str] = set()
    parse_warnings: list[str] = []

    for header in reader.fieldnames:
        clean_header = (header or "").strip()
        if not clean_header:
            parse_warnings.append("CSV contains a blank header column")
            continue

        if clean_header in seen_headers:
            parse_warnings.append(f"CSV contains a duplicate header after trimming: {clean_header}")

        seen_headers.add(clean_header)
        headers.append(clean_header)

    rows: list[dict[str, str | None]] = []
    for row_number, raw_row in enumerate(reader, start=1):
        row: dict[str, str | None] = {}

        if raw_row.get(None):
            parse_warnings.append(f"Row {row_number} has extra values beyond the header columns")

        for raw_header in reader.fieldnames:
            clean_header = (raw_header or "").strip()
            if not clean_header:
                continue

            row[clean_header] = raw_row.get(raw_header)

        rows.append(row)

    return headers, rows, parse_warnings
