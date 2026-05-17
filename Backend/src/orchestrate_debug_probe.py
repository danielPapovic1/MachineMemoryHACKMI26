from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
TOKEN_URL = "https://iam.platform.saas.ibm.com/siusermgr/api/1.0/apikeys/token"
MESSAGE = "Hello. Reply with one sentence confirming this agent endpoint works."


def main() -> None:
    load_dotenv(ENV_PATH, override=True)

    api_key = _required_env("WATSONX_API_KEY")
    host_url = _required_env("ORCHESTRATE_HOST_URL").rstrip("/")
    agent_id = _required_env("ORCHESTRATE_AGENT_ID")
    instance_id = _extract_instance_id(host_url)

    print("=== Orchestrate Debug Probe ===")
    print(f"Loaded host: {host_url}")
    print(f"Loaded agent id: {agent_id}")
    if instance_id:
        print(f"Loaded instance id: {instance_id}")

    token = _get_orchestrate_bearer_token(api_key)
    print("Token generated: yes")
    print(f"Token preview: {token[:10]}...")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    list_agents = _probe(
        title="Probe 1: list agents",
        method="GET",
        url=f"{host_url}/api/v1/orchestrate/agents",
        headers=headers,
    )
    configured_agent = _probe(
        title="Probe 2: get configured agent",
        method="GET",
        url=f"{host_url}/api/v1/orchestrate/agents/{agent_id}",
        headers=headers,
    )
    _probe(
        title="Probe 3: GET chat endpoint check",
        method="GET",
        url=f"{host_url}/api/v1/orchestrate/{agent_id}/chat/completions",
        headers=headers,
    )
    post_chat = _probe(
        title="Probe 4: POST chat endpoint check",
        method="POST",
        url=f"{host_url}/api/v1/orchestrate/{agent_id}/chat/completions",
        headers=headers,
        json_payload={
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": MESSAGE,
                }
            ],
        },
    )

    print()
    print("=== Conclusion ===")
    agent_summaries = _extract_agent_summaries(list_agents.body_json)
    if agent_summaries:
        print("Discovered agents:")
        for summary in agent_summaries:
            print(f"- {summary}")

    if post_chat.status_code == 200:
        print("POST chat returned 200; the Orchestrate agent call path works.")
    elif list_agents.status_code == 404:
        print("List agents returned 404; ORCHESTRATE_HOST_URL is likely wrong.")
    elif list_agents.status_code in {401, 403}:
        print("List agents returned 401/403; the API key or token does not have needed Orchestrate access.")
    elif configured_agent.status_code == 404:
        print("Configured agent was not found; ORCHESTRATE_AGENT_ID is likely wrong.")
    else:
        print("Review the probe status codes and response bodies above for the next fix.")


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip().strip("\"'")


def _get_orchestrate_bearer_token(api_key: str) -> str:
    response = requests.post(
        TOKEN_URL,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={"apikey": api_key},
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(f"Orchestrate token request failed: HTTP {response.status_code}: {response.text}")

    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Orchestrate token response was not an object: {data}")

    token = data.get("token") or data.get("access_token") or data.get("jwt")
    if not token:
        raise RuntimeError(f"Orchestrate token response did not include a token field: {data}")

    return str(token)


class ProbeResult:
    def __init__(self, status_code: int, body_text: str, body_json: Any = None) -> None:
        self.status_code = status_code
        self.body_text = body_text
        self.body_json = body_json


def _probe(
    title: str,
    method: str,
    url: str,
    headers: dict[str, str],
    json_payload: dict[str, Any] | None = None,
) -> ProbeResult:
    print()
    print(f"--- {title} ---")
    print(f"URL: {url}")

    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            json=json_payload,
            timeout=90,
        )
    except requests.RequestException as exc:
        print("STATUS: request_error")
        print(f"BODY: {exc}")
        return ProbeResult(status_code=0, body_text=str(exc))

    body = response.text or ""
    print(f"STATUS: {response.status_code}")
    print(f"BODY: {body[:1500]}")

    body_json: Any = None
    try:
        body_json = response.json()
    except ValueError:
        pass

    return ProbeResult(status_code=response.status_code, body_text=body, body_json=body_json)


def _extract_instance_id(host_url: str) -> str | None:
    match = re.search(r"/instances/([^/?#]+)", host_url)
    return match.group(1) if match else None


def _extract_agent_summaries(value: Any) -> list[str]:
    agents = _find_agent_objects(value)
    summaries: list[str] = []
    for agent in agents:
        agent_id = agent.get("id") or agent.get("agent_id") or agent.get("agentId")
        name = agent.get("name") or agent.get("display_name") or agent.get("displayName") or agent.get("title")
        if agent_id or name:
            summaries.append(f"id={agent_id or 'unknown'} name={name or 'unknown'}")
    return summaries


def _find_agent_objects(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        direct_agents = value.get("agents") or value.get("items") or value.get("resources") or value.get("data")
        if isinstance(direct_agents, list):
            return [item for item in direct_agents if isinstance(item, dict)]
        if any(key in value for key in ("id", "agent_id", "agentId")):
            return [value]
        found: list[dict[str, Any]] = []
        for item in value.values():
            found.extend(_find_agent_objects(item))
        return found

    if isinstance(value, list):
        found: list[dict[str, Any]] = []
        for item in value:
            found.extend(_find_agent_objects(item))
        return found

    return []


if __name__ == "__main__":
    main()
