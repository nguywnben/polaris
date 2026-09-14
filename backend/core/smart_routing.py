"""Concurrency-aware credential selection for provider requests."""

from __future__ import annotations

import asyncio
import random
import secrets
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional, Set, Tuple

from core.advanced_routing import provider_cost_rank, weighted_order
from core.governance_coordination import GovernanceGenerationObserver
from core.provider_registry import (
    credential_model_support_level,
    get_credential_provider,
    get_credential_provider_variant,
    normalize_provider_id,
)
from core.request_context import get_request_elapsed_ms, get_request_id
from core.request_trace_service import trace_decision
from core.routing_coordination import (
    GOVERNANCE_SCOPE_CREDENTIALS,
    MAX_CREDENTIAL_LEASES,
    CredentialCoordinationSnapshot,
    CredentialLease,
    RouteOutcomeSnapshot,
    RoutingCoordinationAdapter,
)
from core.routing_decision import RouteCandidate, RouteDecision
from core.state_store import InMemoryStateStore
from log import log

CredentialResult = Tuple[str, Dict[str, Any]]
CredentialKey = Tuple[str, str]

VALID_ROUTING_STRATEGIES = frozenset(
    {"balanced", "priority", "weighted", "least_latency", "lowest_cost"}
)
LATENCY_BUCKET_MS = 100.0
MAX_ROUTING_CANDIDATES = 100
DEFAULT_ROUTE_STATE_CACHE_TTL_SECONDS = 0.25
DEFAULT_ROUTE_TRANSIENT_BACKOFF_SECONDS = 2.0
_PROCESS_ROUTING_IDENTIFIER_KEY = secrets.token_bytes(32)


class SmartCredentialRouter:
    """Select healthy credentials while spreading concurrent requests."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        lease_ttl_seconds: float = 15 * 60,
        state_cache_ttl_seconds: float = DEFAULT_ROUTE_STATE_CACHE_TTL_SECONDS,
        base_backoff_seconds: float = DEFAULT_ROUTE_TRANSIENT_BACKOFF_SECONDS,
        max_backoff_seconds: float = 30.0,
        auth_backoff_seconds: float = 300.0,
        model_backoff_seconds: float = 60.0,
        coordination: Optional[RoutingCoordinationAdapter] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self._clock = clock
        self._lease_ttl_seconds = max(1.0, float(lease_ttl_seconds))
        self._state_cache_ttl_seconds = max(0.0, float(state_cache_ttl_seconds))
        self._base_backoff_seconds = max(0.0, float(base_backoff_seconds))
        self._max_backoff_seconds = max(self._base_backoff_seconds, float(max_backoff_seconds))
        self._auth_backoff_seconds = max(self._max_backoff_seconds, float(auth_backoff_seconds))
        self._model_backoff_seconds = max(self._base_backoff_seconds, float(model_backoff_seconds))
        self._state_lock = asyncio.Lock()
        # Distributed CAS is the admission authority. Holding a process-wide
        # mutex across storage I/O serializes every otherwise independent
        # request, so only bound the number of concurrent routing operations.
        self._io_slots = asyncio.Semaphore(MAX_CREDENTIAL_LEASES)
        self._coordination = (
            coordination
            if coordination is not None
            else RoutingCoordinationAdapter(
                InMemoryStateStore(clock=clock),
                identifier_key=_PROCESS_ROUTING_IDENTIFIER_KEY,
                fencing_epoch=1,
            )
        )
        self._active_leases: Dict[CredentialKey, Deque[CredentialLease]] = {}
        self._providers: Dict[CredentialKey, str] = {}
        self._credentials: Dict[CredentialKey, Dict[str, Any]] = {}
        self._state_cache: Dict[str, Tuple[float, Dict[str, Dict[str, Any]]]] = {}
        self._recent_decisions: Deque[RouteDecision] = deque(maxlen=100)
        self._provider_variants: Dict[CredentialKey, str] = {}
        self._credential_generation = GovernanceGenerationObserver(GOVERNANCE_SCOPE_CREDENTIALS)
        self._rng = rng

    async def _invalidate_credential_views(self) -> None:
        self._providers.clear()
        self._provider_variants.clear()
        self._credentials.clear()
        self._state_cache.clear()

    @staticmethod
    def _failure_kind(error_code: Optional[int]) -> str:
        if error_code in {401, 403}:
            return "authentication"
        if error_code == 404:
            return "model_unavailable"
        if error_code == 429:
            return "rate_limited"
        if error_code is not None and 400 <= error_code < 500:
            return "client_request"
        return "transient"

    def _retry_after(
        self,
        *,
        failure_count: int,
        failure_kind: str,
        now: float,
        cooldown_until: Optional[float],
    ) -> float:
        if cooldown_until is not None and cooldown_until > now:
            return cooldown_until
        if failure_kind == "authentication":
            return now + self._auth_backoff_seconds
        if failure_kind == "model_unavailable":
            return now + self._model_backoff_seconds
        backoff = min(
            self._base_backoff_seconds * (2 ** (failure_count - 1)),
            self._max_backoff_seconds,
        )
        return now + backoff

    @staticmethod
    def _latency_rank(samples: tuple[float, ...]) -> int:
        """Bucketed average latency; unknown credentials rank first (0).

        Bucketing (100ms) keeps the sort stable against noise, mirroring the
        buffer approach in LiteLLM's lowest-latency strategy so traffic does
        not permanently pin to one credential.
        """
        if not samples:
            return 0
        return int((sum(samples) / len(samples)) // LATENCY_BUCKET_MS)

    @staticmethod
    def _model_retry_after(state: Dict[str, Any], model_name: Optional[str], now: float) -> float:
        if not model_name:
            return 0.0
        cooldowns = state.get("model_cooldowns") or {}
        cooldown_until = cooldowns.get(model_name)
        if isinstance(cooldown_until, (int, float)) and cooldown_until > now:
            return float(cooldown_until - now)
        return 0.0

    @staticmethod
    def _unavailable_reason(
        decisions: Dict[str, RouteCandidate],
        *,
        has_credentials: bool,
    ) -> tuple[str, float]:
        if not has_credentials:
            return "no_credentials", 0.0
        retry_delays = [
            candidate.retry_after_seconds
            for candidate in decisions.values()
            if candidate.retry_after_seconds > 0
        ]
        if retry_delays:
            return "cooldown_active", min(retry_delays)
        reasons = {candidate.reason for candidate in decisions.values()}
        if reasons == {"disabled"}:
            return "credentials_disabled", 0.0
        if "coordination_capacity" in reasons:
            return "capacity_exhausted", 0.0
        if reasons.intersection(
            {
                "credential_model_blacklist",
                "model_unsupported",
                "preview_incompatible",
                "provider_model_blacklist",
            }
        ):
            return "model_unavailable", 0.0
        return "no_candidate", 0.0

    @staticmethod
    def _preview_penalty(
        state: Dict[str, Any], mode: str, model_name: Optional[str]
    ) -> Optional[int]:
        if mode != "code_assist" or not model_name:
            return 0

        is_preview_credential = bool(state.get("preview", True))
        if "preview" in model_name.lower():
            return 0 if is_preview_credential else None
        return 1 if is_preview_credential else 0

    def _rank_candidates(
        self,
        states: Dict[str, Dict[str, Any]],
        *,
        mode: str,
        model_name: Optional[str],
        routing_strategy: str,
        preferred_provider: Optional[str],
        excluded_provider_models: Set[Tuple[str, str]],
        excluded_credential_models: Set[Tuple[str, str]],
        coordinated_credentials: Dict[str, CredentialCoordinationSnapshot],
        coordinated_outcomes: Dict[str, RouteOutcomeSnapshot],
        now: float,
    ) -> tuple[list[tuple[tuple[Any, ...], str]], Dict[str, RouteCandidate]]:
        candidates = []
        decisions: Dict[str, RouteCandidate] = {}

        for filename, state in states.items():
            key = (mode, filename)
            provider_id = self._providers.get(key, "")
            coordinated = coordinated_credentials[filename]
            outcome = coordinated_outcomes[filename]
            in_flight = coordinated.in_flight
            consecutive_failures = outcome.failure_count

            if state.get("disabled", False):
                decisions[filename] = RouteCandidate(
                    filename,
                    provider_id,
                    "rejected",
                    "disabled",
                    in_flight=in_flight,
                    consecutive_failures=consecutive_failures,
                )
                continue
            model_retry_after = self._model_retry_after(state, model_name, now)
            if model_retry_after > 0:
                decisions[filename] = RouteCandidate(
                    filename,
                    provider_id,
                    "rejected",
                    "model_cooldown",
                    in_flight=in_flight,
                    consecutive_failures=consecutive_failures,
                    retry_after_seconds=model_retry_after,
                )
                continue

            preview_penalty = self._preview_penalty(state, mode, model_name)
            if preview_penalty is None:
                decisions[filename] = RouteCandidate(
                    filename,
                    provider_id,
                    "rejected",
                    "preview_incompatible",
                    in_flight=in_flight,
                    consecutive_failures=consecutive_failures,
                )
                continue

            if model_name and (filename, model_name) in excluded_credential_models:
                decisions[filename] = RouteCandidate(
                    filename,
                    provider_id,
                    "rejected",
                    "credential_model_blacklist",
                    in_flight=in_flight,
                    consecutive_failures=consecutive_failures,
                )
                continue
            if model_name and (provider_id, model_name) in excluded_provider_models:
                decisions[filename] = RouteCandidate(
                    filename,
                    provider_id,
                    "rejected",
                    "provider_model_blacklist",
                    in_flight=in_flight,
                    consecutive_failures=consecutive_failures,
                )
                continue
            provider_penalty = 0
            if routing_strategy == "priority" and preferred_provider:
                provider_penalty = int(self._providers.get(key) != preferred_provider)

            strategy_rank = 0
            if routing_strategy == "least_latency":
                strategy_rank = self._latency_rank(outcome.latency_samples_ms)
            elif routing_strategy == "lowest_cost":
                strategy_rank = provider_cost_rank(self._provider_variants.get(key) or provider_id)

            retry_after = now + outcome.retry_after_seconds
            error_count = len(state.get("error_codes") or [])
            last_selected = max(
                float(state.get("last_success") or 0.0),
                coordinated.last_selected_ms / 1000,
            )

            score = (
                strategy_rank,
                provider_penalty,
                preview_penalty,
                in_flight,
                last_selected,
                max(0, int(state.get("call_count") or 0)),
                consecutive_failures,
                error_count,
                max(0, int(state.get("rotation_order") or 0)),
                filename,
            )
            candidates.append((score, filename, retry_after))
            failure_reason = ""
            if retry_after > now:
                failure_reason = (
                    f"backoff_{outcome.failure_kind}" if outcome.failure_kind else "backoff"
                )
            decisions[filename] = RouteCandidate(
                filename,
                provider_id,
                "eligible" if retry_after <= now else "rejected",
                failure_reason,
                in_flight=in_flight,
                consecutive_failures=consecutive_failures,
                retry_after_seconds=max(0.0, retry_after - now),
            )

        ready = [item for item in candidates if item[2] <= now]
        return sorted((score, filename) for score, filename, _ in ready), decisions

    async def _load_candidate_providers(
        self,
        storage_adapter: Any,
        filenames,
        *,
        mode: str,
    ) -> None:
        """Cache provider identities used by the routing policy."""
        for filename in filenames:
            key = (mode, filename)
            if key in self._providers:
                continue
            credential_data = await storage_adapter.get_credential(filename, mode=mode)
            if credential_data:
                self._credentials[key] = dict(credential_data)
                self._providers[key] = get_credential_provider(credential_data)
                self._provider_variants[key] = get_credential_provider_variant(credential_data)

    async def acquire_with_decision(
        self,
        storage_adapter: Any,
        *,
        mode: str = "primary",
        model_name: Optional[str] = None,
        provider_id: Optional[str] = None,
        routing_strategy: str = "balanced",
        preferred_provider: Optional[str] = None,
        excluded_provider_models: Optional[Set[Tuple[str, str]]] = None,
        excluded_credential_models: Optional[Set[Tuple[str, str]]] = None,
    ) -> tuple[Optional[CredentialResult], RouteDecision]:
        """Reserve the best credential and return its diagnostic decision."""
        async with self._io_slots:
            await self._credential_generation.synchronize(self._invalidate_credential_views)
            now = self._clock()
            cached = self._state_cache.get(mode)
            if cached and cached[0] > now:
                states = cached[1]
            else:
                states = await storage_adapter.get_all_credential_states(mode=mode)
                self._state_cache[mode] = (
                    now + self._state_cache_ttl_seconds,
                    states,
                )
            normalized_strategy = str(routing_strategy or "balanced").strip().lower()
            if normalized_strategy not in VALID_ROUTING_STRATEGIES:
                normalized_strategy = "balanced"
            if len(states) > MAX_ROUTING_CANDIDATES:
                decision = RouteDecision(
                    mode=mode,
                    requested_model=str(model_name or ""),
                    required_provider=str(provider_id or ""),
                    routing_strategy=normalized_strategy,
                    selected_filename=None,
                    selected_provider=None,
                    candidates=(),
                    created_at=now,
                    request_id=get_request_id(),
                    reason="candidate_capacity",
                )
                self._recent_decisions.append(decision)
                trace_decision(
                    category="routing",
                    action="unavailable",
                    result="failed",
                    reason="candidate_capacity",
                    model=str(model_name or ""),
                    candidate_count=len(states),
                )
                log.error(
                    "Credential routing refused a candidate set above the supported capacity."
                )
                return None, decision
            await self._load_candidate_providers(storage_adapter, states, mode=mode)
            normalized_preferred_provider = (
                normalize_provider_id(preferred_provider) if preferred_provider else None
            )
            normalized_exclusions = {
                (normalize_provider_id(excluded_provider), str(excluded_model).strip())
                for excluded_provider, excluded_model in (excluded_provider_models or set())
                if str(excluded_provider or "").strip() and str(excluded_model or "").strip()
            }
            normalized_credential_exclusions = {
                (
                    str(excluded_filename).replace("\\", "/").rsplit("/", 1)[-1],
                    str(excluded_model).strip(),
                )
                for excluded_filename, excluded_model in (excluded_credential_models or set())
                if str(excluded_filename or "").strip() and str(excluded_model or "").strip()
            }
            coordinated_credentials: Dict[str, CredentialCoordinationSnapshot] = {}
            coordinated_outcomes: Dict[str, RouteOutcomeSnapshot] = {}
            for filename in states:
                coordinated_credentials[filename] = await self._coordination.read_credential(
                    mode, filename
                )
                outcome = await self._coordination.read_route_outcome(
                    mode, filename, str(model_name or "")
                )
                if model_name and outcome.retry_after_seconds <= 0:
                    general = await self._coordination.read_route_outcome(mode, filename)
                    if general.retry_after_seconds > 0:
                        outcome = RouteOutcomeSnapshot(
                            general.failure_count,
                            general.failure_kind,
                            general.retry_after_seconds,
                            outcome.latency_samples_ms or general.latency_samples_ms,
                        )
                coordinated_outcomes[filename] = outcome
            ranked, decisions = self._rank_candidates(
                states,
                mode=mode,
                model_name=model_name,
                routing_strategy=normalized_strategy,
                preferred_provider=normalized_preferred_provider,
                excluded_provider_models=normalized_exclusions,
                excluded_credential_models=normalized_credential_exclusions,
                coordinated_credentials=coordinated_credentials,
                coordinated_outcomes=coordinated_outcomes,
                now=now,
            )

            if normalized_strategy == "weighted" and len(ranked) > 1:
                # Weighted-random spread across healthy credentials using the
                # optional per-credential ``weight`` state field (default 1).
                # The selection loop below picks the minimal score, so the
                # weighted draw order is encoded as the score itself.
                weighted_items = [
                    (filename, float(states.get(filename, {}).get("weight") or 1.0))
                    for _, filename in ranked
                ]
                ranked = [
                    ((position,), filename)
                    for position, filename in enumerate(
                        weighted_order(weighted_items, rng=self._rng)
                    )
                ]

            supported_candidates = []
            for score, filename in ranked:
                credential_data = self._credentials.get((mode, filename))
                if not credential_data:
                    candidate = decisions[filename]
                    decisions[filename] = RouteCandidate(
                        filename,
                        candidate.provider_id,
                        "rejected",
                        "credential_missing",
                        in_flight=candidate.in_flight,
                        consecutive_failures=candidate.consecutive_failures,
                    )
                    continue
                support_level = credential_model_support_level(
                    credential_data,
                    model_name,
                    required_provider=provider_id,
                )
                if not support_level:
                    candidate = decisions[filename]
                    decisions[filename] = RouteCandidate(
                        filename,
                        candidate.provider_id,
                        "rejected",
                        "model_unsupported",
                        in_flight=candidate.in_flight,
                        consecutive_failures=candidate.consecutive_failures,
                    )
                    continue

                candidate = decisions[filename]
                decisions[filename] = RouteCandidate(
                    filename,
                    candidate.provider_id,
                    "eligible",
                    support_level=support_level,
                    in_flight=candidate.in_flight,
                    consecutive_failures=candidate.consecutive_failures,
                )

                candidate = ((-support_level, *score), score, filename, dict(credential_data))
                supported_candidates.append(candidate)

            selected = None
            selected_lease = None
            for candidate in sorted(supported_candidates, key=lambda item: item[0]):
                _, _score, filename, _credential_data = candidate
                raw_limit = states.get(filename, {}).get("max_concurrency", MAX_CREDENTIAL_LEASES)
                try:
                    max_concurrency = int(raw_limit)
                except (TypeError, ValueError):
                    max_concurrency = MAX_CREDENTIAL_LEASES
                max_concurrency = min(
                    MAX_CREDENTIAL_LEASES,
                    max(1, max_concurrency),
                )
                lease = await self._coordination.acquire_credential(
                    mode,
                    filename,
                    ttl_seconds=self._lease_ttl_seconds,
                    max_concurrency=max_concurrency,
                )
                if lease is not None:
                    selected = candidate
                    selected_lease = lease
                    break
                prior = decisions[filename]
                decisions[filename] = RouteCandidate(
                    filename,
                    prior.provider_id,
                    "rejected",
                    "coordination_capacity",
                    support_level=prior.support_level,
                    in_flight=max_concurrency,
                    consecutive_failures=prior.consecutive_failures,
                )

            if selected is not None:
                assert selected_lease is not None
                _, score, filename, credential_data = selected

                if mode == "primary":
                    credential_data["enable_credit"] = bool(
                        states.get(filename, {}).get("enable_credit", False)
                    )

                key = (mode, filename)
                self._active_leases.setdefault(key, deque()).append(selected_lease)
                candidate = decisions[filename]
                selected_provider = get_credential_provider(credential_data)
                decisions[filename] = RouteCandidate(
                    filename,
                    selected_provider,
                    "selected",
                    support_level=candidate.support_level,
                    in_flight=selected_lease.in_flight,
                    consecutive_failures=candidate.consecutive_failures,
                )
                decision = RouteDecision(
                    mode=mode,
                    requested_model=str(model_name or ""),
                    required_provider=str(provider_id or ""),
                    routing_strategy=normalized_strategy,
                    selected_filename=filename,
                    selected_provider=selected_provider,
                    candidates=tuple(decisions[name] for name in sorted(decisions)),
                    created_at=now,
                    request_id=get_request_id(),
                    reason="healthy_candidate",
                )
                self._recent_decisions.append(decision)
                trace_decision(
                    category="routing",
                    action="selected",
                    result="succeeded",
                    reason="healthy_candidate",
                    provider=selected_provider,
                    model=str(model_name or ""),
                    candidate_count=len(decision.candidates),
                )
                in_flight_display = score[3] + 1 if len(score) > 5 else "?"
                calls_display = score[5] if len(score) > 5 else "?"
                log.debug(
                    f"Smart routing selected {filename} "
                    f"(mode={mode}, model={model_name or ''}, "
                    f"provider={get_credential_provider(credential_data)}, "
                    f"support={-selected[0][0]}, in_flight={in_flight_display}, "
                    f"calls={calls_display}, strategy={normalized_strategy})."
                )
                return (filename, credential_data), decision

            reason, retry_after_seconds = self._unavailable_reason(
                decisions,
                has_credentials=bool(states),
            )
            decision = RouteDecision(
                mode=mode,
                requested_model=str(model_name or ""),
                required_provider=str(provider_id or ""),
                routing_strategy=normalized_strategy,
                selected_filename=None,
                selected_provider=None,
                candidates=tuple(decisions[name] for name in sorted(decisions)),
                created_at=now,
                request_id=get_request_id(),
                reason=reason,
                retry_after_seconds=retry_after_seconds,
            )
            self._recent_decisions.append(decision)
            trace_decision(
                category="routing",
                action="unavailable",
                result="failed",
                reason=(
                    reason
                    if reason in {"cooldown_active", "model_unavailable", "no_candidate"}
                    else "no_candidate"
                ),
                model=str(model_name or ""),
                candidate_count=len(decision.candidates),
            )
            return None, decision

    async def acquire(
        self,
        storage_adapter: Any,
        *,
        mode: str = "primary",
        model_name: Optional[str] = None,
        provider_id: Optional[str] = None,
        routing_strategy: str = "balanced",
        preferred_provider: Optional[str] = None,
        excluded_provider_models: Optional[Set[Tuple[str, str]]] = None,
        excluded_credential_models: Optional[Set[Tuple[str, str]]] = None,
    ) -> Optional[CredentialResult]:
        """Reserve and return the best currently available credential."""
        result, _ = await self.acquire_with_decision(
            storage_adapter,
            mode=mode,
            model_name=model_name,
            provider_id=provider_id,
            routing_strategy=routing_strategy,
            preferred_provider=preferred_provider,
            excluded_provider_models=excluded_provider_models,
            excluded_credential_models=excluded_credential_models,
        )
        return result

    async def recent_decisions(self, limit: int = 20) -> tuple[RouteDecision, ...]:
        """Return recent sanitized decisions for diagnostics without credential secrets."""
        bounded_limit = min(self._recent_decisions.maxlen or 100, max(0, int(limit)))
        if bounded_limit == 0:
            return ()
        async with self._state_lock:
            return tuple(list(self._recent_decisions)[-bounded_limit:])

    async def complete(
        self,
        filename: str,
        *,
        mode: str = "primary",
        success: bool,
        cooldown_until: Optional[float] = None,
        model_name: Optional[str] = None,
        error_code: Optional[int] = None,
    ) -> None:
        """Release one reservation and update the short-lived health penalty."""
        async with self._io_slots:
            now = self._clock()
            if not success:
                # Failure handling may persist cooldown/disable state immediately;
                # force the next admission to observe that mutation. Successful
                # completions are already represented by coordination state and
                # the bounded cache TTL, so invalidating every success only adds
                # redundant storage reads to the hot path.
                self._state_cache.pop(mode, None)
            key = (mode, filename)
            lease = self._take_active_lease(key)
            if lease is not None:
                await self._coordination.release_credential(lease)

            if success:
                latency = float(get_request_elapsed_ms())
                await self._coordination.record_route_outcome(
                    mode,
                    filename,
                    str(model_name or ""),
                    success=True,
                    failure_kind="",
                    retry_after_seconds=0,
                    latency_ms=latency if latency > 0 else None,
                )
                return

            failure_kind = self._failure_kind(error_code)
            if failure_kind == "client_request":
                return

            previous = await self._coordination.read_route_outcome(
                mode, filename, str(model_name or "")
            )
            failure_count = previous.failure_count + 1
            retry_after = self._retry_after(
                failure_count=failure_count,
                failure_kind=failure_kind,
                now=now,
                cooldown_until=cooldown_until,
            )
            await self._coordination.record_route_outcome(
                mode,
                filename,
                str(model_name or ""),
                success=False,
                failure_kind=failure_kind,
                retry_after_seconds=max(0.0, retry_after - now),
                latency_ms=None,
            )

    def _take_active_lease(self, key: CredentialKey) -> CredentialLease | None:
        leases = self._active_leases.get(key)
        if not leases:
            return None
        lease = leases.popleft()
        if not leases:
            self._active_leases.pop(key, None)
        return lease

    async def release(self, filename: str, *, mode: str = "primary") -> None:
        """Release one reservation without changing credential health."""
        async with self._io_slots:
            self._state_cache.pop(mode, None)
            lease = self._take_active_lease((mode, filename))
            if lease is not None:
                await self._coordination.release_credential(lease)

    async def reset(self) -> None:
        acquired_slots = 0
        try:
            for _ in range(MAX_CREDENTIAL_LEASES):
                await self._io_slots.acquire()
                acquired_slots += 1
            async with self._state_lock:
                leases = [lease for queue in self._active_leases.values() for lease in queue]
                self._active_leases.clear()
                self._providers.clear()
                self._credentials.clear()
                self._state_cache.clear()
                self._recent_decisions.clear()
                self._provider_variants.clear()
            for lease in leases:
                await self._coordination.release_credential(lease)
        finally:
            for _ in range(acquired_slots):
                self._io_slots.release()
