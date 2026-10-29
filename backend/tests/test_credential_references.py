"""Opaque console references never rename credential storage keys."""

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import credential_privacy
from core.credential_references import credential_reference_key, resolve_credential_reference
from core.identity import ManagementPrincipal, ManagementRole
from core.panel import credentials, usage_routes
from core.utils import _VerifiedPanelToken, verify_panel_token


class CredentialReferenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_ordinary_http_configuration_hides_email_filename(self):
        app = FastAPI()
        app.include_router(credentials.router, prefix="/api/credentials")
        app.dependency_overrides[verify_panel_token] = lambda: "owner"
        storage = AsyncMock()
        storage.get_config.return_value = base64.urlsafe_b64encode(b"k" * 32).decode()
        storage.list_credentials.return_value = ["someone42@example.com.json"]
        storage.get_credential.return_value = {
            "provider": "google_antigravity",
            "credential_label": "Main",
        }
        with (
            patch("core.panel.credentials.get_storage_adapter", return_value=storage),
            patch("core.storage_adapter.get_storage_adapter", return_value=storage),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                initial = credential_privacy.credential_reference(
                    "someone42@example.com.json", b"k" * 32
                )
                response = await client.get(
                    f"/api/credentials/configuration/{initial}?mode=provider"
                )
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("someone42@example.com", response.text)
                reference = response.json()["filename"]
                self.assertTrue(reference.startswith("credref-v1-"))
                again = await client.get(
                    f"/api/credentials/configuration/{reference}?mode=provider"
                )
                self.assertEqual(again.status_code, 200)
                self.assertEqual(again.json()["filename"], reference)
        storage.get_credential.assert_awaited_with("someone42@example.com.json", mode="primary")
        storage.store_credential.assert_not_called()

    async def test_projection_keys_messages_and_nonmutation(self):
        key = b"k" * 32
        filename = "someone42@example.com.json"
        value = {filename: {"filename": filename, "message": f"Failed for {filename}."}}
        original = json.dumps(value)
        projected = credential_privacy.project_credential_references(value, key)
        self.assertNotIn("someone42@example.com", json.dumps(projected))
        self.assertEqual(json.dumps(value), original)
        reference = credential_privacy.credential_reference(filename, key)
        self.assertEqual(list(projected), [reference])
        self.assertEqual(projected[reference]["filename"], reference)
        self.assertEqual(credential_privacy.credential_reference("plain.json", key), "plain.json")
        self.assertNotEqual(reference, credential_privacy.credential_reference(filename, b"z" * 32))

    async def test_unknown_reference_never_falls_back_to_a_storage_filename(self):
        from core.credential_references import resolve_credential_reference

        storage = AsyncMock()
        storage.get_config.return_value = base64.urlsafe_b64encode(b"k" * 32).decode()
        storage.list_credentials.return_value = ["plain.json"]
        with patch("core.storage_adapter.get_storage_adapter", return_value=storage):
            with self.assertRaises(HTTPException) as error:
                await resolve_credential_reference(
                    "credref-v1-" + "0" * 64 + ".json", mode="primary"
                )
        self.assertEqual(error.exception.status_code, 404)
        storage.get_credential.assert_not_called()

    async def test_malformed_references_fail_before_storage_access(self):
        malformed = (
            "credref-v1-short.json",
            "credref-v1-" + "0" * 63 + ".json",
            "credref-v1-" + "A" * 64 + ".json",
            "credref-v1-" + "g" * 64 + ".json",
            "credref-v1-" + "0" * 64 + ".JSON",
            "credref-v1-" + "0" * 64 + ".json.extra",
            "credref-v1-../account.json",
        )
        storage = AsyncMock()
        with patch("core.storage_adapter.get_storage_adapter", return_value=storage) as get_storage:
            for reference in malformed:
                with self.subTest(reference=reference), self.assertRaises(HTTPException) as raised:
                    await resolve_credential_reference(reference, mode="primary")
                self.assertEqual(raised.exception.status_code, 404)
        get_storage.assert_not_called()
        storage.get_credential.assert_not_called()

    async def test_raw_email_filenames_are_not_an_existence_oracle(self):
        with patch(
            "core.storage_adapter.get_storage_adapter", new_callable=AsyncMock
        ) as get_storage:
            for filename in ("someone42@example.com.json", "người42@example.com.json"):
                with self.subTest(filename=filename), self.assertRaises(HTTPException) as raised:
                    await resolve_credential_reference(filename, mode="primary")
                self.assertEqual(raised.exception.status_code, 404)
                self.assertEqual(raised.exception.detail, "Credential does not exist.")
        get_storage.assert_not_awaited()

    async def test_actual_reserved_prefix_filename_is_addressable_only_by_its_own_alias(self):
        actual = "credref-v1-" + "1" * 64 + ".json"
        key = b"k" * 32
        alias = credential_privacy.credential_reference(actual, key)
        self.assertNotEqual(alias, actual)
        storage = AsyncMock()
        storage.get_config.return_value = base64.urlsafe_b64encode(key).decode()
        storage.list_credentials.return_value = [actual]
        with patch("core.storage_adapter.get_storage_adapter", return_value=storage):
            self.assertEqual(await resolve_credential_reference(alias, mode="primary"), actual)
            with self.assertRaises(HTTPException) as raised:
                await resolve_credential_reference(actual, mode="primary")
        self.assertEqual(raised.exception.status_code, 404)
        storage.get_credential.assert_not_awaited()
        storage.store_credential.assert_not_awaited()

    async def test_missing_or_corrupt_persisted_key_fails_closed_without_writes(self):
        bad_keys = (
            None,
            "",
            "!" * 44,
            "k" * 44,
            42,
            base64.urlsafe_b64encode(b"k" * 31).decode(),
            base64.urlsafe_b64encode(b"k" * 33).decode(),
        )
        for encoded in bad_keys:
            storage = AsyncMock()
            storage.get_config.return_value = encoded
            with self.subTest(encoded=encoded), self.assertRaises(HTTPException) as raised:
                await credential_reference_key(storage)
            self.assertEqual(raised.exception.status_code, 503)
            storage.set_config.assert_not_awaited()
            storage.store_credential.assert_not_awaited()

    async def test_alias_is_stable_across_independent_storage_instances(self):
        filename = "someone42@example.com.json"
        key = b"k" * 32
        alias = credential_privacy.credential_reference(filename, key)
        for mode in ("primary", "code_assist"):
            storage = AsyncMock()
            storage.get_config.return_value = base64.urlsafe_b64encode(key).decode()
            storage.list_credentials.return_value = [filename]
            with patch("core.storage_adapter.get_storage_adapter", return_value=storage):
                loaded_key = await credential_reference_key()
                self.assertEqual(
                    credential_privacy.credential_reference(filename, loaded_key), alias
                )
                self.assertEqual(await resolve_credential_reference(alias, mode=mode), filename)
            storage.list_credentials.assert_awaited_once_with(mode=mode)

    async def test_alias_resolution_never_searches_another_mode(self):
        alias = credential_privacy.credential_reference("someone42@example.com.json", b"k" * 32)
        storage = AsyncMock()
        storage.get_config.return_value = base64.urlsafe_b64encode(b"k" * 32).decode()
        storage.list_credentials.return_value = []
        with patch("core.storage_adapter.get_storage_adapter", return_value=storage):
            with self.assertRaises(HTTPException) as raised:
                await resolve_credential_reference(alias, mode="code_assist")
        self.assertEqual(raised.exception.status_code, 404)
        storage.list_credentials.assert_awaited_once_with(mode="code_assist")

    async def test_ambiguous_inventory_reference_fails_closed(self):
        filename = "someone42@example.com.json"
        alias = credential_privacy.credential_reference(filename, b"k" * 32)
        storage = AsyncMock()
        storage.get_config.return_value = base64.urlsafe_b64encode(b"k" * 32).decode()
        storage.list_credentials.return_value = [filename, filename]
        with patch("core.storage_adapter.get_storage_adapter", return_value=storage):
            with self.assertRaises(HTTPException) as raised:
                await resolve_credential_reference(alias, mode="primary")
        self.assertEqual(raised.exception.status_code, 404)
        storage.get_credential.assert_not_awaited()

    async def test_authorization_denial_precedes_any_alias_storage_scan(self):
        app = FastAPI()
        app.include_router(credentials.router, prefix="/api/credentials")
        viewer = ManagementPrincipal.oidc_user(
            issuer="https://idp.example",
            subject="viewer",
            role=ManagementRole.VIEWER,
        )
        token = _VerifiedPanelToken("test-session", viewer)
        alias = credential_privacy.credential_reference("someone42@example.com.json", b"k" * 32)
        with (
            patch("core.utils.verify_panel_token_value", AsyncMock(return_value=token)),
            patch(
                "core.storage_adapter.get_storage_adapter", new_callable=AsyncMock
            ) as shared_storage,
            patch.object(
                credentials, "get_storage_adapter", new_callable=AsyncMock
            ) as route_storage,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                for path, method, body in (
                    (f"/email/{alias}?mode=provider", "GET", None),
                    ("/action?mode=provider", "POST", {"filename": alias, "action": "disable"}),
                ):
                    response = await client.request(
                        method,
                        f"/api/credentials{path}",
                        json=body,
                        headers={"Authorization": "Bearer test-session"},
                    )
                    self.assertEqual(response.status_code, 403)
                    self.assertNotIn("someone42@example.com", response.text)
        shared_storage.assert_not_awaited()
        route_storage.assert_not_awaited()

    async def test_http_status_and_usage_keys_hide_original_inventory_names(self):
        app = FastAPI()
        app.include_router(credentials.router, prefix="/api/credentials")
        app.include_router(usage_routes.router)
        app.dependency_overrides[verify_panel_token] = lambda: "owner"
        filename = "someone42@example.com.json"
        expected_alias = credential_privacy.credential_reference(filename, b"k" * 32)
        storage = AsyncMock()
        storage.get_config.return_value = base64.urlsafe_b64encode(b"k" * 32).decode()
        with (
            patch("core.storage_adapter.get_storage_adapter", return_value=storage),
            patch.object(
                credentials,
                "get_creds_status_common",
                AsyncMock(
                    return_value={
                        "items": [{"filename": filename, "user_email": "so***42@example.com"}],
                    }
                ),
            ),
            patch.object(
                usage_routes,
                "get_stats_for_period",
                AsyncMock(
                    return_value={
                        filename: {
                            "calls": 2,
                            "successful_calls": 2,
                            "provider": "google_antigravity",
                        },
                    }
                ),
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                status = await client.get("/api/credentials/status?mode=provider")
                self.assertEqual(status.status_code, 200)
                self.assertEqual(status.json()["items"][0]["filename"], expected_alias)
                self.assertNotIn("someone42@example.com", status.text)
                for route in ("/api/usage/stats", "/api/usage/stats/page"):
                    response = await client.get(route)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(list(response.json()["data"]), [expected_alias])
                    self.assertNotIn("someone42@example.com", response.text)
                    self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_http_action_resolves_only_the_selected_storage_key(self):
        app = FastAPI()
        app.include_router(credentials.router, prefix="/api/credentials")
        app.dependency_overrides[verify_panel_token] = lambda: "owner"
        filename = "someone42@example.com.json"
        alias = credential_privacy.credential_reference(filename, b"k" * 32)
        content = {"provider": "google_antigravity", "user_email": "someone42@example.com"}
        storage = AsyncMock()
        storage.get_config.return_value = base64.urlsafe_b64encode(b"k" * 32).decode()
        storage.list_credentials.return_value = ["other77@example.com.json", filename]
        storage.get_credential.return_value = content
        with (
            patch("core.storage_adapter.get_storage_adapter", return_value=storage),
            patch.object(credentials, "get_storage_adapter", return_value=storage),
            patch.object(
                credentials,
                "_execute_credential_action",
                AsyncMock(
                    return_value={
                        "success": True,
                        "filename": filename,
                    }
                ),
            ) as execute,
            patch.object(credentials, "record_durable_credential_mutation", new_callable=AsyncMock),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/credentials/action?mode=provider",
                    json={
                        "filename": alias,
                        "action": "disable",
                    },
                )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["filename"], alias)
        execute.assert_awaited_once_with(storage, filename, content, "disable", mode="primary")
        storage.get_credential.assert_awaited_once_with(filename, mode="primary")
        storage.store_credential.assert_not_awaited()
        self.assertEqual(content["user_email"], "someone42@example.com")
