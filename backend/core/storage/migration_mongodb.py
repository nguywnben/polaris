"""Additive MongoDB persistence for W4.13 migration checkpoints."""

from __future__ import annotations

import asyncio
from typing import Any

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
from pymongo.errors import DuplicateKeyError


class MongoMigrationCheckpointRepository:
    def __init__(self, collection: Any) -> None:
        self._collection = collection
        self._initialized = False
        self._initialize_lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._initialize_lock:
            self._initialized = False
            try:
                await self._collection.create_index(
                    [("revision", 1)], name="idx_durable_migration_revision"
                )
                async for document in self._collection.find({}):
                    self._decode_document(document)
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
            await self._collection.insert_one(self._document(checkpoint))
        except DuplicateKeyError as exc:
            raise CheckpointRevisionConflict("Migration checkpoint already exists.") from exc
        except Exception as exc:
            raise CheckpointStoreCorrupt("Durable migration checkpoint store is invalid.") from exc
        return checkpoint

    async def get(self, plan_id: str) -> MigrationCheckpoint | None:
        self._ensure_initialized()
        require_plan_id(plan_id)
        try:
            document = await self._collection.find_one({"_id": plan_id})
        except Exception as exc:
            raise CheckpointStoreCorrupt("Durable migration checkpoint store is invalid.") from exc
        return None if document is None else self._decode_document(document)

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
            result = await self._collection.replace_one(
                {"_id": checkpoint.plan_id, "revision": expected_revision},
                self._document(checkpoint),
                upsert=False,
            )
        except Exception as exc:
            raise CheckpointStoreCorrupt("Durable migration checkpoint store is invalid.") from exc
        if type(result.matched_count) is not int or result.matched_count != 1:
            raise CheckpointRevisionConflict("Migration checkpoint revision conflict.")
        return checkpoint

    @staticmethod
    def _document(checkpoint: MigrationCheckpoint) -> dict[str, object]:
        return {
            "_id": checkpoint.plan_id,
            "revision": checkpoint.revision,
            "record_json": encode_checkpoint(checkpoint),
        }

    @staticmethod
    def _decode_document(document: object) -> MigrationCheckpoint:
        if not isinstance(document, dict) or set(document) != {
            "_id",
            "revision",
            "record_json",
        }:
            raise CheckpointStoreCorrupt("Durable migration checkpoint store is invalid.")
        return decode_checkpoint(
            plan_id=document["_id"],
            revision=document["revision"],
            encoded=document["record_json"],
        )

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("Migration checkpoint repository is not initialized.")
