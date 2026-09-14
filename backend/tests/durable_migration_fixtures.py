"""Synthetic, content-free migration fixtures for durable-backend contracts."""

from __future__ import annotations

from datetime import datetime, timezone

from core.durable_migration import (
    DURABLE_COPY_FAMILIES,
    DURABLE_MANIFEST_CHECKSUM,
    DURABLE_MANIFEST_VERSION,
    MIGRATION_SCHEMA_VERSION,
    AuthoritySide,
    DurableBackend,
    FamilyProgress,
    MigrationCheckpoint,
    MigrationPhase,
)

PLAN_ID = "dmg_0123456789abcdef0123456789abcdef"


def completed_migration_checkpoint() -> MigrationCheckpoint:
    now = datetime(2026, 9, 5, tzinfo=timezone.utc).isoformat()
    return MigrationCheckpoint(
        schema_version=MIGRATION_SCHEMA_VERSION,
        manifest_version=DURABLE_MANIFEST_VERSION,
        manifest_checksum=DURABLE_MANIFEST_CHECKSUM,
        plan_id=PLAN_ID,
        source_backend=DurableBackend.SQLITE,
        target_backend=DurableBackend.POSTGRESQL,
        source_instance_id="ins_11111111111111111111111111111111",
        target_instance_id="ins_22222222222222222222222222222222",
        source_revision=7,
        target_revision=11,
        source_barrier_id="bar_33333333333333333333333333333333",
        phase=MigrationPhase.TARGET_AUTHORITATIVE,
        authority=AuthoritySide.TARGET,
        revision=4,
        families=tuple(
            FamilyProgress(
                family=family,
                copy_offset=0,
                copied_count=0,
                copy_complete=True,
                explicitly_empty=True,
                source_count=0,
                target_count=0,
                source_checksum="a" * 64,
                target_checksum="a" * 64,
                verified=True,
            )
            for family in DURABLE_COPY_FAMILIES
        ),
        failure_code=None,
        created_at=now,
        updated_at=now,
    )


class MemoryMigrationCheckpoints:
    def __init__(self, checkpoint: MigrationCheckpoint | None = None) -> None:
        self.records = {}
        if checkpoint is not None:
            self.records[checkpoint.plan_id] = checkpoint

    async def get(self, plan_id: str):
        return self.records.get(plan_id)
