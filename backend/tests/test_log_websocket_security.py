"""Authentication contracts for the runtime-log WebSocket."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.websockets import WebSocketState

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import (
    AuthorizationDenied,
    ManagementPermission,
    ManagementPrincipal,
    ManagementRole,
    evaluate_permission,
)
from core.panel.logs import _websocket_origin_matches_host, websocket_logs
from core.utils import PANEL_SESSION_COOKIE


class FakeWebSocket:
    def __init__(
        self,
        *,
        cookie_token: str | None = None,
        query_token: str | None = None,
        origin: str = "http://testserver",
        host: str = "testserver",
    ):
        self.cookies = {PANEL_SESSION_COOKIE: cookie_token} if cookie_token else {}
        self.query_params = {"token": query_token} if query_token else {}
        self.headers = {"origin": origin, "host": host}
        self.close_calls = []
        self.sent_text = []
        self.client_state = WebSocketState.CONNECTED
        self.state = SimpleNamespace()

    async def close(self, **kwargs):
        self.close_calls.append(kwargs)

    async def send_text(self, value):
        self.sent_text.append(value)

    async def receive_text(self):
        raise RuntimeError("test disconnect")


class LogWebSocketSecurityTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def verified(principal: ManagementPrincipal | None = None) -> SimpleNamespace:
        return SimpleNamespace(principal=principal or ManagementPrincipal.local_owner())

    def test_websocket_origin_must_match_the_console_host(self):
        self.assertTrue(_websocket_origin_matches_host(FakeWebSocket()))
        self.assertFalse(
            _websocket_origin_matches_host(
                FakeWebSocket(origin="https://attacker.example", host="testserver")
            )
        )

    async def test_cross_origin_websocket_is_rejected(self):
        websocket = FakeWebSocket(
            cookie_token="session-token",
            origin="https://attacker.example",
        )

        await websocket_logs(websocket)

        self.assertEqual(websocket.close_calls, [{"code": 4403, "reason": "Origin not allowed"}])

    async def test_query_string_tokens_are_rejected(self):
        websocket = FakeWebSocket(query_token="legacy-query-token")

        await websocket_logs(websocket)

        self.assertEqual(len(websocket.close_calls), 1)
        self.assertEqual(websocket.close_calls[0]["code"], 4401)
        self.assertEqual(websocket.close_calls[0]["reason"], "Authentication required")

    async def test_authenticated_websocket_is_authorized_before_connecting(self):
        websocket = FakeWebSocket(cookie_token="session-token")
        principal = ManagementPrincipal.oidc_user(
            issuer="https://identity.example.com/tenant",
            subject="viewer-1",
            role=ManagementRole.VIEWER,
        )

        with (
            patch(
                "core.panel.logs.verify_panel_token_value",
                new=AsyncMock(return_value=self.verified(principal)),
            ),
            patch("core.panel.logs.require_management_route") as authorize,
            patch("core.panel.logs.manager.connect", new=AsyncMock(return_value=False)),
        ):
            await websocket_logs(websocket)

        authorize.assert_called_once()
        call = authorize.call_args
        self.assertEqual(call.kwargs["method"], "WEBSOCKET")
        self.assertEqual(call.kwargs["path"], "/api/logs/stream")
        self.assertIs(call.args[0], principal)
        self.assertIs(websocket.state.management_principal, principal)

    async def test_websocket_permission_denial_closes_before_connecting(self):
        websocket = FakeWebSocket(cookie_token="session-token")
        decision = evaluate_permission(
            ManagementPrincipal.system("background-task"),
            ManagementPermission.LOGS_READ,
        )

        with (
            patch(
                "core.panel.logs.verify_panel_token_value",
                new=AsyncMock(return_value=self.verified()),
            ),
            patch(
                "core.panel.logs.require_management_route",
                side_effect=AuthorizationDenied(decision),
            ),
            patch("core.panel.logs.manager.connect", new=AsyncMock()) as connect,
        ):
            await websocket_logs(websocket)

        self.assertEqual(
            websocket.close_calls,
            [{"code": 4403, "reason": "Management permission denied"}],
        )
        connect.assert_not_awaited()

    async def test_runtime_read_failure_does_not_expose_exception_detail(self):
        websocket = FakeWebSocket(cookie_token="session-token")

        with (
            patch(
                "core.panel.logs.verify_panel_token_value",
                new=AsyncMock(return_value=self.verified()),
            ),
            patch("core.panel.logs.require_management_route"),
            patch("core.panel.logs.manager.connect", new=AsyncMock(return_value=True)),
            patch("core.panel.logs.manager.disconnect"),
            patch(
                "core.panel.logs.asyncio.to_thread",
                new=AsyncMock(side_effect=[RuntimeError("password=do-not-expose"), 0]),
            ),
        ):
            await websocket_logs(websocket)

        self.assertEqual(websocket.sent_text, ["Error reading log file."])
        self.assertNotIn("do-not-expose", "".join(websocket.sent_text))


if __name__ == "__main__":
    unittest.main()
