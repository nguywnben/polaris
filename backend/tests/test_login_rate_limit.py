"""Atomic, privacy-preserving authentication admission tests."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel import auth_support
from core.panel.auth_support import AuthenticationAttemptService
from core.security_coordination import SecurityAttemptCategory
from core.state_store import InMemoryStateStore


class AuthenticationAttemptCoordinationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = 1_000.0
        self.backend = InMemoryStateStore(clock=lambda: self.now)
        self.service = AuthenticationAttemptService(
            self.backend,
            hmac_key=b"a" * 32,
        )
        self.previous = auth_support.set_authentication_attempt_service_for_testing(self.service)

    def tearDown(self) -> None:
        auth_support.set_authentication_attempt_service_for_testing(self.previous)

    async def test_concurrent_login_admission_enforces_one_atomic_threshold(self) -> None:
        with patch.object(auth_support, "LOGIN_MAX_ATTEMPTS", 3):
            results = await asyncio.gather(
                *(auth_support._assert_login_allowed("198.51.100.8") for _ in range(8)),
                return_exceptions=True,
            )

        self.assertEqual(sum(result is None for result in results), 3)
        denials = [result for result in results if isinstance(result, HTTPException)]
        self.assertEqual(len(denials), 5)
        self.assertTrue(all(result.status_code == 429 for result in denials))
        self.assertTrue(all(int(result.headers["Retry-After"]) > 0 for result in denials))

    async def test_every_category_has_an_independent_concurrent_threshold(self) -> None:
        for category in SecurityAttemptCategory:
            with self.subTest(category=category):
                backend = InMemoryStateStore(clock=lambda: self.now)
                service = AuthenticationAttemptService(backend, hmac_key=b"b" * 32)
                results = await asyncio.gather(
                    *(
                        service.reserve(
                            category,
                            "shared-client",
                            limit=2,
                            window_seconds=300,
                        )
                        for _ in range(6)
                    ),
                    return_exceptions=True,
                )
                self.assertEqual(sum(result is None for result in results), 2)
                self.assertEqual(
                    sum(isinstance(result, HTTPException) for result in results),
                    4,
                )

    async def test_client_identity_is_hmac_indexed_and_categories_are_isolated(self) -> None:
        raw_identity = "sensitive-client-address"
        with (
            patch.object(auth_support, "LOGIN_MAX_ATTEMPTS", 1),
            patch.object(auth_support, "RECOVERY_MAX_ATTEMPTS", 1),
        ):
            await auth_support._assert_login_allowed(raw_identity)
            await auth_support._assert_recovery_allowed(raw_identity)

        rendered = repr(self.backend._security_attempts)
        self.assertNotIn(raw_identity, rendered)
        self.assertEqual(
            len(self.backend._security_attempts[SecurityAttemptCategory.LOGIN]),
            1,
        )
        self.assertEqual(
            len(self.backend._security_attempts[SecurityAttemptCategory.RECOVERY]),
            1,
        )

    async def test_success_clear_and_expiry_restore_admission(self) -> None:
        with patch.object(auth_support, "LOGIN_MAX_ATTEMPTS", 1):
            await auth_support._assert_login_allowed("client")
            with self.assertRaises(HTTPException):
                await auth_support._assert_login_allowed("client")
            await auth_support._clear_login_failures("client")
            await auth_support._assert_login_allowed("client")
            self.now += auth_support.LOGIN_WINDOW_SECONDS + 1
            await auth_support._assert_login_allowed("client")

    async def test_oidc_start_is_admitted_before_transaction_allocation(self) -> None:
        with patch.object(auth_support, "OIDC_START_MAX_ATTEMPTS", 2):
            await auth_support._assert_and_record_oidc_start("client")
            await auth_support._assert_and_record_oidc_start("client")
            with self.assertRaises(HTTPException) as blocked:
                await auth_support._assert_and_record_oidc_start("client")

        self.assertEqual(blocked.exception.status_code, 429)
        self.assertIn("Retry-After", blocked.exception.headers)

    async def test_coordination_outage_fails_closed_without_client_disclosure(self) -> None:
        await self.backend.close()
        with self.assertRaises(HTTPException) as blocked:
            await auth_support._assert_login_allowed("private-client")

        self.assertEqual(blocked.exception.status_code, 503)
        self.assertNotIn("private-client", str(blocked.exception.detail))


if __name__ == "__main__":
    unittest.main()
