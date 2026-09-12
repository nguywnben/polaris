"""Tests for the model pricing table and cost ledger integration."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from core import dynamic_pricing, pricing, usage_stats
from core.storage.usage_ledger_sqlite import SQLiteUsageLedgerRepository
from core.usage_ledger_service import UsageLedgerService
from support import workspace_temp_directory


class ModelPricingLookupTests(unittest.TestCase):
    def test_pricing_status_exposes_snapshot_freshness_without_local_path(self):
        with workspace_temp_directory() as temp_dir:
            overrides_path = Path(temp_dir) / pricing.PRICING_OVERRIDES_FILENAME
            overrides_path.write_text("{}", encoding="utf-8")
            with patch.object(pricing, "_pricing_overrides_path", return_value=overrides_path):
                status = pricing.get_pricing_table_status()

        reviewed_at = date.fromisoformat(status["built_in_reviewed_at"])
        override_updated_at = datetime.fromisoformat(status["override_updated_at"])
        self.assertLessEqual(reviewed_at, date.today())
        self.assertEqual(override_updated_at.tzinfo, timezone.utc)
        self.assertTrue(status["override_file_present"])
        self.assertNotIn(str(overrides_path), repr(status))

    def test_exact_match_returns_pricing(self):
        entry = pricing.find_model_pricing("gemini-2.5-pro")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.input_per_million, 1.25)
        self.assertEqual(entry.output_per_million, 10.00)

    def test_dated_variant_inherits_base_pricing_via_longest_prefix(self):
        base = pricing.find_model_pricing("gpt-5")
        dated = pricing.find_model_pricing("gpt-5-2026-01-12")
        mini = pricing.find_model_pricing("gpt-5-mini-2026-01-12")
        self.assertIsNotNone(base)
        self.assertIsNotNone(dated)
        self.assertIsNotNone(mini)
        self.assertEqual(dated.input_per_million, base.input_per_million)
        # Longest prefix must win: gpt-5-mini variant maps to mini pricing.
        self.assertEqual(mini.input_per_million, 0.25)

    def test_models_prefix_and_tag_suffixes_are_normalized(self):
        self.assertIsNotNone(pricing.find_model_pricing("models/gemini-2.5-flash"))
        self.assertIsNone(pricing.find_model_pricing("llama3:8b"))

    def test_unknown_model_returns_none(self):
        self.assertIsNone(pricing.find_model_pricing("totally-unknown-model"))
        self.assertIsNone(pricing.find_model_pricing(""))


class CalculateCostTests(unittest.TestCase):
    def test_cost_combines_all_token_classes(self):
        # gemini-2.5-pro: in 1.25, out 10.0, cache 0.31 per 1M tokens.
        cost = pricing.calculate_cost_usd(
            "gemini-2.5-pro",
            input_tokens=1_000_000,
            output_tokens=100_000,
            cached_tokens=200_000,
            reasoning_tokens=50_000,
        )
        expected = (800_000 * 1.25 + 200_000 * 0.31 + 100_000 * 10.0 + 50_000 * 10.0) / 1_000_000
        self.assertAlmostEqual(cost, expected, places=8)

    def test_cost_prices_cache_creation_separately_from_uncached_input(self):
        table = pricing._PricingTable()
        table.replace_dynamic(
            {
                ("anthropic", "claude-test"): pricing.ModelPricing(
                    input_per_million=3.0,
                    output_per_million=15.0,
                    cache_read_per_million=0.3,
                    cache_creation_per_million=3.75,
                )
            },
            fetched_at="2026-09-12T00:00:00+00:00",
        )
        with patch.object(pricing, "_pricing_table", table):
            cost = pricing.calculate_cost_usd(
                "claude-test",
                provider="anthropic",
                input_tokens=1_000_000,
                cached_tokens=200_000,
                cache_creation_tokens=100_000,
                output_tokens=100_000,
            )

        expected = (700_000 * 3.0 + 200_000 * 0.3 + 100_000 * 3.75 + 100_000 * 15.0) / 1_000_000
        self.assertAlmostEqual(cost, expected, places=8)

    def test_cached_tokens_clamped_to_input(self):
        cost_normal = pricing.calculate_cost_usd("gpt-4o", input_tokens=100, cached_tokens=100)
        cost_overflow = pricing.calculate_cost_usd("gpt-4o", input_tokens=100, cached_tokens=5_000)
        self.assertAlmostEqual(cost_normal, cost_overflow, places=10)

    def test_overlapping_cache_classes_are_clamped_to_input(self):
        table = pricing._PricingTable()
        table.replace_dynamic(
            {
                ("anthropic", "claude-test"): pricing.ModelPricing(
                    input_per_million=3.0,
                    output_per_million=15.0,
                    cache_read_per_million=0.3,
                    cache_creation_per_million=3.75,
                )
            },
            fetched_at="2026-09-12T00:00:00+00:00",
        )
        with patch.object(pricing, "_pricing_table", table):
            cost = pricing.calculate_cost_usd(
                "claude-test",
                provider="anthropic",
                input_tokens=100,
                cached_tokens=80,
                cache_creation_tokens=80,
            )

        expected = (80 * 0.3 + 20 * 3.75) / 1_000_000
        self.assertAlmostEqual(cost, expected, places=10)

    def test_zero_cost_provider_short_circuits(self):
        cost = pricing.calculate_cost_usd(
            "gpt-4o", input_tokens=1_000_000, output_tokens=1_000_000, provider="ollama"
        )
        self.assertEqual(cost, 0.0)

    def test_unknown_model_costs_zero(self):
        self.assertEqual(pricing.calculate_cost_usd("mystery-model", input_tokens=1_000_000), 0.0)

    def test_negative_token_counts_are_sanitized(self):
        self.assertEqual(
            pricing.calculate_cost_usd("gpt-4o", input_tokens=-50, output_tokens=-10),
            0.0,
        )


class PricingOverridesTests(unittest.TestCase):
    def test_overrides_file_extends_and_replaces_builtin_entries(self):
        with workspace_temp_directory() as temp_dir:
            overrides_path = Path(temp_dir) / pricing.PRICING_OVERRIDES_FILENAME
            overrides_path.write_text(
                json.dumps(
                    {
                        "gpt-4o": {"input": 99.0, "output": 199.0},
                        "custom-house-model": {
                            "input": 1.0,
                            "output": 2.0,
                            "cache_read": 0.5,
                        },
                    }
                ),
                encoding="utf-8",
            )
            table = pricing._PricingTable()
            with patch.object(pricing, "_pricing_overrides_path", return_value=overrides_path):
                overridden = table.lookup("gpt-4o")
                custom = table.lookup("custom-house-model")
            self.assertEqual(overridden.input_per_million, 99.0)
            self.assertEqual(custom.cache_read_per_million, 0.5)

    def test_malformed_overrides_are_ignored(self):
        with workspace_temp_directory() as temp_dir:
            overrides_path = Path(temp_dir) / pricing.PRICING_OVERRIDES_FILENAME
            overrides_path.write_text("not-json", encoding="utf-8")
            table = pricing._PricingTable()
            with patch.object(pricing, "_pricing_overrides_path", return_value=overrides_path):
                entry = table.lookup("gpt-4o")
            # Falls back to the built-in table.
            self.assertEqual(entry.input_per_million, 2.50)

    def test_non_finite_or_negative_override_prices_are_ignored(self):
        for entry in (
            {"input": -1, "output": 2},
            {"input": "NaN", "output": 2},
            {"input": 1, "output": "Infinity"},
            {"input": 1, "output": 2, "cache_read": -0.5},
        ):
            with self.subTest(entry=entry):
                self.assertIsNone(pricing._parse_override_entry(entry))


class DynamicPricingTests(unittest.TestCase):
    def test_litellm_catalog_is_converted_to_provider_qualified_prices(self):
        catalog = {
            "gpt-new": {
                "litellm_provider": "openai",
                "mode": "chat",
                "input_cost_per_token": 0.000002,
                "output_cost_per_token": 0.000008,
                "cache_read_input_token_cost": 0.0000005,
                "cache_creation_input_token_cost": 0.0000025,
            },
            "gemini/gemini-new": {
                "litellm_provider": "gemini",
                "mode": "chat",
                "input_cost_per_token": 0.000001,
                "output_cost_per_token": 0.000004,
            },
        }

        parsed = dynamic_pricing.parse_litellm_catalog(catalog)

        self.assertEqual(parsed[("openai", "gpt-new")].input_per_million, 2.0)
        self.assertEqual(parsed[("openai", "gpt-new")].cache_read_per_million, 0.5)
        self.assertEqual(parsed[("openai", "gpt-new")].cache_creation_per_million, 2.5)
        self.assertEqual(parsed[("gemini", "gemini-new")].output_per_million, 4.0)

    def test_catalog_rejects_untrusted_shapes_and_unbounded_prices(self):
        with self.assertRaisesRegex(ValueError, "JSON object"):
            dynamic_pricing.parse_litellm_catalog([])

        parsed = dynamic_pricing.parse_litellm_catalog(
            {
                "embedding-only": {
                    "litellm_provider": "openai",
                    "mode": "embedding",
                    "input_cost_per_token": 0.000001,
                    "output_cost_per_token": 0.000001,
                },
                "negative": {
                    "litellm_provider": "openai",
                    "mode": "chat",
                    "input_cost_per_token": -1,
                    "output_cost_per_token": 0.000001,
                },
                "absurd": {
                    "litellm_provider": "openai",
                    "mode": "chat",
                    "input_cost_per_token": 2,
                    "output_cost_per_token": 2,
                },
            }
        )
        self.assertEqual(parsed, {})

    def test_resolution_order_is_manual_then_dynamic_then_builtin(self):
        with workspace_temp_directory() as temp_dir:
            overrides_path = Path(temp_dir) / pricing.PRICING_OVERRIDES_FILENAME
            overrides_path.write_text(
                json.dumps({"gpt-5": {"input": 99, "output": 199}}),
                encoding="utf-8",
            )
            table = pricing._PricingTable()
            table.replace_dynamic(
                {
                    ("openai", "gpt-5"): pricing.ModelPricing(9, 19),
                    ("openai", "brand-new-model"): pricing.ModelPricing(2, 8),
                },
                fetched_at="2026-09-12T00:00:00+00:00",
            )
            with patch.object(pricing, "_pricing_overrides_path", return_value=overrides_path):
                self.assertEqual(table.lookup("gpt-5", provider="openai").input_per_million, 99)
                self.assertEqual(
                    table.lookup("brand-new-model", provider="openai").output_per_million,
                    8,
                )
                self.assertEqual(table.lookup("gemini-2.5-pro").input_per_million, 1.25)

    def test_provider_qualification_prevents_cross_provider_collision(self):
        table = pricing._PricingTable()
        table.replace_dynamic(
            {
                ("openai", "shared-model"): pricing.ModelPricing(1, 2),
                ("xai", "shared-model"): pricing.ModelPricing(3, 4),
            },
            fetched_at="2026-09-12T00:00:00+00:00",
        )
        self.assertEqual(table.lookup("shared-model", provider="openai").input_per_million, 1)
        self.assertEqual(table.lookup("shared-model", provider="xai").input_per_million, 3)
        # Provider-less reservation estimates use the conservative maximum.
        self.assertEqual(table.lookup("shared-model").input_per_million, 3)
        self.assertEqual(table.lookup("shared-model").output_per_million, 4)

    def test_valid_cache_survives_a_failed_refresh(self):
        with workspace_temp_directory() as temp_dir:
            cache_path = Path(temp_dir) / dynamic_pricing.PRICING_CACHE_FILENAME
            cache_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "fetched_at": "2026-09-12T00:00:00+00:00",
                        "models": {
                            "openai/new-model": {
                                "provider": "openai",
                                "model": "new-model",
                                "input": 1.0,
                                "output": 4.0,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            table = pricing._PricingTable()
            service = dynamic_pricing.DynamicPricingService(table=table, cache_path=cache_path)

            self.assertTrue(service.load_cache())
            service.mark_refresh_failed("network_error")

            self.assertEqual(table.lookup("new-model", provider="openai").output_per_million, 4.0)
            status = table.status()
            self.assertEqual(status["dynamic_state"], "stale")
            self.assertEqual(status["dynamic_last_error"], "network_error")

    def test_provider_is_used_by_cost_calculation(self):
        table = pricing._PricingTable()
        table.replace_dynamic(
            {
                ("openai", "shared-model"): pricing.ModelPricing(1, 2),
                ("xai", "shared-model"): pricing.ModelPricing(3, 4),
            },
            fetched_at="2026-09-12T00:00:00+00:00",
        )
        with patch.object(pricing, "_pricing_table", table):
            openai_cost = pricing.calculate_cost_usd(
                "shared-model", provider="openai", input_tokens=1_000_000
            )
            xai_cost = pricing.calculate_cost_usd(
                "shared-model", provider="xai", input_tokens=1_000_000
            )
        self.assertEqual(openai_cost, 1.0)
        self.assertEqual(xai_cost, 3.0)

    def test_missing_cache_discount_uses_full_input_price(self):
        entry = pricing.ModelPricing(input_per_million=2.0, output_per_million=8.0)
        self.assertEqual(entry.effective_cache_read(), 2.0)

    def test_conflicting_catalog_aliases_are_rejected(self):
        parsed = dynamic_pricing.parse_litellm_catalog(
            {
                "gpt-conflict": {
                    "litellm_provider": "openai",
                    "mode": "chat",
                    "input_cost_per_token": 0.000001,
                    "output_cost_per_token": 0.000004,
                },
                "openai/gpt-conflict": {
                    "litellm_provider": "openai",
                    "mode": "chat",
                    "input_cost_per_token": 0.000002,
                    "output_cost_per_token": 0.000008,
                },
            }
        )
        self.assertNotIn(("openai", "gpt-conflict"), parsed)


class DynamicPricingRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_persists_and_installs_only_a_complete_catalog(self):
        catalog = {
            f"model-{index}": {
                "litellm_provider": "openai",
                "mode": "chat",
                "input_cost_per_token": 0.000001,
                "output_cost_per_token": 0.000004,
            }
            for index in range(dynamic_pricing.MIN_REMOTE_CATALOG_ENTRIES)
        }
        with workspace_temp_directory() as temp_dir:
            cache_path = Path(temp_dir) / dynamic_pricing.PRICING_CACHE_FILENAME
            table = pricing._PricingTable()
            service = dynamic_pricing.DynamicPricingService(table=table, cache_path=cache_path)
            service._download_catalog = AsyncMock(return_value=catalog)

            self.assertTrue(await service.refresh())
            self.assertTrue(cache_path.exists())
            self.assertEqual(table.status()["dynamic_model_count"], len(catalog))
            self.assertEqual(
                table.lookup("model-4", provider="openai").output_per_million,
                4.0,
            )

    async def test_failed_refresh_retains_last_good_snapshot(self):
        table = pricing._PricingTable()
        table.replace_dynamic(
            {("openai", "existing"): pricing.ModelPricing(1, 4)},
            fetched_at="2026-09-12T00:00:00+00:00",
        )
        service = dynamic_pricing.DynamicPricingService(
            table=table,
            cache_path=Path("unused-cache.json"),
        )
        service._download_catalog = AsyncMock(return_value={})

        self.assertFalse(await service.refresh())
        self.assertEqual(table.lookup("existing", provider="openai").output_per_million, 4)
        self.assertEqual(table.status()["dynamic_state"], "stale")


class CostLedgerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = workspace_temp_directory()
        repository = SQLiteUsageLedgerRepository(
            str(Path(self.temp_dir.__enter__()) / "credentials.db")
        )
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

    async def test_record_call_persists_cost_and_api_key_id(self):
        await usage_stats.record_call(
            "credential.json",
            model="gemini-2.5-flash",
            provider="google_ai_studio",
            token_usage={
                "promptTokenCount": 1_000_000,
                "candidatesTokenCount": 100_000,
                "totalTokenCount": 1_100_000,
            },
            request_id="request-cost-1",
            api_key_id="vk_test123",
        )

        spend = await usage_stats.get_spend_since(0, api_key_id="vk_test123")
        self.assertAlmostEqual(spend["cost_usd"], 0.30 + 0.25, places=6)
        self.assertEqual(spend["calls"], 1)

    async def test_get_spend_since_filters_by_api_key(self):
        for key_id in ("vk_a", "vk_a", "vk_b"):
            await usage_stats.record_call(
                "credential.json",
                model="gpt-4o-mini",
                provider="openai_platform",
                token_usage={
                    "prompt_tokens": 1_000_000,
                    "completion_tokens": 0,
                    "total_tokens": 1_000_000,
                },
                api_key_id=key_id,
            )

        spend_all = await usage_stats.get_spend_since(0)
        spend_a = await usage_stats.get_spend_since(0, api_key_id="vk_a")
        spend_b = await usage_stats.get_spend_since(0, api_key_id="vk_b")

        self.assertEqual(spend_all["calls"], 3)
        self.assertEqual(spend_a["calls"], 2)
        self.assertEqual(spend_b["calls"], 1)
        self.assertAlmostEqual(spend_all["cost_usd"], 0.45, places=6)
        self.assertAlmostEqual(spend_a["cost_usd"], 0.30, places=6)
        self.assertGreater(spend_a["total_tokens"], 0)

    async def test_spend_since_future_timestamp_returns_zero(self):
        await usage_stats.record_call(
            "credential.json",
            model="gpt-4o",
            provider="openai_platform",
            token_usage={"prompt_tokens": 1000, "completion_tokens": 100},
        )
        spend = await usage_stats.get_spend_since(9_999_999_999)
        self.assertEqual(spend["calls"], 0)
        self.assertEqual(spend["cost_usd"], 0.0)


if __name__ == "__main__":
    unittest.main()
