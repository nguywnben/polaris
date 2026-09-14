"""Storage backend selection must be explicit and fail closed."""

from __future__ import annotations

import builtins
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.storage_adapter import StorageAdapter


class PostgreSQLBackend:
    def __init__(self) -> None:
        self._dsn = "postgresql://owner:super-secret@database/polaris"

    async def get_database_info(self):
        return {
            "dsn": self._dsn,
            "password": "super-secret",
            "server_version": "test-only",
        }


class FailingPostgreSQLBackend(PostgreSQLBackend):
    async def get_database_info(self):
        raise RuntimeError(f"could not connect with {self._dsn}")


class StorageBackendSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_sqlite_selection_does_not_import_optional_drivers(self):
        from core.storage import sqlite_manager

        adapter = StorageAdapter()
        backend = AsyncMock()
        original_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.endswith(("storage.postgresql_manager", "storage.mongodb_manager")):
                raise AssertionError(f"default startup imported optional driver: {name}")
            return original_import(name, globals, locals, fromlist, level)

        with (
            patch.dict(os.environ, {"POSTGRESQL_URI": "", "MONGODB_URI": ""}),
            patch.object(sqlite_manager, "SQLiteManager", return_value=backend),
            patch("builtins.__import__", side_effect=guarded_import),
        ):
            await adapter.initialize()

        backend.initialize.assert_awaited_once_with()
        self.assertIs(adapter._backend, backend)

    async def test_backend_info_never_exposes_postgresql_connection_metadata(self):
        adapter = StorageAdapter()
        adapter._backend = PostgreSQLBackend()
        adapter._initialized = True

        info = await adapter.get_backend_info()

        self.assertEqual(info, {"backend_type": "postgresql", "initialized": True})
        self.assertNotIn("super-secret", repr(info))

    async def test_backend_info_does_not_expose_database_error_details(self):
        adapter = StorageAdapter()
        adapter._backend = FailingPostgreSQLBackend()
        adapter._initialized = True

        info = await adapter.get_backend_info()

        self.assertEqual(info, {"backend_type": "postgresql", "initialized": True})
        self.assertNotIn("super-secret", repr(info))

    async def test_rejects_ambiguous_external_storage_configuration(self):
        adapter = StorageAdapter()
        with patch.dict(
            os.environ,
            {
                "POSTGRESQL_URI": "postgresql://database",
                "MONGODB_URI": "mongodb://database",
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "Configure only one external storage"):
                await adapter.initialize()

    async def test_postgresql_failure_does_not_fallback_to_sqlite(self):
        from core.storage import postgresql_manager

        adapter = StorageAdapter()
        backend = AsyncMock()
        backend.initialize.side_effect = RuntimeError(
            "postgresql://owner:super-secret@database/polaris"
        )

        with (
            patch.dict(os.environ, {"POSTGRESQL_URI": "postgresql://database", "MONGODB_URI": ""}),
            patch.object(postgresql_manager, "PostgreSQLManager", return_value=backend),
            patch("core.storage.sqlite_manager.SQLiteManager") as sqlite_manager,
            patch("core.storage_adapter.log") as storage_log,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "PostgreSQL storage backend is unavailable.*requirements.lock"
            ):
                await adapter.initialize()

        backend.close.assert_awaited_once_with()
        sqlite_manager.assert_not_called()
        self.assertIsNone(adapter._backend)
        self.assertFalse(adapter._initialized)
        self.assertNotIn("super-secret", " ".join(str(call) for call in storage_log.mock_calls))

    async def test_mongodb_failure_does_not_fallback_to_sqlite(self):
        from core.storage import mongodb_manager

        adapter = StorageAdapter()
        backend = AsyncMock()
        backend.initialize.side_effect = RuntimeError(
            "mongodb://owner:super-secret@database/polaris"
        )

        with (
            patch.dict(os.environ, {"POSTGRESQL_URI": "", "MONGODB_URI": "mongodb://database"}),
            patch.object(mongodb_manager, "MongoDBManager", return_value=backend),
            patch("core.storage.sqlite_manager.SQLiteManager") as sqlite_manager,
            patch("core.storage_adapter.log") as storage_log,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "MongoDB storage backend is unavailable.*requirements.lock"
            ):
                await adapter.initialize()

        backend.close.assert_awaited_once_with()
        sqlite_manager.assert_not_called()
        self.assertIsNone(adapter._backend)
        self.assertFalse(adapter._initialized)
        self.assertNotIn("super-secret", " ".join(str(call) for call in storage_log.mock_calls))


if __name__ == "__main__":
    unittest.main()
