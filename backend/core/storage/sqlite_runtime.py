"""Shared production connection policy for the Core SQLite storage tier."""

from __future__ import annotations

import sqlite3
import time
from contextlib import asynccontextmanager, closing
from os import PathLike
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

SQLITE_BUSY_TIMEOUT_MS = 5_000
SQLITE_BUSY_TIMEOUT_SECONDS = SQLITE_BUSY_TIMEOUT_MS / 1_000
SQLITE_INTEGRITY_CHECK_TIMEOUT_SECONDS = 10.0


class SQLiteIntegrityError(RuntimeError):
    """Raised when existing SQLite state is unsafe to migrate or serve."""


@asynccontextmanager
async def open_sqlite(
    database_path: str | PathLike[str],
    *,
    isolation_level: str | None = "",
) -> AsyncIterator[aiosqlite.Connection]:
    """Open SQLite with the one-worker production lock and integrity policy."""

    connection = await aiosqlite.connect(
        database_path,
        timeout=SQLITE_BUSY_TIMEOUT_SECONDS,
        isolation_level=isolation_level,
    )
    try:
        await connection.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        await connection.execute("PRAGMA foreign_keys=ON")
        yield connection
    finally:
        await connection.close()


def verify_existing_sqlite_database(database_path: str | PathLike[str]) -> None:
    """Read-only, bounded integrity preflight before any startup migration writes."""

    path = Path(database_path)
    if not path.exists():
        return

    deadline = time.monotonic() + SQLITE_INTEGRITY_CHECK_TIMEOUT_SECONDS
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        with closing(
            sqlite3.connect(uri, uri=True, timeout=SQLITE_BUSY_TIMEOUT_SECONDS)
        ) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.set_progress_handler(
                lambda: int(time.monotonic() >= deadline),
                1_000,
            )
            result = connection.execute("PRAGMA quick_check(1)").fetchone()
            connection.set_progress_handler(None, 0)
        if result != ("ok",):
            raise SQLiteIntegrityError(
                "SQLite integrity preflight failed. Restore a verified backup before retrying."
            )
    except SQLiteIntegrityError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise SQLiteIntegrityError(
            "SQLite integrity preflight failed. Restore a verified backup before retrying."
        ) from exc
