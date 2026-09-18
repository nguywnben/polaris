"""OpenCode Zen/Go API-key transport at the canonical Gemini boundary.

Protocol contracts: https://opencode.ai/docs/zen/#endpoints and
https://opencode.ai/docs/go/#endpoints. Catalog access is public and is not an
authentication check. No browser login, public-key impersonation or paid probes.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from core.anthropic import gemini_request_to_anthropic
from core.codex import gemini_request_to_codex
from core.httpx_client import http_client
from core.provider_registry import MAX_DECLARED_MODELS, MAX_MODEL_ID_LENGTH
from core.xai import gemini_request_to_xai

DEFAULT_BASE_URLS = {
    "zen": "https://opencode.ai/zen/v1",
    "go": "https://opencode.ai/zen/go/v1",
}
MAX_CATALOG_BYTES = 1024 * 1024
USER_AGENT = "Polaris/0.1 (OpenCode API integration)"
_MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,255}$")
_SESSION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")


class OpenCodeError(ValueError):
    """Sanitized failure safe to expose through provider management APIs."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _base_url(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise OpenCodeError("Invalid OpenCode API base URL.")
    value = value.strip().rstrip("/")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise OpenCodeError("Invalid OpenCode API base URL.") from None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "opencode.ai"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(character.isspace() or ord(character) < 32 for character in value)
        or "\\" in value
        or "%" in value
        or any(segment in {".", ".."} for segment in parsed.path.split("/"))
        or port not in {None, 443}
    ):
        raise OpenCodeError("OpenCode API base URL requires HTTPS without credentials or queries.")
    return value


def normalize_credential(data: dict) -> dict:
    if not isinstance(data, dict):
        raise OpenCodeError("OpenCode credential must be an object.")
    key = data.get("api_key")
    if (
        not isinstance(key, str)
        or not key.strip()
        or len(key) > 8192
        or key.strip().lower() == "public"
        or any(ord(character) < 33 or ord(character) > 126 for character in key.strip())
    ):
        raise OpenCodeError("An OpenCode API key is required.")
    plan = data.get("plan", "zen")
    if plan not in DEFAULT_BASE_URLS:
        raise OpenCodeError("OpenCode plan must be Zen or Go.")
    base = _base_url(data.get("base_url") or DEFAULT_BASE_URLS[plan])
    models = data.get("model_ids") or []
    if not isinstance(models, list) or len(models) > MAX_DECLARED_MODELS:
        raise OpenCodeError("Invalid OpenCode model list.")
    result = {
        **data,
        "provider": "opencode",
        "credential_type": "api_key",
        "api_key": key.strip(),
        "plan": plan,
        "base_url": base,
        "model_ids": [],
    }
    for model in models:
        protocol_for_model(result, model)
        if model not in result["model_ids"]:
            result["model_ids"].append(model)
    return result


def protocol_for_model(data: dict, model: str) -> str:
    """Known documented families only; unknown future protocols fail closed."""
    if (
        not isinstance(model, str)
        or len(model) > MAX_MODEL_ID_LENGTH
        or not _MODEL_ID.fullmatch(model)
    ):
        raise OpenCodeError("Invalid OpenCode model identifier.")
    plan = data.get("plan", "zen")
    if plan not in DEFAULT_BASE_URLS:
        raise OpenCodeError("OpenCode plan must be Zen or Go.")
    if model.startswith(("gpt-", "grok-", "muse-spark-")):
        return "responses"
    if model.startswith("claude-"):
        if plan == "go":
            raise OpenCodeError("Claude models require the OpenCode Zen plan.")
        return "anthropic"
    if model.startswith("qwen") and re.match(r"^qwen\d", model):
        return "anthropic"
    if model.startswith("gemini-"):
        if plan == "go":
            raise OpenCodeError("Gemini models require the OpenCode Zen plan.")
        return "gemini"
    if model.startswith("minimax-"):
        return "anthropic" if plan == "go" else "openai"
    if (
        model == "big-pickle"
        or model.startswith(
            ("glm-", "kimi-", "deepseek-", "mimo-", "nemotron-", "ling-", "longcat-")
        )
        or model in {"hy3", "hy4-preview"}
    ):
        return "openai"
    raise OpenCodeError("OpenCode model protocol is not supported yet.")


async def discover_models(data: dict) -> list[str]:
    """Read a bounded public catalog, without leaking the account key to it."""
    normalized = normalize_credential(data)
    url = normalized["base_url"] + "/models"
    try:
        async with http_client.get_client(
            timeout=20.0, destination_url=url, follow_redirects=False
        ) as client:
            async with client.stream(
                "GET", url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
            ) as response:
                if response.status_code != 200:
                    raise OpenCodeError(
                        "OpenCode model discovery failed.",
                        response.status_code if response.status_code >= 400 else 502,
                    )
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    body.extend(chunk)
                    if len(body) > MAX_CATALOG_BYTES:
                        raise OpenCodeError("OpenCode model catalog exceeds the size limit.", 502)
        payload = json.loads(body)
    except httpx.HTTPError:
        raise OpenCodeError("OpenCode model discovery could not reach the server.", 502) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise OpenCodeError("OpenCode returned an invalid model catalog.", 502) from None
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list) or len(items) > MAX_DECLARED_MODELS:
        raise OpenCodeError("OpenCode returned an invalid model catalog.", 502)
    result = []
    for item in items:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not _MODEL_ID.fullmatch(item["id"])
        ):
            raise OpenCodeError("OpenCode returned an invalid model identifier.", 502)
        try:
            protocol_for_model(normalized, item["id"])
        except OpenCodeError:
            continue
        if item["id"] not in result:
            result.append(item["id"])
    if not result:
        raise OpenCodeError("OpenCode returned no supported models.", 502)
    return result


def _session_id(data: dict, request: dict) -> str:
    supplied = request.get("_polaris_session_id")
    if supplied is not None:
        if not isinstance(supplied, str) or not _SESSION_ID.fullmatch(supplied):
            raise OpenCodeError("Invalid OpenCode conversation session identifier.")
        return supplied
    # Preserve a stable fallback across follow-up turns without transmitting
    # prompt text. Explicit native session IDs avoid equal-opening conversations
    # sharing a cache identity. Key scoping prevents cross-account correlation.
    opening = next(
        (item for item in request.get("contents", []) if item.get("role") != "model"), {}
    )
    digest = hmac.new(
        data["api_key"].encode(),
        json.dumps(opening, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    return "polaris-" + digest


def _check_semantics(payload: dict, protocol: str) -> None:
    config = payload.get("generationConfig") or {}
    if protocol == "gemini":
        return
    # The non-native converters do not round-trip signed reasoning blocks.
    # Reject them before conversion instead of silently losing history/signatures.
    history = [payload.get("systemInstruction") or {}, *(payload.get("contents") or [])]
    for item in history:
        for part in item.get("parts") or []:
            if part.get("thought") is True or "thoughtSignature" in part:
                raise OpenCodeError(
                    "Reasoning history is supported only by native Gemini on OpenCode."
                )
    function = (payload.get("toolConfig") or {}).get("functionCallingConfig") or {}
    if (
        function.get("mode", "AUTO").upper() not in {"AUTO", "ANY", "NONE"}
        or len(function.get("allowedFunctionNames") or []) > 1
    ):
        raise OpenCodeError("Requested tool selection is unsupported by this OpenCode protocol.")
    allowed = {"maxOutputTokens", "temperature", "topP", "responseMimeType", "responseSchema"}
    if protocol == "openai":
        allowed |= {
            "stopSequences",
            "candidateCount",
            "seed",
            "frequencyPenalty",
            "presencePenalty",
        }
    elif protocol == "anthropic":
        allowed |= {"topK", "stopSequences"}
    for field, value in config.items():
        if (
            value is not None
            and field not in allowed
            and not (field == "candidateCount" and value == 1)
        ):
            raise OpenCodeError(
                "Requested generation option is unsupported by this OpenCode protocol."
            )
    if config.get("responseMimeType") not in {None, "text/plain", "application/json"}:
        raise OpenCodeError("Requested output type is unsupported by this OpenCode protocol.")
    if (
        protocol == "anthropic"
        and config.get("responseMimeType") == "application/json"
        and not config.get("responseSchema")
    ):
        raise OpenCodeError("OpenCode Messages JSON output requires a response schema.")
    for group in payload.get("tools") or []:
        if set(group) - {"functionDeclarations"}:
            raise OpenCodeError("Only function tools are supported by this OpenCode protocol.")
    for item in payload.get("contents") or []:
        for part in item.get("parts") or []:
            if set(part) - {
                "text",
                "thought",
                "thoughtSignature",
                "inlineData",
                "inline_data",
                "functionCall",
                "function_call",
                "functionResponse",
                "function_response",
            }:
                raise OpenCodeError(
                    "Requested content part is unsupported by this OpenCode protocol."
                )
            if "fileData" in part or "file_data" in part:
                raise OpenCodeError("Remote file parts are unsupported by this OpenCode protocol.")
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and not str(
                inline.get("mimeType") or inline.get("mime_type") or ""
            ).startswith("image/"):
                raise OpenCodeError("Only inline images are supported by this OpenCode protocol.")


def _link_tool_ids(payload: dict) -> None:
    """Supply consistent call/result IDs when Gemini callers only send names."""
    pending: dict[str, list[str]] = {}
    counter = 0
    for item in payload.get("contents") or []:
        for part in item.get("parts") or []:
            call = part.get("functionCall") or part.get("function_call")
            if isinstance(call, dict):
                counter += 1
                name = str(call.get("name") or "tool")
                call["id"] = str(call.get("id") or f"polaris_call_{counter}")
                pending.setdefault(name, []).append(call["id"])
            result = part.get("functionResponse") or part.get("function_response")
            if isinstance(result, dict):
                name = str(result.get("name") or "tool")
                candidates = pending.get(name, [])
                if not result.get("id"):
                    if len(candidates) != 1:
                        raise OpenCodeError(
                            "Tool result requires an unambiguous matching call identifier."
                        )
                    result["id"] = candidates[0]
                if result["id"] in candidates:
                    candidates.remove(result["id"])


def prepare_request(
    data: dict, gemini_request: dict, model: str, streaming: bool
) -> tuple[str, dict, dict]:
    normalized = normalize_credential(data)
    protocol = protocol_for_model(normalized, model)
    _check_semantics(gemini_request, protocol)
    source = copy.deepcopy(gemini_request)
    if protocol != "gemini":
        _link_tool_ids(source)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "x-opencode-session": _session_id(normalized, source),
    }
    if streaming:
        headers["Accept"] = "text/event-stream"
    base = normalized["base_url"]
    if protocol == "anthropic":
        headers.update({"x-api-key": normalized["api_key"], "anthropic-version": "2023-06-01"})
        body = gemini_request_to_anthropic(source, model, streaming)
        function = (source.get("toolConfig") or {}).get("functionCallingConfig") or {}
        mode = function.get("mode", "AUTO").upper()
        names = function.get("allowedFunctionNames") or []
        if mode == "NONE":
            body.pop("tools", None)
        elif mode == "ANY":
            if len(names) > 1:
                raise OpenCodeError("Multiple forced tools are unsupported by OpenCode Messages.")
            body["tool_choice"] = {"type": "tool", "name": names[0]} if names else {"type": "any"}
        return base + "/messages", headers, body
    headers["Authorization"] = "Bearer " + normalized["api_key"]
    if protocol == "gemini":
        body = {key: value for key, value in source.items() if not key.startswith("_")}
        operation = "streamGenerateContent?alt=sse" if streaming else "generateContent"
        return f"{base}/models/{model}:{operation}", headers, body
    if protocol == "openai":
        body = gemini_request_to_xai(source, model, streaming)
        if streaming:
            body["stream_options"] = {"include_usage": True}
        return base + "/chat/completions", headers, body
    body = gemini_request_to_codex(source, model, streaming)
    body["stream"] = bool(streaming)
    body.pop("include", None)
    config = source.get("generationConfig") or {}
    for origin, target in {
        "maxOutputTokens": "max_output_tokens",
        "temperature": "temperature",
        "topP": "top_p",
    }.items():
        if config.get(origin) is not None:
            body[target] = config[origin]
    if config.get("responseMimeType") == "application/json":
        output = {"type": "json_object"}
        if config.get("responseSchema"):
            output = {"type": "json_schema", "name": "response", "schema": config["responseSchema"]}
        body["text"] = {"format": output}
    return base + "/responses", headers, body
