"""Browser boundary tests for the activated OIDC authorization-code flow."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import (  # noqa: E402
    OidcAuthorizationRequest,
    OidcLoginDisabled,
    OidcLoginError,
)
from core.panel.identity_browser_routes import OIDC_BROWSER_COOKIE, router  # noqa: E402
from core.utils import PANEL_SESSION_COOKIE  # noqa: E402


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


class OidcBrowserRoutesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = SimpleNamespace(
            begin=AsyncMock(
                return_value=OidcAuthorizationRequest(
                    authorization_url="https://identity.example.com/authorize?state=opaque",
                    browser_token="B" * 43,
                    expires_in_seconds=300,
                )
            ),
            complete=AsyncMock(return_value=SimpleNamespace(token="ogs_" + "S" * 43)),
        )
        self.patch = patch(
            "core.panel.identity_browser_routes.get_or_initialize_oidc_login_service",
            new=AsyncMock(return_value=self.service),
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.admission_patch = patch(
            "core.panel.identity_browser_routes._assert_and_record_oidc_start",
            new=AsyncMock(return_value=None),
        )
        self.admission_patch.start()
        self.addCleanup(self.admission_patch.stop)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_app()),
            base_url="https://gateway.example.com",
            follow_redirects=False,
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_start_is_a_303_and_binds_a_short_lived_http_only_browser_cookie(self):
        response = await self.client.get("/api/identity/oidc/start")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "https://identity.example.com/authorize?state=opaque",
        )
        cookie = response.headers["set-cookie"]
        self.assertIn(f"{OIDC_BROWSER_COOKIE}=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertIn("Path=/api/identity/oidc/callback", cookie)
        self.assertIn("Max-Age=300", cookie)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")

    async def test_callback_issues_panel_cookie_and_redirects_to_a_clean_same_origin_url(self):
        await self.client.get("/api/identity/oidc/start")

        response = await self.client.get(
            "/api/identity/oidc/callback?code=provider-code&state=opaque"
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/")
        cookies = response.headers.get_list("set-cookie")
        self.assertTrue(any(f"{PANEL_SESSION_COOKIE}=ogs_" in value for value in cookies))
        self.assertTrue(
            any(f"{OIDC_BROWSER_COOKIE}=" in value and "Max-Age=0" in value for value in cookies)
        )
        self.assertNotIn("provider-code", repr(response.headers))
        self.service.complete.assert_awaited_once()
        call = self.service.complete.await_args
        self.assertEqual(call.kwargs["browser_token"], "B" * 43)
        self.assertEqual(call.args[0], b"code=provider-code&state=opaque")

    async def test_provider_controlled_failure_is_not_reflected_and_clears_browser_binding(self):
        await self.client.get("/api/identity/oidc/start")
        self.service.complete.side_effect = OidcLoginError()

        response = await self.client.get(
            "/api/identity/oidc/callback?error=evil%0d%0aInjected&state=opaque"
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login")
        self.assertNotIn("evil", repr(response.headers).lower())
        self.assertNotIn("evil", response.text.lower())
        self.assertTrue(
            any(
                f"{OIDC_BROWSER_COOKIE}=" in value and "Max-Age=0" in value
                for value in response.headers.get_list("set-cookie")
            )
        )

    async def test_disabled_start_is_hidden_and_outage_does_not_touch_local_routes(self):
        self.service.begin.side_effect = OidcLoginDisabled()

        response = await self.client.get("/api/identity/oidc/start")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "OIDC login is unavailable."})


if __name__ == "__main__":
    unittest.main()
