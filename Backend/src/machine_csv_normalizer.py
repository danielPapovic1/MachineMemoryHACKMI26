from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
import math
import re
from typing import Any

from .cue_bank import normalize_column_name, tokenize_column_name


MACHINE_FIELDS = [
    "machine_id",
    "machine_name",
    "machine_type",
    "line",
    "zone",
    "location",
    "status",
    "temperature",
    "vibration",
    "pressure",
    "runtime_hours",
    "error_count",
    "last_maintenance",
    "next_maintenance",
    "downtime_cost_per_minute",
    "criticality",
    "x",
    "y",
    "width",
    "height",
    "manufacturer",
    "model",
    "installed_date",
    "operator_notes",
    "maintenance_count",
    "energy_usage",
    "throughput_per_hour",
]

FIELD_CUES: dict[str, list[str]] = {
    "machine_id": ["machine_id", "machine id", "asset id", "equipment id", "machine", "asset", "equipment", "unit id"],
    "machine_name": ["machine_name", "machine name", "asset name", "equipment name", "line name", "display name"],
    "machine_type": ["machine_type", "machine type", "asset type", "equipment type", "type", "category"],
    "line": ["line", "production line", "line code", "line name"],
    "zone": ["zone", "plant zone", "area", "department", "factory area", "work area"],
    "location": ["location", "machine location", "asset location", "plant location", "position"],
    "status": ["status", "machine status", "health", "health status", "state", "condition"],
    "temperature": ["temperature", "temp", "temperature c", "temperature f", "bearing temperature"],
    "vibration": ["vibration", "vibration level", "vibration mm s", "vibration score"],
    "pressure": ["pressure", "hydraulic pressure", "air pressure", "line pressure"],
    "runtime_hours": ["runtime_hours", "runtime hours", "run hours", "operating hours", "hours run"],
    "error_count": ["error_count", "error count", "fault count", "alarm count", "failures", "events"],
    "last_maintenance": ["last_maintenance", "last maintenance", "last pm", "last service", "last repair"],
    "next_maintenance": ["next_maintenance", "next maintenance", "next pm", "next service", "pm due"],
    "downtime_cost_per_minute": [
        "downtime_cost_per_minute",
        "downtime cost per minute",
        "cost per minute",
        "downtime cost",
        "cost min",
    ],
    "criticality": ["criticality", "criticality level", "priority", "importance", "asset criticality"],
    "x": ["x", "x position", "map x", "layout x"],
    "y": ["y", "y position", "map y", "layout y"],
    "width": ["width", "map width", "layout width"],
    "height": ["height", "map height", "layout height"],
    "manufacturer": ["manufacturer", "make", "vendor", "oem"],
    "model": ["model", "model number", "asset model", "equipment model"],
    "installed_date": ["installed_date", "installed date", "install date", "commissioned date"],
    "operator_notes": ["operator_notes", "operator notes", "notes", "operator comments", "comments"],
    "maintenance_count": ["maintenance_count", "maintenance count", "pm count", "service count"],
    "energy_usage": ["energy_usage", "energy usage", "power usage", "kwh"],
    "throughput_per_hour": ["throughput_per_hour", "throughput per hour", "throughput", "units per hour"],
}

KEYWORD_RULES: dict[str, dict[str, int]] = {
    "machine_id": {"machine": 4, "asset": 4, "equipment": 4, "unit": 3, "id": 4, "tag": 2},
    "machine_name": {"machine": 3, "asset": 3, "equipment": 3, "name": 4, "display": 2},
    "machine_type": {"machine": 2, "asset": 2, "equipment": 2, "type": 5, "category": 3},
    "line": {"line": 5, "production": 2},
    "zone": {"zone": 5, "area": 4, "department": 4, "plant": 2, "factory": 2},
    "location": {"location": 5, "loc": 4, "position": 2},
    "status": {"status": 5, "health": 4, "state": 4, "condition": 3},
    "temperature": {"temperature": 5, "temp": 5, "bearing": 2},
    "vibration": {"vibration": 5, "vib": 5},
    "pressure": {"pressure": 5, "hydraulic": 2, "air": 2},
    "runtime_hours": {"runtime": 5, "run": 3, "operating": 3, "hours": 4},
    "error_count": {"error": 5, "fault": 4, "alarm": 4, "count": 3, "failures": 3, "events": 2},
    "last_maintenance": {"last": 4, "maintenance": 3, "pm": 3, "service": 2, "repair": 2},
    "next_maintenance": {"next": 4, "due": 3, "maintenance": 3, "pm": 3, "service": 2},
    "downtime_cost_per_minute": {"downtime": 4, "cost": 5, "minute": 3, "min": 3},
    "criticality": {"criticality": 5, "critical": 4, "priority": 3, "importance": 2},
    "x": {"x": 5, "map": 1, "layout": 1},
    "y": {"y": 5, "map": 1, "layout": 1},
    "width": {"width": 5},
    "height": {"height": 5},
    "manufacturer": {"manufacturer": 5, "make": 4, "vendor": 3, "oem": 3},
    "model": {"model": 5},
    "installed_date": {"installed": 5, "install": 4, "commissioned": 4, "date": 2},
    "operator_notes": {"operator": 3, "notes": 4, "comments": 4},
    "maintenance_count": {"maintenance": 3, "pm": 3, "service": 2, "count": 4},
    "energy_usage": {"energy": 5, "power": 3, "usage": 3, "kwh": 5},
    "throughput_per_hour": {"throughput": 5, "units": 3, "hour": 2},
}

EXACT_CONFIDENCE = 1.0
FUZZY_MIN_CONFIDENCE = 0.86
FUZZY_MIN_MARGIN = 0.04
KEYWORD_MIN_SCORE = 4
KEYWORD_MIN_MARGIN = 2

_FIELD_PRIORITY = {field: index for index, field in enumerate(MACHINE_FIELDS)}
_EXACT_LOOKUP = {
    normalize_column_name(cue): field
    for field, cues in FIELD_CUES.items()
    for cue in cues
}
_FUZZY_CUES = [
    (normalize_column_name(cue), cue, field)
    for field, cues in FIELD_CUES.items()
    for cue in cues
]


@dataclass(frozen=True)
class MachineColumnMapping:
    uploaded_column: str
    normalized_field: str
    strategy: str
    confidence: float
    matched_cue: str | None = None


@dataclass(frozen=True)
class MachineUnmappedColumn:
    uploaded_column: str
    reason: str


@dataclass(frozen=True)
class MachineSkippedRow:
    row_number: int
    reason: str


def normalize_machine_csv_rows(
    headers: Sequence[str],
    rows: Sequence[Mapping[str, str | None]],
    source: str,
) -> dict[str, Any]:
    mapping_result = detect_machine_column_mappings(headers)
    mappings: dict[str, MachineColumnMapping] = mapping_result["active_mappings"]
    warnings = list(mapping_result["warnings"])
    skipped_rows: list[MachineSkippedRow] = []
    machines: list[dict[str, Any]] = []

    for row_index, row in enumerate(rows, start=1):
        if _is_empty_row(row):
            skipped_rows.append(MachineSkippedRow(row_number=row_index, reason="Row is empty"))
            continue

        raw_machine = {field: None for field in MACHINE_FIELDS}
        for mapping in mappings.values():
            raw_machine[mapping.normalized_field] = _clean_text(row.get(mapping.uploaded_column))

        machine_id = _normalize_machine_id(raw_machine.get("machine_id"))
        if machine_id is None:
            skipped_rows.append(MachineSkippedRow(row_number=row_index, reason="Missing machine_id"))
            continue

        machines.append(_enrich_machine(raw_machine, machine_id, source))

    unique_machines, duplicate_warnings = _dedupe_machines_by_id(machines)
    warnings.extend(duplicate_warnings)
    metrics = calculate_dashboard_metrics(unique_machines)

    return {
        "source": source,
        "row_count": len(rows),
        "normalized_count": len(unique_machines),
        "raw_normalized_count": len(machines),
        "detected_column_mappings": [asdict(mapping) for mapping in mapping_result["detected_mappings"]],
        "normalized_machines": unique_machines,
        "dashboard_summary": metrics,
        "unmapped_columns": [asdict(column) for column in mapping_result["unmapped_columns"]],
        "warnings": warnings,
        "skipped_rows": [asdict(row) for row in skipped_rows],
    }


def calculate_dashboard_metrics(machines: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    machines = _unique_machine_sequence(machines)
    status_counts = {"healthy": 0, "warning": 0, "critical": 0, "unknown": 0}
    risk_scores: list[float] = []
    downtime_values: list[float] = []
    cost_values: list[float] = []

    for machine in machines:
        status = str(machine.get("status") or "unknown")
        if status not in status_counts:
            status = "unknown"
        status_counts[status] += 1

        risk_score = machine.get("riskScore")
        if isinstance(risk_score, (int, float)):
            risk_scores.append(float(risk_score))

        downtime = machine.get("estimatedDowntimeMinutes")
        if isinstance(downtime, (int, float)):
            downtime_values.append(float(downtime))

        cost = machine.get("estimatedCostExposure")
        if isinstance(cost, (int, float)):
            cost_values.append(float(cost))

    average_risk = round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else None

    return {
        "totalMachines": len(machines),
        "healthyCount": status_counts["healthy"],
        "warningCount": status_counts["warning"],
        "criticalCount": status_counts["critical"],
        "unknownCount": status_counts["unknown"],
        "averageRiskScore": average_risk,
        "estimatedDowntimeRisk": sum(downtime_values) if downtime_values else None,
        "estimatedCostRisk": sum(cost_values) if cost_values else None,
    }


def _dedupe_machines_by_id(machines: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    unique_by_id: dict[str, dict[str, Any]] = {}
    duplicate_counts: dict[str, int] = {}

    for machine in machines:
        machine_id = _machine_identity(machine)
        if not machine_id:
            continue

        if machine_id in unique_by_id:
            duplicate_counts[machine_id] = duplicate_counts.get(machine_id, 1) + 1

        unique_by_id[machine_id] = machine

    warnings = [
        f"Duplicate machine_id {machine_id} appeared {count} times; kept the latest row for dashboard metrics"
        for machine_id, count in sorted(duplicate_counts.items())
    ]
    return list(unique_by_id.values()), warnings


def _unique_machine_sequence(machines: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    unique_by_id: dict[str, Mapping[str, Any]] = {}

    for machine in machines:
        machine_id = _machine_identity(machine)
        if not machine_id:
            continue

        unique_by_id[machine_id] = machine

    return list(unique_by_id.values())


def _machine_identity(machine: Mapping[str, Any]) -> str | None:
    machine_id = machine.get("id") or machine.get("machine_id")
    cleaned = _clean_text(machine_id)
    return cleaned.upper() if cleaned else None


def detect_machine_column_mappings(headers: Sequence[str]) -> dict[str, Any]:
    mappings_by_column: dict[str, MachineColumnMapping] = {}
    unmapped_columns: list[MachineUnmappedColumn] = []

    for header in headers:
        clean_header = header.strip()
        if not clean_header:
            unmapped_columns.append(MachineUnmappedColumn(uploaded_column=header, reason="Blank header"))
            continue

        mapping = _match_column(clean_header)
        if mapping is None:
            unmapped_columns.append(
                MachineUnmappedColumn(uploaded_column=clean_header, reason="No confident machine-field match")
            )
            continue

        mappings_by_column[clean_header] = mapping

    active_mappings, warnings, duplicate_unmapped = _resolve_duplicate_mappings(mappings_by_column)
    unmapped_columns.extend(duplicate_unmapped)

    if "machine_id" not in active_mappings:
        warnings.append("Missing required machine_id mapping; rows without machine_id will be skipped")

    return {
        "detected_mappings": list(active_mappings.values()),
        "active_mappings": active_mappings,
        "unmapped_columns": unmapped_columns,
        "warnings": warnings,
    }


def _match_column(column_name: str) -> MachineColumnMapping | None:
    normalized_name = normalize_column_name(column_name)

    exact_field = _EXACT_LOOKUP.get(normalized_name)
    if exact_field:
        return MachineColumnMapping(column_name, exact_field, "cue_bank_exact", EXACT_CONFIDENCE, column_name)

    fuzzy_match = _fuzzy_match(column_name, normalized_name)
    if fuzzy_match:
        return fuzzy_match

    return _keyword_match(column_name)


def _fuzzy_match(column_name: str, normalized_name: str) -> MachineColumnMapping | None:
    scored = [
        (SequenceMatcher(None, normalized_name, normalized_cue).ratio(), cue, field)
        for normalized_cue, cue, field in _FUZZY_CUES
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return None

    best_score, best_cue, best_field = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0

    if best_score < FUZZY_MIN_CONFIDENCE or best_score - second_score < FUZZY_MIN_MARGIN:
        return None

    return MachineColumnMapping(column_name, best_field, "fuzzy", round(best_score, 3), best_cue)


def _keyword_match(column_name: str) -> MachineColumnMapping | None:
    tokens = tokenize_column_name(column_name)
    normalized_name = normalize_column_name(column_name)
    scored_fields: list[tuple[int, str]] = []

    for field, keywords in KEYWORD_RULES.items():
        score = 0
        for keyword, weight in keywords.items():
            normalized_keyword = normalize_column_name(keyword)
            if normalized_keyword in tokens:
                score += weight
            elif " " in normalized_keyword and normalized_keyword in normalized_name:
                score += weight

        if score:
            scored_fields.append((score, field))

    scored_fields.sort(key=lambda item: (item[0], -_FIELD_PRIORITY[item[1]]), reverse=True)
    if not scored_fields:
        return None

    best_score, best_field = scored_fields[0]
    second_score = scored_fields[1][0] if len(scored_fields) > 1 else 0
    if best_score < KEYWORD_MIN_SCORE or best_score - second_score < KEYWORD_MIN_MARGIN:
        return None

    confidence = min(0.84, 0.55 + (best_score / 20))
    return MachineColumnMapping(column_name, best_field, "keyword", round(confidence, 3), ", ".join(tokens))


def _resolve_duplicate_mappings(
    mappings_by_column: Mapping[str, MachineColumnMapping],
) -> tuple[dict[str, MachineColumnMapping], list[str], list[MachineUnmappedColumn]]:
    mappings_by_field: dict[str, MachineColumnMapping] = {}
    warnings: list[str] = []
    unmapped_columns: list[MachineUnmappedColumn] = []

    for mapping in mappings_by_column.values():
        existing = mappings_by_field.get(mapping.normalized_field)
        if existing is None:
            mappings_by_field[mapping.normalized_field] = mapping
            continue

        winner, loser = _choose_mapping(existing, mapping)
        mappings_by_field[mapping.normalized_field] = winner
        unmapped_columns.append(
            MachineUnmappedColumn(
                uploaded_column=loser.uploaded_column,
                reason=f"Duplicate mapping for {loser.normalized_field}; kept {winner.uploaded_column}",
            )
        )
        warnings.append(
            f"Duplicate mapping for {winner.normalized_field}: kept {winner.uploaded_column}, ignored {loser.uploaded_column}"
        )

    return mappings_by_field, warnings, unmapped_columns


def _choose_mapping(
    first: MachineColumnMapping,
    second: MachineColumnMapping,
) -> tuple[MachineColumnMapping, MachineColumnMapping]:
    strategy_rank = {"cue_bank_exact": 3, "fuzzy": 2, "keyword": 1}
    first_score = (first.confidence, strategy_rank.get(first.strategy, 0))
    second_score = (second.confidence, strategy_rank.get(second.strategy, 0))

    if second_score > first_score:
        return second, first

    return first, second


def _enrich_machine(raw_machine: Mapping[str, Any], machine_id: str, source: str) -> dict[str, Any]:
    temperature = _parse_number(raw_machine.get("temperature"))
    vibration = _parse_number(raw_machine.get("vibration"))
    pressure = _parse_number(raw_machine.get("pressure"))
    error_count = _parse_number(raw_machine.get("error_count"))
    criticality = _normalize_criticality(raw_machine.get("criticality"))
    status = _normalize_status(raw_machine.get("status")) or _infer_status(temperature, vibration, pressure, error_count)
    risk_score = _calculate_risk_score(temperature, vibration, pressure, error_count, criticality)
    maintenance_status = _maintenance_status(raw_machine.get("next_maintenance"))
    maintenance_overdue = maintenance_status == "overdue"
    anomaly_flags = _anomaly_flags(temperature, vibration, pressure, error_count, maintenance_overdue)
    estimated_downtime = _estimated_downtime(status)
    cost_per_minute = _parse_number(raw_machine.get("downtime_cost_per_minute"))
    estimated_cost = estimated_downtime * cost_per_minute if estimated_downtime is not None and cost_per_minute is not None else None
    line = _clean_text(raw_machine.get("line"))
    zone = _clean_text(raw_machine.get("zone"))
    location = _clean_text(raw_machine.get("location")) or _combined_location(line, zone)

    return {
        "id": machine_id,
        "machine_id": machine_id,
        "name": _clean_text(raw_machine.get("machine_name")),
        "type": _clean_text(raw_machine.get("machine_type")),
        "line": line,
        "zone": zone,
        "location": location,
        "status": status,
        "riskScore": risk_score,
        "criticality": criticality,
        "sensorSummary": {
            "temperature": temperature,
            "vibration": vibration,
            "pressure": pressure,
        },
        "runtimeHours": _parse_number(raw_machine.get("runtime_hours")),
        "errorCount": error_count,
        "lastMaintenance": _clean_text(raw_machine.get("last_maintenance")),
        "nextMaintenance": _clean_text(raw_machine.get("next_maintenance")),
        "maintenanceOverdue": maintenance_overdue,
        "maintenanceStatus": maintenance_status,
        "anomalyFlags": anomaly_flags,
        "downtimeCostPerMinute": cost_per_minute,
        "estimatedDowntimeMinutes": estimated_downtime,
        "estimatedCostExposure": estimated_cost,
        "manufacturer": _clean_text(raw_machine.get("manufacturer")),
        "model": _clean_text(raw_machine.get("model")),
        "installedDate": _clean_text(raw_machine.get("installed_date")),
        "operatorNotes": _clean_text(raw_machine.get("operator_notes")),
        "maintenanceCount": _parse_number(raw_machine.get("maintenance_count")),
        "energyUsage": _parse_number(raw_machine.get("energy_usage")),
        "throughputPerHour": _parse_number(raw_machine.get("throughput_per_hour")),
        "x": _parse_number(raw_machine.get("x")),
        "y": _parse_number(raw_machine.get("y")),
        "width": _parse_number(raw_machine.get("width")),
        "height": _parse_number(raw_machine.get("height")),
        "source": source,
        "aiAnalysis": None,
    }


def _calculate_risk_score(
    temperature: float | None,
    vibration: float | None,
    pressure: float | None,
    error_count: float | None,
    criticality: str | None,
) -> int | None:
    weighted_scores: list[tuple[float, float]] = []

    _append_score(weighted_scores, _threshold_score(temperature, 85, 95), 0.25)
    _append_score(weighted_scores, _threshold_score(vibration, 0.70, 0.90), 0.30)
    _append_score(weighted_scores, _threshold_score(pressure, 120, 140), 0.15)
    _append_score(weighted_scores, _threshold_score(error_count, 4, 10), 0.20)
    _append_score(weighted_scores, _criticality_score(criticality), 0.10)

    total_weight = sum(weight for _, weight in weighted_scores)
    if total_weight <= 0:
        return None

    risk_score = sum(score * weight for score, weight in weighted_scores) / total_weight
    return int(round(min(max(risk_score, 0), 100)))


def _append_score(weighted_scores: list[tuple[float, float]], score: float | None, weight: float) -> None:
    if score is not None:
        weighted_scores.append((score, weight))


def _threshold_score(value: float | None, warning_threshold: float, critical_threshold: float) -> float | None:
    if value is None:
        return None
    if value >= critical_threshold:
        return 100
    if value >= warning_threshold:
        span = critical_threshold - warning_threshold
        if span <= 0:
            return 70
        return 65 + ((value - warning_threshold) / span) * 30
    return min((value / warning_threshold) * 40, 40)


def _criticality_score(criticality: str | None) -> float | None:
    if criticality == "high":
        return 100
    if criticality == "medium":
        return 55
    if criticality == "low":
        return 15
    return None


def _normalize_status(value: Any) -> str | None:
    cleaned = normalize_column_name(str(value)) if _clean_text(value) else None
    if cleaned is None:
        return None

    if cleaned in {"healthy", "good", "normal", "ok", "running", "closed", "complete"}:
        return "healthy"
    if cleaned in {"warning", "watch", "degraded", "caution", "medium"}:
        return "warning"
    if cleaned in {"critical", "high", "down", "failed", "failure", "stopped"}:
        return "critical"
    if cleaned in {"unknown", "n a", "na", "none"}:
        return "unknown"

    return cleaned.replace(" ", "_")


def _infer_status(
    temperature: float | None,
    vibration: float | None,
    pressure: float | None,
    error_count: float | None,
) -> str:
    values = [temperature, vibration, pressure, error_count]
    if all(value is None for value in values):
        return "unknown"
    if (
        _at_or_above(temperature, 95)
        or _at_or_above(vibration, 0.90)
        or _at_or_above(pressure, 140)
        or _at_or_above(error_count, 10)
    ):
        return "critical"
    if (
        _at_or_above(temperature, 85)
        or _at_or_above(vibration, 0.70)
        or _at_or_above(pressure, 120)
        or _at_or_above(error_count, 4)
    ):
        return "warning"
    return "healthy"


def _anomaly_flags(
    temperature: float | None,
    vibration: float | None,
    pressure: float | None,
    error_count: float | None,
    maintenance_overdue: bool,
) -> list[str]:
    flags: list[str] = []
    if _at_or_above(temperature, 85):
        flags.append("High temperature")
    if _at_or_above(vibration, 0.70):
        flags.append("Elevated vibration")
    if _at_or_above(pressure, 120):
        flags.append("Pressure outside normal range")
    if _at_or_above(error_count, 4):
        flags.append("Repeated error events")
    if maintenance_overdue:
        flags.append("Maintenance overdue")
    return flags


def _maintenance_status(next_maintenance: Any) -> str:
    parsed_date = _parse_date(_clean_text(next_maintenance))
    if parsed_date is None:
        return "unknown"

    today = date.today()
    if parsed_date < today:
        return "overdue"
    if (parsed_date - today).days <= 14:
        return "due_soon"
    return "up_to_date"


def _estimated_downtime(status: str) -> int | None:
    if status == "critical":
        return 240
    if status == "warning":
        return 90
    if status == "healthy":
        return 0
    return None


def _normalize_criticality(value: Any) -> str | None:
    cleaned = normalize_column_name(str(value)) if _clean_text(value) else None
    if cleaned is None:
        return None

    if cleaned in {"high", "h", "critical", "p1", "urgent"}:
        return "high"
    if cleaned in {"medium", "med", "m", "p2", "moderate"}:
        return "medium"
    if cleaned in {"low", "l", "p3", "minor"}:
        return "low"
    return cleaned.replace(" ", "_")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None


def _combined_location(line: str | None, zone: str | None) -> str | None:
    parts = [part for part in (line, zone) if part]
    return " / ".join(parts) if parts else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    cleaned = str(value).strip()
    return cleaned if cleaned else None


def _normalize_machine_id(value: Any) -> str | None:
    cleaned = _clean_text(value)
    return cleaned.upper() if cleaned else None


def _parse_number(value: Any) -> float | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", cleaned.replace(",", ""))
    if not match:
        return None

    number = float(match.group(0))
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def _at_or_above(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def _is_empty_row(row: Mapping[str, str | None]) -> bool:
    return all(_clean_text(value) is None for value in row.values())
