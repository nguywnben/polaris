"""Additive SQLite persistence for W4.13 migration checkpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
from core.durable_migration import MigrationCheckpoint
from core.durable_migration_runner import (
    CheckpointRevisionConflict,
    CheckpointStoreCorrupt,
)
from core.storage.migration_checkpoint_codec import (
    decode_checkpoint,
    encode_checkpoint,
    require_checkpoint,
    require_plan_id,
)
from core.storage.sqlite_runtime import open_sqlite


class SQLiteMigrationCheckpointRepository:
    """Metadata-only checkpoint store with optimistic compare-and-set updates."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = str(database_path)
        self._initialized = False
        self._initialize_lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._initialize_lock:
            self._initialized = False
            try:
                async with open_sqlite(self._database_path) as db:
                    await db.execute("PRAGMA journal_mode=WAL")
                    await db.execute("BEGIN IMMEDIATE")
                    try:
                        await db.execute("""
                            CREATE TABLE IF NOT EXISTS durable_migration_checkpoints (
                                plan_id TEXT NOT NULL PRIMARY KEY,
                                revision INTEGER NOT NULL CHECK(revision >= 1),
                                record_json TEXT NOT NULL
                            )
                        """)
                        await self._validate_store(db)
                        await db.commit()
                    except Exception:
                        await db.rollback()
                        raise
            except CheckpointStoreCorrupt:
                raise
            except Exception as exc:
                raise CheckpointStoreCorrupt(
                    "Durable migration checkpoint store is invalid."
                ) from exc
            self._initialized = True

    async def create(self, checkpoint: MigrationCheckpoint) -> MigrationCheckpoint:
        self._ensure_initialized()
        require_checkpoint(checkpoint)
        if checkpoint.revision != 1:
            raise ValueError("A new migration checkpoint must start at revision one.")
        encoded = encode_checkpoint(checkpoint)
        try:
            async with open_sqlite(self._database_path) as db:
                await db.execute("BEGIN IMMEDIATE")
                try:
                    await db.execute(
                        """
                        INSERT INTO durable_migration_checkpoints (plan_id, revision, record_json)
                        VALUES (?, ?, ?)
                        """,
                        (checkpoint.plan_id, checkpoint.revision, encoded),
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
        except aiosqlite.IntegrityError as exc:
            raise CheckpointRevisionConflict("Migration checkpoint already exists.") from exc
        return checkpoint

    async def get(self, plan_id: str) -> MigrationCheckpoint | None:
        self._ensure_initialized()
        require_plan_id(plan_id)
        try:
            async with open_sqlite(self._database_path) as db:
                async with db.execute(
                    """
                    SELECT revision, record_json
                    FROM durable_migration_checkpoints
                    WHERE plan_id = ?
                    """,
                    (plan_id,),
                ) as cursor:
                    row = await cursor.fetchone()
        except Exception as exc:
            raise CheckpointStoreCorrupt("Durable migration checkpoint store is invalid.") from exc
        if row is None:
            return None
        return decode_checkpoint(plan_id=plan_id, revision=row[0], encoded=row[1])

    async def compare_and_set(
        self,
        checkpoint: MigrationCheckpoint,
        *,
        expected_revision: int,
    ) -> MigrationCheckpoint:
        self._ensure_initialized()
        require_checkpoint(checkpoint)
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("Migration checkpoint expected revision is invalid.")
        if checkpoint.revision != expected_revision + 1:
            raise ValueError("Migration checkpoint revision must advance by one.")
        encoded = encode_checkpoint(checkpoint)
        try:
            async with open_sqlite(self._database_path) as db:
                await db.execute("BEGIN IMMEDIATE")
                try:
                    cursor = await db.execute(
                        """
                        UPDATE durable_migration_checkpoints
                        SET revision = ?, record_json = ?
                        WHERE plan_id = ? AND revision = ?
                        """,
                        (
                            checkpoint.revision,
                            encoded,
                            checkpoint.plan_id,
                            expected_revision,
                        ),
                    )
                    if cursor.rowcount != 1:
                        await db.rollback()
                        raise CheckpointRevisionConflict("Migration checkpoint revision conflict.")
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
        except CheckpointRevisionConflict:
            raise
        except Exception as exc:
            raise CheckpointStoreCorrupt("Durable migration checkpoint store is invalid.") from exc
        return checkpoint

    async def _validate_store(self, db: aiosqlite.Connection) -> None:
        async with db.execute(
            "SELECT plan_id, revision, record_json FROM durable_migration_checkpoints"
        ) as cursor:
            rows = await cursor.fetchall()
        for plan_id, revision, encoded in rows:
            decode_checkpoint(plan_id=plan_id, revision=revision, encoded=encoded)

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("Migration checkpoint repository is not initialized.")
