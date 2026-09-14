"""Selected storage backend owns the durable request trace repository."""

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

CURSOR_KEY = b"request-trace-selection-cursor-key-32"


class RequestTraceRepositorySelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_forwards_to_selected_backend(self):
        expected = object()
        backend = Mock()
        backend.create_request_trace_repository = AsyncMock(return_value=expected)
        adapter = StorageAdapter()
        adapter._backend = backend
        adapter._initialized = True

        selected = await adapter.create_request_trace_repository(cursor_signing_key=CURSOR_KEY)

        self.assertIs(selected, expected)
        backend.create_request_trace_repository.assert_awaited_once_with(
            cursor_signing_key=CURSOR_KEY
        )

    async def test_managers_construct_backend_specific_repositories(self):
        cases = (
            (
                SQLiteManager(),
                "core.storage.request_trace_sqlite.SQLiteRequestTraceRepository",
                "credentials.db",
                None,
            ),
            (
                PostgreSQLManager(),
                "core.storage.request_trace_postgresql.PostgreSQLRequestTraceRepository",
                object(),
                None,
            ),
            (
                MongoDBManager(),
                "core.storage.request_trace_mongodb.MongoRequestTraceRepository",
                object(),
                "request_traces",
            ),
        )
        for manager, target, dependency, collection_name in cases:
            with self.subTest(manager=type(manager).__name__):
                manager._initialized = True
                if isinstance(manager, SQLiteManager):
                    manager._db_path = dependency
                elif isinstance(manager, PostgreSQLManager):
                    manager._pool = dependency
                else:
                    manager._db = {collection_name: dependency}
                repository = Mock(initialize=AsyncMock())
                with patch(target, return_value=repository) as repository_class:
                    selected = await manager.create_request_trace_repository(
                        cursor_signing_key=CURSOR_KEY
                    )
                repository_class.assert_called_once_with(dependency, cursor_signing_key=CURSOR_KEY)
                repository.initialize.assert_awaited_once_with()
                self.assertIs(selected, repository)


if __name__ == "__main__":
    unittest.main()
