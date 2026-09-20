"""Cost provenance and priced-call coverage without rewriting legacy usage."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core import pricing, usage_stats
from core.panel import usage_routes
from core.storage.usage_ledger_mongodb import MongoDBUsageLedgerRepository
from core.storage.usage_ledger_postgresql import PostgreSQLUsageLedgerRepository
from core.storage.usage_ledger_sqlite import SQLiteUsageLedgerRepository
from core.usage_ledger import usage_entry_from_record
from core.usage_ledger_service import UsageLedgerService

from backend.tests.support import workspace_temp_directory
from backend.tests.test_usage_ledger_contract import _usage
from backend.tests.test_usage_ledger_sqlite import NOW, _reservation


class CostProvenanceContractTests(unittest.TestCase):
    def test_legacy_payload_defaults_status_without_changing_serialized_checksum(self):
        original = _usage().to_record()
        provenance_fields = {"cost_status", "cost_source", "pricing_model", "pricing_provider"}
        self.assertTrue(provenance_fields.isdisjoint(original))
        original_hash = hashlib.sha256(json.dumps(original, sort_keys=True).encode()).digest()

        restored = usage_entry_from_record(original)

        self.assertEqual(restored.cost_status, "legacy")
        self.assertEqual(restored.cost_source, "")
        self.assertEqual(restored.pricing_model, "")
        self.assertEqual(restored.pricing_provider, "")
        self.assertEqual(
            hashlib.sha256(json.dumps(restored.to_record(), sort_keys=True).encode()).digest(),
            original_hash,
        )

    def test_nonlegacy_status_and_price_attribution_round_trip(self):
        for status in ("unpriced", "estimated", "reported", "free", "unknown_usage"):
            with self.subTest(status=status):
                entry = dataclasses.replace(
                    _usage(),
                    cost_status=status,
                    cost_source={
                        "unpriced": "",
                        "estimated": "manual",
                        "reported": "provider",
                        "free": "local",
                        "unknown_usage": "litellm",
                    }[status],
                    pricing_model="priced-fixture-model" if status == "estimated" else "",
                    pricing_provider="openai" if status == "estimated" else "",
                    cost_nanos=100 if status in {"estimated", "reported"} else 0,
                )

                self.assertEqual(entry.to_record()["cost_status"], status)
                self.assertEqual(usage_entry_from_record(entry.to_record()), entry)

    def test_invalid_cost_status_is_rejected(self):
        for status in ("unknown", "ESTIMATED", "", None, 1):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    dataclasses.replace(_usage(), cost_status=status)

    def test_unpriced_or_unknown_usage_cannot_claim_nonzero_cost(self):
        for status in ("unpriced", "unknown_usage"):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    dataclasses.replace(_usage(), cost_status=status, cost_nanos=1)

    def test_legacy_entry_rejects_provenance_that_serialization_would_discard(self):
        for provenance in (
            {"cost_source": "manual"},
            {"pricing_model": "fixture-model"},
            {"pricing_provider": "gemini"},
        ):
            with self.subTest(provenance=provenance):
                with self.assertRaises(ValueError):
                    dataclasses.replace(_usage(), cost_status="legacy", **provenance)

    def test_status_and_source_must_describe_the_same_cost_evidence(self):
        for status, source in (
            ("reported", "manual"),
            ("estimated", "provider"),
            ("unknown_usage", "unsupported"),
            ("free", "budget"),
        ):
            with self.subTest(status=status, source=source):
                with self.assertRaises(ValueError):
                    dataclasses.replace(
                        _usage(), cost_status=status, cost_source=source, cost_nanos=0
                    )

    def test_legacy_aggregate_has_zero_priced_calls_without_guessing_from_nonzero_cost(self):
        for repository in (PostgreSQLUsageLedgerRepository, MongoDBUsageLedgerRepository):
            with self.subTest(repository=repository.__name__):
                aggregate = repository._aggregate_credentials([_usage()])[0]

                self.assertGreater(aggregate.cost_nanos, 0)
                self.assertEqual(aggregate.successful_calls, 1)
                self.assertEqual(aggregate.priced_calls, 0)

    def test_usage_record_exposes_coverage_based_on_successful_calls(self):
        record = usage_stats._usage_record(
            existing={},
            provider="openai",
            calls=9,
            successful_calls=6,
            failed_calls=3,
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
            cached_tokens=0,
            cache_creation_tokens=0,
            reasoning_tokens=0,
            reported_usage_calls=5,
            estimated_input_tokens=0,
            estimated_tokens_saved=0,
            compressed_messages=0,
            total_latency_ms=600,
            retry_count=0,
            cost_usd=0.01,
            priced_calls=3,
        )

        self.assertEqual(record["priced_calls"], 3)
        self.assertEqual(record["unpriced_calls"], 3)
        self.assertEqual(record["cost_usd"], 0.01)


class CostCoverageStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_committed_hard_budget_reservations_preserve_priced_call_coverage(self):
        entries = [
            dataclasses.replace(
                _usage(),
                event_id="use_" + suffix * 32,
                occurred_at=NOW + (10 if suffix == "a" else 30),
                cost_status=status,
                cost_source=source,
                cost_nanos=cost,
            )
            for suffix, status, source, cost in (
                ("a", "estimated", "manual", 100),
                ("b", "free", "local", 0),
            )
        ]
        with workspace_temp_directory() as temp_dir:
            sqlite = SQLiteUsageLedgerRepository(str(Path(temp_dir) / "usage.db"))
            await sqlite.initialize()
            try:
                for suffix, entry in zip(("a", "b"), entries):
                    reservation = _reservation(
                        suffix,
                        created_at=entry.occurred_at - 10,
                        expires_at=entry.occurred_at + 50,
                        daily_budget_nanos=10_000_000_000,
                    )
                    accepted = await sqlite.reserve_budget(reservation)
                    self.assertTrue(accepted.accepted, (suffix, accepted.reason))
                    committed = await sqlite.commit_reservation(
                        reservation.reservation_id, entry, transitioned_at=entry.occurred_at
                    )
                    self.assertTrue(committed.committed)
                sqlite_rows = await sqlite.aggregate_credentials(since=NOW)
            finally:
                await sqlite.close()

        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0].calls, 2)
        self.assertEqual(sqlite_rows[0].successful_calls, 2)
        self.assertEqual(sqlite_rows[0].cost_nanos, 100)
        self.assertEqual(sqlite_rows[0].priced_calls, 2)
        for repository in (PostgreSQLUsageLedgerRepository, MongoDBUsageLedgerRepository):
            with self.subTest(repository=repository.__name__):
                self.assertEqual(repository._aggregate_credentials(entries), sqlite_rows)

    async def test_all_storage_aggregators_count_only_successful_known_price_calls(self):
        statuses = (
            ("estimated", True),
            ("reported", True),
            ("free", True),
            ("unpriced", True),
            ("unknown_usage", True),
            ("legacy", True),
            ("estimated", False),
            ("reported", False),
            ("free", False),
        )
        entries = [
            dataclasses.replace(
                _usage(),
                event_id="use_" + f"{index:032x}",
                cost_status=status,
                cost_source={
                    "legacy": "",
                    "unpriced": "",
                    "estimated": "manual",
                    "reported": "provider",
                    "free": "local",
                    "unknown_usage": "litellm",
                }[status],
                success=success,
                status_code=200 if success else 503,
                cost_nanos=100 if status in {"estimated", "reported", "legacy"} else 0,
            )
            for index, (status, success) in enumerate(statuses)
        ]
        with workspace_temp_directory() as temp_dir:
            sqlite = SQLiteUsageLedgerRepository(str(Path(temp_dir) / "usage.db"))
            await sqlite.initialize()
            try:
                for entry in entries:
                    await sqlite.append_usage(entry)
                sqlite_rows = await sqlite.aggregate_credentials()
            finally:
                await sqlite.close()

        self.assertEqual(len(sqlite_rows), 1)
        self.assertEqual(sqlite_rows[0].calls, 9)
        self.assertEqual(sqlite_rows[0].successful_calls, 6)
        self.assertEqual(sqlite_rows[0].priced_calls, 3)
        for repository in (PostgreSQLUsageLedgerRepository, MongoDBUsageLedgerRepository):
            with self.subTest(repository=repository.__name__):
                self.assertEqual(repository._aggregate_credentials(entries), sqlite_rows)


class RecordedCostProvenanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp_dir = self.enterContext(workspace_temp_directory())
        self.repository = SQLiteUsageLedgerRepository(str(Path(temp_dir) / "usage.db"))
        await self.repository.initialize()
        self.addAsyncCleanup(self.repository.close)
        self.enterContext(
            patch.object(
                usage_stats,
                "get_usage_ledger_service",
                return_value=UsageLedgerService(self.repository),
            )
        )

    async def test_explicit_reported_cost_including_zero_wins_over_budget_estimate(self):
        for reported in (0.0, 0.125):
            with self.subTest(reported=reported):
                self.assertTrue(
                    await usage_stats.record_call(
                        "account.json",
                        model="unknown-house-model",
                        provider="custom_endpoint",
                        cost_override_usd=0.5,
                        reported_cost_usd=reported,
                        request_id=f"reported-{reported}",
                    )
                )

        entries = await self.repository._committed_entries()
        self.assertEqual([entry.cost_nanos for entry in entries], [0, 125_000_000])
        self.assertTrue(all(entry.cost_status == "reported" for entry in entries))
        self.assertTrue(all(entry.cost_source == "provider" for entry in entries))
        aggregate = (await self.repository.aggregate_credentials())[0]
        self.assertEqual(aggregate.priced_calls, 2)

    async def test_budget_override_is_estimated_not_a_provider_report(self):
        self.assertTrue(
            await usage_stats.record_call(
                "account.json",
                model="unknown-house-model",
                provider="custom_endpoint",
                cost_override_usd=0.5,
            )
        )

        entry = (await self.repository._committed_entries())[0]
        self.assertEqual(entry.cost_nanos, 500_000_000)
        self.assertEqual((entry.cost_status, entry.cost_source), ("estimated", "budget"))

    async def test_matching_budget_override_preserves_known_catalog_price_provenance(self):
        table = pricing._PricingTable()
        table.replace_dynamic(
            {("openai", "cost-provenance-fixture"): pricing.ModelPricing(7, 11)},
            fetched_at="2026-09-20T00:00:00+00:00",
        )
        with patch.object(pricing, "_pricing_table", table):
            self.assertTrue(
                await usage_stats.record_call(
                    "account.json",
                    model="cost-provenance-fixture",
                    provider="openai",
                    token_usage={"prompt_tokens": 1_000_000, "completion_tokens": 0},
                    cost_override_usd=7.0,
                )
            )

        entry = (await self.repository._committed_entries())[0]
        self.assertEqual(entry.cost_nanos, 7_000_000_000)
        self.assertEqual((entry.cost_status, entry.cost_source), ("estimated", "litellm"))
        self.assertEqual(
            (entry.pricing_provider, entry.pricing_model), ("openai", "cost-provenance-fixture")
        )

    async def test_invalid_reported_cost_is_rejected_without_ledger_write(self):
        for reported in (-1.0, float("nan"), float("inf"), True):
            with self.subTest(reported=reported):
                with self.assertRaises(ValueError):
                    await usage_stats.record_call(
                        "account.json", provider="custom_endpoint", reported_cost_usd=reported
                    )

        self.assertEqual(await self.repository._committed_entries(), [])


class DashboardCostCoverageTests(unittest.IsolatedAsyncioTestCase):
    async def test_aggregated_route_exposes_mixed_legacy_and_new_coverage_without_repricing(self):
        credential_stats = {
            "legacy.json": {
                "calls": 5,
                "successful_calls": 4,
                "failed_calls": 1,
                "cost_usd": 0.25,
            },
            "new.json": {
                "calls": 7,
                "successful_calls": 6,
                "failed_calls": 1,
                "priced_calls": 5,
                "unpriced_calls": 1,
                "cost_usd": 1.125,
            },
        }
        with (
            patch.object(
                usage_routes, "get_stats_for_period", AsyncMock(return_value=credential_stats)
            ),
            patch.object(
                usage_routes,
                "get_credential_counts",
                AsyncMock(return_value={"total": 2, "active": 2, "disabled": 0}),
            ),
            patch.object(usage_routes, "get_time_series_stats", AsyncMock(return_value=[])),
            patch.object(
                usage_routes, "get_pricing_table_status", return_value={"dynamic_source": "LiteLLM"}
            ),
        ):
            # Direct handler unit test: authentication dependencies remain unchanged.
            result = await usage_routes.get_aggregated_stats(
                period="1d", timezone_offset_minutes=420, token="unit-handler-token"
            )

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["total_calls"], 12)
        self.assertEqual(data["successful_calls"], 10)
        self.assertEqual(data["failed_calls"], 2)
        self.assertEqual(data["priced_calls"], 5)
        self.assertEqual(data["unpriced_calls"], 5)
        self.assertEqual(data["total_cost_usd"], 1.375)


if __name__ == "__main__":
    unittest.main()
