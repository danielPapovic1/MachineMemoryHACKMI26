from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from ibm_watsonx_ai import APIClient, Credentials
from ibm_watsonx_ai.foundation_models import ModelInference


BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH, override=True)

REQUIRED_ENV_VARS = [
    "WATSONX_API_KEY",
    "WATSONX_PROJECT_ID",
    "WATSONX_URL",
    "WATSONX_MODEL_ID",
]

_model: ModelInference | None = None
_model_config: tuple[str, str, str] | None = None


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip().strip("\"'")


def _get_model() -> ModelInference:
    global _model, _model_config

    load_dotenv(ENV_PATH, override=True)

    model_id = _get_required_env("WATSONX_MODEL_ID")
    project_id = _get_required_env("WATSONX_PROJECT_ID")
    watsonx_url = _get_required_env("WATSONX_URL")
    current_config = (watsonx_url, project_id, model_id)

    if _model is not None and _model_config == current_config:
        return _model

    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))

    credentials = Credentials(
        url=watsonx_url,
        api_key=_get_required_env("WATSONX_API_KEY"),
    )
    api_client = APIClient(credentials)

    _model = ModelInference(
        model_id=model_id,
        api_client=api_client,
        project_id=project_id,
        params={
            "temperature": 0.2,
            "max_new_tokens": 700,
        },
    )
    _model_config = current_config
    return _model


def call_model(
    user_prompt: str,
    system_prompt: str = "You are a helpful AI assistant.",
    temperature: float | None = None,
    max_new_tokens: int | None = None,
) -> str:
    return call_model_with_metadata(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_new_tokens=max_new_tokens,
    )["text"]


def call_model_with_metadata(
    user_prompt: str,
    system_prompt: str = "You are a helpful AI assistant.",
    temperature: float | None = None,
    max_new_tokens: int | None = None,
) -> dict[str, Any]:
    if not user_prompt or not user_prompt.strip():
        raise ValueError("user_prompt cannot be empty")

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": user_prompt,
                }
            ],
        },
    ]

    params: dict[str, Any] = {}
    if temperature is not None:
        params["temperature"] = temperature
    if max_new_tokens is not None:
        params["max_new_tokens"] = max_new_tokens

    try:
        model = _get_model()
        try:
            response = model.chat(messages=messages, params=params or None)
        except TypeError:
            response = model.chat(messages=messages)
    except Exception as exc:
        raise RuntimeError(f"watsonx.ai model call failed: {exc}") from exc

    text = _extract_model_text(response)
    return {
        "text": text,
        "metadata": _extract_response_metadata(response),
    }


def _extract_model_text(response: Any) -> str:
    try:
        return str(response["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise RuntimeError(f"Unexpected watsonx.ai response shape: {response}") from exc


def _extract_response_metadata(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {"response_type": type(response).__name__}

    metadata: dict[str, Any] = {}
    for key in ("id", "model", "model_id", "created", "created_at", "usage"):
        if key in response:
            metadata[key] = response[key]

    choices = response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        first_choice = choices[0]
        if "finish_reason" in first_choice:
            metadata["finish_reason"] = first_choice["finish_reason"]
        message = first_choice.get("message")
        if isinstance(message, dict) and "role" in message:
            metadata["message_role"] = message["role"]

    return metadata


if __name__ == "__main__":
    print(
        call_model(
            user_prompt="Explain predictive maintenance in one concise sentence.",
            system_prompt="You are a manufacturing AI assistant. Be direct and practical.",
        )
    )
