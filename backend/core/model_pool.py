"""Dynamic model catalog and virtual-model routing configuration."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Mapping, Optional, Sequence

from core.governance_coordination import GovernanceGenerationObserver
from core.routing_coordination import GOVERNANCE_SCOPE_MODEL_CATALOG
from core.storage_adapter import get_storage_adapter
from log import log

DEFAULT_VIRTUAL_MODEL_ALIAS = "polaris"
MODEL_POOL_CONFIG_KEY = "virtual_model_pool"
MODEL_CATALOG_TTL_SECONDS = 5 * 60.0
MODEL_CATALOG_STALE_RETRY_SECONDS = 30.0
MAX_POOL_MODELS = 64
MODEL_ROUTING_SCHEMA_VERSION = "model-routing.v1"
_MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


class ModelPoolError(ValueError):
    """A safe model-pool configuration or resolution error."""


@dataclass(frozen=True, order=True)
class ModelCatalogEntry:
    model_id: str
    providers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "providers": list(self.providers),
            "available": bool(self.providers),
        }


@dataclass(frozen=True)
class ModelResolution:
    requested_model: str
    response_model: str
    candidates: tuple[str, ...]
    is_virtual: bool


CatalogLoader = Callable[[], Awaitable[Mapping[str, Iterable[str]]]]


def normalize_model_id(value: Any) -> str:
    model_id = str(value or "").strip()
    if model_id.startswith("models/"):
        model_id = model_id[7:]
    if not model_id or not _MODEL_ID_PATTERN.fullmatch(model_id):
        raise ModelPoolError("Enter a valid provider model ID.")
    return model_id


def _normalize_selected_models(values: Sequence[Any]) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise ModelPoolError("selected_models must be an array.")
    if len(values) > MAX_POOL_MODELS:
        raise ModelPoolError(f"A model pool can contain at most {MAX_POOL_MODELS} models.")

    selected: list[str] = []
    seen = set()
    for value in values:
        model_id = normalize_model_id(value)
        if model_id in seen:
            continue
        seen.add(model_id)
        selected.append(model_id)
    return selected


async def _default_catalog_loader() -> Mapping[str, Iterable[str]]:
    from core.api.primary import fetch_configured_provider_models

    return await fetch_configured_provider_models()


class ModelCatalogService:
    """Cache normalized provider model discovery without losing provenance."""

    def __init__(
        self,
        *,
        loader: Optional[CatalogLoader] = None,
        ttl_seconds: float = MODEL_CATALOG_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._loader = loader or _default_catalog_loader
        self._ttl_seconds = max(0.0, float(ttl_seconds))
        self._clock = clock
        self._lock = asyncio.Lock()
        self._entries: tuple[ModelCatalogEntry, ...] = ()
        self._expires_at = 0.0
        self._loaded = False
        self._last_refresh_error = ""
        self._generation = GovernanceGenerationObserver(GOVERNANCE_SCOPE_MODEL_CATALOG)
        self._refresh_task: Optional[asyncio.Task[None]] = None

    async def get_catalog(self, *, force_refresh: bool = False) -> list[ModelCatalogEntry]:
        await self._generation.synchronize(self.invalidate)
        now = self._clock()
        if not force_refresh and self._loaded and self._expires_at > now:
            return list(self._entries)

        # Once a catalog has been loaded, never make the first request after
        # expiry wait on every provider's model-discovery call. Return the
        # last known catalog and refresh it in the background. Explicit
        # force_refresh callers still wait for that refresh to finish.
        if not force_refresh and self._loaded:
            self._schedule_background_refresh()
            return list(self._entries)

        refresh_task: Optional[asyncio.Task[None]] = None
        async with self._lock:
            now = self._clock()
            if not force_refresh and self._loaded and self._expires_at > now:
                return list(self._entries)

            if force_refresh and self._refresh_task is not None:
                refresh_task = self._refresh_task
            else:
                await self._refresh_locked(now=now)

        if refresh_task is not None:
            await refresh_task
        return list(self._entries)

    def _schedule_background_refresh(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            return

        task = asyncio.create_task(
            self._refresh_in_background(),
            name="model-catalog-refresh",
        )
        self._refresh_task = task

        def clear_task(completed: asyncio.Task[None]) -> None:
            if self._refresh_task is completed:
                self._refresh_task = None

        task.add_done_callback(clear_task)

    async def _refresh_in_background(self) -> None:
        async with self._lock:
            await self._refresh_locked(now=self._clock())

    async def _refresh_locked(self, *, now: float) -> None:
        try:
            provider_models = await self._loader()
        except Exception as exc:
            self._last_refresh_error = str(exc)
            if not self._loaded:
                raise
            self._expires_at = now + min(
                self._ttl_seconds,
                MODEL_CATALOG_STALE_RETRY_SECONDS,
            )
            log.warning(
                f"Provider model discovery failed; serving the last known catalog: {exc}"
            )
            return

        providers_by_model: dict[str, set[str]] = {}
        for provider_id, model_ids in provider_models.items():
            normalized_provider = str(provider_id or "").strip()
            if not normalized_provider:
                continue
            for value in model_ids or ():
                try:
                    model_id = normalize_model_id(value)
                except ModelPoolError:
                    continue
                providers_by_model.setdefault(model_id, set()).add(normalized_provider)

        self._entries = tuple(
            ModelCatalogEntry(model_id, tuple(sorted(providers)))
            for model_id, providers in sorted(providers_by_model.items())
        )
        self._expires_at = now + self._ttl_seconds
        self._loaded = True
        self._last_refresh_error = ""

    async def invalidate(self) -> None:
        refresh_task = self._refresh_task
        if refresh_task is not None and not refresh_task.done():
            refresh_task.cancel()
        self._refresh_task = None
        async with self._lock:
            self._entries = ()
            self._expires_at = 0.0
            self._loaded = False
            self._last_refresh_error = ""

    async def get_diagnostics(self) -> dict[str, Any]:
        """Return cache health without exposing provider credentials or models."""
        async with self._lock:
            return {
                "loaded": self._loaded,
                "entries": len(self._entries),
                "expires_at": self._expires_at,
                "last_refresh_error": self._last_refresh_error,
            }


model_catalog_service = ModelCatalogService()


def _normalize_pool_config(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    try:
        selected_models = _normalize_selected_models(source.get("selected_models") or [])
    except ModelPoolError:
        selected_models = []
    return {
        "alias": DEFAULT_VIRTUAL_MODEL_ALIAS,
        "strategy": "priority_fallback",
        "selected_models": selected_models,
        "enabled": bool(source.get("enabled", True)),
    }


def decorate_virtual_model_pool(pool: Mapping[str, Any]) -> dict[str, Any]:
    """Add an opaque revision and lifecycle state without changing stored data."""
    normalized = _normalize_pool_config(dict(pool))
    revision_source = json.dumps(
        normalized,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        **normalized,
        "configured": bool(normalized["selected_models"]),
        "revision": hashlib.sha256(revision_source).hexdigest()[:24],
    }


def assess_virtual_model_pool(
    selected_models: Sequence[Any],
    catalog: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a bounded, credential-free validation result for one route draft."""
    try:
        selected = _normalize_selected_models(selected_models)
    except ModelPoolError as exc:
        return {
            "valid": False,
            "status": "unavailable",
            "issues": [
                {
                    "code": "invalid_model_selection",
                    "severity": "error",
                    "model_id": "",
                    "message": str(exc),
                }
            ],
            "summary": {
                "selected_models": 0,
                "available_models": 0,
                "unavailable_models": 0,
                "provider_routes": 0,
            },
        }

    by_model = {
        str(entry.get("model_id") or ""): entry
        for entry in catalog
        if isinstance(entry, Mapping) and entry.get("model_id")
    }
    issues: list[dict[str, str]] = []
    available_count = 0
    provider_routes = 0
    unavailable_count = 0
    for model_id in selected:
        entry = by_model.get(model_id)
        if entry is None:
            unavailable_count += 1
            issues.append(
                {
                    "code": "model_not_discovered",
                    "severity": "error",
                    "model_id": model_id,
                    "message": "This model is not in the current provider catalog.",
                }
            )
            continue
        providers = entry.get("routable_providers") or ()
        if bool(entry.get("available")) and providers:
            available_count += 1
            provider_routes += len(providers)
            continue
        unavailable_count += 1
        issues.append(
            {
                "code": "model_temporarily_unavailable",
                "severity": "warning",
                "model_id": model_id,
                "message": "No enabled provider credential can currently route this model.",
            }
        )

    if not selected:
        issues.append(
            {
                "code": "route_has_no_models",
                "severity": "error",
                "model_id": "",
                "message": "Select at least one discovered provider model.",
            }
        )
    elif available_count == 0:
        issues.append(
            {
                "code": "route_has_no_available_model",
                "severity": "error",
                "model_id": "",
                "message": "The route needs at least one model with an available provider.",
            }
        )

    has_error = any(issue["severity"] == "error" for issue in issues)
    if not selected:
        status = "draft"
    elif available_count == 0 or has_error:
        status = "unavailable"
    elif unavailable_count:
        status = "degraded"
    else:
        status = "ready"
    return {
        "valid": bool(selected) and available_count > 0 and not has_error,
        "status": status,
        "issues": issues,
        "summary": {
            "selected_models": len(selected),
            "available_models": available_count,
            "unavailable_models": unavailable_count,
            "provider_routes": provider_routes,
        },
    }


async def get_virtual_model_pool(storage_adapter=None) -> dict[str, Any]:
    storage = storage_adapter or await get_storage_adapter()
    raw = await storage.get_config(MODEL_POOL_CONFIG_KEY, {})
    return decorate_virtual_model_pool(_normalize_pool_config(raw))


async def save_virtual_model_pool(
    selected_models: Sequence[Any],
    *,
    enabled: bool = True,
    storage_adapter=None,
) -> dict[str, Any]:
    storage = storage_adapter or await get_storage_adapter()
    config = {
        "alias": DEFAULT_VIRTUAL_MODEL_ALIAS,
        "strategy": "priority_fallback",
        "selected_models": _normalize_selected_models(selected_models),
        "enabled": bool(enabled),
    }
    if not await storage.set_config(MODEL_POOL_CONFIG_KEY, config):
        raise ModelPoolError("The virtual model configuration could not be saved.")
    return decorate_virtual_model_pool(config)


async def resolve_model_request(
    model_name: Any,
    *,
    storage_adapter=None,
) -> ModelResolution:
    requested_model = normalize_model_id(model_name)
    if requested_model != DEFAULT_VIRTUAL_MODEL_ALIAS:
        return ModelResolution(
            requested_model=requested_model,
            response_model=requested_model,
            candidates=(requested_model,),
            is_virtual=False,
        )

    pool = await get_virtual_model_pool(storage_adapter=storage_adapter)
    if not pool["enabled"] or not pool["selected_models"]:
        raise ModelPoolError(
            f'The virtual model "{DEFAULT_VIRTUAL_MODEL_ALIAS}" has no configured provider models.'
        )

    return ModelResolution(
        requested_model=requested_model,
        response_model=DEFAULT_VIRTUAL_MODEL_ALIAS,
        candidates=tuple(pool["selected_models"]),
        is_virtual=True,
    )


async def get_public_virtual_models(storage_adapter=None) -> list[str]:
    pool = await get_virtual_model_pool(storage_adapter=storage_adapter)
    if pool["enabled"] and pool["selected_models"]:
        return [pool["alias"]]
    return []
