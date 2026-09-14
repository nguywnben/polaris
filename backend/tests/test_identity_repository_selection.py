"""Storage backend selection tests for durable identity repositories."""

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


class IdentityRepositorySelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_forwards_repository_creation_to_selected_backend(self):
        expected_repository = object()
        backend = Mock()
        backend.create_identity_repository = AsyncMock(return_value=expected_repository)
        adapter = StorageAdapter()
        adapter._backend = backend
        adapter._initialized = True

        repository = await adapter.create_identity_repository()

        self.assertIs(repository, expected_repository)
        backend.create_identity_repository.assert_awaited_once_with()

    async def test_sqlite_manager_constructs_and_initializes_repository(self):
        manager = SQLiteManager()
        manager._db_path = "credentials.db"
        manager._initialized = True
        repository = Mock()
        repository.initialize = AsyncMock()

        with patch(
            "core.storage.identity_sqlite.SQLiteIdentityRepository", return_value=repository
        ) as repository_class:
            selected = await manager.create_identity_repository()

        repository_class.assert_called_once_with("credentials.db")
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
            "core.storage.identity_postgresql.PostgreSQLIdentityRepository",
            return_value=repository,
        ) as repository_class:
            selected = await manager.create_identity_repository()

        repository_class.assert_called_once_with(pool)
        repository.initialize.assert_awaited_once_with()
        self.assertIs(selected, repository)

    async def test_mongodb_manager_reuses_dedicated_collection_and_initializes_repository(self):
        manager = MongoDBManager()
        collection = object()
        manager._db = {"management_identity_state": collection}
        manager._initialized = True
        repository = Mock()
        repository.initialize = AsyncMock()

        with patch(
            "core.storage.identity_mongodb.MongoDBIdentityRepository",
            return_value=repository,
        ) as repository_class:
            selected = await manager.create_identity_repository()

        repository_class.assert_called_once_with(collection)
        repository.initialize.assert_awaited_once_with()
        self.assertIs(selected, repository)

    async def test_uninitialized_managers_fail_closed(self):
        for manager in (SQLiteManager(), PostgreSQLManager(), MongoDBManager()):
            with self.subTest(manager=type(manager).__name__):
                with self.assertRaises(RuntimeError):
                    await manager.create_identity_repository()


if __name__ == "__main__":
    unittest.main()
