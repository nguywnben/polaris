"""Canonical bounded fields for AI quality decision telemetry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

QUALITY_PROFILES = frozenset({"quality", "balanced", "capacity", "custom", "unavailable"})
COMPRESSION_REASONS = frozenset(
    {
        "disabled",
        "below_threshold",
        "no_history",
        "invalid_history",
        "invalid_tool_history",
        "minimum_history",
        "no_safe_boundary",
        "no_savings",
        "estimation_failed",
        "invariant_failed",
        "target_reached",
        "minimum_history_reached",
    }
)
MAX_POLICY_REVISION = 2_147_483_647


def _bounded_revision(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        revision = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return revision if 0 <= revision <= MAX_POLICY_REVISION else 0


def normalize_quality_decision(metrics: Mapping[str, Any] | None) -> dict[str, str | int]:
    """Return allowlisted metadata without carrying arbitrary request content."""
    source = metrics or {}
    raw_profile = source.get("quality_profile")
    raw_reason = source.get("compression_reason")
    profile = raw_profile if isinstance(raw_profile, str) else ""
    reason = raw_reason if isinstance(raw_reason, str) else ""
    return {
        "quality_profile": profile if profile in QUALITY_PROFILES else "unavailable",
        "quality_policy_revision": _bounded_revision(source.get("quality_policy_revision")),
        "compression_reason": reason if reason in COMPRESSION_REASONS else "unknown",
    }
