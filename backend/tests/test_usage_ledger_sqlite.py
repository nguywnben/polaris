"""Real SQLite W4.14 usage-ledger repository contract."""

from __future__ import annotations

import asyncio
import dataclasses
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.storage.sqlite_manager import SQLiteManager
from core.storage.usage_ledger_sqlite import SQLiteUsageLedgerRepository
from core.storage_adapter import StorageAdapter
from core.usage_ledger import (
    USAGE_LEDGER_SCHEMA_VERSION,
    BudgetReservationRequest,
    UsageLedgerConflict,
    UsageLedgerCorrupt,
    UsageLedgerEntry,
    UsageLedgerStateConflict,
    usd_to_nanos,
)

from backend.tests.support import workspace_temp_directory

NOW = 1_777_777_700.0
KEY_ID = "vk_enterprise"


def _usage(suffix: str = "a", **overrides) -> UsageLedgerEntry:
    values = {
        "schema_version": USAGE_LEDGER_SCHEMA_VERSION,
        "event_id": "use_" + (suffix * 32),
        "occurred_at": NOW + 10,
        "credential_ref": "account.json",
        "request_id": f"request-{suffix}",
        "model": "gpt-5.6",
        "provider": "openai",
        "status_code": 200,
        "success": True,
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
        "cached_tokens": 5,
        "reasoning_tokens": 3,
        "estimated_input_tokens": 110,
        "estimated_tokens_saved": 10,
        "compressed_messages": 2,
        "quality_profile": "balanced",
        "quality_policy_revision": 4,
        "compression_reason": "target_reached",
        "latency_ms": 250,
        "retry_count": 1,
        "cost_nanos": usd_to_nanos("0.25"),
        "api_key_id": KEY_ID,
        "cache_creation_tokens": 2,
        "usage_reported": True,
    }
    values.update(overrides)
    return UsageLedgerEntry(**values)


def _reservation(suffix: str, **overrides) -> BudgetReservationRequest:
    values = {
        "schema_version": USAGE_LEDGER_SCHEMA_VERSION,
        "reservation_id": "qrs_" + (suffix * 32),
        "key_id": KEY_ID,
        "created_at": NOW,
        "expires_at": NOW + 60,
        "estimated_tokens": 1_000,
        "estimated_cost_nanos": usd_to_nanos("0.60"),
        "daily_budget_nanos": usd_to_nanos("1.00"),
        "monthly_budget_nanos": usd_to_nanos("10.00"),
    }
    values.update(overrides)
    return BudgetReservationRequest(**values)


class SQLiteUsageLedgerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = workspace_temp_directory()
        self.database_path = str(Path(self.temp_dir.__enter__()) / "credentials.db")
        self.repository = SQLiteUsageLedgerRepository(self.database_path)
        await self.repository.initialize()

    async def asyncTearDown(self):
        await self.repository.close()
        self.temp_dir.__exit__(None, None, None)

    async def test_runtime_operations_reuse_one_bounded_connection(self):
        self.assertIsNotNone(self.repository._database)
        with patch(
            "core.storage.usage_ledger_sqlite.open_sqlite",
            side_effect=AssertionError("runtime operation opened another SQLite connection"),
        ):
            await self.repository.append_usage(_usage("a"))
            await self.repository.append_usage(_usage("b"))

    async def test_append_is_exactly_idempotent_and_conflict_safe(self):
        entry = _usage()
        first = await self.repository.append_usage(entry)
        repeated = await self.repository.append_usage(entry)
        self.assertTrue(first.inserted)
        self.assertFalse(first.idempotent)
        self.assertFalse(repeated.inserted)
        self.assertTrue(repeated.idempotent)

        with self.assertRaises(UsageLedgerConflict):
            await self.repository.append_usage(dataclasses.replace(entry, cost_nanos=1))

        spend = await self.repository.get_spend(since=0, api_key_id=KEY_ID)
        self.assertTrue(spend.available)
        self.assertEqual(spend.calls, 1)
        self.assertEqual(spend.total_tokens, 120)
        self.assertEqual(spend.cost_nanos, usd_to_nanos("0.25"))

    async def test_reconciliation_pages_only_scan_active_liabilities(self):
        for suffix in "abcde":
            await self.repository.append_usage(_usage(suffix, cost_nanos=0))
        first_reservation = _reservation("f", daily_budget_nanos=usd_to_nanos("2.00"))
        second_reservation = _reservation("0", daily_budget_nanos=usd_to_nanos("2.00"))
        await self.repository.reserve_budget(first_reservation)
        await self.repository.reserve_budget(second_reservation)

        first = await self.repository.reconciliation_page(after=None, limit=1)
        second = await self.repository.reconciliation_page(after=first.cursor, limit=1)

        self.assertFalse(first.complete)
        self.assertEqual(first.scanned, 1)
        self.assertTrue(second.complete)
        self.assertEqual(second.scanned, 1)
        self.assertEqual(
            first.active_liability_nanos + second.active_liability_nanos,
            first_reservation.estimated_cost_nanos + second_reservation.estimated_cost_nanos,
        )
        self.assertEqual(first.active_reservations + second.active_reservations, 2)
        self.assertNotEqual(first.snapshot_digest, second.snapshot_digest)
        replay = await self.repository.reconciliation_page(after=None, limit=1)
        self.assertEqual(replay, first)

        with self.assertRaisesRegex(ValueError, "cursor"):
            await self.repository.reconciliation_page(after="not-a-ledger-id", limit=1)

    async def test_reconciliation_counts_zero_cost_active_reservations(self):
        reservation = _reservation("f", estimated_cost_nanos=0)
        self.assertTrue((await self.repository.reserve_budget(reservation)).accepted)

        page = await self.repository.reconciliation_page(after=None, limit=1)

        self.assertTrue(page.complete)
        self.assertEqual(page.active_liability_nanos, 0)
        self.assertEqual(page.active_reservations, 1)

    async def test_initialize_rejects_an_existing_incompatible_schema(self):
        incompatible_path = str(Path(self.database_path).with_name("incompatible.db"))
        connection = sqlite3.connect(incompatible_path)
        try:
            connection.execute("CREATE TABLE durable_usage_ledger (record_id TEXT PRIMARY KEY)")
            connection.commit()
        finally:
            connection.close()

        repository = SQLiteUsageLedgerRepository(incompatible_path)
        with self.assertRaises(UsageLedgerCorrupt):
            await repository.initialize()

    async def test_initialize_rejects_wrong_types_and_index_definitions(self):
        incompatible_path = str(Path(self.database_path).with_name("wrong-types.db"))
        connection = sqlite3.connect(incompatible_path)
        try:
            connection.execute(
                """
                CREATE TABLE durable_usage_ledger (
                    record_id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL,
                    revision TEXT NOT NULL, key_id TEXT NOT NULL, created_at REAL NOT NULL,
                    expires_at REAL, transitioned_at REAL, estimated_cost_nanos TEXT,
                    daily_budget_nanos INTEGER, monthly_budget_nanos INTEGER, event_id TEXT,
                    occurred_at REAL, credential_ref TEXT, provider TEXT, success INTEGER,
                    total_tokens INTEGER, cost_nanos TEXT, api_key_id TEXT, payload TEXT NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

        repository = SQLiteUsageLedgerRepository(incompatible_path)
        with self.assertRaises(UsageLedgerCorrupt):
            await repository.initialize()

    async def test_availability_probe_touches_the_ledger_table(self):
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute("DROP TABLE durable_usage_ledger")
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(sqlite3.OperationalError):
            await self.repository.check_available()

    async def test_expiry_lookup_uses_its_bounded_partial_index(self):
        connection = sqlite3.connect(self.database_path)
        try:
            plan = connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT record_id FROM durable_usage_ledger
                WHERE kind = 'reservation' AND state = 'active' AND expires_at <= ?
                ORDER BY expires_at, record_id
                LIMIT ?
                """,
                (NOW, 100),
            ).fetchall()
            columns = connection.execute("PRAGMA index_info(idx_durable_usage_expiry)").fetchall()
            definition = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'index' "
                "AND name = 'idx_durable_usage_expiry'"
            ).fetchone()
        finally:
            connection.close()

        rendered_plan = " ".join(str(row) for row in plan)
        self.assertIn("SEARCH durable_usage_ledger", rendered_plan)
        self.assertIn("idx_durable_usage_expiry", rendered_plan)
        self.assertNotIn("TEMP B-TREE", rendered_plan)
        self.assertEqual([row[2] for row in columns], ["expires_at", "record_id"])
        self.assertIsNotNone(definition)
        self.assertIn("kind = 'reservation' AND state = 'active'", definition[0])

    async def test_concurrent_reservations_cannot_knowingly_overspend(self):
        first, second = await asyncio.gather(
            self.repository.reserve_budget(_reservation("a")),
            self.repository.reserve_budget(_reservation("b")),
        )
        accepted = [decision for decision in (first, second) if decision.accepted]
        rejected = [decision for decision in (first, second) if not decision.accepted]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].reason, "daily_budget")

    async def test_reserve_commit_restart_and_replay_count_once(self):
        request = _reservation("a")
        accepted = await self.repository.reserve_budget(request)
        repeated = await self.repository.reserve_budget(request)
        self.assertTrue(accepted.accepted)
        self.assertTrue(repeated.accepted)
        self.assertTrue(repeated.idempotent)

        entry = _usage(occurred_at=NOW + 20, cost_nanos=usd_to_nanos("0.70"))
        committed = await self.repository.commit_reservation(
            request.reservation_id,
            entry,
            transitioned_at=NOW + 20,
        )
        replayed = await self.repository.commit_reservation(
            request.reservation_id,
            entry,
            transitioned_at=NOW + 20,
        )
        self.assertTrue(committed.committed)
        self.assertTrue(committed.overspent)
        self.assertFalse(replayed.committed)
        self.assertTrue(replayed.idempotent)

        restarted = SQLiteUsageLedgerRepository(self.database_path)
        await restarted.initialize()
        spend = await restarted.get_spend(since=0, api_key_id=KEY_ID)
        self.assertEqual(spend.calls, 1)
        self.assertEqual(spend.cost_nanos, usd_to_nanos("0.70"))

        with self.assertRaises(UsageLedgerConflict):
            await restarted.commit_reservation(
                request.reservation_id,
                dataclasses.replace(entry, cost_nanos=usd_to_nanos("0.71")),
                transitioned_at=NOW + 20,
            )
        await restarted.close()

    async def test_committed_operation_admits_bounded_delivery_replay(self):
        request = _reservation("a")
        await self.repository.reserve_budget(request)
        await self.repository.commit_reservation(
            request.reservation_id,
            _usage(occurred_at=NOW + 10),
            transitioned_at=NOW + 10,
        )

        replay = await self.repository.reserve_budget(
            dataclasses.replace(
                request,
                created_at=NOW + 20,
                expires_at=NOW + 80,
            )
        )

        self.assertTrue(replay.accepted)
        self.assertTrue(replay.idempotent)
        self.assertTrue(replay.replayed)

        with self.assertRaises(UsageLedgerConflict):
            await self.repository.reserve_budget(
                dataclasses.replace(
                    request,
                    created_at=NOW + 20,
                    expires_at=NOW + 80,
                    estimated_tokens=request.estimated_tokens + 1,
                )
            )
        with self.assertRaises(UsageLedgerStateConflict):
            await self.repository.reserve_budget(
                dataclasses.replace(
                    request,
                    created_at=NOW + 61,
                    expires_at=NOW + 121,
                )
            )

    async def test_release_and_expiry_are_terminal_and_idempotent(self):
        released_request = _reservation("a")
        await self.repository.reserve_budget(released_request)
        first_release = await self.repository.release_reservation(
            released_request.reservation_id,
            transitioned_at=NOW + 10,
        )
        repeated_release = await self.repository.release_reservation(
            released_request.reservation_id,
            transitioned_at=NOW + 10,
        )
        self.assertTrue(first_release.released)
        self.assertTrue(repeated_release.idempotent)
        with self.assertRaises(UsageLedgerStateConflict):
            await self.repository.commit_reservation(
                released_request.reservation_id,
                _usage(occurred_at=NOW + 20),
                transitioned_at=NOW + 20,
            )

        expired_request = _reservation("b", created_at=NOW + 20, expires_at=NOW + 30)
        await self.repository.reserve_budget(expired_request)
        reconciled = await self.repository.reconcile_expired(now=NOW + 31, limit=100)
        repeated = await self.repository.reconcile_expired(now=NOW + 31, limit=100)
        self.assertEqual(reconciled, 1)
        self.assertEqual(repeated, 0)

        late_release_request = _reservation("c", daily_budget_nanos=usd_to_nanos("2.00"))
        await self.repository.reserve_budget(late_release_request)
        with self.assertRaises(UsageLedgerStateConflict):
            await self.repository.release_reservation(
                late_release_request.reservation_id,
                transitioned_at=NOW + 61,
            )
        self.assertEqual(
            await self.repository.reconcile_expired(now=NOW + 61, limit=100),
            0,
        )
        with self.assertRaises(UsageLedgerStateConflict):
            await self.repository.reserve_budget(late_release_request)

    async def test_conflicting_reservation_replay_and_expired_commit_fail_closed(self):
        request = _reservation("a")
        await self.repository.reserve_budget(request)
        with self.assertRaises(UsageLedgerConflict):
            await self.repository.reserve_budget(
                dataclasses.replace(request, estimated_cost_nanos=usd_to_nanos("0.50"))
            )
        with self.assertRaises(UsageLedgerStateConflict):
            await self.repository.commit_reservation(
                request.reservation_id,
                _usage(occurred_at=NOW + 61),
                transitioned_at=NOW + 61,
            )

    async def test_reporting_and_credential_retirement_use_committed_rows_only(self):
        await self.repository.append_usage(_usage("a"))
        await self.repository.append_usage(
            _usage(
                "b",
                occurred_at=NOW + 20,
                success=False,
                status_code=503,
                total_tokens=0,
                cost_nanos=0,
            )
        )
        request = _reservation("c", created_at=NOW + 30, expires_at=NOW + 90)
        await self.repository.reserve_budget(request)
        await self.repository.commit_reservation(
            request.reservation_id,
            _usage("c", occurred_at=NOW + 40, provider="anthropic", cost_nanos=10),
            transitioned_at=NOW + 40,
        )

        credentials = await self.repository.aggregate_credentials(since=NOW)
        self.assertEqual(len(credentials), 1)
        self.assertEqual(credentials[0].calls, 3)
        self.assertEqual(credentials[0].successful_calls, 2)
        self.assertEqual(credentials[0].failed_calls, 1)

        providers = await self.repository.aggregate_providers()
        self.assertEqual([row.provider for row in providers], ["anthropic", "openai"])
        self.assertEqual(sum(row.calls for row in providers), 3)

        buckets = await self.repository.aggregate_time_series(
            since=NOW,
            until=NOW + 60,
            points=3,
        )
        self.assertEqual([bucket.requests for bucket in buckets], [1, 1, 1])

        changed = await self.repository.retire_credential(
            "account.json",
            "__deleted_credential__openai.json",
            provider="openai",
            limit=100,
        )
        self.assertEqual(changed, 3)
        retired = await self.repository.aggregate_credentials(since=NOW)
        self.assertEqual(retired[0].credential_ref, "__deleted_credential__openai.json")

    async def test_dashboard_aggregates_execute_in_sql_without_materializing_ledger(self):
        await self.repository.append_usage(_usage("a"))
        request = _reservation("b", created_at=NOW + 20, expires_at=NOW + 90)
        await self.repository.reserve_budget(request)
        await self.repository.commit_reservation(
            request.reservation_id,
            _usage(
                "b",
                occurred_at=NOW + 30,
                success=False,
                status_code=503,
                input_tokens=7,
                output_tokens=2,
                total_tokens=9,
                cached_tokens=1,
                reasoning_tokens=4,
                estimated_input_tokens=8,
                estimated_tokens_saved=1,
                compressed_messages=1,
                latency_ms=50,
                retry_count=2,
                cost_nanos=10,
            ),
            transitioned_at=NOW + 30,
        )

        with patch.object(
            self.repository,
            "_committed_entries",
            side_effect=AssertionError("dashboard aggregation materialized the ledger"),
        ):
            credentials = await self.repository.aggregate_credentials(since=NOW)
            buckets = await self.repository.aggregate_time_series(
                since=NOW,
                until=NOW + 60,
                points=2,
            )

        self.assertEqual(len(credentials), 1)
        self.assertEqual(
            dataclasses.astuple(credentials[0]),
            (
                "account.json",
                "openai",
                2,
                1,
                1,
                107,
                22,
                129,
                6,
                7,
                118,
                11,
                3,
                300,
                3,
                usd_to_nanos("0.25") + 10,
                4,
                1,
            ),
        )
        self.assertEqual([bucket.requests for bucket in buckets], [1, 1])
        self.assertEqual(sum(bucket.cached_tokens for bucket in buckets), 6)

    async def test_public_timestamps_are_strict_and_finite(self):
        for invalid in (True, float("nan"), float("inf"), -1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    await self.repository.get_spend(since=invalid)
                with self.assertRaises(ValueError):
                    await self.repository.reconcile_expired(now=invalid, limit=1)

    async def test_reporting_fails_closed_before_materializing_unbounded_rows(self):
        await self.repository.append_usage(_usage("a"))
        await self.repository.append_usage(_usage("b"))

        with patch("core.storage.usage_ledger_sqlite.MAX_USAGE_REPORT_ROWS", 1):
            with self.assertRaises(UsageLedgerCorrupt):
                await self.repository.aggregate_providers()

    async def test_legacy_import_is_read_only_verified_and_incremental(self):
        source_path = str(Path(self.database_path).with_name("usage_stats.db"))
        connection = sqlite3.connect(source_path)
        try:
            connection.execute(
                """
                CREATE TABLE usage_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    request_id TEXT DEFAULT '', model TEXT DEFAULT '',
                    provider TEXT DEFAULT '', status_code INTEGER DEFAULT 200,
                    success INTEGER DEFAULT 1, input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0, total_tokens INTEGER DEFAULT 0,
                    cached_tokens INTEGER DEFAULT 0, reasoning_tokens INTEGER DEFAULT 0,
                    estimated_input_tokens INTEGER DEFAULT 0,
                    estimated_tokens_saved INTEGER DEFAULT 0,
                    compressed_messages INTEGER DEFAULT 0,
                    quality_profile TEXT DEFAULT '',
                    quality_policy_revision INTEGER DEFAULT 0,
                    compression_reason TEXT DEFAULT '', latency_ms INTEGER DEFAULT 0,
                    retry_count INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0,
                    api_key_id TEXT DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                INSERT INTO usage_logs (
                    filename, timestamp, request_id, model, provider, total_tokens,
                    quality_profile, compression_reason, cost_usd, api_key_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy.json",
                    NOW,
                    "request-legacy",
                    "gpt-5.6",
                    "openai",
                    42,
                    "balanced",
                    "target_reached",
                    0.125,
                    KEY_ID,
                ),
            )
            connection.commit()
        finally:
            connection.close()
        source_before = await asyncio.to_thread(Path(source_path).read_bytes)

        first = await self.repository.import_legacy_usage(source_path)
        replay = await self.repository.import_legacy_usage(source_path)
        self.assertEqual(first.source_count, 1)
        self.assertEqual(first.imported_count, 1)
        self.assertTrue(first.verified)
        self.assertEqual(replay.imported_count, 0)
        self.assertTrue(replay.verified)
        self.assertEqual(await asyncio.to_thread(Path(source_path).read_bytes), source_before)
        self.assertEqual((await self.repository.get_spend(since=0)).calls, 1)
        self.assertEqual(
            await self.repository.retire_credential(
                "legacy.json",
                "__deleted_credential__openai.json",
                provider="openai",
                limit=100,
            ),
            1,
        )
        self.assertTrue((await self.repository.import_legacy_usage(source_path)).verified)

        connection = sqlite3.connect(source_path)
        try:
            connection.execute(
                "INSERT INTO usage_logs (filename, timestamp) VALUES (?, ?)",
                ("second.json", NOW + 1),
            )
            connection.commit()
        finally:
            connection.close()

        incremental = await self.repository.import_legacy_usage(source_path)
        self.assertEqual(incremental.source_count, 2)
        self.assertEqual(incremental.imported_count, 1)
        self.assertTrue(incremental.verified)
        self.assertEqual((await self.repository.get_spend(since=0)).calls, 2)

        connection = sqlite3.connect(source_path)
        try:
            connection.execute("DELETE FROM usage_logs WHERE id = 2")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(UsageLedgerConflict):
            await self.repository.import_legacy_usage(source_path)


class UsageLedgerSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_forwards_creation_to_selected_backend(self):
        expected = object()
        backend = Mock()
        backend.create_usage_ledger_repository = AsyncMock(return_value=expected)
        adapter = StorageAdapter()
        adapter._backend = backend
        adapter._initialized = True

        selected = await adapter.create_usage_ledger_repository()

        self.assertIs(selected, expected)
        backend.create_usage_ledger_repository.assert_awaited_once_with()

    async def test_sqlite_manager_constructs_and_initializes_repository(self):
        manager = SQLiteManager()
        manager._db_path = "credentials.db"
        manager._credentials_dir = "credentials"
        manager._initialized = True
        repository = Mock()
        repository.initialize = AsyncMock()
        repository.import_legacy_usage = AsyncMock()

        with patch(
            "core.storage.usage_ledger_sqlite.SQLiteUsageLedgerRepository",
            return_value=repository,
        ) as repository_class:
            selected = await manager.create_usage_ledger_repository()

        repository_class.assert_called_once_with("credentials.db")
        repository.initialize.assert_awaited_once_with()
        repository.import_legacy_usage.assert_awaited_once_with(
            str(Path("credentials") / "usage_stats.db")
        )
        self.assertIs(selected, repository)


if __name__ == "__main__":
    unittest.main()
