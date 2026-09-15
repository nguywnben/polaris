"""Kiro API-key transport at the gateway's canonical Gemini boundary.

API-key usage: https://kiro.dev/docs/getting-started/authentication/
Direct HTTP protocol facts were checked against the read-only OmniRoute 3.8.49
Kiro implementation; this is not an officially documented public HTTP API.
No vendor CLI, cached desktop credentials, or synthetic model IDs are used.
"""

from __future__ import annotations

import base64
import json
import re
import struct
import uuid
import zlib
from collections.abc import AsyncIterator
from typing import Any

import httpx
from core.httpx_client import http_client

REGIONS = frozenset({"us-east-1", "eu-central-1"})
MAX_FRAME_BYTES = 1024 * 1024
MAX_HEADER_BYTES = 16 * 1024
MAX_STREAM_BYTES = 64 * 1024 * 1024
MAX_TOOL_BYTES = 1024 * 1024
MAX_CATALOG_BYTES = 2 * 1024 * 1024


class KiroError(ValueError):
    """A safe transport error; never includes upstream bodies or credentials."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def normalize_credential(data: dict) -> dict:
    if not isinstance(data, dict):
        raise KiroError("Enter a valid Kiro credential.")
    key = data.get("api_key")
    key = key.strip() if isinstance(key, str) else ""
    if not 8 <= len(key) <= 4096 or not all(33 <= ord(char) <= 126 for char in key):
        raise KiroError("Enter a valid Kiro API key.")
    region = data.get("region") or "us-east-1"
    if not isinstance(region, str) or region not in REGIONS:
        raise KiroError("Kiro runtime region must be us-east-1 or eu-central-1.")
    result = {"provider": "kiro", "credential_type": "api_key", "api_key": key, "region": region}
    arn = data.get("profile_arn") or ""
    if arn:
        if not isinstance(arn, str) or not re.fullmatch(
            rf"arn:aws:codewhisperer:{region}:\d{{12}}:profile/[A-Za-z0-9_-]{{1,128}}", arn
        ):
            raise KiroError("Kiro profile ARN must match the selected runtime region.")
        result["profile_arn"] = arn
    return result


def _headers(data: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {data['api_key']}",
        "tokentype": "API_KEY",
        "Content-Type": "application/json",
        "Accept": "application/vnd.amazon.eventstream",
    }


def _host(region: str) -> str:
    return (
        "https://codewhisperer.us-east-1.amazonaws.com"
        if region == "us-east-1"
        else f"https://q.{region}.amazonaws.com"
    )


async def discover_models(data: dict) -> list[str]:
    """Read the key's actual catalog; never spend on inference or invent models."""
    credential = normalize_credential(data)
    url = f"https://q.{credential['region']}.amazonaws.com/ListAvailableModels"
    params = {"origin": "AI_EDITOR"}
    if credential.get("profile_arn"):
        params["profileArn"] = credential["profile_arn"]
    headers = {**_headers(credential), "Accept": "application/json"}
    model_ids: list[str] = []
    seen_pages: set[str] = set()
    try:
        async with http_client.get_client(
            timeout=30.0, destination_url=url, follow_redirects=False
        ) as client:
            for _ in range(10):
                async with client.stream("GET", url, params=params, headers=headers) as response:
                    if response.status_code != 200:
                        status = (
                            response.status_code if response.status_code in {401, 403, 429} else 502
                        )
                        raise KiroError(
                            "Kiro model discovery failed. Check the API key, permissions, and connection.",
                            status,
                        )
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > MAX_CATALOG_BYTES:
                            raise KiroError("Kiro model catalog exceeded the size limit.", 502)
                        body.extend(chunk)
                    payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise KiroError("Kiro returned an invalid model catalog.", 502)
                models = payload.get("models", payload.get("availableModels"))
                if not isinstance(models, list) or len(models) > 500:
                    raise KiroError("Kiro returned an invalid model catalog.", 502)
                for item in models:
                    model = item.get("modelId", item.get("id")) if isinstance(item, dict) else None
                    if (
                        not isinstance(model, str)
                        or not model
                        or len(model) > 256
                        or not model.isprintable()
                        or model != model.strip()
                    ):
                        raise KiroError("Kiro returned an invalid model ID.", 502)
                    if model not in model_ids:
                        model_ids.append(model)
                    if len(model_ids) > 500:
                        raise KiroError("Kiro model catalog exceeded the model limit.", 502)
                token = payload.get("nextToken")
                if not token:
                    return model_ids
                if not isinstance(token, str) or len(token) > 4096 or token in seen_pages:
                    raise KiroError("Kiro returned invalid catalog pagination.", 502)
                seen_pages.add(token)
                params["nextToken"] = token
    except (httpx.HTTPError, OSError) as exc:
        raise KiroError("Unable to reach Kiro. Check outbound connection settings.", 502) from exc
    except (json.JSONDecodeError, UnicodeError, RecursionError) as exc:
        raise KiroError("Kiro returned an invalid model catalog.", 502) from exc
    raise KiroError("Kiro model catalog exceeded the page limit.", 502)


def _name(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise KiroError("Kiro requires a valid function name.")
    return value


def _text_parts(parts: list) -> str:
    if not isinstance(parts, list) or any(
        not isinstance(part, dict) or set(part) != {"text"} or not isinstance(part["text"], str)
        for part in parts
    ):
        raise KiroError("Kiro system instructions must contain text only.")
    return "\n".join(part["text"] for part in parts)


def _schema(value: Any, depth: int = 0) -> Any:
    if depth > 32:
        raise KiroError("Kiro function schema is too deeply nested.")
    if isinstance(value, dict):
        return {
            key: item.lower()
            if key == "type" and isinstance(item, str)
            else _schema(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_schema(item, depth + 1) for item in value]
    return value


def prepare_request(
    data: dict, gemini_request: dict, model: str, streaming: bool
) -> tuple[str, dict, dict]:
    """Prepare a binary-streaming upstream request, irrespective of client mode."""
    credential = normalize_credential(data)
    try:
        if (
            not isinstance(gemini_request, dict)
            or len(json.dumps(gemini_request, allow_nan=False).encode()) > 16 * 1024 * 1024
        ):
            raise ValueError
    except (ValueError, TypeError, RecursionError) as exc:
        raise KiroError("Kiro requires a bounded valid JSON request.") from exc
    if not isinstance(model, str) or not model or len(model) > 256 or not model.isprintable():
        raise KiroError("Select a valid Kiro model.")
    config = gemini_request.get("generationConfig") or {}
    if not isinstance(config, dict):
        raise KiroError("Kiro requires valid generation settings.")
    if (
        any(
            value is not None
            and key not in {"maxOutputTokens", "temperature", "topP", "candidateCount"}
            for key, value in config.items()
        )
        or config.get("candidateCount", 1) != 1
    ):
        raise KiroError("Kiro does not support the requested generation settings.")
    tool_config = gemini_request.get("toolConfig") or {}
    if not isinstance(tool_config, dict):
        raise KiroError("Kiro requires valid tool settings.")
    mode = tool_config.get("functionCallingConfig") or {}
    if not isinstance(mode, dict):
        raise KiroError("Kiro requires valid tool settings.")
    if mode and (mode.get("mode", "AUTO") != "AUTO" or mode.get("allowedFunctionNames")):
        raise KiroError("Kiro supports automatic tool selection only.")
    tools = []
    for group in gemini_request.get("tools") or []:
        if (
            not isinstance(group, dict)
            or set(group) != {"functionDeclarations"}
            or not isinstance(group["functionDeclarations"], list)
        ):
            raise KiroError("Kiro supports function tools only.")
        for declaration in group["functionDeclarations"]:
            if not isinstance(declaration, dict):
                raise KiroError("Kiro requires valid function declarations.")
            schema = (
                declaration.get("parametersJsonSchema")
                or declaration.get("parameters")
                or {"type": "object", "properties": {}}
            )
            if not isinstance(schema, dict):
                raise KiroError("Kiro function schemas must be objects.")
            tools.append(
                {
                    "toolSpecification": {
                        "name": _name(declaration.get("name")),
                        "description": declaration.get("description") or declaration["name"],
                        "inputSchema": {"json": _schema(schema)},
                    }
                }
            )
    if len(tools) > 128:
        raise KiroError("Kiro request contains too many tools.")
    contents = gemini_request.get("contents") or []
    if not isinstance(contents, list) or not contents or len(contents) > 1000:
        raise KiroError("Kiro requires a bounded conversation ending in a user turn.")
    history = []
    pending: dict[str, str] = {}
    for content in contents:
        if (
            not isinstance(content, dict)
            or content.get("role", "user") not in {"user", "model"}
            or not isinstance(content.get("parts"), list)
        ):
            raise KiroError("Kiro requires valid conversation messages.")
        assistant = content.get("role") == "model"
        entry: dict[str, Any] = {"content": ""}
        if not assistant:
            entry.update(modelId=model, origin="AI_EDITOR")
        text, calls, results, images = [], [], [], []
        for part in content.get("parts") or []:
            if not isinstance(part, dict):
                raise KiroError("Kiro requires valid message parts.")
            if part.get("thought") or "thoughtSignature" in part:
                raise KiroError("Kiro does not support reasoning history in this transport.")
            if "text" in part and isinstance(part["text"], str):
                text.append(part["text"])
            elif isinstance(part.get("functionCall"), dict) and assistant:
                call = part["functionCall"]
                name = _name(call.get("name"))
                call_id = call.get("id") or str(uuid.uuid4())
                if not isinstance(call_id, str) or len(call_id) > 256 or call_id in pending:
                    raise KiroError("Kiro request contains an invalid tool call ID.")
                if not isinstance(call.get("args", {}), dict):
                    raise KiroError("Kiro function arguments must be an object.")
                pending[call_id] = name
                calls.append({"toolUseId": call_id, "name": name, "input": call.get("args", {})})
            elif isinstance(part.get("functionResponse"), dict) and not assistant:
                response = part["functionResponse"]
                name = _name(response.get("name"))
                matches = [key for key, value in pending.items() if value == name]
                call_id = response.get("id") or (matches[0] if len(matches) == 1 else None)
                if call_id not in pending or pending[call_id] != name:
                    raise KiroError("Kiro tool results must match a preceding tool call.")
                del pending[call_id]
                results.append(
                    {
                        "toolUseId": call_id,
                        "status": "success",
                        "content": [
                            {"text": json.dumps(response.get("response", {}), ensure_ascii=False)}
                        ],
                    }
                )
            elif isinstance(part.get("inlineData"), dict) and not assistant:
                image = part["inlineData"]
                format_name = {
                    "image/png": "png",
                    "image/jpeg": "jpeg",
                    "image/webp": "webp",
                    "image/gif": "gif",
                }.get(image.get("mimeType"))
                encoded = image.get("data", "")
                try:
                    if (
                        not format_name
                        or not isinstance(encoded, str)
                        or len(encoded) > 8 * 1024 * 1024
                        or not base64.b64decode(encoded, validate=True)
                    ):
                        raise ValueError
                except ValueError as exc:
                    raise KiroError("Kiro requires a valid inline image.") from exc
                images.append({"format": format_name, "source": {"bytes": encoded}})
            else:
                raise KiroError("Kiro does not support this message content.")
        entry["content"] = "\n".join(text)
        if calls:
            entry["toolUses"] = calls
        if results:
            entry["userInputMessageContext"] = {"toolResults": results}
        if images:
            entry["images"] = images
        kind = "assistantResponseMessage" if assistant else "userInputMessage"
        if history and kind in history[-1]:
            previous = history[-1][kind]
            previous["content"] = "\n".join(filter(None, [previous["content"], entry["content"]]))
            for key in ("toolUses", "images"):
                if key in entry:
                    previous.setdefault(key, []).extend(entry[key])
            if results:
                previous.setdefault("userInputMessageContext", {}).setdefault(
                    "toolResults", []
                ).extend(results)
        else:
            history.append({kind: entry})
    if not history or "userInputMessage" not in history[-1] or pending:
        raise KiroError("Kiro requires a final user turn and completed tool results.")
    instruction = gemini_request.get("systemInstruction") or {}
    if not isinstance(instruction, dict):
        raise KiroError("Kiro system instructions must contain text only.")
    system = _text_parts(instruction.get("parts", []))
    if system:
        first_user = next(
            (entry["userInputMessage"] for entry in history if "userInputMessage" in entry), None
        )
        first_user["content"] = (
            f"<system-reminder>\n{system}\n</system-reminder>\n\n{first_user['content']}"
        )
    current = history.pop()
    if tools:
        current["userInputMessage"].setdefault("userInputMessageContext", {})["tools"] = tools
    payload: dict[str, Any] = {
        "conversationState": {
            "chatTriggerType": "MANUAL",
            "conversationId": str(uuid.uuid4()),
            "currentMessage": current,
            "history": history,
        }
    }
    if credential.get("profile_arn"):
        payload["profileArn"] = credential["profile_arn"]
    inference = {
        target: config[key]
        for key, target in {
            "maxOutputTokens": "maxTokens",
            "temperature": "temperature",
            "topP": "topP",
        }.items()
        if config.get(key) is not None
    }
    if inference:
        payload["inferenceConfig"] = inference
    return f"{_host(credential['region'])}/generateAssistantResponse", _headers(credential), payload


def _parse_frame(frame: bytes, header_size: int) -> tuple[dict, dict]:
    if zlib.crc32(frame[:-4]) != struct.unpack(">I", frame[-4:])[0]:
        raise KiroError("Kiro returned a corrupt event frame.", 502)
    headers = {}
    offset, end = 12, 12 + header_size
    while offset < end:
        name_size = frame[offset]
        offset += 1
        if not name_size or offset + name_size + 1 > end:
            raise KiroError("Kiro returned malformed event headers.", 502)
        name = frame[offset : offset + name_size].decode("utf-8")
        offset += name_size
        kind = frame[offset]
        offset += 1
        if kind in {6, 7}:
            if offset + 2 > end:
                raise KiroError("Kiro returned malformed event headers.", 502)
            size = struct.unpack(">H", frame[offset : offset + 2])[0]
            offset += 2
        else:
            size = {0: 0, 1: 0, 2: 1, 3: 2, 4: 4, 5: 8, 8: 8, 9: 16}.get(kind)
            if size is None:
                raise KiroError("Kiro returned an unsupported event header.", 502)
        if offset + size > end or name in headers:
            raise KiroError("Kiro returned malformed event headers.", 502)
        headers[name] = frame[offset : offset + size].decode("utf-8") if kind == 7 else None
        offset += size
    payload = json.loads(frame[end:-4])
    if not isinstance(payload, dict):
        raise KiroError("Kiro returned an invalid event payload.", 502)
    return headers, payload


async def _events(byte_iterator: AsyncIterator[bytes]) -> AsyncIterator[tuple[dict, dict]]:
    buffer = bytearray()
    received = 0
    async for chunk in byte_iterator:
        if not isinstance(chunk, bytes):
            raise KiroError("Kiro returned an invalid event stream.", 502)
        received += len(chunk)
        if received > MAX_STREAM_BYTES:
            raise KiroError("Kiro response exceeded the stream limit.", 502)
        # Consume one frame at a time even if the caller supplied a large chunk.
        source = memoryview(chunk)
        while source:
            needed = (
                12 - len(buffer)
                if len(buffer) < 12
                else struct.unpack(">I", buffer[:4])[0] - len(buffer)
            )
            take = min(needed, len(source))
            buffer.extend(source[:take])
            source = source[take:]
            if len(buffer) < 12:
                continue
            total, header_size, crc = struct.unpack(">III", buffer[:12])
            if (
                not 16 <= total <= MAX_FRAME_BYTES
                or header_size > MAX_HEADER_BYTES
                or header_size > total - 16
                or zlib.crc32(buffer[:8]) != crc
            ):
                raise KiroError("Kiro returned invalid event framing.", 502)
            if len(buffer) < total:
                continue
            try:
                yield _parse_frame(bytes(buffer), header_size)
            except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
                raise KiroError("Kiro returned an invalid event payload.", 502) from exc
            buffer.clear()
    if buffer:
        raise KiroError("Kiro returned a truncated event stream.", 502)


def _sse(parts: list, *, finish: str | None = None, usage: dict | None = None) -> str:
    candidate = {"index": 0, "content": {"role": "model", "parts": parts}}
    if finish:
        candidate["finishReason"] = finish
    response = {"candidates": [candidate]}
    if usage is not None:
        response["usageMetadata"] = usage
    return f"data: {json.dumps(response, ensure_ascii=False)}\n\n"


async def stream_to_gemini(byte_iterator: AsyncIterator[bytes]) -> AsyncIterator[str]:
    """Decode binary frames; emit success only after an explicit stop and clean EOF.

    Transport/read failures and cancellation propagate to the gateway. Tool calls
    are buffered per stream until their complete JSON arguments can be validated.
    """
    stopped = False
    finish = "STOP"
    usage = None
    calls: dict[str, dict] = {}
    async for headers, raw in _events(byte_iterator):
        message_type = headers.get(":message-type")
        event = headers.get(":event-type")
        if message_type in {"exception", "error"}:
            status = 429 if "throttl" in str(event).lower() else 502
            raise KiroError("Kiro rejected the streaming request.", status)
        if message_type != "event" or not isinstance(event, str):
            raise KiroError("Kiro returned invalid event metadata.", 502)
        payload = raw.get(event, raw)
        if not isinstance(payload, dict):
            raise KiroError("Kiro returned an invalid event payload.", 502)
        if event in {"assistantResponseEvent", "toolUseEvent"} and stopped:
            raise KiroError("Kiro returned content after the final event.", 502)
        if event == "assistantResponseEvent":
            text = payload.get("content", "")
            if not isinstance(text, str):
                raise KiroError("Kiro returned invalid assistant content.", 502)
            if text:
                yield _sse([{"text": text}])
        elif event == "toolUseEvent":
            call_id = payload.get("toolUseId")
            if not isinstance(call_id, str) or not call_id or len(call_id) > 256:
                raise KiroError("Kiro returned an invalid tool call ID.", 502)
            if call_id not in calls and len(calls) >= 128:
                raise KiroError("Kiro returned too many tool calls.", 502)
            call = calls.setdefault(call_id, {"name": "", "input": "", "kind": None, "stop": False})
            if call["stop"]:
                raise KiroError("Kiro returned tool arguments after completion.", 502)
            if payload.get("name"):
                name = _name(payload["name"])
                if call["name"] and call["name"] != name:
                    raise KiroError("Kiro changed a tool name during streaming.", 502)
                call["name"] = name
            if "input" in payload:
                value = payload["input"]
                kind = (
                    "text"
                    if isinstance(value, str)
                    else "object"
                    if isinstance(value, dict)
                    else None
                )
                if kind is None or call["kind"] not in {None, kind}:
                    raise KiroError("Kiro returned invalid tool arguments.", 502)
                call["kind"] = kind
                call["input"] = call["input"] + value if kind == "text" else json.dumps(value)
                if len(call["input"].encode()) > MAX_TOOL_BYTES:
                    raise KiroError("Kiro tool arguments exceeded the size limit.", 502)
            call["stop"] = payload.get("stop") is True
        elif event == "metricsEvent":
            counts = [payload.get("inputTokens"), payload.get("outputTokens")]
            if any(type(value) is not int or not 0 <= value <= 2**53 for value in counts):
                raise KiroError("Kiro returned invalid token usage.", 502)
            usage = {
                "promptTokenCount": counts[0],
                "candidatesTokenCount": counts[1],
                "totalTokenCount": sum(counts),
            }
            if "cacheReadTokens" in payload:
                cached = payload["cacheReadTokens"]
                if type(cached) is not int or not 0 <= cached <= counts[0]:
                    raise KiroError("Kiro returned invalid cached token usage.", 502)
                usage["cachedContentTokenCount"] = cached
        elif event == "messageStopEvent":
            if stopped:
                raise KiroError("Kiro returned duplicate final events.", 502)
            stopped = True
            reason = payload.get("stopReason")
            if reason in {"max_tokens", "maxTokens", "length"}:
                finish = "MAX_TOKENS"
        elif event not in {
            "contextUsageEvent",
            "meteringEvent",
            "assistantResponseEndEvent",
            "citationEvent",
            "codeReferenceEvent",
        }:
            raise KiroError("Kiro returned an unsupported response event.", 502)
    if not stopped:
        raise KiroError("Kiro stream ended without a completion event.", 502)
    parts = []
    for call_id, call in calls.items():
        try:
            arguments = json.loads(call["input"] or "{}")
        except (ValueError, RecursionError) as exc:
            raise KiroError("Kiro returned incomplete tool arguments.", 502) from exc
        if not call["name"] or not isinstance(arguments, dict):
            raise KiroError("Kiro returned invalid tool arguments.", 502)
        parts.append({"functionCall": {"id": call_id, "name": call["name"], "args": arguments}})
    yield _sse(parts, finish=finish, usage=usage)
