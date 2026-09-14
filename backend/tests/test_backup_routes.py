"""Authenticated portable-backup API, authorization, and audit contracts."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import UploadFile
from pydantic import SecretStr

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main
from core.identity import ManagementPermission, ManagementRouteTransport, management_route_manifest
from core.management_audit import classify_management_mutation
from core.panel.backup_routes import (
    BackupCreateRequest,
    _reload_restored_runtime,
    create_backup,
    create_sanitized_export,
    restore_backup,
    validate_backup,
)
from core.portable_backup import (
    BackupArchiveError,
    BackupArtifact,
    BackupBackendError,
    BackupConflictError,
    BackupSizeError,
    RestoreConflictPolicy,
    RestorePlan,
    RestoreResult,
)


def _body(response) -> dict:
    return json.loads(response.body)


class _BackupService:
    def __init__(self) -> None:
        self.create_backup = AsyncMock(
            return_value=BackupArtifact(
                content=b"encrypted-backup",
                filename="polaris-backup-20260909T000000Z.ogb",
                created_at="2026-09-09T00:00:00+00:00",
                manifest={"archive_version": 1},
            )
        )
        self.validate_restore = AsyncMock(
            return_value=RestorePlan(
                compatible=True,
                archive_version=1,
                source_application_version="1.4.0",
                created_at="2026-09-09T00:00:00+00:00",
                conflict_policy="replace",
                components=("configuration", "credentials"),
                excluded=("raw_logs",),
                table_counts={"config": 2},
            )
        )
        self.restore = AsyncMock(
            return_value=RestoreResult(
                restored=True,
                pre_restore_snapshot_id="pre-restore-safe-id",
                source_application_version="1.4.0",
                restored_at="2026-09-09T00:01:00+00:00",
                components=("configuration", "credentials"),
            )
        )
        self.create_sanitized_export = AsyncMock(return_value=b'{"restorable":false}')


class BackupRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_routes_are_authenticated_and_use_least_privilege_permissions(self) -> None:
        paths = main.app.openapi()["paths"]
        expected = {
            ("POST", "/api/backups"): ManagementPermission.BACKUP_EXPORT,
            ("POST", "/api/backups/validate"): ManagementPermission.BACKUP_RESTORE,
            ("POST", "/api/backups/restore"): ManagementPermission.BACKUP_RESTORE,
            ("POST", "/api/backups/sanitized-export"): ManagementPermission.BACKUP_EXPORT,
        }
        actual = {
            (entry.method, entry.path): entry.permission
            for entry in management_route_manifest()
            if entry.transport is ManagementRouteTransport.HTTP
        }
        self.assertTrue(expected.keys() <= actual.keys())
        for route, permission in expected.items():
            self.assertEqual(actual[route], permission)
        self.assertIn("/api/backups", paths)

        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            responses = (
                await client.post("/api/backups", json={"passphrase": "long enough secret"}),
                await client.post("/api/backups/sanitized-export"),
                await client.post(
                    "/api/backups/validate",
                    data={"passphrase": "long enough secret", "conflict_policy": "replace"},
                    files={"archive": ("backup.ogb", b"archive")},
                ),
                await client.post(
                    "/api/backups/restore",
                    data={"passphrase": "long enough secret", "conflict_policy": "replace"},
                    files={"archive": ("backup.ogb", b"archive")},
                ),
            )
        self.assertEqual([response.status_code for response in responses], [401, 401, 401, 401])

    async def test_create_returns_non_cacheable_encrypted_attachment(self) -> None:
        service = _BackupService()
        with patch(
            "core.panel.backup_routes.get_portable_backup_service",
            new=AsyncMock(return_value=service),
        ):
            response = await create_backup(
                payload=BackupCreateRequest(passphrase="long enough secret"),
                token="session",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"encrypted-backup")
        self.assertEqual(response.media_type, "application/vnd.polaris.backup+json")
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        service.create_backup.assert_awaited_once_with("long enough secret")

    async def test_validate_is_dry_run_and_maps_the_explicit_policy(self) -> None:
        service = _BackupService()
        upload = UploadFile(filename="anything.ogb", file=io.BytesIO(b"encrypted"))
        with patch(
            "core.panel.backup_routes.get_portable_backup_service",
            new=AsyncMock(return_value=service),
        ):
            response = await validate_backup(
                archive=upload,
                passphrase=SecretStr("long enough secret"),
                conflict_policy=RestoreConflictPolicy.REPLACE,
                token="session",
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(_body(response)["dry_run"])
        service.validate_restore.assert_awaited_once_with(
            b"encrypted",
            "long enough secret",
            conflict_policy=RestoreConflictPolicy.REPLACE,
        )
        service.restore.assert_not_awaited()

    async def test_restore_returns_snapshot_reference_and_reauthentication_notice(self) -> None:
        service = _BackupService()
        upload = UploadFile(filename="backup.ogb", file=io.BytesIO(b"encrypted"))
        with patch(
            "core.panel.backup_routes.get_portable_backup_service",
            new=AsyncMock(return_value=service),
        ):
            response = await restore_backup(
                archive=upload,
                passphrase=SecretStr("long enough secret"),
                conflict_policy=RestoreConflictPolicy.REPLACE,
                token="session",
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(_body(response)["session_reauthentication_required"])
        self.assertEqual(_body(response)["pre_restore_snapshot_id"], "pre-restore-safe-id")

    async def test_sanitized_export_is_a_distinct_non_restorable_attachment(self) -> None:
        service = _BackupService()
        with patch(
            "core.panel.backup_routes.get_portable_backup_service",
            new=AsyncMock(return_value=service),
        ):
            response = await create_sanitized_export(token="session")

        self.assertEqual(response.media_type, "application/json")
        self.assertEqual(response.headers["x-polaris-restorable"], "false")
        self.assertIn("sanitized", response.headers["content-disposition"])

    async def test_failures_use_stable_secret_free_errors(self) -> None:
        scenarios = (
            (BackupBackendError("C:/private/database.db"), 409, "backup_backend_unsupported"),
            (BackupConflictError("secret conflict"), 409, "backup_restore_conflict"),
            (BackupSizeError("large secret archive"), 413, "backup_archive_too_large"),
            (BackupArchiveError("wrong password secret"), 400, "backup_archive_invalid"),
        )
        for error, status, code in scenarios:
            service = _BackupService()
            service.validate_restore.side_effect = error
            upload = UploadFile(filename="backup.ogb", file=io.BytesIO(b"encrypted"))
            with (
                self.subTest(code=code),
                patch(
                    "core.panel.backup_routes.get_portable_backup_service",
                    new=AsyncMock(return_value=service),
                ),
            ):
                response = await validate_backup(
                    archive=upload,
                    passphrase=SecretStr("long enough secret"),
                    conflict_policy=RestoreConflictPolicy.REPLACE,
                    token="session",
                )
            self.assertEqual(response.status_code, status)
            self.assertEqual(_body(response)["error"]["code"], code)
            self.assertNotIn("secret", response.body.decode())
            self.assertNotIn("private", response.body.decode())

    def test_backup_mutations_have_dedicated_audit_semantics(self) -> None:
        create = classify_management_mutation("POST", "/api/backups")
        restore = classify_management_mutation("POST", "/api/backups/restore")
        sanitized = classify_management_mutation("POST", "/api/backups/sanitized-export")

        self.assertEqual((create.action, create.change_codes), ("backup.create", ("created",)))
        self.assertEqual(create.target_identifier, "portable-state")
        self.assertEqual(
            (restore.action, restore.change_codes),
            ("backup.restore", ("restored",)),
        )
        self.assertEqual(
            (sanitized.action, sanitized.change_codes),
            ("backup.export", ("exported",)),
        )
        self.assertIsNone(classify_management_mutation("POST", "/api/backups/validate"))

    async def test_runtime_reload_rebinds_state_derived_services(self) -> None:
        storage = AsyncMock()
        patches = {
            "core.identity.close_oidc_login_service": AsyncMock(),
            "core.usage_ledger_service.close_usage_ledger_service": AsyncMock(),
            "core.request_trace_service.close_request_trace_service": AsyncMock(),
            "core.identity.close_session_service": AsyncMock(),
            "core.audit_service.close_audit_service": AsyncMock(),
            "core.credential_manager.credential_manager.close": AsyncMock(),
            "config.reload_config": AsyncMock(),
            "core.virtual_keys.virtual_key_manager.reset_runtime_state": Mock(),
            "core.virtual_keys.virtual_key_manager.invalidate": Mock(),
            "core.model_pool.model_catalog_service.invalidate": AsyncMock(),
            "core.response_cache.response_cache_coordinator.invalidate": AsyncMock(),
            "core.credential_manager.credential_manager.initialize": AsyncMock(),
            "core.audit_service.initialize_audit_service": AsyncMock(),
            "core.identity.initialize_session_service": AsyncMock(),
            "core.request_trace_service.initialize_request_trace_service": AsyncMock(),
            "core.usage_ledger_service.initialize_usage_ledger_service": AsyncMock(),
            "core.runtime_lifecycle.get_runtime_session_kwargs": Mock(
                return_value={"coordination": object(), "fencing_epoch": 1, "hmac_key": b"x" * 32}
            ),
        }
        stack = ExitStack()
        try:
            mocks = {
                path: stack.enter_context(patch(path, replacement))
                for path, replacement in patches.items()
            }
            await _reload_restored_runtime(storage)
        finally:
            stack.close()

        storage.reload_config_cache.assert_awaited_once()
        mocks["core.audit_service.initialize_audit_service"].assert_awaited_once_with(storage)
        mocks["core.identity.initialize_session_service"].assert_awaited_once()
        mocks[
            "core.request_trace_service.initialize_request_trace_service"
        ].assert_awaited_once_with(storage)
        mocks["core.usage_ledger_service.initialize_usage_ledger_service"].assert_awaited_once_with(
            storage
        )
        mocks["core.response_cache.response_cache_coordinator.invalidate"].assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
