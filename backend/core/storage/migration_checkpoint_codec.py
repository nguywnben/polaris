"""Shared strict serialization for durable migration checkpoint repositories."""

from __future__ import annotations

import json
import re

from core.durable_migration import (
    HistoricalMigrationCheckpoint,
    MigrationCheckpoint,
    checkpoint_from_record,
)
from core.durable_migration_runner import CheckpointStoreCorrupt

_PLAN_ID = re.compile(r"dmg_[0-9a-f]{32}")


def require_plan_id(plan_id: object) -> str:
    if not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id):
        raise ValueError("Migration plan ID is invalid.")
    return plan_id


def require_checkpoint(checkpoint: object) -> MigrationCheckpoint:
    if type(checkpoint) is not MigrationCheckpoint:
        raise ValueError("Migration checkpoint is invalid.")
    return checkpoint


def encode_checkpoint(checkpoint: MigrationCheckpoint) -> str:
    require_checkpoint(checkpoint)
    return json.dumps(
        checkpoint.to_record(),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def decode_checkpoint(
    *, plan_id: object, revision: object, encoded: object
) -> MigrationCheckpoint | HistoricalMigrationCheckpoint:
    try:
        safe_plan_id = require_plan_id(plan_id)
        if type(revision) is not int or revision < 1 or not isinstance(encoded, str):
            raise ValueError
        checkpoint = checkpoint_from_record(json.loads(encoded))
        if checkpoint.plan_id != safe_plan_id or checkpoint.revision != revision:
            raise ValueError
        return checkpoint
    except (TypeError, ValueError) as exc:
        raise CheckpointStoreCorrupt("Durable migration checkpoint store is invalid.") from exc
