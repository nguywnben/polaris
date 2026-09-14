"""Fixed-cardinality RED metrics for ephemeral Playground runs."""

from __future__ import annotations

import threading

PLAYGROUND_PROTOCOLS = frozenset(
    {"openai_chat", "openai_responses", "anthropic_messages", "gemini"}
)
PLAYGROUND_OUTCOMES = frozenset(
    {"succeeded", "invalid", "denied", "rate_limited", "timed_out", "cancelled", "failed"}
)
_DURATION_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 15.0, 30.0, 60.0, 120.0)
_lock = threading.Lock()
_run_counts: dict[tuple[str, str], int] = {}
_duration_counts: dict[tuple[str, str, float], int] = {}
_duration_sums: dict[tuple[str, str], float] = {}


def bounded_playground_protocol(value: object) -> str:
    candidate = str(value or "")
    return candidate if candidate in PLAYGROUND_PROTOCOLS else "unknown"


def bounded_playground_outcome(value: object) -> str:
    candidate = str(value or "")
    return candidate if candidate in PLAYGROUND_OUTCOMES else "failed"


def record_playground_result(protocol: object, outcome: object, duration_ms: object) -> None:
    """Record a run without user, request, model, or content labels."""
    safe_protocol = bounded_playground_protocol(protocol)
    safe_outcome = bounded_playground_outcome(outcome)
    try:
        seconds = max(0.0, min(float(duration_ms) / 1000.0, 120.0))
    except (TypeError, ValueError, OverflowError):
        seconds = 0.0
    key = (safe_protocol, safe_outcome)
    with _lock:
        _run_counts[key] = _run_counts.get(key, 0) + 1
        _duration_sums[key] = _duration_sums.get(key, 0.0) + seconds
        for bucket in _DURATION_BUCKETS:
            if seconds <= bucket:
                bucket_key = (safe_protocol, safe_outcome, bucket)
                _duration_counts[bucket_key] = _duration_counts.get(bucket_key, 0) + 1


def render_playground_metrics() -> str:
    with _lock:
        counts = dict(_run_counts)
        buckets = dict(_duration_counts)
        sums = dict(_duration_sums)
    lines = [
        "# HELP polaris_playground_runs_total Ephemeral Playground runs by protocol and outcome.",
        "# TYPE polaris_playground_runs_total counter",
    ]
    for (protocol, outcome), count in sorted(counts.items()):
        labels = f'protocol="{protocol}",outcome="{outcome}"'
        lines.append(f"polaris_playground_runs_total{{{labels}}} {count}")
    lines.extend(
        [
            "# HELP polaris_playground_run_duration_seconds Playground run duration histogram.",
            "# TYPE polaris_playground_run_duration_seconds histogram",
        ]
    )
    for protocol, outcome in sorted(sums):
        labels = f'protocol="{protocol}",outcome="{outcome}"'
        for bucket in _DURATION_BUCKETS:
            count = buckets.get((protocol, outcome, bucket), 0)
            lines.append(
                f'polaris_playground_run_duration_seconds_bucket{{{labels},le="{bucket:g}"}} {count}'
            )
        lines.append(
            f'polaris_playground_run_duration_seconds_bucket{{{labels},le="+Inf"}} '
            f"{counts[(protocol, outcome)]}"
        )
        lines.append(
            f"polaris_playground_run_duration_seconds_sum{{{labels}}} {sums[(protocol, outcome)]:.6f}"
        )
        lines.append(
            f"polaris_playground_run_duration_seconds_count{{{labels}}} {counts[(protocol, outcome)]}"
        )
    return "\n".join(lines) + "\n"


def reset_playground_metrics_for_testing() -> None:
    with _lock:
        _run_counts.clear()
        _duration_counts.clear()
        _duration_sums.clear()
