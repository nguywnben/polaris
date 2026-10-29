"""Shared primitives for the canonical smart-routing policy."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Cost rank per provider: lower ranks are cheaper and preferred by the
# ``lowest_cost`` routing strategy. OAuth/local quota-based providers rank
# before metered pay-per-token API platforms.
PROVIDER_COST_RANKS: Dict[str, int] = {
    "ollama": 0,
    "google_antigravity": 1,
    "openai": 1,  # Codex/ChatGPT OAuth (subscription quota)
    "anthropic": 1,  # Claude Code OAuth (subscription quota)
    "xai": 1,  # Grok Build OAuth (subscription quota)
    "google_ai_studio": 2,  # free-tier API key with limits
    "code_assist": 2,
    "openai_platform": 3,
    "claude_platform": 3,
    "xai_console": 3,
}
DEFAULT_COST_RANK = 2


def provider_cost_rank(provider_id: Any) -> int:
    """Return the cost tier for a provider (lower = cheaper = preferred)."""
    return PROVIDER_COST_RANKS.get(str(provider_id or "").strip().lower(), DEFAULT_COST_RANK)


def model_cost_rank(provider_id: Any, model_name: Optional[str] = None) -> float:
    """Return a composite cost rank combining provider billing tier and per-token pricing."""
    normalized_provider = str(provider_id or "").strip().lower()
    tier = float(provider_cost_rank(normalized_provider))
    if not model_name or tier == 0.0:
        return tier
    try:
        from core.pricing import find_model_pricing

        rates = find_model_pricing(str(model_name), provider=normalized_provider)
        if rates is not None:
            blended = max(0.0, float(rates.input_per_million) + float(rates.output_per_million))
            if blended > 0:
                return tier + min(0.999999, blended / 100_000.0)
    except Exception:
        pass
    return tier


def weighted_order(
    items: Sequence[Tuple[Any, float]],
    *,
    rng: Optional[random.Random] = None,
) -> List[Any]:
    """Return items in weighted-random order (sampling without replacement).

    ``items`` are ``(value, weight)`` pairs; non-positive weights are clamped
    to a tiny epsilon so every candidate keeps a nonzero chance.
    """
    generator = rng or random
    remaining = [(value, max(1e-6, float(weight))) for value, weight in items]
    ordered: List[Any] = []
    while remaining:
        total = sum(weight for _, weight in remaining)
        pick = generator.uniform(0, total)
        cursor = 0.0
        for index, (value, weight) in enumerate(remaining):
            cursor += weight
            if cursor >= pick:
                ordered.append(value)
                remaining.pop(index)
                break
        else:
            ordered.append(remaining.pop()[0])
    return ordered
