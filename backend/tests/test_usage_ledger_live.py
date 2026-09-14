"""Opt-in live parity tests for shared durable W4.14 usage backends.

Set ``POLARIS_TEST_POSTGRESQL_URI`` and/or ``POLARIS_TEST_MONGODB_URI``. Every test
uses a unique namespace and deletes only that namespace during teardown.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
import uuid
from pathlib import Path

import asyncpg
from pymongo import AsyncMongoClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.storage.usage_ledger_mongodb import MongoDBUsageLedgerRepository
from core.storage.usage_ledger_postgresql import PostgreSQLUsageLedgerRepository
from core.usage_ledger import (
    USAGE_LEDGER_SCHEMA_VERSION,
    BudgetReservationRequest,
    UsageLedgerEntry,
    usd_to_nanos,
)

POSTGRESQL_URI = os.getenv("POLARIS_TEST_POSTGRESQL_URI", "").strip()
MONGODB_URI = os.getenv("POLARIS_TEST_MONGODB_URI", "").strip()
NOW = 1_777_777_700.0
KEY_ID = "vk_live_enterprise"


def _usage(suffix: str, *, cost: str = "0.25") -> UsageLedgerEntry:
    return UsageLedgerEntry(
        schema_version=USAGE_LEDGER_SCHEMA_VERSION,
        event_id="use_" + (suffix * 32),
        occurred_at=NOW + 20,
        credential_ref="live-account.json",
        request_id=f"live-{suffix}",
        model="gpt-5.6",
        provider="openai",
        status_code=200,
        success=True,
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        cached_tokens=5,
        reasoning_tokens=3,
        estimated_input_tokens=110,
        estimated_tokens_saved=10,
        compressed_messages=2,
        quality_profile="balanced",
        quality_policy_revision=4,
        compression_reason="target_reached",
        latency_ms=250,
        retry_count=1,
        cost_nanos=usd_to_nanos(cost),
        api_key_id=KEY_ID,
    )


def _reservation(suffix: str, **overrides) -> BudgetReservationRequest:
    values = dict(
        schema_version=USAGE_LEDGER_SCHEMA_VERSION,
        reservation_id="qrs_" + (suffix * 32),
        key_id=KEY_ID,
        created_at=NOW,
        expires_at=NOW + 60,
        estimated_tokens=1_000,
        estimated_cost_nanos=usd_to_nanos("0.60"),
        daily_budget_nanos=usd_to_nanos("1.00"),
        monthly_budget_nanos=usd_to_nanos("10.00"),
    )
    values.update(overrides)
    return BudgetReservationRequest(**values)


class UsageLedgerLiveParityMixin:
    repository: object

    async def restart_repository(self):
        raise NotImplementedError

    async def test_reserve_commit_restart_reporting_and_idempotency(self):
        request = _reservation("a")
        first = await self.repository.reserve_budget(request)
        replay = await self.repository.reserve_budget(request)
        self.assertTrue(first.accepted)
        self.assertTrue(replay.idempotent)

        entry = _usage("a", cost="0.70")
        committed = await self.repository.commit_reservation(
            request.reservation_id, entry, transitioned_at=NOW + 20
        )
        repeated = await self.repository.commit_reservation(
            request.reservation_id, entry, transitioned_at=NOW + 20
        )
        self.assertTrue(committed.committed)
        self.assertTrue(committed.overspent)
        self.assertTrue(repeated.idempotent)

        restarted = await self.restart_repository()
        spend = await restarted.get_spend(since=0, api_key_id=KEY_ID)
        self.assertEqual((spend.calls, spend.total_tokens, spend.cost_nanos), (1, 120, 700_000_000))
        self.assertEqual((await restarted.aggregate_credentials())[0].calls, 1)
        self.assertEqual((await restarted.aggregate_providers())[0].provider, "openai")

    async def test_concurrent_reservations_are_serialized(self):
        first, second = await asyncio.gather(
            self.repository.reserve_budget(_reservation("b")),
            self.repository.reserve_budget(_reservation("c")),
        )
        decisions = [first, second]
        self.assertEqual(sum(item.accepted for item in decisions), 1)
        self.assertEqual([item.reason for item in decisions if not item.accepted], ["daily_budget"])

    async def test_reconciliation_pages_exclude_history_and_preserve_active_liability(self):
        first_reservation = _reservation("d", daily_budget_nanos=usd_to_nanos("2.00"))
        second_reservation = _reservation("f", daily_budget_nanos=usd_to_nanos("2.00"))
        self.assertTrue((await self.repository.reserve_budget(first_reservation)).accepted)
        await self.repository.append_usage(_usage("e"))
        self.assertTrue((await self.repository.reserve_budget(second_reservation)).accepted)

        first = await self.repository.reconciliation_page(after=None, limit=1)
        second = await self.repository.reconciliation_page(after=first.cursor, limit=1)

        self.assertFalse(first.complete)
        self.assertTrue(second.complete)
        self.assertEqual(first.scanned + second.scanned, 2)
        self.assertEqual(
            first.active_liability_nanos + second.active_liability_nanos,
            first_reservation.estimated_cost_nanos + second_reservation.estimated_cost_nanos,
        )
        self.assertEqual(first.active_reservations + second.active_reservations, 2)

        restarted = await self.restart_repository()
        replay_first = await restarted.reconciliation_page(after=None, limit=1)
        replay_second = await restarted.reconciliation_page(
            after=replay_first.cursor,
            limit=1,
        )
        self.assertEqual((replay_first, replay_second), (first, second))


@unittest.skipUnless(POSTGRESQL_URI, "POLARIS_TEST_POSTGRESQL_URI is not configured")
class LivePostgreSQLUsageLedgerTests(
    UsageLedgerLiveParityMixin,
    unittest.IsolatedAsyncioTestCase,
):
    async def asyncSetUp(self):
        self.schema_name = f"polaris_usage_test_{uuid.uuid4().hex}"
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
        self.repository = PostgreSQLUsageLedgerRepository(self.pool)
        await self.repository.initialize()

    async def asyncTearDown(self):
        await self.pool.close()
        admin = await asyncpg.connect(POSTGRESQL_URI)
        try:
            await admin.execute(f'DROP SCHEMA "{self.schema_name}" CASCADE')
        finally:
            await admin.close()

    async def restart_repository(self):
        restarted = PostgreSQLUsageLedgerRepository(self.pool)
        await restarted.initialize()
        return restarted


@unittest.skipUnless(MONGODB_URI, "POLARIS_TEST_MONGODB_URI is not configured")
class LiveMongoDBUsageLedgerTests(
    UsageLedgerLiveParityMixin,
    unittest.IsolatedAsyncioTestCase,
):
    async def asyncSetUp(self):
        self.database_name = f"polaris_usage_test_{uuid.uuid4().hex}"
        self.client = AsyncMongoClient(MONGODB_URI)
        self.database = self.client[self.database_name]
        self.ledger = self.database["durable_usage_ledger"]
        self.keys = self.database["durable_usage_budget_keys"]
        self.repository = MongoDBUsageLedgerRepository(self.client, self.ledger, self.keys)
        await self.repository.initialize()

    async def asyncTearDown(self):
        await self.client.drop_database(self.database_name)
        await self.client.close()

    async def restart_repository(self):
        restarted = MongoDBUsageLedgerRepository(self.client, self.ledger, self.keys)
        await restarted.initialize()
        return restarted


if __name__ == "__main__":
    unittest.main()
