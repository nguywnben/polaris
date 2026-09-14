"""Real-table durable-family adapters and SQLite source barrier contracts."""

from __future__ import annotations

import os
import shutil
import sys
import unittest
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.audit import create_audit_event
from core.durable_migration import AuthoritySide, DurableFamily, MigrationPhase
from core.durable_migration_runner import MigrationDuplicateConflict, MigrationRunner
from core.request_trace import REQUEST_TRACE_SCHEMA_VERSION, RequestDecision, RequestTrace
from core.storage.audit_postgresql import PostgreSQLAuditRepository
from core.storage.audit_sqlite import SQLiteAuditRepository
from core.storage.durable_family_barrier import (
    SourceMutationBarrierLost,
    SQLiteSourceMutationBarrier,
)
from core.storage.durable_family_postgresql import PostgreSQLDurableFamilyAdapter
from core.storage.durable_family_sqlite import SQLiteDurableFamilyAdapter
from core.storage.identity_postgresql import PostgreSQLIdentityRepository
from core.storage.identity_sqlite import SQLiteIdentityRepository
from core.storage.migration_postgresql import PostgreSQLMigrationCheckpointRepository
from core.storage.migration_sqlite import SQLiteMigrationCheckpointRepository
from core.storage.postgresql_manager import PostgreSQLManager
from core.storage.request_trace_postgresql import PostgreSQLRequestTraceRepository
from core.storage.request_trace_sqlite import SQLiteRequestTraceRepository
from core.storage.sqlite_manager import SQLiteManager
from core.storage.usage_ledger_postgresql import PostgreSQLUsageLedgerRepository
from core.storage.usage_ledger_sqlite import SQLiteUsageLedgerRepository
from core.usage_ledger import (
    USAGE_LEDGER_SCHEMA_VERSION,
    BudgetReservationRequest,
    UsageLedgerEntry,
)

from backend.tests.durable_migration_fixtures import completed_migration_checkpoint

PLAN_ID = "dmg_0123456789abcdef0123456789abcdef"
BARRIER_ID = "bar_33333333333333333333333333333333"
SOURCE_ID = "ins_11111111111111111111111111111111"
TARGET_ID = "ins_22222222222222222222222222222222"
NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
POSTGRESQL_URI = os.getenv("POLARIS_TEST_POSTGRESQL_URI", "").strip()


async def _initialize_database(directory: str) -> Path:
    database_path = Path(directory) / "credentials.db"
    with patch.dict(os.environ, {"CREDENTIALS_DIR": directory}):
        manager = SQLiteManager()
        await manager.initialize()
        await manager.close()
    for repository in (
        SQLiteIdentityRepository(database_path, clock=lambda: NOW),
        SQLiteAuditRepository(database_path, cursor_signing_key=b"a" * 32),
        SQLiteRequestTraceRepository(database_path, cursor_signing_key=b"t" * 32),
        SQLiteUsageLedgerRepository(str(database_path)),
        SQLiteMigrationCheckpointRepository(database_path),
    ):
        await repository.initialize()
    return database_path


class SQLiteDurableFamilyAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = WORKSPACE_DIR / "temp" / "tests" / f"w4c-{uuid.uuid4().hex}"
        self.temporary.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.temporary, True)
        self.source_path = await _initialize_database(str(self.temporary / "source"))
        self.target_path = await _initialize_database(str(self.temporary / "target"))
        async with aiosqlite.connect(self.source_path) as db:
            await db.executemany(
                "INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?)",
                (("alpha", '"one"', 1.0), ("beta", '"two"', 2.0), ("virtual_keys", "[]", 3.0)),
            )
            await db.commit()
        self.source = SQLiteDurableFamilyAdapter(
            self.source_path, instance_id=SOURCE_ID, revision=7
        )
        self.target = SQLiteDurableFamilyAdapter(
            self.target_path, instance_id=TARGET_ID, revision=11
        )

    async def test_pagination_is_bounded_stable_and_separates_virtual_keys(self):
        first = await self.source.read_page(family=DurableFamily.CONFIGURATION, offset=0, limit=1)
        second = await self.source.read_page(family=DurableFamily.CONFIGURATION, offset=1, limit=1)
        virtual_keys = await self.source.read_page(
            family=DurableFamily.VIRTUAL_KEY, offset=0, limit=1
        )

        self.assertEqual(len(first.records), 1)
        self.assertFalse(first.is_complete)
        self.assertEqual(len(second.records), 1)
        self.assertTrue(second.is_complete)
        self.assertEqual(dict(virtual_keys.records[0].payload)["key"], "virtual_keys")
        with self.assertRaises(ValueError):
            await self.source.read_page(family=DurableFamily.CONFIGURATION, offset=0, limit=1001)

    async def test_put_is_exactly_idempotent_and_rejects_conflicting_duplicate(self):
        page = await self.source.read_page(family=DurableFamily.CONFIGURATION, offset=0, limit=1)
        record = page.records[0]
        await self.target.put_if_absent_or_equal(record)
        await self.target.put_if_absent_or_equal(record)

        async with aiosqlite.connect(self.target_path) as db:
            await db.execute(
                "UPDATE config SET value = ? WHERE key = ?",
                ('"changed"', dict(record.payload)["key"]),
            )
            await db.commit()
        with self.assertRaises(MigrationDuplicateConflict):
            await self.target.put_if_absent_or_equal(record)

    async def test_barrier_atomically_blocks_application_mutation_and_detects_loss(self):
        barrier = SQLiteSourceMutationBarrier(self.source_path)
        await barrier.activate(
            plan_id=PLAN_ID,
            barrier_id=BARRIER_ID,
            source_instance_id=SOURCE_ID,
        )
        await barrier.assert_active(
            plan_id=PLAN_ID,
            barrier_id=BARRIER_ID,
            source_instance_id=SOURCE_ID,
        )
        async with aiosqlite.connect(self.source_path) as db:
            with self.assertRaises(aiosqlite.IntegrityError):
                await db.execute("UPDATE config SET value = '3' WHERE key = 'alpha'")
            await db.rollback()
            await db.execute("DROP TRIGGER polaris_migration_fence_v2_config_update")
            await db.commit()
        with self.assertRaises(SourceMutationBarrierLost):
            await barrier.assert_active(
                plan_id=PLAN_ID,
                barrier_id=BARRIER_ID,
                source_instance_id=SOURCE_ID,
            )


@unittest.skipUnless(POSTGRESQL_URI, "POLARIS_TEST_POSTGRESQL_URI is not configured")
class LivePostgreSQLDurableFamilyMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = WORKSPACE_DIR / "temp" / "tests" / f"w4c-{uuid.uuid4().hex}"
        self.temporary.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.temporary, True)
        self.source_path = await _initialize_database(str(self.temporary / "source"))
        await self._seed_source()

        self.schema_name = f"polaris_durable_migration_{uuid.uuid4().hex}"
        admin = await asyncpg.connect(POSTGRESQL_URI)
        try:
            await admin.execute(f'CREATE SCHEMA "{self.schema_name}"')
        finally:
            await admin.close()
        self.pool = await asyncpg.create_pool(
            POSTGRESQL_URI,
            min_size=1,
            max_size=4,
            server_settings={"search_path": self.schema_name},
        )
        async with self.pool.acquire() as connection:
            await PostgreSQLManager()._create_tables(connection)
        for repository in (
            PostgreSQLIdentityRepository(self.pool, clock=lambda: NOW),
            PostgreSQLAuditRepository(self.pool, cursor_signing_key=b"a" * 32),
            PostgreSQLRequestTraceRepository(self.pool, cursor_signing_key=b"t" * 32),
            PostgreSQLUsageLedgerRepository(self.pool),
            PostgreSQLMigrationCheckpointRepository(self.pool),
        ):
            await repository.initialize()
        self.source = SQLiteDurableFamilyAdapter(
            self.source_path, instance_id=SOURCE_ID, revision=7
        )
        self.target = PostgreSQLDurableFamilyAdapter(self.pool, instance_id=TARGET_ID, revision=11)

    async def asyncTearDown(self) -> None:
        if not hasattr(self, "pool"):
            return
        await self.pool.close()
        admin = await asyncpg.connect(POSTGRESQL_URI)
        try:
            await admin.execute(f'DROP SCHEMA "{self.schema_name}" CASCADE')
        finally:
            await admin.close()

    async def _seed_source(self) -> None:
        async with aiosqlite.connect(self.source_path) as db:
            await db.executemany(
                "INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?)",
                (("alpha", '"one"', 1.0), ("virtual_keys", "[]", 2.0)),
            )
            await db.execute(
                "INSERT INTO credentials (filename, credential_data) VALUES (?, ?)",
                ("synthetic-provider.json", '{"type":"synthetic"}'),
            )
            await db.execute(
                "INSERT INTO primary_credentials (filename, credential_data) VALUES (?, ?)",
                ("synthetic-primary.json", '{"type":"synthetic"}'),
            )
            await db.commit()

        audit = SQLiteAuditRepository(self.source_path, cursor_signing_key=b"a" * 32)
        await audit.initialize()
        await audit.append(
            create_audit_event(
                request_id="migration-live-1",
                actor_type="panel_session",
                actor_identifier="synthetic-owner",
                action="virtual_key.update",
                target_type="virtual_key",
                target_identifier="synthetic-key",
                outcome="succeeded",
                change_codes=("limits_changed",),
                fingerprint_key=b"f" * 32,
                occurred_at=NOW,
            )
        )
        trace_repository = SQLiteRequestTraceRepository(
            self.source_path, cursor_signing_key=b"t" * 32
        )
        await trace_repository.initialize()
        await trace_repository.append(self._trace())
        ledger = SQLiteUsageLedgerRepository(str(self.source_path))
        await ledger.initialize()
        await ledger.append_usage(self._usage())
        await ledger.reserve_budget(self._reservation())
        checkpoints = SQLiteMigrationCheckpointRepository(self.source_path)
        await checkpoints.initialize()
        await checkpoints.create(
            replace(
                completed_migration_checkpoint(),
                phase=MigrationPhase.PLANNED,
                authority=AuthoritySide.SOURCE,
                revision=1,
            )
        )

    @staticmethod
    def _trace() -> RequestTrace:
        return RequestTrace(
            schema_version=REQUEST_TRACE_SCHEMA_VERSION,
            trace_id="b" * 32,
            request_id="migration-live-1",
            protocol="openai_chat",
            started_at=NOW.isoformat(),
            completed_at=(NOW + timedelta(milliseconds=10)).isoformat(),
            outcome="succeeded",
            status_code=200,
            duration_ms=10,
            requested_model="synthetic-model",
            selected_provider="synthetic-provider",
            input_tokens=10,
            output_tokens=2,
            total_tokens=12,
            cost_usd=0.0,
            decisions=(
                RequestDecision(
                    sequence=1,
                    elapsed_ms=1,
                    category="routing",
                    action="selected",
                    result="succeeded",
                    reason="healthy_candidate",
                    provider="synthetic-provider",
                    model="synthetic-model",
                    candidate_count=1,
                ),
            ),
        )

    @staticmethod
    def _usage() -> UsageLedgerEntry:
        return UsageLedgerEntry(
            schema_version=USAGE_LEDGER_SCHEMA_VERSION,
            event_id="use_" + ("a" * 32),
            occurred_at=1_800_000_000.0,
            credential_ref="synthetic-provider.json",
            request_id="migration-live-usage",
            model="synthetic-model",
            provider="synthetic-provider",
            status_code=200,
            success=True,
            input_tokens=10,
            output_tokens=2,
            total_tokens=12,
            cached_tokens=0,
            reasoning_tokens=0,
            estimated_input_tokens=10,
            estimated_tokens_saved=0,
            compressed_messages=0,
            quality_profile="balanced",
            quality_policy_revision=1,
            compression_reason="below_threshold",
            latency_ms=10,
            retry_count=0,
            cost_nanos=1,
            api_key_id="vk_synthetic",
        )

    @staticmethod
    def _reservation() -> BudgetReservationRequest:
        return BudgetReservationRequest(
            schema_version=USAGE_LEDGER_SCHEMA_VERSION,
            reservation_id="qrs_" + ("b" * 32),
            key_id="vk_synthetic",
            created_at=1_800_000_000.0,
            expires_at=1_800_000_060.0,
            estimated_tokens=12,
            estimated_cost_nanos=1,
            daily_budget_nanos=100,
            monthly_budget_nanos=1000,
        )

    async def test_every_real_application_family_round_trips_to_postgresql(self) -> None:
        exercised = set()
        for family in DurableFamily:
            source_page = await self.source.read_page(family=family, offset=0, limit=100)
            self.assertTrue(source_page.records, family.value)
            for record in source_page.records:
                await self.target.put_if_absent_or_equal(record)
                await self.target.put_if_absent_or_equal(record)
            target_page = await self.target.read_page(family=family, offset=0, limit=100)
            self.assertEqual(target_page.records, source_page.records, family.value)
            exercised.add(family)
        self.assertEqual(exercised, set(DurableFamily))

    async def test_runner_completes_all_copy_families_with_real_postgresql_target(self) -> None:
        barrier = SQLiteSourceMutationBarrier(self.source_path)
        await barrier.activate(
            plan_id=PLAN_ID,
            barrier_id=BARRIER_ID,
            source_instance_id=SOURCE_ID,
        )
        checkpoint_repository = SQLiteMigrationCheckpointRepository(self.source_path)
        await checkpoint_repository.initialize()
        # Use a different plan because the family coverage fixture already occupies the first ID.
        runner_plan = "dmg_abcdefabcdefabcdefabcdefabcdefab"
        runner_barrier = "bar_abcdefabcdefabcdefabcdefabcdefab"
        await barrier.deactivate(
            plan_id=PLAN_ID,
            barrier_id=BARRIER_ID,
            source_instance_id=SOURCE_ID,
        )
        await barrier.activate(
            plan_id=runner_plan,
            barrier_id=runner_barrier,
            source_instance_id=SOURCE_ID,
        )
        runner = MigrationRunner(
            source=self.source,
            target=self.target,
            checkpoints=checkpoint_repository,
            source_barrier=barrier,
            integrity_key=b"migration-live-integrity-key-32b",
            batch_size=2,
        )
        await runner.start(
            plan_id=runner_plan,
            source_barrier_id=runner_barrier,
            explicitly_empty_families=(),
            now=NOW,
        )
        for index in range(100):
            checkpoint = await runner.copy_next(runner_plan, now=NOW + timedelta(seconds=index + 1))
            if checkpoint.phase.value == "verifying":
                break
        else:
            self.fail("Migration did not reach verification.")
        verified = await runner.verify(runner_plan, now=NOW + timedelta(seconds=101))
        self.assertEqual(verified.phase.value, "ready_to_switch")


if __name__ == "__main__":
    unittest.main()
