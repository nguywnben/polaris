"""Storage backend selection tests for durable audit repositories."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.storage.mongodb_manager import MongoDBManager
from core.storage.postgresql_manager import PostgreSQLManager
from core.storage.sqlite_manager import SQLiteManager
from core.storage_adapter import StorageAdapter

CURSOR_KEY = b"storage-adapter-audit-cursor-key-32b"


class AuditRepositorySelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_forwards_repository_creation_to_selected_backend(self):
        expected_repository = object()
        backend = Mock()
        backend.create_audit_repository = AsyncMock(return_value=expected_repository)
        adapter = StorageAdapter()
        adapter._backend = backend
        adapter._initialized = True

        repository = await adapter.create_audit_repository(cursor_signing_key=CURSOR_KEY)

        self.assertIs(repository, expected_repository)
        backend.create_audit_repository.assert_awaited_once_with(cursor_signing_key=CURSOR_KEY)

    async def test_sqlite_manager_constructs_and_initializes_repository(self):
        manager = SQLiteManager()
        manager._db_path = "credentials.db"
        manager._initialized = True
        repository = Mock()
        repository.initialize = AsyncMock()

        with patch(
            "core.storage.audit_sqlite.SQLiteAuditRepository",
            return_value=repository,
        ) as repository_class:
            selected = await manager.create_audit_repository(cursor_signing_key=CURSOR_KEY)

        repository_class.assert_called_once_with(
            "credentials.db",
            cursor_signing_key=CURSOR_KEY,
        )
        repository.initialize.assert_awaited_once_with()
        self.assertIs(selected, repository)

    async def test_postgresql_manager_reuses_pool_and_initializes_repository(self):
        manager = PostgreSQLManager()
        pool = object()
        manager._pool = pool
        manager._initialized = True
        repository = Mock()
        repository.initialize = AsyncMock()

        with patch(
            "core.storage.audit_postgresql.PostgreSQLAuditRepository",
            return_value=repository,
        ) as repository_class:
            selected = await manager.create_audit_repository(cursor_signing_key=CURSOR_KEY)

        repository_class.assert_called_once_with(pool, cursor_signing_key=CURSOR_KEY)
        repository.initialize.assert_awaited_once_with()
        self.assertIs(selected, repository)

    async def test_mongodb_manager_reuses_database_and_initializes_repository(self):
        manager = MongoDBManager()
        collection = object()
        manager._db = {"audit_events": collection}
        manager._initialized = True
        repository = Mock()
        repository.initialize = AsyncMock()

        with patch(
            "core.storage.audit_mongodb.MongoAuditRepository",
            return_value=repository,
        ) as repository_class:
            selected = await manager.create_audit_repository(cursor_signing_key=CURSOR_KEY)

        repository_class.assert_called_once_with(collection, cursor_signing_key=CURSOR_KEY)
        repository.initialize.assert_awaited_once_with()
        self.assertIs(selected, repository)

    async def test_uninitialized_managers_fail_closed(self):
        for manager in (SQLiteManager(), PostgreSQLManager(), MongoDBManager()):
            with self.subTest(manager=type(manager).__name__):
                with self.assertRaises(RuntimeError):
                    await manager.create_audit_repository(cursor_signing_key=CURSOR_KEY)


if __name__ == "__main__":
    unittest.main()
