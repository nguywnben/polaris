"""Bounded, non-blocking synchronization of the public LiteLLM price catalog."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.httpx_client import http_client
from core.pricing import ModelPricing, _parse_override_entry, _pricing_table, _PricingTable
from log import log
from paths import DEFAULT_CREDENTIALS_DIR

PRICING_CATALOG_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)
PRICING_CACHE_FILENAME = "dynamic_model_pricing.json"
PRICING_CACHE_SCHEMA_VERSION = 1
MAX_CATALOG_BYTES = 16 * 1024 * 1024
MAX_CATALOG_ENTRIES = 25_000
MIN_REMOTE_CATALOG_ENTRIES = 100
MAX_MODEL_KEY_LENGTH = 512
MAX_USD_PER_MILLION = 1_000_000.0
CATALOG_TIMEOUT_SECONDS = 15.0
FAILED_SYNC_RETRY_SECONDS = 3600
SUPPORTED_MODES = frozenset({"chat", "completion", "responses"})


def _cache_path() -> Path:
    credentials_dir = Path(os.getenv("CREDENTIALS_DIR", str(DEFAULT_CREDENTIALS_DIR))).expanduser()
    return credentials_dir / PRICING_CACHE_FILENAME


def _canonical_provider(value: Any) -> str:
    provider = str(value or "").strip().lower().replace("-", "_")
    if provider in {"gemini", "google", "vertex_ai", "vertex"}:
        return "gemini"
    if provider in {"openai", "anthropic", "xai"}:
        return provider
    return provider if re.fullmatch(r"[a-z0-9_]{1,64}", provider) else ""


def _canonical_model(catalog_key: Any, provider: str) -> str:
    key = str(catalog_key or "").strip().lower()
    if not key or len(key) > MAX_MODEL_KEY_LENGTH:
        return ""
    for prefix in (
        f"{provider}/",
        "google/" if provider == "gemini" else "",
        "vertex_ai/" if provider == "gemini" else "",
    ):
        if prefix and key.startswith(prefix):
            key = key[len(prefix) :]
            break
    if key.startswith("models/"):
        key = key[len("models/") :]
    return key if key and not any(ord(char) < 33 for char in key) else ""


def _price_per_million(entry: dict[str, Any], field: str) -> float | None:
    value = entry.get(field)
    if value is None:
        return None
    try:
        parsed = float(value) * 1_000_000.0
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0 or parsed > MAX_USD_PER_MILLION:
        return None
    return parsed


def _pricing_within_bounds(pricing: ModelPricing | None) -> bool:
    if pricing is None:
        return False
    return all(
        value is None or value <= MAX_USD_PER_MILLION
        for value in (
            pricing.input_per_million,
            pricing.output_per_million,
            pricing.cache_read_per_million,
            pricing.reasoning_per_million,
            pricing.cache_creation_per_million,
        )
    )


def parse_litellm_catalog(raw: Any) -> dict[tuple[str, str], ModelPricing]:
    """Validate and convert direct-provider text generation prices."""
    if not isinstance(raw, dict):
        raise ValueError("pricing catalog must be a JSON object")
    if len(raw) > MAX_CATALOG_ENTRIES:
        raise ValueError("pricing catalog contains too many entries")

    parsed: dict[tuple[str, str], ModelPricing] = {}
    ambiguous: set[tuple[str, str]] = set()
    for catalog_key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        provider = _canonical_provider(entry.get("litellm_provider"))
        if not provider:
            continue
        mode = str(entry.get("mode") or "chat").strip().lower()
        if mode not in SUPPORTED_MODES:
            continue
        model = _canonical_model(catalog_key, provider)
        if not model:
            continue
        input_price = _price_per_million(entry, "input_cost_per_token")
        output_price = _price_per_million(entry, "output_cost_per_token")
        if input_price is None or output_price is None:
            continue
        cache_price = _price_per_million(entry, "cache_read_input_token_cost")
        cache_creation_price = _price_per_million(entry, "cache_creation_input_token_cost")
        qualified_model = (provider, model)
        model_pricing = ModelPricing(
            input_per_million=input_price,
            output_per_million=output_price,
            cache_read_per_million=cache_price,
            reasoning_per_million=output_price,
            cache_creation_per_million=cache_creation_price,
            # Keep an explicit barrier rather than falling back to a flat builtin.
            # These require measurements/rate selection not yet in our token ledger.
            supported=not any(("above_" in key or "tiered_pricing" == key) for key in entry),
        )
        if qualified_model in ambiguous:
            continue
        existing = parsed.get(qualified_model)
        if existing is not None and existing != model_pricing:
            parsed.pop(qualified_model, None)
            ambiguous.add(qualified_model)
            continue
        parsed[qualified_model] = model_pricing
    return parsed


class DynamicPricingService:
    """Own the persisted snapshot and install only complete, valid replacements."""

    def __init__(self, *, table: _PricingTable, cache_path: Path) -> None:
        self._table = table
        self._cache_path = cache_path

    def load_cache(self) -> bool:
        try:
            if not self._cache_path.exists():
                return False
            if self._cache_path.stat().st_size > MAX_CATALOG_BYTES:
                raise ValueError("cache_too_large")
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
            entries, fetched_at = self._parse_cache(payload)
            self._table.replace_dynamic(entries, fetched_at=fetched_at, state="cached")
            log.info(f"[pricing] loaded {len(entries)} synchronized model prices from cache")
            return True
        except Exception as exc:
            self.mark_refresh_failed("invalid_cache")
            log.warning(
                f"[pricing] ignored invalid synchronized price cache ({type(exc).__name__})"
            )
            return False

    def _parse_cache(self, payload: Any) -> tuple[dict[tuple[str, str], ModelPricing], str]:
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != PRICING_CACHE_SCHEMA_VERSION
        ):
            raise ValueError("unsupported_cache_schema")
        fetched_at = str(payload.get("fetched_at") or "")
        timestamp = datetime.fromisoformat(fetched_at)
        if timestamp.tzinfo is None:
            raise ValueError("cache_timestamp_requires_timezone")
        models = payload.get("models")
        if not isinstance(models, dict) or len(models) > MAX_CATALOG_ENTRIES:
            raise ValueError("invalid_cache_models")
        entries: dict[tuple[str, str], ModelPricing] = {}
        for item in models.values():
            if not isinstance(item, dict):
                continue
            provider = _canonical_provider(item.get("provider"))
            model = _canonical_model(item.get("model"), provider)
            model_pricing = _parse_override_entry(item)
            if (
                provider
                and model
                and model_pricing is not None
                and _pricing_within_bounds(model_pricing)
            ):
                entries[(provider, model)] = model_pricing
        if not entries:
            raise ValueError("empty_cache")
        return entries, timestamp.astimezone(timezone.utc).isoformat()

    def mark_refresh_failed(self, error_code: str) -> None:
        self._table.mark_dynamic_failure(error_code)

    async def refresh(self) -> bool:
        try:
            raw = await self._download_catalog()
            entries = parse_litellm_catalog(raw)
            if len(entries) < MIN_REMOTE_CATALOG_ENTRIES:
                raise ValueError("remote_catalog_incomplete")
            fetched_at = datetime.now(timezone.utc).isoformat()
            self._write_cache(entries, fetched_at=fetched_at)
            self._table.replace_dynamic(entries, fetched_at=fetched_at)
            log.info(f"[pricing] synchronized {len(entries)} direct-provider model prices")
            return True
        except Exception as exc:
            error_code = self._error_code(exc)
            self.mark_refresh_failed(error_code)
            log.warning(f"[pricing] catalog synchronization failed ({error_code})")
            return False

    async def _download_catalog(self) -> Any:
        headers = {
            "Accept": "application/json",
            "User-Agent": "Polaris pricing-sync",
        }
        content = bytearray()
        async with http_client.get_streaming_client(timeout=CATALOG_TIMEOUT_SECONDS) as client:
            async with client.stream("GET", PRICING_CATALOG_URL, headers=headers) as response:
                response.raise_for_status()
                declared_length = response.headers.get("content-length")
                if declared_length:
                    try:
                        declared_bytes = int(declared_length)
                    except ValueError:
                        declared_bytes = 0
                    if declared_bytes > MAX_CATALOG_BYTES:
                        raise ValueError("remote_catalog_too_large")
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    content.extend(chunk)
                    if len(content) > MAX_CATALOG_BYTES:
                        raise ValueError("remote_catalog_too_large")
        return json.loads(content)

    def _write_cache(
        self,
        entries: dict[tuple[str, str], ModelPricing],
        *,
        fetched_at: str,
    ) -> None:
        models: dict[str, dict[str, Any]] = {}
        for (provider, model), price in sorted(entries.items()):
            models[f"{provider}/{model}"] = {
                "provider": provider,
                "model": model,
                "input": price.input_per_million,
                "output": price.output_per_million,
                "cache_read": price.cache_read_per_million,
                "reasoning": price.reasoning_per_million,
                "cache_creation": price.cache_creation_per_million,
                "supported": price.supported,
            }
        payload = {
            "schema_version": PRICING_CACHE_SCHEMA_VERSION,
            "fetched_at": fetched_at,
            "models": models,
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._cache_path.with_suffix(self._cache_path.suffix + ".tmp")
        temporary.write_text(encoded, encoding="utf-8")
        os.replace(temporary, self._cache_path)

    @staticmethod
    def _error_code(exc: Exception) -> str:
        if isinstance(exc, json.JSONDecodeError):
            return "invalid_json"
        if isinstance(exc, ValueError):
            code = str(exc)
            if code in {
                "remote_catalog_incomplete",
                "remote_catalog_too_large",
                "pricing catalog contains too many entries",
                "pricing catalog must be a JSON object",
            }:
                return code[:80]
            return "invalid_catalog"
        return "network_error"


dynamic_pricing_service = DynamicPricingService(table=_pricing_table, cache_path=_cache_path())


def pricing_sync_enabled() -> bool:
    return str(os.getenv("PRICING_SYNC_ENABLED", "true")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def pricing_sync_interval_seconds() -> int:
    try:
        hours = int(str(os.getenv("PRICING_SYNC_INTERVAL_HOURS", "24")).strip())
    except ValueError:
        hours = 24
    return min(168, max(1, hours)) * 3600


async def run_dynamic_pricing_sync_loop() -> None:
    """Refresh immediately and then periodically; never fail the service lifecycle."""
    while True:
        synchronized = await dynamic_pricing_service.refresh()
        delay = pricing_sync_interval_seconds() if synchronized else FAILED_SYNC_RETRY_SECONDS
        await asyncio.sleep(delay)
