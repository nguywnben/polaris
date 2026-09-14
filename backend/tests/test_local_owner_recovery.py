"""Local-owner break-glass recovery remains isolated, bounded, and auditable."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.management_audit import classify_management_mutation, record_management_response
from core.models import RecoveryRequest
from core.panel import auth_support
from core.panel.auth import recover_local_owner
from core.panel.auth_support import AuthenticationAttemptService
from core.security_coordination import SecurityAttemptCategory
from core.state_store import InMemoryStateStore
from fastapi import HTTPException
from starlette.requests import Request


def recovery_request(*, client: str = "127.0.0.1", host: str = "localhost:4283") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/auth/recovery",
            "headers": [(b"host", host.encode("ascii"))],
            "client": (client, 50_000),
            "server": ("localhost", 4283),
        }
    )


class LocalOwnerRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.backend = InMemoryStateStore()
        self.attempt_service = AuthenticationAttemptService(
            self.backend,
            hmac_key=b"r" * 32,
        )
        self.previous_attempt_service = auth_support.set_authentication_attempt_service_for_testing(
            self.attempt_service
        )

    def tearDown(self):
        auth_support.set_authentication_attempt_service_for_testing(self.previous_attempt_service)

    async def test_success_issues_opaque_cookie_without_reflecting_or_retaining_secret(self):
        secret = "break-glass-password"
        payload = RecoveryRequest(password=secret)
        self.assertNotIn(secret, repr(payload))

        with (
            patch(
                "core.panel.auth.config.has_password_configured", new=AsyncMock(return_value=True)
            ),
            patch("core.panel.auth.verify_password", new=AsyncMock(return_value=True)),
            patch(
                "core.panel.auth.create_panel_session_token",
                new=AsyncMock(return_value="ogs_" + "A" * 43),
            ),
        ):
            response = await recover_local_owner(payload, recovery_request())

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(secret, response.body.decode())
        self.assertIn("panel_session=ogs_", response.headers["set-cookie"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertEqual(
            self.backend._security_attempts[SecurityAttemptCategory.RECOVERY],
            {},
        )

    async def test_recovery_has_an_independent_rate_window_from_normal_login(self):
        client = "127.0.0.1"
        for _attempt in range(auth_support.LOGIN_MAX_ATTEMPTS):
            await auth_support._assert_login_allowed(client)
        with (
            patch(
                "core.panel.auth.config.has_password_configured", new=AsyncMock(return_value=True)
            ),
            patch("core.panel.auth.verify_password", new=AsyncMock(return_value=False)),
            self.assertRaises(HTTPException) as first,
        ):
            await recover_local_owner(
                RecoveryRequest(password="incorrect-password"),
                recovery_request(),
            )
        self.assertEqual(first.exception.status_code, 401)
        self.assertEqual(
            len(self.backend._security_attempts[SecurityAttemptCategory.RECOVERY]),
            1,
        )

        for _attempt in range(auth_support.RECOVERY_MAX_ATTEMPTS - 1):
            await auth_support._assert_recovery_allowed(client)
        with (
            patch(
                "core.panel.auth.config.has_password_configured", new=AsyncMock(return_value=True)
            ),
            self.assertRaises(HTTPException) as blocked,
        ):
            await recover_local_owner(
                RecoveryRequest(password="not-checked"),
                recovery_request(),
            )
        self.assertEqual(blocked.exception.status_code, 429)

    async def test_optional_local_only_policy_checks_direct_host_and_peer(self):
        with (
            patch.dict(os.environ, {"PANEL_RECOVERY_LOCAL_ONLY": "true"}),
            patch(
                "core.panel.auth.config.has_password_configured", new=AsyncMock(return_value=True)
            ),
            patch("core.panel.auth.verify_password", new=AsyncMock()) as verify,
            self.assertRaises(HTTPException) as denied,
        ):
            await recover_local_owner(
                RecoveryRequest(password="not-checked"),
                recovery_request(client="198.51.100.10", host="gateway.example"),
            )
        self.assertEqual(denied.exception.status_code, 403)
        verify.assert_not_awaited()

    async def test_recovery_action_has_bounded_unauthenticated_audit_evidence(self):
        mutation = classify_management_mutation("POST", "/api/auth/recovery")
        self.assertEqual(
            (mutation.action, mutation.target_type, mutation.change_codes),
            ("auth.recovery", "session", ("created",)),
        )
        service = AsyncMock()
        service.record.return_value = SimpleNamespace()
        with patch("core.audit_service.get_audit_service", return_value=service):
            await record_management_response(
                method="POST",
                path="/api/auth/recovery",
                status_code=429,
                request_id="recovery-rate-limited",
            )
        kwargs = service.record.await_args.kwargs
        self.assertEqual(kwargs["outcome"], "denied")
        self.assertEqual(kwargs["actor_type"], "system")
        self.assertEqual(kwargs["actor_identifier"], "unauthenticated-control-plane")
        self.assertNotIn("password", json.dumps(kwargs))


if __name__ == "__main__":
    unittest.main()
