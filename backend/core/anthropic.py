"""Claude Code OAuth and Claude Platform Messages API helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from urllib.parse import urlencode, urlparse

import httpx
from config import (
    get_anthropic_api_url,
    get_claude_client_id,
    get_claude_oauth_authorize_url,
    get_claude_oauth_token_url,
    get_claude_user_agent,
)
from core.credential_manager import credential_manager
from core.httpx_client import get_async, post_async
from core.provider_authorization_coordination import (
    ProviderAuthorizationError,
    get_provider_authorization_service,
    is_provider_authorization_state,
)
from core.provider_registry import (
    ANTHROPIC,
    MAX_DECLARED_MODELS,
    MAX_MODEL_ID_LENGTH,
    api_key_fingerprint,
)

ANTHROPIC_VERSION = "2023-06-01"
CLAUDE_OAUTH_BETA = "claude-code-20250219,oauth-2025-04-20"
CLAUDE_SCOPE = "org:create_api_key user:profile user:inference"
ANTHROPIC_REDIRECT_URI = "http://localhost:4283/callback"
CLAUDE_FLOW_TTL_SECONDS = 15 * 60
_stream_tool_blocks: Dict[str, Dict[int, Dict[str, Any]]] = {}


class AnthropicError(RuntimeError):
    """A sanitized Anthropic integration error."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AnthropicValidation:
    model_ids: List[str]

    @property
    def model_count(self) -> int:
        return len(self.model_ids)


def normalize_anthropic_api_url(value: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Anthropic API endpoint must use HTTP or HTTPS.")
    if parsed.username or parsed.password:
        raise ValueError("Anthropic API endpoint must not contain credentials.")
    return normalized


def normalize_claude_oauth_url(value: str, label: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    parsed = urlparse(normalized)
    hostname = str(parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname:
        raise ValueError(f"{label} must use HTTPS.")
    if (
        hostname != "anthropic.com"
        and not hostname.endswith(".anthropic.com")
        and hostname != "claude.ai"
        and not hostname.endswith(".claude.ai")
    ):
        raise ValueError(f"{label} must use an Anthropic or Claude host.")
    return normalized


def build_anthropic_headers(
    credential_data: Dict[str, Any],
    *,
    user_agent: str = "",
) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
    }
    credential_type = str(credential_data.get("credential_type") or "").strip().lower()
    if credential_type == "oauth":
        token = str(
            credential_data.get("access_token") or credential_data.get("token") or ""
        ).strip()
        if not token:
            raise ValueError("Claude Code credential does not contain an access token.")
        headers["Authorization"] = f"Bearer {token}"
        headers["anthropic-beta"] = CLAUDE_OAUTH_BETA
        headers["x-app"] = "cli"
    else:
        api_key = str(credential_data.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("Claude Platform credential does not contain an API key.")
        headers["x-api-key"] = api_key
    if str(user_agent or "").strip():
        headers["User-Agent"] = str(user_agent).strip()
    return headers


def parse_anthropic_model_ids(payload: Any) -> List[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise AnthropicError("Anthropic returned an invalid model response.", 502)
    models: List[str] = []
    for item in payload["data"]:
        model_id = str(item.get("id") if isinstance(item, dict) else "").strip()
        if (
            model_id
            and len(model_id) <= MAX_MODEL_ID_LENGTH
            and model_id.isprintable()
            and model_id not in models
        ):
            models.append(model_id)
            if len(models) >= MAX_DECLARED_MODELS:
                break
    return models


async def fetch_anthropic_model_ids(credential_data: Dict[str, Any]) -> List[str]:
    try:
        response = await get_async(
            f"{normalize_anthropic_api_url(await get_anthropic_api_url())}/models",
            headers=build_anthropic_headers(
                credential_data,
                user_agent=await get_claude_user_agent(),
            ),
            timeout=30.0,
        )
    except (httpx.HTTPError, OSError) as exc:
        raise AnthropicError(
            "Unable to reach Anthropic. Check outbound network and proxy settings.", 502
        ) from exc
    if response.status_code in {401, 403}:
        raise AnthropicError(
            "Anthropic rejected this credential. Check its access and permissions."
        )
    if response.status_code != 200:
        raise AnthropicError(
            f"Anthropic model discovery failed with HTTP {response.status_code}.",
            502 if response.status_code >= 500 else 400,
        )
    try:
        model_ids = parse_anthropic_model_ids(response.json())
    except ValueError as exc:
        raise AnthropicError("Anthropic returned invalid JSON.", 502) from exc
    if not model_ids:
        raise AnthropicError("The credential is valid, but no Claude models are available.")
    return model_ids


async def validate_anthropic_api_key(api_key: str) -> AnthropicValidation:
    normalized = str(api_key or "").strip()
    if len(normalized) < 16 or len(normalized) > 1024:
        raise AnthropicError("Enter a valid Claude Platform API key.")
    credential = {"provider": ANTHROPIC, "credential_type": "api_key", "api_key": normalized}
    return AnthropicValidation(model_ids=await fetch_anthropic_model_ids(credential))


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def is_claude_oauth_state(state: str | None) -> bool:
    """Return whether callback state is syntactically routed to Claude Code."""
    return is_provider_authorization_state("claude", state)


def _decode_claude_authorization(payload: bytes) -> Dict[str, str]:
    try:
        pairs = json.loads(payload, object_pairs_hook=lambda values: values)
        if type(pairs) is not list or any(type(pair) is not tuple for pair in pairs):
            raise ValueError
        flow = dict(pairs)
        if len(flow) != len(pairs) or set(flow) != {
            "client_id",
            "code_verifier",
            "schema_version",
        }:
            raise ValueError
        client_id = flow["client_id"]
        verifier = flow["code_verifier"]
        if (
            flow["schema_version"] != 1
            or type(client_id) is not str
            or not 1 <= len(client_id) <= 1024
            or not client_id.isprintable()
            or type(verifier) is not str
            or len(verifier) != 128
            or any(
                character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
                for character in verifier
            )
        ):
            raise ValueError
        return {"client_id": client_id, "code_verifier": verifier}
    except Exception:
        raise AnthropicError(
            "The Claude Code authorization session was not found or has expired."
        ) from None


async def create_claude_oauth_url() -> Dict[str, str]:
    verifier = _base64url(os.urandom(96))
    challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
    client_id = await get_claude_client_id()
    authorize_url = normalize_claude_oauth_url(
        await get_claude_oauth_authorize_url(), "Claude authorization endpoint"
    )
    try:
        state = await get_provider_authorization_service().create(
            "claude",
            json.dumps(
                {
                    "client_id": client_id,
                    "code_verifier": verifier,
                    "schema_version": 1,
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii"),
            ttl_seconds=CLAUDE_FLOW_TTL_SECONDS,
        )
    except ProviderAuthorizationError:
        raise AnthropicError(
            "The Claude Code authorization session could not be started.", 503
        ) from None
    params = {
        "code": "true",
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": ANTHROPIC_REDIRECT_URI,
        "scope": CLAUDE_SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return {
        "auth_url": f"{authorize_url}?{urlencode(params)}",
        "state": state,
        "redirect_uri": ANTHROPIC_REDIRECT_URI,
    }


async def _exchange_claude_token(payload: Dict[str, Any], token_url: str) -> Dict[str, Any]:
    endpoint = normalize_claude_oauth_url(token_url, "Claude token endpoint")
    try:
        response = await post_async(
            endpoint,
            json=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30.0,
        )
    except (httpx.HTTPError, OSError) as exc:
        raise AnthropicError("Unable to reach the Claude OAuth token endpoint.", 502) from exc
    if response.status_code != 200:
        raise AnthropicError("Claude Code did not accept the OAuth authorization response.")
    try:
        tokens = response.json()
    except ValueError as exc:
        raise AnthropicError("Claude Code returned an invalid OAuth token response.", 502) from exc
    if not tokens.get("access_token"):
        raise AnthropicError("Claude Code OAuth response did not include an access token.", 502)
    return tokens


async def complete_claude_oauth(code: str, state: str) -> Dict[str, Any]:
    raw_code = str(code or "").strip()
    submitted_state = str(state or "").strip()
    if "#" in raw_code:
        raw_code, code_state = raw_code.split("#", 1)
        submitted_state = code_state.strip() or submitted_state
    if not raw_code:
        raise AnthropicError("Enter the authorization code shown by Claude.")
    if "://" in raw_code or "code=" in raw_code:
        raise AnthropicError("Enter the Claude authorization code, not a callback URL.")
    try:
        flow = _decode_claude_authorization(
            await get_provider_authorization_service().consume("claude", submitted_state)
        )
    except ProviderAuthorizationError:
        raise AnthropicError("The Claude Code authorization session was not found or has expired.")
    token_url = await get_claude_oauth_token_url()
    tokens = await _exchange_claude_token(
        {
            "code": raw_code,
            "state": submitted_state,
            "grant_type": "authorization_code",
            "client_id": flow["client_id"],
            "redirect_uri": ANTHROPIC_REDIRECT_URI,
            "code_verifier": flow["code_verifier"],
        },
        token_url,
    )
    credential = {
        "provider": ANTHROPIC,
        "credential_type": "oauth",
        "access_token": tokens["access_token"],
        "token": tokens["access_token"],
        "refresh_token": str(tokens.get("refresh_token") or ""),
        "token_type": str(tokens.get("token_type") or "Bearer"),
        "client_id": flow["client_id"],
        "token_uri": token_url,
    }
    model_ids = await fetch_anthropic_model_ids(credential)
    expires_in = max(60, int(tokens.get("expires_in") or 3600))
    identity = str(
        tokens.get("email")
        or (tokens.get("account") or {}).get("email")
        or credential["refresh_token"]
        or credential["access_token"]
    ).strip()
    fingerprint = api_key_fingerprint(identity)
    credential.update(
        {
            "user_email": identity if "@" in identity else "",
            "credential_label": identity
            if "@" in identity
            else f"Claude Code account {fingerprint[:8]}",
            "account_fingerprint": fingerprint,
            "model_ids": model_ids,
            "expiry": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    filename = f"claude-code-{fingerprint}.json"
    saved = await credential_manager.add_primary_credential(filename, credential)
    return {
        "action": saved.get("action", "created"),
        "filename": saved.get("filename", filename),
        "label": credential["credential_label"],
        "model_count": len(model_ids),
    }


async def refresh_claude_oauth_credential(credential_data: Dict[str, Any]) -> Dict[str, Any]:
    refresh_token = str(credential_data.get("refresh_token") or "").strip()
    if not refresh_token:
        raise AnthropicError("Claude Code credential does not contain a refresh token.", 401)
    token_url = str(credential_data.get("token_uri") or await get_claude_oauth_token_url()).strip()
    client_id = str(credential_data.get("client_id") or await get_claude_client_id()).strip()
    tokens = await _exchange_claude_token(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        },
        token_url,
    )
    refreshed = dict(credential_data)
    expires_in = max(60, int(tokens.get("expires_in") or 3600))
    refreshed.update(
        {
            "access_token": tokens["access_token"],
            "token": tokens["access_token"],
            "refresh_token": str(tokens.get("refresh_token") or refresh_token),
            "expiry": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
        }
    )
    return refreshed


def _text_parts(parts: List[Dict[str, Any]]) -> str:
    return "\n".join(
        str(part.get("text") or "")
        for part in parts
        if isinstance(part, dict)
        and part.get("text") is not None
        and part.get("thought") is not True
    ).strip()


def _anthropic_content(parts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for index, part in enumerate(parts):
        if not isinstance(part, dict) or part.get("thought") is True:
            continue
        if part.get("text") is not None:
            blocks.append({"type": "text", "text": str(part.get("text") or "")})
            continue
        inline = part.get("inlineData") or part.get("inline_data")
        if isinstance(inline, dict) and inline.get("data"):
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": str(
                            inline.get("mimeType")
                            or inline.get("mime_type")
                            or "application/octet-stream"
                        ),
                        "data": str(inline["data"]),
                    },
                }
            )
            continue
        call = part.get("functionCall") or part.get("function_call")
        if isinstance(call, dict):
            blocks.append(
                {
                    "type": "tool_use",
                    "id": str(call.get("id") or f"tool_{index}"),
                    "name": str(call.get("name") or "tool"),
                    "input": call.get("args") if isinstance(call.get("args"), dict) else {},
                }
            )
            continue
        result = part.get("functionResponse") or part.get("function_response")
        if isinstance(result, dict):
            blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": str(result.get("id") or result.get("name") or f"tool_{index}"),
                    "content": json.dumps(result.get("response", {}), ensure_ascii=False),
                }
            )
    return blocks


def _merge_message(
    messages: List[Dict[str, Any]], role: str, content: List[Dict[str, Any]]
) -> None:
    if not content:
        return
    if messages and messages[-1]["role"] == role:
        messages[-1]["content"].extend(content)
    else:
        messages.append({"role": role, "content": content})


def gemini_request_to_anthropic(
    payload: Dict[str, Any], model: str, streaming: bool
) -> Dict[str, Any]:
    messages: List[Dict[str, Any]] = []
    for item in payload.get("contents") or []:
        if not isinstance(item, dict):
            continue
        role = "assistant" if item.get("role") == "model" else "user"
        _merge_message(messages, role, _anthropic_content(item.get("parts") or []))
    request: Dict[str, Any] = {
        "model": model,
        "messages": messages or [{"role": "user", "content": [{"type": "text", "text": ""}]}],
        "max_tokens": 4096,
        "stream": bool(streaming),
    }
    system = _text_parts((payload.get("systemInstruction") or {}).get("parts") or [])
    if system:
        request["system"] = system
    config = payload.get("generationConfig") or {}
    mapping = {
        "maxOutputTokens": "max_tokens",
        "temperature": "temperature",
        "topP": "top_p",
        "topK": "top_k",
        "stopSequences": "stop_sequences",
    }
    for source, target in mapping.items():
        if config.get(source) is not None:
            request[target] = config[source]
    if config.get("responseMimeType") == "application/json" and isinstance(
        config.get("responseSchema"), dict
    ):
        request["output_config"] = {
            "format": {
                "type": "json_schema",
                "schema": config["responseSchema"],
            }
        }
    tools: List[Dict[str, Any]] = []
    for group in payload.get("tools") or []:
        if not isinstance(group, dict):
            continue
        for declaration in group.get("functionDeclarations") or []:
            if not isinstance(declaration, dict) or not declaration.get("name"):
                continue
            tool = {
                "name": str(declaration["name"]),
                "input_schema": declaration.get("parametersJsonSchema")
                or declaration.get("parameters")
                or {"type": "object", "properties": {}},
            }
            if declaration.get("description"):
                tool["description"] = str(declaration["description"])
            tools.append(tool)
    if tools:
        request["tools"] = tools
    return request


def _finish_reason(value: Any) -> str:
    return {
        "end_turn": "STOP",
        "stop_sequence": "STOP",
        "max_tokens": "MAX_TOKENS",
        "tool_use": "STOP",
    }.get(str(value or ""), "STOP")


def anthropic_response_to_gemini(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("content"), list):
        raise AnthropicError("Anthropic returned an invalid message response.", 502)
    parts: List[Dict[str, Any]] = []
    for block in payload["content"]:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append({"text": str(block.get("text") or "")})
        elif block.get("type") == "thinking":
            parts.append({"text": str(block.get("thinking") or ""), "thought": True})
        elif block.get("type") == "tool_use":
            parts.append(
                {
                    "functionCall": {
                        "id": str(block.get("id") or ""),
                        "name": str(block.get("name") or "tool"),
                        "args": block.get("input") if isinstance(block.get("input"), dict) else {},
                    }
                }
            )
    usage = payload.get("usage") or {}
    uncached_input_tokens = int(usage.get("input_tokens") or 0)
    cached_tokens = int(usage.get("cache_read_input_tokens") or 0)
    cache_creation_tokens = int(usage.get("cache_creation_input_tokens") or 0)
    input_tokens = uncached_input_tokens + cached_tokens + cache_creation_tokens
    output_tokens = int(usage.get("output_tokens") or 0)
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": parts or [{"text": ""}]},
                "finishReason": _finish_reason(payload.get("stop_reason")),
                "index": 0,
            }
        ],
        "usageMetadata": {
            "promptTokenCount": input_tokens,
            "candidatesTokenCount": output_tokens,
            "totalTokenCount": input_tokens + output_tokens,
            "cachedContentTokenCount": cached_tokens,
            "cacheCreationTokenCount": cache_creation_tokens,
        },
        "modelVersion": str(payload.get("model") or ""),
    }


def anthropic_stream_line_to_gemini(line: Any, stream_id: str = "default") -> str:
    text = line.decode("utf-8", errors="ignore") if isinstance(line, bytes) else str(line or "")
    stripped = text.strip()
    if not stripped or stripped.startswith("event:") or stripped.startswith(":"):
        return ""
    if stripped.startswith("data:"):
        stripped = stripped[5:].strip()
    try:
        event = json.loads(stripped)
    except json.JSONDecodeError:
        return ""
    event_type = str(event.get("type") or "")
    delta = event.get("delta") or {}
    parts: List[Dict[str, Any]] = []
    usage: Dict[str, int] = {}
    if event_type == "content_block_delta":
        if delta.get("type") == "text_delta":
            parts.append({"text": str(delta.get("text") or "")})
        elif delta.get("type") == "thinking_delta":
            parts.append({"text": str(delta.get("thinking") or ""), "thought": True})
        elif delta.get("type") == "input_json_delta":
            index = int(event.get("index") or 0)
            state = _stream_tool_blocks.setdefault(stream_id, {}).setdefault(index, {})
            state["json"] = str(state.get("json") or "") + str(delta.get("partial_json") or "")
    elif event_type == "content_block_start":
        block = event.get("content_block") or {}
        if block.get("type") == "tool_use":
            index = int(event.get("index") or 0)
            _stream_tool_blocks.setdefault(stream_id, {})[index] = {
                "id": str(block.get("id") or ""),
                "name": str(block.get("name") or "tool"),
                "json": json.dumps(block.get("input") or {}),
            }
    elif event_type == "content_block_stop":
        index = int(event.get("index") or 0)
        block = _stream_tool_blocks.get(stream_id, {}).pop(index, None)
        if block:
            try:
                arguments = json.loads(str(block.get("json") or "{}"))
            except json.JSONDecodeError:
                arguments = {}
            parts.append(
                {
                    "functionCall": {
                        "id": block.get("id", ""),
                        "name": block.get("name", "tool"),
                        "args": arguments,
                    }
                }
            )
    elif event_type == "message_start":
        message_usage = (event.get("message") or {}).get("usage") or {}
        uncached_input_tokens = int(message_usage.get("input_tokens") or 0)
        cached_tokens = int(message_usage.get("cache_read_input_tokens") or 0)
        cache_creation_tokens = int(message_usage.get("cache_creation_input_tokens") or 0)
        input_tokens = uncached_input_tokens + cached_tokens + cache_creation_tokens
        usage.update(
            {
                "promptTokenCount": input_tokens,
                "cachedContentTokenCount": cached_tokens,
                "cacheCreationTokenCount": cache_creation_tokens,
                "totalTokenCount": input_tokens,
            }
        )
    elif event_type == "message_delta":
        output_tokens = int((event.get("usage") or {}).get("output_tokens") or 0)
        if output_tokens:
            usage["candidatesTokenCount"] = output_tokens
            usage["totalTokenCount"] = output_tokens
    elif event_type in {"message_stop", "error"}:
        if event_type == "error":
            error = event.get("error") or {}
            raise AnthropicError(str(error.get("message") or "Anthropic stream failed."), 502)
        _stream_tool_blocks.pop(stream_id, None)
    if not parts and not usage and event_type != "message_delta":
        return ""
    candidate: Dict[str, Any] = {"content": {"role": "model", "parts": parts}, "index": 0}
    if event_type == "message_delta":
        candidate["finishReason"] = _finish_reason(delta.get("stop_reason"))
    result: Dict[str, Any] = {"candidates": [candidate]}
    if usage:
        result["usageMetadata"] = usage
    return f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
