"""Integration regressions for the expanded provider runtime boundary."""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.api import primary
from core.extended_provider_runtime import (
    _StreamDecoder,
    discover_extended_models,
    prepare_extended_request,
    stream_extended_request,
)
from core.provider_registry import EXTENDED_PROVIDERS

from backend.tests.test_kiro import frame

KEY = "test-key-not-real"
CANONICAL = 'data: {"candidates":[{"content":{"role":"model","parts":[{"text":"ok"}]},"finishReason":"STOP"}]}\n\n'


class ExtendedRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def test_multiple_candidates_are_rejected_before_provider_preparation(self):
        for count in (0, 2, True, "1"):
            with (
                self.subTest(count=count),
                patch("core.extended_provider_runtime.transport") as leaf,
            ):
                with self.assertRaises(ValueError):
                    prepare_extended_request(
                        {"provider": "kimi"},
                        {"generationConfig": {"candidateCount": count}},
                        "model",
                        True,
                    )
                leaf.assert_not_called()

    async def test_discovery_timeout_is_a_safe_provider_error(self):
        with patch("core.kiro.discover_models", AsyncMock(side_effect=TimeoutError("secret"))):
            with self.assertRaises(ValueError) as caught:
                await discover_extended_models({"provider": "kiro", "api_key": KEY})
        self.assertEqual(caught.exception.status_code, 504)
        self.assertNotIn("secret", str(caught.exception))

    async def test_http_response_is_closed_on_consumer_cancellation(self):
        closed = []

        class Body(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
                raise AssertionError("Consumer should close before the next body read")

            async def aclose(self):
                closed.append(True)

        @asynccontextmanager
        async def client(**kwargs):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Body()))
            ) as value:
                yield value

        with patch("core.extended_provider_runtime.http_client.get_streaming_client", client):
            stream = stream_extended_request(
                {"provider": "kimi", "api_key": KEY},
                "model",
                url="https://fixture.invalid",
                body={},
                headers={},
                timeout=30,
            )
            await anext(stream)
            await stream.aclose()
        self.assertEqual(closed, [True])

    async def run_wire(self, provider, wire, status=200, headers=None):
        @asynccontextmanager
        async def client(**kwargs):
            self.assertFalse(kwargs["follow_redirects"])
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(status, content=wire, headers=headers)
                )
            ) as value:
                yield value

        with patch("core.extended_provider_runtime.http_client.get_streaming_client", client):
            return [
                item
                async for item in stream_extended_request(
                    {
                        "provider": provider,
                        "api_key": KEY,
                        **(
                            {
                                "credential_type": "oauth",
                                "access_token": KEY,
                                "account_id": "0" * 64,
                            }
                            if provider == "muse_code"
                            else {}
                        ),
                    },
                    {
                        "meta": "muse-spark-1.1",
                        "muse_code": "muse-code/muse-spark-1.1",
                        "opencode": "gpt-test",
                    }.get(provider, "model"),
                    url="https://fixture.invalid",
                    body={},
                    headers={},
                    timeout=30,
                )
            ]

    async def test_binary_kiro_is_decoded_without_text_line_reader(self):
        wire = frame("assistantResponseEvent", {"content": "ok"}) + frame("messageStopEvent", {})
        result = await self.run_wire("kiro", wire)
        self.assertIn('"text": "ok"', result[0])
        self.assertIn('"finishReason": "STOP"', result[-1])

    async def test_vendor_error_body_is_not_forwarded(self):
        result = await self.run_wire("kiro", b"secret upstream key", 429)
        self.assertEqual(result[0].status_code, 429)
        self.assertNotIn(b"secret", result[0].body)

    async def test_all_extended_providers_preserve_safe_throttle_headers_not_secrets(self):
        for provider in EXTENDED_PROVIDERS:
            for status in (401, 403, 404, 402, 429, 503, 504):
                with self.subTest(provider=provider, status=status):
                    result = await self.run_wire(
                        provider,
                        b"secret upstream body",
                        status,
                        {
                            "Retry-After": "37",
                            "X-Provider-Secret": "secret",
                            "Set-Cookie": "secret",
                        },
                    )
                    self.assertEqual(result[0].status_code, status)
                    self.assertEqual(result[0].headers.get("retry-after"), "37")
                    self.assertNotIn("secret", str(dict(result[0].headers)))
                    self.assertNotIn(b"secret", result[0].body)

    async def test_untrusted_retry_header_does_not_cross_extended_provider_boundary(self):
        for retry_after in ("secret", "-1", "9" * 200):
            with self.subTest(retry_after=retry_after):
                result = await self.run_wire("kimi", b"secret", 429, {"Retry-After": retry_after})
                self.assertNotIn("retry-after", result[0].headers)

    async def test_malformed_json_or_missing_terminal_is_not_success(self):
        wires = (b"data: broken\n\n", b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n')
        for wire in wires:
            with self.subTest(wire=wire), self.assertRaises(ValueError):
                await self.run_wire("kimi", wire)

    async def test_malformed_tool_arguments_fail_closed(self):
        payload = {
            "id": "s",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call",
                                "function": {"name": "search", "arguments": "broken"},
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }
        wire = f"data: {json.dumps(payload)}\n\ndata: [DONE]\n\n".encode()
        with self.assertRaises(ValueError):
            await self.run_wire("kimi", wire)

    def test_anthropic_partial_json_does_not_keep_initial_empty_object(self):
        decoder = _StreamDecoder("anthropic")
        decoder.decode(
            {
                "type": "message_start",
                "message": {"usage": {"input_tokens": 5, "cache_read_input_tokens": 3}},
            }
        )
        decoder.decode(
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "tool_use", "id": "call1", "name": "search", "input": {}},
            }
        )
        decoder.decode(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": '{"q":"ok"}'},
            }
        )
        result = decoder.decode({"type": "content_block_stop", "index": 0})
        self.assertIn('"args": {"q": "ok"}', result)
        decoder.decode(
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use"},
                "usage": {"output_tokens": 2},
            }
        )
        decoder.decode({"type": "message_delta", "usage": {"output_tokens": 4}})
        decoder.decode({"type": "message_stop"})
        self.assertEqual(json.loads(decoder.complete()[6:])["usageMetadata"]["totalTokenCount"], 12)

    def test_openai_and_responses_preserve_cached_and_reasoning_usage(self):
        for protocol, input_key, output_key in (
            ("openai", "prompt_tokens", "completion_tokens"),
            ("responses", "input_tokens", "output_tokens"),
        ):
            with self.subTest(protocol=protocol):
                decoder = _StreamDecoder(protocol)
                usage = {
                    input_key: 20,
                    output_key: 10,
                    "total_tokens": 30,
                    f"{input_key}_details": {"cached_tokens": 7},
                    f"{output_key}_details": {"reasoning_tokens": 4},
                }
                if protocol == "openai":
                    decoder.decode({"choices": [{"delta": {}, "finish_reason": "stop"}]})
                    decoder.decode({"choices": [], "usage": usage})
                    decoder.decode({"choices": [], "usage": usage})
                else:
                    decoder.decode({"type": "response.completed", "response": {"usage": usage}})
                self.assertEqual(
                    json.loads(decoder.complete()[6:])["usageMetadata"],
                    {
                        "promptTokenCount": 20,
                        "candidatesTokenCount": 6,
                        "totalTokenCount": 30,
                        "cachedContentTokenCount": 7,
                        "thoughtsTokenCount": 4,
                    },
                )

    def test_usage_details_are_validated_and_optional(self):
        for details in ({"reasoning_tokens": -1}, {"reasoning_tokens": True}, "bad"):
            with self.subTest(details=details), self.assertRaises(ValueError):
                _StreamDecoder("openai").decode({"usage": {"completion_tokens_details": details}})
        decoder = _StreamDecoder("openai")
        decoder.decode({"usage": {"prompt_tokens": 2, "completion_tokens": 3}})
        self.assertNotIn("thoughtsTokenCount", decoder.usage)
        self.assertNotIn("cachedContentTokenCount", decoder.usage)
        self.assertEqual(decoder.usage["totalTokenCount"], 5)

    def test_responses_malformed_tools_do_not_turn_into_raw_arguments(self):
        decoder = _StreamDecoder("responses")
        with self.assertRaises(ValueError):
            decoder.decode(
                {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "function_call",
                        "id": "i1",
                        "call_id": "c1",
                        "name": "search",
                        "arguments": "bad",
                    },
                }
            )

    def test_response_and_gemini_terminals_are_preserved(self):
        for protocol, event in (
            (
                "responses",
                {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "usage": {"input_tokens": 3, "output_tokens": 4},
                    },
                },
            ),
            (
                "gemini",
                {
                    "candidates": [
                        {"content": {"parts": [{"text": "ok"}]}, "finishReason": "MAX_TOKENS"}
                    ],
                    "usageMetadata": {"totalTokenCount": 7},
                },
            ),
        ):
            with self.subTest(protocol=protocol):
                decoder = _StreamDecoder(protocol)
                decoder.decode(event)
                result = json.loads(decoder.complete()[6:])
                self.assertEqual(result["usageMetadata"]["totalTokenCount"], 7)
                self.assertEqual(
                    result["candidates"][0]["finishReason"],
                    "MAX_TOKENS" if protocol == "gemini" else "STOP",
                )

    def test_content_after_terminal_is_rejected_in_each_protocol(self):
        for protocol, stop, extra in (
            (
                "anthropic",
                {"type": "message_stop"},
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "late"}},
            ),
            (
                "responses",
                {"type": "response.completed"},
                {"type": "response.output_text.delta", "delta": "late"},
            ),
            (
                "gemini",
                {"candidates": [{"finishReason": "STOP"}]},
                {"candidates": [{"content": {"parts": [{"text": "late"}]}}]},
            ),
        ):
            with self.subTest(protocol=protocol):
                decoder = _StreamDecoder(protocol)
                decoder.decode(stop)
                with self.assertRaises(ValueError):
                    decoder.decode(extra)

    def test_partial_tools_are_isolated_between_requests(self):
        first, second = _StreamDecoder("openai"), _StreamDecoder("openai")
        first.decode(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call",
                                    "function": {"name": "search", "arguments": "{"},
                                }
                            ]
                        }
                    }
                ]
            }
        )
        second.decode({"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]})
        self.assertNotIn("functionCall", second.complete())
        with self.assertRaises(ValueError):
            first.complete()


class PrimaryExtendedIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_upstream_failure_bodies_never_enter_stream_or_nonstream_logs(self):
        secret = "arbitrary-private-upstream-content"
        for streaming in (False, True):
            for status in (400, 503):
                provider = "kiro" if streaming else "google_ai_studio"
                stack, _ = self.fixtures(
                    [("model", "fixture.json", {"provider": provider, "api_key": KEY})]
                )

                async def failed_stream(*args, **kwargs):
                    yield primary.Response(secret, status_code=status)

                with (
                    self.subTest(streaming=streaming, status=status),
                    stack,
                    patch(
                        "core.api.primary.post_async",
                        AsyncMock(return_value=httpx.Response(status, text=secret)),
                    ),
                    patch("core.api.primary.stream_extended_request", failed_stream),
                    patch("core.api.primary.log.error") as error_log,
                ):
                    if streaming:
                        result = [
                            item
                            async for item in primary._stream_request_upstream({"model": "model"})
                        ][-1]
                    else:
                        result = await primary._non_stream_request_upstream({"model": "model"})
                self.assertEqual(result.status_code, status)
                self.assertNotIn(secret, str(error_log.call_args_list))

    async def test_cancelled_nonstream_collection_releases_extended_credential(self):
        async def cancelled(*args, **kwargs):
            raise asyncio.CancelledError
            yield CANONICAL

        stack, release = self.fixtures([("model", "k.json", {"provider": "kiro", "api_key": KEY})])
        with stack, patch("core.api.primary.stream_extended_request", cancelled):
            with self.assertRaises(asyncio.CancelledError):
                await primary._non_stream_request_upstream({"model": "model"})
            release.assert_awaited_once()

    async def test_ingress_headers_cannot_override_kiro_credentials(self):
        with patch("core.api.primary.get_token_compression_config", AsyncMock(return_value={})):
            context = await primary.prepare_provider_request(
                {"provider": "kiro", "api_key": KEY},
                {"model": "model", "contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
                streaming=True,
                extra_headers={
                    "Authorization": "Bearer injected",
                    "tokentype": "injected",
                    "Host": "evil.example",
                },
            )
        self.assertEqual(context.headers["Authorization"], f"Bearer {KEY}")
        self.assertEqual(context.headers["tokentype"], "API_KEY")
        self.assertNotIn("Host", context.headers)

    def fixtures(self, routes):
        stack = ExitStack()

        def mock(name, value=None, *, side_effect=None):
            item = AsyncMock(return_value=value, side_effect=side_effect)
            stack.enter_context(patch(f"core.api.primary.{name}", item))
            return item

        mock("credential_manager.get_valid_model_credential", side_effect=routes)
        release = mock("credential_manager.release_credential")
        mock("get_retry_config", {"retry_enabled": False, "max_retries": 0, "retry_interval": 0})
        mock("get_auto_disable_error_codes", [])
        mock("get_upstream_timeout_seconds", 30)
        mock("get_antigravity_switch_credential_enabled", True)
        mock("get_antigravity_stream_to_nonstream", False)
        mock("record_api_call_success")
        mock("record_api_call_error")
        mock("record_model_route_miss")

        async def prepare(credential, body, *, streaming, extra_headers):
            return primary.ProviderRequestContext(
                credential["provider"], "https://fixture.invalid", {}, {"stream": streaming}, {}
            )

        stack.enter_context(patch("core.api.primary.prepare_provider_request", prepare))
        return stack, release

    async def test_closing_primary_stream_closes_active_transport_immediately(self):
        closed = []

        async def transport(*args, **kwargs):
            try:
                yield CANONICAL
            finally:
                closed.append(True)

        stack, release = self.fixtures([("model", "k.json", {"provider": "kiro", "api_key": KEY})])
        with stack, patch("core.api.primary.stream_extended_request", transport):
            stream = primary._stream_request_upstream({"model": "model"})
            await anext(stream)
            await stream.aclose()
            self.assertEqual(closed, [True])
            release.assert_awaited_once()

    async def test_nonstream_retry_from_old_provider_to_kiro_uses_binary_path(self):
        routes = [
            ("model", "old.json", {"provider": "google_ai_studio", "api_key": KEY}),
            ("model", "new.json", {"provider": "kiro", "api_key": KEY}),
        ]
        stream_calls = []

        async def transport(*args, **kwargs):
            stream_calls.append(kwargs)
            yield CANONICAL

        stack, _ = self.fixtures(routes)
        post = AsyncMock(return_value=httpx.Response(404, content=b"not found"))
        with (
            stack,
            patch("core.api.primary.post_async", post),
            patch("core.api.primary.stream_extended_request", transport),
        ):
            result = await primary._non_stream_request_upstream({"model": "model"})
        self.assertEqual(result.status_code, 200)
        self.assertIn(b"ok", result.body)
        post.assert_awaited_once()
        self.assertEqual(len(stream_calls), 1)

    async def test_stream_failure_can_switch_to_an_extended_provider(self):
        routes = [
            ("model", "old.json", {"provider": "google_ai_studio", "api_key": KEY}),
            ("model", "new.json", {"provider": "kiro", "api_key": KEY}),
        ]

        async def old(**kwargs):
            from fastapi import Response

            yield Response(status_code=404)

        async def new(*args, **kwargs):
            yield CANONICAL

        stack, _ = self.fixtures(routes)
        with (
            stack,
            patch("core.api.primary.stream_post_async", old),
            patch("core.api.primary.stream_extended_request", new),
        ):
            result = [item async for item in primary._stream_request_upstream({"model": "model"})]
        self.assertEqual(result, [CANONICAL])
