"""Kiro portal callbacks are PKCE-protected, owner-bound and one-use."""

import base64
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.device_authorization_coordination import (
    DeviceAuthorizationService,
    configure_device_authorization_service,
)
from core.state_store import InMemoryStateStore


class KiroBrowserLoginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = DeviceAuthorizationService(
            InMemoryStateStore(), key=b"x" * 32, fencing_epoch=1
        )
        configure_device_authorization_service(self.service)

    def tearDown(self):
        configure_device_authorization_service(None)

    async def start(self):
        from core.kiro_browser_login import start_login

        return await start_login("owner", callback_origin="http://localhost:4283")

    def callback(self, started, **params):
        return "http://localhost:4283/oauth/callback?" + urlencode(
            {
                "state": started["flow_id"],
                "login_option": "google",
                "code": "synthetic-code",
                **params,
            }
        )

    async def test_pkce_callback_and_owner_completion(self):
        from core.kiro_browser_login import accept_callback, complete_login

        started = await self.start()
        query = parse_qs(urlsplit(started["authorization_url"]).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["redirect_uri"], ["http://localhost:4283"])
        self.assertNotIn("code_verifier", json.dumps(started))
        self.assertEqual((await complete_login("owner", started["flow_id"]))["status"], "pending")
        await accept_callback(self.callback(started))
        with self.assertRaises(ValueError):
            await complete_login("other-owner", started["flow_id"])
        with (
            patch(
                "core.kiro_browser_login.auth_request",
                AsyncMock(
                    return_value=(
                        200,
                        {
                            "data": {
                                "accessToken": "access",
                                "refreshToken": "refresh",
                                "expiresIn": 3600,
                            }
                        },
                    )
                ),
            ) as exchange,
            patch(
                "core.kiro_browser_login.store_extended_credential",
                AsyncMock(return_value={"filename": "kiro.json", "action": "created"}),
            ) as save,
        ):
            result = await complete_login("owner", started["flow_id"])
            self.assertTrue(result["credential_saved"])
            self.assertEqual(result["credential_action"], "created")
            self.assertNotIn("refresh", json.dumps(result))
            body = exchange.call_args.args[1]
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(body["code_verifier"].encode()).digest())
                .rstrip(b"=")
                .decode()
            )
            self.assertEqual(query["code_challenge"], [challenge])
            self.assertEqual(
                body["redirect_uri"], "http://localhost:4283/oauth/callback?login_option=google"
            )
            self.assertEqual(save.call_args.args[0]["auth_method"], "social")
            with self.assertRaises(ValueError):
                await complete_login("owner", started["flow_id"])

    async def test_rejects_redirects_duplicate_parameters_and_cross_origin(self):
        from core.kiro_browser_login import accept_callback, start_login

        for origin in (
            "http://evil.example",
            "http://localhost:4283/path",
            "http://localhost:4283@evil.example",
            "http://localhost:4283?x=1",
        ):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                await start_login("owner", callback_origin=origin)
        started = await self.start()
        for callback in (
            self.callback(started).replace("localhost", "evil.example"),
            self.callback(started) + "&state=other",
            self.callback(started).replace("/oauth/callback", "/other"),
            self.callback(started).replace(":4283", ":4284"),
            self.callback(started) + "&loginOption=github",
            self.callback(started) + "#fragment",
        ):
            with self.subTest(callback=callback), self.assertRaises(ValueError):
                await accept_callback(callback)

    async def test_cancel_and_unsupported_portal_method(self):
        from core.kiro_browser_login import accept_callback, cancel_login, complete_login

        started = await self.start()
        await accept_callback(self.callback(started, login_option="builderid", code=""))
        self.assertEqual(
            (await complete_login("owner", started["flow_id"]))["reason"], "unsupported_method"
        )
        started = await self.start()
        await cancel_login("owner", started["flow_id"])
        with self.assertRaises(ValueError):
            await accept_callback(self.callback(started))

    async def test_device_endpoint_cannot_consume_browser_flow(self):
        from core.kiro_browser_login import complete_login
        from core.kiro_device_login import cancel_login, poll_login

        started = await self.start()
        for operation in (poll_login, cancel_login):
            with self.assertRaises(ValueError):
                await operation("owner", started["flow_id"])
        self.assertEqual((await complete_login("owner", started["flow_id"]))["status"], "pending")

    async def test_manual_owner_and_state_binding_leave_flow_available(self):
        from core.kiro_browser_login import accept_callback, cancel_login, complete_login

        started = await self.start()
        other = await self.start()
        with self.assertRaises(ValueError):
            await accept_callback(self.callback(started), token="other", flow_id=started["flow_id"])
        with self.assertRaises(ValueError):
            await accept_callback(self.callback(started), token="owner", flow_id=other["flow_id"])
        with self.assertRaises(ValueError):
            await cancel_login("other", started["flow_id"])
        await accept_callback(self.callback(started), token="owner", flow_id=started["flow_id"])
        with self.assertRaises(ValueError):
            await accept_callback(self.callback(started, code="replacement"))
        self.assertEqual((await complete_login("owner", other["flow_id"]))["status"], "pending")

    async def test_storage_retry_does_not_exchange_code_twice(self):
        from core.kiro_browser_login import accept_callback, complete_login

        started = await self.start()
        await accept_callback(self.callback(started, login_option="github"))
        with (
            patch(
                "core.kiro_browser_login.auth_request",
                AsyncMock(
                    return_value=(
                        200,
                        {
                            "accessToken": "access",
                            "refreshToken": "refresh",
                            "expiresIn": 3600,
                        },
                    )
                ),
            ) as exchange,
            patch(
                "core.kiro_browser_login.store_extended_credential",
                AsyncMock(
                    side_effect=[
                        OSError("synthetic storage failure"),
                        {"filename": "kiro.json", "action": "updated"},
                    ]
                ),
            ) as save,
        ):
            with self.assertRaises(OSError):
                await complete_login("owner", started["flow_id"])
            self.assertTrue((await complete_login("owner", started["flow_id"]))["credential_saved"])
            self.assertEqual(exchange.await_count, 1)
            self.assertEqual(save.await_count, 2)

    async def test_ambiguous_exchange_failure_consumes_code(self):
        from core.kiro_browser_login import accept_callback, complete_login

        started = await self.start()
        await accept_callback(self.callback(started))
        with patch("core.kiro_browser_login.auth_request", AsyncMock(side_effect=TimeoutError)):
            with self.assertRaises(TimeoutError):
                await complete_login("owner", started["flow_id"])
        with self.assertRaises(ValueError):
            await complete_login("owner", started["flow_id"])

    async def test_callback_error_does_not_exchange_tokens(self):
        from core.kiro_browser_login import accept_callback, complete_login

        started = await self.start()
        await accept_callback(self.callback(started, code="", error="access_denied"))
        with patch("core.kiro_browser_login.auth_request", AsyncMock()) as exchange:
            self.assertEqual(
                (await complete_login("owner", started["flow_id"]))["reason"], "denied"
            )
            exchange.assert_not_awaited()

    async def test_busy_flow_is_retryable_without_consuming_callback(self):
        from core.device_authorization_coordination import DeviceAuthorizationBusyError
        from core.kiro_browser_login import accept_callback, complete_login

        started = await self.start()
        claim = await self.service.claim(started["flow_id"], lease_seconds=60, provider="kiro")
        with self.assertRaises(DeviceAuthorizationBusyError):
            await complete_login("owner", started["flow_id"])
        with self.assertRaises(DeviceAuthorizationBusyError):
            await accept_callback(self.callback(started))
        await self.service.release(claim)
        await accept_callback(self.callback(started))

    async def test_expiry_prevents_callback_and_exchange(self):
        from core.kiro_browser_login import accept_callback, complete_login

        now = [1000.0]
        configure_device_authorization_service(
            DeviceAuthorizationService(
                InMemoryStateStore(clock=lambda: now[0]), key=b"x" * 32, fencing_epoch=1
            )
        )
        started = await self.start()
        now[0] += 601
        with patch("core.kiro_browser_login.auth_request", AsyncMock()) as exchange:
            with self.assertRaises(ValueError):
                await accept_callback(self.callback(started))
            with self.assertRaises(ValueError):
                await complete_login("owner", started["flow_id"])
            exchange.assert_not_awaited()

    async def test_public_callback_only_captures_and_redirects_without_secrets(self):
        from core.panel.providers.kiro import router
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        app = FastAPI()
        app.include_router(router)
        started = await self.start()
        with patch("core.kiro_browser_login.auth_request", AsyncMock()) as exchange:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://localhost:4283"
            ) as client:
                response = await client.get(self.callback(started))
                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], "/callback?kiro=received")
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(response.headers["referrer-policy"], "no-referrer")
                self.assertNotIn("synthetic-code", response.text)
                response = await client.get("/signin/callback?state=invalid&code=secret")
                self.assertEqual(response.headers["location"], "/callback?kiro=failed")
            exchange.assert_not_awaited()

    async def test_completion_route_audits_only_saved_credentials(self):
        from core.panel.providers.kiro import KiroFlowRequest, browser_complete
        from starlette.requests import Request

        started = await self.start()
        http_request = Request({"type": "http", "headers": []})
        payload = KiroFlowRequest(flow_id=started["flow_id"])
        with (
            patch(
                "core.kiro_browser_login.complete_login",
                AsyncMock(
                    side_effect=[
                        {"status": "pending"},
                        {"status": "complete", "credential_saved": True},
                    ]
                ),
            ),
            patch(
                "core.panel.providers.kiro.record_classified_management_response", AsyncMock()
            ) as audit,
        ):
            await browser_complete(payload, http_request, "owner")
            audit.assert_not_awaited()
            await browser_complete(payload, http_request, "owner")
            audit.assert_awaited_once()
            self.assertEqual(audit.call_args.args[0].target_identifier, "kiro:collection")
            self.assertNotIn(started["flow_id"], str(audit.call_args))
