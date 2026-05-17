from __future__ import annotations

from collections import Counter
import re
from typing import Any

from .dashboard_data import get_machine_detail, get_machines, load_maintenance_logs
from .machine_store import load_machines
from .upload_logs import get_upload_logs_page


DEEP_REVIEW_SECTIONS = [
    "maintenance_history_summary",
    "recurring_failure_patterns",
    "downtime_and_cost_context",
    "root_cause_hypotheses",
    "recommended_actions",
    "technician_checklist",
]


def get_machines_page_profile(selector: str) -> dict[str, Any] | None:
    resolved = _resolve_machine(selector)
    if resolved is None:
        return None

    machine_id = resolved["machineId"]
    detail = get_machine_detail(machine_id) or {}
    detail_machine = detail.get("machine") if isinstance(detail.get("machine"), dict) else {}
    machine = _merge_machine_context(resolved.get("registryMachine"), detail_machine, resolved.get("apiMachine"))
    logs = _logs_for_machine(machine_id)
    sorted_logs = _sort_logs(logs)
    upload_page = get_upload_logs_page(machine_id=machine_id, limit=50, offset=0)

    maintenance_summary = _maintenance_summary(logs, sorted_logs)
    downtime_context = _downtime_context(machine, logs)
    machine_identity = _machine_identity(machine, machine_id)
    status_context = {
        "status": machine.get("status") or _status_from_logs(logs),
        "attentionLevel": detail.get("attentionLevel"),
        "attentionReasons": detail.get("attentionReasons") or [],
        "latestUploadStatus": _latest_upload_status(upload_page),
        "latestSourceFile": maintenance_summary.get("latestSourceFile") or machine.get("source"),
        "latestLogTime": maintenance_summary.get("latestLogTime"),
        "latestIssue": maintenance_summary.get("latestIssue"),
    }
    risk_signals = detail.get("riskSignals") or detail.get("operationalSignals") or []
    repeated_patterns = detail.get("patternMatches") or []

    return {
        "machine": machine_identity,
        "attentionLevel": status_context.get("attentionLevel") or status_context.get("status"),
        "attentionReasons": status_context.get("attentionReasons") or [],
        "operationalSummary": _dashboard_operational_summary(maintenance_summary),
        "operationalSignals": risk_signals,
        "patternMatches": repeated_patterns,
        "analysis": detail.get("analysis"),
        "statusContext": status_context,
        "sensorContext": _sensor_context(machine),
        "businessContext": {
            "criticality": machine.get("criticality"),
            "downtimeCostPerMinute": machine.get("downtimeCostPerMinute"),
            "estimatedDowntimeMinutes": machine.get("estimatedDowntimeMinutes"),
            "estimatedCostExposure": downtime_context.get("estimatedCostExposure"),
        },
        "maintenanceSummary": maintenance_summary,
        "downtimeContext": downtime_context,
        "riskSignals": risk_signals,
        "repeatedPatterns": repeated_patterns,
        "recentLogs": [_log_for_profile(log) for log in sorted_logs[:10]],
        "similarHistoricalEvents": detail.get("similarHistoricalEvents") or [],
        "affectedUploads": upload_page.get("uploads") or [],
        "rawExtractedFields": _raw_fields(machine),
        "dataAvailability": _data_availability(machine, logs, upload_page.get("uploads") or []),
    }


def get_machine_deep_review_placeholder(selector: str) -> dict[str, Any] | None:
    resolved = _resolve_machine(selector)
    if resolved is None:
        return None

    machine = _merge_machine_context(
        resolved.get("registryMachine"),
        resolved.get("apiMachine"),
    )
    return {
        "machineId": resolved["machineId"],
        "machineName": machine.get("name"),
        "reviewStatus": "not_started",
        "message": (
            "Machine Deep Review endpoint is wired. "
            "Full deep review AI logic will be implemented later."
        ),
        "sections": DEEP_REVIEW_SECTIONS,
        "review": None,
    }


def _resolve_machine(selector: str) -> dict[str, Any] | None:
    cleaned = _normalize_selector(selector)
    if not cleaned:
        return None

    api_machines = get_machines()
    registry_machines = load_machines()
    registry_by_id = {
        _normalize_selector(machine.get("machine_id")): machine
        for machine in registry_machines
        if machine.get("machine_id")
    }

    for machine in api_machines:
        machine_id = machine.get("id") or machine.get("machine_id")
        names = [machine.get("name"), machine.get("machine_name")]
        candidates = [_normalize_selector(machine_id), *[_normalize_selector(name) for name in names]]
        if cleaned in candidates:
            stable_id = str(machine_id or "").strip()
            if not stable_id:
                continue
            return {
                "machineId": stable_id,
                "apiMachine": machine,
                "registryMachine": registry_by_id.get(_normalize_selector(stable_id)),
            }

    for registry_machine in registry_machines:
        machine_id = str(registry_machine.get("machine_id") or "").strip()
        candidates = [
            _normalize_selector(machine_id),
            _normalize_selector(registry_machine.get("name")),
        ]
        if cleaned in candidates:
            return {
                "machineId": machine_id,
                "apiMachine": None,
                "registryMachine": registry_machine,
            }

    return None


def _merge_machine_context(*machines: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for machine in machines:
        if not isinstance(machine, dict):
            continue
        normalized = _normalize_machine_keys(machine)
        for key, value in normalized.items():
            if value not in (None, "", [], {}, "No values yet"):
                merged[key] = value
    return merged


def _normalize_machine_keys(machine: dict[str, Any]) -> dict[str, Any]:
    machine_id = machine.get("id") or machine.get("machine_id")
    install_year = machine.get("install_year")
    normalized = dict(machine)
    normalized.update(
        {
            "id": machine_id,
            "machine_id": machine_id,
            "name": machine.get("name") or machine.get("machine_name"),
            "type": machine.get("type") or machine.get("machine_type"),
            "zone": machine.get("zone") or machine.get("location") or machine.get("line"),
            "downtimeCostPerMinute": machine.get("downtimeCostPerMinute")
            or machine.get("downtime_cost_per_minute"),
            "installedDate": machine.get("installedDate") or machine.get("installed_date"),
        }
    )
    if not normalized.get("installedDate") and install_year:
        normalized["installedDate"] = str(install_year)
    return normalized


def _machine_identity(machine: dict[str, Any], machine_id: str) -> dict[str, Any]:
    resolved_id = machine.get("id") or machine.get("machine_id") or machine_id
    resolved_name = machine.get("name")
    resolved_type = machine.get("type")
    resolved_location = machine.get("location") or machine.get("zone")

    return {
        "id": resolved_id,
        "machine_id": resolved_id,
        "machineId": resolved_id,
        "name": resolved_name,
        "machineName": resolved_name,
        "type": resolved_type,
        "machineType": resolved_type,
        "zone": machine.get("zone"),
        "line": machine.get("line"),
        "location": resolved_location,
        "status": machine.get("status"),
        "manufacturer": machine.get("manufacturer"),
        "model": machine.get("model"),
        "installedDate": machine.get("installedDate"),
        "criticality": machine.get("criticality"),
        "downtimeCostPerMinute": machine.get("downtimeCostPerMinute"),
        "source": machine.get("source"),
    }


def _dashboard_operational_summary(maintenance_summary: dict[str, Any]) -> dict[str, Any]:
    matching_records = maintenance_summary.get("matchingHistoryRecords") or 0
    return {
        "matchingHistoryRecords": maintenance_summary.get("matchingHistoryRecords"),
        "recentUploadedRecords": maintenance_summary.get("recentUploadedRecords"),
        "highCriticalLogs": maintenance_summary.get("warningOrCriticalLogCount"),
        "openItems": maintenance_summary.get("openMaintenanceItems"),
        "totalLoggedDowntimeMinutes": maintenance_summary.get("totalLoggedDowntimeMinutes"),
        "mostCommonLoggedIssue": maintenance_summary.get("mostCommonLoggedIssue"),
        "lastLoggedIssue": maintenance_summary.get("latestIssue"),
        "latestUploadSource": maintenance_summary.get("latestSourceFile"),
        "latestLogTime": maintenance_summary.get("latestLogTime"),
        "matchedMachine": bool(matching_records),
    }


def _sensor_context(machine: dict[str, Any]) -> dict[str, Any]:
    sensor_summary = machine.get("sensorSummary") if isinstance(machine.get("sensorSummary"), dict) else {}
    return {
        "temperature": sensor_summary.get("temperature") or machine.get("temperature"),
        "vibration": sensor_summary.get("vibration") or machine.get("vibration"),
        "pressure": sensor_summary.get("pressure") or machine.get("pressure"),
        "runtimeHours": machine.get("runtimeHours"),
        "errorCount": machine.get("errorCount"),
        "lastMaintenance": machine.get("lastMaintenance"),
        "nextMaintenance": machine.get("nextMaintenance"),
        "maintenanceStatus": machine.get("maintenanceStatus"),
        "maintenanceOverdue": machine.get("maintenanceOverdue"),
        "energyUsage": machine.get("energyUsage"),
        "throughputPerHour": machine.get("throughputPerHour"),
    }


def _maintenance_summary(logs: list[dict[str, Any]], sorted_logs: list[dict[str, Any]]) -> dict[str, Any]:
    high_or_critical = [
        log for log in logs if str(log.get("severity") or "").lower() in {"high", "critical"}
    ]
    open_items = [
        log for log in logs if str(log.get("status") or "").lower() in {"open", "in_progress", "new", "created", "assigned", "working"}
    ]
    issue_counter = Counter(
        _clean_text(log.get("issue"))
        for log in logs
        if _clean_text(log.get("issue"))
    )
    latest_log = sorted_logs[0] if sorted_logs else {}
    total_downtime = sum(_number_or_zero(log.get("downtime_minutes")) for log in logs)
    total_labor = sum(_number_or_zero(log.get("labor_hours")) for log in logs)

    return {
        "matchingHistoryRecords": len(logs),
        "recentUploadedRecords": min(len(sorted_logs), 10),
        "warningOrCriticalLogCount": len(high_or_critical),
        "openMaintenanceItems": len(open_items),
        "totalLoggedDowntimeMinutes": _clean_number(total_downtime),
        "totalLaborHours": _clean_number(total_labor),
        "mostCommonLoggedIssue": issue_counter.most_common(1)[0][0] if issue_counter else None,
        "latestIssue": latest_log.get("issue"),
        "latestLogTime": latest_log.get("timestamp_opened") or latest_log.get("timestamp") or latest_log.get("ingested_at"),
        "latestSourceFile": latest_log.get("source"),
        "technicians": sorted({str(log.get("technician")) for log in logs if log.get("technician")}),
    }


def _downtime_context(machine: dict[str, Any], logs: list[dict[str, Any]]) -> dict[str, Any]:
    total_downtime = sum(_number_or_zero(log.get("downtime_minutes")) for log in logs)
    cost_per_minute = _number_or_zero(machine.get("downtimeCostPerMinute"))
    estimated_cost = total_downtime * cost_per_minute if cost_per_minute else None
    return {
        "downtimeCostPerMinute": machine.get("downtimeCostPerMinute"),
        "totalLoggedDowntimeMinutes": _clean_number(total_downtime),
        "estimatedCostExposure": _clean_number(estimated_cost) if estimated_cost is not None else None,
        "recordsWithDowntime": sum(1 for log in logs if _number_or_zero(log.get("downtime_minutes")) > 0),
    }


def _log_for_profile(log: dict[str, Any]) -> dict[str, Any]:
    return {
        "sourceRecordId": log.get("source_record_id"),
        "timestampOpened": log.get("timestamp_opened") or log.get("timestamp"),
        "timestampClosed": log.get("timestamp_closed"),
        "machineId": log.get("machine_id"),
        "issue": log.get("issue"),
        "severity": log.get("severity"),
        "status": log.get("status"),
        "operatorNote": log.get("operator_note"),
        "resolutionNote": log.get("resolution_note"),
        "downtimeMinutes": log.get("downtime_minutes"),
        "laborHours": log.get("labor_hours"),
        "technician": log.get("technician"),
        "sourceFile": log.get("source"),
        "sourceRowNumber": log.get("source_row_number"),
        "uploadId": log.get("upload_id"),
        "matchedMachine": log.get("matched_machine"),
    }


def _raw_fields(machine: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in machine.items()
        if value not in (None, "", [], {}, "No values yet")
    }


def _data_availability(
    machine: dict[str, Any],
    logs: list[dict[str, Any]],
    uploads: list[dict[str, Any]],
) -> dict[str, Any]:
    sensor = _sensor_context(machine)
    return {
        "hasRegistryMatch": bool(machine.get("machine_id") or machine.get("id")),
        "hasMaintenanceHistory": bool(logs),
        "hasAffectedUploads": bool(uploads),
        "hasSensorData": any(
            sensor.get(key) is not None for key in ("temperature", "vibration", "pressure", "runtimeHours", "errorCount")
        ),
        "missingCoreFields": [
            label
            for label, value in {
                "machineName": machine.get("name"),
                "machineType": machine.get("type"),
                "zone": machine.get("zone"),
                "downtimeCostPerMinute": machine.get("downtimeCostPerMinute"),
            }.items()
            if value in (None, "")
        ],
    }


def _logs_for_machine(machine_id: str) -> list[dict[str, Any]]:
    target = machine_id.upper()
    return [
        log
        for log in load_maintenance_logs()
        if str(log.get("machine_id") or "").upper() == target
    ]


def _sort_logs(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        logs,
        key=lambda log: str(log.get("timestamp_opened") or log.get("timestamp") or log.get("ingested_at") or ""),
        reverse=True,
    )


def _latest_upload_status(upload_page: dict[str, Any]) -> str | None:
    uploads = upload_page.get("uploads")
    if isinstance(uploads, list) and uploads:
        return uploads[0].get("status")
    return None


def _status_from_logs(logs: list[dict[str, Any]]) -> str:
    if not logs:
        return "unknown"
    if any(str(log.get("status") or "").lower() in {"open", "in_progress", "new", "created", "assigned", "working"} for log in logs):
        return "critical"
    if any(str(log.get("severity") or "").lower() in {"critical", "high"} for log in logs):
        return "critical"
    if any(str(log.get("severity") or "").lower() == "medium" for log in logs):
        return "warning"
    return "healthy"


def _normalize_selector(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _clean_text(value: Any) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text or text.lower() == "unknown":
        return None
    return text


def _number_or_zero(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _clean_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value
