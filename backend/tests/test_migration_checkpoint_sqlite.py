"""Durable SQLite checkpoint persistence, CAS, corruption, and restart contract."""

from __future__ import annotations

import dataclasses
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import aiosqlite

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.durable_migration import (
    DURABLE_COPY_FAMILIES,
    DURABLE_MANIFEST_CHECKSUM,
    DURABLE_MANIFEST_VERSION,
    MIGRATION_SCHEMA_VERSION,
    AuthoritySide,
    DurableBackend,
    DurableFamily,
    FamilyProgress,
    HistoricalMigrationCheckpoint,
    MigrationCheckpoint,
    MigrationPhase,
)
from core.durable_migration_runner import (
    CheckpointRevisionConflict,
    CheckpointStoreCorrupt,
)
from core.storage.migration_sqlite import SQLiteMigrationCheckpointRepository
from core.storage.sqlite_manager import SQLiteManager
from core.storage_adapter import StorageAdapter

from backend.tests.support import workspace_temp_directory

NOW = datetime(2026, 8, 29, 11, 0, tzinfo=timezone.utc)
PLAN_ID = "dmg_0123456789abcdef0123456789abcdef"


def _checkpoint(*, revision=1, phase=MigrationPhase.PLANNED, updated_at=NOW):
    return MigrationCheckpoint(
        schema_version=MIGRATION_SCHEMA_VERSION,
        manifest_version=DURABLE_MANIFEST_VERSION,
        manifest_checksum=DURABLE_MANIFEST_CHECKSUM,
        plan_id=PLAN_ID,
        source_backend=DurableBackend.SQLITE,
        target_backend=DurableBackend.POSTGRESQL,
        source_instance_id="ins_11111111111111111111111111111111",
        target_instance_id="ins_22222222222222222222222222222222",
        source_revision=1,
        target_revision=1,
        source_barrier_id="bar_33333333333333333333333333333333",
        phase=phase,
        authority=AuthoritySide.SOURCE,
        revision=revision,
        families=tuple(
            FamilyProgress(
                family=family,
                copy_offset=0,
                copied_count=0,
                copy_complete=False,
                explicitly_empty=family is not DurableFamily.CONFIGURATION,
                source_count=None,
                target_count=None,
                source_checksum=None,
                target_checksum=None,
                verified=False,
            )
            for family in DURABLE_COPY_FAMILIES
        ),
        failure_code=None,
        created_at=NOW.isoformat(),
        updated_at=updated_at.isoformat(),
    )


class SQLiteMigrationCheckpointRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = workspace_temp_directory()
        self.database_path = Path(self.temp.__enter__()) / "credentials.db"
        self.repository = SQLiteMigrationCheckpointRepository(self.database_path)
        await self.repository.initialize()

    async def asyncTearDown(self):
        self.temp.__exit__(None, None, None)

    async def test_create_get_and_restart_preserve_exact_checkpoint(self):
        checkpoint = _checkpoint()
        self.assertEqual(await self.repository.create(checkpoint), checkpoint)
        self.assertEqual(await self.repository.get(PLAN_ID), checkpoint)

        restarted = SQLiteMigrationCheckpointRepository(self.database_path)
        await restarted.initialize()
        self.assertEqual(await restarted.get(PLAN_ID), checkpoint)
        self.assertFalse(hasattr(restarted, "delete"))

    async def test_create_is_unique_and_compare_and_set_is_monotonic(self):
        checkpoint = _checkpoint()
        with self.assertRaises(ValueError):
            await self.repository.create(dataclasses.replace(checkpoint, revision=17))
        await self.repository.create(checkpoint)
        with self.assertRaises(CheckpointRevisionConflict):
            await self.repository.create(checkpoint)

        updated = dataclasses.replace(
            checkpoint,
            phase=MigrationPhase.COPYING,
            revision=2,
            updated_at=(NOW + timedelta(seconds=1)).isoformat(),
        )
        self.assertEqual(
            await self.repository.compare_and_set(updated, expected_revision=1), updated
        )
        with self.assertRaises(CheckpointRevisionConflict):
            await self.repository.compare_and_set(updated, expected_revision=1)
        with self.assertRaises(ValueError):
            await self.repository.compare_and_set(
                dataclasses.replace(updated, revision=4), expected_revision=2
            )

    async def test_historical_v1_checkpoint_survives_repository_restart_as_ineligible(self):
        record = _checkpoint().to_record()
        record["manifest_version"] = 1
        record["manifest_checksum"] = "9" * 64
        record.pop("source_revision")
        record.pop("target_revision")
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                "INSERT INTO durable_migration_checkpoints (plan_id, revision, record_json) "
                "VALUES (?, ?, ?)",
                (PLAN_ID, 1, json.dumps(record)),
            )
            await db.commit()

        restarted = SQLiteMigrationCheckpointRepository(self.database_path)
        await restarted.initialize()
        historical = await restarted.get(PLAN_ID)

        self.assertIsInstance(historical, HistoricalMigrationCheckpoint)
        self.assertFalse(historical.eligible_for_binding)

    async def test_corrupt_unknown_or_contradictory_stored_record_fails_closed(self):
        checkpoint = _checkpoint()
        await self.repository.create(checkpoint)
        corrupt = {**checkpoint.to_record(), "secret": "must-not-be-accepted"}
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                "UPDATE durable_migration_checkpoints SET record_json = ? WHERE plan_id = ?",
                (json.dumps(corrupt), PLAN_ID),
            )
            await db.commit()

        with self.assertRaisesRegex(CheckpointStoreCorrupt, "checkpoint store is invalid"):
            await self.repository.get(PLAN_ID)
        restarted = SQLiteMigrationCheckpointRepository(self.database_path)
        with self.assertRaisesRegex(CheckpointStoreCorrupt, "checkpoint store is invalid"):
            await restarted.initialize()


class MigrationCheckpointSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_forwards_creation_to_selected_backend(self):
        expected = object()
        backend = Mock()
        backend.create_migration_checkpoint_repository = AsyncMock(return_value=expected)
        adapter = StorageAdapter()
        adapter._backend = backend
        adapter._initialized = True

        selected = await adapter.create_migration_checkpoint_repository()

        self.assertIs(selected, expected)
        backend.create_migration_checkpoint_repository.assert_awaited_once_with()

    async def test_sqlite_manager_constructs_and_initializes_repository(self):
        manager = SQLiteManager()
        manager._db_path = "credentials.db"
        manager._initialized = True
        repository = Mock()
        repository.initialize = AsyncMock()

        with patch(
            "core.storage.migration_sqlite.SQLiteMigrationCheckpointRepository",
            return_value=repository,
        ) as repository_class:
            selected = await manager.create_migration_checkpoint_repository()

        repository_class.assert_called_once_with("credentials.db")
        repository.initialize.assert_awaited_once_with()
        self.assertIs(selected, repository)


if __name__ == "__main__":
    unittest.main()
