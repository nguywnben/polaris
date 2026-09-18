"""Runtime defenses for Google endpoints carrying OAuth secrets or bearer tokens."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.google_oauth_api import Credentials, TokenError, get_user_info


class GoogleOAuthRuntimeSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_rejects_untrusted_runtime_url_before_sending_secrets(self):
        credentials = Credentials(
            access_token="expired",
            refresh_token="refresh-secret",
            client_id="client",
            client_secret="client-secret",
        )
        post = AsyncMock()
        with (
            patch(
                "core.google_oauth_api.get_oauth_proxy_url",
                new=AsyncMock(return_value="https://oauth2.googleapis.com.attacker.test"),
            ),
            patch("core.google_oauth_api.post_async", new=post),
        ):
            with self.assertRaises(TokenError):
                await credentials.refresh()

        post.assert_not_awaited()

    async def test_userinfo_rejects_untrusted_runtime_url_before_sending_bearer(self):
        credentials = Credentials(access_token="bearer-secret")
        credentials.expires_at = None
        credentials.refresh_if_needed = AsyncMock(return_value=False)
        get = AsyncMock()
        with (
            patch(
                "core.google_oauth_api.get_googleapis_proxy_url",
                new=AsyncMock(return_value="https://www.googleapis.com.attacker.test"),
            ),
            patch("core.google_oauth_api.get_async", new=get),
        ):
            self.assertIsNone(await get_user_info(credentials))

        get.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
