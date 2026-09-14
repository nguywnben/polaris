"""PostgreSQL/MongoDB boundary parity for W4.13 checkpoint metadata."""

from __future__ import annotations

import json
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

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
    MigrationCheckpoint,
    MigrationPhase,
)
from core.durable_migration_runner import CheckpointRevisionConflict, CheckpointStoreCorrupt
from core.storage.migration_mongodb import MongoMigrationCheckpointRepository
from core.storage.migration_postgresql import PostgreSQLMigrationCheckpointRepository
from core.storage.mongodb_manager import MongoDBManager
from core.storage.postgresql_manager import PostgreSQLManager

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
PLAN_ID = "dmg_0123456789abcdef0123456789abcdef"


def _checkpoint():
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
        phase=MigrationPhase.PLANNED,
        authority=AuthoritySide.SOURCE,
        revision=1,
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
        updated_at=NOW.isoformat(),
    )


class _AcquireContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


class _TransactionContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _PostgreSQLConnection:
    def __init__(self):
        self.executions = []
        self.fetch_results = [[]]
        self.fetchrow_results = []
        self.execute_results = []

    async def execute(self, sql, *args):
        self.executions.append((sql, args))
        return self.execute_results.pop(0) if self.execute_results else "OK"

    async def fetch(self, sql, *args):
        return self.fetch_results.pop(0)

    async def fetchrow(self, sql, *args):
        return self.fetchrow_results.pop(0)

    def transaction(self):
        return _TransactionContext()


class _PostgreSQLPool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _AcquireContext(self.connection)


class PostgreSQLMigrationCheckpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = _PostgreSQLConnection()
        self.repository = PostgreSQLMigrationCheckpointRepository(_PostgreSQLPool(self.connection))
        await self.repository.initialize()

    async def test_schema_is_additive_and_writes_are_parameterized(self):
        with self.assertRaises(ValueError):
            await self.repository.create(replace(_checkpoint(), revision=17))
        await self.repository.create(_checkpoint())
        sql = "\n".join(statement for statement, _args in self.connection.executions)
        args = tuple(value for _sql, values in self.connection.executions for value in values)
        self.assertIn("CREATE TABLE IF NOT EXISTS durable_migration_checkpoints", sql)
        self.assertIn("VALUES ($1, $2, $3)", sql)
        self.assertNotIn(PLAN_ID, sql)
        self.assertIn(PLAN_ID, args)
        self.assertNotIn("DROP ", sql.upper())
        self.assertNotIn("TRUNCATE ", sql.upper())

    async def test_get_revalidates_record_and_cas_normalizes_conflict(self):
        checkpoint = _checkpoint()
        self.connection.fetchrow_results = [
            {"revision": 1, "record_json": json.dumps(checkpoint.to_record())}
        ]
        self.assertEqual(await self.repository.get(PLAN_ID), checkpoint)

        self.connection.execute_results = ["UPDATE 0"]
        with self.assertRaises(CheckpointRevisionConflict):
            await self.repository.compare_and_set(
                replace(checkpoint, revision=2, phase=MigrationPhase.COPYING),
                expected_revision=1,
            )


class _Result:
    def __init__(self, matched_count=1):
        self.matched_count = matched_count


class _Cursor:
    def __init__(self, documents):
        self.documents = documents

    def __aiter__(self):
        async def iterate():
            for document in self.documents:
                yield document

        return iterate()


class _MongoCollection:
    def __init__(self):
        self.indexes = []
        self.documents = []
        self.inserted = []
        self.find_one_results = []
        self.replace_results = []

    async def create_index(self, *args, **kwargs):
        self.indexes.append((args, kwargs))

    def find(self, *_args, **_kwargs):
        return _Cursor(self.documents)

    async def insert_one(self, document):
        self.inserted.append(document)

    async def find_one(self, *_args, **_kwargs):
        return self.find_one_results.pop(0)

    async def replace_one(self, *_args, **_kwargs):
        return self.replace_results.pop(0)


class MongoMigrationCheckpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.collection = _MongoCollection()
        self.repository = MongoMigrationCheckpointRepository(self.collection)
        await self.repository.initialize()

    async def test_index_has_no_ttl_and_document_is_closed_metadata(self):
        checkpoint = _checkpoint()
        with self.assertRaises(ValueError):
            await self.repository.create(replace(checkpoint, revision=17))
        await self.repository.create(checkpoint)
        self.assertTrue(self.collection.indexes)
        self.assertTrue(
            all("expireAfterSeconds" not in kwargs for _args, kwargs in self.collection.indexes)
        )
        document = self.collection.inserted[-1]
        self.assertEqual(set(document), {"_id", "revision", "record_json"})
        self.assertNotIn("payload", document["record_json"])

    async def test_corrupt_document_fails_closed_and_cas_conflict_is_generic(self):
        checkpoint = _checkpoint()
        self.collection.find_one_results = [
            {"_id": PLAN_ID, "revision": 1, "record_json": "{}", "unexpected": True}
        ]
        with self.assertRaises(CheckpointStoreCorrupt):
            await self.repository.get(PLAN_ID)

        updated = replace(checkpoint, phase=MigrationPhase.COPYING, revision=2)
        self.collection.replace_results = [_Result(matched_count=0)]
        with self.assertRaises(CheckpointRevisionConflict):
            await self.repository.compare_and_set(updated, expected_revision=1)


class ExternalMigrationCheckpointSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_managers_reuse_selected_shared_backend_and_initialize(self):
        for manager, module, class_name, expected_arg in (
            (
                PostgreSQLManager(),
                "core.storage.migration_postgresql",
                "PostgreSQLMigrationCheckpointRepository",
                object(),
            ),
            (
                MongoDBManager(),
                "core.storage.migration_mongodb",
                "MongoMigrationCheckpointRepository",
                object(),
            ),
        ):
            repository = Mock()
            repository.initialize = AsyncMock()
            manager._initialized = True
            if isinstance(manager, PostgreSQLManager):
                manager._pool = expected_arg
            else:
                manager._db = {"durable_migration_checkpoints": expected_arg}
            with patch(f"{module}.{class_name}", return_value=repository) as repository_class:
                selected = await manager.create_migration_checkpoint_repository()
            repository_class.assert_called_once_with(expected_arg)
            repository.initialize.assert_awaited_once_with()
            self.assertIs(selected, repository)


if __name__ == "__main__":
    unittest.main()
