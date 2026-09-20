"""Discovery stays compact while explicit legacy feature IDs remain callable."""

from __future__ import annotations

import json
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import Response

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main

MODEL = "gemini-2.5-flash"
PROVIDER_VARIANT = "claude-sonnet-4-6-thinking"
PREFIXES = ("fake-streaming/", "streaming-anti-truncation/")


def _payload():
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": "Hello [done]"}]},
                "finishReason": "STOP",
            }
        ]
    }


class ModelDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = self.enterContext(ExitStack())
        self.stack.enter_context(patch("main.get_audit_service", return_value=AsyncMock()))
        self.stack.enter_context(patch("main.get_request_trace_service", return_value=AsyncMock()))
        self.stack.enter_context(
            patch("config.get_api_key", new=AsyncMock(return_value="sk-polaris-discovery-test"))
        )
        self.catalog = self.stack.enter_context(
            patch(
                "core.router.primary.model_list.model_catalog_service.get_catalog",
                new=AsyncMock(
                    return_value=[
                        SimpleNamespace(model_id=MODEL),
                        SimpleNamespace(model_id=PROVIDER_VARIANT),
                    ]
                ),
            )
        )
        self.aliases = self.stack.enter_context(
            patch(
                "core.router.primary.model_list.get_public_virtual_models",
                new=AsyncMock(return_value=["polaris"]),
            )
        )
        self.client = await self.enterAsyncContext(
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=main.app),
                base_url="http://test",
                headers={"Authorization": "Bearer sk-polaris-discovery-test"},
            )
        )

    async def assert_discovery(self, expected):
        for path in ("/v1/models", "/v1beta/models"):
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                if path == "/v1/models":
                    self.assertEqual(payload["object"], "list")
                    actual = [item["id"] for item in payload["data"]]
                else:
                    actual = [item["name"].removeprefix("models/") for item in payload["models"]]
                self.assertEqual(actual, expected)

    async def test_only_provider_models_and_configured_alias_are_advertised(self):
        await self.assert_discovery([MODEL, PROVIDER_VARIANT, "polaris"])

    async def test_duplicate_provider_ids_and_alias_collisions_are_deduplicated(self):
        self.catalog.return_value.append(SimpleNamespace(model_id=MODEL))
        self.aliases.return_value = [MODEL, "polaris", "polaris"]
        await self.assert_discovery([MODEL, PROVIDER_VARIANT, "polaris"])

    async def test_configured_alias_survives_empty_catalog(self):
        self.catalog.return_value = []
        await self.assert_discovery(["polaris"])

    async def test_empty_catalog_and_no_alias_return_empty_lists(self):
        self.catalog.return_value = []
        self.aliases.return_value = []
        await self.assert_discovery([])

    async def test_explicit_legacy_prefixes_still_route_and_stream(self):
        self.stack.enter_context(
            patch("config.get_return_thoughts_to_frontend", new=AsyncMock(return_value=True))
        )
        self.stack.enter_context(
            patch(
                "core.router.primary.openai.get_anti_truncation_max_attempts",
                new=AsyncMock(return_value=1),
            )
        )
        calls = []

        async def non_stream(**kwargs):
            calls.append(("nonstream", kwargs))
            return Response(content=json.dumps(_payload()), media_type="application/json")

        async def stream(**kwargs):
            calls.append(("stream", kwargs))
            yield f"data: {json.dumps(_payload())}\n\n"
            yield "data: [DONE]\n\n"

        self.stack.enter_context(patch("core.api.primary.non_stream_request", new=non_stream))
        self.stack.enter_context(patch("core.api.primary.stream_request", new=stream))
        for prefix, mode in zip(PREFIXES, ("nonstream", "stream"), strict=True):
            with self.subTest(prefix=prefix):
                calls.clear()
                response = await self.client.post(
                    "/v1/chat/completions",
                    json={
                        "model": prefix + MODEL,
                        "messages": [{"role": "user", "content": "Hello"}],
                        "stream": True,
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn("text/event-stream", response.headers["content-type"])
                self.assertIn("Hello", response.text)
                self.assertIn("data: [DONE]", response.text)
                self.assertEqual(len(calls), 1)
                actual_mode, kwargs = calls[0]
                self.assertEqual(actual_mode, mode)
                self.assertEqual(kwargs["body"]["model"], MODEL)
                self.assertEqual(kwargs["model_candidates"], [MODEL])


if __name__ == "__main__":
    unittest.main()
