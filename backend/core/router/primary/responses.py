"""OpenAI Responses API compatibility built on the chat translation layer."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, List

from core.httpx_client import MAX_STREAM_LINE_BYTES, UpstreamStreamProtocolError
from core.models import (
    OpenAIChatCompletionRequest,
    OpenAIResponsesRequest,
    model_to_dict,
)
from core.request_trace_service import trace_decision
from core.router.primary.openai import chat_completions
from core.router.stream_passthrough import ManagedStreamingResponse, close_async_iterator
from core.utils import authenticate_bearer
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter()
_MAX_SSE_FRAME_BYTES = MAX_STREAM_LINE_BYTES
_MAX_RESPONSES_OUTPUT_BYTES = 8 * MAX_STREAM_LINE_BYTES


def _content_to_chat(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")

    converted = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type in {"input_text", "output_text", "text"}:
            converted.append({"type": "text", "text": str(part.get("text") or "")})
        elif part_type == "input_image" and part.get("image_url"):
            converted.append(
                {
                    "type": "image_url",
                    "image_url": {"url": str(part["image_url"])},
                }
            )
    return converted


def responses_to_chat_request(request: OpenAIResponsesRequest) -> OpenAIChatCompletionRequest:
    messages: List[Dict[str, Any]] = []
    if request.instructions:
        messages.append({"role": "system", "content": request.instructions})

    if isinstance(request.input, str):
        messages.append({"role": "user", "content": request.input})
    else:
        for item in request.input:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "function_call_output":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(item.get("call_id") or ""),
                        "content": str(item.get("output") or ""),
                    }
                )
                continue
            if item_type == "function_call":
                call_id = str(item.get("call_id") or item.get("id") or "")
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": str(item.get("name") or ""),
                                    "arguments": str(item.get("arguments") or "{}"),
                                },
                            }
                        ],
                    }
                )
                continue
            role = str(item.get("role") or "user")
            if role not in {"user", "assistant", "system", "developer"}:
                continue
            messages.append(
                {
                    "role": "system" if role == "developer" else role,
                    "content": _content_to_chat(item.get("content", "")),
                }
            )

    if not messages:
        raise HTTPException(status_code=400, detail="The input must contain at least one message.")

    tools = []
    for tool in request.tools or []:
        if tool.get("type") != "function":
            raise HTTPException(
                status_code=400,
                detail="Only function tools are supported by this provider route.",
            )
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.get("name"),
                    "description": tool.get("description"),
                    "parameters": tool.get("parameters") or {},
                },
            }
        )

    tool_choice = request.tool_choice
    if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
        tool_choice = {
            "type": "function",
            "function": {"name": str(tool_choice.get("name") or "")},
        }

    response_format = None
    if request.text:
        output_format = request.text["format"]
        format_type = output_format["type"]
        if format_type == "json_schema":
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    key: output_format[key]
                    for key in ("name", "description", "schema", "strict")
                    if key in output_format
                },
            }
        else:
            response_format = {"type": format_type}

    payload: Dict[str, Any] = {
        "model": request.model,
        "messages": messages,
        "stream": request.stream,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_tokens": request.max_output_tokens,
        "tools": tools or None,
        "tool_choice": tool_choice,
        "response_format": response_format,
    }
    return OpenAIChatCompletionRequest(**payload)


def _response_usage(chat_usage: Dict[str, Any]) -> Dict[str, Any]:
    input_tokens = int(chat_usage.get("prompt_tokens") or 0)
    output_tokens = int(chat_usage.get("completion_tokens") or 0)
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {
            "cached_tokens": int(
                chat_usage.get("prompt_tokens_details", {}).get("cached_tokens") or 0
            )
        },
        "output_tokens": output_tokens,
        "output_tokens_details": {
            "reasoning_tokens": int(
                chat_usage.get("completion_tokens_details", {}).get("reasoning_tokens") or 0
            )
        },
        "total_tokens": int(chat_usage.get("total_tokens") or input_tokens + output_tokens),
    }


def _base_response(
    request: OpenAIResponsesRequest,
    *,
    response_id: str,
    created_at: int,
    status: str,
    output: List[Dict[str, Any]],
    usage: Dict[str, Any] | None,
) -> Dict[str, Any]:
    return {
        "id": response_id,
        "object": "response",
        "created_at": created_at,
        "completed_at": created_at if status == "completed" else None,
        "status": status,
        "error": None,
        "incomplete_details": None,
        "instructions": request.instructions,
        "max_output_tokens": request.max_output_tokens,
        "model": request.model,
        "output": output,
        "parallel_tool_calls": request.parallel_tool_calls,
        "previous_response_id": None,
        "reasoning": request.reasoning,
        "store": request.store,
        "temperature": request.temperature,
        "text": request.text or {"format": {"type": "text"}},
        "tool_choice": request.tool_choice or "auto",
        "tools": request.tools or [],
        "top_p": request.top_p,
        "truncation": "disabled",
        "usage": usage,
        "metadata": request.metadata or {},
    }


def chat_to_responses_response(
    chat: Dict[str, Any], request: OpenAIResponsesRequest
) -> Dict[str, Any]:
    created_at = int(chat.get("created") or time.time())
    response_id = str(chat.get("id") or f"resp_{uuid.uuid4().hex}").replace("chatcmpl-", "resp_")
    choices = chat.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    finish_reason = choices[0].get("finish_reason") if choices else None
    incomplete_reason = {
        "length": "max_output_tokens",
        "content_filter": "content_filter",
    }.get(finish_reason)
    status = "incomplete" if incomplete_reason else "completed"
    output: List[Dict[str, Any]] = []
    reasoning_content = message.get("reasoning_content")
    if reasoning_content:
        output.append(
            {
                "id": f"rs_{uuid.uuid4().hex}",
                "type": "reasoning",
                "status": "completed",
                "summary": [
                    {
                        "type": "summary_text",
                        "text": str(reasoning_content),
                    }
                ],
            }
        )
    content = message.get("content")
    if content is not None:
        output.append(
            {
                "id": f"msg_{uuid.uuid4().hex}",
                "type": "message",
                "status": status,
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": str(content),
                        "annotations": [],
                    }
                ],
            }
        )
    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") or {}
        output.append(
            {
                "id": str(tool_call.get("id") or f"fc_{uuid.uuid4().hex}"),
                "call_id": str(tool_call.get("id") or f"call_{uuid.uuid4().hex}"),
                "type": "function_call",
                "name": str(function.get("name") or ""),
                "arguments": str(function.get("arguments") or "{}"),
                "status": "completed",
            }
        )

    response = _base_response(
        request,
        response_id=response_id,
        created_at=created_at,
        status=status,
        output=output,
        usage=_response_usage(chat.get("usage") or {}),
    )
    if incomplete_reason:
        response["incomplete_details"] = {"reason": incomplete_reason}
    return response


def _sse(event_type: str, data: Dict[str, Any]) -> bytes:
    return f"event: {event_type}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n".encode()


async def _iter_chat_events(
    body: AsyncIterator[Any],
) -> AsyncIterator[Dict[str, Any] | None]:
    buffer = bytearray()
    terminal_received = False
    try:
        async for chunk in body:
            raw = chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8")
            buffer.extend(raw)
            while True:
                lf_index = buffer.find(b"\n\n")
                crlf_index = buffer.find(b"\r\n\r\n")
                candidates = [index for index in (lf_index, crlf_index) if index >= 0]
                if not candidates:
                    break
                frame_end = min(candidates)
                delimiter_size = 4 if frame_end == crlf_index else 2
                if frame_end > _MAX_SSE_FRAME_BYTES:
                    raise UpstreamStreamProtocolError(
                        f"OpenAI SSE frame exceeds {_MAX_SSE_FRAME_BYTES} bytes"
                    )
                frame = bytes(buffer[:frame_end])
                del buffer[: frame_end + delimiter_size]
                heartbeat = False
                for line in frame.splitlines():
                    if line.startswith(b":"):
                        heartbeat = True
                        continue
                    if not line.startswith(b"data:"):
                        continue
                    value = line[5:].strip()
                    if value == b"[DONE]":
                        terminal_received = True
                    elif value:
                        yield json.loads(value.decode("utf-8", errors="replace"))
                if heartbeat:
                    yield None
            if len(buffer) > _MAX_SSE_FRAME_BYTES:
                raise UpstreamStreamProtocolError(
                    f"OpenAI SSE frame exceeds {_MAX_SSE_FRAME_BYTES} bytes"
                )
        if buffer.strip() or not terminal_received:
            raise UpstreamStreamProtocolError("OpenAI chat stream ended before its terminal event")
    finally:
        await close_async_iterator(body)


async def _responses_stream(
    chat_response: StreamingResponse,
    request: OpenAIResponsesRequest,
) -> AsyncIterator[bytes]:
    created_at = int(time.time())
    response_id = f"resp_{uuid.uuid4().hex}"
    message_id = f"msg_{uuid.uuid4().hex}"
    output_text = ""
    output_bytes = 0
    output_item = {
        "id": message_id,
        "type": "message",
        "status": "in_progress",
        "role": "assistant",
        "content": [],
    }
    sequence = 0

    def event(event_type: str, **payload: Any) -> bytes:
        nonlocal sequence
        sequence += 1
        return _sse(event_type, {"type": event_type, "sequence_number": sequence, **payload})

    initial = _base_response(
        request,
        response_id=response_id,
        created_at=created_at,
        status="in_progress",
        output=[],
        usage=None,
    )
    yield event("response.created", response=initial)
    yield event("response.output_item.added", output_index=0, item=output_item)
    yield event(
        "response.content_part.added",
        item_id=message_id,
        output_index=0,
        content_index=0,
        part={"type": "output_text", "text": "", "annotations": []},
    )

    chat_body = chat_response.body_iterator
    try:
        async for chat_event in _iter_chat_events(chat_body):
            if chat_event is None:
                yield b": keep-alive\n\n"
                continue
            if chat_event.get("error"):
                error = chat_event["error"]
                yield event(
                    "error",
                    code=str(error.get("code") or "upstream_error"),
                    message=str(error.get("message") or "The upstream request failed."),
                    param=None,
                )
                return
            choices = chat_event.get("choices") or []
            delta = choices[0].get("delta", {}) if choices else {}
            text = delta.get("content")
            if text:
                text = str(text)
                text_bytes = len(text.encode("utf-8"))
                if output_bytes + text_bytes > _MAX_RESPONSES_OUTPUT_BYTES:
                    trace_decision(
                        category="upstream",
                        action="failed",
                        result="failed",
                        reason="provider_error",
                        provider="responses_adapter",
                        model=request.model,
                        status_code=502,
                    )
                    yield event(
                        "error",
                        code="response_output_limit",
                        message="The streaming response exceeded the supported output limit.",
                        param=None,
                    )
                    return
                output_text += text
                output_bytes += text_bytes
                yield event(
                    "response.output_text.delta",
                    item_id=message_id,
                    output_index=0,
                    content_index=0,
                    delta=text,
                    logprobs=[],
                )
    except UpstreamStreamProtocolError:
        trace_decision(
            category="upstream",
            action="failed",
            result="failed",
            reason="provider_error",
            provider="responses_adapter",
            model=request.model,
            status_code=502,
        )
        yield event(
            "error",
            code="upstream_stream_incomplete",
            message="The upstream streaming response ended unexpectedly.",
            param=None,
        )
        return
    finally:
        await close_async_iterator(chat_body)

    content_part = {"type": "output_text", "text": output_text, "annotations": []}
    output_item = {**output_item, "status": "completed", "content": [content_part]}
    yield event(
        "response.output_text.done",
        item_id=message_id,
        output_index=0,
        content_index=0,
        text=output_text,
        logprobs=[],
    )
    yield event(
        "response.content_part.done",
        item_id=message_id,
        output_index=0,
        content_index=0,
        part=content_part,
    )
    yield event("response.output_item.done", output_index=0, item=output_item)
    completed = _base_response(
        request,
        response_id=response_id,
        created_at=created_at,
        status="completed",
        output=[output_item],
        usage=_response_usage({}),
    )
    yield event("response.completed", response=completed)


@router.post("/v1/responses")
async def create_response(
    request: OpenAIResponsesRequest,
    token: str = Depends(authenticate_bearer),
):
    """Create a response using the existing provider translation pipeline."""
    raw_request = model_to_dict(request)
    if raw_request.get("store"):
        raise HTTPException(
            status_code=400,
            detail="Stored responses are not supported. Send store=false or omit it.",
        )
    if raw_request.get("previous_response_id") or raw_request.get("conversation"):
        raise HTTPException(
            status_code=400,
            detail="Server-managed response history is not supported. Send the conversation in input.",
        )
    if request.stream and request.tools:
        raise HTTPException(
            status_code=400,
            detail="Streaming function calls are not supported. Use stream=false for tool requests.",
        )

    chat_request = responses_to_chat_request(request)
    chat_response = await chat_completions(chat_request, token)
    if request.stream:
        if not isinstance(chat_response, StreamingResponse):
            return chat_response
        return ManagedStreamingResponse(
            _responses_stream(chat_response, request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if not isinstance(chat_response, JSONResponse):
        raise HTTPException(status_code=502, detail="The upstream response was invalid.")
    payload = json.loads(chat_response.body)
    if chat_response.status_code >= 400:
        return JSONResponse(payload, status_code=chat_response.status_code)
    return JSONResponse(chat_to_responses_response(payload, request))
