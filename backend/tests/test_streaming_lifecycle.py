"""Deterministic lifecycle tests for public streaming responses."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import Response
from starlette.requests import ClientDisconnect

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.api import vertex
from core.api.primary import ProviderRequestContext, stream_request
from core.httpx_client import UpstreamStreamProtocolError, iter_bounded_lines
from core.router.stream_passthrough import (
    ManagedStreamingResponse,
    build_streaming_response_or_error,
    cascade_close_async_iterator,
)


async def _collect_primary_stream(fake_stream_post_async, *, max_retries=3):
    credential = {
        "provider": "google_ai_studio",
        "credential_type": "api_key",
        "api_key": "example-key",
    }
    context = ProviderRequestContext(
        provider_id="google_ai_studio",
        target_url="https://upstream.invalid",
        headers={},
        payload={"model": "gemini-test"},
        request_metrics={},
    )
    record_error = AsyncMock()
    record_success = AsyncMock()
    with (
        patch(
            "core.api.primary.credential_manager.get_valid_model_credential",
            AsyncMock(return_value=("gemini-test", "credential.json", credential)),
        ),
        patch(
            "core.api.primary.prepare_provider_request",
            AsyncMock(return_value=context),
        ),
        patch(
            "core.api.primary.get_retry_config",
            AsyncMock(
                return_value={
                    "retry_enabled": max_retries > 0,
                    "max_retries": max_retries,
                    "retry_interval": 0,
                }
            ),
        ),
        patch(
            "core.api.primary.get_antigravity_switch_credential_enabled",
            AsyncMock(return_value=False),
        ),
        patch(
            "core.api.primary.get_auto_disable_error_codes",
            AsyncMock(return_value=[]),
        ),
        patch(
            "core.api.primary.get_upstream_timeout_seconds",
            AsyncMock(return_value=30),
        ),
        patch("core.api.primary.stream_post_async", side_effect=fake_stream_post_async),
        patch("core.api.primary.record_api_call_error", record_error),
        patch("core.api.primary.record_api_call_success", record_success),
    ):
        chunks = [chunk async for chunk in stream_request(body={"model": "gemini-test"})]
    return chunks, record_error, record_success


class _FakeWreqStream:
    def __init__(self, chunks, error=None):
        self._chunks = chunks
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for chunk in self._chunks:
            yield chunk
        if self._error is not None:
            raise self._error


class _FakeWreqResponse:
    status = 200

    def __init__(self, chunks, error=None):
        self._stream = _FakeWreqStream(chunks, error)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def stream(self):
        return self._stream


class StreamingLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_cascade_closer_releases_nested_stream_on_outer_cancel(self):
        closed = False

        async def source():
            nonlocal closed
            try:
                yield b"one"
                yield b"two"
            finally:
                closed = True

        source_iterator = source()

        async def wrapper():
            async for chunk in source_iterator:
                yield chunk

        stream = cascade_close_async_iterator(wrapper(), [source_iterator])
        self.assertEqual(await anext(stream), b"one")
        await stream.aclose()

        self.assertTrue(closed)

    async def test_cascade_closer_observes_cleanup_failure_and_continues(self):
        class BrokenCloser:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

            async def aclose(self):
                raise RuntimeError("provider-secret")

        broken = BrokenCloser()
        stream = cascade_close_async_iterator(broken, [])
        with patch("core.router.stream_passthrough.log") as stream_log:
            self.assertEqual([item async for item in stream], [])

        rendered_logs = " ".join(str(call) for call in stream_log.mock_calls)
        self.assertNotIn("provider-secret", rendered_logs)
        self.assertIn("RuntimeError", rendered_logs)

    async def test_vertex_stream_does_not_succeed_or_retry_after_partial_failure(self):
        envelope = json.dumps(
            {"results": [{"data": {"candidates": [{"content": {"parts": [{"text": "partial"}]}}]}}]}
        ).encode()
        post = AsyncMock(
            return_value=_FakeWreqResponse([envelope], error=TimeoutError("upstream stalled"))
        )
        success = AsyncMock()

        with (
            patch.object(vertex, "WREQ_AVAILABLE", True),
            patch.object(vertex, "get_upstream_timeout_seconds", AsyncMock(return_value=30)),
            patch.object(vertex, "fetch_recaptcha_token", AsyncMock(return_value="token")),
            patch.object(vertex, "_get_batch_graphql_url", return_value="https://invalid"),
            patch.object(vertex.wreq, "post", post),
            patch("core.api.utils.record_unassigned_api_call_success", success),
        ):
            chunks = [
                chunk
                async for chunk in vertex.stream_request({"model": "gemini-test", "request": {}})
            ]

        post.assert_awaited_once()
        self.assertEqual(post.await_args.kwargs["read_timeout"].total_seconds(), 30)
        self.assertIsInstance(chunks[-1], Response)
        self.assertEqual(chunks[-1].status_code, 504)
        success.assert_not_awaited()

    async def test_vertex_stream_records_success_only_after_terminal_event(self):
        envelope = json.dumps(
            {
                "results": [
                    {
                        "data": {
                            "candidates": [{"finishReason": "STOP"}],
                            "usageMetadata": {"totalTokenCount": 4},
                        }
                    }
                ]
            }
        ).encode()
        post = AsyncMock(return_value=_FakeWreqResponse([envelope]))
        success = AsyncMock()

        with (
            patch.object(vertex, "WREQ_AVAILABLE", True),
            patch.object(vertex, "get_upstream_timeout_seconds", AsyncMock(return_value=30)),
            patch.object(vertex, "fetch_recaptcha_token", AsyncMock(return_value="token")),
            patch.object(vertex, "_get_batch_graphql_url", return_value="https://invalid"),
            patch.object(vertex.wreq, "post", post),
            patch("core.api.utils.record_unassigned_api_call_success", success),
        ):
            chunks = [
                chunk
                async for chunk in vertex.stream_request({"model": "gemini-test", "request": {}})
            ]

        self.assertEqual(len(chunks), 1)
        self.assertNotIsInstance(chunks[0], Response)
        success.assert_awaited_once()

    async def test_vertex_stream_applies_compression_once_and_records_its_decision(self):
        envelope = json.dumps(
            {
                "results": [
                    {
                        "data": {
                            "candidates": [{"finishReason": "STOP"}],
                            "usageMetadata": {"totalTokenCount": 4},
                        }
                    }
                ]
            }
        ).encode()
        post = AsyncMock(return_value=_FakeWreqResponse([envelope]))
        success = AsyncMock()
        contents = []
        for turn in range(5):
            contents.extend(
                (
                    {"role": "user", "parts": [{"text": f"old-{turn}-" + "u" * 240}]},
                    {"role": "model", "parts": [{"text": f"answer-{turn}-" + "m" * 240}]},
                )
            )
        contents.append({"role": "user", "parts": [{"text": "CURRENT-VERTEX"}]})

        with (
            patch.object(vertex, "WREQ_AVAILABLE", True),
            patch.object(vertex, "get_upstream_timeout_seconds", AsyncMock(return_value=30)),
            patch.object(
                vertex,
                "get_token_compression_config",
                AsyncMock(
                    return_value={
                        "enabled": True,
                        "threshold_tokens": 128,
                        "target_tokens": 64,
                        "min_recent_turns": 1,
                        "quality_profile": "balanced",
                        "quality_policy_revision": 7,
                    }
                ),
            ) as get_compression,
            patch.object(vertex, "fetch_recaptcha_token", AsyncMock(return_value="token")),
            patch.object(vertex, "_get_batch_graphql_url", return_value="https://invalid"),
            patch.object(vertex.wreq, "post", post),
            patch("core.api.utils.record_unassigned_api_call_success", success),
        ):
            chunks = [
                chunk
                async for chunk in vertex.stream_request(
                    {"model": "gemini-test", "request": {"contents": contents}}
                )
            ]

        self.assertEqual(len(chunks), 1)
        get_compression.assert_awaited_once()
        forwarded = post.await_args.kwargs["json"]["variables"]["contents"]
        self.assertLess(len(forwarded), len(contents))
        self.assertIn("CURRENT-VERTEX", json.dumps(forwarded))
        metrics = success.await_args.kwargs["request_metrics"]
        self.assertEqual(metrics["quality_profile"], "balanced")
        self.assertEqual(metrics["quality_policy_revision"], 7)
        self.assertGreater(metrics["estimated_tokens_saved"], 0)

    async def test_vertex_stream_preserves_utf8_split_between_transport_chunks(self):
        envelope = json.dumps(
            {
                "results": [
                    {
                        "data": {
                            "candidates": [
                                {
                                    "content": {"parts": [{"text": "Tiếng Việt"}]},
                                    "finishReason": "STOP",
                                }
                            ]
                        }
                    }
                ]
            },
            ensure_ascii=False,
        ).encode("utf-8")
        split_at = envelope.index("ế".encode("utf-8")) + 1
        post = AsyncMock(return_value=_FakeWreqResponse([envelope[:split_at], envelope[split_at:]]))

        with (
            patch.object(vertex, "WREQ_AVAILABLE", True),
            patch.object(vertex, "get_upstream_timeout_seconds", AsyncMock(return_value=30)),
            patch.object(vertex, "fetch_recaptcha_token", AsyncMock(return_value="token")),
            patch.object(vertex, "_get_batch_graphql_url", return_value="https://invalid"),
            patch.object(vertex.wreq, "post", post),
            patch("core.api.utils.record_unassigned_api_call_success", AsyncMock()),
        ):
            chunks = [
                chunk
                async for chunk in vertex.stream_request({"model": "gemini-test", "request": {}})
            ]

        self.assertEqual(len(chunks), 1)
        self.assertIn("Tiếng Việt", chunks[0])

    async def test_vertex_stream_rejects_oversized_unframed_buffer(self):
        post = AsyncMock(return_value=_FakeWreqResponse([b"x" * 17]))
        success = AsyncMock()

        with (
            patch.object(vertex, "WREQ_AVAILABLE", True),
            patch.object(vertex, "get_upstream_timeout_seconds", AsyncMock(return_value=30)),
            patch.object(vertex, "_MAX_VERTEX_STREAM_BUFFER_BYTES", 16),
            patch.object(vertex, "fetch_recaptcha_token", AsyncMock(return_value="token")),
            patch.object(vertex, "_get_batch_graphql_url", return_value="https://invalid"),
            patch.object(vertex.wreq, "post", post),
            patch.object(vertex.asyncio, "sleep", AsyncMock()),
            patch("core.api.utils.record_unassigned_api_call_success", success),
        ):
            chunks = [
                chunk
                async for chunk in vertex.stream_request({"model": "gemini-test", "request": {}})
            ]

        self.assertEqual(post.await_count, 4)
        self.assertIsInstance(chunks[-1], Response)
        self.assertEqual(chunks[-1].status_code, 502)
        success.assert_not_awaited()

    async def test_primary_stream_does_not_retry_after_model_output(self):
        stream_calls = 0

        def fake_stream_post_async(**_kwargs):
            nonlocal stream_calls
            stream_calls += 1

            async def chunks():
                yield 'data: {"candidates":[{"content":{"parts":[{"text":"partial"}]}}]}'
                raise httpx.ReadTimeout("upstream stalled")

            return chunks()

        chunks, record_error, record_success = await _collect_primary_stream(fake_stream_post_async)

        self.assertEqual(stream_calls, 1)
        self.assertEqual(chunks[0][:5], "data:")
        self.assertIsInstance(chunks[-1], Response)
        self.assertEqual(chunks[-1].status_code, 504)
        record_error.assert_awaited_once()
        record_success.assert_not_awaited()

    async def test_primary_stream_rejects_eof_without_terminal_event(self):
        def fake_stream_post_async(**_kwargs):
            async def chunks():
                yield 'data: {"candidates":[{"content":{"parts":[{"text":"partial"}]}}]}'

            return chunks()

        chunks, record_error, record_success = await _collect_primary_stream(
            fake_stream_post_async, max_retries=0
        )

        self.assertIsInstance(chunks[-1], Response)
        self.assertEqual(chunks[-1].status_code, 502)
        record_error.assert_awaited_once()
        record_success.assert_not_awaited()

    async def test_primary_stream_does_not_retry_midstream_error_response(self):
        stream_calls = 0

        def fake_stream_post_async(**_kwargs):
            nonlocal stream_calls
            stream_calls += 1

            async def chunks():
                yield 'data: {"candidates":[{"content":{"parts":[{"text":"partial"}]}}]}'
                yield Response(content=b'{"error":"overloaded"}', status_code=503)

            return chunks()

        chunks, record_error, record_success = await _collect_primary_stream(fake_stream_post_async)

        self.assertEqual(stream_calls, 1)
        self.assertIsInstance(chunks[-1], Response)
        self.assertEqual(chunks[-1].status_code, 503)
        record_error.assert_awaited_once()
        record_success.assert_not_awaited()

    async def test_primary_stream_heartbeat_does_not_suppress_safe_retry(self):
        stream_calls = 0

        def fake_stream_post_async(**_kwargs):
            nonlocal stream_calls
            stream_calls += 1

            async def chunks():
                if stream_calls == 1:
                    yield ": keep-alive"
                    raise httpx.ReadTimeout("upstream stalled")
                yield 'data: {"candidates":[{"finishReason":"STOP"}]}'

            return chunks()

        chunks, record_error, record_success = await _collect_primary_stream(fake_stream_post_async)

        self.assertEqual(stream_calls, 2)
        self.assertEqual(
            chunks,
            [
                ": keep-alive\n\n",
                'data: {"candidates":[{"finishReason":"STOP"}]}\n\n',
            ],
        )
        record_error.assert_awaited_once()
        record_success.assert_awaited_once()

    async def test_bounded_line_reader_preserves_split_crlf_frames(self):
        class FakeResponse:
            async def aiter_bytes(self, chunk_size):
                self.chunk_size = chunk_size
                for chunk in (b"data: one\r", b"\ndata: two\n", b"tail"):
                    yield chunk

        response = FakeResponse()

        lines = [line async for line in iter_bounded_lines(response, max_line_bytes=16)]

        self.assertEqual(lines, ["data: one", "data: two", "tail"])
        self.assertGreater(response.chunk_size, 0)

    async def test_bounded_line_reader_rejects_oversized_frame(self):
        class FakeResponse:
            async def aiter_bytes(self, chunk_size):
                del chunk_size
                yield b"12345"
                yield b"67890"

        with self.assertRaisesRegex(UpstreamStreamProtocolError, "exceeds"):
            _ = [line async for line in iter_bounded_lines(FakeResponse(), max_line_bytes=8)]

    async def test_prefetched_error_closes_source_iterator(self):
        closed = False

        async def source():
            nonlocal closed
            try:
                yield Response(status_code=502)
            finally:
                closed = True

        response = await build_streaming_response_or_error(source())

        self.assertEqual(response.status_code, 502)
        self.assertTrue(closed)

    async def test_downstream_disconnect_closes_source_iterator(self):
        closed = False

        async def source():
            nonlocal closed
            try:
                yield b"first"
                yield b"second"
            finally:
                closed = True

        response = ManagedStreamingResponse(source())
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/v1/chat/completions",
            "headers": [],
            "asgi": {"spec_version": "2.4"},
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                raise OSError("client disconnected")

        with self.assertRaises(ClientDisconnect):
            await response(scope, receive, send)

        self.assertTrue(closed)


if __name__ == "__main__":
    unittest.main()
