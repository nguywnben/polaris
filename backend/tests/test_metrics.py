"""Tests for the Prometheus /metrics endpoint and telemetry export wiring."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from core import metrics as metrics_module
from core import usage_stats
from core.coordination import QuotaCommitRequest, QuotaCommitResult
from core.coordination_service import (
    CoordinationService,
    clear_coordination_operation_metrics_for_testing,
    record_coordination_operation_for_testing,
)
from core.credential_operation_evidence import (
    clear_credential_operation_evidence_for_testing,
    record_credential_mutation,
)
from core.metrics import metrics, render_prometheus_metrics
from core.routing_coordination import (
    clear_routing_coordination_metrics_for_testing,
    record_routing_coordination_metric_for_testing,
)
from core.security_coordination import (
    AttemptReservationRequest,
    SecurityAttemptCategory,
)
from core.state_store import InMemoryStateStore
from core.storage.usage_ledger_sqlite import SQLiteUsageLedgerRepository
from core.usage_ledger_service import UsageLedgerService
from support import workspace_temp_directory


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


SAMPLE_ROWS = [
    {
        "provider": "google_ai_studio",
        "calls": 10,
        "successful_calls": 9,
        "failed_calls": 1,
        "total_tokens": 12345,
        "cost_usd": 0.5,
        "total_latency_ms": 4500,
    },
    {
        "provider": "openai_platform",
        "calls": 3,
        "successful_calls": 3,
        "failed_calls": 0,
        "total_tokens": 900,
        "cost_usd": 0.01,
        "total_latency_ms": 300,
    },
]


class _RejectedQuotaCommitStore:
    async def commit_quota(self, _request):
        return QuotaCommitResult(False)

    async def close(self):
        return None


class RenderPrometheusMetricsTests(unittest.TestCase):
    def setUp(self):
        clear_credential_operation_evidence_for_testing()
        clear_coordination_operation_metrics_for_testing()
        clear_routing_coordination_metrics_for_testing()

    def test_renders_per_provider_counters(self):
        output = render_prometheus_metrics(SAMPLE_ROWS)
        self.assertIn('polaris_requests_total{provider="google_ai_studio"} 10', output)
        self.assertIn('polaris_requests_success_total{provider="google_ai_studio"} 9', output)
        self.assertIn('polaris_requests_failed_total{provider="google_ai_studio"} 1', output)
        self.assertIn('polaris_tokens_total{provider="openai_platform"} 900', output)
        self.assertIn('polaris_cost_usd_total{provider="google_ai_studio"} 0.500000', output)
        self.assertIn("polaris_uptime_seconds", output)
        self.assertIn("polaris_response_cache_hits_total", output)

    def test_help_and_type_lines_present(self):
        output = render_prometheus_metrics(SAMPLE_ROWS)
        self.assertIn("# HELP polaris_requests_total", output)
        self.assertIn("# TYPE polaris_requests_total counter", output)
        self.assertIn("# TYPE polaris_uptime_seconds gauge", output)

    def test_unknown_provider_labels_are_collapsed(self):
        rows = [dict(SAMPLE_ROWS[0], provider='weird"provider\\name')]
        output = render_prometheus_metrics(rows)
        self.assertIn('provider="other"', output)
        self.assertNotIn("weird", output)

    def test_empty_rows_still_render_process_metrics(self):
        output = render_prometheus_metrics([])
        self.assertIn("polaris_uptime_seconds", output)
        self.assertIn("polaris_response_cache_entries", output)
        self.assertIn("polaris_virtual_key_quota_events_total", output)
        self.assertIn("polaris_storage_ready 1", output)

    def test_red_metrics_have_only_fixed_labels(self):
        snapshot = {
            "status": "warning",
            "red": {
                "requests": 10,
                "error_rate": 0.1,
                "p50_duration_ms": 1,
                "p95_duration_ms": 2,
                "p99_duration_ms": 3,
            },
            "exhaustion": {"quota": 2, "budget": 1},
            "routes": [{"model": "must-not-be-a-label", "route": "secret-route"}],
        }
        output = render_prometheus_metrics([], snapshot)
        self.assertIn('polaris_red_duration_milliseconds{quantile="0.95"} 2', output)
        self.assertIn('polaris_exhaustion_events{category="quota"} 2', output)
        self.assertNotIn("must-not-be-a-label", output)
        self.assertNotIn("secret-route", output)

    def test_credential_operation_metrics_are_exposed_with_bounded_labels(self):
        with patch("core.credential_operation_evidence.log.info"):
            record_credential_mutation(
                action="disable",
                operation="toggle",
                mode="primary",
                filename="must-not-appear.json",
                variant_id="google_ai_studio",
                outcome="succeeded",
                duration_ms=25,
                summary_code="operation_succeeded",
            )

        output = render_prometheus_metrics([])
        self.assertIn("# TYPE polaris_credential_operations_total counter", output)
        self.assertIn(
            'operation="toggle",outcome="succeeded",mode="provider",variant="google_ai_studio"',
            output,
        )
        self.assertIn("# TYPE polaris_credential_operation_duration_seconds histogram", output)
        self.assertNotIn("must-not-appear", output)

    def test_coordination_metrics_are_exposed_with_fixed_labels_and_empty_metadata(self):
        empty = render_prometheus_metrics([])
        self.assertIn("# HELP polaris_coordination_operations_total", empty)
        self.assertIn("# TYPE polaris_coordination_operations_total counter", empty)

        record_coordination_operation_for_testing("unknown", "reserve_quota", "rejected")
        record_coordination_operation_for_testing(["untrusted"], ["tenant/key"], ["top-secret"])
        output = render_prometheus_metrics([])
        self.assertIn(
            'polaris_coordination_operations_total{backend="unknown",operation="reserve_quota",result="rejected"} 1',
            output,
        )
        self.assertNotIn("untrusted", output)
        self.assertNotIn("tenant/key", output)
        self.assertNotIn("top-secret", output)

    def test_security_coordination_metrics_are_exposed_without_client_identity(self):
        client_index = "b" * 64
        service = CoordinationService(InMemoryStateStore())
        decision = _run(
            service.reserve_security_attempt(
                AttemptReservationRequest(
                    SecurityAttemptCategory.LOGIN,
                    client_index,
                    1,
                    300,
                    1,
                    "metrics-security-attempt",
                )
            )
        )

        self.assertTrue(decision.allowed)
        output = render_prometheus_metrics([])
        self.assertIn(
            'polaris_coordination_operations_total{backend="in_memory",operation="reserve_security_attempt",result="success"} 1',
            output,
        )
        self.assertNotIn(client_index, output)

    def test_routing_coordination_metrics_are_fixed_cardinality(self):
        record_routing_coordination_metric_for_testing("lease_acquire", "success")
        record_routing_coordination_metric_for_testing("tenant/cache-key", "top-secret")
        output = render_prometheus_metrics([])
        self.assertIn(
            'polaris_routing_coordination_events_total{operation="lease_acquire",result="success"} 1',
            output,
        )
        self.assertIn(
            'polaris_routing_coordination_events_total{operation="generation_read",result="conflict"} 1',
            output,
        )
        self.assertNotIn("tenant/cache-key", output)
        self.assertNotIn("top-secret", output)

    def test_stale_quota_commit_renders_as_rejected_not_success(self):
        service = CoordinationService(_RejectedQuotaCommitStore())
        result = _run(service.commit_quota(QuotaCommitRequest("stale", 1.0, None, None, False)))

        self.assertFalse(result.committed)
        output = render_prometheus_metrics([])
        self.assertIn(
            'polaris_coordination_operations_total{backend="unknown",operation="commit_quota",result="rejected"} 1',
            output,
        )
        self.assertNotIn('operation="commit_quota",result="success"', output)


class MetricsEndpointTests(unittest.TestCase):
    def test_endpoint_is_not_externally_enabled_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            response = _run(metrics(authorization=None))
        self.assertEqual(response.status_code, 404)

    def test_enabled_endpoint_returns_text_format(self):
        env = {"PROMETHEUS_EXPORT_ENABLED": "true", "METRICS_TOKEN": "x" * 32}
        with (
            patch.dict("os.environ", env, clear=True),
            patch.object(
                metrics_module,
                "get_provider_metrics",
                new=AsyncMock(return_value=SAMPLE_ROWS),
            ),
        ):
            response = _run(metrics(authorization=f"Bearer {'x' * 32}"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.media_type)
        self.assertIn(b"polaris_requests_total", response.body)

    def test_token_protection_rejects_missing_bearer(self):
        env = {"PROMETHEUS_EXPORT_ENABLED": "true", "METRICS_TOKEN": "s" * 32}
        with patch.dict("os.environ", env, clear=True):
            response = _run(metrics(authorization=None))
            self.assertEqual(response.status_code, 401)

            response_bad = _run(metrics(authorization="Bearer wrong"))
            self.assertEqual(response_bad.status_code, 401)

    def test_token_protection_accepts_valid_bearer(self):
        env = {"PROMETHEUS_EXPORT_ENABLED": "true", "METRICS_TOKEN": "s" * 32}
        with patch.dict("os.environ", env, clear=True):
            with patch.object(
                metrics_module,
                "get_provider_metrics",
                new=AsyncMock(return_value=[]),
            ):
                response = _run(metrics(authorization=f"Bearer {'s' * 32}"))
        self.assertEqual(response.status_code, 200)

    def test_invalid_enabled_configuration_fails_closed(self):
        env = {"PROMETHEUS_EXPORT_ENABLED": "true", "METRICS_TOKEN": "short"}
        with patch.dict("os.environ", env, clear=True):
            response = _run(metrics(authorization="Bearer short"))
        self.assertEqual(response.status_code, 503)


class ProviderMetricsLedgerTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_provider_metrics_groups_by_provider(self):
        with workspace_temp_directory() as temp_dir:
            repository = SQLiteUsageLedgerRepository(str(Path(temp_dir) / "credentials.db"))
            await repository.initialize()
            service = UsageLedgerService(repository)
            try:
                with patch.object(usage_stats, "get_usage_ledger_service", return_value=service):
                    await usage_stats.record_call(
                        "a.json",
                        model="gpt-4o-mini",
                        provider="openai_platform",
                        token_usage={"prompt_tokens": 100, "completion_tokens": 10},
                    )
                    await usage_stats.record_call(
                        "a.json",
                        model="gpt-4o-mini",
                        provider="openai_platform",
                        status_code=500,
                        success=False,
                    )
                    await usage_stats.record_call(
                        "b.json",
                        model="gemini-2.5-flash",
                        provider="google_ai_studio",
                        token_usage={"promptTokenCount": 50, "candidatesTokenCount": 5},
                    )

                    rows = await usage_stats.get_provider_metrics()
                    by_provider = {row["provider"]: row for row in rows}

                    self.assertEqual(by_provider["openai_platform"]["calls"], 2)
                    self.assertEqual(by_provider["openai_platform"]["successful_calls"], 1)
                    self.assertEqual(by_provider["openai_platform"]["failed_calls"], 1)
                    self.assertEqual(by_provider["google_ai_studio"]["calls"], 1)
                    self.assertGreater(by_provider["google_ai_studio"]["total_tokens"], 0)
            finally:
                await service.close()


class TelemetryConfigTests(unittest.TestCase):
    def test_disabled_without_keys(self):
        import config as config_module

        async def fake_get_config_value(key, default=None, env_var=None):
            return default

        async def scenario():
            with patch.object(config_module, "get_config_value", new=fake_get_config_value):
                return await config_module.get_telemetry_config()

        settings = _run(scenario())
        self.assertFalse(settings["enabled"])
        self.assertEqual(settings["langfuse_host"], "https://cloud.langfuse.com")

    def test_enabled_with_env_keys(self):
        import config as config_module

        with patch.dict(
            "os.environ",
            {
                "LANGFUSE_PUBLIC_KEY": "pk-test",
                "LANGFUSE_SECRET_KEY": "sk-test",
                "LANGFUSE_HOST": "https://langfuse.internal",
            },
        ):
            settings = _run(config_module.get_telemetry_config())
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["langfuse_host"], "https://langfuse.internal")


if __name__ == "__main__":
    unittest.main()
