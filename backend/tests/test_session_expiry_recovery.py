"""Management login recovers after ordinary dashboard session traffic goes idle."""

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import Depends, FastAPI

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.coordination_service import CoordinationService
from core.identity import IdentityRecord, ManagedIdentity, ManagementPrincipal, RoleBindingRecord
from core.identity.sessions import (
    CoordinatedSessionStore,
    IssuedSession,
    SessionAuthenticationMethod,
    SessionExpired,
    SessionNotFound,
    SessionPolicy,
    SessionRecord,
    SessionService,
)
from core.panel.auth import router as auth_router
from core.panel.auth_support import AuthenticationAttemptService
from core.state_store import InMemoryStateStore
from core.utils import PANEL_SESSION_COOKIE, verify_panel_token


class SessionExpiryRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.clock = 1_000.0
        self.coordination = CoordinationService(InMemoryStateStore(clock=lambda: self.clock))
        self.sessions = CoordinatedSessionStore(
            self.coordination,
            hmac_key=b"expiry-recovery-test-key-32-bytes!",
            policy=SessionPolicy(idle_ttl_seconds=1_800, absolute_ttl_seconds=86_400),
        )
        self.owner = ManagementPrincipal.local_owner()

    async def asyncTearDown(self) -> None:
        await self.coordination.close()

    async def _login(self) -> IssuedSession:
        return await self.sessions.issue(
            principal=self.owner,
            authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
            authorization_epoch=1,
            now=self.clock,
        )

    async def _resolve(self, token: str) -> SessionRecord:
        return await self.sessions.resolve(token, current_authorization_epoch=1, now=self.clock)

    async def _dashboard_then_idle(self) -> tuple[IssuedSession, IssuedSession]:
        old = await self._login()
        # Natural resolves create operation replay records, without editing store internals.
        # All touches share a deterministic instant so their expiry forms one backlog.
        for _ in range(300):
            self.assertEqual((await self._resolve(old.token)).principal, self.owner)

        self.clock += 1_000
        unrelated_live = await self._login()
        self.clock += 801
        return old, unrelated_live

    async def test_first_login_after_idle_recovers_without_losing_live_sessions(self) -> None:
        old, unrelated_live = await self._dashboard_then_idle()

        # The same readiness primitive succeeds even when the old session path is stuck.
        clock = await self.coordination.read_coordination_time(epoch=1)
        self.assertEqual(clock.milliseconds, int(self.clock * 1_000))
        self.assertTrue(self.coordination.health_snapshot()["available"])

        # The first real login must succeed; no restart or repeated failed login is required.
        fresh = await self._login()
        self.assertEqual((await self._resolve(fresh.token)).principal, self.owner)
        self.assertEqual((await self._resolve(unrelated_live.token)).principal, self.owner)
        with self.assertRaises((SessionNotFound, SessionExpired)):
            await self._resolve(old.token)

        self.assertTrue(await self.sessions.revoke(fresh.token))
        with self.assertRaises(SessionNotFound):
            await self._resolve(fresh.token)

    async def test_revoke_as_first_operation_after_idle_does_not_bypass_revocation(self) -> None:
        old, unrelated_live = await self._dashboard_then_idle()

        # Revocation must not silently fail or be treated as success during recovery.
        self.assertTrue(await self.sessions.revoke(unrelated_live.token))
        with self.assertRaises(SessionNotFound):
            await self._resolve(unrelated_live.token)
        with self.assertRaises((SessionNotFound, SessionExpired)):
            await self._resolve(old.token)
        fresh = await self._login()
        self.assertEqual((await self._resolve(fresh.token)).principal, self.owner)

    async def test_http_login_cookie_and_logout_recover_after_dashboard_idle(self) -> None:
        identity_time = datetime(2026, 9, 19, tzinfo=timezone.utc)
        owner = ManagedIdentity(
            identity=IdentityRecord.local_owner(now=identity_time),
            binding=RoleBindingRecord.local_owner(now=identity_time),
        )
        service = SessionService(
            self.sessions,
            identity_repository=SimpleNamespace(get_identity=AsyncMock(return_value=owner)),
        )
        attempts = AuthenticationAttemptService(self.coordination, hmac_key=b"a" * 32)
        app = FastAPI()
        app.include_router(auth_router)

        @app.get("/api/credentials/status")
        async def protected_status(_token: str = Depends(verify_panel_token)) -> dict[str, bool]:
            return {"ok": True}

        def cookie_header(token: str) -> dict[str, str]:
            return {"Cookie": f"{PANEL_SESSION_COOKIE}={token}"}

        with (
            patch("core.panel.auth.config.has_password_configured", AsyncMock(return_value=True)),
            patch("core.panel.auth.verify_password", AsyncMock(return_value=True)),
            patch("core.panel.auth_support._attempt_service", attempts),
            patch("core.panel.auth.get_session_service", return_value=service),
            patch("core.utils.get_session_service", return_value=service),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                first = await client.post(
                    "/api/auth/login", json={"password": "synthetic-password"}
                )
                self.assertEqual(first.status_code, 200)
                old_token = first.cookies[PANEL_SESSION_COOKIE]
                for request_index in range(300):
                    page = await client.get("/api/credentials/status")
                    self.assertEqual(page.status_code, 200)
                    if request_index % 10 == 0:
                        await asyncio.sleep(0)

                self.clock += 1_000
                live_login = await client.post(
                    "/api/auth/login", json={"password": "synthetic-password"}
                )
                self.assertEqual(live_login.status_code, 200)
                live_token = live_login.cookies[PANEL_SESSION_COOKIE]
                self.clock += 801

                login = await client.post(
                    "/api/auth/login", json={"password": "synthetic-password"}
                )
                self.assertEqual(login.status_code, 200)
                fresh_token = login.cookies[PANEL_SESSION_COOKIE]
                self.assertNotIn(fresh_token, login.text)
                cookie = login.headers["set-cookie"]
                self.assertIn("HttpOnly", cookie)
                self.assertIn("SameSite=lax", cookie)
                self.assertIn("Path=/", cookie)

                for token, expected in ((old_token, 401), (live_token, 200), (fresh_token, 200)):
                    result = await client.get(
                        "/api/credentials/status", headers=cookie_header(token)
                    )
                    self.assertEqual(result.status_code, expected)

                logout = await client.post(
                    "/api/auth/logout",
                    headers={**cookie_header(fresh_token), "Origin": "http://test"},
                )
                self.assertEqual(logout.status_code, 200)
                self.assertIn("Max-Age=0", logout.headers["set-cookie"])
                revoked = await client.get(
                    "/api/credentials/status", headers=cookie_header(fresh_token)
                )
                self.assertEqual(revoked.status_code, 401)
                survivor = await client.get(
                    "/api/credentials/status", headers=cookie_header(live_token)
                )
                self.assertEqual(survivor.status_code, 200)


if __name__ == "__main__":
    unittest.main()
