"""Generation-based invalidation for process-local views of durable governance state."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Final

from core.routing_coordination import (
    GOVERNANCE_SCOPE_CONFIG,
    GOVERNANCE_SCOPE_CREDENTIALS,
    GOVERNANCE_SCOPE_MODEL_BLACKLIST,
    GOVERNANCE_SCOPE_MODEL_CATALOG,
    GOVERNANCE_SCOPE_VIRTUAL_KEYS,
    VALID_INVALIDATION_SCOPES,
    RoutingCoordinationAdapter,
)

_CONFIG_SCOPE_BY_KEY: Final = {
    "virtual_keys": GOVERNANCE_SCOPE_VIRTUAL_KEYS,
    "model_route_blacklist": GOVERNANCE_SCOPE_MODEL_BLACKLIST,
}
_governance_coordination: RoutingCoordinationAdapter | None = None
_governance_binding_revision = 0
_local_scope_revisions = {scope: 0 for scope in VALID_INVALIDATION_SCOPES}
_GENERATION_POLL_INTERVAL_SECONDS: Final = 0.1


def configure_governance_coordination(
    coordination: RoutingCoordinationAdapter | None,
) -> None:
    """Select one lifecycle-owned adapter; ``None`` is standalone no-op mode."""

    global _governance_binding_revision, _governance_coordination
    _governance_coordination = coordination
    _governance_binding_revision += 1


def config_invalidation_scope(key: object) -> str:
    return _CONFIG_SCOPE_BY_KEY.get(str(key or ""), GOVERNANCE_SCOPE_CONFIG)


async def publish_governance_invalidation(scope: str) -> int | None:
    if scope not in VALID_INVALIDATION_SCOPES:
        raise ValueError("Invalidation scope is invalid.")
    coordination = _governance_coordination
    if coordination is None:
        return None
    generation = await coordination.invalidate(scope)
    _local_scope_revisions[scope] += 1
    return generation


class GovernanceGenerationObserver:
    """Per-owner generation cursor; one owner cannot consume another owner's invalidation."""

    def __init__(self, scope: str) -> None:
        if scope not in VALID_INVALIDATION_SCOPES:
            raise ValueError("Invalidation scope is invalid.")
        self._scope = scope
        self._observed: int | None = None
        self._binding_revision: int | None = None
        self._local_scope_revision = -1
        self._next_poll_monotonic = 0.0
        self._lock = asyncio.Lock()

    @property
    def observed_generation(self) -> int | None:
        return self._observed

    async def synchronize(
        self,
        invalidate: Callable[[], Awaitable[None]],
        *,
        force: bool = False,
    ) -> bool:
        coordination = _governance_coordination
        if coordination is None:
            return False
        binding_revision = _governance_binding_revision
        local_revision = _local_scope_revisions[self._scope]
        now = time.monotonic()
        if not force and (
            self._observed is not None
            and self._binding_revision == binding_revision
            and self._local_scope_revision == local_revision
            and now < self._next_poll_monotonic
        ):
            return False
        async with self._lock:
            coordination = _governance_coordination
            if coordination is None:
                return False
            binding_revision = _governance_binding_revision
            local_revision = _local_scope_revisions[self._scope]
            now = time.monotonic()
            if not force and (
                self._observed is not None
                and self._binding_revision == binding_revision
                and self._local_scope_revision == local_revision
                and now < self._next_poll_monotonic
            ):
                return False
            generation = await coordination.current_generation(self._scope)
            if self._observed == generation and self._binding_revision == binding_revision:
                self._local_scope_revision = local_revision
                self._next_poll_monotonic = time.monotonic() + _GENERATION_POLL_INTERVAL_SECONDS
                return False
            await invalidate()
            self._observed = generation
            self._binding_revision = binding_revision
            self._local_scope_revision = local_revision
            self._next_poll_monotonic = time.monotonic() + _GENERATION_POLL_INTERVAL_SECONDS
            return True


def credential_invalidation_scopes() -> tuple[str, str]:
    return GOVERNANCE_SCOPE_CREDENTIALS, GOVERNANCE_SCOPE_MODEL_CATALOG
