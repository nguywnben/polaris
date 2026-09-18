"""Demo fixtures must follow production contracts, not pre-rendered UI payloads."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.demo_credentials import build_records


class DemoFidelityTests(unittest.TestCase):
    def test_corpus_fits_production_routing_capacity(self):
        from core.smart_routing import MAX_ROUTING_CANDIDATES

        records = build_records(int(time.time()))
        self.assertLessEqual(len(records), MAX_ROUTING_CANDIDATES)

    def test_refresh_dates_moves_native_quota_fields_without_changing_durations(self):
        from tools.refresh_demo_dates import _shift_json

        self.assertEqual(
            _shift_json(
                {
                    "nextDateReset": 1000,
                    "freeTrialExpiry": 2000,
                    "model_cooldowns": {"gpt-5.4": 1500},
                    "window_duration_mins": 300,
                },
                60,
            ),
            {
                "nextDateReset": 1060,
                "freeTrialExpiry": 2060,
                "model_cooldowns": {"gpt-5.4": 1560},
                "window_duration_mins": 300,
            },
        )

    def test_history_prices_and_terminal_decisions_follow_production_contracts(self):
        from core.pricing import calculate_cost_usd
        from core.usage_ledger import usd_to_nanos

        from tools.demo_activity import build_activity
        from tools.demo_application import build_keys

        now = int(time.time())
        records = build_records(now)
        keys = build_keys(now, records)
        for usage, trace in build_activity(records, keys, now):
            self.assertEqual(trace.decisions[-1].category, "outcome")
            self.assertEqual(usage.retry_count, sum(d.category == "retry" for d in trace.decisions))
            self.assertEqual(
                usage.cost_nanos,
                usd_to_nanos(
                    calculate_cost_usd(
                        usage.model,
                        provider=usage.provider,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        cached_tokens=usage.cached_tokens,
                        cache_creation_tokens=usage.cache_creation_tokens,
                        reasoning_tokens=usage.reasoning_tokens,
                    )
                ),
            )
            key = next(k for k in keys if k.id == usage.api_key_id)
            self.assertLessEqual(key.created_at, usage.occurred_at)
            if key.revoked_at:
                self.assertLess(usage.occurred_at, key.revoked_at)
            self.assertLess(usage.occurred_at, key.expires_at)

    def test_demo_does_not_override_management_or_inference_routes(self):
        root = Path(__file__).resolve().parents[2]
        preview = (root / "tools/demo_preview.py").read_text(encoding="utf-8")
        runtime = (root / "tools/demo_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn('@router.get("/api/credentials/', preview)
        self.assertNotIn("playground._dispatch_public_request =", runtime)
        self.assertNotIn("_recent_decisions.append", runtime)

    def test_meta_wire_catalog_does_not_include_polaris_namespace(self):
        import httpx

        from tools.demo_transport import fixture_response

        response = fixture_response(
            httpx.Request("GET", "https://api.meta.ai/v1/models"),
            {"variant": "muse_code", "responses": {}, "models": ["muse-code/muse-spark-1.3"]},
        )
        self.assertEqual(response.json()["data"][0]["id"], "muse-spark-1.3")

    def test_hosted_demo_catalogs_survive_the_real_provider_filters(self):
        import httpx
        from core.hosted_providers import HOSTED_PROVIDERS, _catalog_ids

        from tools.demo_transport import fixture_response

        for record in build_records(int(time.time())):
            variant = record["variant"]
            if variant not in HOSTED_PROVIDERS:
                continue
            with self.subTest(provider=variant):
                fixture = {
                    "variant": variant,
                    "responses": record["upstream"],
                    "models": record["data"]["model_ids"],
                }
                response = fixture_response(
                    httpx.Request("GET", "https://fixture.invalid/models"), fixture
                )
                self.assertEqual(_catalog_ids(response.json(), variant), fixture["models"])

    def test_all_pre_upstream_outcomes_have_no_usage_or_routing_claim(self):
        from tools.demo_activity import build_local_traces

        traces = list(build_local_traces(int(time.time())))
        self.assertEqual(
            {t.outcome for t in traces},
            {
                "denied",
                "rate_limited",
                "unavailable",
                "cancelled",
                "client_error",
                "internal_error",
                "succeeded",
            },
        )
        self.assertTrue(all(not t.selected_provider and t.total_tokens == 0 for t in traces))

    def test_models_and_quota_have_traceable_source_records(self):
        for record in build_records(int(time.time())):
            with self.subTest(filename=record["filename"]):
                self.assertTrue(record.get("sources"))
                self.assertFalse(any("demo-" in m for m in record["data"]["model_ids"]))
                self.assertNotIn("quota", record)
                self.assertIn("upstream", record)

    def test_no_generic_oauth_fields_or_made_up_identity_and_tier(self):
        for record in build_records(int(time.time())):
            data, state = record["data"], record["state"]
            with self.subTest(filename=record["filename"]):
                self.assertNotEqual(state.get("tier"), "pro")
                self.assertNotIn("token_uri", data)
                if record["variant"] in {"kiro", "muse_code"}:
                    self.assertIsNone(state.get("user_email"))
                if data["credential_type"] == "api_key":
                    self.assertIsNone(state.get("user_email"))
                    self.assertNotIn("refresh_token", data)
                if record["variant"] == "muse_code":
                    self.assertNotIn("client_secret", data)


if __name__ == "__main__":
    unittest.main()
