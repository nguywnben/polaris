"""Contract tests for bounded RED, route-health, and exhaustion summaries."""

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.operational_health import build_operational_health_snapshot
from core.request_trace import REQUEST_TRACE_SCHEMA_VERSION, RequestDecision, RequestTrace
from core.request_trace_service import RequestTraceService
from core.routing_decision import RouteCandidate, RouteDecision


def _run(coro):
    return asyncio.run(coro)


def _trace(index: int, *, outcome="succeeded", duration_ms=100, provider="openai"):
    now = datetime.now(timezone.utc) - timedelta(seconds=index)
    reason = "completed"
    category = "outcome"
    if outcome == "rate_limited":
        reason, category = "quota_exceeded", "quota"
    return RequestTrace(
        schema_version=REQUEST_TRACE_SCHEMA_VERSION,
        trace_id=f"{index + 1:032x}",
        request_id=f"request-{index}",
        protocol="openai_chat",
        started_at=now.isoformat(),
        completed_at=(now + timedelta(milliseconds=duration_ms)).isoformat(),
        outcome=outcome,
        status_code=200 if outcome == "succeeded" else 429 if outcome == "rate_limited" else 401,
        duration_ms=duration_ms,
        requested_model="customer-model-name",
        selected_provider=provider,
        decisions=(
            RequestDecision(
                sequence=1,
                elapsed_ms=duration_ms,
                category=category,
                action="completed" if category == "outcome" else "denied",
                result="succeeded" if outcome == "succeeded" else "denied",
                reason=reason,
                provider=provider,
                model="customer-model-name",
            ),
        ),
    )


class OperationalHealthTests(unittest.TestCase):
    def test_red_quantiles_routes_and_exhaustion_are_bounded(self):
        traces = [_trace(index, duration_ms=(index + 1) * 100) for index in range(10)]
        traces.append(_trace(20, outcome="rate_limited", provider="anthropic"))

        result = build_operational_health_snapshot(traces, window_seconds=900, truncated=False)

        self.assertEqual(result["red"]["requests"], 11)
        self.assertEqual(result["red"]["errors"], 1)
        self.assertEqual(result["red"]["p95_duration_ms"], 1000)
        self.assertEqual(result["exhaustion"]["quota"], 1)
        self.assertLessEqual(len(result["routes"]), 50)
        self.assertEqual(result["routes"][0]["route"], "openai / customer-model-name")

    def test_empty_snapshot_is_explicit_no_data(self):
        result = build_operational_health_snapshot([], window_seconds=3600, truncated=False)
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["red"]["requests_per_minute"], 0.0)

    def test_caller_denials_do_not_degrade_the_service_error_slo(self):
        denied = _trace(3, outcome="denied")
        result = build_operational_health_snapshot([denied], window_seconds=900)
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["red"]["errors"], 0)
        self.assertEqual(result["red"]["rejections"], 1)

    def test_snapshot_does_not_expose_trace_or_request_ids(self):
        result = build_operational_health_snapshot([_trace(1)], window_seconds=900)
        serialized = repr(result)
        self.assertNotIn("request-1", serialized)
        self.assertNotIn(f"{2:032x}", serialized)

    def test_service_query_is_capped_and_reports_truncation(self):
        class Repository:
            async def query(self, query):
                from core.request_trace import RequestTracePage

                return RequestTracePage(
                    traces=tuple(_trace(index) for index in range(query.page_size)),
                    next_cursor="more",
                )

        service = RequestTraceService(
            Repository(),
            storage=object(),
            retention_policy=__import__(
                "core.request_trace", fromlist=["RequestTraceRetentionPolicy"]
            ).RequestTraceRetentionPolicy(),
        )
        result = _run(
            __import__(
                "core.operational_health", fromlist=["get_operational_health_snapshot"]
            ).get_operational_health_snapshot(
                service, window_seconds=900, max_traces=200, cache_seconds=0
            )
        )
        self.assertTrue(result["sample_truncated"])
        self.assertEqual(result["sample_size"], 200)

    def test_authenticated_health_route_returns_bounded_contract(self):
        from core.panel import observability_routes
        from core.request_trace import RequestTracePage

        class Service:
            async def query(self, query):
                return RequestTracePage(traces=(_trace(1),), next_cursor=None)

        with patch.object(
            observability_routes, "get_request_trace_service", return_value=Service()
        ):
            response = _run(
                observability_routes.get_operational_health(window_seconds=900, token="panel")
            )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"request-1", response.body)
        self.assertIn(b"customer-model-name", response.body)
        self.assertIn(b'"telemetry"', response.body)

    def test_authenticated_routing_health_is_bounded_and_secret_free(self):
        from core.panel import observability_routes

        decision = RouteDecision(
            mode="primary",
            requested_model="model-a",
            required_provider="",
            routing_strategy="balanced",
            selected_filename=None,
            selected_provider=None,
            candidates=(
                RouteCandidate(
                    filename="owner@example.com.json",
                    provider_id="google_ai_studio",
                    state="rejected",
                    reason="backoff_rate_limited",
                    retry_after_seconds=4.2,
                ),
            ),
            created_at=100.0,
            request_id="request-secret",
            reason="cooldown_active",
            retry_after_seconds=4.2,
        )
        manager = AsyncMock()
        manager.get_recent_routing_decisions.return_value = (decision,)

        with patch.object(observability_routes, "credential_manager", manager):
            response = _run(observability_routes.get_routing_health(limit=20, token="panel"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'"reason":"cooldown_active"', response.body)
        self.assertIn(b'"retry_after_seconds":5', response.body)
        self.assertNotIn(b"owner@example.com.json", response.body)
        self.assertNotIn(b"request-secret", response.body)


class TelemetryPolicyTests(unittest.TestCase):
    def test_external_exporters_are_disabled_by_default(self):
        from core.telemetry_policy import get_telemetry_policy

        with patch.dict("os.environ", {}, clear=True):
            policy = get_telemetry_policy()
        self.assertFalse(policy.prometheus_enabled)
        self.assertFalse(policy.otel_enabled)

    def test_disabled_otel_exporter_never_constructs_network_client(self):
        from core import otel_exporter
        from core.telemetry_policy import get_telemetry_policy

        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(otel_exporter.httpx, "AsyncClient") as client,
        ):
            result = _run(otel_exporter.export_operational_metrics(get_telemetry_policy()))

        self.assertFalse(result)
        client.assert_not_called()

    def test_prometheus_requires_a_strong_token_when_enabled(self):
        from core.telemetry_policy import TelemetryConfigurationError, get_telemetry_policy

        with patch.dict(
            "os.environ",
            {"PROMETHEUS_EXPORT_ENABLED": "true", "METRICS_TOKEN": "short"},
            clear=True,
        ):
            with self.assertRaises(TelemetryConfigurationError):
                get_telemetry_policy()

    def test_otel_requires_https_and_redacts_endpoint_credentials(self):
        from core.telemetry_policy import TelemetryConfigurationError, get_telemetry_policy

        with patch.dict(
            "os.environ",
            {"OTEL_EXPORT_ENABLED": "true", "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector"},
            clear=True,
        ):
            with self.assertRaises(TelemetryConfigurationError):
                get_telemetry_policy()

    def test_otlp_payload_has_fixed_metric_names_and_no_trace_dimensions(self):
        from core.otel_exporter import build_otlp_metrics_payload

        snapshot = build_operational_health_snapshot([_trace(1)], window_seconds=900)
        payload = build_otlp_metrics_payload(snapshot)
        serialized = repr(payload)
        self.assertIn("polaris.red.error_ratio", serialized)
        self.assertNotIn("customer-model-name", serialized)
        self.assertNotIn("request-1", serialized)

    def test_otel_export_posts_json_to_metrics_path_without_content(self):
        from core import otel_exporter
        from core.telemetry_policy import get_telemetry_policy

        calls = []

        class Response:
            status_code = 200
            content = b"{}"
            headers = {}

            def raise_for_status(self):
                return None

            def json(self):
                return {}

        class Client:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, endpoint, **kwargs):
                calls.append((endpoint, kwargs))
                return Response()

        env = {
            "OTEL_EXPORT_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "https://collector.example/base",
        }
        snapshot = build_operational_health_snapshot([_trace(1)], window_seconds=900)
        with (
            patch.dict("os.environ", env, clear=True),
            patch.object(otel_exporter.httpx, "AsyncClient", Client),
            patch.object(
                otel_exporter,
                "get_operational_health_snapshot",
                new=AsyncMock(return_value=snapshot),
            ),
            patch.object(otel_exporter, "get_request_trace_service", return_value=object()),
        ):
            result = _run(otel_exporter.export_operational_metrics(get_telemetry_policy()))
        self.assertTrue(result)
        self.assertEqual(calls[0][0], "https://collector.example/base/v1/metrics")
        serialized = repr(calls[0][1]["json"])
        self.assertNotIn("customer-model-name", serialized)
        self.assertEqual(calls[0][1]["headers"]["Content-Type"], "application/json")
