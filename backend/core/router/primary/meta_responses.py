"""Meta native Responses replay through Polaris authorization and quality routing."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from core.httpx_client import MAX_STREAM_LINE_BYTES, UpstreamStreamProtocolError
from core.meta_responses_models import MetaResponsesRequest
from core.model_pool import ModelPoolError, resolve_model_request
from core.router.protocol_errors import protocol_error_payload
from core.router.stream_passthrough import (
    ManagedStreamingResponse,
    close_async_iterator,
    prepend_async_item,
)
from fastapi import Response
from fastapi.responses import JSONResponse

_MAX_FRAME_BYTES = 8 * MAX_STREAM_LINE_BYTES
_PUBLIC_FAILURE = "The Meta response could not be completed."


async def native_request_to_gemini(request: MetaResponsesRequest) -> dict:
    """Mirror inspectable history for policy/accounting; never decode opaque reasoning."""
    from core.converter.openai_to_gemini import convert_tool_choice_to_tool_config

    contents, system = [], []
    if request.instructions:
        system.append({"text": request.instructions})
    calls = {}
    items = (
        [{"role": "user", "content": request.input}]
        if isinstance(request.input, str)
        else request.input
    )
    for item in items:
        kind = item.get("type", "message")
        if kind == "reasoning":
            summary = "\n".join(part["text"] for part in item["summary"])
            if summary:
                contents.append({"role": "model", "parts": [{"text": summary, "thought": True}]})
        elif kind == "function_call":
            calls[item["call_id"]] = item["name"]
            contents.append(
                {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "id": item["call_id"],
                                "name": item["name"],
                                "args": json.loads(item["arguments"]),
                            }
                        }
                    ],
                }
            )
        elif kind == "function_call_output":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "id": item["call_id"],
                                "name": calls[item["call_id"]],
                                "response": {"result": item["output"]},
                            }
                        }
                    ],
                }
            )
        else:
            content = item["content"]
            parts = [{"text": content}] if isinstance(content, str) else []
            if isinstance(content, list):
                for part in content:
                    if part["type"] != "input_image":
                        parts.append({"text": part["text"]})
                    elif part["image_url"].startswith("data:"):
                        header, data = part["image_url"].split(",", 1)
                        parts.append(
                            {"inlineData": {"mimeType": header[5:].split(";", 1)[0], "data": data}}
                        )
                    else:
                        parts.append(
                            {"fileData": {"mimeType": "image/*", "fileUri": part["image_url"]}}
                        )
            if item["role"] in {"system", "developer"}:
                system.extend(parts)
            else:
                contents.append(
                    {"role": "model" if item["role"] == "assistant" else "user", "parts": parts}
                )
    mirror = {"contents": contents, "generationConfig": {}}
    if system:
        mirror["systemInstruction"] = {"parts": system}
    for name, target in (
        ("temperature", "temperature"),
        ("top_p", "topP"),
        ("max_output_tokens", "maxOutputTokens"),
    ):
        value = getattr(request, name)
        if value is not None:
            mirror["generationConfig"][target] = value
    if request.tools:
        mirror["tools"] = [
            {
                "functionDeclarations": [
                    {
                        key: value
                        for key, value in tool.items()
                        if key in {"name", "description", "parameters"}
                    }
                    for tool in request.tools
                ]
            }
        ]
    if request.tool_choice:
        choice = request.tool_choice
        mirror["toolConfig"] = convert_tool_choice_to_tool_config(
            {"type": "function", "function": {"name": choice["name"]}}
            if isinstance(choice, dict)
            else choice
        )
    return mirror


def _failure(status: int = 502) -> JSONResponse:
    return JSONResponse(
        protocol_error_payload("openai", status, _PUBLIC_FAILURE), status_code=status
    )


def _checked_event(payload: Any, response_model: str) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("_polaris_meta_event"), dict):
        raise UpstreamStreamProtocolError("Missing native Responses event.")
    event = payload["_polaris_meta_event"]
    kind = event.get("type")
    if (
        not isinstance(kind, str)
        or not kind.startswith("response.")
        or "\n" in kind
        or "\r" in kind
    ):
        raise UpstreamStreamProtocolError("Invalid native Responses event.")
    if kind in {"response.failed", "response.error"} or event.get("error"):
        raise UpstreamStreamProtocolError("Native Responses failure.")
    event = dict(event)
    if "response" in event:
        response = event["response"]
        if not isinstance(response, dict) or response.get("error"):
            raise UpstreamStreamProtocolError("Invalid native response.")
        event["response"] = {**response, "model": response_model}
    if kind in {"response.completed", "response.incomplete"} and not isinstance(
        event.get("response"), dict
    ):
        raise UpstreamStreamProtocolError("Missing terminal response.")
    return event


async def _native_events(body: AsyncIterator, response_model: str):
    buffer = bytearray()
    terminal = None
    try:
        async for chunk in body:
            if isinstance(chunk, Response):
                yield _failure(chunk.status_code if chunk.status_code >= 400 else 502)
                return
            if not isinstance(chunk, (bytes, str)):
                raise UpstreamStreamProtocolError("Invalid canonical stream.")
            raw = chunk if isinstance(chunk, bytes) else chunk.encode()
            if len(raw) > _MAX_FRAME_BYTES:
                raise UpstreamStreamProtocolError("Native response frame is too large.")
            buffer.extend(raw)
            while True:
                lf, crlf = buffer.find(b"\n\n"), buffer.find(b"\r\n\r\n")
                ends = [index for index in (lf, crlf) if index >= 0]
                if not ends:
                    break
                end = min(ends)
                if end > _MAX_FRAME_BYTES:
                    raise UpstreamStreamProtocolError("Native response frame is too large.")
                frame = bytes(buffer[:end])
                del buffer[: end + (4 if end == crlf else 2)]
                lines = [
                    line[5:].strip() for line in frame.splitlines() if line.startswith(b"data:")
                ]
                if not lines:
                    continue
                if b"\n".join(lines) == b"[DONE]":
                    if terminal is None:
                        raise UpstreamStreamProtocolError(
                            "Stream ended without native terminal response."
                        )
                    continue
                if terminal is not None:
                    raise UpstreamStreamProtocolError("Unexpected event after terminal response.")
                event = _checked_event(json.loads(b"\n".join(lines)), response_model)
                if event["type"] in {"response.completed", "response.incomplete"}:
                    terminal = event
                else:
                    yield event
            if len(buffer) > _MAX_FRAME_BYTES:
                raise UpstreamStreamProtocolError("Native response frame is too large.")
        if buffer.strip() or terminal is None:
            raise UpstreamStreamProtocolError("Native response ended unexpectedly.")
        # Exhaust the managed pipeline before returning success: its accounting
        # finalization runs after the provider's final yield, not only in aclose().
        yield terminal
    except (UpstreamStreamProtocolError, ValueError, TypeError, UnicodeError):
        yield _failure()
    finally:
        await close_async_iterator(body)


async def _encode_events(events):
    try:
        async for event in events:
            if isinstance(event, Response):
                error = {
                    "type": "error",
                    "code": "upstream_stream_error",
                    "message": _PUBLIC_FAILURE,
                }
                yield ("event: error\ndata: " + json.dumps(error) + "\n\n").encode()
                return
            yield (
                "event: "
                + event["type"]
                + "\ndata: "
                + json.dumps(event, separators=(",", ":"))
                + "\n\n"
            ).encode()
    finally:
        await close_async_iterator(events)


async def create_meta_response(request: MetaResponsesRequest, token: str, *, resolution=None):
    """Called only by the authenticated Responses route after selecting Meta."""
    from core.api.primary import stream_request
    from core.meta_model_api import MetaModelAPIError, protocol_for_model
    from core.meta_native_boundary import seal_native_request

    if resolution is None:
        try:
            resolution = await resolve_model_request(request.model)
        except ModelPoolError:
            return _failure(503)
    candidates = list(resolution.candidates)
    if not candidates:
        return _failure(503)
    try:
        for candidate in candidates:
            protocol_for_model({}, candidate)
            if (
                request.reasoning
                and request.reasoning.get("effort") == "max"
                and candidate != "muse-spark-1.3"
            ):
                return _failure(400)
    except MetaModelAPIError:
        return _failure(400)
    mirror = await native_request_to_gemini(request)
    native = request.model_dump(exclude_none=True)
    native["model"] = candidates[0]
    mirror = seal_native_request(mirror, native)
    events = _native_events(
        stream_request(
            body={"model": candidates[0], "request": mirror},
            native=False,
            model_candidates=candidates,
            model_routing=resolution.is_virtual,
        ),
        resolution.response_model,
    )
    if not request.stream:
        try:
            async for event in events:
                if isinstance(event, Response):
                    return event
                if event["type"] in {"response.completed", "response.incomplete"}:
                    return JSONResponse(event["response"])
            return _failure()
        finally:
            await close_async_iterator(events)
    first = await anext(events)
    if isinstance(first, Response):
        await close_async_iterator(events)
        return first
    return ManagedStreamingResponse(
        _encode_events(prepend_async_item(first, events)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
