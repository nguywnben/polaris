"""Account email is private until an authorized, explicit reveal."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.credential_fleet_query import enrich_credential_summary
from core.credential_privacy import mask_account_email, mask_email_text
from core.identity import (
    ManagementPermission,
    ManagementPrincipal,
    ManagementRole,
    management_route_manifest,
)
from core.panel import credential_operations, credentials
from core.utils import _VerifiedPanelToken


class EmailPrivacyTests(unittest.TestCase):
    def test_short_localparts_do_not_reveal_the_entire_account_name(self):
        for email, expected in (
            ("a@example.com", "***@example.com"),
            ("ab@example.com", "***@example.com"),
            ("abc@example.com", "a***@example.com"),
            ("abcd@example.com", "a***@example.com"),
            ("abcde@example.com", "ab***de@example.com"),
        ):
            with self.subTest(email=email):
                self.assertEqual(mask_account_email(email), expected)
                self.assertNotEqual(mask_account_email(email), email)

    def test_invalid_input_is_never_returned_as_an_unmasked_identity(self):
        for value in (None, "", "  ", 42, {}, []):
            with self.subTest(value=value):
                self.assertIsNone(mask_account_email(value))
        for value in ("not-an-email", "someone@@example.com", "someone @example.com"):
            with self.subTest(value=value):
                self.assertEqual(mask_account_email(value), "***")

    def test_unicode_addresses_and_already_masked_values_are_stable(self):
        self.assertEqual(mask_account_email("  người42@example.com  "), "ng***42@example.com")
        for value in ("ng***42@example.com", "***@example.com", "a***@example.com"):
            with self.subTest(value=value):
                self.assertEqual(mask_account_email(value), value)

    def test_labels_preserve_plain_text_and_mask_each_embedded_address(self):
        self.assertEqual(mask_email_text("Main account"), "Main account")
        self.assertEqual(
            mask_email_text("Main <someone42@example.com>; backup other77@example.net"),
            "Main <so***42@example.com>; backup ot***77@example.net",
        )

    def test_fleet_masks_account_email_and_label_without_mutating_storage_data(self):
        summary = {"filename": "account.json", "user_email": "someone42@example.com"}
        content = {
            "provider": "google_antigravity",
            "credential_label": "Main someone42@example.com",
        }
        item = enrich_credential_summary(summary, content, backend_type="sqlite", mode="primary")
        self.assertNotIn("someone42@example.com", json.dumps(item))
        self.assertEqual(item["user_email"], "so***42@example.com")
        self.assertEqual(summary["user_email"], "someone42@example.com")
        self.assertEqual(content["credential_label"], "Main someone42@example.com")

    def test_configuration_does_not_leak_an_email_used_as_a_label(self):
        payload = credentials._credential_configuration_payload(
            "account.json",
            {"provider": "google_antigravity", "credential_label": "someone42@example.com"},
        )
        self.assertNotIn("someone42@example.com", json.dumps(payload))

    def test_muse_payload_email_is_masked_even_when_summary_state_is_empty(self):
        content = {"provider": "muse_code", "user_email": "someone42@example.com"}
        item = enrich_credential_summary(
            {"filename": "muse.json", "user_email": None},
            content,
            backend_type="sqlite",
            mode="provider",
        )
        self.assertEqual(item["user_email"], "so***42@example.com")
        self.assertNotIn("someone42@example.com", json.dumps(item))
        self.assertEqual(content["user_email"], "someone42@example.com")

    def test_reveal_route_requires_the_export_permission(self):
        entries = [
            entry
            for entry in management_route_manifest()
            if entry.method == "GET" and entry.path == "/api/credentials/email/{filename}"
        ]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].permission, ManagementPermission.CREDENTIALS_EXPORT)


class EmailRevealTests(unittest.IsolatedAsyncioTestCase):
    async def test_reveal_returns_only_email_and_disables_caching(self):
        adapter = AsyncMock()
        adapter.get_credential.return_value = {
            "provider": "muse_code",
            "user_email": "someone42@example.com",
            "access_token": "secret-token",
        }
        adapter.get_credential_state.return_value = {"user_email": "stale@example.com"}
        with patch.object(credentials, "get_storage_adapter", return_value=adapter):
            response = await credentials.reveal_credential_email(
                "account.json", token="test", mode="provider"
            )
        self.assertEqual(json.loads(response.body), {"user_email": "someone42@example.com"})
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("secret-token", response.body.decode())
        adapter.store_credential.assert_not_awaited()
        adapter.update_credential_state.assert_not_awaited()

    async def test_reveal_falls_back_to_cached_identity_when_payload_has_none(self):
        adapter = AsyncMock()
        adapter.get_credential.return_value = {"provider": "google_antigravity", "token": "secret"}
        adapter.get_credential_state.return_value = {"user_email": "someone42@example.com"}
        with patch.object(credentials, "get_storage_adapter", return_value=adapter):
            response = await credentials.reveal_credential_email(
                "account.json", token="test", mode="provider"
            )
        self.assertEqual(json.loads(response.body), {"user_email": "someone42@example.com"})
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_reveal_returns_null_without_fetching_upstream_when_no_email_exists(self):
        adapter = AsyncMock()
        adapter.get_credential.return_value = {"provider": "openai", "api_key": "secret"}
        adapter.get_credential_state.return_value = None
        with patch.object(credentials, "get_storage_adapter", return_value=adapter):
            response = await credentials.reveal_credential_email(
                "account.json", token="test", mode="provider"
            )
        self.assertEqual(json.loads(response.body), {"user_email": None})
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_missing_credential_is_not_revealed_from_stale_state(self):
        adapter = AsyncMock()
        adapter.get_credential.return_value = None
        adapter.get_credential_state.return_value = {"user_email": "stale@example.com"}
        with patch.object(credentials, "get_storage_adapter", return_value=adapter):
            with self.assertRaises(HTTPException) as raised:
                await credentials.reveal_credential_email(
                    "missing.json", token="test", mode="provider"
                )
        self.assertEqual(raised.exception.status_code, 404)
        self.assertNotIn("stale@example.com", str(raised.exception.detail))

    async def test_http_reveal_denies_viewer_operator_and_allows_security_admin(self):
        app = FastAPI()
        app.include_router(credentials.router, prefix="/api/credentials")
        adapter = AsyncMock()
        adapter.get_credential.return_value = {
            "provider": "muse_code",
            "user_email": "someone42@example.com",
            "token": "private-token",
        }
        adapter.get_credential_state.return_value = {}
        for role, status in (
            (ManagementRole.VIEWER, 403),
            (ManagementRole.OPERATOR, 403),
            (ManagementRole.SECURITY_ADMIN, 200),
        ):
            principal = ManagementPrincipal.oidc_user(
                issuer="https://idp.example",
                subject=role.value,
                role=role,
            )
            token = _VerifiedPanelToken("test-session", principal)
            with (
                self.subTest(role=role),
                patch("core.utils.verify_panel_token_value", AsyncMock(return_value=token)),
                patch.object(credentials, "get_storage_adapter", return_value=adapter),
            ):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get(
                        "/api/credentials/email/account.json?mode=provider",
                        headers={"Authorization": "Bearer test-session"},
                    )
                self.assertEqual(response.status_code, status)
                self.assertNotIn("private-token", response.text)
                if status == 200:
                    self.assertEqual(response.json(), {"user_email": "someone42@example.com"})
                    self.assertEqual(response.headers["cache-control"], "no-store")
                else:
                    self.assertNotIn("someone42@example.com", response.text)


class EmailRefreshPrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_email_returns_masked_projection(self):
        adapter = AsyncMock()
        adapter.get_credential.return_value = {"provider": "google_antigravity"}
        with (
            patch.object(credential_operations, "get_storage_adapter", return_value=adapter),
            patch.object(
                credential_operations.credential_manager,
                "get_or_fetch_user_email",
                AsyncMock(return_value="someone42@example.com"),
            ),
        ):
            response = await credential_operations.fetch_user_email_common(
                "account.json", mode="provider"
            )
        self.assertEqual(json.loads(response.body)["user_email"], "so***42@example.com")
        self.assertNotIn("someone42@example.com", response.body.decode())

    async def test_batch_refresh_masks_both_cached_and_fetched_addresses(self):
        adapter = AsyncMock()
        states = {"cached.json": {"user_email": "cached42@example.com"}, "fresh.json": {}}
        adapter.get_all_credential_states.return_value = states
        with (
            patch.object(credential_operations, "get_storage_adapter", return_value=adapter),
            patch.object(
                credential_operations.credential_manager,
                "get_or_fetch_user_email",
                AsyncMock(return_value="fresh77@example.com"),
            ),
        ):
            response = await credential_operations.refresh_all_user_emails_common(mode="provider")
        payload = json.loads(response.body)
        self.assertEqual(payload["skipped_count"], 1)
        self.assertEqual(payload["success_count"], 1)
        self.assertEqual(
            [item["user_email"] for item in payload["results"]],
            ["ca***42@example.com", "fr***77@example.com"],
        )
        self.assertNotIn("cached42@example.com", response.body.decode())
        self.assertNotIn("fresh77@example.com", response.body.decode())
        self.assertEqual(states["cached.json"]["user_email"], "cached42@example.com")


if __name__ == "__main__":
    unittest.main()
