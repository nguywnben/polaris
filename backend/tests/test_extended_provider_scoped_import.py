"""Selected-provider imports are bounded, offline and never attest authorization."""

import asyncio
import io
import json
import stat
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, UploadFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.panel.providers import extended
from core.provider_registry import EXTENDED_PROVIDERS

KEY = "synthetic-import-secret"


def upload(data, filename="key.json"):
    return UploadFile(filename=filename, file=io.BytesIO(json.dumps(data).encode()))


def archive(entries):
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as output:
        for name, value in entries:
            output.writestr(name, value if isinstance(value, bytes) else json.dumps(value))
    content.seek(0)
    return UploadFile(filename="keys.zip", file=content)


async def import_files(provider, files):
    response = await extended.import_extended_credentials(provider, files, token="test-session")
    return json.loads(response.body)


class ScopedProviderImportTests(unittest.IsolatedAsyncioTestCase):
    def test_prefixed_import_errors_are_localized_without_success_claims(self):
        from core.i18n import MESSAGES, locale_context, translate_text

        for locale in MESSAGES["provider.ext.wrong_import_provider"]:
            with locale_context(locale):
                if locale == "en":
                    continue
                for source, key in (
                    (
                        "Credential belongs to a different provider.",
                        "provider.ext.wrong_import_provider",
                    ),
                    (
                        "Import an API key credential for this provider.",
                        "provider.ext.import_api_key",
                    ),
                ):
                    self.assertEqual(translate_text("file.json: " + source), MESSAGES[key][locale])

    async def test_existing_skip_does_not_claim_its_catalog_or_validation_state(self):
        with patch(
            "core.provider_store.credential_manager.add_primary_credential",
            AsyncMock(return_value={"action": "skipped"}),
        ):
            report = await import_files("kimi", [upload({"api_key": KEY})])
        item = report["results"][0]
        self.assertEqual(item["status"], "skipped")
        self.assertNotIn("validation_status", item)
        self.assertNotIn("model_count", item)

    def test_import_route_is_permission_scoped_and_audited_as_import(self):
        from core.identity import ManagementPermission, ManagementRole, permissions_for_role
        from core.identity.manifest import management_route_manifest
        from core.management_audit import classify_management_mutation

        path = "/api/providers/extended/{provider_id}/credentials/import"
        policy = next(
            (p for p in management_route_manifest() if p.path == path and p.method == "POST"), None
        )
        self.assertIsNotNone(policy)
        self.assertEqual(policy.permission, ManagementPermission.CREDENTIALS_MANAGE)
        self.assertNotIn(policy.permission, permissions_for_role(ManagementRole.VIEWER))
        self.assertNotIn(policy.permission, permissions_for_role(ManagementRole.OPERATOR))
        self.assertIn(policy.permission, permissions_for_role(ManagementRole.SECURITY_ADMIN))
        for provider in EXTENDED_PROVIDERS:
            mutation = classify_management_mutation("POST", path.replace("{provider_id}", provider))
            self.assertIsNotNone(mutation)
            self.assertEqual(mutation.action, "credential.import")

    async def test_all_eight_import_json_and_zip_offline_without_trusting_metadata(self):
        with (
            patch(
                "core.httpx_client.http_client.get_client", side_effect=AssertionError("network")
            ),
            patch(
                "core.provider_store.credential_manager.add_primary_credential",
                AsyncMock(return_value={"action": "created"}),
            ) as save,
        ):
            for provider in EXTENDED_PROVIDERS:
                for zipped in (False, True):
                    with self.subTest(provider=provider, zipped=zipped):
                        data = {
                            "api_key": KEY,
                            "validation_status": "verified",
                            "model_ids": ["forged"],
                            "credential_label": "Work",
                        }
                        if provider == "cloudflare":
                            data["account_id"] = "a" * 32
                        file = archive([("key.json", data)]) if zipped else upload(data)
                        report = await import_files(provider, [file])
                        self.assertEqual(report["uploaded_count"], 1)
                        self.assertEqual(report["error_count"], 0)
                        stored = save.await_args.args[1]
                        self.assertEqual(stored["provider"], provider)
                        self.assertEqual(stored["validation_status"], "unverified")
                        self.assertEqual(stored["model_ids"], [])
                        self.assertEqual(stored["credential_label"], "Work")
                        self.assertEqual(report["results"][0]["validation_status"], "unverified")
                        self.assertNotIn(KEY, json.dumps(report))

    async def test_wrong_provider_and_oauth_entries_do_not_save_or_prevent_valid_entry(self):
        entries = [
            ("wrong.json", {"provider": "kilo", "api_key": KEY}),
            ("oauth.json", {"api_key": KEY, "refresh_token": "oauth-secret"}),
            ("valid.json", {"api_key": KEY}),
        ]
        with patch(
            "core.provider_store.credential_manager.add_primary_credential",
            AsyncMock(return_value={"action": "created"}),
        ) as save:
            report = await import_files("kimi", [archive(entries)])
        self.assertEqual(report["uploaded_count"], 1)
        self.assertEqual(report["error_count"], 2)
        self.assertEqual(save.await_count, 1)
        self.assertNotIn(KEY, json.dumps(report))

    async def test_oauth_type_aliases_are_not_accepted_as_api_key_imports(self):
        with patch(
            "core.provider_store.credential_manager.add_primary_credential",
            AsyncMock(return_value={"action": "created"}),
        ) as save:
            for field in ("type", "auth_kind"):
                report = await import_files("kimi", [upload({"api_key": KEY, field: "oauth"})])
                self.assertEqual(report["error_count"], 1)
        save.assert_not_awaited()

    async def test_aggregate_archive_budget_rejects_entire_batch_before_writes(self):
        with patch(
            "core.provider_store.credential_manager.add_primary_credential", new_callable=AsyncMock
        ) as save:
            files = [
                archive([(f"{n}.json", {"api_key": KEY}) for n in range(251)]) for _ in range(2)
            ]
            with self.assertRaises(HTTPException) as caught:
                await import_files("kimi", files)
            self.assertEqual(caught.exception.status_code, 400)
            # Lower only the test's resource budget to reproduce aggregate size
            # exhaustion without allocating a 25 MiB fixture.
            with patch("core.pool_import.MAX_POOL_UNCOMPRESSED_BYTES", 60):
                with self.assertRaises(HTTPException):
                    await import_files(
                        "kimi",
                        [upload({"api_key": KEY}), archive([("key.json", {"api_key": KEY})])],
                    )
        save.assert_not_awaited()

    async def test_duplicate_connection_skipped_across_json_and_zip(self):
        data = {"api_key": KEY, "organization_id": "first"}
        other = {**data, "organization_id": "second"}
        with patch(
            "core.provider_store.credential_manager.add_primary_credential",
            AsyncMock(return_value={"action": "created"}),
        ) as save:
            report = await import_files(
                "kilo", [upload(data), archive([("same.json", data), ("other.json", other)])]
            )
        self.assertEqual(report["uploaded_count"], 2)
        self.assertEqual(report["skipped_count"], 1)
        self.assertEqual(save.await_count, 2)

    async def test_bad_archive_entries_are_rejected_without_file_extraction(self):
        symlink = zipfile.ZipInfo("link.json")
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        entries = [
            ("../escape.json", {"api_key": KEY}),
            (symlink, {"api_key": KEY}),
            ("bad.json", b"\xff"),
            ("list.json", []),
        ]
        with patch(
            "core.provider_store.credential_manager.add_primary_credential", new_callable=AsyncMock
        ) as save:
            report = await import_files("kimi", [archive(entries)])
        self.assertEqual(report["error_count"], 4)
        save.assert_not_awaited()

    async def test_upload_limits_fail_before_any_persistence(self):
        for files in (
            [],
            [upload({}) for _ in range(101)],
            [UploadFile(filename="bad.json", file=io.BytesIO(b"x" * (2 * 1024 * 1024 + 1)))],
            [upload({}, "key.txt")],
        ):
            with (
                self.subTest(count=len(files)),
                patch(
                    "core.provider_store.credential_manager.add_primary_credential",
                    new_callable=AsyncMock,
                ) as save,
            ):
                with self.assertRaises(HTTPException) as caught:
                    await import_files("kimi", files)
                self.assertEqual(caught.exception.status_code, 400)
                save.assert_not_awaited()

    async def test_storage_errors_are_secret_free_and_cancellation_propagates(self):
        with patch(
            "core.provider_store.credential_manager.add_primary_credential",
            AsyncMock(side_effect=RuntimeError(KEY)),
        ):
            report = await import_files("kimi", [upload({"api_key": KEY})])
        self.assertEqual(report["error_count"], 1)
        self.assertNotIn(KEY, json.dumps(report))
        with patch(
            "core.provider_store.credential_manager.add_primary_credential",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await import_files("kimi", [upload({"api_key": KEY})])

    async def test_unsupported_provider_rejected_and_route_requires_panel_authentication(self):
        with self.assertRaises(HTTPException) as caught:
            await import_files("unknown", [upload({"api_key": KEY})])
        self.assertEqual(caught.exception.status_code, 404)
        route = next(
            route for route in extended.router.routes if route.path.endswith("/credentials/import")
        )
        self.assertTrue(
            any(dep.call is extended.verify_panel_token for dep in route.dependant.dependencies)
        )
