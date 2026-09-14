"""Production contracts for the Core SQLite storage tier."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from core.storage.sqlite_manager import SQLiteManager
from core.storage.sqlite_runtime import SQLITE_BUSY_TIMEOUT_MS, SQLiteIntegrityError, open_sqlite
from support import workspace_temp_directory


class SQLiteProductionStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_corrupt_existing_database_fails_before_schema_migration(self) -> None:
        with workspace_temp_directory() as temp_dir:
            database = Path(temp_dir) / "credentials.db"
            original = b"not-a-sqlite-database\x00production-state"
            database.write_bytes(original)
            manager = SQLiteManager()

            with (
                patch.dict(os.environ, {"CREDENTIALS_DIR": temp_dir}),
                patch.object(
                    manager,
                    "_ensure_schema_compatibility",
                    new=AsyncMock(),
                ) as migrate,
            ):
                with self.assertRaisesRegex(
                    SQLiteIntegrityError,
                    "Restore a verified backup before retrying",
                ):
                    await manager.initialize()

            migrate.assert_not_awaited()
            self.assertEqual(database.read_bytes(), original)
            self.assertFalse(manager._initialized)

    async def test_every_managed_connection_enables_production_pragmas(self) -> None:
        with workspace_temp_directory() as temp_dir:
            database = Path(temp_dir) / "state.db"
            async with open_sqlite(database) as connection:
                foreign_keys = (await (await connection.execute("PRAGMA foreign_keys")).fetchone())[
                    0
                ]
                busy_timeout = (await (await connection.execute("PRAGMA busy_timeout")).fetchone())[
                    0
                ]

            self.assertEqual(foreign_keys, 1)
            self.assertEqual(busy_timeout, SQLITE_BUSY_TIMEOUT_MS)

    async def test_transient_writer_lock_waits_then_commits(self) -> None:
        with workspace_temp_directory() as temp_dir:
            database = Path(temp_dir) / "state.db"
            with closing(sqlite3.connect(database)) as setup:
                setup.execute("CREATE TABLE items (value TEXT NOT NULL)")
                setup.commit()

            blocker = sqlite3.connect(database, isolation_level=None)
            blocker.execute("BEGIN IMMEDIATE")
            attempting_write = asyncio.Event()
            try:

                async def write() -> None:
                    async with open_sqlite(database) as connection:
                        attempting_write.set()
                        await connection.execute("INSERT INTO items VALUES ('saved')")
                        await connection.commit()

                pending = asyncio.create_task(write())
                await asyncio.wait_for(attempting_write.wait(), timeout=1.0)
                await asyncio.sleep(0.05)
                self.assertFalse(pending.done())
                blocker.execute("COMMIT")
                await asyncio.wait_for(pending, timeout=3.0)
            finally:
                blocker.close()

            with closing(sqlite3.connect(database)) as verification:
                self.assertEqual(
                    verification.execute("SELECT value FROM items").fetchall(), [("saved",)]
                )

    async def test_failed_additive_upgrade_rolls_back_before_startup(self) -> None:
        with workspace_temp_directory() as temp_dir:
            database = Path(temp_dir) / "credentials.db"
            with closing(sqlite3.connect(database)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE credentials (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        filename TEXT UNIQUE NOT NULL,
                        credential_data TEXT NOT NULL
                    );
                    CREATE TABLE primary_credentials (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        filename TEXT UNIQUE NOT NULL,
                        credential_data TEXT NOT NULL
                    );
                    """
                )
                connection.commit()

            manager = SQLiteManager()
            with (
                patch.dict(os.environ, {"CREDENTIALS_DIR": temp_dir}),
                patch.object(
                    manager,
                    "_create_tables",
                    new=AsyncMock(side_effect=RuntimeError("injected migration failure")),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "injected migration failure"):
                    await manager.initialize()

            with closing(sqlite3.connect(database)) as verification:
                credential_columns = {
                    row[1]
                    for row in verification.execute("PRAGMA table_info(credentials)").fetchall()
                }
                primary_columns = {
                    row[1]
                    for row in verification.execute(
                        "PRAGMA table_info(primary_credentials)"
                    ).fetchall()
                }
            self.assertEqual(credential_columns, {"id", "filename", "credential_data"})
            self.assertEqual(primary_columns, {"id", "filename", "credential_data"})
            self.assertFalse(manager._initialized)


if __name__ == "__main__":
    unittest.main()
