"""Provider connection diagnostics stay useful without exposing upstream bodies."""

from __future__ import annotations

import asyncio
import json
import ssl
import sys
import unittest
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.provider_connection_diagnostics import (
    ConnectionTestDisconnected,
    ConnectionTestTimedOut,
    build_connection_test_failure,
    classify_provider_exception,
    classify_provider_response,
    run_bounded_connection_test,
)
from core.provider_registry import list_credential_variant_capabilities

FIXTURE_PATH = BACKEND_DIR / "tests" / "fixtures" / "provider-connection-errors-v1.json"


class ProviderConnectionDiagnosticContractTests(unittest.TestCase):
    def test_versioned_adapter_fixtures_cover_every_advertised_variant(self) -> None:
        contract = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(contract["schema_version"], 1)
        fixtures = contract["fixtures"]
        self.assertEqual(
            {fixture["variant_id"] for fixture in fixtures},
            {item["variant_id"] for item in list_credential_variant_capabilities()},
        )

        for fixture in fixtures:
            with self.subTest(variant_id=fixture["variant_id"]):
                diagnostic = classify_provider_response(
                    fixture["status_code"],
                    fixture["body"],
                )
                self.assertEqual(diagnostic.category, fixture["category"])
                self.assertEqual(diagnostic.provider_code, fixture["provider_code"])
                self.assertEqual(diagnostic.retryable, fixture["retryable"])

    def test_http_outcomes_use_stable_categories_and_safe_provider_codes(self) -> None:
        cases = (
            (401, "invalid_api_key", "credential", False),
            (403, "permission_error", "permission", False),
            (402, "insufficient_quota", "quota", False),
            (429, "rate_limit_exceeded", "rate_limit", True),
            (404, "model_not_found", "invalid_model", False),
            (501, "unsupported_operation", "unsupported_operation", False),
            (503, "overloaded_error", "upstream", True),
        )

        for status, provider_code, category, retryable in cases:
            with self.subTest(status=status, provider_code=provider_code):
                diagnostic = classify_provider_response(
                    status,
                    json.dumps(
                        {
                            "error": {
                                "code": provider_code,
                                "message": "upstream body must never be returned",
                            }
                        }
                    ),
                )

                self.assertEqual(diagnostic.category, category)
                self.assertEqual(diagnostic.provider_status, status)
                self.assertEqual(diagnostic.provider_code, provider_code)
                self.assertEqual(diagnostic.retryable, retryable)
                self.assertTrue(diagnostic.message)
                self.assertTrue(diagnostic.remediation)

    def test_untrusted_body_and_unknown_code_never_enter_the_public_contract(self) -> None:
        secret = "sk-secret-that-must-not-leak"
        diagnostic = classify_provider_response(
            400,
            json.dumps(
                {
                    "error": {
                        "code": secret,
                        "message": f"Authorization: Bearer {secret}",
                        "details": {"request": secret},
                    }
                }
            ),
        )
        payload = build_connection_test_failure(
            diagnostic,
            filename="provider.json",
            provider="openai",
            credential_type="api_key",
            model="gpt-test",
        )

        encoded = json.dumps(payload)
        self.assertNotIn(secret, encoded)
        self.assertNotIn("Authorization", encoded)
        self.assertIsNone(diagnostic.provider_code)
        self.assertEqual(payload["diagnostic"]["schema_version"], 1)
        self.assertEqual(payload["error"], diagnostic.message)
        self.assertEqual(payload["detail"], diagnostic.message)

    def test_oversized_body_is_not_parsed(self) -> None:
        body = json.dumps(
            {
                "error": {
                    "code": "invalid_api_key",
                    "message": "x" * 40_000,
                }
            }
        )

        diagnostic = classify_provider_response(401, body)

        self.assertEqual(diagnostic.category, "credential")
        self.assertIsNone(diagnostic.provider_code)

    def test_transport_exceptions_have_actionable_categories(self) -> None:
        request = httpx.Request("POST", "https://provider.example/v1/test")
        cases = (
            (httpx.ProxyError("proxy secret", request=request), "proxy"),
            (ssl.SSLError("certificate secret"), "tls"),
            (httpx.ConnectError("network secret", request=request), "network"),
            (httpx.ReadTimeout("timeout secret", request=request), "timeout"),
        )

        for error, category in cases:
            with self.subTest(category=category):
                diagnostic = classify_provider_exception(error)
                self.assertEqual(diagnostic.category, category)
                self.assertNotIn("secret", json.dumps(diagnostic.as_dict()))


class BoundedConnectionTestTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_cancels_the_provider_operation(self) -> None:
        cancelled = asyncio.Event()

        async def blocked() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with self.assertRaises(ConnectionTestTimedOut):
            await run_bounded_connection_test(blocked(), timeout_seconds=0.001)

        self.assertTrue(cancelled.is_set())

    async def test_disconnect_cancels_the_provider_operation(self) -> None:
        cancelled = asyncio.Event()

        async def blocked() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def disconnected() -> bool:
            return True

        with self.assertRaises(ConnectionTestDisconnected):
            await run_bounded_connection_test(
                blocked(),
                is_disconnected=disconnected,
                timeout_seconds=1,
                disconnect_poll_seconds=0,
            )

        self.assertTrue(cancelled.is_set())

    async def test_caller_cancellation_propagates_and_cleans_up(self) -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def blocked() -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        task = asyncio.create_task(run_bounded_connection_test(blocked(), timeout_seconds=10))
        await started.wait()
        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cancelled.is_set())


if __name__ == "__main__":
    unittest.main()
