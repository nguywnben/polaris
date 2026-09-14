"""Fault-injection coverage for every public streaming protocol family."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.converter.anthropic_to_gemini import gemini_stream_to_anthropic_stream
from core.model_pool import ModelResolution
from core.models import ClaudeRequest, GeminiRequest, OpenAIChatCompletionRequest
from core.router.primary import anthropic, gemini, openai
from core.router.vertex import gemini as vertex_gemini
from core.router.vertex import openai as vertex_openai


class PublicStreamingLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_anthropic_midstream_error_stays_an_error_event(self):
        async def source():
            yield (
                b'data: {"type":"error","error":{"type":"api_error",'
                b'"message":"upstream failed"}}\n\n'
            )

        chunks = [
            chunk async for chunk in gemini_stream_to_anthropic_stream(source(), "gemini-test", 200)
        ]

        payload = b"".join(chunks)
        self.assertIn(b"event: error", payload)
        self.assertNotIn(b"event: message_stop", payload)

    async def _assert_heartbeat_and_close(self, invoke, *, resolve_target=None):
        closed = False

        def fake_stream_request(**_kwargs):
            async def source():
                nonlocal closed
                try:
                    yield ": upstream-ping"
                    yield 'data: {"candidates":[{"finishReason":"STOP"}]}'
                finally:
                    closed = True

            return source()

        resolution = ModelResolution(
            requested_model="gemini-test",
            response_model="gemini-test",
            candidates=("gemini-test",),
            is_virtual=False,
        )
        patches = [patch("core.api.primary.stream_request", side_effect=fake_stream_request)]
        if resolve_target:
            patches.append(patch(resolve_target, AsyncMock(return_value=resolution)))

        with patches[0]:
            if len(patches) == 2:
                with patches[1]:
                    response = await invoke()
            else:
                response = await invoke()

            first = await anext(response.body_iterator)
            await response.body_iterator.aclose()

        self.assertEqual(first, b": upstream-ping\n\n")
        self.assertTrue(closed)

    async def test_openai_chat_stream_heartbeat_and_disconnect(self):
        request = OpenAIChatCompletionRequest(
            model="gemini-test",
            messages=[{"role": "user", "content": "hello"}],
            stream=True,
        )
        await self._assert_heartbeat_and_close(
            lambda: openai.chat_completions(request, token="test"),
            resolve_target="core.router.primary.openai.resolve_model_request",
        )

    async def test_gemini_stream_heartbeat_and_disconnect(self):
        request = GeminiRequest(contents=[{"role": "user", "parts": [{"text": "hello"}]}])
        await self._assert_heartbeat_and_close(
            lambda: gemini.stream_generate_content(request, model="gemini-test", api_key="test"),
            resolve_target="core.router.primary.gemini.resolve_model_request",
        )

    async def test_anthropic_stream_heartbeat_and_disconnect(self):
        request = ClaudeRequest(
            model="gemini-test",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=32,
            stream=True,
        )
        await self._assert_heartbeat_and_close(
            lambda: anthropic.messages(request, _token="test"),
            resolve_target="core.router.primary.anthropic.resolve_model_request",
        )

    async def test_vertex_openai_stream_heartbeat_and_disconnect(self):
        request = OpenAIChatCompletionRequest(
            model="gemini-test",
            messages=[{"role": "user", "content": "hello"}],
            stream=True,
        )
        with patch("core.api.vertex.stream_request") as stream_request:
            stream_request.side_effect = self._vertex_source_factory()
            response = await vertex_openai.chat_completions(request, token="test")
            first = await anext(response.body_iterator)
            await response.body_iterator.aclose()
            closed = stream_request.side_effect.closed

        self.assertEqual(first, b": upstream-ping\n\n")
        self.assertTrue(closed())

    async def test_vertex_gemini_stream_heartbeat_and_disconnect(self):
        request = GeminiRequest(contents=[{"role": "user", "parts": [{"text": "hello"}]}])
        with patch("core.api.vertex.stream_request") as stream_request:
            stream_request.side_effect = self._vertex_source_factory()
            response = await vertex_gemini.stream_generate_content(
                request, model="gemini-test", api_key="test"
            )
            first = await anext(response.body_iterator)
            await response.body_iterator.aclose()
            closed = stream_request.side_effect.closed

        self.assertEqual(first, b": upstream-ping\n\n")
        self.assertTrue(closed())

    @staticmethod
    def _vertex_source_factory():
        state = {"closed": False}

        def factory(**_kwargs):
            async def source():
                try:
                    yield ": upstream-ping"
                    yield 'data: {"candidates":[{"finishReason":"STOP"}]}'
                finally:
                    state["closed"] = True

            return source()

        factory.closed = lambda: state["closed"]
        return factory


if __name__ == "__main__":
    unittest.main()
