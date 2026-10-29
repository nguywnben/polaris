"""Hermes reasoning effort requests must cross the public Chat API boundary."""

from __future__ import annotations

import json
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import Response

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main
from core.model_pool import ModelResolution

MODEL = "gemini-3.8-flash-tiered"
PATHS = ("/v1/chat/completions", "/vertex/v1/chat/completions")
ANSWER = "Hermes reasoning request completed."


def _upstream_payload():
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": ANSWER}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 3,
            "candidatesTokenCount": 2,
            "totalTokenCount": 5,
        },
    }


async def _upstream_response(**_kwargs):
    return Response(content=json.dumps(_upstream_payload()), media_type="application/json")


async def _upstream_stream(**_kwargs):
    yield f"data: {json.dumps(_upstream_payload())}\n\n"
    yield "data: [DONE]\n\n"


class HermesReasoningBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch("main.get_audit_service", return_value=AsyncMock()))
        stack.enter_context(patch("main.get_request_trace_service", return_value=AsyncMock()))
        stack.enter_context(
            patch("config.get_api_key", new=AsyncMock(return_value="sk-polaris-test-key"))
        )
        stack.enter_context(
            patch("config.get_return_thoughts_to_frontend", new=AsyncMock(return_value=True))
        )
        stack.enter_context(
            patch(
                "core.router.primary.openai.resolve_model_request",
                new=AsyncMock(
                    return_value=ModelResolution(
                        requested_model=MODEL,
                        response_model=MODEL,
                        candidates=(MODEL,),
                        is_virtual=False,
                    )
                ),
            )
        )
        for provider in ("primary", "vertex"):
            stack.enter_context(
                patch(f"core.api.{provider}.non_stream_request", new=_upstream_response)
            )
            stack.enter_context(patch(f"core.api.{provider}.stream_request", new=_upstream_stream))
        self.client = await self.enterAsyncContext(
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app),
                base_url="http://test",
                headers={"Authorization": "Bearer sk-polaris-test-key"},
            )
        )

    async def test_hermes_low_and_high_effort_complete_nonstreaming(self):
        for path in PATHS:
            for effort in ("low", "high"):
                with self.subTest(path=path, effort=effort):
                    response = await self.client.post(
                        path,
                        json={
                            "model": MODEL,
                            "messages": [{"role": "user", "content": "Hello"}],
                            "reasoning_effort": effort,
                            "stream": False,
                        },
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["choices"][0]["message"]["content"], ANSWER)

    async def test_hermes_low_and_high_effort_complete_streaming(self):
        for path in PATHS:
            for effort in ("low", "high"):
                with self.subTest(path=path, effort=effort):
                    response = await self.client.post(
                        path,
                        json={
                            "model": MODEL,
                            "messages": [{"role": "user", "content": "Hello"}],
                            "reasoning_effort": effort,
                            "stream": True,
                        },
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertIn("text/event-stream", response.headers["content-type"])
                    chunks = [
                        json.loads(line[6:])
                        for line in response.text.splitlines()
                        if line.startswith("data: ") and line != "data: [DONE]"
                    ]
                    answer = "".join(
                        choice.get("delta", {}).get("content", "")
                        for chunk in chunks
                        for choice in chunk.get("choices", [])
                    )
                    self.assertEqual(answer, ANSWER)
                    self.assertIn("data: [DONE]", response.text)

    async def test_invalid_reasoning_effort_still_returns_http_400(self):
        for path in PATHS:
            for effort in ("unknown", "", 42, True, {"effort": "high"}):
                for streaming in (False, True):
                    with self.subTest(path=path, effort=effort, streaming=streaming):
                        response = await self.client.post(
                            path,
                            json={
                                "model": MODEL,
                                "messages": [{"role": "user", "content": "Hello"}],
                                "reasoning_effort": effort,
                                "stream": streaming,
                            },
                        )
                        self.assertEqual(response.status_code, 400, response.text)
                        error = response.json()["error"]
                        self.assertEqual(error["type"], "invalid_request_error")
                        self.assertIn("reasoning_effort", error["message"])

    async def test_vertex_none_is_clear_http_400_before_any_upstream_dispatch(self):
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                response = await self.client.post(
                    "/vertex/v1/chat/completions",
                    json={
                        "model": MODEL,
                        "messages": [{"role": "user", "content": "Hello"}],
                        "reasoning_effort": "none",
                        "stream": streaming,
                    },
                )
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(response.json()["error"]["type"], "invalid_request_error")
                self.assertIn(
                    "does not support disabling reasoning", response.json()["error"]["message"]
                )

    async def test_primary_none_uses_real_preparation_and_does_not_penalize_credential(self):
        from core.api import primary

        from backend.tests.test_extended_provider_runtime import PrimaryExtendedIntegrationTests

        real_prepare = primary.prepare_provider_request
        for streaming in (False, True):
            stack, release = PrimaryExtendedIntegrationTests().fixtures(
                [(MODEL, "fixture.json", {"provider": "google_antigravity"})]
            )
            with (
                self.subTest(streaming=streaming),
                stack,
                patch.object(primary, "prepare_provider_request", real_prepare),
                patch.object(primary, "non_stream_request", primary._non_stream_request_upstream),
                patch.object(primary, "stream_request", primary._stream_request_upstream),
                patch.object(primary, "post_async", new=AsyncMock()) as post,
                patch.object(primary, "stream_post_async") as stream,
            ):
                response = await self.client.post(
                    "/v1/chat/completions",
                    json={
                        "model": MODEL,
                        "messages": [{"role": "user", "content": "Hello"}],
                        "reasoning_effort": "none",
                        "stream": streaming,
                    },
                )
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(response.json()["error"]["type"], "invalid_request_error")
                self.assertIn(
                    "does not support disabling reasoning", response.json()["error"]["message"]
                )
                release.assert_awaited_once_with("fixture.json", mode="primary")
                primary.record_api_call_error.assert_not_awaited()
                post.assert_not_awaited()
                stream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
