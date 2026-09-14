"""Opt-in, authenticated Prometheus endpoint with low-cardinality metrics."""

from __future__ import annotations

import hmac
import time
from typing import Dict, List, Optional

from core.coordination_service import render_coordination_operation_metrics
from core.credential_operation_evidence import render_credential_operation_metrics
from core.identity import render_management_session_metrics
from core.operational_health import get_operational_health_snapshot
from core.playground_metrics import render_playground_metrics
from core.provider_registry import (
    ANTHROPIC,
    CLAUDE_CODE,
    CLAUDE_PLATFORM,
    CODEX,
    GOOGLE_AI_STUDIO,
    GOOGLE_ANTIGRAVITY,
    GROK,
    OLLAMA,
    OPENAI,
    OPENAI_PLATFORM,
    XAI,
    XAI_CONSOLE,
)
from core.request_trace_service import get_request_trace_service
from core.response_cache import response_cache
from core.routing_coordination import render_routing_coordination_metrics
from core.runtime_lifecycle import render_runtime_metrics
from core.storage_adapter import get_storage_adapter
from core.telemetry_policy import TelemetryConfigurationError, get_telemetry_policy
from core.usage_ledger_service import render_usage_ledger_metrics
from core.usage_stats import get_provider_metrics
from core.virtual_keys import render_virtual_key_quota_metrics
from fastapi import APIRouter, Header, Response, status

router = APIRouter(tags=["Metrics"])

_PROCESS_STARTED_AT = time.time()
_METRIC_PROVIDER_LABELS = frozenset(
    {
        GOOGLE_ANTIGRAVITY,
        GOOGLE_AI_STUDIO,
        XAI,
        GROK,
        XAI_CONSOLE,
        OPENAI,
        CODEX,
        OPENAI_PLATFORM,
        ANTHROPIC,
        CLAUDE_CODE,
        CLAUDE_PLATFORM,
        OLLAMA,
        "unknown",
    }
)


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _bounded_provider_label(value: object) -> str:
    candidate = str(value or "unknown").strip().lower()
    return candidate if candidate in _METRIC_PROVIDER_LABELS else "other"


def render_prometheus_metrics(
    provider_rows: List[Dict],
    operational_snapshot: Optional[Dict] = None,
    storage_ready: bool = True,
) -> str:
    """Render gateway metrics in the Prometheus text exposition format."""
    lines: List[str] = []

    def emit(name: str, metric_type: str, help_text: str) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {metric_type}")

    emit("polaris_uptime_seconds", "gauge", "Seconds since the gateway process started.")
    lines.append(f"polaris_uptime_seconds {max(0.0, time.time() - _PROCESS_STARTED_AT):.0f}")

    emit(
        "polaris_requests_total",
        "counter",
        "Total upstream requests recorded in the usage ledger.",
    )
    emit_success = []
    emit_failed = []
    emit_tokens = []
    emit_cost = []
    emit_latency = []
    for row in provider_rows:
        provider = _escape_label_value(_bounded_provider_label(row.get("provider")))
        label = f'{{provider="{provider}"}}'
        lines.append(f"polaris_requests_total{label} {int(row.get('calls') or 0)}")
        emit_success.append(
            f"polaris_requests_success_total{label} {int(row.get('successful_calls') or 0)}"
        )
        emit_failed.append(
            f"polaris_requests_failed_total{label} {int(row.get('failed_calls') or 0)}"
        )
        emit_tokens.append(f"polaris_tokens_total{label} {int(row.get('total_tokens') or 0)}")
        emit_cost.append(f"polaris_cost_usd_total{label} {float(row.get('cost_usd') or 0.0):.6f}")
        emit_latency.append(
            f"polaris_latency_milliseconds_total{label} {int(row.get('total_latency_ms') or 0)}"
        )

    emit(
        "polaris_requests_success_total",
        "counter",
        "Successful upstream requests per provider.",
    )
    lines.extend(emit_success)
    emit("polaris_requests_failed_total", "counter", "Failed upstream requests per provider.")
    lines.extend(emit_failed)
    emit("polaris_tokens_total", "counter", "Total tokens processed per provider.")
    lines.extend(emit_tokens)
    emit(
        "polaris_cost_usd_total",
        "counter",
        "Estimated USD spend per provider from the pricing table.",
    )
    lines.extend(emit_cost)
    emit(
        "polaris_latency_milliseconds_total",
        "counter",
        "Cumulative successful-request latency per provider; divide by "
        "polaris_requests_success_total for the average.",
    )
    lines.extend(emit_latency)

    emit(
        "polaris_response_cache_hits_total",
        "counter",
        "Exact-match response cache hits since process start.",
    )
    lines.append(f"polaris_response_cache_hits_total {int(response_cache.hits)}")
    emit(
        "polaris_response_cache_misses_total",
        "counter",
        "Exact-match response cache misses since process start.",
    )
    lines.append(f"polaris_response_cache_misses_total {int(response_cache.misses)}")
    emit(
        "polaris_response_cache_entries",
        "gauge",
        "Unexpired entries currently held by the response cache.",
    )
    lines.append(f"polaris_response_cache_entries {int(response_cache.size())}")

    lines.extend(render_credential_operation_metrics().rstrip().splitlines())
    lines.extend(render_coordination_operation_metrics().rstrip().splitlines())
    lines.extend(render_routing_coordination_metrics().rstrip().splitlines())
    lines.extend(render_runtime_metrics().rstrip().splitlines())
    lines.extend(render_management_session_metrics().rstrip().splitlines())
    lines.extend(render_virtual_key_quota_metrics().rstrip().splitlines())
    lines.extend(render_usage_ledger_metrics().rstrip().splitlines())
    lines.extend(render_playground_metrics().rstrip().splitlines())
    emit("polaris_storage_ready", "gauge", "Whether the configured durable storage is reachable.")
    lines.append(f"polaris_storage_ready {int(storage_ready)}")

    if operational_snapshot:
        red = operational_snapshot.get("red", {})
        emit("polaris_red_requests", "gauge", "Requests observed in the bounded RED window.")
        lines.append(f"polaris_red_requests {int(red.get('requests') or 0)}")
        emit("polaris_red_error_ratio", "gauge", "Error ratio in the bounded RED window.")
        lines.append(f"polaris_red_error_ratio {float(red.get('error_rate') or 0):.6f}")
        emit(
            "polaris_red_rejections",
            "gauge",
            "Caller and policy rejections excluded from the service error ratio.",
        )
        lines.append(f"polaris_red_rejections {int(red.get('rejections') or 0)}")
        emit(
            "polaris_red_duration_milliseconds",
            "gauge",
            "Request duration quantiles in the bounded RED window.",
        )
        for quantile, key in (
            ("0.50", "p50_duration_ms"),
            ("0.95", "p95_duration_ms"),
            ("0.99", "p99_duration_ms"),
        ):
            lines.append(
                f'polaris_red_duration_milliseconds{{quantile="{quantile}"}} {int(red.get(key) or 0)}'
            )
        emit(
            "polaris_exhaustion_events",
            "gauge",
            "Requests affected by a bounded exhaustion category in the RED window.",
        )
        for category, count in sorted((operational_snapshot.get("exhaustion") or {}).items()):
            lines.append(
                f'polaris_exhaustion_events{{category="{_escape_label_value(category)}"}} '
                f"{int(count or 0)}"
            )
        emit(
            "polaris_operational_health_status",
            "gauge",
            "Current operational status; exactly one status label is 1.",
        )
        current = str(operational_snapshot.get("status") or "no_data")
        for label in ("healthy", "warning", "critical", "no_data"):
            lines.append(
                f'polaris_operational_health_status{{status="{label}"}} {int(label == current)}'
            )

    return "\n".join(lines) + "\n"


@router.get("/metrics", include_in_schema=True)
async def metrics(authorization: Optional[str] = Header(None)) -> Response:
    try:
        policy = get_telemetry_policy()
    except TelemetryConfigurationError:
        return Response(
            content="telemetry configuration invalid\n",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="text/plain",
        )
    if not policy.prometheus_enabled:
        return Response(content="not found\n", status_code=404, media_type="text/plain")
    provided = ""
    if authorization and authorization[:7].lower() == "bearer ":
        provided = authorization[7:]
    if not hmac.compare_digest(provided.encode(), policy.metrics_token.encode()):
        return Response(
            content="unauthorized\n",
            status_code=status.HTTP_401_UNAUTHORIZED,
            media_type="text/plain",
        )

    provider_rows = await get_provider_metrics()
    try:
        operational = await get_operational_health_snapshot(
            get_request_trace_service(), window_seconds=900
        )
    except Exception:
        operational = None
    try:
        storage = await get_storage_adapter()
        await storage.get_all_config()
        storage_ready = True
    except Exception:
        storage_ready = False
    return Response(
        content=render_prometheus_metrics(provider_rows, operational, storage_ready),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
