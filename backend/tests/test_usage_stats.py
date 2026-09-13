"""Integration tests for selected-backend durable usage accounting."""

from __future__ import annotations

import asyncio
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from core import usage_stats
from core.storage.usage_ledger_sqlite import SQLiteUsageLedgerRepository
from core.usage_ledger import USAGE_LEDGER_SCHEMA_VERSION, BudgetReservationRequest
from core.usage_ledger_service import UsageLedgerService
from support import workspace_temp_directory


class UsageStatsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = workspace_temp_directory()
        database_path = str(Path(self.temp_dir.__enter__()) / "credentials.db")
        repository = SQLiteUsageLedgerRepository(database_path)
        await repository.initialize()
        self.repository = repository
        self.service = UsageLedgerService(repository)
        self.service_patch = patch.object(
            usage_stats,
            "get_usage_ledger_service",
            return_value=self.service,
        )
        self.service_patch.start()

    async def asyncTearDown(self):
        self.service_patch.stop()
        await self.service.close()
        self.temp_dir.__exit__(None, None, None)

    async def test_concurrent_period_reads_share_one_inflight_aggregation(self):
        async def load(_period, _timezone_offset_minutes):
            await asyncio.sleep(0.01)
            return {"credential.json": {"calls": 1}}

        loader = AsyncMock(side_effect=load)
        with patch.object(
            usage_stats,
            "_load_stats_for_period",
            loader,
            create=True,
        ):
            first = asyncio.create_task(usage_stats.get_stats_for_period("1d"))
            second = asyncio.create_task(usage_stats.get_stats_for_period("1d"))
            results = await asyncio.gather(first, second)

        self.assertEqual(results[0], results[1])
        loader.assert_awaited_once_with("1d", 0)

    def test_usage_windows_align_to_fixed_browser_clock_boundaries(self):
        local_timezone = timezone(timedelta(hours=7))
        now = datetime(2026, 9, 13, 11, 24, tzinfo=local_timezone).timestamp()

        day_start, day_end, day_points = usage_stats.get_usage_time_window(
            "1d", timezone_offset_minutes=-420, now=now
        )
        week_start, week_end, week_points = usage_stats.get_usage_time_window(
            "7d", timezone_offset_minutes=-420, now=now
        )
        month_start, month_end, month_points = usage_stats.get_usage_time_window(
            "30d", timezone_offset_minutes=-420, now=now
        )
        all_start, all_end, all_points = usage_stats.get_usage_time_window(
            "all", timezone_offset_minutes=-420, now=now
        )

        self.assertEqual(
            datetime.fromtimestamp(day_start, local_timezone),
            datetime(2026, 9, 12, 12, 0, tzinfo=local_timezone),
        )
        self.assertEqual(
            datetime.fromtimestamp(day_end, local_timezone),
            datetime(2026, 9, 13, 12, 0, tzinfo=local_timezone),
        )
        self.assertEqual(day_points, 24)
        self.assertEqual(
            datetime.fromtimestamp(week_start, local_timezone),
            datetime(2026, 9, 6, 12, 0, tzinfo=local_timezone),
        )
        self.assertEqual(
            datetime.fromtimestamp(week_end, local_timezone),
            datetime(2026, 9, 13, 12, 0, tzinfo=local_timezone),
        )
        self.assertEqual(week_points, 28)
        self.assertEqual(
            datetime.fromtimestamp(month_start, local_timezone),
            datetime(2026, 8, 15, 0, 0, tzinfo=local_timezone),
        )
        self.assertEqual(
            datetime.fromtimestamp(month_end, local_timezone),
            datetime(2026, 9, 14, 0, 0, tzinfo=local_timezone),
        )
        self.assertEqual(month_points, 30)
        self.assertEqual((all_start, all_end, all_points), (month_start, month_end, 30))

        with self.assertRaisesRegex(ValueError, "point count"):
            usage_stats.get_usage_time_window("1d", points=0, now=now)

    def test_provider_display_names_preserve_google_ai_capitalization(self):
        self.assertEqual(
            usage_stats._provider_display_name("google_ai_studio"),
            "Google AI Studio",
        )
        self.assertEqual(
            usage_stats._provider_display_name("Google Antigravity"),
            "Google Antigravity",
        )
        self.assertEqual(usage_stats._provider_display_name("xai"), "Grok Build")

    def test_credential_display_names_distinguish_grok_from_xai_console(self):
        self.assertEqual(
            usage_stats._credential_provider_display_name("xai", "oauth"),
            "Grok Build",
        )

    def test_stream_usage_merge_preserves_split_anthropic_totals(self):
        start = usage_stats.extract_token_usage_from_stream_chunk(
            'data: {"usageMetadata":{"promptTokenCount":18,'
            '"cachedContentTokenCount":5,"cacheCreationTokenCount":3,'
            '"totalTokenCount":18}}'
        )
        delta = usage_stats.extract_token_usage_from_stream_chunk(
            'data: {"usageMetadata":{"candidatesTokenCount":4,"totalTokenCount":4}}'
        )

        merged = usage_stats.merge_token_usage(start, delta)

        self.assertEqual(merged["input_tokens"], 18)
        self.assertEqual(merged["output_tokens"], 4)
        self.assertEqual(merged["cached_tokens"], 5)
        self.assertEqual(merged["cache_creation_tokens"], 3)
        self.assertEqual(merged["total_tokens"], 22)
        self.assertTrue(merged["usage_reported"])

    def test_usage_provenance_distinguishes_missing_from_explicit_zero(self):
        self.assertFalse(usage_stats.normalize_token_usage(None)["usage_reported"])
        self.assertTrue(
            usage_stats.normalize_token_usage(
                {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            )["usage_reported"]
        )
        self.assertEqual(
            usage_stats._credential_provider_display_name("xai", "api_key"),
            "SpaceXAI Console",
        )

    async def test_record_call_persists_provider_compression_and_cost(self):
        recorded = await usage_stats.record_call(
            "credential.json",
            model="model-a",
            provider="primary",
            token_usage={
                "promptTokenCount": 120,
                "candidatesTokenCount": 30,
                "totalTokenCount": 150,
            },
            request_metrics={
                "estimated_input_tokens": 100,
                "estimated_tokens_saved": 40,
                "compressed_messages": 6,
                "quality_profile": "balanced",
                "quality_policy_revision": 7,
                "compression_reason": "target_reached",
                "latency_ms": 125,
                "retry_count": 2,
            },
            request_id="request-123",
            cost_override_usd=0.125,
        )

        rows = await self.repository.aggregate_credentials()
        self.assertTrue(recorded)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.provider, "primary")
        self.assertEqual(row.input_tokens, 120)
        self.assertEqual(row.output_tokens, 30)
        self.assertEqual(row.total_tokens, 150)
        self.assertEqual(row.reported_usage_calls, 1)
        self.assertEqual(row.estimated_input_tokens, 100)
        self.assertEqual(row.estimated_tokens_saved, 40)
        self.assertEqual(row.compressed_messages, 6)
        self.assertEqual(row.total_latency_ms, 125)
        self.assertEqual(row.retry_count, 2)
        self.assertEqual((await usage_stats.get_spend_since(0))["cost_usd"], 0.125)

    async def test_aggregate_counts_only_successes_with_provider_reported_usage(self):
        await usage_stats.record_call(
            "credential.json",
            success=True,
            token_usage=None,
        )
        await usage_stats.record_call(
            "credential.json",
            success=True,
            token_usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        )

        rows = await self.repository.aggregate_credentials()

        self.assertEqual(rows[0].successful_calls, 2)
        self.assertEqual(rows[0].reported_usage_calls, 1)

    async def test_record_call_atomically_settles_durable_budget_reservation(self):
        now = time.time()
        reservation_id = "qrs_" + ("a" * 32)
        await self.service.reserve_budget(
            BudgetReservationRequest(
                schema_version=USAGE_LEDGER_SCHEMA_VERSION,
                reservation_id=reservation_id,
                key_id="vk_enterprise",
                created_at=now,
                expires_at=now + 60,
                estimated_tokens=200,
                estimated_cost_nanos=200_000_000,
                daily_budget_nanos=1_000_000_000,
                monthly_budget_nanos=None,
            )
        )

        recorded = await usage_stats.record_call(
            "credential.json",
            provider="openai",
            token_usage={"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
            api_key_id="vk_enterprise",
            cost_override_usd=0.125,
            durable_reservation_id=reservation_id,
        )

        spend = await self.repository.get_spend(since=0, api_key_id="vk_enterprise")
        self.assertTrue(recorded)
        self.assertEqual((spend.calls, spend.total_tokens, spend.cost_nanos), (1, 100, 125_000_000))

    async def test_invalid_cost_override_is_rejected_without_a_record(self):
        with self.assertRaises(ValueError):
            await usage_stats.record_call("credential.json", cost_override_usd=float("nan"))
        self.assertEqual((await self.repository.get_spend(since=0)).calls, 0)

    async def test_deleted_credential_usage_is_retained_anonymously(self):
        filename = "google-ai-studio-private-fingerprint.json"
        await usage_stats.record_call(
            filename,
            provider="google_ai_studio",
            token_usage={
                "promptTokenCount": 40,
                "candidatesTokenCount": 10,
                "totalTokenCount": 50,
            },
        )
        changed = await usage_stats.retire_credential_usage(filename, "google_ai_studio")

        with (
            patch.object(
                usage_stats,
                "get_credential_usage_metadata",
                AsyncMock(return_value={}),
            ),
            patch.object(
                usage_stats,
                "get_all_credential_filenames",
                AsyncMock(return_value=[]),
            ),
        ):
            result = await usage_stats.get_stats_for_period("all")

        deleted = usage_stats.deleted_usage_filename("google_ai_studio")
        self.assertEqual(changed, 1)
        self.assertEqual(list(result), [deleted])
        self.assertEqual(result[deleted]["credential_label"], "Deleted credential")
        self.assertTrue(result[deleted]["is_deleted"])
        self.assertTrue(result[deleted]["is_historical"])
        self.assertEqual(result[deleted]["total_tokens"], 50)

    async def test_unavailable_and_readded_credentials_keep_history_separate(self):
        unavailable = "legacy-account.json"
        readded = "google-antigravity-account.json"
        await usage_stats.record_call(
            unavailable,
            provider="grok",
            token_usage={"totalTokenCount": 25},
        )
        await usage_stats.record_call(readded, provider="google_antigravity")
        await usage_stats.retire_credential_usage(readded, "google_antigravity")

        with (
            patch.object(
                usage_stats,
                "get_credential_usage_metadata",
                AsyncMock(
                    return_value={
                        readded: {
                            "user_email": "readded@example.com",
                            "provider": "google_antigravity",
                            "provider_name": "Google Antigravity",
                        }
                    }
                ),
            ),
            patch.object(
                usage_stats,
                "get_all_credential_filenames",
                AsyncMock(return_value=[readded]),
            ),
        ):
            result = await usage_stats.get_stats_for_period("all")

        self.assertTrue(result[unavailable]["is_historical"])
        self.assertEqual(result[unavailable]["credential_label"], "Unavailable credential")
        self.assertEqual(result[unavailable]["provider_name"], "Grok Build")
        self.assertEqual(result[readded]["calls"], 0)
        deleted = usage_stats.deleted_usage_filename("google_antigravity")
        self.assertEqual(result[deleted]["calls"], 1)

    async def test_deleted_credentials_are_aggregated_by_provider(self):
        for filename in ("account-a.json", "account-b.json"):
            await usage_stats.record_call(filename, provider="google_antigravity")
            await usage_stats.retire_credential_usage(filename, "google_antigravity")

        with (
            patch.object(
                usage_stats,
                "get_credential_usage_metadata",
                AsyncMock(return_value={}),
            ),
            patch.object(
                usage_stats,
                "get_all_credential_filenames",
                AsyncMock(return_value=[]),
            ),
        ):
            result = await usage_stats.get_stats_for_period("all")

        deleted = usage_stats.deleted_usage_filename("google_antigravity")
        self.assertEqual(list(result), [deleted])
        self.assertEqual(result[deleted]["calls"], 2)

    async def test_period_time_series_and_provider_metrics_use_selected_ledger(self):
        await usage_stats.record_call(
            "credential.json",
            provider="openai",
            token_usage={"totalTokenCount": 25, "cachedContentTokenCount": 5},
            request_metrics={
                "estimated_tokens_saved": 4,
                "compressed_messages": 2,
                "latency_ms": 125,
                "retry_count": 1,
            },
            cost_override_usd=0.01,
        )
        with (
            patch.object(
                usage_stats,
                "get_credential_usage_metadata",
                AsyncMock(return_value={}),
            ),
            patch.object(
                usage_stats,
                "get_all_credential_filenames",
                AsyncMock(return_value=[]),
            ),
        ):
            aggregate = await usage_stats.get_stats_for_period("all")
        timeline = await usage_stats.get_time_series_stats("1d", points=4)
        providers = await usage_stats.get_provider_metrics()

        self.assertEqual(aggregate["credential.json"]["estimated_tokens_saved"], 4)
        self.assertEqual(aggregate["credential.json"]["compressed_messages"], 2)
        self.assertEqual(aggregate["credential.json"]["average_latency_ms"], 125)
        self.assertEqual(sum(point["requests"] for point in timeline), 1)
        self.assertEqual(providers[0]["provider"], "openai")
        self.assertEqual(providers[0]["cost_usd"], 0.01)


if __name__ == "__main__":
    unittest.main()
