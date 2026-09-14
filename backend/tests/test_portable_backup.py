"""Portable SQLite backup, validation, restore, and sanitized-export contracts."""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import sqlite3
import sys
import unittest
import uuid
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.encrypted_backup import decrypt_bytes, encrypt_bytes
from core.portable_backup import (
    BackupArchiveError,
    BackupConflictError,
    BackupRestoreError,
    PortableBackupService,
    RestoreConflictPolicy,
)
from core.storage.sqlite_manager import SQLiteManager

PASSPHRASE = "portable backup test passphrase"
GOLDEN_CONTRACT = BACKEND_DIR / "tests" / "fixtures" / "p1_4_golden_archive_contract.json"


async def _initialize_state(root: Path, marker: str) -> None:
    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
    with patch.dict(os.environ, {"CREDENTIALS_DIR": str(root)}):
        manager = SQLiteManager()
        await manager.initialize()
        await manager.create_audit_repository(cursor_signing_key=b"a" * 32)
        await manager.create_identity_repository()
        await manager.create_request_trace_repository(cursor_signing_key=b"b" * 32)
        await manager.create_usage_ledger_repository()
        await manager.store_credential(
            f"{marker}.json",
            {
                "provider": "openai_platform",
                "credential_type": "api_key",
                "api_key": f"sk-live-{marker}-must-not-leak",
            },
            mode="primary",
        )
        await manager.set_config("api_key", f"sk-polaris-{marker}-root-secret")
        await manager.set_config("panel_password", f"scrypt${marker}-password-hash")
        await manager.set_config("routing_strategy", marker)
        await manager.set_config(
            "virtual_model_pool",
            {
                "alias": "polaris",
                "strategy": "priority_fallback",
                "selected_models": ["gpt-test"],
                "enabled": True,
            },
        )
        await manager.set_config(
            "quality_policy_document",
            {"schema_version": 1, "revision": 1, "profile": "balanced"},
        )
        await manager.set_config(
            "virtual_keys",
            [
                {
                    "schema_version": 2,
                    "id": f"vk_{marker}",
                    "name": "Automation",
                    "key_hash": f"scrypt$virtual-{marker}-hash",
                    "key_preview": "sk-polaris-vk-...abcd",
                    "enabled": True,
                }
            ],
        )
        await manager.close()


def _read_config(database: Path, key: str) -> object:
    with closing(sqlite3.connect(database)) as connection:
        row = connection.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def _rewrite_archive(encrypted: bytes, transform) -> bytes:
    source = io.BytesIO(decrypt_bytes(encrypted, PASSPHRASE))
    output = io.BytesIO()
    with (
        zipfile.ZipFile(source, "r") as archive,
        zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as rewritten,
    ):
        for entry in archive.infolist():
            transformed = transform(entry.filename, archive.read(entry))
            if transformed is not None:
                name, data = transformed
                rewritten.writestr(name, data)
    return encrypt_bytes(output.getvalue(), PASSPHRASE)


class PortableBackupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        test_root = Path(os.environ["CREDENTIALS_DIR"]).parent
        test_root.mkdir(parents=True, exist_ok=True)
        base = test_root / f"portable-backup-{uuid.uuid4().hex}"
        base.mkdir()
        self._base = base
        self.source = base / "source"
        self.destination = base / "destination"
        await _initialize_state(self.source, "source")
        await _initialize_state(self.destination, "destination")
        self.source_service = PortableBackupService(
            self.source / "credentials.db",
            credentials_dir=self.source,
            application_version="1.4.0",
        )
        self.destination_service = PortableBackupService(
            self.destination / "credentials.db",
            credentials_dir=self.destination,
            application_version="1.4.0",
        )

    async def asyncTearDown(self) -> None:
        shutil.rmtree(self._base, ignore_errors=True)

    async def test_encrypted_roundtrip_restores_routing_access_and_credentials(self) -> None:
        artifact = await self.source_service.create_backup(PASSPHRASE)
        plan = await self.destination_service.validate_restore(
            artifact.content,
            PASSPHRASE,
            conflict_policy=RestoreConflictPolicy.REPLACE,
        )

        self.assertTrue(plan.compatible)
        self.assertEqual(plan.archive_version, 1)
        self.assertIn("credentials", plan.components)
        self.assertNotIn("raw_logs", plan.components)
        result = await self.destination_service.restore(
            artifact.content,
            PASSPHRASE,
            conflict_policy=RestoreConflictPolicy.REPLACE,
        )

        self.assertTrue(result.restored)
        self.assertTrue(result.pre_restore_snapshot_id.startswith("pre-restore-"))
        self.assertEqual(
            _read_config(self.destination / "credentials.db", "routing_strategy"),
            "source",
        )
        self.assertEqual(
            _read_config(self.destination / "credentials.db", "api_key"),
            "sk-polaris-source-root-secret",
        )
        with closing(sqlite3.connect(self.destination / "credentials.db")) as connection:
            credential = connection.execute(
                "SELECT credential_data FROM primary_credentials WHERE filename = ?",
                ("source.json",),
            ).fetchone()
        self.assertIn("sk-live-source-must-not-leak", credential[0])
        self.assertEqual(len(list((self.destination / "backups").glob("*.ogb"))), 1)

    async def test_golden_archive_contract_matches_versioned_fixture(self) -> None:
        artifact = await self.source_service.create_backup(PASSPHRASE)
        expected = json.loads(GOLDEN_CONTRACT.read_text(encoding="utf-8"))
        with zipfile.ZipFile(io.BytesIO(decrypt_bytes(artifact.content, PASSPHRASE))) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            actual = {
                "archive_version": manifest["archive_version"],
                "components": manifest["components"],
                "excluded": manifest["excluded"],
                "format": manifest["format"],
                "members": sorted(archive.namelist()),
                "state_schema_version": manifest["state_schema_version"],
            }

        self.assertEqual(actual, expected)

    async def test_dry_run_and_abort_policy_do_not_mutate_or_snapshot(self) -> None:
        artifact = await self.source_service.create_backup(PASSPHRASE)

        with self.assertRaises(BackupConflictError):
            await self.destination_service.validate_restore(
                artifact.content,
                PASSPHRASE,
                conflict_policy=RestoreConflictPolicy.ABORT_IF_CONFIGURED,
            )

        self.assertEqual(
            _read_config(self.destination / "credentials.db", "routing_strategy"),
            "destination",
        )
        self.assertFalse((self.destination / "backups").exists())

    async def test_corrupted_manifest_hash_fails_before_mutation(self) -> None:
        artifact = await self.source_service.create_backup(PASSPHRASE)

        def corrupt(name: str, data: bytes):
            if name == "state/credentials.db":
                return name, data[:-1] + bytes([data[-1] ^ 1])
            return name, data

        corrupted = _rewrite_archive(artifact.content, corrupt)
        with self.assertRaisesRegex(BackupArchiveError, "hash"):
            await self.destination_service.restore(
                corrupted,
                PASSPHRASE,
                conflict_policy=RestoreConflictPolicy.REPLACE,
            )

        self.assertEqual(
            _read_config(self.destination / "credentials.db", "routing_strategy"),
            "destination",
        )

    async def test_traversal_and_unknown_members_fail_closed(self) -> None:
        artifact = await self.source_service.create_backup(PASSPHRASE)

        def add_traversal(name: str, data: bytes):
            if name == "manifest.json":
                return "../manifest.json", data
            return name, data

        malicious = _rewrite_archive(artifact.content, add_traversal)
        with self.assertRaises(BackupArchiveError):
            await self.destination_service.validate_restore(
                malicious,
                PASSPHRASE,
                conflict_policy=RestoreConflictPolicy.REPLACE,
            )

    async def test_oversized_member_fails_before_reading_database(self) -> None:
        artifact = await self.source_service.create_backup(PASSPHRASE)
        with patch("core.portable_backup.MAX_BACKUP_DATABASE_BYTES", 16):
            with self.assertRaisesRegex(BackupArchiveError, "size"):
                await self.destination_service.validate_restore(
                    artifact.content,
                    PASSPHRASE,
                    conflict_policy=RestoreConflictPolicy.REPLACE,
                )

    async def test_incompatible_schema_fails_closed(self) -> None:
        artifact = await self.source_service.create_backup(PASSPHRASE)

        def alter_manifest(name: str, data: bytes):
            if name == "manifest.json":
                manifest = json.loads(data)
                manifest["state_schema_version"] = 999
                return name, json.dumps(manifest, sort_keys=True).encode()
            return name, data

        incompatible = _rewrite_archive(artifact.content, alter_manifest)
        with self.assertRaisesRegex(BackupArchiveError, "version"):
            await self.destination_service.validate_restore(
                incompatible,
                PASSPHRASE,
                conflict_policy=RestoreConflictPolicy.REPLACE,
            )

    async def test_inert_compatibility_table_does_not_block_core_restore(self) -> None:
        with patch.dict(os.environ, {"CREDENTIALS_DIR": str(self.source)}):
            manager = SQLiteManager()
            await manager.initialize()
            await manager.create_migration_checkpoint_repository()
            await manager.close()
        artifact = await self.source_service.create_backup(PASSPHRASE)

        plan = await self.destination_service.validate_restore(
            artifact.content,
            PASSPHRASE,
            conflict_policy=RestoreConflictPolicy.REPLACE,
        )
        self.assertTrue(plan.compatible)
        self.assertIn("durable_migration_checkpoints", plan.table_counts)

    async def test_unknown_sqlite_table_fails_closed(self) -> None:
        with closing(sqlite3.connect(self.source / "credentials.db")) as connection:
            connection.execute("CREATE TABLE attacker_payload (value TEXT)")
            connection.commit()

        with self.assertRaisesRegex(BackupArchiveError, "unknown table"):
            await self.source_service.create_backup(PASSPHRASE)

    async def test_sqlite_view_or_trigger_fails_closed(self) -> None:
        with closing(sqlite3.connect(self.source / "credentials.db")) as connection:
            connection.execute("CREATE VIEW rogue_view AS SELECT 1 AS value")
            connection.execute(
                "CREATE TRIGGER rogue_trigger AFTER UPDATE ON config BEGIN SELECT 1; END"
            )
            connection.commit()

        with self.assertRaisesRegex(BackupArchiveError, "unsupported schema object"):
            await self.source_service.create_backup(PASSPHRASE)

    async def test_restore_rolls_back_database_when_runtime_reload_fails(self) -> None:
        artifact = await self.source_service.create_backup(PASSPHRASE)
        failing_service = PortableBackupService(
            self.destination / "credentials.db",
            credentials_dir=self.destination,
            application_version="1.4.0",
            reload_callback=self._fail_reload_once(),
        )

        with self.assertRaises(BackupRestoreError):
            await failing_service.restore(
                artifact.content,
                PASSPHRASE,
                conflict_policy=RestoreConflictPolicy.REPLACE,
            )

        self.assertEqual(
            _read_config(self.destination / "credentials.db", "routing_strategy"),
            "destination",
        )

    async def test_request_cancellation_waits_for_consistent_restored_state(self) -> None:
        artifact = await self.source_service.create_backup(PASSPHRASE)
        reload_started = asyncio.Event()

        async def delayed_reload() -> None:
            reload_started.set()
            await asyncio.sleep(0.05)

        service = PortableBackupService(
            self.destination / "credentials.db",
            credentials_dir=self.destination,
            application_version="1.4.0",
            reload_callback=delayed_reload,
        )
        operation = asyncio.create_task(
            service.restore(
                artifact.content,
                PASSPHRASE,
                conflict_policy=RestoreConflictPolicy.REPLACE,
            )
        )
        await reload_started.wait()
        operation.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await operation
        self.assertEqual(
            _read_config(self.destination / "credentials.db", "routing_strategy"),
            "source",
        )

    async def test_sqlite_reload_discards_keys_absent_from_restored_database(self) -> None:
        with patch.dict(os.environ, {"CREDENTIALS_DIR": str(self.destination)}):
            manager = SQLiteManager()
            await manager.initialize()
            await manager.set_config("routing_strategy", "priority")
            with closing(sqlite3.connect(self.destination / "credentials.db")) as connection:
                connection.execute("DELETE FROM config WHERE key = ?", ("routing_strategy",))
                connection.commit()

            self.assertEqual(await manager.get_config("routing_strategy"), "priority")
            await manager.reload_config_cache()
            self.assertIsNone(await manager.get_config("routing_strategy"))
            await manager.close()

    @staticmethod
    def _fail_reload_once():
        attempts = 0

        async def callback() -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("injected reload failure")

        return callback

    async def test_sanitized_export_contains_inventory_but_no_usable_secret(self) -> None:
        exported = json.loads(await self.source_service.create_sanitized_export())
        serialized = json.dumps(exported, sort_keys=True)

        self.assertEqual(exported["format"], "polaris-sanitized-state")
        self.assertEqual(exported["version"], 1)
        self.assertEqual(exported["credentials"]["primary"], 1)
        self.assertEqual(exported["virtual_keys"]["configured"], 1)
        self.assertNotIn("sk-live-source-must-not-leak", serialized)
        self.assertNotIn("sk-polaris-source-root-secret", serialized)
        self.assertNotIn("source-password-hash", serialized)
        self.assertNotIn("virtual-source-hash", serialized)
        self.assertNotIn("key_preview", serialized)


if __name__ == "__main__":
    unittest.main()
