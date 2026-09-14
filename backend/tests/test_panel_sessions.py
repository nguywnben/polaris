"""Security contracts for control-panel session cookies."""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request
from starlette.responses import JSONResponse

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import jwt
from core.identity import (
    ManagementPrincipal,
    ManagementRole,
    OidcRoleSource,
    SessionExpired,
    SessionNotFound,
)
from core.panel.auth import _client_identity, logout, setup_status
from core.utils import (
    PANEL_SESSION_COOKIE,
    _VerifiedPanelToken,
    clear_panel_session_cookie,
    create_panel_session_token,
    set_panel_session_cookie,
    verify_panel_token,
    verify_panel_token_value,
)
from core.virtual_keys import VirtualKey


def verified_panel_token(value: str) -> _VerifiedPanelToken:
    return _VerifiedPanelToken(value, ManagementPrincipal.local_owner())


def build_request(
    *,
    cookie: str = "",
    scheme: str = "http",
    forwarded_for: str = "",
    forwarded_proto: str = "",
    client_host: str = "127.0.0.1",
    method: str = "GET",
    origin: str = "",
    sec_fetch_site: str = "",
    route_path: str = "/api/config/get",
    internal_route_path: str = "",
) -> Request:
    headers = []
    if cookie:
        headers.append((b"cookie", cookie.encode("ascii")))
    if forwarded_for:
        headers.append((b"x-forwarded-for", forwarded_for.encode("ascii")))
    if forwarded_proto:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode("ascii")))
    if origin:
        headers.append((b"origin", origin.encode("ascii")))
    if sec_fetch_site:
        headers.append((b"sec-fetch-site", sec_fetch_site.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": method,
            "scheme": scheme,
            "path": route_path,
            "route": SimpleNamespace(
                path=internal_route_path or route_path,
                path_format=route_path,
            ),
            "headers": headers,
            "client": (client_host, 50000),
            "server": ("localhost", 4283),
        }
    )


class PanelSessionCookieTests(unittest.IsolatedAsyncioTestCase):
    async def test_setup_status_reports_a_valid_cookie_session_without_a_401_probe(self):
        request = build_request(cookie=f"{PANEL_SESSION_COOKIE}=cookie-session")

        with (
            patch(
                "core.panel.auth.config.has_password_configured", new=AsyncMock(return_value=True)
            ),
            patch(
                "core.panel.auth.verify_panel_token_value",
                new=AsyncMock(return_value="cookie-session"),
            ) as verifier,
        ):
            response = await setup_status(request)

        payload = json.loads(response.body)
        self.assertTrue(payload["authenticated"])
        verifier.assert_awaited_once_with("cookie-session")

    async def test_setup_status_reports_an_invalid_cookie_as_signed_out(self):
        request = build_request(cookie=f"{PANEL_SESSION_COOKIE}=expired-session")

        with (
            patch(
                "core.panel.auth.config.has_password_configured", new=AsyncMock(return_value=True)
            ),
            patch(
                "core.panel.auth.verify_panel_token_value",
                new=AsyncMock(side_effect=HTTPException(status_code=401)),
            ),
        ):
            response = await setup_status(request)

        self.assertFalse(json.loads(response.body)["authenticated"])

    async def test_cookie_is_http_only_same_site_and_path_scoped(self):
        response = JSONResponse({"success": True})

        set_panel_session_cookie(response, "signed-session", build_request())

        cookie = response.headers["set-cookie"]
        self.assertIn(f"{PANEL_SESSION_COOKIE}=signed-session", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertIn("Path=/", cookie)

    async def test_https_requests_receive_secure_cookie(self):
        response = JSONResponse({"success": True})

        set_panel_session_cookie(
            response,
            "signed-session",
            build_request(scheme="https"),
        )

        self.assertIn("Secure", response.headers["set-cookie"])

    async def test_untrusted_forwarded_proto_does_not_set_secure_cookie(self):
        response = JSONResponse({"success": True})

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRUST_PROXY_HEADERS", None)
            set_panel_session_cookie(
                response,
                "signed-session",
                build_request(forwarded_proto="https"),
            )

        self.assertNotIn("Secure", response.headers["set-cookie"])

    async def test_trusted_forwarded_proto_sets_secure_cookie(self):
        response = JSONResponse({"success": True})

        with patch.dict(os.environ, {"TRUST_PROXY_HEADERS": "true"}):
            set_panel_session_cookie(
                response,
                "signed-session",
                build_request(forwarded_proto="https"),
            )

        self.assertIn("Secure", response.headers["set-cookie"])

    async def test_cookie_token_is_accepted_without_authorization_header(self):
        request = build_request(cookie=f"{PANEL_SESSION_COOKIE}=cookie-session")

        with patch(
            "core.utils.verify_panel_token_value",
            new=AsyncMock(return_value=verified_panel_token("cookie-session")),
        ) as verifier:
            token = await verify_panel_token(request, credentials=None)

        self.assertEqual(token, "cookie-session")
        verifier.assert_awaited_once_with("cookie-session")
        self.assertRegex(request.state.management_auth_reference, r"^[0-9a-f]{64}$")
        self.assertNotEqual(request.state.management_auth_reference, "cookie-session")

    async def test_bearer_token_remains_supported_for_non_browser_clients(self):
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="legacy-session",
        )

        with patch(
            "core.utils.verify_panel_token_value",
            new=AsyncMock(return_value=verified_panel_token("legacy-session")),
        ):
            token = await verify_panel_token(build_request(), credentials=credentials)

        self.assertEqual(token, "legacy-session")

    async def test_untyped_verified_token_never_falls_back_to_local_owner(self):
        request = build_request(cookie=f"{PANEL_SESSION_COOKIE}=cookie-session")

        with (
            patch(
                "core.utils.verify_panel_token_value",
                new=AsyncMock(return_value="cookie-session"),
            ),
            self.assertRaises(HTTPException) as context,
        ):
            await verify_panel_token(request, credentials=None)

        self.assertEqual(context.exception.status_code, 503)
        self.assertFalse(hasattr(request.state, "management_principal"))

    async def test_virtual_key_bearer_authorizes_management_read_scope(self):
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="sk-polaris-vk-management-reader",
        )
        record = VirtualKey(
            id="vk_reader",
            name="reader",
            key_hash="hash",
            key_preview="sk-polaris-vk-...ader",
            scopes=("management:read",),
        )
        request = build_request()
        with (
            patch(
                "core.virtual_keys.virtual_key_manager.verify",
                new=AsyncMock(return_value=record),
            ) as verify,
            patch(
                "core.virtual_keys.virtual_key_manager.note_last_used",
                new=AsyncMock(),
            ) as note_last_used,
        ):
            token = await verify_panel_token(request, credentials=credentials)

        self.assertEqual(token, credentials.credentials)
        verify.assert_awaited_once_with(credentials.credentials)
        note_last_used.assert_awaited_once_with(record)
        self.assertEqual(request.state.management_principal.principal_id, "vk_reader")

    async def test_virtual_key_bearer_uses_write_scope_for_unsafe_method(self):
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="sk-polaris-vk-management-writer",
        )
        record = VirtualKey(
            id="vk_writer",
            name="writer",
            key_hash="hash",
            key_preview="sk-polaris-vk-...iter",
            scopes=("management:read", "management:write"),
        )
        with (
            patch(
                "core.virtual_keys.virtual_key_manager.verify",
                new=AsyncMock(return_value=record),
            ),
            patch(
                "core.virtual_keys.virtual_key_manager.note_last_used",
                new=AsyncMock(),
            ),
        ):
            await verify_panel_token(
                build_request(method="POST", route_path="/api/config/save"),
                credentials=credentials,
            )

    async def test_virtual_key_denial_happens_before_last_used_is_recorded(self):
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="sk-polaris-vk-management-reader",
        )
        record = VirtualKey(
            id="vk_reader",
            name="reader",
            key_hash="hash",
            key_preview="sk-polaris-vk-...ader",
            scopes=("management:read",),
        )
        request = build_request(method="POST", route_path="/api/config/save")
        with (
            patch(
                "core.virtual_keys.virtual_key_manager.verify",
                new=AsyncMock(return_value=record),
            ),
            patch(
                "core.virtual_keys.virtual_key_manager.note_last_used",
                new=AsyncMock(),
            ) as note_last_used,
            self.assertRaises(HTTPException) as context,
        ):
            await verify_panel_token(request, credentials=credentials)

        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(context.exception.detail, "Management permission denied.")
        self.assertEqual(request.state.management_principal.principal_id, "vk_reader")
        note_last_used.assert_not_awaited()

    async def test_unclassified_protected_route_fails_closed_before_handler(self):
        request = build_request(
            cookie=f"{PANEL_SESSION_COOKIE}=cookie-session",
            route_path="/api/unclassified",
        )

        with (
            patch(
                "core.utils.verify_panel_token_value",
                new=AsyncMock(return_value=verified_panel_token("cookie-session")),
            ),
            self.assertRaises(HTTPException) as context,
        ):
            await verify_panel_token(request, credentials=None)

        self.assertEqual(context.exception.status_code, 500)
        self.assertEqual(
            context.exception.detail,
            "Management authorization policy is incomplete.",
        )

    async def test_fastapi_path_converter_uses_the_openapi_route_template(self):
        request = build_request(
            cookie=f"{PANEL_SESSION_COOKIE}=cookie-session",
            method="DELETE",
            route_path="/api/model-blacklist/{provider_id}/models/{model_id}",
            internal_route_path="/api/model-blacklist/{provider_id}/models/{model_id:path}",
        )

        with patch(
            "core.utils.verify_panel_token_value",
            new=AsyncMock(return_value=verified_panel_token("cookie-session")),
        ):
            token = await verify_panel_token(request, credentials=None)

        self.assertEqual(token, "cookie-session")

    async def test_nested_fastapi_router_uses_the_effective_route_template(self):
        leaf_router = APIRouter()

        @leaf_router.get("/status")
        async def status(_token: str = Depends(verify_panel_token)) -> dict[str, bool]:
            return {"ok": True}

        panel_router = APIRouter()
        panel_router.include_router(leaf_router, prefix="/api/credentials")
        app = FastAPI()
        app.include_router(panel_router)
        transport = httpx.ASGITransport(app=app)

        with patch(
            "core.utils.verify_panel_token_value",
            new=AsyncMock(return_value=verified_panel_token("cookie-session")),
        ):
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
                cookies={PANEL_SESSION_COOKIE: "cookie-session"},
            ) as client:
                response = await client.get("/api/credentials/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    async def test_same_origin_cookie_request_is_accepted(self):
        request = build_request(
            cookie=f"{PANEL_SESSION_COOKIE}=cookie-session",
            method="POST",
            origin="http://localhost:4283",
            sec_fetch_site="same-origin",
            route_path="/api/config/save",
        )

        with patch(
            "core.utils.verify_panel_token_value",
            new=AsyncMock(return_value=verified_panel_token("cookie-session")),
        ):
            token = await verify_panel_token(request, credentials=None)

        self.assertEqual(token, "cookie-session")

    async def test_cross_origin_cookie_request_is_rejected(self):
        request = build_request(
            cookie=f"{PANEL_SESSION_COOKIE}=cookie-session",
            method="POST",
            origin="https://attacker.example",
        )

        with self.assertRaises(HTTPException) as context:
            await verify_panel_token(request, credentials=None)

        self.assertEqual(context.exception.status_code, 403)

    async def test_cross_site_fetch_metadata_is_rejected_without_origin(self):
        request = build_request(
            cookie=f"{PANEL_SESSION_COOKIE}=cookie-session",
            method="DELETE",
            sec_fetch_site="cross-site",
        )

        with self.assertRaises(HTTPException) as context:
            await verify_panel_token(request, credentials=None)

        self.assertEqual(context.exception.status_code, 403)

    async def test_bearer_request_does_not_require_browser_origin(self):
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="automation-session",
        )
        request = build_request(
            method="POST",
            origin="https://automation.example",
            sec_fetch_site="cross-site",
            route_path="/api/config/save",
        )

        with patch(
            "core.utils.verify_panel_token_value",
            new=AsyncMock(return_value=verified_panel_token("automation-session")),
        ):
            token = await verify_panel_token(request, credentials=credentials)

        self.assertEqual(token, "automation-session")

    async def test_missing_session_is_rejected(self):
        with self.assertRaises(HTTPException) as context:
            await verify_panel_token(build_request(), credentials=None)

        self.assertEqual(context.exception.status_code, 401)

    async def test_logout_cookie_expires_immediately(self):
        response = JSONResponse({"success": True})

        clear_panel_session_cookie(response)

        cookie = response.headers["set-cookie"]
        self.assertIn(f"{PANEL_SESSION_COOKIE}=", cookie)
        self.assertIn("Max-Age=0", cookie)


class PanelSessionLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_login_tokens_are_issued_by_the_opaque_session_service(self):
        service = SimpleNamespace(
            issue_local_owner=AsyncMock(return_value=SimpleNamespace(token="ogs_" + "A" * 43))
        )

        with (
            patch("core.utils.get_session_service", return_value=service),
            patch("core.utils.time.time", return_value=1_000.0),
        ):
            token = await create_panel_session_token()

        self.assertEqual(token, "ogs_" + "A" * 43)
        service.issue_local_owner.assert_awaited_once_with(now=1_000.0)

    async def test_opaque_session_resolution_maps_expiry_and_replay_to_generic_http_errors(self):
        service = SimpleNamespace(
            resolve=AsyncMock(
                return_value=SimpleNamespace(principal=ManagementPrincipal.local_owner())
            )
        )
        token = "ogs_" + "A" * 43
        with (
            patch("core.utils.get_session_service", return_value=service),
            patch("core.utils.time.time", return_value=1_001.0),
        ):
            self.assertEqual(await verify_panel_token_value(token), token)
        service.resolve.assert_awaited_once_with(token, now=1_001.0)

        for error, detail in (
            (SessionExpired("expired"), "Session expired. Please sign in again."),
            (SessionNotFound("missing"), "Invalid session token."),
        ):
            service.resolve.reset_mock(side_effect=True)
            service.resolve.side_effect = error
            with (
                patch("core.utils.get_session_service", return_value=service),
                self.assertRaises(HTTPException) as context,
            ):
                await verify_panel_token_value(token)
            self.assertEqual(context.exception.status_code, 401)
            self.assertEqual(context.exception.detail, detail)

    async def test_opaque_oidc_session_authorizes_its_real_role_instead_of_local_owner(self):
        principal = ManagementPrincipal.oidc_user(
            issuer="https://identity.example.com/tenant",
            subject="subject-viewer",
            role=ManagementRole.VIEWER,
            role_source=OidcRoleSource.CLAIM_MAPPING,
        )
        service = SimpleNamespace(
            resolve=AsyncMock(return_value=SimpleNamespace(principal=principal))
        )
        token = "ogs_" + "A" * 43

        with patch("core.utils.get_session_service", return_value=service):
            read_request = build_request(
                cookie=f"{PANEL_SESSION_COOKIE}={token}",
                route_path="/api/config/get",
            )
            self.assertEqual(await verify_panel_token(read_request, credentials=None), token)
            self.assertEqual(read_request.state.management_principal, principal)

            write_request = build_request(
                cookie=f"{PANEL_SESSION_COOKIE}={token}",
                method="POST",
                origin="http://localhost:4283",
                route_path="/api/config/save",
            )
            with self.assertRaises(HTTPException) as context:
                await verify_panel_token(write_request, credentials=None)

        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(write_request.state.management_principal, principal)

    async def test_legacy_jwt_is_accepted_only_inside_its_bounded_migration_window(self):
        now = int(time.time())
        secret = b"l" * 32

        def legacy_token(issued_at: int) -> str:
            return jwt.encode(
                {
                    "sub": "panel",
                    "aud": "panel",
                    "iat": issued_at,
                    "exp": now + 600,
                },
                secret,
                algorithm="HS256",
            )

        with (
            patch("core.utils._get_panel_session_secret", new=AsyncMock(return_value=secret)),
            patch.dict(os.environ, {"PANEL_LEGACY_SESSION_MIGRATION_SECONDS": "300"}),
            patch("core.utils.time.time", return_value=float(now)),
        ):
            recent = legacy_token(now - 299)
            self.assertEqual(await verify_panel_token_value(recent), recent)
            with self.assertRaises(HTTPException) as context:
                await verify_panel_token_value(legacy_token(now - 300))

        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.detail, "Session expired. Please sign in again.")

    async def test_logout_revokes_the_presented_opaque_session_before_clearing_cookie(self):
        token = "ogs_" + "A" * 43
        service = SimpleNamespace(revoke=AsyncMock(return_value=True))
        request = build_request(
            cookie=f"{PANEL_SESSION_COOKIE}={token}",
            method="POST",
            origin="http://localhost:4283",
            sec_fetch_site="same-origin",
            route_path="/api/auth/logout",
        )

        with patch("core.panel.auth.get_session_service", return_value=service):
            response = await logout(request)

        service.revoke.assert_awaited_once_with(token)
        self.assertIn("Max-Age=0", response.headers["set-cookie"])

    async def test_cross_origin_logout_is_rejected_before_session_revocation(self):
        token = "ogs_" + "A" * 43
        service = SimpleNamespace(revoke=AsyncMock())
        request = build_request(
            cookie=f"{PANEL_SESSION_COOKIE}={token}",
            method="POST",
            origin="https://attacker.example",
            route_path="/api/auth/logout",
        )

        with (
            patch("core.panel.auth.get_session_service", return_value=service),
            self.assertRaises(HTTPException) as context,
        ):
            await logout(request)

        self.assertEqual(context.exception.status_code, 403)
        service.revoke.assert_not_awaited()


class ClientIdentityTests(unittest.TestCase):
    def test_forwarded_address_is_ignored_by_default(self):
        request = build_request(
            forwarded_for="198.51.100.20",
            client_host="192.0.2.10",
        )

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRUST_PROXY_HEADERS", None)
            self.assertEqual(_client_identity(request), "192.0.2.10")

    def test_forwarded_address_can_be_enabled_for_a_trusted_proxy(self):
        request = build_request(
            forwarded_for="198.51.100.20, 192.0.2.10",
            client_host="192.0.2.10",
        )

        with patch.dict(os.environ, {"TRUST_PROXY_HEADERS": "true"}):
            self.assertEqual(_client_identity(request), "198.51.100.20")
