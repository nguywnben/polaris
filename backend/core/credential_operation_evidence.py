"""Redacted credential mutation audit events and bounded RED telemetry."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import uuid
from collections import Counter, deque
from datetime import datetime, timezone
from typing import Any

from core.provider_registry import CREDENTIAL_OPERATIONS, list_credential_variant_capabilities
from core.request_context import get_request_id
from log import log

MAX_CREDENTIAL_AUDIT_EVENTS = 1000
_DURATION_BUCKETS_SECONDS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
_ALLOWED_ACTIONS = {
    "enable",
    "disable",
    "delete",
    "enable_credit",
    "disable_credit",
}
_ALLOWED_OPERATIONS = set(CREDENTIAL_OPERATIONS)
_ALLOWED_MODES = {"code_assist", "provider"}
_ALLOWED_VARIANTS = {item["variant_id"] for item in list_credential_variant_capabilities()} | {
    "unknown"
}
_ALLOWED_OUTCOMES = {
    "succeeded",
    "unsupported",
    "not_found",
    "invalid",
    "duplicate",
    "timed_out",
    "failed",
    "cancelled",
    "unknown",
}
_ALLOWED_SUMMARIES = {
    "operation_succeeded",
    "credential_operation_unsupported",
    "credential_not_found",
    "invalid_filename",
    "duplicate_target",
    "operation_timed_out",
    "operation_failed",
    "operation_cancelled",
    "unknown",
} | {f"http_{status_code}" for status_code in (400, 404, 409, 422, 429, 500, 503)}
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_TARGET_FINGERPRINT_KEY = secrets.token_bytes(32)

_audit_events: deque[dict[str, Any]] = deque(maxlen=MAX_CREDENTIAL_AUDIT_EVENTS)
_operation_counts: Counter[tuple[str, str, str, str]] = Counter()
_duration_buckets: Counter[tuple[str, str, str, str, float]] = Counter()
_duration_counts: Counter[tuple[str, str, str, str]] = Counter()
_duration_sums: Counter[tuple[str, str, str, str]] = Counter()
_evidence_lock = threading.RLock()


def record_credential_mutation(
    *,
    action: str,
    operation: str,
    mode: str,
    filename: str,
    variant_id: str,
    outcome: str,
    duration_ms: float,
    summary_code: str,
    actor: str = "panel_session",
) -> dict[str, Any]:
    """Append one allowlisted event and update fixed-cardinality metrics."""
    safe_action = action if action in _ALLOWED_ACTIONS else "unknown"
    safe_operation = operation if operation in _ALLOWED_OPERATIONS else "unknown"
    safe_mode = _normalize_mode(mode)
    safe_variant = variant_id if variant_id in _ALLOWED_VARIANTS else "unknown"
    safe_outcome = outcome if outcome in _ALLOWED_OUTCOMES else "unknown"
    safe_summary = summary_code if summary_code in _ALLOWED_SUMMARIES else "unknown"
    safe_request_id = str(get_request_id() or "unknown")
    if not _SAFE_REQUEST_ID.fullmatch(safe_request_id):
        safe_request_id = "unknown"
    safe_duration_ms = round(max(0.0, min(float(duration_ms or 0), 300_000.0)), 3)

    bounded_filename = str(filename or "")[:512]
    target_material = f"{safe_mode}\0{bounded_filename}".encode("utf-8", errors="replace")
    target_fingerprint = hmac.new(
        _TARGET_FINGERPRINT_KEY,
        target_material,
        hashlib.sha256,
    ).hexdigest()[:20]
    event = {
        "schema_version": 1,
        "event_id": uuid.uuid4().hex,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "request_id": safe_request_id,
        "actor": "panel_session" if actor == "panel_session" else "unknown",
        "action": safe_action,
        "operation": safe_operation,
        "mode": safe_mode,
        "target_fingerprint": target_fingerprint,
        "variant_id": safe_variant,
        "outcome": safe_outcome,
        "duration_ms": safe_duration_ms,
        "summary_code": safe_summary,
    }

    metric_key = (safe_operation, safe_outcome, safe_mode, safe_variant)
    duration_seconds = safe_duration_ms / 1000.0
    with _evidence_lock:
        _audit_events.append(dict(event))
        _operation_counts[metric_key] += 1
        _duration_counts[metric_key] += 1
        _duration_sums[metric_key] += duration_seconds
        for bucket in _DURATION_BUCKETS_SECONDS:
            if duration_seconds <= bucket:
                _duration_buckets[(*metric_key, bucket)] += 1

    log.info(json.dumps({"event": "credential_mutation", **event}, separators=(",", ":")))
    return dict(event)


async def record_durable_credential_mutation(**values: Any) -> dict[str, Any]:
    """Retain W2 telemetry while appending the same logical result durably once."""

    event = record_credential_mutation(**values)
    try:
        from core.audit_service import record_credential_response

        await record_credential_response(
            request_id=event["request_id"],
            action=event["action"],
            mode=event["mode"],
            filename=str(values.get("filename") or ""),
            outcome=event["outcome"],
        )
    except Exception as exc:
        log.critical(
            "Durable credential audit append failed "
            f"(request_id={event['request_id']}, error_type={type(exc).__name__})."
        )
    return event


def get_credential_audit_events() -> tuple[dict[str, Any], ...]:
    """Return immutable copies for internal diagnostics and focused tests."""
    with _evidence_lock:
        return tuple(dict(event) for event in _audit_events)


def render_credential_operation_metrics() -> str:
    """Render fixed-cardinality Prometheus counters and duration histograms."""
    lines = [
        "# HELP polaris_credential_operations_total Credential mutation attempts by bounded outcome.",
        "# TYPE polaris_credential_operations_total counter",
    ]
    with _evidence_lock:
        metric_keys = sorted(_operation_counts)
        for key in metric_keys:
            label = _metric_label(key)
            lines.append(f"polaris_credential_operations_total{label} {_operation_counts[key]}")

        lines.extend(
            [
                "# HELP polaris_credential_operation_duration_seconds Credential mutation duration.",
                "# TYPE polaris_credential_operation_duration_seconds histogram",
            ]
        )
        for key in metric_keys:
            label_values = _metric_label_values(key)
            for bucket in _DURATION_BUCKETS_SECONDS:
                count = _duration_buckets.get((*key, bucket), 0)
                lines.append(
                    "polaris_credential_operation_duration_seconds_bucket"
                    f'{{{label_values},le="{bucket:g}"}} {count}'
                )
            count = _duration_counts[key]
            lines.append(
                "polaris_credential_operation_duration_seconds_bucket"
                f'{{{label_values},le="+Inf"}} {count}'
            )
            lines.append(
                f"polaris_credential_operation_duration_seconds_sum{{{label_values}}} "
                f"{_duration_sums[key]:.6f}"
            )
            lines.append(
                f"polaris_credential_operation_duration_seconds_count{{{label_values}}} {count}"
            )
    return "\n".join(lines) + "\n"


def clear_credential_operation_evidence_for_testing() -> None:
    with _evidence_lock:
        _audit_events.clear()
        _operation_counts.clear()
        _duration_buckets.clear()
        _duration_counts.clear()
        _duration_sums.clear()


def _normalize_mode(mode: str) -> str:
    if mode == "primary":
        return "provider"
    return mode if mode in _ALLOWED_MODES else "unknown"


def _metric_label(key: tuple[str, str, str, str]) -> str:
    return "{" + _metric_label_values(key) + "}"


def _metric_label_values(key: tuple[str, str, str, str]) -> str:
    operation, outcome, mode, variant_id = key
    return f'operation="{operation}",outcome="{outcome}",mode="{mode}",variant="{variant_id}"'
