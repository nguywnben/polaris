"""Google OAuth transport diagnostics never expose proxy credentials or raw errors."""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from core.google_oauth_api import _format_oauth_request_error


class GoogleOAuthErrorRedactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_proxy_credentials_and_transport_detail_never_reach_diagnostic(self):
        with patch(
            "core.google_oauth_api.get_proxy_config",
            AsyncMock(return_value="http://fixture-user:fixture-password@proxy.invalid:8080"),
        ):
            message = await _format_oauth_request_error(
                "Token refresh failed",
                "https://oauth2.googleapis.com/token",
                httpx.ConnectError("fixture-raw-secret"),
            )
        self.assertIn("https://oauth2.googleapis.com/token", message)
        self.assertIn("proxy is configured", message)
        self.assertIn("ConnectError", message)
        for secret in ("fixture-user", "fixture-password", "proxy.invalid", "fixture-raw-secret"):
            self.assertNotIn(secret, message)

    async def test_missing_or_unavailable_proxy_keeps_safe_actionable_hint(self):
        for lookup in (AsyncMock(return_value=None), AsyncMock(side_effect=RuntimeError("secret"))):
            with patch("core.google_oauth_api.get_proxy_config", lookup):
                message = await _format_oauth_request_error(
                    "Token refresh failed",
                    "https://oauth2.googleapis.com/token",
                    httpx.ReadTimeout("secret"),
                )
            self.assertIn("No outbound proxy is configured", message)
            self.assertIn("ReadTimeout", message)
            self.assertNotIn("secret", message)
