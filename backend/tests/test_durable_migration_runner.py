"""Resumable one-page W4.13 migration runner behavior."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.durable_migration import (
    DURABLE_COPY_FAMILIES,
    AuthoritySide,
    DurableBackend,
    DurableFamily,
    DurableRecord,
    MigrationEndpointDescriptor,
    MigrationPhase,
)
from core.durable_migration_runner import (
    CheckpointRevisionConflict,
    MigrationDuplicateConflict,
    MigrationError,
    MigrationRecordPage,
    MigrationRunner,
)

NOW = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)
PLAN_ID = "dmg_0123456789abcdef0123456789abcdef"
BARRIER_ID = "bar_33333333333333333333333333333333"
KEY = b"migration-integrity-key-32-bytes!!"
FAMILY = DurableFamily.CONFIGURATION
SOURCE_DESCRIPTOR = MigrationEndpointDescriptor(
    DurableBackend.SQLITE, "ins_11111111111111111111111111111111"
)
TARGET_DESCRIPTOR = MigrationEndpointDescriptor(
    DurableBackend.POSTGRESQL, "ins_22222222222222222222222222222222"
)
EMPTY_FAMILIES = tuple(family for family in DURABLE_COPY_FAMILIES if family is not FAMILY)


def _record(suffix: str, value: int) -> DurableRecord:
    return DurableRecord(
        family=FAMILY,
        logical_id=f"cfg_{suffix * 16}",
        schema_version=1,
        payload={"value": value},
    )


class MemoryRecords:
    def __init__(self, descriptor, records=()):
        self.descriptor = descriptor
        self.records = {(record.family, record.logical_id): record for record in records}
        self.interrupt_after: int | None = None
        self.write_calls = 0

    async def read_page(self, *, family, offset, limit):
        records = sorted(
            (record for (kind, _), record in self.records.items() if kind is family),
            key=lambda record: record.logical_id,
        )
        page = tuple(records[offset : offset + limit])
        return MigrationRecordPage(
            records=page,
            is_complete=offset + len(page) >= len(records),
        )

    async def put_if_absent_or_equal(self, record):
        self.write_calls += 1
        if self.interrupt_after is not None and self.write_calls > self.interrupt_after:
            self.interrupt_after = None
            raise RuntimeError("simulated interruption")
        identity = (record.family, record.logical_id)
        existing = self.records.get(identity)
        if existing is not None and existing != record:
            raise MigrationDuplicateConflict("Conflicting durable record.")
        self.records[identity] = record


class MemoryCheckpoints:
    def __init__(self):
        self.records = {}

    async def create(self, checkpoint):
        if checkpoint.plan_id in self.records:
            raise CheckpointRevisionConflict("Checkpoint already exists.")
        self.records[checkpoint.plan_id] = checkpoint
        return checkpoint

    async def get(self, plan_id):
        return self.records.get(plan_id)

    async def compare_and_set(self, checkpoint, *, expected_revision):
        current = self.records.get(checkpoint.plan_id)
        if current is None or current.revision != expected_revision:
            raise CheckpointRevisionConflict("Checkpoint revision conflict.")
        self.records[checkpoint.plan_id] = checkpoint
        return checkpoint


class MemoryBarrier:
    def __init__(self):
        self.active = True
        self.checks = 0
        self.fail_on_check: int | None = None

    async def assert_active(self, *, plan_id, barrier_id, source_instance_id):
        self.checks += 1
        if (
            plan_id != PLAN_ID
            or barrier_id != BARRIER_ID
            or source_instance_id != SOURCE_DESCRIPTOR.instance_id
            or not self.active
            or self.fail_on_check == self.checks
        ):
            raise RuntimeError("source mutation barrier is not active")


def _source(records=()):
    return MemoryRecords(SOURCE_DESCRIPTOR, records)


def _target(records=(), *, descriptor=TARGET_DESCRIPTOR):
    return MemoryRecords(descriptor, records)


def _runner(source, target, checkpoints, *, batch_size=2, barrier=None):
    return MigrationRunner(
        source=source,
        target=target,
        checkpoints=checkpoints,
        source_barrier=barrier or MemoryBarrier(),
        integrity_key=KEY,
        batch_size=batch_size,
    )


async def _start(runner, *, explicitly_empty=EMPTY_FAMILIES):
    return await runner.start(
        plan_id=PLAN_ID,
        source_barrier_id=BARRIER_ID,
        explicitly_empty_families=explicitly_empty,
        now=NOW,
    )


async def _copy_all(runner, *, start_second=1):
    for second in range(start_second, start_second + len(DURABLE_COPY_FAMILIES) + 5):
        checkpoint = await runner.copy_next(PLAN_ID, now=NOW + timedelta(seconds=second))
        if checkpoint.phase is MigrationPhase.VERIFYING:
            return checkpoint
    raise AssertionError("Migration did not enter verification within the bounded test loop.")


class MigrationCopyTests(unittest.IsolatedAsyncioTestCase):
    async def test_interruption_leaves_source_authoritative_and_replays_page_idempotently(self):
        source = _source((_record("1", 1), _record("2", 2)))
        target = _target()
        target.interrupt_after = 1
        checkpoints = MemoryCheckpoints()
        runner = _runner(source, target, checkpoints)
        await _start(runner)

        with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
            await runner.copy_next(PLAN_ID, now=NOW + timedelta(seconds=1))

        interrupted = await checkpoints.get(PLAN_ID)
        self.assertIs(interrupted.authority, AuthoritySide.SOURCE)
        self.assertIs(interrupted.phase, MigrationPhase.COPYING)
        self.assertEqual(interrupted.families[0].copied_count, 0)
        self.assertEqual(len(target.records), 1)

        resumed = await runner.copy_next(PLAN_ID, now=NOW + timedelta(seconds=2))
        self.assertIs(resumed.phase, MigrationPhase.COPYING)
        self.assertEqual(resumed.families[0].copied_count, 2)
        self.assertEqual(len(target.records), 2)
        self.assertEqual(target.write_calls, 4)

    async def test_conflicting_duplicate_stops_without_advancing_checkpoint(self):
        source = _source((_record("1", 1),))
        target = _target((_record("1", 999),))
        checkpoints = MemoryCheckpoints()
        runner = _runner(source, target, checkpoints)
        await _start(runner)

        with self.assertRaises(MigrationDuplicateConflict):
            await runner.copy_next(PLAN_ID, now=NOW + timedelta(seconds=1))

        checkpoint = await checkpoints.get(PLAN_ID)
        self.assertIs(checkpoint.phase, MigrationPhase.COPYING)
        self.assertIs(checkpoint.authority, AuthoritySide.SOURCE)
        self.assertEqual(checkpoint.families[0].copied_count, 0)

    async def test_restart_resumes_from_persisted_safe_numeric_position(self):
        source = _source((_record("1", 1), _record("2", 2), _record("3", 3)))
        target = _target()
        checkpoints = MemoryCheckpoints()
        first_process = _runner(source, target, checkpoints, batch_size=1)
        await _start(first_process)
        first_page = await first_process.copy_next(PLAN_ID, now=NOW + timedelta(seconds=1))
        self.assertEqual(first_page.families[0].copy_offset, 1)

        restarted = _runner(source, target, checkpoints, batch_size=1)
        second_page = await restarted.copy_next(PLAN_ID, now=NOW + timedelta(seconds=2))
        self.assertEqual(second_page.families[0].copy_offset, 2)
        third_page = await restarted.copy_next(PLAN_ID, now=NOW + timedelta(seconds=3))
        self.assertTrue(third_page.families[0].copy_complete)
        self.assertEqual(third_page.families[0].copied_count, 3)

    async def test_copy_refuses_to_read_when_source_mutation_barrier_is_lost(self):
        source = _source((_record("1", 1),))
        target = _target()
        checkpoints = MemoryCheckpoints()
        barrier = MemoryBarrier()
        runner = _runner(source, target, checkpoints, barrier=barrier)
        await _start(runner)
        barrier.active = False

        with self.assertRaisesRegex(RuntimeError, "barrier is not active"):
            await runner.copy_next(PLAN_ID, now=NOW + timedelta(seconds=1))

        checkpoint = await checkpoints.get(PLAN_ID)
        self.assertIs(checkpoint.phase, MigrationPhase.PLANNED)
        self.assertIs(checkpoint.authority, AuthoritySide.SOURCE)
        self.assertFalse(target.records)

    async def test_restart_with_different_target_instance_fails_closed(self):
        source = _source((_record("1", 1),))
        checkpoints = MemoryCheckpoints()
        first = _runner(source, _target(), checkpoints)
        await _start(first)
        wrong_target = _target(
            descriptor=MigrationEndpointDescriptor(
                DurableBackend.POSTGRESQL,
                "ins_99999999999999999999999999999999",
            )
        )

        with self.assertRaisesRegex(MigrationError, "does not match the persisted plan"):
            await _runner(source, wrong_target, checkpoints).copy_next(
                PLAN_ID, now=NOW + timedelta(seconds=1)
            )


class MigrationVerificationAndAuthorityTests(unittest.IsolatedAsyncioTestCase):
    async def _copied(self, *, explicitly_empty=EMPTY_FAMILIES):
        source = _source((_record("1", 1), _record("2", 2)))
        target = _target()
        checkpoints = MemoryCheckpoints()
        barrier = MemoryBarrier()
        runner = _runner(source, target, checkpoints, barrier=barrier)
        await _start(runner, explicitly_empty=explicitly_empty)
        await _copy_all(runner)
        return runner, source, target, checkpoints, barrier

    async def test_checksum_mismatch_stays_in_verification_with_source_authoritative(self):
        runner, _source_store, target, _checkpoints, _barrier = await self._copied()
        target.records[(FAMILY, _record("2", 2).logical_id)] = _record("2", 7)

        checkpoint = await runner.verify(PLAN_ID, now=NOW + timedelta(seconds=20))

        self.assertIs(checkpoint.phase, MigrationPhase.VERIFYING)
        self.assertIs(checkpoint.authority, AuthoritySide.SOURCE)
        self.assertEqual(checkpoint.failure_code, "verification_mismatch")
        self.assertFalse(checkpoint.families[0].verified)

    async def test_equal_empty_scan_needs_explicit_empty_declaration(self):
        missing_declaration = tuple(
            family for family in EMPTY_FAMILIES if family is not DurableFamily.REQUEST_TRACE
        )
        runner, *_rest = await self._copied(explicitly_empty=missing_declaration)

        checkpoint = await runner.verify(PLAN_ID, now=NOW + timedelta(seconds=20))

        progress = next(
            item for item in checkpoint.families if item.family is DurableFamily.REQUEST_TRACE
        )
        self.assertFalse(progress.verified)
        self.assertEqual(checkpoint.failure_code, "verification_mismatch")

    async def test_complete_canonical_manifest_can_switch_only_by_explicit_activation(self):
        runner, *_rest = await self._copied()
        checkpoint = await runner.verify(PLAN_ID, now=NOW + timedelta(seconds=20))

        self.assertIs(checkpoint.phase, MigrationPhase.READY_TO_SWITCH)
        self.assertIs(checkpoint.authority, AuthoritySide.SOURCE)
        self.assertIsNone(checkpoint.failure_code)
        self.assertTrue(all(item.verified for item in checkpoint.families))
        activated = await runner.activate_target(
            PLAN_ID,
            expected_revision=checkpoint.revision,
            now=NOW + timedelta(seconds=21),
        )
        self.assertIs(activated.phase, MigrationPhase.TARGET_AUTHORITATIVE)
        self.assertIs(activated.authority, AuthoritySide.TARGET)
        self.assertFalse(hasattr(runner, "complete_rollback"))

    async def test_barrier_loss_after_scans_cannot_publish_verified_evidence(self):
        runner, _source_store, _target_store, checkpoints, barrier = await self._copied()
        barrier.fail_on_check = barrier.checks + 2

        with self.assertRaisesRegex(RuntimeError, "barrier is not active"):
            await runner.verify(PLAN_ID, now=NOW + timedelta(seconds=20))

        checkpoint = await checkpoints.get(PLAN_ID)
        self.assertIs(checkpoint.phase, MigrationPhase.VERIFYING)
        self.assertIs(checkpoint.authority, AuthoritySide.SOURCE)
        self.assertFalse(checkpoint.families[0].verified)


if __name__ == "__main__":
    unittest.main()
