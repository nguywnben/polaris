"""Provider OAuth flow state must never disclose a management session capability."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.auth import (
    asyncio_complete_auth_flow,
    auth_flows,
    complete_auth_flow_from_callback_url,
    create_auth_url,
    get_auth_status,
)


class ProviderOAuthSessionIsolationTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        auth_flows.clear()

    async def test_external_oauth_state_is_independent_from_internal_session_reference(self):
        flow = MagicMock()
        flow.get_auth_url.side_effect = lambda *, state: (
            f"https://issuer.example/auth?state={state}"
        )
        session_reference = "a" * 64

        with (
            patch(
                "core.auth.get_antigravity_oauth_client_config",
                new=AsyncMock(return_value=("client-id", "client-secret")),
            ),
            patch("core.auth.get_server_port", new=AsyncMock(return_value=4283)),
            patch("core.auth.Flow", return_value=flow),
        ):
            result = await create_auth_url(
                "project-1",
                session_reference,
                mode="primary",
            )

        self.assertTrue(result["success"])
        self.assertNotIn(session_reference, result["state"])
        self.assertNotIn(session_reference, result["auth_url"])
        self.assertEqual(auth_flows[result["state"]]["user_session"], session_reference)

    async def test_explicit_project_completion_cannot_consume_another_session_flow(self):
        flow = MagicMock()
        flow.exchange_code = AsyncMock()
        auth_flows["private-state"] = {
            "flow": flow,
            "project_id": "shared-project",
            "user_session": "owner-session-reference",
            "callback_port": 4283,
            "callback_url": "http://localhost:4283/callback",
            "server": None,
            "server_thread": None,
            "code": "authorization-code",
            "completed": True,
            "created_at": 1.0,
            "auto_project_detection": False,
            "mode": "primary",
        }

        result = await asyncio_complete_auth_flow(
            "shared-project",
            "different-session-reference",
            mode="primary",
        )

        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"].lower())
        flow.exchange_code.assert_not_awaited()

    def test_project_status_does_not_disclose_another_session_state(self):
        auth_flows["private-state"] = {
            "project_id": "shared-project",
            "user_session": "owner-session-reference",
            "completed": False,
            "created_at": 1.0,
        }

        self.assertEqual(
            get_auth_status("shared-project", "different-session-reference"),
            {"status": "not_found"},
        )
        self.assertEqual(
            get_auth_status("shared-project", "owner-session-reference")["state"],
            "private-state",
        )

    async def test_pasted_callback_cannot_consume_another_session_flow(self):
        flow = MagicMock()
        flow.redirect_uri = "http://localhost:4283/callback"
        flow.exchange_code = AsyncMock()
        auth_flows["private-state"] = {
            "flow": flow,
            "project_id": "shared-project",
            "user_session": "owner-session-reference",
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
            "http://localhost:4283/callback?state=private-state&code=authorization-code",
            mode="primary",
            user_session="different-session-reference",
        )

        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"].lower())
        flow.exchange_code.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
