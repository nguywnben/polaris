"""Authentication failures must not expose internal exception details."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.auth import (
    asyncio_complete_auth_flow,
    auth_flows,
    complete_auth_flow_from_callback_url,
    create_auth_url,
)
from core.models import LoginRequest, SetupRequest
from core.panel.auth import complete_setup, login, setup_status
from fastapi import HTTPException
from starlette.requests import Request


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "headers": [(b"host", b"localhost:4283")],
            "client": ("127.0.0.1", 50000),
            "server": ("localhost", 4283),
        }
    )


class AuthErrorSanitizationTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        auth_flows.clear()

    async def _assert_sanitized(self, operation, expected_detail: str) -> None:
        with patch(
            "core.panel.auth.config.has_password_configured",
            new=AsyncMock(side_effect=RuntimeError("postgresql://user:secret@database")),
        ):
            with self.assertRaises(HTTPException) as context:
                await operation()

        self.assertEqual(context.exception.status_code, 500)
        self.assertEqual(context.exception.detail, expected_detail)
        self.assertNotIn("secret", context.exception.detail)

    async def test_login_error_is_sanitized(self):
        await self._assert_sanitized(
            lambda: login(LoginRequest(password="not-used"), _request("/api/auth/login")),
            "Unable to sign in because of an internal service error.",
        )

    async def test_setup_status_error_is_sanitized(self):
        await self._assert_sanitized(
            lambda: setup_status(_request("/api/auth/setup/status")),
            "Unable to determine the initial setup status.",
        )

    async def test_setup_error_is_sanitized(self):
        await self._assert_sanitized(
            lambda: complete_setup(
                SetupRequest(password="password", confirm_password="password"),
                _request("/api/auth/setup"),
            ),
            "Unable to complete initial setup because of an internal service error.",
        )

    async def test_oauth_start_does_not_return_configuration_exception_details(self):
        with patch(
            "core.auth.get_code_assist_oauth_client_config",
            new=AsyncMock(
                side_effect=RuntimeError("client_secret=oauth-secret configuration failed")
            ),
        ):
            result = await create_auth_url(user_session="session-reference")

        self.assertFalse(result["success"])
        self.assertEqual(
            result["error"],
            "Unable to start OAuth authentication. Check the OAuth configuration and retry.",
        )
        self.assertNotIn("oauth-secret", repr(result))

    async def test_oauth_exchange_does_not_return_provider_exception_details(self):
        flow = AsyncMock()
        flow.exchange_code.side_effect = RuntimeError(
            "access_token=provider-secret exchange failed"
        )
        auth_flows["state-1"] = {
            "flow": flow,
            "project_id": "project-1",
            "user_session": "session-reference",
            "callback_port": 11451,
            "callback_url": "http://localhost:11451",
            "server": None,
            "server_thread": None,
            "code": "authorization-code",
            "completed": True,
            "created_at": 1.0,
            "auto_project_detection": False,
            "mode": "code_assist",
        }

        result = await asyncio_complete_auth_flow(
            "project-1",
            "session-reference",
        )

        self.assertFalse(result["success"])
        self.assertEqual(
            result["error"],
            "Unable to retrieve OAuth credentials. Start authentication again and retry.",
        )
        self.assertNotIn("provider-secret", repr(result))

    async def test_pasted_callback_does_not_return_provider_exception_details(self):
        flow = AsyncMock()
        flow.redirect_uri = "http://localhost:4283/callback"
        flow.exchange_code.side_effect = RuntimeError(
            "refresh_token=provider-secret exchange failed"
        )
        auth_flows["state-2"] = {
            "flow": flow,
            "project_id": "project-2",
            "user_session": "session-reference",
            "callback_port": 4283,
            "callback_url": "http://localhost:4283/callback",
            "server": None,
            "server_thread": None,
            "code": None,
            "completed": False,
            "created_at": 1.0,
            "auto_project_detection": False,
            "mode": "primary",
        }

        result = await complete_auth_flow_from_callback_url(
            "http://localhost:4283/callback?state=state-2&code=authorization-code",
            mode="primary",
        )

        self.assertFalse(result["success"])
        self.assertEqual(
            result["error"],
            "Unable to retrieve OAuth credentials. Start authentication again and retry.",
        )
        self.assertNotIn("provider-secret", repr(result))


if __name__ == "__main__":
    unittest.main()
