"""Manual Muse device completion with real encrypted coordinator fixtures."""

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import muse_device_login as login
from core.device_authorization_coordination import (
    DeviceAuthorizationService,
    configure_device_authorization_service,
)
from core.muse_oauth import MuseOAuthError
from core.state_store import InMemoryStateStore


class MuseDeviceLoginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = DeviceAuthorizationService(
            InMemoryStateStore(), key=b"m" * 32, fencing_epoch=1
        )
        configure_device_authorization_service(self.service)
        self.stack = []
        for target, value in (
            (
                "start_device_authorization",
                {
                    "device_code": "device-secret",
                    "user_code": "ABCD-EFGH",
                    "verification_uri_complete": "https://auth.meta.com/oauth/device/?code=ABCD-EFGH",
                    "expires_in": 600,
                    "interval": 5,
                },
            ),
            ("exchange_device_token", {"access_token": "oauth-secret"}),
            ("discover_minted_models", ["muse-code/muse-spark-1.3"]),
            (
                "mint_key",
                {
                    "provider": "muse_code",
                    "credential_type": "oauth",
                    "access_token": "oauth-secret",
                    "api_key": "key-secret",
                    "account_id": "a" * 64,
                },
            ),
            (
                "store_extended_credential",
                {"filename": "muse_code-account.json", "action": "created"},
            ),
        ):
            mocked = AsyncMock(return_value=value)
            self.stack.append(patch.object(login, target, mocked))
            self.stack[-1].start()
            setattr(self, target, mocked)
        self.clock = patch.object(login.time, "time", return_value=time.time())
        self.now = self.clock.start()

    def tearDown(self):
        self.clock.stop()
        for patcher in reversed(self.stack):
            patcher.stop()
        configure_device_authorization_service(None)

    async def start(self):
        started = await login.start_login("owner-session", credential_label="My Muse")
        self.now.return_value += 10
        return started["flow_id"]

    async def test_start_never_exchanges_or_returns_device_secret(self):
        result = await login.start_login("owner-session")
        self.assertTrue(result["flow_id"].startswith("muse_code_"))
        self.assertNotIn("secret", json.dumps(result))
        self.exchange_device_token.assert_not_awaited()
        self.store_extended_credential.assert_not_awaited()

    async def test_owner_binding_and_complete_once_without_secret_output(self):
        flow = await self.start()
        with self.assertRaises(MuseOAuthError):
            await login.complete_login("other-session", flow)
        result = await login.complete_login("owner-session", flow)
        self.assertTrue(result["credential_saved"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertEqual(
            self.store_extended_credential.call_args.args[0]["credential_label"], "My Muse"
        )
        with self.assertRaises(MuseOAuthError):
            await login.complete_login("owner-session", flow)
        self.store_extended_credential.assert_awaited_once()

    async def test_no_automatic_poll_and_slow_down_is_retained(self):
        result = await login.start_login("owner-session")
        flow = result["flow_id"]
        self.assertEqual((await login.complete_login("owner-session", flow))["status"], "pending")
        self.exchange_device_token.assert_not_awaited()
        self.now.return_value += 10
        self.exchange_device_token.side_effect = MuseOAuthError("Wait.", 400, "slow_down")
        self.assertEqual((await login.complete_login("owner-session", flow))["interval"], 10)
        await login.complete_login("owner-session", flow)
        self.exchange_device_token.assert_awaited_once()

    async def test_mint_retry_never_reexchanges_consumed_device_grant(self):
        flow = await self.start()
        self.mint_key.side_effect = [MuseOAuthError("Unavailable."), self.mint_key.return_value]
        with self.assertRaises(MuseOAuthError):
            await login.complete_login("owner-session", flow)
        self.now.return_value += 10
        self.assertTrue((await login.complete_login("owner-session", flow))["credential_saved"])
        self.exchange_device_token.assert_awaited_once()

    async def test_storage_retry_preserves_minted_credential(self):
        flow = await self.start()
        self.store_extended_credential.side_effect = [
            RuntimeError("storage failure"),
            self.store_extended_credential.return_value,
        ]
        with self.assertRaises(RuntimeError):
            await login.complete_login("owner-session", flow)
        self.now.return_value += 10
        self.assertTrue((await login.complete_login("owner-session", flow))["credential_saved"])
        self.exchange_device_token.assert_awaited_once()
        self.mint_key.assert_awaited_once()

    async def test_denied_expired_or_subscription_failure_consumes_flow(self):
        for code in ("access_denied", "expired_token", "subscription_required"):
            flow = await self.start()
            self.exchange_device_token.side_effect = MuseOAuthError("Stopped.", 400, code)
            with self.assertRaises(MuseOAuthError):
                await login.complete_login("owner-session", flow)
            with self.assertRaises(MuseOAuthError):
                await login.cancel_login("owner-session", flow)
            self.exchange_device_token.side_effect = None

    async def test_concurrent_save_and_cancel_cannot_steal_lease(self):
        flow = await self.start()
        entered, release = asyncio.Event(), asyncio.Event()

        async def exchange(*args):
            entered.set()
            await release.wait()
            return {"access_token": "oauth-secret"}

        self.exchange_device_token.side_effect = exchange
        first = asyncio.create_task(login.complete_login("owner-session", flow))
        await asyncio.wait_for(entered.wait(), timeout=2)
        try:
            with self.assertRaises(MuseOAuthError):
                await login.complete_login("owner-session", flow)
            with self.assertRaises(MuseOAuthError):
                await login.cancel_login("owner-session", flow)
        finally:
            release.set()
        self.assertTrue((await first)["credential_saved"])
        self.store_extended_credential.assert_awaited_once()

    async def test_cancel_and_cross_provider_flows_fail_closed(self):
        flow = await self.start()
        await login.cancel_login("owner-session", flow)
        with self.assertRaises(MuseOAuthError):
            await login.complete_login("owner-session", flow)
        kiro = await self.service.create(b"{}", ttl_seconds=600, provider="kiro")
        with self.assertRaises(MuseOAuthError):
            await login.complete_login("owner-session", kiro)

    async def test_lease_deadline_uses_coordinator_clock_not_wall_epoch(self):
        flow = await self.start()
        claim = await self.service.claim(flow, lease_seconds=60, provider="muse_code")
        seconds = await self.service.lease_remaining_seconds(claim)
        self.assertGreater(seconds, 55)
        self.assertLessEqual(seconds, 60)
        await self.service.release(claim)
