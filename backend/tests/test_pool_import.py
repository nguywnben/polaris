"""Tests for mixed-provider credential pool restore archives."""

from __future__ import annotations

import io
import json
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, UploadFile

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.credential_pool import upsert_credential_by_email
from core.credential_pool_mutation import CredentialPoolRecord
from core.google_ai_studio import GoogleAIStudioValidation
from core.panel.credential_operations import download_all_creds_common
from core.panel.credentials import download_cred_file, import_pool_credentials
from core.pool_import import (
    PoolImportError,
    classify_pool_credential,
    extract_pool_archive,
    restore_pool_archive,
)
from core.provider_registry import (
    GOOGLE_AI_STUDIO,
    GOOGLE_ANTIGRAVITY,
    OPENAI,
    XAI,
    XAI_CONSOLE,
    antigravity_account_fingerprint,
    build_antigravity_credential_filename,
    canonicalize_antigravity_credential_filename,
)
from core.xai import XaiValidation


def build_zip(entries: list[tuple[str, object]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries:
            content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            archive.writestr(name, content)
    return buffer.getvalue()


def upload_archive(entries: list[tuple[str, object]]) -> UploadFile:
    return UploadFile(filename="provider_credentials.zip", file=io.BytesIO(build_zip(entries)))


class PoolCredentialClassificationTests(unittest.TestCase):
    def test_classifies_explicit_and_legacy_provider_payloads(self):
        self.assertEqual(
            classify_pool_credential(
                {"provider": "google_ai_studio", "credential_type": "api_key", "api_key": "key"}
            ),
            GOOGLE_AI_STUDIO,
        )
        self.assertEqual(
            classify_pool_credential(
                {"client_id": "id", "client_secret": "secret", "refresh_token": "refresh"}
            ),
            GOOGLE_ANTIGRAVITY,
        )
        self.assertEqual(
            classify_pool_credential(
                {
                    "provider": "xai",
                    "credential_type": "api_key",
                    "api_key": "xai-key",
                }
            ),
            XAI,
        )
        self.assertEqual(
            classify_pool_credential(
                {
                    "provider": "openai",
                    "credential_type": "api_key",
                    "api_key": "sk-openai-key",
                }
            ),
            OPENAI,
        )
        self.assertEqual(
            classify_pool_credential(
                {
                    "provider": "codex",
                    "credential_type": "oauth",
                    "refresh_token": "refresh",
                }
            ),
            OPENAI,
        )
        self.assertEqual(
            classify_pool_credential(
                {
                    "provider": "xai",
                    "credential_type": "oauth",
                    "refresh_token": "refresh",
                }
            ),
            XAI,
        )

    def test_rejects_ambiguous_and_unsupported_payloads(self):
        with self.assertRaisesRegex(PoolImportError, "could not be identified"):
            classify_pool_credential({"token": "access-only"})

        with self.assertRaisesRegex(PoolImportError, "not supported"):
            classify_pool_credential({"provider": "another_provider", "api_key": "key"})

    def test_rejects_payload_that_conflicts_with_explicit_provider(self):
        with self.assertRaisesRegex(PoolImportError, "valid API key credential"):
            classify_pool_credential({"provider": "google_ai_studio", "refresh_token": "refresh"})

    def test_builds_canonical_antigravity_filename(self):
        self.assertEqual(
            antigravity_account_fingerprint(
                {"user_email": " User@Example.com ", "refresh_token": "different-token"}
            ),
            "b4c9a289323b21a0",
        )
        self.assertEqual(
            build_antigravity_credential_filename(
                {"user_email": " User@Example.com ", "refresh_token": "different-token"}
            ),
            "google-antigravity-b4c9a289323b21a0.json",
        )

    def test_converts_legacy_antigravity_filename_without_changing_identity(self):
        self.assertEqual(
            canonicalize_antigravity_credential_filename(
                "provider_root-iterator-kxhgq-1783348337.json",
                {
                    "project_id": "root-iterator-kxhgq",
                    "user_email": "user@example.com",
                },
            ),
            "google-antigravity-b4c9a289323b21a0.json",
        )

    def test_falls_back_to_refresh_token_fingerprint_without_email(self):
        self.assertEqual(
            build_antigravity_credential_filename(
                {"project_id": "shared-project", "refresh_token": "refresh-token-value"}
            ),
            "google-antigravity-e65009f6e0ae9fc2.json",
        )


class PoolArchiveExtractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_mixed_provider_archive(self):
        candidates, errors = await extract_pool_archive(
            upload_archive(
                [
                    (
                        "antigravity.json",
                        {
                            "provider": "google_antigravity",
                            "client_id": "id",
                            "client_secret": "secret",
                            "refresh_token": "refresh",
                        },
                    ),
                    (
                        "nested/ai-studio.json",
                        {
                            "provider": "google_ai_studio",
                            "credential_type": "api_key",
                            "api_key": "google-key",
                        },
                    ),
                    (
                        "nested/xai.json",
                        {
                            "provider": "xai",
                            "credential_type": "api_key",
                            "api_key": "xai-key",
                        },
                    ),
                ]
            )
        )

        self.assertEqual(
            [candidate["provider"] for candidate in candidates],
            [GOOGLE_ANTIGRAVITY, GOOGLE_AI_STUDIO, XAI],
        )
        self.assertEqual(
            [candidate["filename"] for candidate in candidates],
            ["antigravity.json", "ai-studio.json", "xai.json"],
        )
        self.assertEqual(errors, [])

    async def test_retains_valid_entries_and_reports_unsafe_or_invalid_entries(self):
        candidates, errors = await extract_pool_archive(
            upload_archive(
                [
                    (
                        "valid.json",
                        {
                            "client_id": "id",
                            "client_secret": "secret",
                            "refresh_token": "refresh",
                        },
                    ),
                    ("../outside.json", {"provider": "google_ai_studio", "api_key": "key"}),
                    ("broken.json", b"{not-json"),
                ]
            )
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("unsafe path" in item["message"] for item in errors))
        self.assertTrue(any("valid UTF-8 JSON" in item["message"] for item in errors))

    async def test_windows_drive_path_is_rejected(self):
        candidates, errors = await extract_pool_archive(
            upload_archive(
                [
                    (
                        "C:/credentials/key.json",
                        {
                            "provider": GOOGLE_AI_STUDIO,
                            "credential_type": "api_key",
                            "api_key": "test-key",
                        },
                    )
                ]
            )
        )

        self.assertEqual(candidates, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("unsafe path", errors[0]["message"])


class PoolArchiveRestoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_skips_duplicate_ai_studio_keys_within_one_archive(self):
        archive = upload_archive(
            [
                ("first.json", {"provider": "google_ai_studio", "api_key": "same-key"}),
                ("second.json", {"provider": "google_ai_studio", "api_key": "same-key"}),
            ]
        )
        validation = GoogleAIStudioValidation(model_ids=["gemini-test"])

        with (
            patch(
                "core.pool_import.validate_api_key",
                new=AsyncMock(return_value=validation),
            ) as validate_mock,
            patch(
                "core.pool_import.store_google_ai_studio_credential",
                new=AsyncMock(
                    return_value={
                        "action": "created",
                        "filename": "google-ai-studio-test.json",
                        "label": "API key ending -key",
                    }
                ),
            ),
        ):
            result = await restore_pool_archive(archive)

        self.assertEqual(result["uploaded_count"], 1)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(validate_mock.await_count, 1)

    async def test_restores_each_provider_with_its_own_validation_and_deduplication(self):
        archive = upload_archive(
            [
                (
                    "provider_test-project-1234567890.json",
                    {
                        "provider": "google_antigravity",
                        "client_id": "id",
                        "client_secret": "secret",
                        "refresh_token": "refresh-token-value",
                        "project_id": "test-project",
                        "expiry": "2030-01-01T00:00:00+00:00",
                    },
                ),
                (
                    "ai-studio.json",
                    {
                        "provider": "google_ai_studio",
                        "credential_type": "api_key",
                        "api_key": "google-api-key-value",
                    },
                ),
                (
                    "xai.json",
                    {
                        "provider": "xai",
                        "credential_type": "api_key",
                        "api_key": "xai-api-key-value",
                    },
                ),
            ]
        )
        validation = GoogleAIStudioValidation(model_ids=["gemini-test"])
        xai_validation = XaiValidation(model_ids=["grok-test"])

        with (
            patch(
                "core.pool_import.validate_api_key",
                new=AsyncMock(return_value=validation),
            ) as validate_mock,
            patch(
                "core.pool_import.store_google_ai_studio_credential",
                new=AsyncMock(
                    return_value={
                        "action": "updated",
                        "filename": "google-ai-studio-test.json",
                        "label": "API key ending alue",
                    }
                ),
            ) as store_mock,
            patch(
                "core.pool_import.credential_manager.add_primary_credential",
                new=AsyncMock(
                    return_value={
                        "action": "created",
                        "stored": True,
                        "filename": "google-antigravity-e65009f6e0ae9fc2.json",
                        "email": "user@example.com",
                        "message": "Credential added to the pool.",
                    }
                ),
            ) as add_mock,
            patch(
                "core.pool_import.validate_xai_api_key",
                new=AsyncMock(return_value=xai_validation),
            ) as validate_xai_mock,
            patch(
                "core.pool_import.store_xai_api_key_credential",
                new=AsyncMock(
                    return_value={
                        "action": "created",
                        "filename": "xai-grok-test.json",
                        "label": "API key ending alue",
                    }
                ),
            ) as store_xai_mock,
        ):
            result = await restore_pool_archive(archive)

        self.assertEqual(result["uploaded_count"], 3)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(result["providers"][GOOGLE_ANTIGRAVITY]["created"], 1)
        self.assertEqual(result["providers"][GOOGLE_AI_STUDIO]["updated"], 1)
        self.assertEqual(result["providers"][XAI_CONSOLE]["created"], 1)
        self.assertEqual(result["providers"][XAI_CONSOLE]["provider_name"], "SpaceXAI Console")
        self.assertEqual(result["providers"][XAI_CONSOLE]["routing_provider"], XAI)
        validate_mock.assert_awaited_once_with("google-api-key-value")
        store_mock.assert_awaited_once()
        validate_xai_mock.assert_awaited_once_with("xai-api-key-value")
        store_xai_mock.assert_awaited_once()
        add_mock.assert_awaited_once()
        self.assertEqual(
            add_mock.await_args.args[0],
            "google-antigravity-e65009f6e0ae9fc2.json",
        )
        serialized = json.dumps(result)
        self.assertNotIn("google-api-key-value", serialized)
        self.assertNotIn("xai-api-key-value", serialized)
        self.assertNotIn("refresh-token-value", serialized)


class AntigravityStorageFilenameTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolved_email_controls_new_credential_filename(self):
        storage = AsyncMock()
        storage.list_credentials.return_value = []
        storage.store_credential.return_value = True
        storage.update_credential_state.return_value = True
        storage.mutate_credential_pool.side_effect = lambda mode, planner: planner(()).result
        credential = {
            "provider": GOOGLE_ANTIGRAVITY,
            "project_id": "shared-project",
            "client_id": "id",
            "client_secret": "secret",
            "refresh_token": "refresh-token-value",
        }

        with (
            patch(
                "core.credential_pool.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch(
                "core.credential_pool.resolve_credential_email",
                new=AsyncMock(return_value="user@example.com"),
            ),
        ):
            result = await upsert_credential_by_email(
                "provider_shared-project-1234567890.json",
                credential,
                mode="provider",
            )

        self.assertEqual(result["filename"], "google-antigravity-b4c9a289323b21a0.json")
        storage.mutate_credential_pool.assert_awaited_once()

    async def test_same_email_is_kept_separately_for_different_providers(self):
        storage = AsyncMock()
        storage.list_credentials.return_value = ["google-antigravity-existing.json"]
        storage.get_credential.return_value = {
            "provider": GOOGLE_ANTIGRAVITY,
            "credential_type": "oauth",
            "user_email": "user@example.com",
            "expiry": "2030-01-01T00:00:00+00:00",
        }
        storage.get_credential_state.return_value = {"user_email": "user@example.com"}
        storage.store_credential.return_value = True
        storage.update_credential_state.return_value = True
        storage.mutate_credential_pool.side_effect = lambda mode, planner: (
            planner(
                (
                    CredentialPoolRecord(
                        filename="google-antigravity-existing.json",
                        credential_data=storage.get_credential.return_value,
                        user_email="user@example.com",
                        rotation_order=0,
                    ),
                )
            ).result
        )
        incoming = {
            "provider": XAI,
            "credential_type": "oauth",
            "user_email": "user@example.com",
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expiry": "2029-01-01T00:00:00+00:00",
        }

        with patch(
            "core.credential_pool.get_storage_adapter",
            new=AsyncMock(return_value=storage),
        ):
            result = await upsert_credential_by_email(
                "xai-grok-example.json",
                incoming,
                mode="primary",
            )

        self.assertEqual(result["action"], "created")
        self.assertEqual(result["filename"], "xai-grok-example.json")
        storage.mutate_credential_pool.assert_awaited_once()


class PoolImportRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_route_returns_the_service_contract(self):
        archive = upload_archive([])
        expected = {
            "success": True,
            "completed": True,
            "total_count": 0,
            "uploaded_count": 0,
            "skipped_count": 0,
            "error_count": 0,
            "providers": {},
            "results": [],
            "message": "Pool restore complete.",
        }

        with patch(
            "core.panel.credentials.restore_pool_archive",
            new=AsyncMock(return_value=expected),
        ):
            response = await import_pool_credentials(archive=archive, token="test")

        self.assertEqual(json.loads(response.body), expected)

    async def test_route_maps_archive_validation_to_bad_request(self):
        archive = upload_archive([])

        with patch(
            "core.panel.credentials.restore_pool_archive",
            new=AsyncMock(side_effect=PoolImportError("Invalid archive.")),
        ):
            with self.assertRaises(HTTPException) as context:
                await import_pool_credentials(archive=archive, token="test")

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(context.exception.detail, "Invalid archive.")


class AntigravityDownloadFilenameTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.legacy_filename = "provider_test-project-1234567890.json"
        self.canonical_filename = "google-antigravity-b4c9a289323b21a0.json"
        self.credential = {
            "provider": GOOGLE_ANTIGRAVITY,
            "project_id": "test-project",
            "user_email": "user@example.com",
            "client_id": "id",
            "client_secret": "secret",
            "refresh_token": "refresh",
        }

    async def test_pool_zip_uses_canonical_antigravity_filename(self):
        storage = AsyncMock()
        storage.list_credentials.return_value = [self.legacy_filename]
        storage.get_credential.return_value = self.credential

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.deduplicate_credentials_by_account_email",
                new=AsyncMock(return_value={"deleted_count": 0}),
            ),
        ):
            response = await download_all_creds_common(mode="provider")

        with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
            self.assertEqual(archive.namelist(), [self.canonical_filename])

    async def test_pool_zip_keeps_filenames_unique_for_shared_project(self):
        storage = AsyncMock()
        storage.list_credentials.return_value = [
            self.legacy_filename,
            "provider_test-project-1234567891.json",
        ]
        storage.get_credential.side_effect = [
            {**self.credential, "user_email": "first@example.com"},
            {**self.credential, "user_email": "second@example.com"},
        ]

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.deduplicate_credentials_by_account_email",
                new=AsyncMock(return_value={"deleted_count": 0}),
            ),
        ):
            response = await download_all_creds_common(mode="provider")

        with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
            self.assertEqual(
                archive.namelist(),
                [
                    "google-antigravity-f7faa8d2b759b8e4.json",
                    "google-antigravity-27b677683f02ace6.json",
                ],
            )

    async def test_single_download_uses_canonical_antigravity_filename(self):
        storage = AsyncMock()
        storage.get_credential.return_value = self.credential

        with patch(
            "core.panel.credentials.get_storage_adapter",
            new=AsyncMock(return_value=storage),
        ):
            response = await download_cred_file(
                filename=self.legacy_filename,
                token="test",
                mode="provider",
            )

        self.assertEqual(
            response.headers["content-disposition"],
            f"attachment; filename={self.canonical_filename}",
        )


if __name__ == "__main__":
    unittest.main()
