from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import re
from typing import Any

from .cue_bank import (
    BACKEND_CREATED_FIELDS,
    EXACT_CUE_LOOKUP,
    EXACT_MATCH_CONFIDENCE,
    FIELD_CUES,
    FIELD_PRIORITY,
    FUZZY_MATCH_MIN_CONFIDENCE,
    FUZZY_MATCH_MIN_MARGIN,
    IGNORED_COLUMN_CUES,
    KEYWORD_MATCH_MIN_MARGIN,
    KEYWORD_MATCH_MIN_SCORE,
    KEYWORD_RULES,
    NORMALIZED_FIELDS,
    REQUIRED_OR_NEAR_REQUIRED_FIELDS,
    STRONGLY_PREFERRED_FIELDS,
    normalize_column_name,
    tokenize_column_name,
)


@dataclass(frozen=True)
class ColumnMapping:
    uploaded_column: str
    normalized_field: str
    strategy: str
    confidence: float
    matched_cue: str | None = None


@dataclass(frozen=True)
class UnmappedColumn:
    uploaded_column: str
    reason: str


@dataclass(frozen=True)
class SkippedRow:
    row_number: int
    reason: str


_FUZZY_CUES = [
    (normalize_column_name(cue), cue, field)
    for field, cues in FIELD_CUES.items()
    for cue in cues
    if field not in BACKEND_CREATED_FIELDS
]


def normalize_csv_rows(
    headers: Sequence[str],
    rows: Sequence[Mapping[str, str | None]],
    source: str,
    known_machine_ids: set[str],
) -> dict[str, Any]:
    mapping_result = detect_column_mappings(headers)
    active_mappings = mapping_result["active_mappings"]
    warnings = list(mapping_result["warnings"])
    skipped_rows: list[SkippedRow] = []
    normalized_records: list[dict[str, Any]] = []

    known_machine_lookup = {machine_id.strip().upper() for machine_id in known_machine_ids}

    for row_index, raw_row in enumerate(rows, start=1):
        if _is_empty_row(raw_row):
            skipped_rows.append(SkippedRow(row_number=row_index, reason="Row is empty"))
            continue

        record = _new_record(source)

        for mapping in active_mappings.values():
            raw_value = raw_row.get(mapping.uploaded_column)
            record[mapping.normalized_field] = _clean_text(raw_value)

        row_warnings = _coerce_record_values(record, row_index)
        warnings.extend(row_warnings)

        machine_id = record.get("machine_id")
        record["matched_machine"] = bool(machine_id and str(machine_id).upper() in known_machine_lookup)

        missing_fields = [
            field
            for field in REQUIRED_OR_NEAR_REQUIRED_FIELDS
            if record.get(field) in (None, "", "unknown")
        ]
        if missing_fields:
            warnings.append(
                f"Row {row_index} is missing or defaulted required fields: {', '.join(sorted(missing_fields))}"
            )

        normalized_records.append(record)

    return {
        "detected_column_mappings": [asdict(mapping) for mapping in mapping_result["detected_mappings"]],
        "normalized_records": normalized_records,
        "unmapped_columns": [asdict(column) for column in mapping_result["unmapped_columns"]],
        "row_count": len(rows),
        "normalized_count": len(normalized_records),
        "warnings": warnings,
        "skipped_rows": [asdict(row) for row in skipped_rows],
    }


def detect_column_mappings(headers: Sequence[str]) -> dict[str, Any]:
    detected_by_column: dict[str, ColumnMapping] = {}
    unmapped_columns: list[UnmappedColumn] = []
    warnings: list[str] = []

    for header in headers:
        clean_header = header.strip()
        normalized_header = normalize_column_name(clean_header)

        if not normalized_header:
            unmapped_columns.append(UnmappedColumn(uploaded_column=header, reason="Blank header"))
            continue

        if normalized_header in IGNORED_COLUMN_CUES:
            unmapped_columns.append(
                UnmappedColumn(uploaded_column=clean_header, reason="Known non-core column for this proof of concept")
            )
            continue

        mapping = _match_column(clean_header)
        if mapping is None:
            unmapped_columns.append(
                UnmappedColumn(uploaded_column=clean_header, reason="No confident exact, fuzzy, or keyword match")
            )
            continue

        detected_by_column[clean_header] = mapping

    active_mappings, duplicate_warnings, duplicate_unmapped = _resolve_duplicate_field_mappings(detected_by_column)
    warnings.extend(duplicate_warnings)
    unmapped_columns.extend(duplicate_unmapped)

    mapped_fields = set(active_mappings)
    missing_required = sorted(REQUIRED_OR_NEAR_REQUIRED_FIELDS.difference(mapped_fields))
    if missing_required:
        warnings.append(f"Missing required or near-required mappings: {', '.join(missing_required)}")

    missing_preferred = sorted(STRONGLY_PREFERRED_FIELDS.difference(mapped_fields))
    if missing_preferred:
        warnings.append(f"Missing preferred mappings: {', '.join(missing_preferred)}")

    return {
        "detected_mappings": list(active_mappings.values()),
        "active_mappings": active_mappings,
        "unmapped_columns": unmapped_columns,
        "warnings": warnings,
    }


def _match_column(column_name: str) -> ColumnMapping | None:
    normalized_name = normalize_column_name(column_name)

    exact_field = EXACT_CUE_LOOKUP.get(normalized_name)
    if exact_field and exact_field not in BACKEND_CREATED_FIELDS:
        return ColumnMapping(
            uploaded_column=column_name,
            normalized_field=exact_field,
            strategy="cue_bank_exact",
            confidence=EXACT_MATCH_CONFIDENCE,
            matched_cue=column_name,
        )

    fuzzy_mapping = _fuzzy_match(column_name, normalized_name)
    if fuzzy_mapping:
        return fuzzy_mapping

    return _keyword_match(column_name)


def _fuzzy_match(column_name: str, normalized_name: str) -> ColumnMapping | None:
    scored_matches: list[tuple[float, str, str]] = []

    for normalized_cue, cue, field in _FUZZY_CUES:
        ratio = SequenceMatcher(None, normalized_name, normalized_cue).ratio()
        scored_matches.append((ratio, cue, field))

    scored_matches.sort(key=lambda item: item[0], reverse=True)
    if not scored_matches:
        return None

    best_score, best_cue, best_field = scored_matches[0]
    second_score = scored_matches[1][0] if len(scored_matches) > 1 else 0.0

    if best_score < FUZZY_MATCH_MIN_CONFIDENCE:
        return None

    if best_score - second_score < FUZZY_MATCH_MIN_MARGIN:
        return None

    return ColumnMapping(
        uploaded_column=column_name,
        normalized_field=best_field,
        strategy="fuzzy",
        confidence=round(best_score, 3),
        matched_cue=best_cue,
    )


def _keyword_match(column_name: str) -> ColumnMapping | None:
    tokens = tokenize_column_name(column_name)
    normalized_name = normalize_column_name(column_name)
    scored_fields: list[tuple[int, str]] = []

    for field, keyword_weights in KEYWORD_RULES.items():
        score = 0
        for keyword, weight in keyword_weights.items():
            normalized_keyword = normalize_column_name(keyword)
            if keyword in tokens:
                score += weight
            elif " " in normalized_keyword and normalized_keyword in normalized_name:
                score += weight

        if score:
            scored_fields.append((score, field))

    scored_fields.sort(key=lambda item: (item[0], -FIELD_PRIORITY.index(item[1])), reverse=True)
    if not scored_fields:
        return None

    best_score, best_field = scored_fields[0]
    second_score = scored_fields[1][0] if len(scored_fields) > 1 else 0

    if best_score < KEYWORD_MATCH_MIN_SCORE:
        return None

    if best_score - second_score < KEYWORD_MATCH_MIN_MARGIN:
        return None

    confidence = min(0.84, 0.55 + (best_score / 20))
    return ColumnMapping(
        uploaded_column=column_name,
        normalized_field=best_field,
        strategy="keyword",
        confidence=round(confidence, 3),
        matched_cue=", ".join(tokens),
    )


def _resolve_duplicate_field_mappings(
    mappings_by_column: Mapping[str, ColumnMapping],
) -> tuple[dict[str, ColumnMapping], list[str], list[UnmappedColumn]]:
    mappings_by_field: dict[str, ColumnMapping] = {}
    warnings: list[str] = []
    unmapped_columns: list[UnmappedColumn] = []

    for mapping in mappings_by_column.values():
        existing_mapping = mappings_by_field.get(mapping.normalized_field)
        if existing_mapping is None:
            mappings_by_field[mapping.normalized_field] = mapping
            continue

        winner, loser = _choose_mapping(existing_mapping, mapping)
        mappings_by_field[mapping.normalized_field] = winner
        unmapped_columns.append(
            UnmappedColumn(
                uploaded_column=loser.uploaded_column,
                reason=f"Duplicate mapping for {loser.normalized_field}; kept {winner.uploaded_column}",
            )
        )
        warnings.append(
            "Duplicate mapping for "
            f"{winner.normalized_field}: kept {winner.uploaded_column}, ignored {loser.uploaded_column}"
        )

    return mappings_by_field, warnings, unmapped_columns


def _choose_mapping(first: ColumnMapping, second: ColumnMapping) -> tuple[ColumnMapping, ColumnMapping]:
    strategy_rank = {"cue_bank_exact": 3, "fuzzy": 2, "keyword": 1}
    first_score = (first.confidence, strategy_rank.get(first.strategy, 0))
    second_score = (second.confidence, strategy_rank.get(second.strategy, 0))

    if second_score > first_score:
        return second, first

    return first, second


def _new_record(source: str) -> dict[str, Any]:
    record = {field: None for field in NORMALIZED_FIELDS}
    record["source"] = source
    record["matched_machine"] = False
    return record


def _coerce_record_values(record: dict[str, Any], row_index: int) -> list[str]:
    warnings: list[str] = []

    record["machine_id"] = _normalize_machine_id(record.get("machine_id"))
    record["severity"] = _normalize_severity(record.get("severity"))
    record["status"] = _normalize_status(record.get("status"))

    downtime_value, downtime_warning = _parse_number(record.get("downtime_minutes"), default=0)
    record["downtime_minutes"] = downtime_value
    if downtime_warning:
        warnings.append(f"Row {row_index} downtime_minutes {downtime_warning}; defaulted to 0")

    labor_value, labor_warning = _parse_number(record.get("labor_hours"), default=None)
    record["labor_hours"] = labor_value
    if labor_warning:
        warnings.append(f"Row {row_index} labor_hours {labor_warning}; left empty")

    return warnings


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = str(value).strip()
    return cleaned if cleaned else None


def _normalize_machine_id(value: Any) -> str | None:
    cleaned = _clean_text(value)
    return cleaned.upper() if cleaned else None


def _normalize_severity(value: Any) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return "unknown"

    normalized = normalize_column_name(cleaned)
    high_values = {"high", "h", "p1", "urgent", "critical", "crit", "severe"}
    medium_values = {"medium", "med", "m", "p2", "moderate", "normal"}
    low_values = {"low", "l", "p3", "minor", "minimal"}
    unknown_values = {"n a", "na", "none", "unknown", "blank"}

    if normalized in high_values or "critical" in normalized or "urgent" in normalized:
        return "high"
    if normalized in medium_values or "moderate" in normalized:
        return "medium"
    if normalized in low_values or "minor" in normalized:
        return "low"
    if normalized in unknown_values:
        return "unknown"

    return normalized


def _normalize_status(value: Any) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return "unknown"

    normalized = normalize_column_name(cleaned)

    if normalized in {"closed", "complete", "completed", "done", "finished", "resolved"}:
        return "closed"
    if normalized in {"open", "new", "created"}:
        return "open"
    if normalized in {"in progress", "active", "assigned", "working", "progress"}:
        return "in_progress"
    if normalized in {"n a", "na", "none", "unknown", "blank"}:
        return "unknown"

    return normalized.replace(" ", "_")


def _parse_number(value: Any, default: float | int | None) -> tuple[float | int | None, str | None]:
    cleaned = _clean_text(value)
    if cleaned is None:
        return default, None

    normalized = cleaned.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", normalized)
    if not match:
        return default, f"value {cleaned!r} is not numeric"

    number = float(match.group(0))
    if number.is_integer():
        return int(number), None

    return number, None


def _is_empty_row(row: Mapping[str, str | None]) -> bool:
    return all(_clean_text(value) is None for value in row.values())
