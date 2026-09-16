"""OpenAI Platform API-key transport and model discovery helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx
from config import get_openai_api_url
from core.httpx_client import get_async
from core.xai import (
    gemini_request_to_xai,
    xai_response_to_gemini,
    xai_stream_line_to_gemini,
)


class OpenAIPlatformError(RuntimeError):
    """A sanitized OpenAI Platform integration error."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class OpenAIPlatformValidation:
    model_ids: List[str]

    @property
    def model_count(self) -> int:
        return len(self.model_ids)


def normalize_openai_api_url(value: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("OpenAI Platform API endpoint must use HTTP or HTTPS.")
    return normalized


def build_openai_headers(api_key: str) -> Dict[str, str]:
    token = str(api_key or "").strip()
    if not token:
        raise ValueError("OpenAI Platform credential does not contain an API key.")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def parse_openai_model_ids(payload: Any) -> List[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise OpenAIPlatformError("OpenAI Platform returned an invalid model response.", 502)
    model_ids: List[str] = []
    for item in payload["data"]:
        raw_id = item.get("id") if isinstance(item, dict) else None
        model_id = raw_id.strip() if isinstance(raw_id, str) else ""
        if model_id and model_id.isprintable() and model_id not in model_ids:
            model_ids.append(model_id)
    return model_ids[:500]


async def fetch_openai_model_ids(api_key: str) -> List[str]:
    try:
        response = await get_async(
            f"{normalize_openai_api_url(await get_openai_api_url())}/models",
            headers=build_openai_headers(api_key),
            timeout=30.0,
        )
    except (httpx.HTTPError, OSError) as exc:
        raise OpenAIPlatformError(
            "Unable to reach OpenAI Platform. Check outbound network and proxy settings.",
            502,
        ) from exc
    if response.status_code in {401, 403}:
        raise OpenAIPlatformError(
            "OpenAI Platform rejected this API key. Check the key and project permissions."
        )
    if response.status_code != 200:
        raise OpenAIPlatformError(
            f"OpenAI Platform model discovery failed with HTTP {response.status_code}.",
            502 if response.status_code >= 500 else 400,
        )
    try:
        model_ids = parse_openai_model_ids(response.json())
    except ValueError as exc:
        raise OpenAIPlatformError("OpenAI Platform returned invalid JSON.", 502) from exc
    if not model_ids:
        raise OpenAIPlatformError("The API key is valid, but no OpenAI models are available.")
    return model_ids


async def validate_openai_api_key(api_key: str) -> OpenAIPlatformValidation:
    normalized = str(api_key or "").strip()
    if len(normalized) < 16 or len(normalized) > 1024:
        raise OpenAIPlatformError("Enter a valid OpenAI Platform API key.")
    return OpenAIPlatformValidation(model_ids=await fetch_openai_model_ids(normalized))


# OpenAI Platform uses the same Chat Completions shape as the existing xAI adapter.
gemini_request_to_openai = gemini_request_to_xai
openai_response_to_gemini = xai_response_to_gemini
openai_stream_line_to_gemini = xai_stream_line_to_gemini
