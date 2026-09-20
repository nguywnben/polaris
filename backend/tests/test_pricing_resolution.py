"""Provider-scoped pricing resolution regressions, using synthetic fixture rates."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from core import dynamic_pricing, pricing
from core.virtual_keys import VirtualKey, VirtualKeyManager
from fastapi import HTTPException
from support import workspace_temp_directory


class ProviderScopedPricingResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = self.enterContext(workspace_temp_directory())
        self.overrides_path = Path(self.temp_dir) / pricing.PRICING_OVERRIDES_FILENAME
        self.aliases_path = Path(self.temp_dir) / "model_pricing_aliases.json"
        self.enterContext(
            patch.object(pricing, "_pricing_overrides_path", return_value=self.overrides_path)
        )
        self.enterContext(
            patch.object(pricing, "_pricing_aliases_path", return_value=self.aliases_path)
        )
        self.table = pricing._PricingTable()
        self.gemini_price = pricing.ModelPricing(7.0, 11.0, 2.0)
        self.table.replace_dynamic(
            {("gemini", "gemini-3.8-flash"): self.gemini_price},
            fetched_at="2026-09-20T00:00:00+00:00",
        )

    def test_antigravity_tiered_model_resolves_verified_base_catalog_price(self):
        resolved = self.table.lookup("gemini-3.8-flash-tiered", provider="google_antigravity")

        self.assertEqual(resolved, self.gemini_price)

    def test_antigravity_alias_does_not_apply_to_other_providers(self):
        for provider in ("google_ai_studio", "openai", "custom_endpoint"):
            with self.subTest(provider=provider):
                self.assertIsNone(self.table.lookup("gemini-3.8-flash-tiered", provider=provider))

    def test_unknown_antigravity_variants_are_not_guessed_from_a_prefix(self):
        for model in ("gemini-3.8-flash-unknown", "gemini-8.8-flash-tiered"):
            with self.subTest(model=model):
                self.assertIsNone(self.table.lookup(model, provider="google_antigravity"))

    def test_explicit_unknown_provider_cannot_take_another_vendors_exact_price(self):
        self.table.replace_dynamic(
            {("openai", "shared-fixture-model"): pricing.ModelPricing(3.0, 5.0)},
            fetched_at="2026-09-20T00:00:00+00:00",
        )

        self.assertIsNone(self.table.lookup("shared-fixture-model", provider="custom_endpoint"))

    def test_explicit_known_provider_does_not_take_another_vendors_exact_price(self):
        self.table.replace_dynamic(
            {("xai", "shared-fixture-model"): pricing.ModelPricing(3.0, 5.0)},
            fetched_at="2026-09-20T00:00:00+00:00",
        )

        self.assertIsNone(self.table.lookup("shared-fixture-model", provider="openai"))

    def test_provider_qualified_manual_price_overrides_verified_alias_catalog(self):
        self.overrides_path.write_text(
            json.dumps(
                {
                    "google_antigravity/gemini-3.8-flash-tiered": {
                        "input": 17.0,
                        "output": 19.0,
                    }
                }
            ),
            encoding="utf-8",
        )

        resolved = self.table.lookup("gemini-3.8-flash-tiered", provider="google_antigravity")

        self.assertEqual(resolved, pricing.ModelPricing(17.0, 19.0))
        self.assertIsNone(self.table.lookup("gemini-3.8-flash-tiered", provider="google_ai_studio"))

    def test_provider_qualified_manual_price_beats_plain_legacy_override(self):
        self.overrides_path.write_text(
            json.dumps(
                {
                    "google_antigravity/shared-fixture-model": {"input": 17.0, "output": 19.0},
                    "shared-fixture-model": {"input": 23.0, "output": 29.0},
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(
            self.table.lookup("shared-fixture-model", provider="google_antigravity"),
            pricing.ModelPricing(17.0, 19.0),
        )
        self.assertEqual(
            self.table.lookup("shared-fixture-model", provider="custom_endpoint"),
            pricing.ModelPricing(23.0, 29.0),
        )

    def test_plain_legacy_manual_price_still_overrides_catalog(self):
        self.overrides_path.write_text(
            json.dumps({"gemini-3.8-flash": {"input": 17.0, "output": 19.0}}),
            encoding="utf-8",
        )

        self.assertEqual(
            self.table.lookup("gemini-3.8-flash", provider="google_ai_studio"),
            pricing.ModelPricing(17.0, 19.0),
        )

    def test_legacy_prefix_requires_a_model_name_boundary(self):
        self.overrides_path.write_text(
            json.dumps({"gpt-5": {"input": 17.0, "output": 19.0}}),
            encoding="utf-8",
        )

        self.assertEqual(
            self.table.lookup("gpt-5-2026-09-20", provider="openai"),
            pricing.ModelPricing(17.0, 19.0),
        )
        self.assertIsNone(self.table.lookup("gpt-50", provider="openai"))

    def test_provider_qualified_manual_price_is_exact_not_a_prefix_rule(self):
        self.overrides_path.write_text(
            json.dumps(
                {"google_antigravity/shared-fixture-model": {"input": 17.0, "output": 19.0}}
            ),
            encoding="utf-8",
        )

        self.assertIsNone(
            self.table.lookup("shared-fixture-model-new", provider="google_antigravity")
        )

    def test_generic_alias_resolves_explicit_target_without_leaking_to_other_providers(self):
        self.aliases_path.write_text(
            json.dumps(
                {
                    "private_gateway": {
                        "house-model": {"provider": "gemini", "model": "gemini-3.8-flash"}
                    }
                }
            ),
            encoding="utf-8",
        )

        resolved = self.table.resolve("house-model", provider="private_gateway")

        self.assertEqual(resolved.pricing, self.gemini_price)
        self.assertEqual((resolved.provider, resolved.model), ("gemini", "gemini-3.8-flash"))
        self.assertIsNone(self.table.lookup("house-model", provider="other_gateway"))

    def test_aliases_are_one_hop_and_cycles_do_not_infer_prices(self):
        self.aliases_path.write_text(
            json.dumps(
                {
                    "private_gateway": {
                        "first": {"provider": "private_gateway", "model": "second"},
                        "second": {"provider": "gemini", "model": "gemini-3.8-flash"},
                        "cycle-a": {"provider": "private_gateway", "model": "cycle-b"},
                        "cycle-b": {"provider": "private_gateway", "model": "cycle-a"},
                    }
                }
            ),
            encoding="utf-8",
        )

        self.assertIsNone(self.table.lookup("first", provider="private_gateway"))
        self.assertEqual(self.table.lookup("second", provider="private_gateway"), self.gemini_price)
        self.assertIsNone(self.table.lookup("cycle-a", provider="private_gateway"))

    def test_malformed_alias_configuration_cannot_create_prices(self):
        documents = (
            "not-json",
            "[]",
            json.dumps(
                {"../gemini": {"house-model": {"provider": "gemini", "model": "gemini-3.8-flash"}}}
            ),
            json.dumps(
                {
                    "private_gateway": {
                        "house-model": {"provider": "../gemini", "model": "gemini-3.8-flash"}
                    }
                }
            ),
            json.dumps(
                {
                    "private_gateway": {
                        "house-model": {
                            "provider": "gemini",
                            "model": "gemini-3.8-flash",
                            "input": 0,
                        }
                    }
                }
            ),
        )
        for document in documents:
            with self.subTest(document=document):
                self.aliases_path.write_text(document, encoding="utf-8")
                table = pricing._PricingTable()
                table.replace_dynamic(
                    {("gemini", "gemini-3.8-flash"): self.gemini_price},
                    fetched_at="2026-09-20T00:00:00+00:00",
                )
                self.assertIsNone(table.lookup("house-model", provider="private_gateway"))
                self.assertEqual(
                    table.lookup("gemini-3.8-flash", provider="gemini"), self.gemini_price
                )

    def test_exact_dynamic_price_beats_configured_alias_target(self):
        self.aliases_path.write_text(
            json.dumps(
                {
                    "private_gateway": {
                        "house-model": {"provider": "gemini", "model": "gemini-3.8-flash"}
                    }
                }
            ),
            encoding="utf-8",
        )
        direct_price = pricing.ModelPricing(31.0, 37.0)
        self.table.replace_dynamic(
            {
                ("private_gateway", "house-model"): direct_price,
                ("gemini", "gemini-3.8-flash"): self.gemini_price,
            },
            fetched_at="2026-09-20T00:00:00+00:00",
        )

        self.assertEqual(self.table.lookup("house-model", provider="private_gateway"), direct_price)

    def test_catalog_imports_generic_providers_and_normalizes_vertex_prefix(self):
        catalog = {
            "deepseek/deepseek-chat": {"litellm_provider": "deepseek"},
            "openrouter/acme/house-model": {"litellm_provider": "openrouter"},
            "vertex_ai/gemini-fixture": {"litellm_provider": "vertex_ai"},
        }
        for entry in catalog.values():
            entry.update(mode="chat", input_cost_per_token=0.000007, output_cost_per_token=0.000011)
        parsed = dynamic_pricing.parse_litellm_catalog(catalog)
        self.table.replace_dynamic(parsed, fetched_at="2026-09-20T00:00:00+00:00")

        for provider, model in (
            ("deepseek", "deepseek-chat"),
            ("openrouter", "acme/house-model"),
            ("vertex_ai", "gemini-fixture"),
        ):
            with self.subTest(provider=provider):
                self.assertEqual(self.table.lookup(model, provider=provider).input_per_million, 7)
        self.assertIsNone(self.table.lookup("acme/house-model", provider="deepseek"))

    def test_conditional_catalog_rates_block_flat_builtin_fallback(self):
        for conditional in (
            {"input_cost_per_token_above_128k_tokens": 0.000014},
            {"tiered_pricing": [{"input": 14}]},
        ):
            with self.subTest(conditional=conditional):
                parsed = dynamic_pricing.parse_litellm_catalog(
                    {
                        "gemini/gemini-2.5-pro": {
                            "litellm_provider": "gemini",
                            "mode": "chat",
                            "input_cost_per_token": 0.000007,
                            "output_cost_per_token": 0.000011,
                            **conditional,
                        }
                    }
                )
                self.table.replace_dynamic(parsed, fetched_at="2026-09-20T00:00:00+00:00")
                self.assertIsNone(self.table.lookup("gemini-2.5-pro", provider="google_ai_studio"))
                self.assertEqual(
                    self.table.resolve("gemini-2.5-pro", "google_ai_studio").source, "unsupported"
                )

    def test_unsupported_catalog_rate_barrier_survives_cache_round_trip(self):
        cache_path = Path(self.temp_dir) / "dynamic_model_pricing.json"
        unsupported = pricing.ModelPricing(7, 11, supported=False)
        service = dynamic_pricing.DynamicPricingService(table=self.table, cache_path=cache_path)
        service._write_cache(
            {("gemini", "gemini-2.5-pro"): unsupported}, fetched_at="2026-09-20T00:00:00+00:00"
        )
        restored_table = pricing._PricingTable()
        restored_service = dynamic_pricing.DynamicPricingService(
            table=restored_table, cache_path=cache_path
        )

        self.assertTrue(restored_service.load_cache())
        self.assertIsNone(restored_table.lookup("gemini-2.5-pro", provider="gemini"))
        self.assertEqual(restored_table.resolve("gemini-2.5-pro", "gemini").source, "unsupported")

    def test_alias_target_uses_plain_manual_override_before_dynamic_catalog(self):
        self.aliases_path.write_text(
            json.dumps(
                {
                    "private_gateway": {
                        "house-model": {"provider": "gemini", "model": "gemini-3.8-flash"}
                    }
                }
            ),
            encoding="utf-8",
        )
        self.overrides_path.write_text(
            json.dumps({"gemini-3.8-flash": {"input": 17, "output": 19}}), encoding="utf-8"
        )

        resolved = self.table.resolve("house-model", provider="private_gateway")

        self.assertEqual(resolved.pricing, pricing.ModelPricing(17, 19))
        self.assertEqual(resolved.source, "manual")
        self.assertEqual((resolved.provider, resolved.model), ("gemini", "gemini-3.8-flash"))

    def test_explicit_alias_target_uses_builtin_when_catalog_is_offline(self):
        self.aliases_path.write_text(
            json.dumps(
                {
                    "private_gateway": {
                        "house-model": {"provider": "gemini", "model": "gemini-2.5-flash"}
                    }
                }
            ),
            encoding="utf-8",
        )
        self.table.replace_dynamic({}, fetched_at="2026-09-20T00:00:00+00:00")

        resolved = self.table.resolve("house-model", provider="private_gateway")

        self.assertEqual(resolved.pricing, pricing.BUILTIN_MODEL_PRICING["gemini-2.5-flash"])
        self.assertEqual(resolved.source, "builtin")
        self.assertEqual((resolved.provider, resolved.model), ("gemini", "gemini-2.5-flash"))

    def test_providerless_budget_lookup_takes_conservative_maximum_of_explicit_aliases(self):
        self.aliases_path.write_text(
            json.dumps(
                {
                    "gateway_a": {
                        "house-model": {"provider": "gemini", "model": "gemini-fixture-a"}
                    },
                    "gateway_b": {"house-model": {"provider": "openai", "model": "fixture-b"}},
                }
            ),
            encoding="utf-8",
        )
        self.table.replace_dynamic(
            {
                ("gemini", "gemini-fixture-a"): pricing.ModelPricing(17, 11, 2),
                ("openai", "fixture-b"): pricing.ModelPricing(7, 29, 5),
            },
            fetched_at="2026-09-20T00:00:00+00:00",
        )

        with patch.object(pricing, "_pricing_table", self.table):
            resolved = pricing.find_model_pricing("house-model")

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.input_per_million, 17)
        self.assertEqual(resolved.output_per_million, 29)
        self.assertEqual(resolved.effective_cache_read(), 5)

    def test_providerless_budget_lookup_fails_closed_for_unsupported_alias_target(self):
        self.aliases_path.write_text(
            json.dumps(
                {
                    "private_gateway": {
                        "house-model": {"provider": "gemini", "model": "gemini-fixture"}
                    }
                }
            ),
            encoding="utf-8",
        )
        self.table.replace_dynamic(
            {
                ("openai", "house-model"): pricing.ModelPricing(7, 11),
                ("gemini", "gemini-fixture"): pricing.ModelPricing(17, 29, supported=False),
            },
            fetched_at="2026-09-20T00:00:00+00:00",
        )

        with patch.object(pricing, "_pricing_table", self.table):
            self.assertIsNone(pricing.find_model_pricing("house-model"))

    def test_hard_budget_estimator_prices_verified_alias_and_denies_unsupported_target(self):
        record = VirtualKey(
            id="vk_pricing_test",
            name="Pricing regression",
            key_hash="0" * 64,
            key_preview="test",
            budget_daily_usd=100,
            unknown_pricing_policy="deny",
        )
        manager = VirtualKeyManager()
        with patch.object(pricing, "_pricing_table", self.table):
            estimate = manager._estimate_cost(
                record,
                models=["gemini-3.8-flash-tiered"],
                input_tokens=1_000_000,
                output_tokens=100_000,
            )
            self.assertAlmostEqual(estimate, 8.1)

            self.table.replace_dynamic(
                {("gemini", "gemini-3.8-flash"): pricing.ModelPricing(7, 11, supported=False)},
                fetched_at="2026-09-20T00:00:00+00:00",
            )
            with self.assertRaises(HTTPException) as rejected:
                manager._estimate_cost(
                    record,
                    models=["gemini-3.8-flash-tiered"],
                    input_tokens=1_000_000,
                    output_tokens=100_000,
                )
        self.assertEqual(rejected.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
