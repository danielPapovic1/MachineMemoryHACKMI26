from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
import re
from typing import Any

from .machine_store import DATA_DIR


AI_RESPONSES_FILE = DATA_DIR / "ai-responses.json"
AI_TYPE_MACHINE_SNAPSHOT = "machine_snapshot"
AI_TYPE_DEEP_REVIEW = "deep_review"
ALLOWED_AI_TYPES = {AI_TYPE_MACHINE_SNAPSHOT, AI_TYPE_DEEP_REVIEW}


class AIInsightsError(RuntimeError):
    pass


def get_ai_insights_page(
    ai_type: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    requested_type = _canonical_ai_type(ai_type) if ai_type else None
    records = _sorted_records(_normalized_records())
    if requested_type:
        records = [record for record in records if record["aiType"] == requested_type]

    groups = {
        AI_TYPE_MACHINE_SNAPSHOT: _group_payload(AI_TYPE_MACHINE_SNAPSHOT, records, limit, offset),
        AI_TYPE_DEEP_REVIEW: _group_payload(AI_TYPE_DEEP_REVIEW, records, limit, offset),
    }

    return {
        "summary": {
            "totalResponses": len(records),
            "machineSnapshotResponses": sum(1 for record in records if record["aiType"] == AI_TYPE_MACHINE_SNAPSHOT),
            "deepReviewResponses": sum(1 for record in records if record["aiType"] == AI_TYPE_DEEP_REVIEW),
            "machinesWithMachineSnapshots": len(groups[AI_TYPE_MACHINE_SNAPSHOT]["machines"]),
            "machinesWithDeepReviews": len(groups[AI_TYPE_DEEP_REVIEW]["machines"]),
            "latestResponseTime": records[0]["createdAt"] if records else None,
        },
        "groups": groups,
        AI_TYPE_MACHINE_SNAPSHOT: groups[AI_TYPE_MACHINE_SNAPSHOT]["machines"],
        AI_TYPE_DEEP_REVIEW: groups[AI_TYPE_DEEP_REVIEW]["machines"],
    }


def get_machine_ai_insights(
    machine_id: str,
    ai_type: str,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    clean_machine_id = str(machine_id or "").strip()
    if not clean_machine_id:
        raise AIInsightsError("Machine ID is required")

    requested_type = _canonical_ai_type(ai_type)
    records = [
        record
        for record in _sorted_records(_normalized_records())
        if record["aiType"] == requested_type and _same_machine(record["machineId"], clean_machine_id)
    ]
    paged_records = _paginate(records, limit, offset)

    return {
        "machineId": clean_machine_id,
        "machineName": records[0].get("machineName") if records else None,
        "zone": records[0].get("zone") if records else None,
        "aiType": requested_type,
        "responseCount": len(records),
        "limit": limit,
        "offset": offset or 0,
        "latest": paged_records[0] if paged_records else None,
        "responses": paged_records,
    }


def append_ai_response(record: dict[str, Any]) -> None:
    existing = _read_ai_response_records()
    existing.append(record)
    AI_RESPONSES_FILE.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")


def _group_payload(
    ai_type: str,
    records: list[dict[str, Any]],
    limit: int | None,
    offset: int | None,
) -> dict[str, Any]:
    type_records = [record for record in records if record["aiType"] == ai_type]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in type_records:
        machine_id = record.get("machineId") or "unknown"
        grouped[str(machine_id)].append(record)

    machine_cards = [
        _machine_card(machine_records)
        for machine_records in grouped.values()
        if machine_records
    ]
    machine_cards.sort(key=lambda card: str(card.get("latestResponseTime") or ""), reverse=True)

    return {
        "aiType": ai_type,
        "label": "Machine Snapshot (Watsonx)" if ai_type == AI_TYPE_MACHINE_SNAPSHOT else "Deep Review (Orchestrate Agent)",
        "responseCount": len(type_records),
        "machineCount": len(machine_cards),
        "machines": _paginate(machine_cards, limit, offset),
    }


def _machine_card(records: list[dict[str, Any]]) -> dict[str, Any]:
    latest = records[0]
    return {
        "machineId": latest.get("machineId"),
        "machineName": latest.get("machineName"),
        "zone": latest.get("zone"),
        "latestResponseTime": latest.get("createdAt"),
        "latestSummary": latest.get("summary"),
        "responseCount": len(records),
        "latestStatus": latest.get("status"),
        "latestConfidence": latest.get("confidence"),
        "source": latest.get("source"),
    }


def _normalized_records() -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for record in _read_ai_response_records():
        normalized_record = _normalize_record(record)
        if normalized_record:
            normalized.append(normalized_record)
    return normalized


def _normalize_record(record: dict[str, Any]) -> dict[str, Any] | None:
    ai_type = _canonical_ai_type(record.get("ai_type") or record.get("aiType"), allow_unknown=True)
    if ai_type is None:
        return None

    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    response_text = str(record.get("response_text") or record.get("responseText") or record.get("agentResponse") or "")
    parsed = record.get("review") if isinstance(record.get("review"), dict) else _parse_json_object(response_text)
    if not isinstance(parsed, dict):
        parsed = {}

    machine_id = (
        metadata.get("machine_id")
        or metadata.get("machineId")
        or record.get("machine_id")
        or record.get("machineId")
        or parsed.get("machine_id")
        or parsed.get("machineId")
    )

    created_at = (
        record.get("received_at")
        or record.get("createdAt")
        or record.get("generatedAt")
        or metadata.get("generatedAt")
        or metadata.get("receivedAt")
    )
    source = metadata.get("provider") or record.get("source") or _default_source(ai_type)
    status = _status_for_record(ai_type, record, metadata, parsed)
    confidence = metadata.get("confidence") or parsed.get("confidence")

    return _strip_empty(
        {
            "responseId": record.get("response_id") or record.get("responseId") or _fallback_response_id(ai_type, machine_id, created_at),
            "machineId": str(machine_id) if machine_id else None,
            "machineName": metadata.get("machine_name") or metadata.get("machineName") or record.get("machineName") or parsed.get("machine_name"),
            "machineType": metadata.get("machine_type") or metadata.get("machineType") or parsed.get("machine_type"),
            "zone": metadata.get("zone") or record.get("zone") or parsed.get("zone"),
            "aiType": ai_type,
            "createdAt": created_at,
            "status": status,
            "summary": _summary_for_record(ai_type, response_text, parsed),
            "confidence": confidence,
            "source": source,
            "modelOrAgent": metadata.get("model") or metadata.get("agent") or source,
            "responseText": response_text,
            "metadata": metadata,
            "parsed": parsed,
            "snapshot": _snapshot_fields(parsed, metadata) if ai_type == AI_TYPE_MACHINE_SNAPSHOT else None,
            "deepReview": _deep_review_fields(parsed) if ai_type == AI_TYPE_DEEP_REVIEW else None,
        }
    )


def _snapshot_fields(parsed: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    return _strip_empty(
        {
            "urgency": metadata.get("urgency") or parsed.get("urgency"),
            "keyAnomaly": parsed.get("key_anomaly") or parsed.get("predicted_issue") or parsed.get("summary"),
            "suggestedNextStep": parsed.get("recommended_next_step") or parsed.get("recommendedAction"),
            "predictedDowntimeIfIgnored": parsed.get("predicted_downtime_if_ignored"),
            "downtimeReasoning": parsed.get("downtime_reasoning"),
            "evidence": parsed.get("evidence"),
        }
    )


def _deep_review_fields(parsed: dict[str, Any]) -> dict[str, Any]:
    downtime = parsed.get("downtime_exposure") if isinstance(parsed.get("downtime_exposure"), dict) else {}
    findings = parsed.get("key_findings")
    action_plan = parsed.get("preventive_action_plan")
    hypotheses = parsed.get("root_cause_hypotheses")

    return _strip_empty(
        {
            "rootCause": _first_text(hypotheses),
            "patternFindings": findings,
            "maintenanceRecommendation": _first_text(action_plan) or parsed.get("final_recommendation"),
            "historicalMatch": parsed.get("historical_match"),
            "riskOutlook": downtime.get("risk_outlook") or downtime.get("downtime_risk") or parsed.get("current_condition"),
            "downtimeExposure": downtime,
            "finalRecommendation": parsed.get("final_recommendation"),
        }
    )


def _summary_for_record(ai_type: str, response_text: str, parsed: dict[str, Any]) -> str:
    if ai_type == AI_TYPE_DEEP_REVIEW:
        summary = parsed.get("executive_summary") or parsed.get("summary") or parsed.get("final_recommendation")
    else:
        summary = parsed.get("summary") or parsed.get("predicted_issue")

    if summary:
        return _clean_summary(summary)
    return _clean_summary(response_text) or "Saved AI response"


def _status_for_record(
    ai_type: str,
    record: dict[str, Any],
    metadata: dict[str, Any],
    parsed: dict[str, Any],
) -> str:
    if ai_type == AI_TYPE_DEEP_REVIEW:
        return str(record.get("reviewStatus") or parsed.get("review_status") or metadata.get("status") or "completed")
    return str(metadata.get("urgency") or parsed.get("urgency") or metadata.get("status") or "completed")


def _canonical_ai_type(value: Any, allow_unknown: bool = False) -> str | None:
    cleaned = re.sub(r"[\s-]+", "_", str(value or "").strip().lower())
    if cleaned in {"machine_snapshot", "snapshot", "base", "base_snapshot"}:
        return AI_TYPE_MACHINE_SNAPSHOT
    if cleaned in {"deep_review", "machine_deep_review", "deep_orchestrate_machine_review"}:
        return AI_TYPE_DEEP_REVIEW
    if allow_unknown:
        return None
    raise AIInsightsError(f"Unsupported ai_type: {value}")


def _read_ai_response_records() -> list[dict[str, Any]]:
    if not AI_RESPONSES_FILE.exists():
        return []

    text = AI_RESPONSES_FILE.read_text(encoding="utf-8").strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIInsightsError("ai-responses.json is not valid JSON") from exc

    if not isinstance(parsed, list):
        raise AIInsightsError("ai-responses.json must contain a JSON list")

    return [item for item in parsed if isinstance(item, dict)]


def _parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    candidates = [cleaned]
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _sorted_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: _sort_key(record.get("createdAt")), reverse=True)


def _sort_key(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return text


def _paginate(items: list[dict[str, Any]], limit: int | None, offset: int | None) -> list[dict[str, Any]]:
    start = max(offset or 0, 0)
    if limit is None or limit < 0:
        return items[start:]
    return items[start : start + limit]


def _same_machine(left: Any, right: Any) -> bool:
    return str(left or "").strip().casefold() == str(right or "").strip().casefold()


def _fallback_response_id(ai_type: str, machine_id: Any, created_at: Any) -> str:
    safe_machine = re.sub(r"[^0-9A-Za-z_-]+", "-", str(machine_id or "unknown")).strip("-") or "unknown"
    safe_time = re.sub(r"[^0-9A-Za-z]+", "", str(created_at or "undated")) or "undated"
    return f"{ai_type}-{safe_machine}-{safe_time}"


def _default_source(ai_type: str) -> str:
    return "watsonx_orchestrate" if ai_type == AI_TYPE_DEEP_REVIEW else "ibm_watsonx_ai"


def _clean_summary(value: Any) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, default=str)
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:240]


def _first_text(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
    if isinstance(value, dict):
        for key in ("recommendation", "action", "root_cause", "hypothesis", "summary", "finding", "description"):
            if value.get(key):
                return _clean_summary(value[key])
    if value not in (None, ""):
        return _clean_summary(value)
    return None


def _strip_empty(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {
            key: _strip_empty(item)
            for key, item in value.items()
            if item not in (None, "", [], {}, "No values yet")
        }
        return {key: item for key, item in cleaned.items() if item not in (None, "", [], {})}
    if isinstance(value, list):
        return [
            item
            for item in (_strip_empty(entry) for entry in value)
            if item not in (None, "", [], {}, "No values yet")
        ]
    return value
