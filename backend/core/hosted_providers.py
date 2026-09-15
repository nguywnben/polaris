"""API-key hosted Chat Completions providers; catalogs never prove inference access.

Protocol sources: docs/specs/provider-expansion-2026-09.md. Only documented vendor
origins accept credentials. Private endpoint paths remain configurable, but arbitrary
proxy hosts require a separately reviewed allowlist rather than implicit SSRF access.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from core.httpx_client import http_client
from core.openai_platform import gemini_request_to_openai
from core.provider_registry import (
    EXTENDED_CONNECTION_FIELDS,
    MAX_DECLARED_MODELS,
    MAX_MODEL_ID_LENGTH,
)

HOSTED_PROVIDERS = {
    "groq": {"name": "GroqCloud", "base_url": "https://api.groq.com/openai/v1"},
    "deepseek": {"name": "DeepSeek Platform", "base_url": "https://api.deepseek.com/v1"},
    "mistral": {"name": "Mistral AI Studio", "base_url": "https://api.mistral.ai/v1"},
    "cerebras": {"name": "Cerebras Cloud", "base_url": "https://api.cerebras.ai/v1"},
    "kimi": {"name": "Kimi API Platform", "base_url": "https://api.moonshot.ai/v1"},
    "cloudflare": {
        "name": "Cloudflare Workers AI",
        "base_url": "https://api.cloudflare.com/client/v4",
    },
    "nvidia": {"name": "NVIDIA NIM", "base_url": "https://integrate.api.nvidia.com/v1"},
    "poolside": {"name": "Poolside Platform", "base_url": "https://inference.poolside.ai/v1"},
    "kimchi": {"name": "Kimchi Coding", "base_url": "https://llm.kimchi.dev/openai/v1"},
    "kilo": {"name": "Kilo", "base_url": "https://api.kilo.ai/api/gateway"},
}
MAX_CATALOG_BYTES = 2 * 1024 * 1024
MAX_CATALOG_PAGES = 20
CATALOG_PAGE_SIZE = 50
# Official contracts: Kimi migration guide; NVIDIA Kimi inference reference;
# Cloudflare Chat schema; Poolside OpenAI examples; Kilo streaming guide.
# Poolside/Kilo also send usage automatically. Kimchi does not document this
# optional parameter, so do not infer support merely from OpenAI compatibility.
STREAM_USAGE_PROVIDERS = frozenset(
    {"kimi", "cloudflare", "nvidia", "poolside", "kilo", "groq", "deepseek"}
)


class HostedProviderError(ValueError):
    """Stable safe error; upstream bodies and secrets must never reach this message."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _base_url(provider: str, value: Any) -> str:
    default = HOSTED_PROVIDERS[provider]["base_url"]
    value = default if value is None or value == "" else value
    if not isinstance(value, str) or len(value) > 2048:
        raise HostedProviderError("Invalid provider API endpoint.")
    value = value.strip()
    if any(ord(c) < 33 or ord(c) > 126 for c in value) or "\\" in value or "%" in value:
        raise HostedProviderError("Invalid provider API endpoint.")
    try:
        parsed = urlsplit(value)
        allowed = {urlsplit(default).hostname}
        if provider == "kimi":
            allowed.add("api.moonshot.cn")
        valid = (
            parsed.scheme == "https"
            and parsed.hostname in allowed
            and parsed.port in {None, 443}
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and all(part not in {".", ".."} for part in parsed.path.split("/"))
        )
    except ValueError:
        valid = False
    if not valid:
        raise HostedProviderError("Invalid provider API endpoint.")
    return urlunsplit(("https", parsed.hostname, parsed.path.rstrip("/"), "", ""))


def normalize_credential(data: dict) -> dict:
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("provider"), str)
        or data["provider"] not in HOSTED_PROVIDERS
    ):
        raise HostedProviderError("Unsupported provider.")
    provider = data["provider"]
    key = data.get("api_key")
    if not isinstance(key, str):
        raise HostedProviderError("Provider credential does not contain an API key.")
    key = key.strip()
    if not key or len(key) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise HostedProviderError("Provider credential does not contain a valid API key.")
    normalized = {
        **data,
        "credential_type": "api_key",
        "api_key": key,
        "base_url": _base_url(provider, data.get("base_url")),
    }
    relevant = {"base_url"}
    if provider == "cloudflare":
        relevant.add("account_id")
    elif provider == "kilo":
        relevant.add("organization_id")
    for field in set(EXTENDED_CONNECTION_FIELDS) - relevant:
        normalized.pop(field, None)
    if provider == "cloudflare":
        account = data.get("account_id", "")
        if not isinstance(account, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", account.strip()):
            raise HostedProviderError("Enter a valid Cloudflare Account ID.")
        normalized["account_id"] = account.strip().lower()
    if provider == "kilo":
        organization = data.get("organization_id", "")
        if not isinstance(organization, str) or (
            organization and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", organization)
        ):
            raise HostedProviderError("Enter a valid organization ID.")
        normalized["organization_id"] = organization
    return normalized


def _headers(data: dict, streaming: bool = False) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {data['api_key']}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if streaming else "application/json",
    }
    if data["provider"] == "kilo" and data.get("organization_id"):
        headers["X-KiloCode-OrganizationId"] = data["organization_id"]
    return headers


def _valid_model_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= MAX_MODEL_ID_LENGTH
        and all(32 < ord(c) < 127 for c in value)
    )


def _link_tool_history(request: dict) -> dict:
    """Assign IDs by conversation history, not independent content-part indexes."""
    request = copy.deepcopy(request)
    parts = [
        part
        for content in request.get("contents") or []
        if isinstance(content, dict)
        for part in content.get("parts") or []
        if isinstance(part, dict)
    ]
    used_ids = {
        str(call["id"])
        for part in parts
        if isinstance(call := part.get("functionCall") or part.get("function_call"), dict)
        and call.get("id")
    }
    pending = {}
    counter = 0
    for part in parts:
        call = part.get("functionCall") or part.get("function_call")
        if isinstance(call, dict):
            if not call.get("id"):
                counter += 1
                while f"polaris_call_{counter}" in used_ids:
                    counter += 1
                call["id"] = f"polaris_call_{counter}"
                used_ids.add(call["id"])
            call_id = str(call["id"])
            if call_id in pending:
                raise HostedProviderError("Invalid tool call history.")
            pending[call_id] = call.get("name")
        result = part.get("functionResponse") or part.get("function_response")
        if isinstance(result, dict):
            if result.get("id"):
                call_id = str(result["id"])
                if call_id not in pending:
                    raise HostedProviderError("Invalid tool call history.")
            else:
                matches = [key for key, name in pending.items() if name == result.get("name")]
                if len(matches) != 1:
                    raise HostedProviderError("Invalid tool call history.")
                call_id = matches[0]
                result["id"] = call_id
            del pending[call_id]
    return request


def _restrict_tools(request: dict) -> None:
    """Keep caller tool restrictions exact when adapting Gemini to Chat."""
    config = (request.get("toolConfig") or {}).get("functionCallingConfig") or {}
    mode = config.get("mode", "AUTO")
    names = config.get("allowedFunctionNames") or []
    if (
        not isinstance(mode, str)
        or mode.upper() not in {"AUTO", "ANY", "NONE"}
        or not isinstance(names, list)
        or any(not isinstance(name, str) or not name for name in names)
    ):
        raise HostedProviderError("Invalid tool selection.")
    declared = set()
    for group in request.get("tools") or []:
        if not isinstance(group, dict) or set(group) - {"functionDeclarations"}:
            raise HostedProviderError("Only function tools are supported by this provider.")
        declarations = group.get("functionDeclarations") or []
        if not isinstance(declarations, list):
            raise HostedProviderError("Invalid function tools.")
        for declaration in declarations:
            if (
                not isinstance(declaration, dict)
                or not isinstance(declaration.get("name"), str)
                or not declaration["name"]
            ):
                raise HostedProviderError("Invalid function tools.")
            declared.add(declaration["name"])
        if names:
            group["functionDeclarations"] = [
                declaration for declaration in declarations if declaration["name"] in names
            ]
    if not set(names) <= declared:
        raise HostedProviderError("Invalid tool selection.")


def prepare_request(
    data: dict, gemini_request: dict, model: str, streaming: bool
) -> tuple[str, dict, dict]:
    """Convert canonical Gemini input without mutating it or dropping thought history."""
    data = normalize_credential(data)
    if not _valid_model_id(model):
        raise HostedProviderError("Invalid model ID.")
    base = data["base_url"]
    if data["provider"] in {"groq", "deepseek", "mistral", "cerebras"}:
        config = gemini_request.get("generationConfig") or {}
        allowed = {
            "temperature",
            "topP",
            "maxOutputTokens",
            "stopSequences",
            "candidateCount",
            "seed",
            "frequencyPenalty",
            "presencePenalty",
            "responseMimeType",
            "responseSchema",
        }
        if data["provider"] == "deepseek":
            allowed.remove("seed")
        if (
            not isinstance(config, dict)
            or any(value is not None and key not in allowed for key, value in config.items())
            or config.get("responseMimeType") not in (None, "text/plain", "application/json")
            or (
                config.get("responseSchema") is not None
                and config.get("responseMimeType") != "application/json"
            )
        ):
            raise HostedProviderError(
                "This provider does not support the requested generation options."
            )
    if data["provider"] == "cloudflare":
        base += f"/accounts/{data['account_id']}/ai/v1"
    gemini_request = _link_tool_history(gemini_request)
    _restrict_tools(gemini_request)
    payload = gemini_request_to_openai(gemini_request, model, streaming)
    if streaming and data["provider"] in STREAM_USAGE_PROVIDERS:
        payload["stream_options"] = {"include_usage": True}
    # Reuse the existing converter per content to retain exact tool-result placement.
    # Its generic adapter intentionally drops thoughts; hosted Kimi/Poolside need them.
    messages = [message for message in payload["messages"] if message["role"] == "system"]
    for content in gemini_request.get("contents") or []:
        if not isinstance(content, dict):
            continue
        converted = gemini_request_to_openai({"contents": [content]}, model, streaming)["messages"]
        reasoning = "".join(
            part["text"]
            for part in content.get("parts") or []
            if isinstance(part, dict)
            and part.get("thought") is True
            and isinstance(part.get("text"), str)
        )
        if content.get("role") == "model" and reasoning:
            assistant = next(
                (message for message in converted if message["role"] == "assistant"), None
            )
            if assistant is None:
                assistant = {"role": "assistant", "content": None}
                converted.insert(0, assistant)
            assistant["reasoning_content"] = reasoning
        messages.extend(converted)
    payload["messages"] = messages
    # Polaris Chat rejects reasoning_content history at its public boundary.
    # Default to replay-safe chat; canonical callers that retain thoughts can
    # continue reasoning histories without dropping the provider's state.
    has_reasoning = any(message.get("reasoning_content") for message in messages)
    if data["provider"] == "deepseek":
        payload["thinking"] = {"type": "enabled" if has_reasoning else "disabled"}
    if data["provider"] == "mistral":
        payload["reasoning_effort"] = "high" if has_reasoning else "none"
        if "seed" in payload:
            payload["random_seed"] = payload.pop("seed")
        _mistral_history(messages)
    return base + "/chat/completions", _headers(data, streaming), payload


def _mistral_history(messages: list[dict]) -> None:
    """Use Mistral content chunks and paired nine-character wire tool IDs."""
    ids = {call["id"] for message in messages for call in message.get("tool_calls", [])}
    mapping = {key: key for key in ids if re.fullmatch(r"[A-Za-z0-9]{9}", key)}
    reserved = set(mapping.values())
    counter = 0
    for key in sorted(ids - mapping.keys()):
        counter += 1
        candidate = f"p{counter:08d}"
        while candidate in reserved:
            counter += 1
            candidate = f"p{counter:08d}"
        mapping[key] = candidate
        reserved.add(candidate)
    for message in messages:
        reasoning = message.pop("reasoning_content", None)
        if reasoning:
            content = message.get("content")
            chunks = [{"type": "thinking", "thinking": [{"type": "text", "text": reasoning}]}]
            if isinstance(content, str) and content:
                chunks.append({"type": "text", "text": content})
            elif isinstance(content, list):
                chunks.extend(content)
            message["content"] = chunks
        for call in message.get("tool_calls", []):
            call["id"] = mapping[call["id"]]
        if "tool_call_id" in message:
            message["tool_call_id"] = mapping[message["tool_call_id"]]


async def _catalog_json(url: str, headers: dict) -> dict:
    try:
        async with http_client.get_client(
            timeout=30.0, destination_url=url, follow_redirects=False
        ) as client:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code != 200:
                    status = response.status_code
                    raise HostedProviderError(
                        f"Provider model discovery failed with HTTP {status}.",
                        status if status in {401, 403, 429} else 502,
                    )
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > MAX_CATALOG_BYTES:
                        raise HostedProviderError("Provider model response is too large.", 502)
    except (httpx.HTTPError, OSError) as exc:
        raise HostedProviderError(
            "Unable to reach provider. Check outbound network and proxy settings.", 502
        ) from exc
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise HostedProviderError("Provider returned invalid JSON.", 502) from exc
    if not isinstance(payload, dict):
        raise HostedProviderError("Provider returned an invalid model response.", 502)
    return payload


def _catalog_ids(payload: dict, provider: str) -> list[str]:
    key = "result" if provider == "cloudflare" else "models" if provider == "kimchi" else "data"
    items = payload.get(key)
    if not isinstance(items, list) or (
        provider == "cloudflare" and payload.get("success") is not True
    ):
        raise HostedProviderError("Provider returned an invalid model response.", 502)
    if provider in {"groq", "deepseek", "mistral", "cerebras"} and len(items) > MAX_DECLARED_MODELS:
        raise HostedProviderError("Provider model response is too large.", 502)
    result = []
    for item in items:
        model = None
        if isinstance(item, dict):
            model = (
                item.get("name")
                if provider == "cloudflare"
                else (
                    item.get("slug") or item.get("id") if provider == "kimchi" else item.get("id")
                )
            )
        if not _valid_model_id(model):
            raise HostedProviderError("Provider returned an invalid model response.", 502)
        if provider == "groq" and (
            item.get("active") is False
            or model.startswith(("whisper-", "canopylabs/orpheus-", "playai-", "groq/compound"))
            or "prompt-guard" in model
        ):
            continue
        if provider == "mistral" and (
            item.get("archived") is True
            or not isinstance(item.get("capabilities"), dict)
            or item["capabilities"].get("completion_chat") is not True
        ):
            continue
        if model not in result:
            result.append(model)
        if len(result) > MAX_DECLARED_MODELS:
            raise HostedProviderError("Provider model response is too large.", 502)
    return result


async def discover_models(data: dict) -> list[str]:
    """Fetch catalogs only, never spend tokens to infer whether a key is authorized."""
    data = normalize_credential(data)
    provider, base = data["provider"], data["base_url"]
    headers = _headers(data)
    if provider != "cloudflare":
        url = base + "/models"
        if provider == "kimchi":
            parsed = urlsplit(base)
            url = urlunsplit(
                (parsed.scheme, parsed.netloc, "/v1/models/metadata", "include_in_cli=true", "")
            )
        result = _catalog_ids(await _catalog_json(url, headers), provider)
    else:
        result = []
        for page in range(1, MAX_CATALOG_PAGES + 1):
            query = urlencode(
                {"task": "Text Generation", "page": page, "per_page": CATALOG_PAGE_SIZE}
            )
            url = f"{base}/accounts/{data['account_id']}/ai/models/search?{query}"
            payload = await _catalog_json(url, headers)
            page_ids = _catalog_ids(payload, provider)
            new_ids = [model for model in page_ids if model not in result]
            if page_ids and not new_ids:
                raise HostedProviderError("Provider model pagination did not advance.", 502)
            result.extend(new_ids)
            if len(result) > MAX_DECLARED_MODELS:
                raise HostedProviderError("Provider model response is too large.", 502)
            info = payload.get("result_info", {})
            if not isinstance(info, dict):
                raise HostedProviderError("Provider returned invalid model pagination.", 502)
            total_pages = info.get("total_pages")
            if total_pages is not None:
                if (
                    type(total_pages) is not int
                    or total_pages < page
                    or total_pages > MAX_CATALOG_PAGES
                ):
                    raise HostedProviderError("Provider returned invalid model pagination.", 502)
                if page == total_pages:
                    break
                if not page_ids:
                    raise HostedProviderError("Provider model pagination did not advance.", 502)
            elif len(payload["result"]) < CATALOG_PAGE_SIZE:
                break
        else:
            raise HostedProviderError("Provider model response is too large.", 502)
    if not result:
        raise HostedProviderError("No models are available from this provider.")
    return result
