"""Kiro device grants remain server-side and bound to their initiating session."""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.device_authorization_coordination import (
    DeviceAuthorizationService,
    configure_device_authorization_service,
)
from core.state_store import InMemoryStateStore


class KiroDeviceLoginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = DeviceAuthorizationService(
            InMemoryStateStore(), key=b"x" * 32, fencing_epoch=1
        )
        configure_device_authorization_service(self.service)
        self.device = {
            "deviceCode": "secret-device",
            "userCode": "ABCD-EFGH",
            "verificationUriComplete": "https://app.kiro.dev/device?user_code=ABCD-EFGH",
            "expiresInMilliseconds": 300000,
            "intervalInMilliseconds": 5000,
        }

    def tearDown(self):
        configure_device_authorization_service(None)

    async def start(self):
        from core.kiro_device_login import start_login

        with patch(
            "core.kiro_device_login.auth_request", AsyncMock(return_value=(200, self.device))
        ):
            return await start_login("session-one", method="google")

    async def test_social_completion_owner_binding_replay_and_no_secret_return(self):
        from core.kiro import KiroError
        from core.kiro_device_login import poll_login

        started = await self.start()
        self.assertNotIn("secret-device", json.dumps(started))
        with self.assertRaises(KiroError):
            await poll_login("session-two", started["flow_id"])
        with (
            patch("core.kiro_device_login.time.time", return_value=9999999999),
            patch(
                "core.kiro_device_login.auth_request",
                AsyncMock(
                    return_value=(
                        200,
                        {
                            "accessToken": "access-secret",
                            "refreshToken": "refresh-secret",
                            "expiresIn": 3600,
                        },
                    )
                ),
            ),
            patch(
                "core.kiro_device_login.store_extended_credential",
                AsyncMock(return_value={"filename": "kiro.json", "action": "created"}),
            ) as save,
        ):
            result = await poll_login("session-one", started["flow_id"])
            self.assertTrue(result["credential_saved"])
            self.assertNotIn("secret", json.dumps(result))
            self.assertEqual(save.call_args.args[0]["credential_type"], "oauth")
            with self.assertRaises(KiroError):
                await poll_login("session-one", started["flow_id"])
            self.assertEqual(save.await_count, 1)

    async def test_pending_throttle_slowdown_and_cancel(self):
        from core.kiro import KiroError
        from core.kiro_device_login import cancel_login, poll_login

        started = await self.start()
        with patch("core.kiro_device_login.auth_request", AsyncMock()) as network:
            result = await poll_login("session-one", started["flow_id"])
            self.assertEqual(result["status"], "pending")
            network.assert_not_awaited()
        with (
            patch("core.kiro_device_login.time.time", return_value=9999999999),
            patch(
                "core.kiro_device_login.auth_request",
                AsyncMock(return_value=(400, {"error": "slow_down"})),
            ),
        ):
            result = await poll_login("session-one", started["flow_id"])
            self.assertEqual(result["interval"], 10)
        await cancel_login("session-one", started["flow_id"])
        with self.assertRaises(KiroError):
            await poll_login("session-one", started["flow_id"])

    async def test_rejects_untrusted_verification_url(self):
        from core.kiro import KiroError

        self.device["verificationUriComplete"] = "https://evil.example/steal"
        with self.assertRaises(KiroError):
            await self.start()

    async def test_storage_failure_retries_without_exchanging_grant_twice(self):
        from core.kiro_device_login import poll_login

        started = await self.start()
        with (
            patch("core.kiro_device_login.time.time", return_value=9999999999),
            patch(
                "core.kiro_device_login.auth_request",
                AsyncMock(
                    return_value=(
                        200,
                        {"accessToken": "synthetic-access", "refreshToken": "synthetic-refresh"},
                    )
                ),
            ) as network,
            patch(
                "core.kiro_device_login.store_extended_credential",
                AsyncMock(
                    side_effect=[
                        RuntimeError("storage unavailable"),
                        {"filename": "kiro.json", "action": "created"},
                    ]
                ),
            ) as save,
        ):
            with self.assertRaises(RuntimeError):
                await poll_login("session-one", started["flow_id"])
            result = await poll_login("session-one", started["flow_id"])
            self.assertTrue(result["credential_saved"])
            network.assert_awaited_once()
            self.assertEqual(save.await_count, 2)

    async def test_concurrent_completion_saves_once(self):
        from core.kiro import KiroError
        from core.kiro_device_login import poll_login

        started = await self.start()
        entered, release = asyncio.Event(), asyncio.Event()

        async def exchange(*args):
            entered.set()
            await release.wait()
            return 200, {"accessToken": "access", "refreshToken": "refresh"}

        with (
            patch("core.kiro_device_login.time.time", return_value=9999999999),
            patch("core.kiro_device_login.auth_request", side_effect=exchange),
            patch(
                "core.kiro_device_login.store_extended_credential",
                AsyncMock(return_value={"filename": "kiro.json", "action": "created"}),
            ) as save,
        ):
            first = asyncio.create_task(poll_login("session-one", started["flow_id"]))
            await entered.wait()
            try:
                with self.assertRaises(KiroError):
                    await poll_login("session-one", started["flow_id"])
            finally:
                release.set()
                await first
            save.assert_awaited_once()

    async def test_denied_grant_is_consumed_but_transient_error_is_retryable(self):
        from core.kiro import KiroError
        from core.kiro_device_login import poll_login

        for status in (403, 503):
            started = await self.start()
            with (
                patch("core.kiro_device_login.time.time", return_value=9999999999),
                patch(
                    "core.kiro_device_login.auth_request",
                    AsyncMock(return_value=(status, {"error": "denied"})),
                ),
            ):
                with self.assertRaises(KiroError):
                    await poll_login("session-one", started["flow_id"])
            if status == 403:
                with self.assertRaises(KiroError):
                    await poll_login("session-one", started["flow_id"])
            else:
                self.assertEqual(
                    (await poll_login("session-one", started["flow_id"]))["status"], "pending"
                )

    async def test_expired_grant_never_calls_vendor_or_storage(self):
        from core.kiro import KiroError
        from core.kiro_device_login import poll_login

        now = [1000.0]
        self.service = DeviceAuthorizationService(
            InMemoryStateStore(clock=lambda: now[0]), key=b"x" * 32, fencing_epoch=1
        )
        configure_device_authorization_service(self.service)
        started = await self.start()
        now[0] += 301
        with patch("core.kiro_device_login.auth_request", AsyncMock()) as network:
            with self.assertRaises(KiroError):
                await poll_login("session-one", started["flow_id"])
            network.assert_not_awaited()

    async def test_builder_id_registers_client_and_keeps_secret_server_side(self):
        from core.kiro_device_login import start_login

        device = {
            "deviceCode": "secret",
            "userCode": "CODE",
            "expiresIn": 600,
            "verificationUriComplete": "https://view.awsapps.com/start/#/device",
        }
        with patch(
            "core.kiro_device_login.auth_request",
            AsyncMock(
                side_effect=[
                    (200, {"clientId": "client", "clientSecret": "secret-client"}),
                    (200, device),
                ]
            ),
        ) as network:
            result = await start_login("session", method="builder-id", token_region="eu-west-1")
            self.assertEqual(
                network.call_args_list[0].args[0],
                "https://oidc.eu-west-1.amazonaws.com/client/register",
            )
            self.assertNotIn("secret-client", json.dumps(result))

    async def test_invalid_enterprise_start_never_calls_network(self):
        from core.kiro import KiroError
        from core.kiro_device_login import start_login

        with patch("core.kiro_device_login.auth_request", AsyncMock()) as network:
            for url in [
                "http://tenant.awsapps.com/start",
                "https://evil.example/start",
                "https://user:pass@tenant.awsapps.com/start",
            ]:
                with self.assertRaises(KiroError):
                    await start_login("session", method="identity-center", start_url=url)
            network.assert_not_awaited()
