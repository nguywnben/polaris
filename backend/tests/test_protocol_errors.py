"""Stable error contracts for the public SDK-compatible endpoints."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import httpx
import main
from core.router.protocol_errors import (
    adapt_protocol_error_response,
    protocol_error_payload,
    protocol_for_path,
)
from core.router.stream_passthrough import build_streaming_response_or_error
from fastapi import Response


class ProtocolErrorUnitTests(unittest.IsolatedAsyncioTestCase):
    def test_retry_after_is_validated_not_an_arbitrary_upstream_string(self):
        for value, expected in (
            ("37", "37"),
            ("Fri, 18 Sep 2026 10:00:00 GMT", "Fri, 18 Sep 2026 10:00:00 GMT"),
            ("secret-provider-token", None),
            ("-1", None),
            ("9" * 200, None),
        ):
            with self.subTest(value=value):
                result = adapt_protocol_error_response(
                    Response("{}", status_code=429, headers={"Retry-After": value}), "openai"
                )
                self.assertEqual(result.headers.get("retry-after"), expected)

    def test_paths_map_to_their_sdk_protocol(self):
        self.assertEqual(protocol_for_path("/v1/chat/completions"), "openai")
        self.assertEqual(protocol_for_path("/v1/responses"), "openai")
        self.assertEqual(protocol_for_path("/v1/messages"), "anthropic")
        self.assertEqual(protocol_for_path("/v1beta/models/gemini:generateContent"), "gemini")
        self.assertEqual(protocol_for_path("/vertex/v1beta/models"), "gemini")
        self.assertEqual(protocol_for_path("/vertex/v1/models"), "openai")
        self.assertIsNone(protocol_for_path("/api/config/get"))

    def test_protocol_payloads_match_documented_envelopes(self):
        openai = protocol_error_payload("openai", 401, "Invalid API key.")
        anthropic = protocol_error_payload("anthropic", 429, "Try again later.")
        gemini = protocol_error_payload("gemini", 503, "No credentials are available.")

        self.assertEqual(openai["error"]["type"], "authentication_error")
        self.assertEqual(openai["error"]["code"], "invalid_api_key")
        self.assertEqual(anthropic["type"], "error")
        self.assertEqual(anthropic["error"]["type"], "rate_limit_error")
        self.assertEqual(gemini["error"]["status"], "UNAVAILABLE")

    def test_upstream_errors_are_redacted_and_keep_retry_guidance(self):
        response = Response(
            content=json.dumps({"error": "API key sk-polaris-secret-value is unavailable."}),
            status_code=503,
            media_type="application/json",
            headers={"Retry-After": "5", "X-Unsafe-Upstream": "discard"},
        )

        adapted = adapt_protocol_error_response(response, "openai")
        payload = json.loads(adapted.body)

        self.assertEqual(adapted.status_code, 503)
        self.assertEqual(adapted.headers["retry-after"], "5")
        self.assertNotIn("x-unsafe-upstream", adapted.headers)
        self.assertNotIn("secret-value", payload["error"]["message"])

    async def test_stream_prefetch_adapts_an_error_before_committing_success(self):
        async def generator():
            yield Response(
                content=json.dumps({"error": "No credentials are available."}),
                status_code=503,
                media_type="application/json",
            )

        response = await build_streaming_response_or_error(generator(), error_protocol="anthropic")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["type"], "error")
        self.assertEqual(payload["error"]["type"], "overloaded_error")


class ProtocolErrorIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app),
            base_url="http://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_missing_authentication_uses_each_sdk_error_contract(self):
        requests = (
            (
                "/v1/chat/completions",
                {"model": "polaris", "messages": [{"role": "user", "content": "Hi"}]},
                "openai",
            ),
            (
                "/v1/messages",
                {
                    "model": "polaris",
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                "anthropic",
            ),
            (
                "/v1beta/models/polaris:generateContent",
                {"contents": [{"role": "user", "parts": [{"text": "Hi"}]}]},
                "gemini",
            ),
        )

        for path, body, protocol in requests:
            with self.subTest(protocol=protocol):
                response = await self.client.post(path, json=body)
                payload = response.json()
                self.assertEqual(response.status_code, 401)
                self.assertTrue(response.headers.get("x-request-id"))
                if protocol == "openai":
                    self.assertEqual(payload["error"]["type"], "authentication_error")
                elif protocol == "anthropic":
                    self.assertEqual(payload["type"], "error")
                    self.assertEqual(payload["error"]["type"], "authentication_error")
                else:
                    self.assertEqual(payload["error"]["status"], "UNAUTHENTICATED")

    async def test_request_ids_are_bounded_and_echoed_when_safe(self):
        accepted = await self.client.get("/health", headers={"X-Request-ID": "client-123"})
        replaced = await self.client.get("/health", headers={"X-Request-ID": "not safe/value"})

        self.assertEqual(accepted.headers["x-request-id"], "client-123")
        self.assertNotEqual(replaced.headers["x-request-id"], "not safe/value")
        self.assertEqual(len(replaced.headers["x-request-id"]), 32)

    async def test_invalid_payloads_use_protocol_errors_and_http_400(self):
        with patch("config.get_api_key", new=AsyncMock(return_value="sk-polaris-test-key")):
            openai = await self.client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer sk-polaris-test-key"},
                json={"model": "polaris"},
            )
            anthropic = await self.client.post(
                "/v1/messages",
                headers={"x-api-key": "sk-polaris-test-key"},
                json={"model": "polaris", "messages": []},
            )
            gemini = await self.client.post(
                "/v1beta/models/polaris:generateContent",
                headers={"x-goog-api-key": "sk-polaris-test-key"},
                json={},
            )

        for response in (openai, anthropic, gemini):
            self.assertEqual(response.status_code, 400)
        self.assertEqual(openai.json()["error"]["type"], "invalid_request_error")
        self.assertEqual(anthropic.json()["error"]["type"], "invalid_request_error")
        self.assertEqual(gemini.json()["error"]["status"], "INVALID_ARGUMENT")

    async def test_count_tokens_rejects_malformed_json_without_parser_details(self):
        with patch("config.get_api_key", new=AsyncMock(return_value="sk-polaris-test-key")):
            responses = (
                await self.client.post(
                    "/v1beta/models/polaris:countTokens",
                    headers={
                        "content-type": "application/json",
                        "x-goog-api-key": "sk-polaris-test-key",
                    },
                    content=b"{invalid",
                ),
                await self.client.post(
                    "/vertex/v1beta/models/polaris:countTokens",
                    headers={
                        "content-type": "application/json",
                        "x-goog-api-key": "sk-polaris-test-key",
                    },
                    content=b"{invalid",
                ),
            )

        for response in responses:
            with self.subTest(path=response.request.url.path):
                self.assertEqual(response.status_code, 400)
                payload = response.json()["error"]
                self.assertEqual(payload["status"], "INVALID_ARGUMENT")
                self.assertEqual(payload["message"], "The request body must contain valid JSON.")


if __name__ == "__main__":
    unittest.main()
