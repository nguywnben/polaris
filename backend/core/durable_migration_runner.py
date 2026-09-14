"""Bounded, resumable W4.13 durable-record copy and authority state machine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol

from core.durable_migration import (
    DURABLE_COPY_FAMILIES,
    DURABLE_INVENTORY,
    DURABLE_MANIFEST_CHECKSUM,
    DURABLE_MANIFEST_VERSION,
    MIGRATION_SCHEMA_VERSION,
    AuthoritySide,
    DurableFamily,
    DurableRecord,
    FamilyProgress,
    MigrationCheckpoint,
    MigrationDigest,
    MigrationEndpointDescriptor,
    MigrationPhase,
)

MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 1_000


class MigrationError(RuntimeError):
    """Generic migration failure that contains no durable record payload."""


class MigrationDuplicateConflict(MigrationError):
    """A target logical key exists with different canonical content."""


class CheckpointRevisionConflict(MigrationError):
    """The checkpoint changed since the caller read it."""


class CheckpointStoreCorrupt(MigrationError):
    """Persisted checkpoint data failed strict reconstruction."""


class CheckpointNotFound(MigrationError):
    """The requested migration checkpoint does not exist."""


@dataclass(frozen=True, slots=True)
class MigrationRecordPage:
    records: tuple[DurableRecord, ...]
    is_complete: bool

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or any(
            type(record) is not DurableRecord for record in self.records
        ):
            raise ValueError("Migration record page is invalid.")
        if type(self.is_complete) is not bool:
            raise ValueError("Migration record completion flag is invalid.")


class MigrationRecordReader(Protocol):
    descriptor: MigrationEndpointDescriptor

    async def read_page(
        self,
        *,
        family: DurableFamily,
        offset: int,
        limit: int,
    ) -> MigrationRecordPage: ...


class MigrationRecordWriter(Protocol):
    descriptor: MigrationEndpointDescriptor

    async def put_if_absent_or_equal(self, record: DurableRecord) -> None: ...


class MigrationCheckpointRepository(Protocol):
    async def create(self, checkpoint: MigrationCheckpoint) -> MigrationCheckpoint: ...

    async def get(self, plan_id: str) -> MigrationCheckpoint | None: ...

    async def compare_and_set(
        self,
        checkpoint: MigrationCheckpoint,
        *,
        expected_revision: int,
    ) -> MigrationCheckpoint: ...


class SourceMutationBarrier(Protocol):
    async def assert_active(
        self,
        *,
        plan_id: str,
        barrier_id: str,
        source_instance_id: str,
    ) -> None: ...


class MigrationRunner:
    """Execute one bounded copy page per call and never switch authority automatically."""

    def __init__(
        self,
        *,
        source: MigrationRecordReader,
        target: MigrationRecordReader | MigrationRecordWriter,
        checkpoints: MigrationCheckpointRepository,
        source_barrier: SourceMutationBarrier,
        integrity_key: bytes,
        batch_size: int = 100,
    ) -> None:
        if type(batch_size) is not int or not MIN_BATCH_SIZE <= batch_size <= MAX_BATCH_SIZE:
            raise ValueError("Migration batch size is invalid.")
        if not isinstance(integrity_key, bytes) or len(integrity_key) < 32:
            raise ValueError("Migration integrity key is too short.")
        if (
            not hasattr(source, "descriptor")
            or type(source.descriptor) is not MigrationEndpointDescriptor
        ):
            raise ValueError("Migration source does not identify its backend instance.")
        if (
            not hasattr(target, "descriptor")
            or type(target.descriptor) is not MigrationEndpointDescriptor
        ):
            raise ValueError("Migration target does not identify its backend instance.")
        if source.descriptor.instance_id == target.descriptor.instance_id:
            raise ValueError("Migration source and target instances must differ.")
        if not hasattr(target, "read_page") or not hasattr(target, "put_if_absent_or_equal"):
            raise ValueError("Migration target does not satisfy the record contract.")
        self._source = source
        self._target = target
        self._checkpoints = checkpoints
        self._source_barrier = source_barrier
        self._integrity_key = integrity_key
        self._batch_size = batch_size

    async def start(
        self,
        *,
        plan_id: str,
        source_barrier_id: str,
        explicitly_empty_families: tuple[DurableFamily, ...],
        now: datetime,
    ) -> MigrationCheckpoint:
        if not isinstance(explicitly_empty_families, tuple) or any(
            type(family) is not DurableFamily for family in explicitly_empty_families
        ):
            raise ValueError("Migration explicit-empty declaration is invalid.")
        if len(set(explicitly_empty_families)) != len(explicitly_empty_families) or not set(
            explicitly_empty_families
        ).issubset(DURABLE_COPY_FAMILIES):
            raise ValueError("Migration explicit-empty declaration is invalid.")
        await self._source_barrier.assert_active(
            plan_id=plan_id,
            barrier_id=source_barrier_id,
            source_instance_id=self._source.descriptor.instance_id,
        )
        timestamp = self._now(now)
        checkpoint = MigrationCheckpoint(
            schema_version=MIGRATION_SCHEMA_VERSION,
            manifest_version=DURABLE_MANIFEST_VERSION,
            manifest_checksum=DURABLE_MANIFEST_CHECKSUM,
            plan_id=plan_id,
            source_backend=self._source.descriptor.backend,
            target_backend=self._target.descriptor.backend,
            source_instance_id=self._source.descriptor.instance_id,
            target_instance_id=self._target.descriptor.instance_id,
            source_revision=self._source.descriptor.revision,
            target_revision=self._target.descriptor.revision,
            source_barrier_id=source_barrier_id,
            phase=MigrationPhase.PLANNED,
            authority=AuthoritySide.SOURCE,
            revision=1,
            families=tuple(
                FamilyProgress(
                    family=family,
                    copy_offset=0,
                    copied_count=0,
                    copy_complete=False,
                    explicitly_empty=family in explicitly_empty_families,
                    source_count=None,
                    target_count=None,
                    source_checksum=None,
                    target_checksum=None,
                    verified=False,
                )
                for family in DURABLE_COPY_FAMILIES
            ),
            failure_code=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
        return await self._checkpoints.create(checkpoint)

    async def copy_next(self, plan_id: str, *, now: datetime) -> MigrationCheckpoint:
        checkpoint = await self._require_checkpoint(plan_id)
        await self._assert_barrier(checkpoint)
        if checkpoint.phase is MigrationPhase.PLANNED:
            checkpoint = await self._save(
                replace(
                    checkpoint,
                    phase=MigrationPhase.COPYING,
                    revision=checkpoint.revision + 1,
                    updated_at=self._now(now),
                ),
                expected_revision=checkpoint.revision,
            )
        if checkpoint.phase is not MigrationPhase.COPYING:
            raise ValueError("Migration is not in the copying phase.")

        index = next(
            (
                position
                for position, progress in enumerate(checkpoint.families)
                if not progress.copy_complete
            ),
            None,
        )
        if index is None:
            return await self._enter_verification(checkpoint, now=now)
        progress = checkpoint.families[index]
        page = await self._source.read_page(
            family=progress.family,
            offset=progress.copy_offset,
            limit=self._batch_size,
        )
        self._validate_page(page, family=progress.family)
        for record in page.records:
            await self._target.put_if_absent_or_equal(record)
        await self._assert_barrier(checkpoint)

        copy_complete = page.is_complete
        updated_progress = replace(
            progress,
            copy_offset=progress.copy_offset + len(page.records),
            copied_count=progress.copied_count + len(page.records),
            copy_complete=copy_complete,
        )
        families = list(checkpoint.families)
        families[index] = updated_progress
        all_complete = all(item.copy_complete for item in families)
        updated = replace(
            checkpoint,
            phase=(MigrationPhase.VERIFYING if all_complete else MigrationPhase.COPYING),
            revision=checkpoint.revision + 1,
            families=tuple(families),
            failure_code=None,
            updated_at=self._now(now),
        )
        return await self._save(updated, expected_revision=checkpoint.revision)

    async def verify(self, plan_id: str, *, now: datetime) -> MigrationCheckpoint:
        checkpoint = await self._require_checkpoint(plan_id)
        if checkpoint.phase is not MigrationPhase.VERIFYING:
            raise ValueError("Migration is not in the verification phase.")

        await self._assert_barrier(checkpoint)
        verified_progress: list[FamilyProgress] = []
        all_matching = True
        for progress in checkpoint.families:
            source_count, source_checksum = await self._scan_digest(self._source, progress.family)
            target_count, target_checksum = await self._scan_digest(self._target, progress.family)
            matches = source_count == target_count and hmac_compare(
                source_checksum, target_checksum
            )
            matches = matches and ((source_count == 0) == progress.explicitly_empty)
            all_matching = all_matching and matches
            verified_progress.append(
                replace(
                    progress,
                    source_count=source_count,
                    target_count=target_count,
                    source_checksum=source_checksum,
                    target_checksum=target_checksum,
                    verified=matches,
                )
            )

        await self._assert_barrier(checkpoint)

        inventory_ready = all(entry.switch_ready for entry in DURABLE_INVENTORY)
        ready = all_matching and inventory_ready
        failure_code = None
        if not all_matching:
            failure_code = "verification_mismatch"
        elif not inventory_ready:
            failure_code = "inventory_not_ready"
        updated = replace(
            checkpoint,
            phase=(MigrationPhase.READY_TO_SWITCH if ready else MigrationPhase.VERIFYING),
            revision=checkpoint.revision + 1,
            families=tuple(verified_progress),
            failure_code=failure_code,
            updated_at=self._now(now),
        )
        return await self._save(updated, expected_revision=checkpoint.revision)

    async def activate_target(
        self,
        plan_id: str,
        *,
        expected_revision: int,
        now: datetime,
    ) -> MigrationCheckpoint:
        checkpoint = await self._require_expected(plan_id, expected_revision)
        await self._assert_barrier(checkpoint)
        if checkpoint.phase is not MigrationPhase.READY_TO_SWITCH:
            raise ValueError("Migration is not ready to switch authority.")
        updated = replace(
            checkpoint,
            phase=MigrationPhase.TARGET_AUTHORITATIVE,
            authority=AuthoritySide.TARGET,
            revision=checkpoint.revision + 1,
            updated_at=self._now(now),
        )
        return await self._save(updated, expected_revision=expected_revision)

    async def prepare_rollback(
        self,
        plan_id: str,
        *,
        expected_revision: int,
        now: datetime,
    ) -> MigrationCheckpoint:
        checkpoint = await self._require_expected(plan_id, expected_revision)
        if checkpoint.phase is not MigrationPhase.TARGET_AUTHORITATIVE:
            raise ValueError("Migration target is not authoritative.")
        updated = replace(
            checkpoint,
            phase=MigrationPhase.ROLLBACK_READY,
            revision=checkpoint.revision + 1,
            updated_at=self._now(now),
        )
        return await self._save(updated, expected_revision=expected_revision)

    async def _enter_verification(
        self, checkpoint: MigrationCheckpoint, *, now: datetime
    ) -> MigrationCheckpoint:
        updated = replace(
            checkpoint,
            phase=MigrationPhase.VERIFYING,
            revision=checkpoint.revision + 1,
            updated_at=self._now(now),
        )
        return await self._save(updated, expected_revision=checkpoint.revision)

    async def _scan_digest(
        self, reader: MigrationRecordReader, family: DurableFamily
    ) -> tuple[int, str]:
        offset = 0
        digest = MigrationDigest(integrity_key=self._integrity_key)
        while True:
            page = await reader.read_page(
                family=family,
                offset=offset,
                limit=self._batch_size,
            )
            self._validate_page(page, family=family)
            for record in page.records:
                try:
                    digest.add(record)
                except ValueError as exc:
                    raise MigrationError(
                        "Migration scan records are duplicated or out of order."
                    ) from exc
            if page.is_complete:
                return digest.count, digest.hexdigest()
            offset += len(page.records)

    def _validate_page(
        self,
        page: MigrationRecordPage,
        *,
        family: DurableFamily,
    ) -> None:
        if type(page) is not MigrationRecordPage or len(page.records) > self._batch_size:
            raise MigrationError("Migration reader violated the bounded page contract.")
        if any(record.family is not family for record in page.records):
            raise MigrationError("Migration reader returned the wrong durable family.")
        identities = [record.logical_id for record in page.records]
        if len(set(identities)) != len(identities):
            raise MigrationError("Migration page contains a duplicate logical record.")
        if not page.is_complete and not page.records:
            raise MigrationError("Migration reader returned an empty continuation page.")

    async def _require_checkpoint(self, plan_id: str) -> MigrationCheckpoint:
        checkpoint = await self._checkpoints.get(plan_id)
        if checkpoint is None:
            raise CheckpointNotFound("Migration checkpoint was not found.")
        if type(checkpoint) is not MigrationCheckpoint:
            raise MigrationError("Migration checkpoint repository returned invalid data.")
        if (
            checkpoint.source_backend is not self._source.descriptor.backend
            or checkpoint.target_backend is not self._target.descriptor.backend
            or checkpoint.source_instance_id != self._source.descriptor.instance_id
            or checkpoint.target_instance_id != self._target.descriptor.instance_id
            or checkpoint.source_revision != self._source.descriptor.revision
            or checkpoint.target_revision != self._target.descriptor.revision
        ):
            raise MigrationError("Migration endpoint does not match the persisted plan.")
        return checkpoint

    async def _assert_barrier(self, checkpoint: MigrationCheckpoint) -> None:
        await self._source_barrier.assert_active(
            plan_id=checkpoint.plan_id,
            barrier_id=checkpoint.source_barrier_id,
            source_instance_id=checkpoint.source_instance_id,
        )

    async def _require_expected(self, plan_id: str, expected_revision: int) -> MigrationCheckpoint:
        checkpoint = await self._require_checkpoint(plan_id)
        if type(expected_revision) is not int or checkpoint.revision != expected_revision:
            raise CheckpointRevisionConflict("Migration checkpoint revision conflict.")
        return checkpoint

    async def _save(
        self, checkpoint: MigrationCheckpoint, *, expected_revision: int
    ) -> MigrationCheckpoint:
        return await self._checkpoints.compare_and_set(
            checkpoint, expected_revision=expected_revision
        )

    @staticmethod
    def _now(value: datetime) -> str:
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("Migration timestamp is invalid.")
        return value.astimezone(timezone.utc).isoformat()


def hmac_compare(left: str, right: str) -> bool:
    """Constant-time comparison kept local to avoid exposing digest implementation details."""

    from hmac import compare_digest

    return compare_digest(left, right)
