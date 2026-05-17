from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from .ai_insights import append_ai_response
from .base_api_call import call_model_with_metadata
from .dashboard_data import get_dashboard_summary, load_maintenance_logs
from .machines_page import get_machines_page_profile


REPO_ROOT = Path(__file__).resolve().parents[2]
DEEP_REVIEW_SYSTEM_PROMPT = REPO_ROOT / "blueprints" / "DEEPREVIEW-SYS.md"

SECRET_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "password",
    "secret",
    "token",
)


class DeepReviewError(RuntimeError):
    pass


class DeepReviewMachineNotFound(DeepReviewError):
    pass


class DeepReviewRequestError(DeepReviewError):
    pass


def run_machine_deep_review(machine_id: str, frontend_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_machine_id = str(machine_id or "").strip()
    if not clean_machine_id:
        raise DeepReviewRequestError("Machine ID is required for deep review")

    body = frontend_payload if isinstance(frontend_payload, dict) else {}
    requested_machine_id = body.get("machineId") or body.get("machine_id")
    if requested_machine_id and _normalize_id(requested_machine_id) != _normalize_id(clean_machine_id):
        raise DeepReviewRequestError("Request machine ID does not match the selected machine")

    profile = get_machines_page_profile(clean_machine_id)
    if profile is None:
        raise DeepReviewMachineNotFound(f"Machine not found: {clean_machine_id}")

    payload = _build_agent_payload(clean_machine_id, profile, body)
    prompt = _build_agent_message(payload)

    model_result = _call_deep_review_model(prompt)
    agent_text = model_result["text"]

    review = _parse_json_object(agent_text)
    machine = payload.get("selected_machine") or {}
    generated_at = datetime.now(timezone.utc).isoformat()
    review_status = _review_status(review, agent_text)

    response = {
        "success": True,
        "machineId": machine.get("machine_id") or clean_machine_id,
        "machineName": machine.get("machine_name"),
        "reviewStatus": review_status,
        "agentResponse": agent_text,
        "review": review,
        "metadata": {
            "generatedAt": generated_at,
            "provider": "Orchestrate",
            "matchingHistoryRecords": (payload.get("maintenance_summary") or {}).get("matchingHistoryRecords"),
            "recentLogCount": len(payload.get("recent_logs") or []),
            "allMatchingLogCount": len(payload.get("matching_maintenance_history") or []),
        },
    }
    _save_deep_review_response(
        machine=machine,
        response=response,
        generated_at=generated_at,
        review_status=review_status,
        response_metadata=model_result.get("metadata"),
    )
    return response


def _build_agent_payload(
    machine_id: str,
    profile: dict[str, Any],
    frontend_payload: dict[str, Any],
) -> dict[str, Any]:
    machine = profile.get("machine") if isinstance(profile.get("machine"), dict) else {}
    status_context = profile.get("statusContext") if isinstance(profile.get("statusContext"), dict) else {}
    business_context = profile.get("businessContext") if isinstance(profile.get("businessContext"), dict) else {}
    downtime_context = profile.get("downtimeContext") if isinstance(profile.get("downtimeContext"), dict) else {}
    maintenance_summary = profile.get("maintenanceSummary") if isinstance(profile.get("maintenanceSummary"), dict) else {}
    frontend_context = _sanitize(frontend_payload.get("selectedMachineContext") or frontend_payload.get("context") or {})

    cost_per_minute = machine.get("downtimeCostPerMinute") or business_context.get("downtimeCostPerMinute")
    matching_logs = [_log_for_agent(log) for log in _matching_logs(machine_id)]
    open_work_items = _open_or_unresolved_logs(matching_logs)
    high_critical_records = _high_or_critical_logs(matching_logs)
    downtime_labor_evidence = _downtime_labor_evidence(matching_logs, cost_per_minute)
    dashboard_context = _strip_empty(
        {
            "backendSummary": get_dashboard_summary(),
            "frontendSummary": _sanitize(frontend_payload.get("dashboardContext") or {}),
        }
    )

    return _strip_empty(
        {
            "review_request": {
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "review_type": "deep_review",
                "selected_machine_id": machine.get("machineId") or machine_id,
                "instructions": (
                    "Analyze only this selected machine using the provided evidence. "
                    "Return the exact JSON object shape required by the system prompt."
                ),
            },
            "selected_machine": {
                "machine_id": machine.get("machineId") or machine_id,
                "machine_name": machine.get("machineName"),
                "machine_type": machine.get("machineType"),
                "zone": machine.get("zone") or machine.get("location"),
                "line": machine.get("line"),
                "location": machine.get("location") or machine.get("zone"),
                "manufacturer": machine.get("manufacturer"),
                "model": machine.get("model"),
                "installed_date": machine.get("installedDate"),
                "criticality": machine.get("criticality") or business_context.get("criticality"),
                "downtimeCostPerMinute": cost_per_minute,
                "downtimeCostPerHour": _cost_per_hour(cost_per_minute),
                "source": machine.get("source"),
            },
            "current_status_and_attention": {
                "status": status_context.get("status"),
                "attention_level": status_context.get("attentionLevel"),
                "attention_reasons": status_context.get("attentionReasons"),
                "latest_upload_status": status_context.get("latestUploadStatus"),
                "latest_source_file": status_context.get("latestSourceFile"),
                "latest_log_time": status_context.get("latestLogTime"),
                "latest_issue": status_context.get("latestIssue"),
                "risk_signals": profile.get("riskSignals") or [],
            },
            "business_context": business_context,
            "downtime_context": downtime_context,
            "maintenance_summary": maintenance_summary,
            "maintenance_history_summary": {
                "matching_record_count": len(matching_logs),
                "recent_record_count": len(profile.get("recentLogs") or []),
                "high_or_critical_record_count": len(high_critical_records),
                "open_or_unresolved_item_count": len(open_work_items),
                "most_common_logged_issue": maintenance_summary.get("mostCommonLoggedIssue"),
                "latest_logged_issue": maintenance_summary.get("latestIssue"),
                "latest_log_time": maintenance_summary.get("latestLogTime"),
                "latest_source_file": maintenance_summary.get("latestSourceFile"),
                "technicians": maintenance_summary.get("technicians"),
            },
            "matching_maintenance_history": matching_logs,
            "open_or_unresolved_work": open_work_items,
            "high_or_critical_maintenance_records": high_critical_records,
            "downtime_and_labor_evidence": downtime_labor_evidence,
            "recent_logs": profile.get("recentLogs") or [],
            "repeated_issue_patterns": profile.get("repeatedPatterns") or [],
            "similar_historical_events": profile.get("similarHistoricalEvents") or [],
            "affected_uploads": profile.get("affectedUploads") or [],
            "sensor_or_latest_state_context": profile.get("sensorContext") or {},
            "data_availability": profile.get("dataAvailability") or {},
            "evidence_quality": {
                "has_machine_identity": bool(machine.get("machineId") or machine_id),
                "has_maintenance_history": bool(matching_logs),
                "has_repeated_patterns": bool(profile.get("repeatedPatterns")),
                "has_similar_historical_events": bool(profile.get("similarHistoricalEvents")),
                "has_downtime_minutes": any(_number_or_none(log.get("downtimeMinutes")) for log in matching_logs),
                "has_labor_hours": any(_number_or_none(log.get("laborHours")) for log in matching_logs),
                "has_cost_context": _number_or_none(cost_per_minute) is not None,
                "missing_core_fields": (profile.get("dataAvailability") or {}).get("missingCoreFields"),
            },
            "raw_machine_fields": _sanitize(profile.get("rawExtractedFields") or {}),
            "frontend_selected_machine_context": frontend_context,
            "plant_context": dashboard_context,
        }
    )


def _build_agent_message(payload: dict[str, Any]) -> str:
    return f"""
Selected machine deep review data:
{json.dumps(payload, indent=2, default=str)}

User ask:
Run a deep maintenance review for the selected machine. Use the complete payload above, including maintenance history, recent logs, attention reasons, repeated patterns, downtime context, similar historical events, unresolved/open items, labor evidence, and cost context. Produce a practical prevention-focused review for a maintenance supervisor.

Return a single JSON object only. Do not wrap the JSON in markdown. Do not include unrelated machines, secrets, request headers, or provider metadata.
""".strip()


def _call_deep_review_model(user_prompt: str) -> dict[str, Any]:
    try:
        return call_model_with_metadata(
            user_prompt=user_prompt,
            system_prompt=_load_deep_review_system_prompt(),
            temperature=0.2,
            max_new_tokens=2500,
        )
    except Exception as exc:
        raise DeepReviewError(f"Deep review model call failed: {exc}") from exc


def _load_deep_review_system_prompt() -> str:
    try:
        return DEEP_REVIEW_SYSTEM_PROMPT.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise DeepReviewError(f"Unable to load deep review system prompt: {exc}") from exc


def _matching_logs(machine_id: str) -> list[dict[str, Any]]:
    target = str(machine_id or "").upper()
    return [
        log
        for log in load_maintenance_logs()
        if str(log.get("machine_id") or "").upper() == target
    ]


def _log_for_agent(log: dict[str, Any]) -> dict[str, Any]:
    return _strip_empty(
        {
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
            "ingestedAt": log.get("ingested_at"),
        }
    )


def _open_or_unresolved_logs(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    open_statuses = {"open", "in_progress", "new", "created", "assigned", "working", "active"}
    return [
        log
        for log in logs
        if str(log.get("status") or "").strip().lower() in open_statuses
    ]


def _high_or_critical_logs(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        log
        for log in logs
        if str(log.get("severity") or "").strip().lower() in {"high", "critical"}
    ]


def _downtime_labor_evidence(logs: list[dict[str, Any]], cost_per_minute: Any) -> dict[str, Any]:
    downtime_values = [
        value
        for value in (_number_or_none(log.get("downtimeMinutes")) for log in logs)
        if value is not None and value > 0
    ]
    labor_values = [
        value
        for value in (_number_or_none(log.get("laborHours")) for log in logs)
        if value is not None and value > 0
    ]
    cost = _number_or_none(cost_per_minute)
    total_downtime = sum(downtime_values)
    total_labor = sum(labor_values)

    return _strip_empty(
        {
            "records_with_downtime": len(downtime_values),
            "records_with_labor_hours": len(labor_values),
            "total_logged_downtime_minutes": _clean_number(total_downtime),
            "total_labor_hours": _clean_number(total_labor),
            "downtime_minutes_range_from_records": {
                "low": _clean_number(min(downtime_values)) if downtime_values else None,
                "high": _clean_number(max(downtime_values)) if downtime_values else None,
            },
            "labor_hours_range_from_records": {
                "low": _clean_number(min(labor_values)) if labor_values else None,
                "high": _clean_number(max(labor_values)) if labor_values else None,
            },
            "downtimeCostPerMinute": cost,
            "downtimeCostPerHour": _cost_per_hour(cost),
            "total_logged_cost_exposure": _clean_number(total_downtime * cost) if cost is not None else None,
        }
    )


def _parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    candidates = [cleaned]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(cleaned[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _review_status(review: dict[str, Any] | None, agent_text: str) -> str:
    if review and review.get("review_status"):
        return str(review["review_status"])
    if agent_text.strip():
        return "completed"
    return "empty_response"


def _save_deep_review_response(
    machine: dict[str, Any],
    response: dict[str, Any],
    generated_at: str,
    review_status: str,
    response_metadata: dict[str, Any] | None,
) -> None:
    machine_id = str(machine.get("machine_id") or response.get("machineId") or "unknown")
    review = response.get("review") if isinstance(response.get("review"), dict) else {}
    current_condition = review.get("current_condition") if isinstance(review.get("current_condition"), dict) else {}
    downtime_exposure = review.get("downtime_exposure") if isinstance(review.get("downtime_exposure"), dict) else {}
    record = _strip_empty(
        {
            "response_id": _response_id(generated_at, machine_id),
            "received_at": generated_at,
            "ai_type": "deep review",
            "response_text": response.get("agentResponse"),
            "review": review,
            "metadata": {
                "machine_id": machine_id,
                "machine_name": machine.get("machine_name") or response.get("machineName"),
                "machine_type": machine.get("machine_type"),
                "zone": machine.get("zone"),
                "provider": "Orchestrate",
                "provider_call_made": True,
                "provider_response": _compact_provider_metadata(response_metadata),
                "review_status": review_status,
                "evidence_strength": current_condition.get("evidence_strength"),
                "downtime_confidence": downtime_exposure.get("confidence"),
                "matching_history_records": (response.get("metadata") or {}).get("matchingHistoryRecords"),
                "recent_log_count": (response.get("metadata") or {}).get("recentLogCount"),
                "all_matching_log_count": (response.get("metadata") or {}).get("allMatchingLogCount"),
            },
        }
    )
    append_ai_response(record)


def _compact_provider_metadata(response_metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not response_metadata:
        return None

    return {
        key: response_metadata[key]
        for key in ("usage", "finish_reason")
        if key in response_metadata
    }


def _response_id(timestamp: str, machine_id: str) -> str:
    safe_timestamp = re.sub(r"[^0-9A-Za-z]+", "", timestamp)
    safe_machine_id = re.sub(r"[^0-9A-Za-z_-]+", "-", machine_id).strip("-") or "unknown"
    return f"deep-review-{safe_machine_id}-{safe_timestamp}"


def _cost_per_hour(value: Any) -> float | int | None:
    number = _number_or_none(value)
    if number is None:
        return None
    hourly = number * 60
    return int(hourly) if hourly.is_integer() else hourly


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _clean_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            normalized_key = key_text.replace("-", "_").lower()
            if any(fragment in normalized_key for fragment in SECRET_KEY_FRAGMENTS):
                continue
            cleaned[key_text] = _sanitize(item)
        return _strip_empty(cleaned)

    if isinstance(value, list):
        return [_sanitize(item) for item in value if item not in (None, "", [], {})]

    return value


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


def _normalize_id(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()
