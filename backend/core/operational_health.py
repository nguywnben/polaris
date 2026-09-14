"""Bounded, content-free operational RED and route-health summaries."""

from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from core.request_trace import RequestTrace, RequestTraceQuery

MAX_HEALTH_SAMPLE_TRACES = 5_000
MAX_HEALTH_ROUTES = 50
HEALTH_SNAPSHOT_CACHE_SECONDS = 15
_SNAPSHOT_CACHE: dict[tuple[int, int, int], tuple[float, dict[str, Any]]] = {}
EXHAUSTION_REASONS = {
    "quota_exceeded": "quota",
    "budget_exceeded": "budget",
    "rate_limited": "rate_limit",
    "cooldown_active": "cooldown",
    "quota_cooldown": "cooldown",
    "model_cooldown": "cooldown",
    "no_candidate": "capacity",
    "model_unavailable": "capacity",
}


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _status(total: int, error_rate: float, p95_ms: int) -> str:
    if total == 0:
        return "no_data"
    if error_rate >= 0.05 or p95_ms >= 15_000:
        return "critical"
    if error_rate >= 0.01 or p95_ms >= 5_000:
        return "warning"
    return "healthy"


def _is_service_error(trace: RequestTrace) -> bool:
    """Exclude caller/policy rejections from service-failure SLOs."""
    return trace.outcome not in {"succeeded", "client_error", "denied"}


def build_operational_health_snapshot(
    traces: Iterable[RequestTrace], *, window_seconds: int, truncated: bool = False
) -> dict[str, Any]:
    """Aggregate validated traces without retaining IDs, content, or unbounded dimensions."""
    sample = list(traces)
    errors = sum(_is_service_error(trace) for trace in sample)
    rejections = sum(trace.outcome in {"client_error", "denied"} for trace in sample)
    durations = [trace.duration_ms for trace in sample]
    error_rate = errors / len(sample) if sample else 0.0
    route_rows: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"requests": 0, "errors": 0, "durations": []}
    )
    exhaustion: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()
    protocols: Counter[str] = Counter()
    for trace in sample:
        outcomes[trace.outcome] += 1
        protocols[trace.protocol] += 1
        provider = trace.selected_provider or "unassigned"
        model = trace.requested_model or "unassigned"
        row = route_rows[(provider, model)]
        row["requests"] += 1
        row["errors"] += _is_service_error(trace)
        row["durations"].append(trace.duration_ms)
        seen: set[str] = set()
        for decision in trace.decisions:
            kind = EXHAUSTION_REASONS.get(decision.reason)
            if kind and kind not in seen:
                exhaustion[kind] += 1
                seen.add(kind)

    ranked = sorted(route_rows.items(), key=lambda item: (-item[1]["requests"], item[0]))
    routes = []
    for (provider, model), row in ranked[:MAX_HEALTH_ROUTES]:
        route_error_rate = row["errors"] / row["requests"] if row["requests"] else 0.0
        p95 = _percentile(row["durations"], 0.95)
        routes.append(
            {
                "route": f"{provider} / {model}",
                "provider": provider,
                "model": model,
                "requests": row["requests"],
                "errors": row["errors"],
                "error_rate": round(route_error_rate, 4),
                "p95_duration_ms": p95,
                "status": _status(row["requests"], route_error_rate, p95),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_seconds": window_seconds,
        "status": _status(len(sample), error_rate, _percentile(durations, 0.95)),
        "sample_size": len(sample),
        "sample_truncated": bool(truncated or len(ranked) > MAX_HEALTH_ROUTES),
        "red": {
            "requests": len(sample),
            "requests_per_minute": round(len(sample) / max(1, window_seconds) * 60, 3),
            "errors": errors,
            "rejections": rejections,
            "error_rate": round(error_rate, 4),
            "p50_duration_ms": _percentile(durations, 0.50),
            "p95_duration_ms": _percentile(durations, 0.95),
            "p99_duration_ms": _percentile(durations, 0.99),
        },
        "outcomes": dict(sorted(outcomes.items())),
        "protocols": dict(sorted(protocols.items())),
        "exhaustion": {
            name: exhaustion.get(name, 0)
            for name in ("quota", "budget", "rate_limit", "cooldown", "capacity")
        },
        "routes": routes,
    }


async def get_operational_health_snapshot(
    service: Any,
    *,
    window_seconds: int = 900,
    max_traces: int = MAX_HEALTH_SAMPLE_TRACES,
    cache_seconds: int = HEALTH_SNAPSHOT_CACHE_SECONDS,
) -> dict[str, Any]:
    max_traces = min(MAX_HEALTH_SAMPLE_TRACES, max(1, int(max_traces)))
    cache_key = (id(service), window_seconds, max_traces)
    cached = _SNAPSHOT_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < max(0, cache_seconds):
        return deepcopy(cached[1])
    traces: list[RequestTrace] = []
    cursor: str | None = None
    has_more = False
    started_after = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    while len(traces) < max_traces:
        page_size = min(200, max_traces - len(traces))
        page = await service.query(
            RequestTraceQuery(
                started_after=started_after,
                page_size=page_size,
                cursor=cursor,
            )
        )
        traces.extend(page.traces)
        cursor = page.next_cursor
        has_more = cursor is not None
        if not cursor:
            break
    result = build_operational_health_snapshot(
        traces, window_seconds=window_seconds, truncated=has_more
    )
    if cache_seconds > 0:
        if len(_SNAPSHOT_CACHE) >= 16:
            oldest = min(_SNAPSHOT_CACHE, key=lambda key: _SNAPSHOT_CACHE[key][0])
            _SNAPSHOT_CACHE.pop(oldest, None)
        _SNAPSHOT_CACHE[cache_key] = (time.monotonic(), deepcopy(result))
    return result
