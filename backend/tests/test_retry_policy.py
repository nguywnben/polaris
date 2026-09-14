"""Transient upstream retry policy tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.api.primary import _is_retryable_status, _no_credential_error_message
from core.api.utils import handle_error_with_retry


class RetryPolicyTests(unittest.IsolatedAsyncioTestCase):
    def test_no_credential_diagnostic_names_the_requested_model(self):
        self.assertEqual(
            _no_credential_error_message("gemini-2.5-flash"),
            "No route is currently available for model 'gemini-2.5-flash'. "
            "Check enabled credentials, model support, cooldowns, and routing settings.",
        )
        self.assertEqual(
            _no_credential_error_message(""),
            "No credential route is currently available. Check credential health and routing settings.",
        )

    def test_transient_http_statuses_are_routable_failures(self):
        for status_code in (408, 409, 429, 500, 502, 503, 504):
            with self.subTest(status_code=status_code):
                self.assertTrue(_is_retryable_status(status_code, []))

    def test_request_and_authentication_errors_are_not_retried_by_default(self):
        for status_code in (400, 401, 404, 422):
            with self.subTest(status_code=status_code):
                self.assertFalse(_is_retryable_status(status_code, []))

    async def test_transient_status_retries_when_budget_remains(self):
        manager = AsyncMock()
        with (
            patch("core.api.utils.check_should_auto_disable", AsyncMock(return_value=False)),
            patch("core.api.utils.asyncio.sleep", AsyncMock()) as sleep_mock,
        ):
            should_retry = await handle_error_with_retry(
                manager,
                502,
                "credential.json",
                True,
                0,
                2,
                0.5,
                mode="primary",
            )

        self.assertTrue(should_retry)
        sleep_mock.assert_awaited_once_with(0.5)

    async def test_non_retryable_status_does_not_consume_retry_budget(self):
        manager = AsyncMock()
        with (
            patch("core.api.utils.check_should_auto_disable", AsyncMock(return_value=False)),
            patch("core.api.utils.asyncio.sleep", AsyncMock()) as sleep_mock,
        ):
            should_retry = await handle_error_with_retry(
                manager,
                422,
                "credential.json",
                True,
                0,
                2,
                0.5,
                mode="primary",
            )

        self.assertFalse(should_retry)
        sleep_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
