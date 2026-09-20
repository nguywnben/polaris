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
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from log import log
from paths import DEFAULT_CREDENTIALS_DIR

PRICING_OVERRIDES_FILENAME = "model_pricing.json"
PRICING_ALIASES_FILENAME = "model_pricing_aliases.json"
BUILTIN_PRICING_REVIEWED_AT = "2026-08-21"

# Providers whose inference is local/self-hosted and therefore free.
ZERO_COST_PROVIDERS = frozenset({"ollama"})

# Explicit pricing identities, not inference rewrites. No wildcard suffix removal.
# Gemini API / Antigravity model metadata reviewed 2026-09-20.
MODEL_PRICING_ALIASES = {
    ("google_antigravity", "gemini-3.8-flash-tiered"): ("gemini", "gemini-3.8-flash"),
}


@dataclass(frozen=True)
class PricingResolution:
    pricing: ModelPricing | None
    model: str
    provider: str
    source: str = "unknown"


def _pricing_aliases_path() -> Path:
    return _pricing_overrides_path().with_name(PRICING_ALIASES_FILENAME)


@dataclass(frozen=True)
class ModelPricing:
    """USD prices per 1M tokens for a model family."""

    input_per_million: float
    output_per_million: float
    cache_read_per_million: Optional[float] = None
    reasoning_per_million: Optional[float] = None
    cache_creation_per_million: Optional[float] = None
    supported: bool = True

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
        self._lock = threading.RLock()
        self._overrides: Dict[str, ModelPricing] = {}
        self._dynamic: Dict[tuple[str, str], ModelPricing] = {}
        self._overrides_mtime: Optional[float] = None
        self._dynamic_fetched_at: Optional[str] = None
        self._dynamic_state = "not_loaded"
        self._dynamic_last_error: Optional[str] = None
        self._aliases = dict(MODEL_PRICING_ALIASES)
        self._aliases_mtime: int | None = None

    def _load_aliases_locked(self) -> None:
        path = _pricing_aliases_path()
        try:
            stamp = path.stat().st_mtime_ns if path.exists() else None
            if stamp == self._aliases_mtime:
                return
            aliases = dict(MODEL_PRICING_ALIASES)
            if stamp is not None:
                if path.stat().st_size > 1_048_576:
                    raise ValueError("alias file too large")
                raw = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("alias providers must be an object")
                for provider, models in raw.items():
                    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", provider) or not isinstance(
                        models, dict
                    ):
                        raise ValueError("invalid alias provider")
                    for model, target in models.items():
                        if not isinstance(target, dict) or set(target) != {"provider", "model"}:
                            raise ValueError("invalid alias target")
                        target_provider = str(target["provider"])
                        names = (model, target["model"])
                        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", target_provider) or any(
                            not isinstance(name, str)
                            or not name
                            or len(name) > 256
                            or any(ord(char) < 33 for char in name)
                            for name in names
                        ):
                            raise ValueError("invalid alias identity")
                        aliases[
                            (provider.lower().replace("-", "_"), _normalize_model_name(model))
                        ] = (
                            _normalize_dynamic_provider(target_provider),
                            _normalize_model_name(target["model"]),
                        )
                        if len(aliases) > 4096:
                            raise ValueError("too many pricing aliases")
            self._aliases = aliases
            self._aliases_mtime = stamp
        except (OSError, ValueError, TypeError):
            # Bad operator configuration does not invent prices or interrupt inference.
            self._aliases = dict(MODEL_PRICING_ALIASES)

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
            if (normalized == key or normalized.startswith(key + "-")) and len(key) > len(best_key):
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
        rates = self.resolve(model, provider).pricing
        return rates if rates is not None and rates.supported else None

    def resolve(self, model: str, provider: str = "") -> PricingResolution:
        result = self._resolve(model, provider)
        if result.pricing is not None and not result.pricing.supported:
            return PricingResolution(None, result.model, result.provider, "unsupported")
        return result

    def _resolve(
        self, model: str, provider: str = "", *, follow_aliases: bool = True
    ) -> PricingResolution:
        normalized = _normalize_model_name(model)
        raw_provider = str(provider or "").strip().lower().replace("-", "_")
        dynamic_provider = _normalize_dynamic_provider(provider)
        if not normalized:
            return PricingResolution(None, normalized, dynamic_provider)
        with self._lock:
            self._load_overrides_locked()
            self._load_aliases_locked()
            if not raw_provider:
                # Admission runs before routing selects a provider. Include explicit
                # aliases and scoped overrides in its conservative price envelope.
                providers = {
                    key_provider
                    for key_provider, key_model in (*self._dynamic, *self._aliases)
                    if key_model == normalized
                }
                providers.update(
                    key.split("/", 1)[0]
                    for key in self._overrides
                    if "/" in key and key.split("/", 1)[1] == normalized
                )
                if providers:
                    resolutions = [self._resolve(normalized, name) for name in sorted(providers)]
                    if any(
                        item.pricing is None or not item.pricing.supported for item in resolutions
                    ):
                        return PricingResolution(None, normalized, "", "unsupported")
                    candidates = [item.pricing for item in resolutions]
                    rates = ModelPricing(
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
                    return PricingResolution(rates, normalized, "", resolutions[0].source)
            override = self._overrides.get(f"{raw_provider}/{normalized}") if raw_provider else None
            if override is None:
                override = self._longest_prefix(
                    {key: value for key, value in self._overrides.items() if "/" not in key},
                    normalized,
                )
            if override is not None:
                return PricingResolution(override, normalized, raw_provider, "manual")

            if dynamic_provider:
                dynamic = self._dynamic.get((dynamic_provider, normalized))
                if dynamic is not None:
                    return PricingResolution(dynamic, normalized, dynamic_provider, "litellm")
                alias = self._aliases.get((raw_provider, normalized)) if follow_aliases else None
                if alias is not None:
                    alias_provider, alias_model = alias
                    return self._resolve(alias_model, alias_provider, follow_aliases=False)

            # Built-in retail families must not leak to an unrelated provider.
            family = next(
                (
                    vendor
                    for prefix, vendor in (
                        ("gemini-", "gemini"),
                        ("claude-", "anthropic"),
                        ("grok-", "xai"),
                        ("gpt-", "openai"),
                        ("o3", "openai"),
                        ("o4", "openai"),
                        ("codex-", "openai"),
                    )
                    if normalized.startswith(prefix)
                ),
                "",
            )
            builtin = (
                self._longest_prefix(BUILTIN_MODEL_PRICING, normalized)
                if (not raw_provider or dynamic_provider == family)
                else None
            )
            return PricingResolution(
                builtin, normalized, dynamic_provider, "builtin" if builtin else "unknown"
            )

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "dynamic_source": "LiteLLM",
                "dynamic_state": self._dynamic_state,
                "dynamic_fetched_at": self._dynamic_fetched_at,
                "dynamic_model_count": sum(entry.supported for entry in self._dynamic.values()),
                "dynamic_last_error": self._dynamic_last_error,
            }


def _parse_override_entry(entry: Any) -> Optional[ModelPricing]:
    if not isinstance(entry, dict) or "input" not in entry or "output" not in entry:
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
            supported=entry.get("supported", True),
        )
        if type(parsed.supported) is not bool:
            return None
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
    return normalized


_pricing_table = _PricingTable()


def find_model_pricing(model: str, provider: str = "") -> Optional[ModelPricing]:
    """Return the pricing entry for ``model`` or ``None`` when unpriced."""
    return _pricing_table.lookup(model, provider=provider)


def resolve_model_pricing(model: str, provider: str = "") -> PricingResolution:
    return _pricing_table.resolve(model, provider=provider)


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

    return calculate_priced_cost(
        pricing,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        cache_creation_tokens=cache_creation_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def calculate_priced_cost(
    pricing: ModelPricing,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_tokens: int = 0,
    cache_creation_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> float:
    """Calculate against one resolved snapshot, without reloading operator settings."""
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
