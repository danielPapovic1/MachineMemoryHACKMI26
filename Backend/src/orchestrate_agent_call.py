from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"
IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"


class OrchestrateAgentError(RuntimeError):
    pass


def call_orchestrate_agent(message: str) -> dict[str, Any]:
    if not message or not message.strip():
        raise ValueError("message cannot be empty")

    api_key = _required_env("WATSONX_API_KEY")
    host = _orchestrate_host()
    agent_id = _required_env("ORCHESTRATE_AGENT_ID")
    bearer_token = _get_iam_bearer_token(api_key)

    url = f"{host.rstrip('/')}/api/v1/orchestrate/{agent_id}/chat/completions"

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
            },
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": message.strip(),
                    }
                ]
            },
            timeout=90,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OrchestrateAgentError(f"Orchestrate agent call failed: {_safe_request_error(exc)}") from exc

    try:
        parsed = response.json()
    except ValueError as exc:
        raise OrchestrateAgentError("Orchestrate agent returned a non-JSON response") from exc

    if not isinstance(parsed, dict):
        raise OrchestrateAgentError("Orchestrate agent returned an unexpected response shape")

    return parsed


def extract_agent_text(response_json: dict[str, Any]) -> str:
    try:
        content = response_json["choices"][0]["message"]["content"]
        if content is not None:
            if isinstance(content, list):
                parts = [
                    str(item.get("text") or item.get("content") or "")
                    for item in content
                    if isinstance(item, dict)
                ]
                joined = "\n".join(part for part in parts if part.strip()).strip()
                if joined:
                    return joined
            return str(content).strip()
    except (KeyError, IndexError, TypeError):
        pass

    for key in ("output", "message", "result", "response"):
        value = response_json.get(key)
        if value not in (None, ""):
            return str(value).strip()

    return str(response_json)


def _get_iam_bearer_token(api_key: str) -> str:
    try:
        response = requests.post(
            IAM_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": api_key,
            },
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OrchestrateAgentError(f"IAM bearer token request failed: {_safe_request_error(exc)}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise OrchestrateAgentError("IAM token response was not valid JSON") from exc

    token = data.get("access_token") if isinstance(data, dict) else None
    if not token:
        raise OrchestrateAgentError("IAM token response did not include access_token")

    return str(token)


def _required_env(name: str) -> str:
    load_dotenv(ENV_PATH, override=True)
    value = os.getenv(name)
    if not value or not value.strip():
        raise OrchestrateAgentError(f"Missing required environment variable: {name}")
    return value.strip().strip("\"'")


def _orchestrate_host() -> str:
    load_dotenv(ENV_PATH, override=True)
    value = os.getenv("ORCHESTRATE_HOST_UR") or os.getenv("ORCHESTRATE_HOST_URL")
    if not value or not value.strip():
        raise OrchestrateAgentError("Missing required environment variable: ORCHESTRATE_HOST_UR")
    return value.strip().strip("\"'")


def _safe_request_error(exc: requests.RequestException) -> str:
    response = exc.response
    if response is None:
        return str(exc)

    detail = response.text[:500] if response.text else response.reason
    return f"HTTP {response.status_code}: {detail}"
