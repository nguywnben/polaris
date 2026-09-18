"""Google AI Studio API-key provider integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List
from urllib.parse import quote, urlencode

import httpx
from config import get_google_ai_studio_api_url
from core.httpx_client import get_async
from core.provider_registry import GOOGLE_AI_STUDIO, MAX_DECLARED_MODELS, normalize_provider_id


class GoogleAIStudioError(RuntimeError):
    """A sanitized Google AI Studio validation error."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GoogleAIStudioValidation:
    model_ids: List[str]

    @property
    def model_count(self) -> int:
        return len(self.model_ids)


def parse_api_key_import_payload(payload: Any) -> List[str]:
    """Extract Google AI Studio API keys from a supported JSON payload."""
    entries: List[Any]

    if isinstance(payload, dict):
        declared_provider = payload.get("provider")
        if declared_provider and normalize_provider_id(declared_provider) != GOOGLE_AI_STUDIO:
            raise ValueError("The import payload targets a different provider.")
        if "api_keys" in payload:
            if not isinstance(payload["api_keys"], list):
                raise ValueError("The api_keys field must be an array.")
            entries = payload["api_keys"]
        elif "api_key" in payload:
            entries = [payload]
        else:
            raise ValueError("The JSON payload must contain api_key or api_keys.")
    elif isinstance(payload, list):
        entries = payload
    else:
        raise ValueError("The JSON payload must be an object or array.")

    api_keys: List[str] = []
    for index, entry in enumerate(entries, start=1):
        if isinstance(entry, str):
            api_key = entry.strip()
        elif isinstance(entry, dict):
            declared_provider = entry.get("provider")
            if declared_provider and normalize_provider_id(declared_provider) != GOOGLE_AI_STUDIO:
                raise ValueError(f"Entry {index} targets a different provider.")
            api_key = str(entry.get("api_key") or "").strip()
        else:
            raise ValueError(f"Entry {index} must be an API key string or object.")

        if not api_key:
            raise ValueError(f"Entry {index} does not contain an API key.")
        api_keys.append(api_key)

    if not api_keys:
        raise ValueError("The import payload does not contain any API keys.")
    return api_keys


def normalize_api_base_url(value: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    if not normalized.startswith(("https://", "http://")):
        raise ValueError("Google AI Studio API endpoint must use HTTP or HTTPS.")
    return normalized


def build_models_url(api_base_url: str) -> str:
    return f"{normalize_api_base_url(api_base_url)}/v1beta/models"


def build_generation_url(api_base_url: str, model: str, streaming: bool) -> str:
    model_id = str(model or "").strip()
    if model_id.startswith("models/"):
        model_id = model_id[7:]
    if not model_id:
        raise ValueError("A model name is required for Google AI Studio requests.")
    safe_model = quote(model_id, safe="-._")
    operation = "streamGenerateContent?alt=sse" if streaming else "generateContent"
    return f"{build_models_url(api_base_url)}/{safe_model}:{operation}"


def build_api_key_headers(api_key: str) -> Dict[str, str]:
    normalized = str(api_key or "").strip()
    if not normalized:
        raise ValueError("Google AI Studio API key is missing.")
    return {
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip",
        "x-goog-api-key": normalized,
    }


def parse_model_ids(payload: Any) -> List[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise GoogleAIStudioError(
            "Google AI Studio returned an invalid model response.", status_code=502
        )

    model_ids = []
    for model in payload["models"]:
        if not isinstance(model, dict):
            continue
        supported_methods = model.get("supportedGenerationMethods") or []
        if "generateContent" not in supported_methods:
            continue
        model_id = str(model.get("name") or "").strip()
        if model_id.startswith("models/"):
            model_id = model_id[7:]
        if model_id and model_id not in model_ids:
            model_ids.append(model_id)
    return model_ids


async def _fetch_model_page(url: str, headers: Dict[str, str]) -> Any:
    try:
        response = await get_async(url, headers=headers, timeout=30.0)
    except (httpx.HTTPError, OSError) as exc:
        raise GoogleAIStudioError(
            "Unable to reach Google AI Studio. Check outbound network and proxy settings.",
            status_code=502,
        ) from exc

    if response.status_code in (401, 403):
        raise GoogleAIStudioError(
            "Google rejected this API key. Check the key and its project restrictions."
        )
    if response.status_code != 200:
        raise GoogleAIStudioError(
            f"Google AI Studio validation failed with HTTP {response.status_code}.",
            status_code=502 if response.status_code >= 500 else 400,
        )

    try:
        return response.json()
    except ValueError as exc:
        raise GoogleAIStudioError(
            "Google AI Studio returned an invalid JSON response.", status_code=502
        ) from exc


async def validate_api_key(api_key: str) -> GoogleAIStudioValidation:
    """Discover every catalog page, without treating a partial catalog as success."""
    normalized_key = str(api_key or "").strip()
    if len(normalized_key) < 16 or len(normalized_key) > 512:
        raise GoogleAIStudioError("Enter a valid Google AI Studio API key.")
    url = build_models_url(await get_google_ai_studio_api_url())
    headers = build_api_key_headers(normalized_key)
    model_ids: List[str] = []
    cursors: set[str] = set()
    cursor = ""
    try:
        async with asyncio.timeout(30.0):
            # https://ai.google.dev/api/models#method:-models.list
            for _ in range(20):
                page_url = f"{url}?{urlencode({'pageToken': cursor})}" if cursor else url
                payload = await _fetch_model_page(page_url, headers)
                model_ids = list(dict.fromkeys([*model_ids, *parse_model_ids(payload)]))
                if len(model_ids) > MAX_DECLARED_MODELS:
                    raise GoogleAIStudioError("Google AI Studio model catalog is too large.", 502)
                cursor = payload.get("nextPageToken", "")
                if cursor == "":
                    break
                if not isinstance(cursor, str) or len(cursor) > 4096 or cursor in cursors:
                    raise GoogleAIStudioError("Google AI Studio returned invalid pagination.", 502)
                cursors.add(cursor)
            else:
                raise GoogleAIStudioError(
                    "Google AI Studio model catalog exceeds the page limit.", 502
                )
    except TimeoutError as exc:
        raise GoogleAIStudioError("Google AI Studio model discovery timed out.", 504) from exc
    if not model_ids:
        raise GoogleAIStudioError(
            "The API key is valid, but no generate-content models are available."
        )
    return GoogleAIStudioValidation(model_ids=model_ids)
