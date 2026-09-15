"""Bounded integration boundary for the additional API-key providers.

The production primary pipeline remains responsible for routing, retries, tracing,
quotas and cancellation. This module only adapts provider wire formats.
"""

from __future__ import annotations

import asyncio
import importlib
import json
from contextlib import aclosing

from core.httpx_client import http_client
from core.provider_registry import EXTENDED_PROVIDERS, get_credential_provider
from fastapi import Response


def transport(credential: dict):
    provider = get_credential_provider(credential)
    if provider not in EXTENDED_PROVIDERS:
        raise ValueError("Unsupported provider.")
    module = (
        "meta_model_api"
        if provider == "meta"
        else provider
        if provider in {"kiro", "opencode"}
        else "hosted_providers"
    )
    return importlib.import_module(f"core.{module}")


def normalize_extended_credential(credential: dict) -> dict:
    return transport(credential).normalize_credential(credential)


async def discover_extended_models(credential: dict) -> list[str]:
    try:
        async with asyncio.timeout(30):
            return await transport(credential).discover_models(credential)
    except TimeoutError as exc:
        raise ProviderDiscoveryTimeout("Provider model discovery timed out.") from exc


def prepare_extended_request(credential: dict, request: dict, model: str, streaming: bool):
    config = request.get("generationConfig") or {}
    if not isinstance(config, dict):
        raise ValueError("Provider generation configuration must be an object.")
    count = config.get("candidateCount", 1)
    if type(count) is not int or count != 1:
        raise ValueError("These providers support exactly one response candidate per request.")
    return transport(credential).prepare_request(credential, request, model, streaming)


class ProviderStreamError(ValueError):
    """Safe upstream failure independent of the vendor's secret-bearing message."""

    status_code = 502


class ProviderDiscoveryTimeout(ValueError):
    """Safe, retryable catalog timeout for management endpoints."""

    status_code = 504


def _object_arguments(value):
    try:
        result = json.loads(value or "{}") if isinstance(value, str) else value
    except (ValueError, RecursionError) as exc:
        raise ProviderStreamError("Provider returned invalid function arguments.") from exc
    if not isinstance(result, dict):
        raise ProviderStreamError("Provider returned invalid function arguments.")
    return result


def _count(value):
    if type(value) is not int or not 0 <= value <= 2**53:
        raise ProviderStreamError("Provider returned invalid usage.")
    return value


class _StreamDecoder:
    """Per-request protocol state: no shared tool buffers across credentials."""

    def __init__(self, protocol):
        self.protocol = protocol
        self.tools = {}
        self.usage = {}
        self.output_tokens = None
        self.finish = None
        self.stopped = False

    def tool(self, index, *, name=None, call_id=None, arguments=None, delta=None):
        if not isinstance(index, (int, str)) or isinstance(index, bool):
            raise ProviderStreamError("Provider returned an invalid function index.")
        if index not in self.tools and len(self.tools) >= 128:
            raise ProviderStreamError("Provider returned too many function calls.")
        item = self.tools.setdefault(index, {"name": "", "id": "", "arguments": "", "delta": False})
        for key, value in (("name", name), ("id", call_id)):
            if value is not None:
                if not isinstance(value, str) or len(value) > 256 or not value.isprintable():
                    raise ProviderStreamError("Provider returned invalid function metadata.")
                if item[key] and item[key] != value:
                    raise ProviderStreamError(
                        "Provider changed function metadata during streaming."
                    )
                item[key] = value
        if arguments is not None:
            item["arguments"] = json.dumps(arguments) if isinstance(arguments, dict) else arguments
        if delta is not None:
            if not isinstance(delta, str):
                raise ProviderStreamError("Provider returned invalid function arguments.")
            if not item["delta"] and item["arguments"] in {"", "{}"}:
                item["arguments"] = ""
            item["delta"] = True
            item["arguments"] += delta
        if not isinstance(item["arguments"], str) or len(item["arguments"].encode()) > 1024 * 1024:
            raise ProviderStreamError("Provider function arguments exceeded the limit.")

    def flush_tools(self, indexes=None):
        parts = []
        for index in list(self.tools) if indexes is None else indexes:
            item = self.tools.pop(index, None)
            if item is None:
                continue
            if not item["name"] or not item["id"]:
                raise ProviderStreamError("Provider returned incomplete function metadata.")
            parts.append(
                {
                    "functionCall": {
                        "name": item["name"],
                        "id": item["id"],
                        "args": _object_arguments(item["arguments"]),
                    }
                }
            )
        return parts

    def usage_counts(self, usage, input_key, output_key):
        if not isinstance(usage, dict):
            raise ProviderStreamError("Provider returned invalid usage.")
        for source, target in (
            (input_key, "promptTokenCount"),
            (output_key, "candidatesTokenCount"),
        ):
            if source in usage:
                self.usage[target] = _count(usage[source])
        if output_key in usage:
            self.output_tokens = _count(usage[output_key])
        if self.protocol in {"openai", "responses"}:
            for detail_key, source, target in (
                (f"{input_key}_details", "cached_tokens", "cachedContentTokenCount"),
                (f"{output_key}_details", "reasoning_tokens", "thoughtsTokenCount"),
            ):
                details = usage.get(detail_key)
                if details is not None:
                    if not isinstance(details, dict):
                        raise ProviderStreamError("Provider returned invalid usage details.")
                    if source in details:
                        self.usage[target] = _count(details[source])
            if self.output_tokens is not None:
                # OpenAI output totals include reasoning; Gemini exposes it
                # separately. Recalculate from the cumulative raw total so
                # repeated usage frames cannot subtract reasoning twice.
                self.usage["candidatesTokenCount"] = max(
                    self.output_tokens - self.usage.get("thoughtsTokenCount", 0), 0
                )
        if self.usage:
            self.usage["totalTokenCount"] = self.usage.get("promptTokenCount", 0) + (
                self.output_tokens or 0
            )
            if "total_tokens" in usage:
                self.usage["totalTokenCount"] = _count(usage["total_tokens"])

    def decode(self, event):
        if (
            not isinstance(event, dict)
            or "error" in event
            or event.get("type") in {"error", "response.failed", "response.incomplete"}
        ):
            raise ProviderStreamError("Provider returned a streaming error.")
        if self.stopped:
            usage_only = (
                self.protocol == "openai"
                and not event.get("choices")
                and isinstance(event.get("usage"), dict)
            ) or (
                self.protocol == "gemini"
                and not event.get("candidates")
                and isinstance(event.get("usageMetadata"), dict)
            )
            if not usage_only and event.get("type") != "ping":
                raise ProviderStreamError("Provider returned content after completion.")
        parts = []
        if self.protocol == "openai":
            choices = event.get("choices", [])
            if not isinstance(choices, list) or len(choices) > 1:
                raise ProviderStreamError("Provider returned invalid choices.")
            for choice in choices:
                if not isinstance(choice, dict) or self.stopped:
                    raise ProviderStreamError("Provider returned content after completion.")
                delta = choice.get("delta") or {}
                for key, thought in (
                    ("content", False),
                    ("reasoning_content", True),
                    ("reasoning", True),
                ):
                    if delta.get(key):
                        if not isinstance(delta[key], str):
                            raise ProviderStreamError("Provider returned invalid text content.")
                        parts.append({"text": delta[key], **({"thought": True} if thought else {})})
                for tool in delta.get("tool_calls") or []:
                    function = tool.get("function") or {}
                    self.tool(
                        tool.get("index", 0),
                        name=function.get("name"),
                        call_id=tool.get("id"),
                        delta=function.get("arguments"),
                    )
                reason = choice.get("finish_reason")
                if reason:
                    if reason not in {"stop", "tool_calls", "length", "content_filter"}:
                        raise ProviderStreamError("Provider returned an unknown completion reason.")
                    parts.extend(self.flush_tools())
                    self.finish = {"length": "MAX_TOKENS", "content_filter": "SAFETY"}.get(
                        reason, "STOP"
                    )
                    self.stopped = True
            self.usage_counts(event.get("usage") or {}, "prompt_tokens", "completion_tokens")
        elif self.protocol == "anthropic":
            kind = event.get("type")
            if kind == "message_start":
                usage = (event.get("message") or {}).get("usage") or {}
                self.usage_counts(usage, "input_tokens", "output_tokens")
                if usage:
                    cached = _count(usage.get("cache_read_input_tokens", 0))
                    creation = _count(usage.get("cache_creation_input_tokens", 0))
                    self.usage["cachedContentTokenCount"] = cached
                    self.usage["promptTokenCount"] = (
                        self.usage.get("promptTokenCount", 0) + cached + creation
                    )
                    self.usage_counts({}, "input_tokens", "output_tokens")
            elif kind == "content_block_start":
                block = event.get("content_block") or {}
                if block.get("type") == "tool_use":
                    self.tool(
                        event.get("index", 0),
                        name=block.get("name"),
                        call_id=block.get("id"),
                        arguments=block.get("input", {}),
                    )
            elif kind == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") in {"text_delta", "thinking_delta"}:
                    thought = delta["type"] == "thinking_delta"
                    text = delta.get("thinking" if thought else "text")
                    if not isinstance(text, str):
                        raise ProviderStreamError("Provider returned invalid text content.")
                    parts.append({"text": text, **({"thought": True} if thought else {})})
                elif delta.get("type") == "input_json_delta":
                    self.tool(event.get("index", 0), delta=delta.get("partial_json"))
            elif kind == "content_block_stop":
                parts.extend(self.flush_tools([event.get("index", 0)]))
            elif kind == "message_delta":
                reason = (event.get("delta") or {}).get("stop_reason")
                if reason:
                    self.finish = "MAX_TOKENS" if reason == "max_tokens" else "STOP"
                self.usage_counts(event.get("usage") or {}, "input_tokens", "output_tokens")
            elif kind == "message_stop":
                self.stopped = True
                self.finish = self.finish or "STOP"
        elif self.protocol == "responses":
            kind = event.get("type", "")
            if kind in {
                "response.output_text.delta",
                "response.reasoning_summary_text.delta",
                "response.reasoning_text.delta",
            }:
                text = event.get("delta")
                if not isinstance(text, str):
                    raise ProviderStreamError("Provider returned invalid text content.")
                parts.append({"text": text, **({"thought": True} if "reasoning" in kind else {})})
            elif kind == "response.output_item.done":
                item = event.get("item") or {}
                if item.get("type") == "function_call":
                    self.tool(
                        item.get("id", ""),
                        name=item.get("name"),
                        call_id=item.get("call_id") or item.get("id"),
                        arguments=item.get("arguments", "{}"),
                    )
                    parts.extend(self.flush_tools())
            elif kind in {"response.completed", "response.done"}:
                response = event.get("response") or event
                if response.get("status", "completed") != "completed":
                    raise ProviderStreamError("Provider response did not complete.")
                self.usage_counts(response.get("usage") or {}, "input_tokens", "output_tokens")
                self.stopped, self.finish = True, "STOP"
        elif self.protocol == "gemini":
            event = event.get("response", event)
            for candidate in event.get("candidates") or []:
                parts.extend((candidate.get("content") or {}).get("parts") or [])
                if candidate.get("finishReason"):
                    self.stopped, self.finish = True, candidate["finishReason"]
            for key, value in (event.get("usageMetadata") or {}).items():
                if key.endswith("TokenCount"):
                    self.usage[key] = _count(value)
        else:
            raise ProviderStreamError("Unsupported provider stream protocol.")
        for part in parts:
            if not isinstance(part, dict):
                raise ProviderStreamError("Provider returned invalid content parts.")
            if "functionCall" in part:
                _object_arguments(part["functionCall"].get("args"))
        return self.encode(parts) if parts else None

    def encode(self, parts, terminal=False):
        candidate = {"index": 0, "content": {"role": "model", "parts": parts}}
        if terminal:
            candidate["finishReason"] = self.finish
        payload = {"candidates": [candidate]}
        if self.usage:
            payload["usageMetadata"] = self.usage
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def complete(self):
        if not self.stopped or not self.finish or self.tools:
            raise ProviderStreamError("Provider stream ended before completion.")
        return self.encode([], terminal=True)


async def _stream_lines(response):
    """Bound line memory without httpx's chunk-size buffering of small deltas."""
    buffer = bytearray()
    received = 0
    async for chunk in response.aiter_bytes():
        received += len(chunk)
        if received > 64 * 1024 * 1024:
            raise ProviderStreamError("Provider stream exceeded the size limit.")
        for piece in chunk.splitlines(keepends=True):
            buffer.extend(piece)
            if len(buffer) > 1024 * 1024:
                raise ProviderStreamError("Provider stream line exceeded the size limit.")
            if buffer.endswith(b"\n"):
                try:
                    yield bytes(buffer).decode("utf-8").rstrip("\r\n")
                except UnicodeError as exc:
                    raise ProviderStreamError("Provider returned invalid UTF-8.") from exc
                buffer.clear()
    if buffer:
        raise ProviderStreamError("Provider returned a truncated SSE line.")


async def _json_events(response):
    data = []
    event_bytes = total_bytes = 0
    done = False
    async for line in _stream_lines(response):
        total_bytes += len(line.encode())
        if total_bytes > 64 * 1024 * 1024:
            raise ProviderStreamError("Provider stream exceeded the size limit.")
        if line.startswith("data:"):
            if done:
                raise ProviderStreamError("Provider returned data after the done marker.")
            value = line[5:].lstrip()
            event_bytes += len(value.encode())
            if event_bytes > 1024 * 1024:
                raise ProviderStreamError("Provider event exceeded the size limit.")
            data.append(value)
        elif not line.strip() and data:
            value = "\n".join(data)
            data, event_bytes = [], 0
            if value == "[DONE]":
                done = True
                continue
            try:
                yield json.loads(value)
            except (ValueError, RecursionError) as exc:
                raise ProviderStreamError("Provider returned invalid streaming JSON.") from exc
    if data:
        raise ProviderStreamError("Provider returned a truncated SSE event.")


async def stream_extended_request(
    credential: dict,
    model: str,
    *,
    url: str,
    body: dict,
    headers: dict,
    timeout: float,
    native_responses: bool = False,
):
    """Yield canonical SSE or a safe HTTP failure, closing HTTP on cancellation."""
    provider = get_credential_provider(credential)
    if native_responses and provider != "meta":
        raise ProviderStreamError("Native Meta history cannot use another provider.")
    protocol = (
        transport(credential).protocol_for_model(credential, model)
        if provider in {"opencode", "meta"}
        else "openai"
    )
    async with http_client.get_streaming_client(
        timeout=timeout, destination_url=url, follow_redirects=False
    ) as client:
        async with client.stream("POST", url, json=body, headers=headers) as response:
            if response.status_code != 200:
                # Vendor bodies can contain credentials or prompt echoes. Status alone
                # drives the existing retry/diagnostic pipeline; do not forward raw text.
                yield Response(
                    json.dumps(
                        {"error": "Provider request failed.", "status_code": response.status_code}
                    ),
                    status_code=response.status_code,
                    media_type="application/json",
                )
                return
            if provider == "kiro":
                stream = transport(credential).stream_to_gemini(response.aiter_bytes())
                async with aclosing(stream):
                    async for chunk in stream:
                        yield chunk
                return
            decoder = _StreamDecoder(protocol)
            completed_event = None
            async for event in _json_events(response):
                try:
                    native_event = _meta_event(event) if native_responses else None
                    decode_event = event
                    output_limited = (
                        provider == "meta" and event.get("type") == "response.incomplete"
                    )
                    if output_limited:
                        response_body = event.get("response") or {}
                        if (response_body.get("incomplete_details") or {}).get(
                            "reason"
                        ) != "max_output_tokens":
                            raise ProviderStreamError("Provider response did not complete.")
                        decode_event = {
                            **event,
                            "type": "response.completed",
                            "response": {**response_body, "status": "completed"},
                        }
                    chunk = decoder.decode(decode_event)
                    if output_limited:
                        decoder.finish = "MAX_TOKENS"
                except (TypeError, AttributeError, KeyError, RecursionError) as exc:
                    raise ProviderStreamError(
                        "Provider returned a malformed stream event."
                    ) from exc
                if native_event and event["type"] in {"response.completed", "response.incomplete"}:
                    completed_event = native_event
                elif native_event:
                    yield _attach_meta_event(chunk or decoder.encode([]), native_event)
                elif chunk:
                    yield chunk
            terminal = decoder.complete()
            if native_responses and completed_event is None:
                raise ProviderStreamError("Provider stream ended before completion.")
            yield _attach_meta_event(terminal, completed_event) if completed_event else terminal


def _attach_meta_event(chunk, event):
    payload = json.loads(chunk[6:])
    payload["_polaris_meta_event"] = event
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _meta_event(event):
    """Only documented Responses events enter the native, authenticated adapter."""
    allowed = {
        "response.created",
        "response.in_progress",
        "response.completed",
        "response.incomplete",
        "response.output_item.added",
        "response.output_item.done",
        "response.content_part.added",
        "response.content_part.done",
        "response.output_text.delta",
        "response.output_text.done",
        "response.function_call_arguments.delta",
        "response.function_call_arguments.done",
        "response.reasoning_summary_part.added",
        "response.reasoning_summary_part.done",
        "response.reasoning_summary_text.delta",
        "response.reasoning_summary_text.done",
        "response.refusal.delta",
        "response.refusal.done",
    }
    if not isinstance(event, dict) or event.get("type") not in allowed:
        raise ProviderStreamError("Provider returned an unsupported native stream event.")
    result = {
        k: v
        for k, v in event.items()
        if k
        in {
            "type",
            "sequence_number",
            "output_index",
            "content_index",
            "summary_index",
            "item_id",
            "delta",
            "text",
            "arguments",
            "refusal",
            "part",
            "item",
            "response",
        }
    }
    if "response" in result:
        response = result["response"]
        if not isinstance(response, dict) or response.get("error"):
            raise ProviderStreamError("Provider returned an invalid native response.")
        result["response"] = {
            k: v
            for k, v in response.items()
            if k
            in {
                "id",
                "object",
                "created_at",
                "status",
                "model",
                "output",
                "usage",
                "parallel_tool_calls",
                "reasoning",
                "text",
                "tool_choice",
                "tools",
                "incomplete_details",
            }
        }
    return result


async def test_extended_credential(credential: dict, model: str) -> Response:
    """Explicit model test, never invoked as a side effect of catalog discovery."""
    from core.api.utils import collect_streaming_response

    request = {
        "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
        "generationConfig": {"maxOutputTokens": 16},
    }
    url, headers, payload = prepare_extended_request(credential, request, model, True)
    stream = stream_extended_request(
        credential, model, url=url, headers=headers, body=payload, timeout=30
    )
    async with aclosing(stream):
        return await collect_streaming_response(stream)
