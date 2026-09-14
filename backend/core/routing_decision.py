"""Sanitized routing decisions shared by execution, diagnostics, and telemetry."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class RouteCandidate:
    """One credential considered during a routing decision."""

    filename: str
    provider_id: str
    state: str
    reason: str = ""
    support_level: int = 0
    in_flight: int = 0
    consecutive_failures: int = 0
    retry_after_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RouteDecision:
    """A secret-free record explaining one credential selection attempt."""

    mode: str
    requested_model: str
    required_provider: str
    routing_strategy: str
    selected_filename: Optional[str]
    selected_provider: Optional[str]
    candidates: tuple[RouteCandidate, ...]
    created_at: float
    request_id: str = ""
    reason: str = "none"
    retry_after_seconds: float = 0.0

    @property
    def selected(self) -> bool:
        return self.selected_filename is not None

    @property
    def message(self) -> str:
        """Return a bounded operator action without exposing credential data."""
        if self.reason == "healthy_candidate":
            return "A healthy credential route was selected."
        if self.reason == "no_credentials":
            return "No provider credentials are configured. Add and enable a provider credential."
        if self.reason == "credentials_disabled":
            return "All provider credentials are disabled. Enable a compatible credential."
        if self.reason == "cooldown_active":
            delay = max(1, math.ceil(self.retry_after_seconds))
            return f"All compatible credentials are temporarily cooling down. Retry in {delay} seconds."
        if self.reason == "capacity_exhausted":
            return (
                "All compatible credentials are busy. Retry after an in-flight request completes."
            )
        if self.reason == "candidate_capacity":
            return "The credential pool exceeds the supported routing capacity. Reduce it to 100 credentials."
        if self.reason == "model_unavailable":
            if self.requested_model:
                return (
                    f"No enabled credential supports model '{self.requested_model}'. "
                    "Verify the model ID or add a compatible provider credential."
                )
            return "No enabled credential supports the requested model. Add a compatible provider credential."
        return "No credential route is currently eligible. Review credential health and routing settings."

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "requested_model": self.requested_model,
            "required_provider": self.required_provider,
            "routing_strategy": self.routing_strategy,
            "selected_filename": self.selected_filename,
            "selected_provider": self.selected_provider,
            "selected": self.selected,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "created_at": self.created_at,
            "request_id": self.request_id,
            "reason": self.reason,
            "retry_after_seconds": self.retry_after_seconds,
            "message": self.message,
        }

    def to_public_dict(self) -> dict[str, Any]:
        """Return bounded routing metadata without credential or request identifiers."""
        candidate_states: dict[str, int] = {}
        candidate_reasons: dict[str, int] = {}
        for candidate in self.candidates:
            candidate_states[candidate.state] = candidate_states.get(candidate.state, 0) + 1
            if candidate.reason:
                candidate_reasons[candidate.reason] = candidate_reasons.get(candidate.reason, 0) + 1
        return {
            "mode": self.mode,
            "requested_model": self.requested_model,
            "required_provider": self.required_provider,
            "routing_strategy": self.routing_strategy,
            "selected": self.selected,
            "selected_provider": self.selected_provider,
            "reason": self.reason,
            "retry_after_seconds": (
                max(1, math.ceil(self.retry_after_seconds)) if self.retry_after_seconds > 0 else 0
            ),
            "message": self.message,
            "candidate_count": len(self.candidates),
            "candidate_states": dict(sorted(candidate_states.items())),
            "candidate_reasons": dict(sorted(candidate_reasons.items())),
            "created_at": self.created_at,
        }
