"""Minimal opt-in OTLP/HTTP JSON exporter for content-free aggregate gauges."""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import httpx
from core.operational_health import get_operational_health_snapshot
from core.request_trace_service import get_request_trace_service
from core.telemetry_policy import TelemetryPolicy
from log import log


def build_otlp_metrics_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build fixed-name gauges with no customer-controlled attributes."""
    red = snapshot.get("red") or {}
    exhaustion = snapshot.get("exhaustion") or {}
    now_ns = str(time.time_ns())

    def gauge(name: str, description: str, value: float) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "unit": "1",
            "gauge": {"dataPoints": [{"timeUnixNano": now_ns, "asDouble": float(value)}]},
        }

    metrics = [
        gauge("omni.red.requests", "Requests in the bounded RED window", red.get("requests", 0)),
        gauge("omni.red.error_ratio", "Error ratio in the RED window", red.get("error_rate", 0)),
        gauge(
            "omni.red.duration.p95_ms",
            "P95 duration in milliseconds",
            red.get("p95_duration_ms", 0),
        ),
    ]
    for category in ("quota", "budget", "rate_limit", "cooldown", "capacity"):
        metrics.append(
            gauge(
                f"omni.exhaustion.{category}",
                f"Requests affected by {category} exhaustion",
                exhaustion.get(category, 0),
            )
        )
    return {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "polaris"}}]
                },
                "scopeMetrics": [{"scope": {"name": "polaris"}, "metrics": metrics}],
            }
        ]
    }


async def export_operational_metrics(policy: TelemetryPolicy) -> bool:
    if not policy.otel_enabled:
        return False
    snapshot = await get_operational_health_snapshot(
        get_request_trace_service(), window_seconds=900
    )
    endpoint = policy.otel_endpoint
    if not endpoint.endswith("/v1/metrics"):
        endpoint += "/v1/metrics"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        **dict(policy.otel_headers),
    }
    payload = build_otlp_metrics_payload(snapshot)
    async with httpx.AsyncClient(timeout=5.0) as client:
        for attempt in range(3):
            try:
                response = await client.post(endpoint, headers=headers, json=payload)
            except httpx.TransportError:
                if attempt == 2:
                    raise
                delay = float(2**attempt)
                await asyncio.sleep(delay + random.uniform(0, min(1.0, delay / 4)))
                continue
            if response.status_code not in {429, 502, 503, 504}:
                response.raise_for_status()
                if len(response.content) > 4 * 1024 * 1024:
                    raise RuntimeError("OTLP response exceeded the safety limit.")
                if response.content:
                    body = response.json()
                    partial = body.get("partialSuccess") if isinstance(body, dict) else None
                    if isinstance(partial, dict) and int(partial.get("rejectedDataPoints") or 0):
                        log.warning("OpenTelemetry collector partially rejected aggregate metrics.")
                        return False
                    if isinstance(partial, dict) and partial.get("errorMessage"):
                        log.warning("OpenTelemetry collector accepted metrics with a warning.")
                return True
            if attempt == 2:
                response.raise_for_status()
            raw_retry = response.headers.get("Retry-After", "")
            try:
                delay = min(10.0, max(0.1, float(raw_retry)))
            except ValueError:
                delay = float(2**attempt)
            await asyncio.sleep(delay + random.uniform(0, min(1.0, delay / 4)))
    return False


async def run_otel_export_loop(policy: TelemetryPolicy) -> None:
    if not policy.otel_enabled:
        return
    while True:
        try:
            await export_operational_metrics(policy)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning(f"OpenTelemetry aggregate export failed ({type(exc).__name__}).")
        await asyncio.sleep(policy.otel_interval_seconds)
