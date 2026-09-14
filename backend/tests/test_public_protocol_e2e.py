"""Deterministic end-to-end success requests for every advertised public protocol."""

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


def _canonical_response() -> Response:
    return Response(
        content=json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": "deterministic answer"}],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 3,
                    "candidatesTokenCount": 2,
                    "totalTokenCount": 5,
                },
            }
        ),
        status_code=200,
        media_type="application/json",
    )


class PublicProtocolEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_public_protocol_completes_against_deterministic_upstream(self):
        resolution = ModelResolution(
            requested_model="fixture-model",
            response_model="fixture-model",
            candidates=("fixture-model",),
            is_virtual=False,
        )
        cases = (
            (
                "openai_chat_completions",
                "/v1/chat/completions",
                {"Authorization": "Bearer sk-polaris-test-key"},
                {
                    "model": "fixture-model",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                lambda body: body["choices"][0]["message"]["content"],
            ),
            (
                "openai_responses",
                "/v1/responses",
                {"Authorization": "Bearer sk-polaris-test-key"},
                {"model": "fixture-model", "input": "Hello"},
                lambda body: body["output"][0]["content"][0]["text"],
            ),
            (
                "anthropic_messages",
                "/v1/messages",
                {"x-api-key": "sk-polaris-test-key"},
                {
                    "model": "fixture-model",
                    "max_tokens": 64,
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                lambda body: body["content"][0]["text"],
            ),
            (
                "gemini_native",
                "/v1beta/models/fixture-model:generateContent",
                {"x-goog-api-key": "sk-polaris-test-key"},
                {"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]},
                lambda body: body["candidates"][0]["content"]["parts"][0]["text"],
            ),
            (
                "vertex",
                "/vertex/v1beta/models/fixture-model:generateContent",
                {"x-goog-api-key": "sk-polaris-test-key"},
                {"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]},
                lambda body: body["candidates"][0]["content"]["parts"][0]["text"],
            ),
        )

        with ExitStack() as stack:
            audit_service = AsyncMock()
            trace_service = AsyncMock()
            stack.enter_context(patch("main.get_audit_service", return_value=audit_service))
            stack.enter_context(patch("main.get_request_trace_service", return_value=trace_service))
            stack.enter_context(
                patch("config.get_api_key", new=AsyncMock(return_value="sk-polaris-test-key"))
            )
            for module in (
                "core.router.primary.openai",
                "core.router.primary.anthropic",
                "core.router.primary.gemini",
            ):
                stack.enter_context(
                    patch(f"{module}.resolve_model_request", new=AsyncMock(return_value=resolution))
                )
            primary_upstream = stack.enter_context(
                patch(
                    "core.api.primary.non_stream_request",
                    new=AsyncMock(side_effect=lambda **_kwargs: _canonical_response()),
                )
            )
            vertex_upstream = stack.enter_context(
                patch(
                    "core.api.vertex.non_stream_request",
                    new=AsyncMock(side_effect=lambda **_kwargs: _canonical_response()),
                )
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app),
                base_url="http://test",
            ) as client:
                for family, path, headers, request, output_text in cases:
                    with self.subTest(family=family):
                        response = await client.post(path, headers=headers, json=request)

                        self.assertEqual(response.status_code, 200, response.text)
                        self.assertEqual(output_text(response.json()), "deterministic answer")

        self.assertEqual(primary_upstream.await_count, 4)
        self.assertEqual(vertex_upstream.await_count, 1)


if __name__ == "__main__":
    unittest.main()
