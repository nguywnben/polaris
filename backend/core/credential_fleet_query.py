"""Deterministic, secret-free querying for the credential management fleet."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import threading
import time
from collections import Counter, OrderedDict
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from core.provider_registry import (
    GOOGLE_ANTIGRAVITY,
    credential_supports_operation,
    get_credential_provider,
    get_credential_provider_variant,
    get_declared_credential_models,
)

SELECTION_TOKEN_TTL_SECONDS = 300
MAX_SELECTION_TOKENS = 256


@dataclass(frozen=True)
class CredentialFleetFilters:
    """Canonical filters stored behind an all-matching selection token."""

    provider: str = "all"
    provider_variant: str = "all"
    credential_kind: str = "all"
    health: str = "all"
    cooldown: str = "all"
    quota_state: str = "all"
    tier: str = "all"
    source: str = "all"
    status: str = "all"
    error_code: str = "all"
    preview: str = "all"


@dataclass(frozen=True)
class _SelectionEntry:
    filters: CredentialFleetFilters
    mode: str
    expires_at: float


class CredentialSelectionRegistry:
    """Bounded, process-local storage for opaque all-matching selections."""

    def __init__(
        self,
        *,
        ttl_seconds: int = SELECTION_TOKEN_TTL_SECONDS,
        max_entries: int = MAX_SELECTION_TOKENS,
        clock=time.monotonic,
    ) -> None:
        if ttl_seconds <= 0 or max_entries <= 0:
            raise ValueError("Selection registry limits must be positive.")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, _SelectionEntry] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    def _prune_locked(self, now: float) -> None:
        expired = [token for token, entry in self._entries.items() if entry.expires_at <= now]
        for token in expired:
            self._entries.pop(token, None)
        while len(self._entries) >= self._max_entries:
            self._entries.popitem(last=False)

    def issue(self, filters: CredentialFleetFilters, *, mode: str) -> str:
        now = self._clock()
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._prune_locked(now)
            self._entries[token] = _SelectionEntry(
                filters=filters,
                mode=mode,
                expires_at=now + self._ttl_seconds,
            )
        return token

    def resolve(self, token: str, *, mode: str) -> CredentialFleetFilters:
        now = self._clock()
        with self._lock:
            entry = self._entries.get(str(token or ""))
            if entry is None or entry.expires_at <= now or entry.mode != mode:
                self._entries.pop(str(token or ""), None)
                raise ValueError("Selection token is invalid or expired.")
            self._entries.move_to_end(token)
            return entry.filters


credential_selection_registry = CredentialSelectionRegistry()


async def load_credential_fleet_items(storage_adapter: Any, *, mode: str) -> list[dict[str, Any]]:
    """Load and allowlist the fleet once for filtering or batch selection."""
    backend_info = await storage_adapter.get_backend_info()
    backend_type = backend_info.get("backend_type", "unknown")
    result = await storage_adapter._backend.get_credentials_summary(
        offset=0,
        limit=None,
        status_filter="all",
        mode=mode,
        error_code_filter=None,
        cooldown_filter=None,
        preview_filter=None,
        tier_filter=None,
    )
    credential_read_semaphore = asyncio.Semaphore(20)

    async def load_public_summary(summary: dict[str, Any]) -> dict[str, Any]:
        filename = os.path.basename(str(summary.get("filename") or ""))
        async with credential_read_semaphore:
            credential_data = await storage_adapter.get_credential(filename, mode=mode) or {}
        return enrich_credential_summary(
            summary,
            credential_data,
            backend_type=backend_type,
            mode=mode,
        )

    return list(
        await asyncio.gather(*(load_public_summary(summary) for summary in result.get("items", [])))
    )


def _derive_health(*, disabled: bool, error_codes: list[Any], has_cooldown: bool) -> str:
    if disabled:
        return "disabled"
    normalized_codes = {str(code) for code in error_codes}
    if normalized_codes & {"400", "401", "403"}:
        return "unhealthy"
    if normalized_codes or has_cooldown:
        return "degraded"
    return "healthy"


def _derive_quota_state(
    credential_data: dict[str, Any], *, error_codes: list[Any], has_cooldown: bool
) -> str:
    if not credential_supports_operation(credential_data, "quota"):
        return "unsupported"
    if "429" in {str(code) for code in error_codes}:
        return "exhausted"
    if has_cooldown:
        return "limited"
    return "available"


def enrich_credential_summary(
    summary: dict[str, Any],
    credential_data: dict[str, Any],
    *,
    backend_type: str,
    mode: str,
) -> dict[str, Any]:
    """Project raw storage records into the public allowlisted fleet shape."""
    error_codes = summary.get("error_codes")
    if not isinstance(error_codes, list):
        error_codes = []
    model_cooldowns = summary.get("model_cooldowns")
    if not isinstance(model_cooldowns, dict):
        model_cooldowns = {}
    disabled = bool(summary.get("disabled"))
    has_cooldown = bool(model_cooldowns)
    credential_kind = str(credential_data.get("credential_type") or "oauth").strip().lower()
    if credential_kind not in {"oauth", "api_key", "connection"}:
        credential_kind = "oauth"
    source = "environment" if credential_data.get("source") == "environment" else "managed"
    provider = get_credential_provider(credential_data)
    tier = (
        str(summary.get("tier") or "pro").strip().lower()
        if provider == GOOGLE_ANTIGRAVITY
        else "not_applicable"
    )

    item: dict[str, Any] = {
        "filename": os.path.basename(str(summary.get("filename") or "")),
        "user_email": summary.get("user_email"),
        "credential_label": credential_data.get("credential_label"),
        "credential_type": credential_kind,
        "credential_kind": credential_kind,
        "provider": provider,
        "provider_variant": get_credential_provider_variant(credential_data),
        "model_count": len(get_declared_credential_models(credential_data)),
        "disabled": disabled,
        "error_codes": error_codes,
        "last_success": summary.get("last_success"),
        "backend_type": backend_type,
        "model_cooldowns": model_cooldowns,
        "tier": tier,
        "health": _derive_health(
            disabled=disabled,
            error_codes=error_codes,
            has_cooldown=has_cooldown,
        ),
        "cooldown_state": "in_cooldown" if has_cooldown else "no_cooldown",
        "quota_state": _derive_quota_state(
            credential_data,
            error_codes=error_codes,
            has_cooldown=has_cooldown,
        ),
        "source": source,
    }
    if mode == "code_assist":
        item["preview"] = bool(summary.get("preview", True))
    else:
        item["enable_credit"] = bool(summary.get("enable_credit", False))
    return item


def _matches(item: dict[str, Any], filters: CredentialFleetFilters) -> bool:
    if filters.provider != "all" and item["provider"] != filters.provider:
        return False
    if filters.provider_variant != "all" and item["provider_variant"] != filters.provider_variant:
        return False
    if filters.credential_kind != "all" and item["credential_kind"] != filters.credential_kind:
        return False
    if filters.health != "all" and item["health"] != filters.health:
        return False
    if filters.cooldown != "all" and item["cooldown_state"] != filters.cooldown:
        return False
    if filters.quota_state != "all" and item["quota_state"] != filters.quota_state:
        return False
    if filters.tier != "all" and item["tier"] != filters.tier:
        return False
    if filters.source != "all" and item["source"] != filters.source:
        return False
    if filters.status == "enabled" and item["disabled"]:
        return False
    if filters.status == "disabled" and not item["disabled"]:
        return False
    if filters.error_code == "none" and item["error_codes"]:
        return False
    if filters.error_code not in {"all", "none"} and filters.error_code not in {
        str(code) for code in item["error_codes"]
    }:
        return False
    if filters.preview == "preview" and not item.get("preview", False):
        return False
    if filters.preview == "no_preview" and item.get("preview", False):
        return False
    return True


def _stable_sort_key(item: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(item.get("provider_variant") or ""),
        str(item.get("source") or ""),
        str(item.get("credential_kind") or ""),
        str(item.get("user_email") or "").lower(),
        str(item.get("filename") or "").lower(),
    )


def credential_query_fingerprint(filters: CredentialFleetFilters, *, mode: str) -> str:
    payload = {"schema": 1, "mode": mode, "filters": asdict(filters)}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


def select_credential_filenames(
    items: Iterable[dict[str, Any]], filters: CredentialFleetFilters
) -> list[str]:
    """Resolve normalized filters against fresh fleet data in stable order."""
    matching = sorted(
        (item for item in items if _matches(item, filters)),
        key=_stable_sort_key,
    )
    return [str(item["filename"]) for item in matching]


def _facet_counts(items: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    fields = {
        "provider_variant": "provider_variant",
        "credential_kind": "credential_kind",
        "health": "health",
        "cooldown": "cooldown_state",
        "quota_state": "quota_state",
        "tier": "tier",
        "source": "source",
    }
    counters = {name: Counter() for name in fields}
    for item in items:
        for facet_name, field_name in fields.items():
            counters[facet_name][str(item.get(field_name) or "unknown")] += 1
    return {name: dict(sorted(counter.items())) for name, counter in counters.items()}


def build_credential_fleet_page(
    items: Iterable[dict[str, Any]],
    filters: CredentialFleetFilters,
    *,
    offset: int,
    limit: int,
    mode: str,
    selection_registry: CredentialSelectionRegistry = credential_selection_registry,
) -> dict[str, Any]:
    """Filter first, sort deterministically, then paginate and issue an opaque selection."""
    matching = sorted((item for item in items if _matches(item, filters)), key=_stable_sort_key)
    total = len(matching)
    token = None
    if total:
        token = selection_registry.issue(filters, mode=mode)
    return {
        "items": matching[offset : offset + limit],
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": (offset + limit) < total,
        "stats": {
            "total": total,
            "normal": sum(1 for item in matching if not item["disabled"]),
            "disabled": sum(1 for item in matching if item["disabled"]),
        },
        "facets": _facet_counts(matching),
        "selection": {
            "scope": "all_matching",
            "token": token,
            "matching_count": total,
            "expires_in_seconds": selection_registry.ttl_seconds if token else 0,
            "query_fingerprint": credential_query_fingerprint(filters, mode=mode),
        },
    }
