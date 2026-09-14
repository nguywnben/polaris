"""Model pricing table and cost calculation for the usage ledger.

Design notes (distilled from LiteLLM's ``model_prices_and_context_window.json``
and Langfuse's provided-vs-computed cost model):

- Prices are expressed in **USD per 1 million tokens** for readability and are
  converted to per-token values at calculation time.
- Operator overrides use longest-prefix matching. Synced catalog entries use
  provider-qualified exact matching so similarly named vendor models cannot
  inherit an unrelated price.
- Operators can override or extend the table by dropping a
  ``model_pricing.json`` file into the credentials directory; the file is
  merged over the built-in table and hot-reloaded on mtime change.
- Unknown models cost ``0.0`` (unpriced) instead of guessing: the ledger keeps
  an honest record and the aggregate endpoint exposes how many calls were
  unpriced so operators can fix the table.
"""

from __future__ import annotations

import json
import math
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from log import log
from paths import DEFAULT_CREDENTIALS_DIR

PRICING_OVERRIDES_FILENAME = "model_pricing.json"
BUILTIN_PRICING_REVIEWED_AT = "2026-08-21"

# Providers whose inference is local/self-hosted and therefore free.
ZERO_COST_PROVIDERS = frozenset({"ollama"})


@dataclass(frozen=True)
class ModelPricing:
    """USD prices per 1M tokens for a model family."""

    input_per_million: float
    output_per_million: float
    cache_read_per_million: Optional[float] = None
    reasoning_per_million: Optional[float] = None
    cache_creation_per_million: Optional[float] = None

    def effective_cache_read(self) -> float:
        if self.cache_read_per_million is not None:
            return self.cache_read_per_million
        # Never assume an unpublished cache discount in cost or budget estimates.
        return self.input_per_million

    def effective_reasoning(self) -> float:
        if self.reasoning_per_million is not None:
            return self.reasoning_per_million
        # Reasoning/thinking tokens are billed as output by every major vendor.
        return self.output_per_million

    def effective_cache_creation(self) -> float:
        if self.cache_creation_per_million is not None:
            return self.cache_creation_per_million
        # Use normal input pricing when the catalog does not publish a distinct
        # cache-write price; guessing a vendor multiplier would distort billing.
        return self.input_per_million


# Built-in price table (USD per 1M tokens). Longest-prefix match wins.
BUILTIN_MODEL_PRICING: Dict[str, ModelPricing] = {
    # --- Google Gemini ---
    "gemini-3-pro": ModelPricing(2.00, 12.00, 0.50),
    "gemini-3-flash": ModelPricing(0.50, 3.00, 0.125),
    "gemini-2.5-pro": ModelPricing(1.25, 10.00, 0.31),
    "gemini-2.5-flash-lite": ModelPricing(0.10, 0.40, 0.025),
    "gemini-2.5-flash": ModelPricing(0.30, 2.50, 0.075),
    "gemini-2.0-flash-lite": ModelPricing(0.075, 0.30, 0.019),
    "gemini-2.0-flash": ModelPricing(0.10, 0.40, 0.025),
    "gemini-1.5-pro": ModelPricing(1.25, 5.00, 0.3125),
    "gemini-1.5-flash": ModelPricing(0.075, 0.30, 0.019),
    # --- OpenAI ---
    "gpt-5-nano": ModelPricing(0.05, 0.40, 0.005),
    "gpt-5-mini": ModelPricing(0.25, 2.00, 0.025),
    "gpt-5": ModelPricing(1.25, 10.00, 0.125),
    "gpt-4.1-nano": ModelPricing(0.10, 0.40, 0.025),
    "gpt-4.1-mini": ModelPricing(0.40, 1.60, 0.10),
    "gpt-4.1": ModelPricing(2.00, 8.00, 0.50),
    "gpt-4o-mini": ModelPricing(0.15, 0.60, 0.075),
    "gpt-4o": ModelPricing(2.50, 10.00, 1.25),
    "o3-mini": ModelPricing(1.10, 4.40, 0.55),
    "o3": ModelPricing(2.00, 8.00, 0.50),
    "o4-mini": ModelPricing(1.10, 4.40, 0.275),
    "codex-mini": ModelPricing(1.50, 6.00, 0.375),
    # --- Anthropic Claude ---
    "claude-opus-4": ModelPricing(
        15.00,
        75.00,
        cache_read_per_million=1.50,
        cache_creation_per_million=18.75,
    ),
    "claude-sonnet-4": ModelPricing(
        3.00,
        15.00,
        cache_read_per_million=0.30,
        cache_creation_per_million=3.75,
    ),
    "claude-haiku-4": ModelPricing(
        0.80,
        4.00,
        cache_read_per_million=0.08,
        cache_creation_per_million=1.00,
    ),
    "claude-3-7-sonnet": ModelPricing(
        3.00,
        15.00,
        cache_read_per_million=0.30,
        cache_creation_per_million=3.75,
    ),
    "claude-3-5-sonnet": ModelPricing(
        3.00,
        15.00,
        cache_read_per_million=0.30,
        cache_creation_per_million=3.75,
    ),
    "claude-3-5-haiku": ModelPricing(
        0.80,
        4.00,
        cache_read_per_million=0.08,
        cache_creation_per_million=1.00,
    ),
    "claude-3-opus": ModelPricing(
        15.00,
        75.00,
        cache_read_per_million=1.50,
        cache_creation_per_million=18.75,
    ),
    # --- xAI Grok ---
    "grok-4": ModelPricing(3.00, 15.00, 0.75),
    "grok-3-mini": ModelPricing(0.30, 0.50, 0.075),
    "grok-3": ModelPricing(3.00, 15.00, 0.75),
    "grok-code-fast": ModelPricing(0.20, 1.50, 0.02),
    "grok-2": ModelPricing(2.00, 10.00),
}


def _pricing_overrides_path() -> Path:
    credentials_dir = Path(os.getenv("CREDENTIALS_DIR", str(DEFAULT_CREDENTIALS_DIR))).expanduser()
    return credentials_dir / PRICING_OVERRIDES_FILENAME


class _PricingTable:
    """Thread-safe manual, synchronized, and built-in pricing resolver."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._overrides: Dict[str, ModelPricing] = {}
        self._dynamic: Dict[tuple[str, str], ModelPricing] = {}
        self._overrides_mtime: Optional[float] = None
        self._dynamic_fetched_at: Optional[str] = None
        self._dynamic_state = "not_loaded"
        self._dynamic_last_error: Optional[str] = None

    def _load_overrides_locked(self) -> None:
        path = _pricing_overrides_path()
        try:
            mtime = path.stat().st_mtime if path.exists() else None
        except OSError:
            mtime = None

        if mtime == self._overrides_mtime:
            return
        self._overrides_mtime = mtime
        self._overrides = {}
        if mtime is None:
            return

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("pricing overrides must be a JSON object")
            for model_name, entry in raw.items():
                pricing = _parse_override_entry(entry)
                if pricing is not None:
                    self._overrides[_normalize_model_name(model_name)] = pricing
            log.info(f"[pricing] loaded {len(raw)} model pricing overrides from {path.name}")
        except Exception as exc:
            log.error(f"[pricing] failed to load pricing overrides: {exc}")

    @staticmethod
    def _longest_prefix(table: Dict[str, ModelPricing], normalized: str) -> Optional[ModelPricing]:
        best_key = ""
        for key in table:
            if normalized.startswith(key) and len(key) > len(best_key):
                best_key = key
        return table.get(best_key) if best_key else None

    def replace_dynamic(
        self,
        entries: Dict[tuple[str, str], ModelPricing],
        *,
        fetched_at: str,
        state: str = "current",
    ) -> None:
        """Atomically replace the in-memory synchronized catalog."""
        with self._lock:
            self._dynamic = dict(entries)
            self._dynamic_fetched_at = fetched_at
            self._dynamic_state = state if state in {"current", "cached"} else "current"
            self._dynamic_last_error = None

    def mark_dynamic_failure(self, error_code: str) -> None:
        """Record a bounded failure code while retaining the last good snapshot."""
        with self._lock:
            self._dynamic_state = "stale" if self._dynamic else "unavailable"
            self._dynamic_last_error = str(error_code)[:80]

    def lookup(self, model: str, provider: str = "") -> Optional[ModelPricing]:
        normalized = _normalize_model_name(model)
        if not normalized:
            return None
        with self._lock:
            self._load_overrides_locked()
            override = self._longest_prefix(self._overrides, normalized)
            if override is not None:
                return override

            dynamic_provider = _normalize_dynamic_provider(provider)
            if dynamic_provider:
                dynamic = self._dynamic.get((dynamic_provider, normalized))
                if dynamic is not None:
                    return dynamic
            else:
                candidates = {
                    entry
                    for (entry_provider, entry_model), entry in self._dynamic.items()
                    if entry_model == normalized
                }
                if candidates:
                    return ModelPricing(
                        input_per_million=max(entry.input_per_million for entry in candidates),
                        output_per_million=max(entry.output_per_million for entry in candidates),
                        cache_read_per_million=max(
                            entry.effective_cache_read() for entry in candidates
                        ),
                        reasoning_per_million=max(
                            entry.effective_reasoning() for entry in candidates
                        ),
                        cache_creation_per_million=max(
                            entry.effective_cache_creation() for entry in candidates
                        ),
                    )

            return self._longest_prefix(BUILTIN_MODEL_PRICING, normalized)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "dynamic_source": "LiteLLM",
                "dynamic_state": self._dynamic_state,
                "dynamic_fetched_at": self._dynamic_fetched_at,
                "dynamic_model_count": len(self._dynamic),
                "dynamic_last_error": self._dynamic_last_error,
            }


def _parse_override_entry(entry: Any) -> Optional[ModelPricing]:
    if not isinstance(entry, dict):
        return None
    try:
        parsed = ModelPricing(
            input_per_million=float(entry.get("input", 0.0)),
            output_per_million=float(entry.get("output", 0.0)),
            cache_read_per_million=(
                float(entry["cache_read"]) if entry.get("cache_read") is not None else None
            ),
            reasoning_per_million=(
                float(entry["reasoning"]) if entry.get("reasoning") is not None else None
            ),
            cache_creation_per_million=(
                float(entry["cache_creation"]) if entry.get("cache_creation") is not None else None
            ),
        )
        prices = (
            parsed.input_per_million,
            parsed.output_per_million,
            parsed.cache_read_per_million,
            parsed.reasoning_per_million,
            parsed.cache_creation_per_million,
        )
        if any(value is not None and (not math.isfinite(value) or value < 0) for value in prices):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _normalize_model_name(model: Any) -> str:
    name = str(model or "").strip().lower()
    if name.startswith("models/"):
        name = name[len("models/") :]
    # Strip local-model tag suffixes such as ``llama3:8b``.
    if ":" in name:
        name = name.split(":", 1)[0]
    return name


def _normalize_dynamic_provider(provider: Any) -> str:
    normalized = str(provider or "").strip().lower().replace("-", "_")
    if normalized in {
        "google_antigravity",
        "google_ai_studio",
        "gemini",
        "vertex",
        "vertex_ai",
    }:
        return "gemini"
    if normalized in {"openai", "openai_platform", "codex"}:
        return "openai"
    if normalized in {"anthropic", "claude_code", "claude_platform"}:
        return "anthropic"
    if normalized in {"xai", "grok", "xai_console"}:
        return "xai"
    return ""


_pricing_table = _PricingTable()


def find_model_pricing(model: str, provider: str = "") -> Optional[ModelPricing]:
    """Return the pricing entry for ``model`` or ``None`` when unpriced."""
    return _pricing_table.lookup(model, provider=provider)


def get_pricing_table_status() -> Dict[str, Any]:
    """Return path-free freshness metadata for operator-facing status APIs."""
    path = _pricing_overrides_path()
    try:
        modified_at = path.stat().st_mtime if path.exists() else None
    except OSError:
        modified_at = None
    return {
        "built_in_reviewed_at": BUILTIN_PRICING_REVIEWED_AT,
        "override_file_present": modified_at is not None,
        "override_updated_at": (
            datetime.fromtimestamp(modified_at, tz=timezone.utc).isoformat()
            if modified_at is not None
            else None
        ),
        "dynamic_sync_enabled": str(os.getenv("PRICING_SYNC_ENABLED", "true")).strip().lower()
        in {"1", "true", "yes", "on"},
        **_pricing_table.status(),
    }


def calculate_cost_usd(
    model: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_tokens: int = 0,
    cache_creation_tokens: int = 0,
    reasoning_tokens: int = 0,
    provider: str = "",
) -> float:
    """Compute the USD cost of one call from its normalized token counts.

    Token semantics follow ``core.usage_stats.normalize_token_usage``:
    ``cached_tokens`` and ``cache_creation_tokens`` are disjoint subsets of
    ``input_tokens`` and
    ``reasoning_tokens`` is tracked separately from ``output_tokens``.
    Unknown models return ``0.0`` (the ledger records them as unpriced).
    """
    if str(provider or "").strip().lower() in ZERO_COST_PROVIDERS:
        return 0.0

    pricing = find_model_pricing(model, provider=provider)
    if pricing is None:
        return 0.0

    safe_input = max(0, int(input_tokens or 0))
    safe_output = max(0, int(output_tokens or 0))
    safe_cached = min(max(0, int(cached_tokens or 0)), safe_input)
    safe_cache_creation = min(max(0, int(cache_creation_tokens or 0)), safe_input - safe_cached)
    safe_reasoning = max(0, int(reasoning_tokens or 0))
    uncached_input = safe_input - safe_cached - safe_cache_creation

    cost = (
        uncached_input * pricing.input_per_million
        + safe_cached * pricing.effective_cache_read()
        + safe_cache_creation * pricing.effective_cache_creation()
        + safe_output * pricing.output_per_million
        + safe_reasoning * pricing.effective_reasoning()
    ) / 1_000_000.0
    return round(cost, 10)
