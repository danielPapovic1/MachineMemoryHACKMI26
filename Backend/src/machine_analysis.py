from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any

from .base_api_call import call_model_with_metadata
from .dashboard_data import (
    get_dashboard_summary,
    get_machine_detail,
    load_maintenance_logs,
)
from .machine_store import DATA_DIR


AI_RESPONSES_FILE = DATA_DIR / "ai-responses.json"


SYSTEM_PROMPT = """
You are Machine Memory, an assistant for manufacturing maintenance teams.
Review only the provided structured data for the selected machine.
Stay grounded in the maintenance history and separate observed facts from possible risk.
Do not invent sensors, failures, exact forecasts, root causes, or actions that are not supported by the data.
If evidence is weak, say so clearly.
Write for a maintenance supervisor who needs concise, practical next steps.
Avoid generic AI filler and avoid overclaiming.
Return only a compact JSON object with these keys:
summary, urgency, predicted_downtime_if_ignored, downtime_reasoning, evidence, recommended_next_step, confidence.
Urgency must be one of low, medium, high, critical.
Confidence must be one of low, medium, high.
Evidence must be a short list of strings.
""".strip()


USER_PROMPT_TEMPLATE = """
Analyze this selected machine using the provided registry context, maintenance summary,
repeated patterns, recent logs, similar historical events, and small plant-level context.

Explain what appears to be happening, whether the machine needs attention, what downtime
risk may exist if no action is taken, what evidence supports the assessment, and what
practical maintenance action should happen next.

If the machine looks stable or has weak evidence, explain that calmly. Do not force a
scary answer when the data does not support one.

Return a short structured JSON object only.

Selected machine payload:
{payload}
""".strip()

ALLOWED_URGENCY = {"low", "medium", "high", "critical"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}


class MachineAnalysisError(RuntimeError):
    pass


class MachineNotFoundError(MachineAnalysisError):
    pass


def analyze_selected_machine(machine_id: str) -> dict[str, Any]:
    clean_machine_id = str(machine_id or "").strip()
    if not clean_machine_id:
        raise MachineAnalysisError("Machine ID is required for analysis")

    detail = get_machine_detail(clean_machine_id)
    if detail is None:
        raise MachineNotFoundError(f"Machine not found: {clean_machine_id}")

    payload = build_machine_analysis_payload(clean_machine_id, detail)
    if not (payload.get("maintenance_summary") or {}).get("matchingHistoryRecords"):
        response = _insufficient_history_response(payload)
        _save_machine_snapshot_response(
            payload=payload,
            frontend_response=response,
            raw_response_text=response["summary"],
            provider_call_made=False,
            response_metadata=None,
        )
        return response

    user_prompt = USER_PROMPT_TEMPLATE.format(payload=json.dumps(payload, indent=2))
    model_result = call_model_with_metadata(
        user_prompt=user_prompt,
        system_prompt=SYSTEM_PROMPT,
        temperature=0.2,
        max_new_tokens=700,
    )
    model_text = model_result["text"]

    response = _normalize_model_response(model_text, payload)
    _save_machine_snapshot_response(
        payload=payload,
        frontend_response=response,
        raw_response_text=model_text,
        provider_call_made=True,
        response_metadata=model_result.get("metadata"),
    )
    return response


def build_machine_analysis_payload(machine_id: str, detail: dict[str, Any]) -> dict[str, Any]:
    machine = detail.get("machine") or {}
    matching_logs = _matching_logs(machine_id)
    recent_logs = [_log_for_payload(log) for log in _sort_logs(matching_logs)[:5]]
    similar_events = [_event_for_payload(log) for log in _sort_logs(matching_logs)[:6]]
    dashboard_summary = get_dashboard_summary()

    payload = {
        "machine": {
            "machine_id": machine.get("id") or machine.get("machine_id") or machine_id,
            "name": machine.get("name"),
            "type": machine.get("type"),
            "zone": machine.get("zone") or machine.get("location"),
            "criticality": machine.get("criticality"),
            "downtime_cost_per_minute": machine.get("downtimeCostPerMinute"),
            "latest_status": machine.get("status"),
            "latest_upload_source": (detail.get("operationalSummary") or {}).get("latestUploadSource")
            or machine.get("source"),
        },
        "attention": {
            "level": detail.get("attentionLevel"),
            "reasons": detail.get("attentionReasons") or [],
            "signals": detail.get("operationalSignals") or [],
        },
        "maintenance_summary": _strip_empty(detail.get("operationalSummary") or {}),
        "repeated_patterns": _strip_empty(detail.get("patternMatches") or []),
        "recent_logs": _strip_empty(recent_logs),
        "similar_historical_events": _strip_empty(similar_events),
        "plant_context": _strip_empty(
            {
                "total_machines_with_history": dashboard_summary.get("totalMachines"),
                "critical_machine_count": dashboard_summary.get("criticalCount"),
                "warning_machine_count": dashboard_summary.get("warningCount"),
                "total_logged_downtime_minutes": dashboard_summary.get("estimatedDowntimeRisk"),
            }
        ),
    }
    return _strip_empty(payload)


def _matching_logs(machine_id: str) -> list[dict[str, Any]]:
    target = machine_id.upper()
    return [
        log
        for log in load_maintenance_logs()
        if str(log.get("machine_id") or "").upper() == target
    ]


def _log_for_payload(log: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": log.get("timestamp_opened") or log.get("timestamp") or log.get("ingested_at"),
        "issue": log.get("issue"),
        "severity": log.get("severity"),
        "status": log.get("status"),
        "technician": log.get("technician"),
        "operator_note": log.get("operator_note"),
        "resolution_note": log.get("resolution_note"),
        "downtime_minutes": log.get("downtime_minutes"),
        "source": log.get("source"),
    }


def _event_for_payload(log: dict[str, Any]) -> dict[str, Any]:
    event = _log_for_payload(log)
    event["pattern"] = log.get("issue") or _first_keyword(log)
    return event


def _first_keyword(log: dict[str, Any]) -> str | None:
    text = " ".join(
        str(value)
        for value in (log.get("operator_note"), log.get("resolution_note"), log.get("failure_code"))
        if value
    ).lower()
    for keyword in (
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
        "coolant",
        "filter",
    ):
        if keyword in text:
            return keyword
    return None


def _sort_logs(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        logs,
        key=lambda log: str(log.get("timestamp_opened") or log.get("timestamp") or log.get("ingested_at") or ""),
        reverse=True,
    )


def _normalize_model_response(model_text: str, payload: dict[str, Any]) -> dict[str, Any]:
    parsed = _parse_json_object(model_text)
    if parsed is None:
        parsed = {
            "summary": model_text.strip(),
            "urgency": _fallback_urgency(payload),
            "predicted_downtime_if_ignored": "Unable to parse a structured downtime estimate from the model response.",
            "downtime_reasoning": "The model returned plain text, so the backend preserved the response as a summary.",
            "evidence": payload.get("attention", {}).get("signals", [])[:3],
            "recommended_next_step": "Review the machine history and inspect the most recent repeated issue.",
            "confidence": "low",
        }

    urgency = _clean_choice(parsed.get("urgency"), ALLOWED_URGENCY, _fallback_urgency(payload))
    confidence = _clean_choice(parsed.get("confidence"), ALLOWED_CONFIDENCE, "medium")
    evidence = parsed.get("evidence")
    if not isinstance(evidence, list):
        evidence = [str(evidence)] if evidence else []

    return _frontend_analysis_response(
        machine_id=str(payload["machine"]["machine_id"]),
        summary=str(parsed.get("summary") or "No summary was returned by the model."),
        urgency=urgency,
        predicted_downtime=str(parsed.get("predicted_downtime_if_ignored") or "Not enough evidence for a specific estimate."),
        downtime_reasoning=str(parsed.get("downtime_reasoning") or "No downtime reasoning was returned."),
        evidence=[str(item) for item in evidence if item],
        recommended_next_step=str(parsed.get("recommended_next_step") or "Review recent maintenance history before the next run."),
        confidence=confidence,
    )


def _parse_json_object(model_text: str) -> dict[str, Any] | None:
    text = model_text.strip()
    candidates = [text]
    match = re.search(r"\{.*\}", text, re.DOTALL)
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


def _insufficient_history_response(payload: dict[str, Any]) -> dict[str, Any]:
    return _frontend_analysis_response(
        machine_id=str(payload["machine"]["machine_id"]),
        summary=(
            "There is not enough matching maintenance history for this machine to produce a strong AI review. "
            "The machine can still be tracked from the registry, but the analysis needs uploaded work-order history."
        ),
        urgency="low",
        predicted_downtime="Not enough machine-specific history to estimate downtime.",
        downtime_reasoning="No matching maintenance records were available for this selected machine.",
        evidence=["No matching uploaded maintenance history was found for this machine."],
        recommended_next_step="Upload maintenance records for this machine, then run analysis again.",
        confidence="low",
    )


def _frontend_analysis_response(
    machine_id: str,
    summary: str,
    urgency: str,
    predicted_downtime: str,
    downtime_reasoning: str,
    evidence: list[str],
    recommended_next_step: str,
    confidence: str,
) -> dict[str, Any]:
    return {
        "machineId": machine_id,
        "summary": summary,
        "urgency": urgency,
        "predictedDowntimeIfIgnored": predicted_downtime,
        "downtimeReasoning": downtime_reasoning,
        "evidence": evidence,
        "recommendedNextStep": recommended_next_step,
        "confidence": confidence,
        "predictedIssue": summary,
        "rootCause": downtime_reasoning,
        "recommendedAction": recommended_next_step,
        "estimatedDowntimeHours": None,
        "estimatedSavings": None,
    }


def _save_machine_snapshot_response(
    payload: dict[str, Any],
    frontend_response: dict[str, Any],
    raw_response_text: str,
    provider_call_made: bool,
    response_metadata: dict[str, Any] | None,
) -> None:
    machine = payload.get("machine") or {}
    summary = payload.get("maintenance_summary") or {}
    received_at = datetime.now(timezone.utc).isoformat()
    response_id = _response_id(received_at, str(machine.get("machine_id") or frontend_response.get("machineId") or "unknown"))

    record = _strip_empty(
        {
            "response_id": response_id,
            "received_at": received_at,
            "ai_type": "machine snapshot",
            "response_text": raw_response_text,
            "metadata": {
                "machine_id": machine.get("machine_id") or frontend_response.get("machineId"),
                "machine_name": machine.get("name"),
                "machine_type": machine.get("type"),
                "zone": machine.get("zone"),
                "provider": "ibm_watsonx_ai" if provider_call_made else "local_backend",
                "provider_call_made": provider_call_made,
                "provider_response": _compact_provider_metadata(response_metadata),
                "urgency": frontend_response.get("urgency"),
                "confidence": frontend_response.get("confidence"),
                "matching_history_records": summary.get("matchingHistoryRecords"),
            },
        }
    )
    _append_ai_response(record)


def _compact_provider_metadata(response_metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not response_metadata:
        return None

    return {
        key: response_metadata[key]
        for key in ("usage", "finish_reason")
        if key in response_metadata
    }


def _append_ai_response(record: dict[str, Any]) -> None:
    existing = _read_ai_responses()
    existing.append(record)
    AI_RESPONSES_FILE.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")


def _read_ai_responses() -> list[dict[str, Any]]:
    if not AI_RESPONSES_FILE.exists():
        return []

    text = AI_RESPONSES_FILE.read_text(encoding="utf-8").strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ai-responses.json is not valid JSON") from exc

    if not isinstance(parsed, list):
        raise RuntimeError("ai-responses.json must contain a JSON list")

    return [item for item in parsed if isinstance(item, dict)]


def _response_id(timestamp: str, machine_id: str) -> str:
    safe_timestamp = re.sub(r"[^0-9A-Za-z]+", "", timestamp)
    safe_machine_id = re.sub(r"[^0-9A-Za-z_-]+", "-", machine_id).strip("-") or "unknown"
    return f"machine-snapshot-{safe_machine_id}-{safe_timestamp}"


def _clean_choice(value: Any, allowed: set[str], fallback: str) -> str:
    cleaned = str(value or "").strip().lower()
    return cleaned if cleaned in allowed else fallback


def _fallback_urgency(payload: dict[str, Any]) -> str:
    level = str(payload.get("attention", {}).get("level") or "").lower()
    if level in ALLOWED_URGENCY:
        return level
    if level == "observed":
        return "low"
    return "medium"


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
            if item not in (None, "", [], {})
        ]
    return value
