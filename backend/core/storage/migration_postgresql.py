"""Additive PostgreSQL persistence for W4.13 migration checkpoints."""

from __future__ import annotations

import asyncio

import asyncpg
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


class PostgreSQLMigrationCheckpointRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._initialized = False
        self._initialize_lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._initialize_lock:
            self._initialized = False
            try:
                async with self._pool.acquire() as connection:
                    async with connection.transaction():
                        await connection.execute("""
                            CREATE TABLE IF NOT EXISTS durable_migration_checkpoints (
                                plan_id TEXT NOT NULL PRIMARY KEY,
                                revision BIGINT NOT NULL CHECK (revision >= 1),
                                record_json TEXT NOT NULL
                            )
                        """)
                        rows = await connection.fetch(
                            "SELECT plan_id, revision, record_json FROM durable_migration_checkpoints"
                        )
                        for row in rows:
                            decode_checkpoint(
                                plan_id=row["plan_id"],
                                revision=row["revision"],
                                encoded=row["record_json"],
                            )
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
        try:
            async with self._pool.acquire() as connection:
                await connection.execute(
                    """
                    INSERT INTO durable_migration_checkpoints (plan_id, revision, record_json)
                    VALUES ($1, $2, $3)
                    """,
                    checkpoint.plan_id,
                    checkpoint.revision,
                    encode_checkpoint(checkpoint),
                )
        except asyncpg.UniqueViolationError as exc:
            raise CheckpointRevisionConflict("Migration checkpoint already exists.") from exc
        except Exception as exc:
            raise CheckpointStoreCorrupt("Durable migration checkpoint store is invalid.") from exc
        return checkpoint

    async def get(self, plan_id: str) -> MigrationCheckpoint | None:
        self._ensure_initialized()
        require_plan_id(plan_id)
        try:
            async with self._pool.acquire() as connection:
                row = await connection.fetchrow(
                    """
                    SELECT revision, record_json
                    FROM durable_migration_checkpoints
                    WHERE plan_id = $1
                    """,
                    plan_id,
                )
        except Exception as exc:
            raise CheckpointStoreCorrupt("Durable migration checkpoint store is invalid.") from exc
        if row is None:
            return None
        return decode_checkpoint(
            plan_id=plan_id,
            revision=row["revision"],
            encoded=row["record_json"],
        )

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
        try:
            async with self._pool.acquire() as connection:
                result = await connection.execute(
                    """
                    UPDATE durable_migration_checkpoints
                    SET revision = $1, record_json = $2
                    WHERE plan_id = $3 AND revision = $4
                    """,
                    checkpoint.revision,
                    encode_checkpoint(checkpoint),
                    checkpoint.plan_id,
                    expected_revision,
                )
        except Exception as exc:
            raise CheckpointStoreCorrupt("Durable migration checkpoint store is invalid.") from exc
        if result != "UPDATE 1":
            raise CheckpointRevisionConflict("Migration checkpoint revision conflict.")
        return checkpoint

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("Migration checkpoint repository is not initialized.")
