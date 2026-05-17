from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from typing import Any

from .machine_csv_normalizer import calculate_dashboard_metrics
from .machine_store import DATA_DIR, load_machines


MAINTENANCE_LOGS_FILE = DATA_DIR / "maintenance_logs.json"
UPLOADED_MACHINES_FILE = DATA_DIR / "uploaded-machines.json"
DASHBOARD_METRICS_FILE = DATA_DIR / "dashboard-metrics.json"


def save_uploaded_machine_dataset(
    machines: list[dict[str, Any]],
    summary: dict[str, Any],
    upload_preview: dict[str, Any],
) -> None:
    unique_machines = _dedupe_machines_by_id(machines)
    _write_json(
        UPLOADED_MACHINES_FILE,
        unique_machines,
    )
    _write_json(
        DASHBOARD_METRICS_FILE,
        {
            "summary": calculate_dashboard_metrics(unique_machines),
            "uploadPreview": upload_preview,
        },
    )


def append_maintenance_logs(
    records: list[dict[str, Any]],
    upload_preview: dict[str, Any],
) -> int:
    existing_logs = load_maintenance_logs()
    updated_logs = [*existing_logs, *records]

    _write_json(MAINTENANCE_LOGS_FILE, updated_logs)
    _save_upload_preview(upload_preview)

    return len(updated_logs)


def get_dashboard_summary() -> dict[str, Any]:
    maintenance_logs = load_maintenance_logs()
    if maintenance_logs:
        return _dashboard_summary_from_maintenance_logs(maintenance_logs)

    uploaded_machines = load_uploaded_machines()
    metrics_document = _read_json_object(DASHBOARD_METRICS_FILE)

    if uploaded_machines and isinstance(metrics_document.get("summary"), dict):
        return metrics_document["summary"]

    return calculate_dashboard_metrics(get_machines())


def get_machines() -> list[dict[str, Any]]:
    uploaded_machines = load_uploaded_machines()
    if uploaded_machines:
        return uploaded_machines

    logs_by_machine = _logs_by_machine_id(load_maintenance_logs())
    return [
        _to_seed_api_machine(machine, logs_by_machine.get(str(machine["machine_id"]).upper(), []))
        for machine in load_machines()
    ]


def get_machine_detail(machine_id: str) -> dict[str, Any] | None:
    machine_lookup = {machine["id"].upper(): machine for machine in get_machines() if machine.get("id")}
    machine = machine_lookup.get(machine_id.upper())
    if machine is None:
        return None

    all_logs = load_maintenance_logs()
    machine_logs = _logs_by_machine_id(all_logs).get(machine["id"].upper(), [])
    similar_events = _similar_historical_events(machine_logs)
    operational_summary = _operational_summary(machine, machine_logs)
    operational_signals = _operational_signals(machine, machine_logs, operational_summary)
    attention_level, attention_reasons = _attention_from_operational_context(operational_summary, operational_signals)

    return {
        "machine": machine,
        "attentionLevel": attention_level,
        "attentionReasons": attention_reasons,
        "operationalSummary": operational_summary,
        "operationalSignals": operational_signals,
        "patternMatches": _pattern_matches(machine_logs),
        "similarHistoricalEvents": similar_events,
        "riskSignals": operational_signals,
        "similarPastFixes": similar_events,
        "recommendations": [],
        "recentLogs": [_to_api_log(log) for log in _sort_logs(machine_logs)[:5]],
        "analysis": machine.get("aiAnalysis"),
    }


def get_factory_map() -> dict[str, Any]:
    machines = get_machines()
    layout = _build_layout(machines)

    return {
        "layout": layout,
        "zones": _build_zones(layout),
        "bounds": _build_bounds(layout),
    }


def get_recent_logs(limit: int | None = 5) -> list[dict[str, Any]]:
    logs = load_maintenance_logs()
    sorted_logs = _sort_logs(logs)

    if limit is not None:
        sorted_logs = sorted_logs[:limit]

    return [_to_api_log(log) for log in sorted_logs]


def get_recent_alerts() -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    for machine in get_machines():
        status = str(machine.get("status") or "unknown")
        if status not in {"critical", "warning"}:
            continue

        machine_id = machine.get("id")
        flags = machine.get("anomalyFlags") or []
        primary_flag = flags[0] if flags else f"{status.title()} machine status"
        alerts.append(
            {
                "level": status,
                "message": f"{machine_id}: {primary_flag}" if machine_id else primary_flag,
                "timestamp": machine.get("nextMaintenance") or machine.get("lastMaintenance"),
            }
        )

    for log in load_maintenance_logs():
        severity = str(log.get("severity") or "").lower()
        if severity not in {"high", "critical"}:
            continue

        machine_id = str(log.get("machine_id") or "")
        issue = log.get("issue")
        timestamp = log.get("timestamp_opened") or log.get("timestamp")
        alerts.append(
            {
                "level": "critical" if severity == "critical" else "warning",
                "message": f"{machine_id} reported {issue}" if machine_id and issue else None,
                "timestamp": timestamp,
            }
        )

    return alerts[:8]


def get_upload_preview() -> dict[str, Any]:
    metrics_document = _read_json_object(DASHBOARD_METRICS_FILE)
    upload_preview = metrics_document.get("uploadPreview")
    if isinstance(upload_preview, dict):
        return upload_preview

    return {
        "detectedColumnMappings": [],
        "lastUpload": None,
        "warnings": [],
        "skippedRows": [],
    }


def get_empty_analysis(machine_id: str) -> dict[str, Any]:
    return {
        "machineId": machine_id,
        "predictedIssue": None,
        "rootCause": None,
        "recommendedAction": None,
        "urgency": None,
        "estimatedDowntimeHours": None,
        "estimatedSavings": None,
        "confidence": None,
    }


def load_uploaded_machines() -> list[dict[str, Any]]:
    return _dedupe_machines_by_id(_read_json_list(UPLOADED_MACHINES_FILE))


def load_maintenance_logs() -> list[dict[str, Any]]:
    return _read_json_list(MAINTENANCE_LOGS_FILE)


def _to_seed_api_machine(machine: dict[str, Any], machine_logs: list[dict[str, Any]]) -> dict[str, Any]:
    machine_id = str(machine["machine_id"])
    last_maintenance = _last_maintenance_timestamp(machine_logs)

    return {
        "id": machine_id,
        "machine_id": machine_id,
        "name": machine.get("name"),
        "type": machine.get("type"),
        "line": None,
        "location": machine.get("zone"),
        "zone": machine.get("zone"),
        "status": _status_from_logs(machine_logs),
        "riskScore": None,
        "criticality": machine.get("criticality"),
        "sensorSummary": {
            "temperature": None,
            "vibration": None,
            "pressure": None,
        },
        "runtimeHours": None,
        "errorCount": None,
        "lastMaintenance": last_maintenance,
        "nextMaintenance": None,
        "maintenanceOverdue": False,
        "maintenanceStatus": "unknown",
        "anomalyFlags": [],
        "downtimeCostPerMinute": machine.get("downtime_cost_per_minute"),
        "estimatedDowntimeMinutes": None,
        "estimatedCostExposure": None,
        "manufacturer": machine.get("manufacturer"),
        "model": machine.get("model"),
        "installedDate": str(machine.get("install_year")) if machine.get("install_year") else None,
        "operatorNotes": None,
        "maintenanceCount": None,
        "energyUsage": None,
        "throughputPerHour": None,
        "x": machine.get("x"),
        "y": machine.get("y"),
        "width": machine.get("width"),
        "height": machine.get("height"),
        "source": "machines.json",
        "aiAnalysis": None,
    }


def _to_api_log(log: dict[str, Any]) -> dict[str, Any]:
    machine_id = log.get("machine_id")
    timestamp = log.get("timestamp_opened") or log.get("timestamp")

    return {
        "time": timestamp,
        "machineId": machine_id,
        "event": log.get("issue") or log.get("operator_note"),
        "downtimeMinutes": log.get("downtime_minutes"),
        "technician": log.get("technician"),
        "status": log.get("status"),
    }


def _operational_summary(machine: dict[str, Any], machine_logs: list[dict[str, Any]]) -> dict[str, Any]:
    sorted_logs = _sort_logs(machine_logs)
    high_or_critical = [
        log
        for log in machine_logs
        if str(log.get("severity") or "").lower() in {"high", "critical"}
    ]
    open_items = [
        log
        for log in machine_logs
        if str(log.get("status") or "").lower() in {"open", "in_progress", "new", "created", "assigned", "working"}
    ]
    total_downtime = sum(_number_or_none(log.get("downtime_minutes")) or 0 for log in machine_logs)
    issue_counter = Counter(
        _normalize_pattern(log.get("issue"))
        for log in machine_logs
        if _normalize_pattern(log.get("issue"))
    )
    latest_log = sorted_logs[0] if sorted_logs else None
    latest_source = latest_log.get("source") if latest_log else machine.get("source")
    latest_issue = latest_log.get("issue") if latest_log else None

    return {
        "matchingHistoryRecords": len(machine_logs),
        "recentUploadedRecords": min(len(sorted_logs), 5),
        "highCriticalLogs": len(high_or_critical),
        "openItems": len(open_items),
        "totalLoggedDowntimeMinutes": int(total_downtime) if float(total_downtime).is_integer() else total_downtime,
        "mostCommonLoggedIssue": issue_counter.most_common(1)[0][0] if issue_counter else None,
        "lastLoggedIssue": latest_issue,
        "latestUploadSource": latest_source,
        "latestLogTime": latest_log.get("timestamp_opened") if latest_log else None,
        "matchedMachine": bool(machine_logs),
    }


def _operational_signals(
    machine: dict[str, Any],
    machine_logs: list[dict[str, Any]],
    summary: dict[str, Any],
) -> list[str]:
    signals: list[str] = []
    pattern_counts = _pattern_counts(machine_logs)
    repeated_patterns = [pattern for pattern, count in pattern_counts.items() if count >= 2]

    if summary["matchingHistoryRecords"]:
        signals.append(f"{summary['matchingHistoryRecords']} matching maintenance records found")
    else:
        signals.append("No matching uploaded maintenance history yet")

    if summary["highCriticalLogs"]:
        signals.append(f"{summary['highCriticalLogs']} high or critical maintenance records")

    if summary["openItems"]:
        signals.append(f"{summary['openItems']} open or unresolved maintenance items")

    if repeated_patterns:
        signals.append(f"Repeated pattern: {repeated_patterns[0]}")

    if summary["totalLoggedDowntimeMinutes"]:
        signals.append(f"{summary['totalLoggedDowntimeMinutes']} minutes of logged downtime")

    anomaly_flags = machine.get("anomalyFlags") or []
    signals.extend(str(flag) for flag in anomaly_flags)

    return signals


def _attention_from_operational_context(
    summary: dict[str, Any],
    operational_signals: list[str],
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if summary["openItems"]:
        reasons.append("Open maintenance work exists")
    if summary["highCriticalLogs"]:
        reasons.append("High or critical history was uploaded")
    if any(signal.startswith("Repeated pattern") for signal in operational_signals):
        reasons.append("Recurring issue pattern detected")
    if (summary["totalLoggedDowntimeMinutes"] or 0) >= 60:
        reasons.append("Logged downtime is above one hour")

    if summary["openItems"] or summary["highCriticalLogs"] >= 2:
        return "critical", reasons
    if summary["highCriticalLogs"] or len(reasons) >= 2:
        return "warning", reasons
    if summary["matchingHistoryRecords"]:
        return "observed", ["Maintenance history is available"]
    return "unknown", ["No matching upload-derived history yet"]


def _pattern_matches(machine_logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = _pattern_counts(machine_logs)
    return [
        {"pattern": pattern, "count": count}
        for pattern, count in counts.most_common(5)
    ]


def _similar_historical_events(machine_logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for log in _sort_logs(machine_logs)[:6]:
        pattern = _normalize_pattern(log.get("issue")) or _first_pattern_from_notes(log)
        events.append(
            {
                "date": log.get("timestamp_opened") or log.get("timestamp"),
                "machineId": log.get("machine_id"),
                "pattern": pattern,
                "issue": log.get("issue"),
                "note": log.get("operator_note"),
                "resolution": log.get("resolution_note"),
                "downtimeMinutes": log.get("downtime_minutes"),
                "source": log.get("source"),
            }
        )

    return events


def _pattern_counts(machine_logs: list[dict[str, Any]]) -> Counter[str]:
    patterns: list[str] = []
    for log in machine_logs:
        issue_pattern = _normalize_pattern(log.get("issue"))
        if issue_pattern:
            patterns.append(issue_pattern)
            continue

        note_pattern = _first_pattern_from_notes(log)
        if note_pattern:
            patterns.append(note_pattern)

    return Counter(patterns)


def _first_pattern_from_notes(log: dict[str, Any]) -> str | None:
    text = " ".join(
        str(value)
        for value in (log.get("operator_note"), log.get("resolution_note"), log.get("failure_code"))
        if value
    )
    normalized_text = text.lower()
    keywords = [
        "overheating",
        "vibration",
        "alarm",
        "bearing",
        "pressure",
        "leak",
        "sensor",
        "alignment",
        "belt",
        "motor",
        "spindle",
    ]
    for keyword in keywords:
        if keyword in normalized_text:
            return keyword.title()

    return None


def _normalize_pattern(value: Any) -> str | None:
    if value is None:
        return None

    cleaned = re.sub(r"\s+", " ", str(value).strip())
    if not cleaned or cleaned.lower() == "unknown":
        return None

    return cleaned[:80]


def _sort_logs(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        logs,
        key=lambda log: str(log.get("timestamp_opened") or log.get("timestamp") or log.get("ingested_at") or ""),
        reverse=True,
    )


def _dashboard_summary_from_maintenance_logs(logs: list[dict[str, Any]]) -> dict[str, Any]:
    logs_by_machine = _logs_by_machine_id(logs)
    registry_by_id = {
        str(machine["machine_id"]).upper(): machine
        for machine in load_machines()
        if machine.get("machine_id")
    }
    status_counts = {"healthy": 0, "warning": 0, "critical": 0, "unknown": 0}
    attention_scores: list[int] = []
    total_downtime = 0.0
    total_cost = 0.0

    for machine_id, machine_logs in logs_by_machine.items():
        status = _maintenance_status_for_dashboard(machine_logs)
        status_counts[status] += 1
        attention_scores.append(_attention_score(status))

        machine_downtime = sum(_number_or_none(log.get("downtime_minutes")) or 0 for log in machine_logs)
        total_downtime += machine_downtime

        cost_per_minute = _number_or_none(registry_by_id.get(machine_id, {}).get("downtime_cost_per_minute"))
        if cost_per_minute is not None:
            total_cost += machine_downtime * cost_per_minute

    average_score = round(sum(attention_scores) / len(attention_scores), 1) if attention_scores else None

    return {
        "totalMachines": len(logs_by_machine),
        "healthyCount": status_counts["healthy"],
        "warningCount": status_counts["warning"],
        "criticalCount": status_counts["critical"],
        "unknownCount": status_counts["unknown"],
        "averageRiskScore": average_score,
        "estimatedDowntimeRisk": int(total_downtime) if total_downtime.is_integer() else total_downtime,
        "estimatedCostRisk": int(total_cost) if total_cost.is_integer() else total_cost,
    }


def _maintenance_status_for_dashboard(machine_logs: list[dict[str, Any]]) -> str:
    if not machine_logs:
        return "unknown"

    has_open = any(
        str(log.get("status") or "").lower() in {"open", "in_progress", "new", "created", "assigned", "working"}
        for log in machine_logs
    )
    if has_open:
        return "critical"

    severities = {str(log.get("severity") or "").lower() for log in machine_logs}
    if severities.intersection({"critical", "high"}):
        return "critical"
    if "medium" in severities:
        return "warning"
    if severities.intersection({"low", "minor"}):
        return "healthy"

    return "unknown"


def _attention_score(status: str) -> int:
    if status == "critical":
        return 90
    if status == "warning":
        return 60
    if status == "healthy":
        return 20
    return 0


def _build_layout(machines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fallback_positions = _generated_positions(machines)
    layout: list[dict[str, Any]] = []

    for machine in machines:
        machine_id = str(machine.get("id") or machine.get("machine_id") or "")
        fallback = fallback_positions.get(machine_id, {})
        x = _number_or_none(machine.get("x")) if machine.get("x") is not None else fallback.get("x")
        y = _number_or_none(machine.get("y")) if machine.get("y") is not None else fallback.get("y")

        layout.append(
            {
                "machineId": machine_id,
                "x": x,
                "y": y,
                "width": _number_or_none(machine.get("width")) or 120,
                "height": _number_or_none(machine.get("height")) or 70,
                "zone": machine.get("zone") or machine.get("line") or machine.get("location"),
            }
        )

    return [item for item in layout if item["machineId"]]


def _generated_positions(machines: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for machine in machines:
        group_name = str(machine.get("line") or machine.get("zone") or machine.get("location") or "Unassigned")
        grouped.setdefault(group_name, []).append(machine)

    positions: dict[str, dict[str, int]] = {}
    for group_index, group_machines in enumerate(grouped.values()):
        for item_index, machine in enumerate(group_machines):
            machine_id = str(machine.get("id") or machine.get("machine_id") or "")
            if not machine_id:
                continue

            positions[machine_id] = {
                "x": 140 + (item_index * 190),
                "y": 120 + (group_index * 170),
            }

    return positions


def _build_zones(layout: list[dict[str, Any]]) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = {}

    for item in layout:
        zone = item.get("zone")
        if zone:
            grouped.setdefault(str(zone), []).append(item)

    for zone_name, items in grouped.items():
        x_values = [item["x"] for item in items if isinstance(item.get("x"), (int, float))]
        y_values = [item["y"] for item in items if isinstance(item.get("y"), (int, float))]
        if not x_values or not y_values:
            zones.append({"name": zone_name, "x": None, "y": None, "width": None, "height": None})
            continue

        min_x = min(x_values)
        max_x = max(x_values)
        min_y = min(y_values)
        max_y = max(y_values)
        zones.append(
            {
                "name": zone_name,
                "x": max(min_x - 70, 0),
                "y": max(min_y - 55, 0),
                "width": max((max_x - min_x) + 160, 160),
                "height": max((max_y - min_y) + 125, 120),
            }
        )

    return zones


def _build_bounds(layout: list[dict[str, Any]]) -> dict[str, float]:
    max_x = max((item.get("x") or 0) + (item.get("width") or 0) for item in layout) if layout else 0
    max_y = max((item.get("y") or 0) + (item.get("height") or 0) for item in layout) if layout else 0
    return {
        "width": max(max_x, 1),
        "height": max(max_y, 1),
    }


def _status_from_logs(machine_logs: list[dict[str, Any]]) -> str:
    if not machine_logs:
        return "unknown"

    has_high = any(str(log.get("severity") or "").lower() in {"high", "critical"} for log in machine_logs)
    if has_high:
        return "critical"

    has_medium = any(str(log.get("severity") or "").lower() == "medium" for log in machine_logs)
    if has_medium:
        return "warning"

    return "healthy"


def _last_maintenance_timestamp(machine_logs: list[dict[str, Any]]) -> str | None:
    timestamps = [
        str(log.get("timestamp_opened") or log.get("timestamp"))
        for log in machine_logs
        if log.get("timestamp_opened") or log.get("timestamp")
    ]
    return max(timestamps) if timestamps else None


def _logs_by_machine_id(logs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for log in logs:
        machine_id = log.get("machine_id")
        if machine_id:
            grouped.setdefault(str(machine_id).upper(), []).append(log)
    return grouped


def _dedupe_machines_by_id(machines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique_by_id: dict[str, dict[str, Any]] = {}
    for machine in machines:
        machine_id = machine.get("id") or machine.get("machine_id")
        if machine_id:
            unique_by_id[str(machine_id).upper()] = machine

    return list(unique_by_id.values())


def _number_or_none(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value

    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None

    return int(number) if number.is_integer() else number


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}

    data = json.loads(text)
    if not isinstance(data, dict):
        return {}

    return data


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"{path.name} must contain a JSON list")

    return [item for item in data if isinstance(item, dict)]


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _save_upload_preview(upload_preview: dict[str, Any]) -> None:
    metrics_document = _read_json_object(DASHBOARD_METRICS_FILE)
    metrics_document["uploadPreview"] = upload_preview
    _write_json(DASHBOARD_METRICS_FILE, metrics_document)
