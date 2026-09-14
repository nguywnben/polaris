"""Process-local state primitives used by the standalone runtime."""

from __future__ import annotations

import abc
import asyncio
import base64
import hashlib
import heapq
import hmac
import json
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Literal, Optional, Tuple

from core.coordination import (
    ADMISSION_BINDING_KEY,
    ADMISSION_FENCE_KEY,
    MAX_COORDINATION_INTEGER,
    MAX_IDENTIFIER_LENGTH,
    AdmissionFence,
    CasRequest,
    CasResult,
    CasSettlementTarget,
    CasSnapshot,
    CoordinationAdmissionFencedError,
    CoordinationCorruptError,
    CoordinationReconciliationRequiredError,
    CoordinationTime,
    CoordinationUnavailableError,
    Epoch,
    EpochState,
    InvalidationGeneration,
    InvalidationRequest,
    InvalidationResult,
    QuotaCommitRequest,
    QuotaCommitResult,
    QuotaReconciliationResult,
    QuotaReservationDecision,
    QuotaReservationRequest,
    decode_admission_json,
    validate_epoch,
    validate_operation_id,
)
from core.quota_rate_window import RATE_BUCKET_COUNT, QuotaRateWindow
from core.security_coordination import (
    MAX_OIDC_TRANSACTION_TTL_SECONDS,
    MAX_SECURITY_SESSION_TTL_SECONDS,
    MAX_SECURITY_TIMESTAMP,
    MIN_SECURITY_ATTEMPT_WINDOW_SECONDS,
    AttemptClearRequest,
    AttemptClearResult,
    AttemptReservationDecision,
    AttemptReservationRequest,
    OidcTransactionConsumeRequest,
    OidcTransactionConsumeResult,
    OidcTransactionCreateRequest,
    SecurityAttemptCategory,
    SecurityPrincipalType,
    SecuritySessionState,
    SessionIssueRequest,
    SessionListRequest,
    SessionMutationResult,
    SessionPage,
    SessionReconciliationSnapshot,
    SessionResolveRequest,
    SessionResolveResult,
    SessionRevokeRequest,
    SessionRevokeResult,
    SessionRevokeTarget,
    SessionRotateRequest,
    TransactionCreateResult,
)

QUOTA_DAILY_WINDOW_SECONDS = 86_400.0
QUOTA_MONTHLY_WINDOW_SECONDS = 30 * QUOTA_DAILY_WINDOW_SECONDS


@dataclass
class _CommittedQuotaReservation:
    reservation_id: str
    key_id: str
    committed_at: float
    business_committed_at: float
    actual_tokens: int
    actual_cost_usd: float
    durable_cost_recorded: bool
    expires_at: float


@dataclass
class _QuotaLifecycleRecord:
    request: QuotaReservationRequest
    reserve_fingerprint: tuple[object, ...]
    reserve_result: QuotaReservationDecision
    state: Literal["active", "committed", "released", "expired"]
    accepted_at: float
    active_expires_at: float
    retained_until: float
    next_expiry_at: float
    committed: _CommittedQuotaReservation | None = None


@dataclass(frozen=True)
class _CasRecord:
    revision: int
    payload: bytes
    expires_at: float


@dataclass(frozen=True)
class _Replay:
    fingerprint: object
    result: object
    expires_at: float


@dataclass(frozen=True)
class _QuotaReplay:
    key_id: object
    fingerprint: object
    result: object
    expires_at: float


@dataclass(frozen=True)
class _SecurityAttemptRecord:
    count: int
    expires_at: float


@dataclass(frozen=True)
class _OidcTransactionRecord:
    browser_index: str
    payload: bytes
    expires_at: float


@dataclass
class _IndexedExpiryHeap:
    """Exact indexed heap with bounded, non-mutating due-entry preflight."""

    entries: list[tuple[float, str]] = field(default_factory=list)
    positions: Dict[str, int] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.entries)

    def expiry_for(self, identifier: str) -> float | None:
        index = self.positions.get(identifier)
        if index is None:
            return None
        expires_at, indexed_identifier = self.entries[index]
        if indexed_identifier != identifier:
            raise CoordinationCorruptError("Coordination state is invalid.")
        parent = (index - 1) // 2
        left = 2 * index + 1
        right = left + 1
        if (
            (index and self.entries[parent] > self.entries[index])
            or (left < len(self.entries) and self.entries[index] > self.entries[left])
            or (right < len(self.entries) and self.entries[index] > self.entries[right])
        ):
            raise CoordinationCorruptError("Coordination state is invalid.")
        return expires_at

    def _swap(self, left: int, right: int) -> None:
        self.entries[left], self.entries[right] = self.entries[right], self.entries[left]
        self.positions[self.entries[left][1]] = left
        self.positions[self.entries[right][1]] = right

    def _sift_up(self, index: int) -> None:
        while index:
            parent = (index - 1) // 2
            if self.entries[parent] <= self.entries[index]:
                return
            self._swap(parent, index)
            index = parent

    def _sift_down(self, index: int) -> None:
        size = len(self.entries)
        while True:
            left = 2 * index + 1
            if left >= size:
                return
            right = left + 1
            smallest = right if right < size and self.entries[right] < self.entries[left] else left
            if self.entries[index] <= self.entries[smallest]:
                return
            self._swap(index, smallest)
            index = smallest

    def replace(self, identifier: str, expires_at: float) -> None:
        entry = (expires_at, identifier)
        index = self.positions.get(identifier)
        if index is None:
            self.positions[identifier] = len(self.entries)
            self.entries.append(entry)
            self._sift_up(len(self.entries) - 1)
            return
        previous = self.entries[index]
        self.entries[index] = entry
        if entry < previous:
            self._sift_up(index)
        elif entry > previous:
            self._sift_down(index)

    def discard(self, identifier: str) -> None:
        index = self.positions.pop(identifier, None)
        if index is None:
            return
        last = self.entries.pop()
        if index == len(self.entries):
            return
        self.entries[index] = last
        self.positions[last[1]] = index
        parent = (index - 1) // 2
        if index and self.entries[index] < self.entries[parent]:
            self._sift_up(index)
        else:
            self._sift_down(index)

    def plan_due(
        self,
        mapping: Dict[str, Any],
        now: float,
        expiry: Callable[[Any], float],
        maximum: int,
    ) -> list[str]:
        if len(self.entries) != len(self.positions) or len(mapping) != len(self.entries):
            raise CoordinationCorruptError("Coordination state is invalid.")
        if maximum <= 0 or not self.entries or self.entries[0][0] > now:
            return []
        frontier = [(self.entries[0][0], self.entries[0][1], 0)]
        due: list[str] = []
        while frontier and frontier[0][0] <= now and len(due) < maximum:
            expires_at, identifier, index = heapq.heappop(frontier)
            if self.positions.get(identifier) != index:
                raise CoordinationCorruptError("Coordination state is invalid.")
            record = mapping.get(identifier)
            if record is None or expiry(record) != expires_at:
                raise CoordinationCorruptError("Coordination state is invalid.")
            due.append(identifier)
            left = 2 * index + 1
            right = left + 1
            if left < len(self.entries):
                left_entry = self.entries[left]
                heapq.heappush(frontier, (left_entry[0], left_entry[1], left))
            if right < len(self.entries):
                right_entry = self.entries[right]
                heapq.heappush(frontier, (right_entry[0], right_entry[1], right))
        return due


class BaseStateStore(abc.ABC):
    """Abstract interface for cluster state, rate limits, and cooldown tracking."""

    @abc.abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a value by key."""
        pass

    @abc.abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        """Set a value with an optional expiration time in seconds."""
        pass

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a key."""
        pass

    @abc.abstractmethod
    async def increment(
        self, key: str, amount: int = 1, ttl_seconds: Optional[float] = None
    ) -> int:
        """Atomically increment a counter."""
        pass

    @abc.abstractmethod
    async def acquire_lock(self, lock_key: str, ttl_seconds: float = 10.0) -> bool:
        """Acquire a distributed lock."""
        pass

    @abc.abstractmethod
    async def release_lock(self, lock_key: str) -> None:
        """Release a distributed lock."""
        pass

    @abc.abstractmethod
    async def reserve_quota(self, request: QuotaReservationRequest) -> QuotaReservationDecision:
        """Atomically reserve RPM, TPM, and budget capacity."""
        pass

    @abc.abstractmethod
    async def commit_quota(self, request: QuotaCommitRequest) -> QuotaCommitResult:
        """Replace an active estimate with actual completed usage."""
        pass

    @abc.abstractmethod
    async def release_quota(self, reservation_id: str, *, now: float) -> bool:
        """Idempotently release one active reservation."""
        pass

    @abc.abstractmethod
    async def reconcile_quota_state(
        self,
        *,
        epoch: int,
        cursor: str | None,
        limit: int,
        apply: bool,
        operation_id: str | None = None,
    ) -> QuotaReconciliationResult:
        """Validate and migrate one bounded page of ephemeral quota state."""
        pass


class InMemoryStateStore(BaseStateStore):
    """Bounded, deterministic reference implementation of coordination semantics."""

    _MAX_PRUNED_PER_MUTATION = 256
    _DEFAULT_COORDINATION_REPLAY_LIMIT = 100_000
    _DEFAULT_QUOTA_RECORD_LIMIT = 100_000
    _DEFAULT_QUOTA_REPLAY_LIMIT = 100_000
    _DEFAULT_SECURITY_SESSION_LIMIT = 10_000
    _DEFAULT_SECURITY_ATTEMPT_LIMIT = 100_000
    _DEFAULT_OIDC_TRANSACTION_LIMIT = 1_000
    _DEFAULT_SECURITY_REPLAY_LIMIT = 100_000
    _UNKNOWN_QUOTA_KEY = ("unknown-reservation",)

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        _coordination_replay_limit_for_testing: int | None = None,
        _quota_record_limit_for_testing: int | None = None,
        _quota_replay_limit_for_testing: int | None = None,
        _security_session_limit_for_testing: int | None = None,
        _security_attempt_limit_for_testing: int | None = None,
        _oidc_transaction_limit_for_testing: int | None = None,
        _security_replay_limit_for_testing: int | None = None,
    ) -> None:
        self._clock = clock
        self._store: Dict[str, Tuple[Optional[float], Any]] = {}
        self._locks: Dict[str, tuple[float, asyncio.Task[Any]]] = {}
        self._epoch = Epoch(1, EpochState.READY)
        self._epoch_advances: Dict[str, _Replay] = {}
        self._epoch_ready: Dict[str, _Replay] = {}
        self._epoch_advance_expiries: list[tuple[float, str]] = []
        self._epoch_ready_expiries: list[tuple[float, str]] = []
        self._cas: Dict[str, _CasRecord] = {}
        self._cas_replays: Dict[str, _Replay] = {}
        self._cas_expiries: list[tuple[float, str]] = []
        self._cas_replay_expiries: list[tuple[float, str]] = []
        from core.routing_coordination import VALID_INVALIDATION_SCOPES

        self._invalidation_generations: Dict[str, int] = {
            scope: 1 for scope in VALID_INVALIDATION_SCOPES
        }
        self._invalidation_replays: Dict[str, _Replay] = {}
        self._invalidation_replay_expiries: list[tuple[float, str]] = []
        self._quota_records: Dict[str, _QuotaLifecycleRecord] = {}
        self._quota_ids_by_key: Dict[str, set[str]] = {}
        self._quota_rate_windows: Dict[str, QuotaRateWindow] = {}
        self._quota_lifecycle_expiries: Dict[str, list[tuple[float, str]]] = {}
        self._quota_replays: Dict[str, _QuotaReplay] = {}
        self._quota_replay_expiries: Dict[object, list[tuple[float, str]]] = {}
        self._quota_replay_counts: Dict[object, int] = {}
        self._quota_reconciled_epochs: set[int] = set()
        self._quota_reconciliation_replays: Dict[
            str, tuple[tuple[object, ...], QuotaReconciliationResult]
        ] = {}
        self._security_sessions: Dict[str, SecuritySessionState] = {}
        self._security_digest_by_reference: Dict[str, str] = {}
        self._security_digests_by_principal: Dict[str, set[str]] = {}
        self._security_digests_by_principal_type: Dict[SecurityPrincipalType, set[str]] = {}
        self._security_session_expiries = _IndexedExpiryHeap()
        self._security_session_replays: Dict[str, _Replay] = {}
        self._security_session_replay_expiries = _IndexedExpiryHeap()
        self._security_attempts: Dict[
            SecurityAttemptCategory, Dict[str, _SecurityAttemptRecord]
        ] = {category: {} for category in SecurityAttemptCategory}
        self._security_attempt_expiries: Dict[SecurityAttemptCategory, _IndexedExpiryHeap] = {
            category: _IndexedExpiryHeap() for category in SecurityAttemptCategory
        }
        self._security_attempt_replays: Dict[SecurityAttemptCategory, Dict[str, _Replay]] = {
            category: {} for category in SecurityAttemptCategory
        }
        self._security_attempt_replay_expiries: Dict[
            SecurityAttemptCategory, _IndexedExpiryHeap
        ] = {category: _IndexedExpiryHeap() for category in SecurityAttemptCategory}
        self._oidc_transactions: Dict[str, _OidcTransactionRecord] = {}
        self._oidc_transaction_expiries = _IndexedExpiryHeap()
        self._oidc_transaction_replays: Dict[str, _Replay] = {}
        self._oidc_transaction_replay_expiries = _IndexedExpiryHeap()
        self._security_last_clock: float | None = None
        self._coordination_replay_limit = (
            self._DEFAULT_COORDINATION_REPLAY_LIMIT
            if _coordination_replay_limit_for_testing is None
            else _coordination_replay_limit_for_testing
        )
        self._quota_record_limit = (
            self._DEFAULT_QUOTA_RECORD_LIMIT
            if _quota_record_limit_for_testing is None
            else _quota_record_limit_for_testing
        )
        self._quota_replay_limit = (
            self._DEFAULT_QUOTA_REPLAY_LIMIT
            if _quota_replay_limit_for_testing is None
            else _quota_replay_limit_for_testing
        )
        self._security_session_limit = (
            self._DEFAULT_SECURITY_SESSION_LIMIT
            if _security_session_limit_for_testing is None
            else _security_session_limit_for_testing
        )
        self._security_attempt_limit = (
            self._DEFAULT_SECURITY_ATTEMPT_LIMIT
            if _security_attempt_limit_for_testing is None
            else _security_attempt_limit_for_testing
        )
        self._oidc_transaction_limit = (
            self._DEFAULT_OIDC_TRANSACTION_LIMIT
            if _oidc_transaction_limit_for_testing is None
            else _oidc_transaction_limit_for_testing
        )
        self._security_replay_limit = (
            self._DEFAULT_SECURITY_REPLAY_LIMIT
            if _security_replay_limit_for_testing is None
            else _security_replay_limit_for_testing
        )
        self._closed = False
        self._async_lock = asyncio.Lock()

    def _ensure_open_locked(self) -> None:
        if self._closed:
            raise CoordinationUnavailableError("Coordination store is closed.")

    def _prune_heap_locked(
        self, heap: list[tuple[float, str]], mapping: Dict[str, Any], now: float
    ) -> None:
        planned_heap = list(heap)
        due: list[tuple[float, str]] = []
        while planned_heap and planned_heap[0][0] <= now:
            expires_at, identifier = heapq.heappop(planned_heap)
            record = mapping.get(identifier)
            if record is not None and record.expires_at == expires_at:
                due.append((expires_at, identifier))
                if len(due) > self._MAX_PRUNED_PER_MUTATION:
                    raise CoordinationReconciliationRequiredError("Reconciliation is required.")

        heap[:] = planned_heap
        for expires_at, identifier in due:
            record = mapping.get(identifier)
            if record is not None and record.expires_at == expires_at:
                mapping.pop(identifier, None)

    @staticmethod
    def _replace_heap_member_locked(
        heap: list[tuple[float, str]], identifier: str, expires_at: float
    ) -> None:
        heap[:] = [entry for entry in heap if entry[1] != identifier]
        heapq.heapify(heap)
        heapq.heappush(heap, (expires_at, identifier))

    @staticmethod
    def _discard_heap_member_locked(heap: list[tuple[float, str]], identifier: str) -> None:
        heap[:] = [entry for entry in heap if entry[1] != identifier]
        heapq.heapify(heap)

    def _is_ready_locked(self, epoch: int) -> bool:
        return self._epoch.epoch == epoch and self._epoch.state is EpochState.READY

    def _admission_fence_locked(self) -> AdmissionFence | None:
        entry = self._store.get(ADMISSION_FENCE_KEY)
        if entry is None:
            return None
        expiry, value = entry
        fence = AdmissionFence.decode(value)
        binding_expiry, binding_value = self._store.get(ADMISSION_BINDING_KEY, (None, None))
        try:
            binding = decode_admission_json(binding_value)
            if set(binding) != {
                "schema_version",
                "deployment_id",
                "namespace_digest",
                "identifier_key_fingerprint",
                "fencing_epoch",
                "manifest_checksum",
                "activation_record",
                "migration_plan_id",
                "migration_checkpoint_revision",
                "migration_source_revision",
                "migration_target_revision",
                "migration_checkpoint_checksum",
            }:
                raise ValueError
            if type(binding["schema_version"]) is not int or binding["schema_version"] != 2:
                raise ValueError
            namespace_digest = binding["namespace_digest"]
            if (
                not isinstance(namespace_digest, str)
                or len(namespace_digest) != 64
                or any(character not in "0123456789abcdef" for character in namespace_digest)
            ):
                raise ValueError
            binding_epoch = validate_epoch(binding["fencing_epoch"])
        except (KeyError, ValueError, TypeError, RecursionError):
            raise CoordinationCorruptError("Coordination drain binding is invalid.") from None
        if (
            expiry is not None
            or binding_expiry is not None
            or fence.namespace_digest != namespace_digest
            or binding_epoch != self._epoch.epoch
            or not (
                fence.epoch == self._epoch.epoch
                or (fence.epoch == self._epoch.epoch - 1 and fence.reconciliation_complete)
            )
        ):
            raise CoordinationCorruptError("Coordination drain binding is invalid.")
        return fence

    def _require_admission_locked(self) -> None:
        if self._admission_fence_locked() is not None:
            raise CoordinationAdmissionFencedError("Coordination admission is drained.")

    @staticmethod
    def _cas_fingerprint(request: CasRequest) -> tuple[object, ...]:
        return (
            request.key,
            request.expected_revision,
            request.payload,
            request.ttl_seconds,
            request.epoch,
            request.settlement_targets,
            request.settlement,
            request.effective_replay_ttl_seconds,
        )

    @staticmethod
    def _quota_reserve_fingerprint(request: QuotaReservationRequest) -> tuple[object, ...]:
        return (
            request.reservation_id,
            request.key_id,
            request.now,
            request.ttl_seconds,
            request.estimated_tokens,
            request.estimated_cost_usd,
            request.rpm_limit,
            request.tpm_limit,
            request.daily_budget_usd,
            request.monthly_budget_usd,
            request.daily_spend_usd,
            request.monthly_spend_usd,
            request.daily_snapshot_started_at,
            request.monthly_snapshot_started_at,
            request.fencing_epoch,
        )

    @staticmethod
    def _quota_commit_fingerprint(request: QuotaCommitRequest) -> tuple[object, ...]:
        return (
            request.reservation_id,
            request.now,
            request.actual_tokens,
            request.actual_cost_usd,
            request.durable_cost_recorded,
            request.fencing_epoch,
        )

    def _security_now_locked(self) -> float:
        now = self._clock()
        if (
            type(now) not in {int, float}
            or not math.isfinite(now)
            or not 0 <= now <= MAX_SECURITY_TIMESTAMP - MAX_SECURITY_SESSION_TTL_SECONDS
            or (self._security_last_clock is not None and now < self._security_last_clock)
        ):
            raise CoordinationCorruptError("Coordination state is invalid.")
        self._security_last_clock = float(now)
        return self._security_last_clock

    def _security_epoch_denial_locked(self, epoch: int) -> str | None:
        if self._is_ready_locked(epoch):
            return None
        return "reconciling" if self._epoch.state is EpochState.RECONCILING else "stale_epoch"

    def _require_security_epoch_locked(self, epoch: int) -> None:
        if self._security_epoch_denial_locked(epoch) is not None:
            raise CoordinationUnavailableError("Coordination store is not ready.")

    def _validate_security_session_locked(self, digest: str) -> SecuritySessionState:
        session = self._security_sessions.get(digest)
        if session is None:
            raise CoordinationCorruptError("Coordination state is invalid.")
        if (
            session.session_digest != digest
            or self._security_digest_by_reference.get(session.session_reference) != digest
            or digest not in self._security_digests_by_principal.get(session.principal_index, ())
            or digest
            not in self._security_digests_by_principal_type.get(session.principal_type, ())
            or self._security_session_expiries.expiry_for(digest)
            != min(session.idle_expires_at, session.absolute_expires_at)
        ):
            raise CoordinationCorruptError("Coordination state is invalid.")
        return session

    def _validate_security_session_indexes_locked(self) -> None:
        expected_references: Dict[str, str] = {}
        expected_principals: Dict[str, set[str]] = {}
        expected_principal_types: Dict[SecurityPrincipalType, set[str]] = {}
        for digest, session in self._security_sessions.items():
            self._validate_security_session_locked(digest)
            expected_references[session.session_reference] = digest
            expected_principals.setdefault(session.principal_index, set()).add(digest)
            expected_principal_types.setdefault(session.principal_type, set()).add(digest)
        if (
            self._security_digest_by_reference != expected_references
            or self._security_digests_by_principal != expected_principals
            or self._security_digests_by_principal_type != expected_principal_types
        ):
            raise CoordinationCorruptError("Coordination state is invalid.")

    def _validate_oidc_transaction_locked(self, state_index: str) -> _OidcTransactionRecord:
        transaction = self._oidc_transactions.get(state_index)
        if (
            transaction is None
            or self._oidc_transaction_expiries.expiry_for(state_index) != transaction.expires_at
        ):
            raise CoordinationCorruptError("Coordination state is invalid.")
        return transaction

    def _remove_security_session_locked(self, digest: str, *, update_heap: bool = True) -> None:
        session = self._security_sessions.pop(digest)
        self._security_digest_by_reference.pop(session.session_reference, None)
        principal = self._security_digests_by_principal[session.principal_index]
        principal.discard(digest)
        if not principal:
            self._security_digests_by_principal.pop(session.principal_index, None)
        principal_type = self._security_digests_by_principal_type[session.principal_type]
        principal_type.discard(digest)
        if not principal_type:
            self._security_digests_by_principal_type.pop(session.principal_type, None)
        if update_heap:
            self._security_session_expiries.discard(digest)

    def _add_security_session_locked(self, session: SecuritySessionState) -> None:
        digest = session.session_digest
        self._security_sessions[digest] = session
        self._security_digest_by_reference[session.session_reference] = digest
        self._security_digests_by_principal.setdefault(session.principal_index, set()).add(digest)
        self._security_digests_by_principal_type.setdefault(session.principal_type, set()).add(
            digest
        )
        self._security_session_expiries.replace(
            digest,
            min(session.idle_expires_at, session.absolute_expires_at),
        )

    def _cleanup_security_sessions_locked(self, now: float) -> None:
        session_due = self._security_session_expiries.plan_due(
            self._security_sessions,
            now,
            lambda item: min(item.idle_expires_at, item.absolute_expires_at),
            self._MAX_PRUNED_PER_MUTATION + 1,
        )
        if len(session_due) > self._MAX_PRUNED_PER_MUTATION:
            raise CoordinationReconciliationRequiredError("Reconciliation is required.")
        replay_due = self._security_session_replay_expiries.plan_due(
            self._security_session_replays,
            now,
            lambda item: item.expires_at,
            self._MAX_PRUNED_PER_MUTATION + 1 - len(session_due),
        )
        if len(session_due) + len(replay_due) > self._MAX_PRUNED_PER_MUTATION:
            raise CoordinationReconciliationRequiredError("Reconciliation is required.")
        for digest in session_due:
            self._validate_security_session_locked(digest)
        for digest in session_due:
            self._remove_security_session_locked(digest)
        for operation_key in replay_due:
            self._security_session_replays.pop(operation_key, None)
            self._security_session_replay_expiries.discard(operation_key)

    def _cleanup_security_attempts_locked(
        self, category: SecurityAttemptCategory, now: float
    ) -> None:
        records = self._security_attempts[category]
        replays = self._security_attempt_replays[category]
        record_due = self._security_attempt_expiries[category].plan_due(
            records,
            now,
            lambda item: item.expires_at,
            self._MAX_PRUNED_PER_MUTATION + 1,
        )
        if len(record_due) > self._MAX_PRUNED_PER_MUTATION:
            raise CoordinationReconciliationRequiredError("Reconciliation is required.")
        replay_due = self._security_attempt_replay_expiries[category].plan_due(
            replays,
            now,
            lambda item: item.expires_at,
            self._MAX_PRUNED_PER_MUTATION + 1 - len(record_due),
        )
        if len(record_due) + len(replay_due) > self._MAX_PRUNED_PER_MUTATION:
            raise CoordinationReconciliationRequiredError("Reconciliation is required.")
        for client_index in record_due:
            records.pop(client_index, None)
            self._security_attempt_expiries[category].discard(client_index)
        for operation_key in replay_due:
            replays.pop(operation_key, None)
            self._security_attempt_replay_expiries[category].discard(operation_key)

    def _cleanup_oidc_transactions_locked(self, now: float) -> None:
        transaction_due = self._oidc_transaction_expiries.plan_due(
            self._oidc_transactions,
            now,
            lambda item: item.expires_at,
            self._MAX_PRUNED_PER_MUTATION + 1,
        )
        if len(transaction_due) > self._MAX_PRUNED_PER_MUTATION:
            raise CoordinationReconciliationRequiredError("Reconciliation is required.")
        replay_due = self._oidc_transaction_replay_expiries.plan_due(
            self._oidc_transaction_replays,
            now,
            lambda item: item.expires_at,
            self._MAX_PRUNED_PER_MUTATION + 1 - len(transaction_due),
        )
        if len(transaction_due) + len(replay_due) > self._MAX_PRUNED_PER_MUTATION:
            raise CoordinationReconciliationRequiredError("Reconciliation is required.")
        for state_index in transaction_due:
            self._oidc_transactions.pop(state_index, None)
            self._oidc_transaction_expiries.discard(state_index)
        for operation_key in replay_due:
            self._oidc_transaction_replays.pop(operation_key, None)
            self._oidc_transaction_replay_expiries.discard(operation_key)

    def _store_security_replay_locked(
        self,
        mapping: Dict[str, _Replay],
        heap: _IndexedExpiryHeap,
        operation_key: str,
        fingerprint: object,
        result: object,
        expires_at: float,
    ) -> bool:
        if operation_key not in mapping and len(mapping) >= self._security_replay_limit:
            return False
        mapping[operation_key] = _Replay(fingerprint, result, expires_at)
        heap.replace(operation_key, expires_at)
        return True

    @staticmethod
    def _session_issue_fingerprint(request: SessionIssueRequest) -> tuple[object, ...]:
        return (
            request.session_digest,
            request.session_reference,
            request.principal_index,
            request.principal_type,
            request.payload,
            request.idle_ttl_seconds,
            request.absolute_ttl_seconds,
            request.fencing_epoch,
        )

    @staticmethod
    def _session_from_issue(request: SessionIssueRequest, now: float) -> SecuritySessionState:
        return SecuritySessionState(
            request.session_digest,
            request.session_reference,
            request.principal_index,
            request.principal_type,
            request.payload,
            now,
            now,
            now + request.idle_ttl_seconds,
            now + request.absolute_ttl_seconds,
        )

    @staticmethod
    def _same_security_session_evidence(
        current: SecuritySessionState,
        original: SecuritySessionState | None,
    ) -> bool:
        return original is not None and (
            current.session_digest,
            current.session_reference,
            current.principal_index,
            current.principal_type,
            current.payload,
            current.issued_at,
            current.absolute_expires_at,
        ) == (
            original.session_digest,
            original.session_reference,
            original.principal_index,
            original.principal_type,
            original.payload,
            original.issued_at,
            original.absolute_expires_at,
        )

    async def get(self, key: str) -> Optional[Any]:
        async with self._async_lock:
            self._ensure_open_locked()
            expires_at, value = self._store.get(key, (None, None))
            if key not in self._store:
                return None
            if expires_at is not None and self._clock() > expires_at:
                self._store.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        async with self._async_lock:
            self._ensure_open_locked()
            self._store[key] = (
                self._clock() + ttl_seconds if ttl_seconds is not None else None,
                value,
            )

    async def delete(self, key: str) -> None:
        async with self._async_lock:
            self._ensure_open_locked()
            self._store.pop(key, None)

    async def increment(
        self, key: str, amount: int = 1, ttl_seconds: Optional[float] = None
    ) -> int:
        async with self._async_lock:
            self._ensure_open_locked()
            expires_at, value = self._store.get(key, (None, 0))
            current = (
                int(value)
                if (expires_at is None or self._clock() <= expires_at)
                and isinstance(value, (int, str))
                and str(value).isdigit()
                else 0
            )
            new_value = current + amount
            self._store[key] = (
                self._clock() + ttl_seconds if ttl_seconds is not None else None,
                new_value,
            )
            return new_value

    async def acquire_lock(self, lock_key: str, ttl_seconds: float = 10.0) -> bool:
        async with self._async_lock:
            self._ensure_open_locked()
            now = self._clock()
            existing = self._locks.get(lock_key)
            if existing is not None and existing[0] > now:
                return False
            owner = asyncio.current_task()
            if owner is None:
                raise CoordinationUnavailableError("Coordination lock owner is unavailable.")
            self._locks[lock_key] = (now + ttl_seconds, owner)
            return True

    async def release_lock(self, lock_key: str) -> None:
        async with self._async_lock:
            self._ensure_open_locked()
            existing = self._locks.get(lock_key)
            if existing is not None and existing[1] is asyncio.current_task():
                self._locks.pop(lock_key, None)

    async def read_epoch(self) -> Epoch:
        async with self._async_lock:
            self._ensure_open_locked()
            return self._epoch

    async def initialize_epoch(self) -> Epoch:
        async with self._async_lock:
            self._ensure_open_locked()
            return self._epoch

    async def read_coordination_time(self, *, epoch: int) -> CoordinationTime:
        async with self._async_lock:
            self._ensure_open_locked()
            requested_epoch = validate_epoch(epoch)
            if not self._is_ready_locked(requested_epoch):
                raise CoordinationUnavailableError("Coordination epoch is not ready.")
            milliseconds = int(self._clock() * 1000)
            return CoordinationTime(milliseconds)

    async def advance_epoch(self, expected_epoch: int, operation_id: str) -> Epoch:
        async with self._async_lock:
            self._ensure_open_locked()
            expected_epoch = validate_epoch(expected_epoch)
            operation_id = validate_operation_id(operation_id)
            fingerprint = (expected_epoch,)
            now = self._clock()
            replay = self._epoch_advances.get(operation_id)
            if replay is not None and replay.expires_at > now:
                if replay.fingerprint == fingerprint:
                    result = replay.result
                    assert isinstance(result, Epoch)
                    return result
                return self._epoch
            self._prune_heap_locked(self._epoch_advance_expiries, self._epoch_advances, now)
            if self._epoch.epoch == expected_epoch and self._epoch.state is EpochState.READY:
                if len(self._epoch_advances) >= self._coordination_replay_limit:
                    raise CoordinationReconciliationRequiredError("Reconciliation is required.")
                self._epoch = Epoch(expected_epoch + 1, EpochState.RECONCILING)
                # Epoch transitions invalidate every process-local cache authority and every
                # revocable management session before the new epoch can ever become ready.
                from core.routing_coordination import VALID_INVALIDATION_SCOPES

                for scope in VALID_INVALIDATION_SCOPES:
                    self._invalidation_generations[scope] = (
                        self._invalidation_generations.get(scope, 0) + 1
                    )
                self._security_sessions.clear()
                self._security_digest_by_reference.clear()
                self._security_digests_by_principal.clear()
                self._security_digests_by_principal_type.clear()
                self._security_session_expiries = _IndexedExpiryHeap()
                self._security_session_replays.clear()
                self._security_session_replay_expiries = _IndexedExpiryHeap()
                expires_at = now + QUOTA_MONTHLY_WINDOW_SECONDS
                self._epoch_advances[operation_id] = _Replay(fingerprint, self._epoch, expires_at)
                self._replace_heap_member_locked(
                    self._epoch_advance_expiries, operation_id, expires_at
                )
            return self._epoch

    async def mark_epoch_ready(self, epoch: int, operation_id: str) -> Epoch:
        async with self._async_lock:
            self._ensure_open_locked()
            epoch = validate_epoch(epoch)
            operation_id = validate_operation_id(operation_id)
            fingerprint = (epoch,)
            now = self._clock()
            replay = self._epoch_ready.get(operation_id)
            if replay is not None and replay.expires_at > now:
                if replay.fingerprint == fingerprint:
                    result = replay.result
                    assert isinstance(result, Epoch)
                    return result
                return self._epoch
            self._prune_heap_locked(self._epoch_ready_expiries, self._epoch_ready, now)
            if self._epoch.epoch == epoch and self._epoch.state is EpochState.RECONCILING:
                if len(self._epoch_ready) >= self._coordination_replay_limit:
                    raise CoordinationReconciliationRequiredError("Reconciliation is required.")
                self._epoch = Epoch(epoch, EpochState.READY)
                expires_at = now + QUOTA_MONTHLY_WINDOW_SECONDS
                self._epoch_ready[operation_id] = _Replay(fingerprint, self._epoch, expires_at)
                self._replace_heap_member_locked(
                    self._epoch_ready_expiries, operation_id, expires_at
                )
            return self._epoch

    async def compare_and_set(self, request: CasRequest) -> CasResult:
        async with self._async_lock:
            self._ensure_open_locked()
            if not self._is_ready_locked(request.epoch):
                return CasResult(False, None)
            fingerprint = self._cas_fingerprint(request)
            now = self._clock()
            fence = self._admission_fence_locked()
            replay = self._cas_replays.get(request.operation_id)
            if replay is not None and replay.expires_at > now:
                if replay.fingerprint == fingerprint:
                    result = replay.result
                    assert isinstance(result, CasResult)
                    return CasResult(result.applied, result.revision, idempotent=True)
                return CasResult(False, None)
            if request.settlement is not None:
                admission = request.settlement.admission
                proof = self._cas_replays.get(admission.operation_id)
                if (
                    proof is None
                    or proof.expires_at <= now
                    or proof.fingerprint != self._cas_fingerprint(admission)
                    or not isinstance(proof.result, CasResult)
                    or not proof.result.applied
                    or request.settlement.target != CasSettlementTarget.from_request(request)
                ):
                    raise CoordinationAdmissionFencedError(
                        "CAS settlement admission is unavailable."
                    )
            elif fence is not None:
                raise CoordinationAdmissionFencedError("Coordination admission is drained.")
            self._prune_heap_locked(self._cas_replay_expiries, self._cas_replays, now)
            if len(self._cas_replays) >= self._coordination_replay_limit:
                raise CoordinationReconciliationRequiredError("Reconciliation is required.")
            existing = self._cas.get(request.key)
            if existing is not None and existing.expires_at <= now:
                self._cas.pop(request.key, None)
                self._discard_heap_member_locked(self._cas_expiries, request.key)
                existing = None
            revision = 1 if existing is None else existing.revision + 1
            if (existing is None and request.expected_revision != 0) or (
                existing is not None and existing.revision != request.expected_revision
            ):
                result = CasResult(False, None)
                expires_at = now + request.effective_replay_ttl_seconds
                self._cas_replays[request.operation_id] = _Replay(fingerprint, result, expires_at)
                self._replace_heap_member_locked(
                    self._cas_replay_expiries, request.operation_id, expires_at
                )
                return result
            record_expires_at = now + request.ttl_seconds
            replay_expires_at = now + request.effective_replay_ttl_seconds
            result = CasResult(True, revision)
            self._cas[request.key] = _CasRecord(revision, request.payload, record_expires_at)
            self._cas_replays[request.operation_id] = _Replay(
                fingerprint, result, replay_expires_at
            )
            self._replace_heap_member_locked(self._cas_expiries, request.key, record_expires_at)
            self._replace_heap_member_locked(
                self._cas_replay_expiries, request.operation_id, replay_expires_at
            )
            return result

    async def complete_admission_drain(
        self, fence: AdmissionFence, *, epoch: int, operation_id: str
    ) -> None:
        validate_epoch(epoch)
        validate_operation_id(operation_id)
        if type(fence) is not AdmissionFence:
            raise ValueError("Coordination drain is invalid.")
        async with self._async_lock:
            self._ensure_open_locked()
            current = self._admission_fence_locked()
            replay = self._epoch_ready.get(operation_id)
            if (
                not self._is_ready_locked(epoch)
                or fence.epoch != epoch - 1
                or not fence.reconciliation_complete
                or replay is None
                or replay.expires_at <= self._clock()
                or replay.fingerprint != (epoch,)
                or replay.result != self._epoch
                or (current is not None and current != fence)
            ):
                raise CoordinationUnavailableError("Coordination drain transition does not match.")
            self._store.pop(ADMISSION_FENCE_KEY, None)

    async def read_cas(self, key: str, *, epoch: int) -> CasSnapshot:
        async with self._async_lock:
            self._ensure_open_locked()
            if (
                not isinstance(key, str)
                or not 1 <= len(key) <= MAX_IDENTIFIER_LENGTH
                or any(ord(character) < 32 or ord(character) > 126 for character in key)
            ):
                raise ValueError("Coordination key is invalid.")
            requested_epoch = validate_epoch(epoch)
            if not self._is_ready_locked(requested_epoch):
                raise CoordinationUnavailableError("Coordination epoch is not ready.")
            now = self._clock()
            existing = self._cas.get(key)
            if existing is not None and existing.expires_at <= now:
                self._cas.pop(key, None)
                self._discard_heap_member_locked(self._cas_expiries, key)
                existing = None
            if existing is None:
                return CasSnapshot(None, None)
            return CasSnapshot(existing.revision, existing.payload)

    async def invalidate(self, request: InvalidationRequest) -> InvalidationResult:
        async with self._async_lock:
            self._ensure_open_locked()
            self._require_admission_locked()
            if not self._is_ready_locked(request.epoch):
                return InvalidationResult(False, None)
            fingerprint = (request.scope, request.epoch, request.replay_ttl_seconds)
            now = self._clock()
            replay = self._invalidation_replays.get(request.operation_id)
            if replay is not None and replay.expires_at > now:
                if replay.fingerprint == fingerprint:
                    result = replay.result
                    assert isinstance(result, InvalidationResult)
                    return InvalidationResult(result.applied, result.generation, idempotent=True)
                return InvalidationResult(False, None)
            self._prune_heap_locked(
                self._invalidation_replay_expiries, self._invalidation_replays, now
            )
            if len(self._invalidation_replays) >= self._coordination_replay_limit:
                raise CoordinationReconciliationRequiredError("Reconciliation is required.")
            generation = self._invalidation_generations.get(request.scope, 0) + 1
            result = InvalidationResult(True, generation)
            expires_at = now + request.replay_ttl_seconds
            self._invalidation_generations[request.scope] = generation
            self._invalidation_replays[request.operation_id] = _Replay(
                fingerprint, result, expires_at
            )
            self._replace_heap_member_locked(
                self._invalidation_replay_expiries, request.operation_id, expires_at
            )
            return result

    async def read_invalidation_generation(self, scope: str) -> InvalidationGeneration:
        async with self._async_lock:
            self._ensure_open_locked()
            return InvalidationGeneration(self._invalidation_generations.get(scope))

    @staticmethod
    def _quota_evidence_retention_seconds(_request: QuotaReservationRequest) -> float:
        return float(RATE_BUCKET_COUNT)

    @staticmethod
    def _validate_quota_release(
        reservation_id: object,
        now: object,
        fencing_epoch: object,
        operation_id: object,
    ) -> tuple[str, float, int, str | None]:
        for value, label in (
            (reservation_id, "Reservation ID"),
            (operation_id, "Operation ID"),
        ):
            if value is None and label == "Operation ID":
                continue
            if (
                not isinstance(value, str)
                or not 1 <= len(value) <= MAX_IDENTIFIER_LENGTH
                or any(ord(character) < 32 or ord(character) > 126 for character in value)
            ):
                raise ValueError(f"{label} is invalid.")
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(float(now))
            or not 0.0 <= float(now) <= MAX_COORDINATION_INTEGER
        ):
            raise ValueError("Quota time is invalid.")
        if (
            isinstance(fencing_epoch, bool)
            or not isinstance(fencing_epoch, int)
            or not 1 <= fencing_epoch <= MAX_COORDINATION_INTEGER
        ):
            raise ValueError("Epoch is invalid.")
        assert isinstance(reservation_id, str)
        assert operation_id is None or isinstance(operation_id, str)
        return reservation_id, float(now), fencing_epoch, operation_id

    def _remove_quota_record_locked(self, reservation_id: str) -> None:
        record = self._quota_records.pop(reservation_id, None)
        if record is None:
            return
        identifiers = self._quota_ids_by_key.get(record.request.key_id)
        if identifiers is not None:
            identifiers.discard(reservation_id)
            if not identifiers:
                self._quota_ids_by_key.pop(record.request.key_id, None)
                self._quota_rate_windows.pop(record.request.key_id, None)

    def _apply_quota_lifecycle_expiry_locked(
        self, key_id: str, reservation_id: str, expires_at: float, now: float
    ) -> None:
        record = self._quota_records.get(reservation_id)
        if record is None or record.request.key_id != key_id or record.next_expiry_at != expires_at:
            return
        if record.retained_until <= now or expires_at >= record.retained_until:
            self._remove_quota_record_locked(reservation_id)
            return
        if record.state == "active" and expires_at == record.active_expires_at:
            record.state = "expired"
        record.next_expiry_at = record.retained_until
        self._replace_heap_member_locked(
            self._quota_lifecycle_expiries.setdefault(key_id, []),
            reservation_id,
            record.retained_until,
        )

    def _apply_quota_replay_expiry_locked(
        self, key_id: object, replay_key: str, expires_at: float
    ) -> None:
        replay = self._quota_replays.get(replay_key)
        if replay is None or replay.key_id != key_id or replay.expires_at != expires_at:
            return
        self._quota_replays.pop(replay_key, None)
        remaining = self._quota_replay_counts.get(key_id, 0) - 1
        if remaining:
            self._quota_replay_counts[key_id] = remaining
        else:
            self._quota_replay_counts.pop(key_id, None)

    def _remove_empty_quota_expiry_heaps_locked(
        self,
        key_id: object,
        lifecycle_heap: list[tuple[float, str]],
        replay_heap: list[tuple[float, str]],
    ) -> None:
        if isinstance(key_id, str) and not lifecycle_heap:
            self._quota_lifecycle_expiries.pop(key_id, None)
        if not replay_heap:
            self._quota_replay_expiries.pop(key_id, None)

    def _plan_quota_key_prune_locked(
        self, key_id: object, now: float
    ) -> (
        tuple[
            list[tuple[float, str]],
            list[tuple[float, str]],
            list[tuple[float, str]],
            list[tuple[float, str]],
        ]
        | None
    ):
        lifecycle_heap = (
            self._quota_lifecycle_expiries.get(key_id, []) if isinstance(key_id, str) else []
        )
        replay_heap = self._quota_replay_expiries.get(key_id, [])
        planned_lifecycle = list(lifecycle_heap)
        planned_replay = list(replay_heap)
        due_lifecycle: list[tuple[float, str]] = []
        due_replay: list[tuple[float, str]] = []
        seen_lifecycle: set[str] = set()
        seen_replay: set[str] = set()
        work = 0
        while True:
            lifecycle_due = bool(planned_lifecycle and planned_lifecycle[0][0] <= now)
            replay_due = bool(planned_replay and planned_replay[0][0] <= now)
            if not lifecycle_due and not replay_due:
                break
            if lifecycle_due and (
                not replay_due or planned_lifecycle[0][0] <= planned_replay[0][0]
            ):
                expires_at, reservation_id = heapq.heappop(planned_lifecycle)
                record = self._quota_records.get(reservation_id)
                if (
                    reservation_id not in seen_lifecycle
                    and record is not None
                    and record.request.key_id == key_id
                    and record.next_expiry_at == expires_at
                ):
                    seen_lifecycle.add(reservation_id)
                    due_lifecycle.append((expires_at, reservation_id))
                    work += 1
            else:
                expires_at, replay_key = heapq.heappop(planned_replay)
                replay = self._quota_replays.get(replay_key)
                if (
                    replay_key not in seen_replay
                    and replay is not None
                    and replay.key_id == key_id
                    and replay.expires_at == expires_at
                ):
                    seen_replay.add(replay_key)
                    due_replay.append((expires_at, replay_key))
                    work += 1
            if work > self._MAX_PRUNED_PER_MUTATION:
                return None
        return planned_lifecycle, planned_replay, due_lifecycle, due_replay

    def _apply_quota_key_prune_locked(
        self,
        key_id: object,
        now: float,
        plan: tuple[
            list[tuple[float, str]],
            list[tuple[float, str]],
            list[tuple[float, str]],
            list[tuple[float, str]],
        ],
    ) -> None:
        planned_lifecycle, planned_replay, due_lifecycle, due_replay = plan
        lifecycle_heap = (
            self._quota_lifecycle_expiries.get(key_id, []) if isinstance(key_id, str) else []
        )
        replay_heap = self._quota_replay_expiries.get(key_id, [])
        lifecycle_heap[:] = planned_lifecycle
        replay_heap[:] = planned_replay
        for expires_at, reservation_id in due_lifecycle:
            self._apply_quota_lifecycle_expiry_locked(str(key_id), reservation_id, expires_at, now)
        for expires_at, replay_key in due_replay:
            self._apply_quota_replay_expiry_locked(key_id, replay_key, expires_at)
        self._remove_empty_quota_expiry_heaps_locked(key_id, lifecycle_heap, replay_heap)

    def _prune_quota_keys_locked(self, key_ids: list[object], now: float) -> bool:
        seen: set[object] = set()
        plans: list[
            tuple[
                object,
                tuple[
                    list[tuple[float, str]],
                    list[tuple[float, str]],
                    list[tuple[float, str]],
                    list[tuple[float, str]],
                ],
            ]
        ] = []
        for key_id in key_ids:
            if key_id in seen:
                continue
            seen.add(key_id)
            plan = self._plan_quota_key_prune_locked(key_id, now)
            if plan is None:
                return False
            plans.append((key_id, plan))
        for key_id, plan in plans:
            self._apply_quota_key_prune_locked(key_id, now, plan)
        return True

    def _store_quota_replay_locked(
        self,
        replay_key: str,
        key_id: object,
        fingerprint: object,
        result: object,
        expires_at: float,
    ) -> bool:
        if self._quota_replay_counts.get(key_id, 0) >= self._quota_replay_limit:
            return False
        self._quota_replays[replay_key] = _QuotaReplay(key_id, fingerprint, result, expires_at)
        self._quota_replay_counts[key_id] = self._quota_replay_counts.get(key_id, 0) + 1
        self._replace_heap_member_locked(
            self._quota_replay_expiries.setdefault(key_id, []), replay_key, expires_at
        )
        return True

    async def reserve_quota(self, request: QuotaReservationRequest) -> QuotaReservationDecision:
        async with self._async_lock:
            self._ensure_open_locked()
            self._require_admission_locked()
            coordination_now = self._clock()
            if not self._is_ready_locked(request.fencing_epoch):
                reason = (
                    "reconciling" if self._epoch.state is EpochState.RECONCILING else "stale_epoch"
                )
                return QuotaReservationDecision(False, request.reservation_id, reason)
            fingerprint = self._quota_reserve_fingerprint(request)
            replay_key = f"reserve:{request.operation_id or request.reservation_id}"
            record = self._quota_records.get(request.reservation_id)
            replay = self._quota_replays.get(replay_key)
            cleanup_keys = [
                replay.key_id if replay is not None else request.key_id,
                record.request.key_id if record is not None else request.key_id,
                request.key_id,
            ]
            if not self._prune_quota_keys_locked(cleanup_keys, coordination_now):
                return QuotaReservationDecision(
                    False, request.reservation_id, "reconciliation_required"
                )
            replay = self._quota_replays.get(replay_key)
            if replay is not None:
                if replay.fingerprint != fingerprint:
                    return QuotaReservationDecision(False, request.reservation_id, "conflict")
                result = replay.result
                assert isinstance(result, QuotaReservationDecision)
                return QuotaReservationDecision(
                    result.accepted,
                    result.reservation_id,
                    result.reason,
                    result.retry_after_seconds,
                    True,
                )
            record = self._quota_records.get(request.reservation_id)
            if record is not None:
                if record.reserve_fingerprint != fingerprint:
                    return QuotaReservationDecision(False, request.reservation_id, "conflict")
                result = record.reserve_result
                return QuotaReservationDecision(
                    result.accepted,
                    result.reservation_id,
                    result.reason,
                    result.retry_after_seconds,
                    True,
                )
            if self._quota_replay_counts.get(request.key_id, 0) >= self._quota_replay_limit:
                return QuotaReservationDecision(
                    False, request.reservation_id, "reconciliation_required"
                )
            result: QuotaReservationDecision | None = None
            if len(self._quota_ids_by_key.get(request.key_id, ())) >= self._quota_record_limit:
                result = QuotaReservationDecision(False, request.reservation_id, "capacity")
            window = self._quota_rate_windows.get(request.key_id)
            if window is None:
                window = QuotaRateWindow()
            totals = window.totals(coordination_now)
            if (
                result is None
                and request.rpm_limit is not None
                and totals.requests >= request.rpm_limit
            ):
                result = QuotaReservationDecision(
                    False,
                    request.reservation_id,
                    "rpm",
                    window.retry_after_seconds(coordination_now),
                )
            if (
                result is None
                and request.tpm_limit is not None
                and totals.tokens + request.estimated_tokens > request.tpm_limit
            ):
                result = QuotaReservationDecision(
                    False,
                    request.reservation_id,
                    "tpm",
                    window.retry_after_seconds(coordination_now),
                )
            if result is not None:
                if not self._store_quota_replay_locked(
                    replay_key,
                    request.key_id,
                    fingerprint,
                    result,
                    coordination_now + request.ttl_seconds,
                ):
                    return QuotaReservationDecision(
                        False, request.reservation_id, "reconciliation_required"
                    )
                return result

            candidate_window = window.copy()
            candidate_window.reserve(coordination_now, request.estimated_tokens)
            result = QuotaReservationDecision(True, request.reservation_id)
            active_expires_at = coordination_now + request.ttl_seconds
            retained_until = max(
                active_expires_at,
                coordination_now + self._quota_evidence_retention_seconds(request),
            )
            if request.operation_id is not None and not self._store_quota_replay_locked(
                replay_key,
                request.key_id,
                fingerprint,
                result,
                retained_until,
            ):
                return QuotaReservationDecision(
                    False, request.reservation_id, "reconciliation_required"
                )
            lifecycle = _QuotaLifecycleRecord(
                request=request,
                reserve_fingerprint=fingerprint,
                reserve_result=result,
                state="active",
                accepted_at=coordination_now,
                active_expires_at=active_expires_at,
                retained_until=retained_until,
                next_expiry_at=min(active_expires_at, retained_until),
            )
            self._quota_records[request.reservation_id] = lifecycle
            self._quota_ids_by_key.setdefault(request.key_id, set()).add(request.reservation_id)
            self._quota_rate_windows[request.key_id] = candidate_window
            self._replace_heap_member_locked(
                self._quota_lifecycle_expiries.setdefault(request.key_id, []),
                request.reservation_id,
                lifecycle.next_expiry_at,
            )
            return result

    async def commit_quota(self, request: QuotaCommitRequest) -> QuotaCommitResult:
        async with self._async_lock:
            self._ensure_open_locked()
            fence = self._admission_fence_locked()
            coordination_now = self._clock()
            if not self._is_ready_locked(request.fencing_epoch):
                return QuotaCommitResult(False)
            replay_key = f"commit:{request.operation_id or request.reservation_id}"
            fingerprint = self._quota_commit_fingerprint(request)
            record = self._quota_records.get(request.reservation_id)
            replay = self._quota_replays.get(replay_key)
            target_key: object = (
                record.request.key_id if record is not None else self._UNKNOWN_QUOTA_KEY
            )
            cleanup_keys = [replay.key_id if replay is not None else target_key, target_key]
            if not self._prune_quota_keys_locked(cleanup_keys, coordination_now):
                raise CoordinationReconciliationRequiredError("Reconciliation is required.")
            replay = self._quota_replays.get(replay_key)
            if replay is not None:
                if replay.fingerprint != fingerprint:
                    return QuotaCommitResult(False)
                result = replay.result
                assert isinstance(result, QuotaCommitResult)
                return QuotaCommitResult(result.committed, result.overspent, True)
            record = self._quota_records.get(request.reservation_id)
            target_key = record.request.key_id if record is not None else self._UNKNOWN_QUOTA_KEY
            if fence is not None and record is None:
                return QuotaCommitResult(False)
            if self._quota_replay_counts.get(target_key, 0) >= self._quota_replay_limit:
                raise CoordinationReconciliationRequiredError("Reconciliation is required.")
            if record is None or record.state != "active":
                result = QuotaCommitResult(False)
                self._store_quota_replay_locked(
                    replay_key,
                    target_key,
                    fingerprint,
                    result,
                    record.retained_until
                    if record is not None
                    else coordination_now + RATE_BUCKET_COUNT,
                )
                return result
            source = record.request
            tokens = (
                source.estimated_tokens
                if request.actual_tokens is None
                else max(0, int(request.actual_tokens))
            )
            cost = (
                source.estimated_cost_usd
                if request.actual_cost_usd is None
                else max(0.0, float(request.actual_cost_usd))
            )
            window = self._quota_rate_windows.get(source.key_id)
            if window is None:
                raise CoordinationCorruptError("Quota rate state is invalid.")
            candidate_window = window.copy()
            candidate_window.commit(
                record.accepted_at,
                source.estimated_tokens,
                coordination_now,
                tokens,
            )
            totals = candidate_window.totals(coordination_now)
            retained_until = max(
                record.active_expires_at,
                coordination_now + self._quota_evidence_retention_seconds(source),
            )
            committed = _CommittedQuotaReservation(
                request.reservation_id,
                source.key_id,
                coordination_now,
                request.now,
                tokens,
                cost,
                bool(request.durable_cost_recorded),
                retained_until,
            )
            record.state = "committed"
            record.committed = committed
            record.retained_until = retained_until
            record.next_expiry_at = retained_until
            self._quota_rate_windows[source.key_id] = candidate_window
            self._replace_heap_member_locked(
                self._quota_lifecycle_expiries.setdefault(source.key_id, []),
                request.reservation_id,
                record.next_expiry_at,
            )
            overspent = bool(source.tpm_limit is not None and totals.tokens > source.tpm_limit)
            result = QuotaCommitResult(True, overspent)
            self._store_quota_replay_locked(
                replay_key,
                source.key_id,
                fingerprint,
                result,
                record.retained_until,
            )
            return result

    async def release_quota(
        self,
        reservation_id: str,
        *,
        now: float,
        fencing_epoch: int = 1,
        operation_id: str | None = None,
    ) -> bool:
        async with self._async_lock:
            self._ensure_open_locked()
            identifier, now, fencing_epoch, operation_id = self._validate_quota_release(
                reservation_id, now, fencing_epoch, operation_id
            )
            fence = self._admission_fence_locked()
            coordination_now = self._clock()
            if not self._is_ready_locked(fencing_epoch):
                return False
            replay_key = f"release:{operation_id or identifier}"
            fingerprint = (identifier, fencing_epoch)
            record = self._quota_records.get(identifier)
            replay = self._quota_replays.get(replay_key)
            target_key: object = (
                record.request.key_id if record is not None else self._UNKNOWN_QUOTA_KEY
            )
            cleanup_keys = [replay.key_id if replay is not None else target_key, target_key]
            if not self._prune_quota_keys_locked(cleanup_keys, coordination_now):
                raise CoordinationReconciliationRequiredError("Reconciliation is required.")
            replay = self._quota_replays.get(replay_key)
            if replay is not None:
                return False
            record = self._quota_records.get(identifier)
            target_key = record.request.key_id if record is not None else self._UNKNOWN_QUOTA_KEY
            if fence is not None and record is None:
                return False
            if self._quota_replay_counts.get(target_key, 0) >= self._quota_replay_limit:
                raise CoordinationReconciliationRequiredError("Reconciliation is required.")
            result = record is not None and record.state == "active"
            expires_at = (
                record.retained_until
                if record is not None
                else coordination_now + RATE_BUCKET_COUNT
            )
            if result:
                window = self._quota_rate_windows.get(record.request.key_id)
                if window is None:
                    raise CoordinationCorruptError("Quota rate state is invalid.")
                candidate_window = window.copy()
                candidate_window.release(
                    record.accepted_at,
                    record.request.estimated_tokens,
                    coordination_now,
                )
                record.state = "released"
                record.next_expiry_at = record.retained_until
                expires_at = record.retained_until
                self._quota_rate_windows[record.request.key_id] = candidate_window
                self._replace_heap_member_locked(
                    self._quota_lifecycle_expiries.setdefault(record.request.key_id, []),
                    identifier,
                    record.next_expiry_at,
                )
            self._store_quota_replay_locked(
                replay_key,
                target_key,
                fingerprint,
                result,
                expires_at,
            )
            return result

    @staticmethod
    def _quota_reconciliation_cursor(family: str) -> str:
        payload = json.dumps(
            {
                "schema_version": 1,
                "family": family,
                "key_scan": 0,
                "target": None,
                "member_scan": 0,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")

    @staticmethod
    def _decode_quota_reconciliation_cursor(cursor: str | None) -> str:
        if cursor is None:
            return "records"
        if (
            not isinstance(cursor, str)
            or not 1 <= len(cursor) <= 2048
            or any(
                not (character.isascii() and (character.isalnum() or character in "-_"))
                for character in cursor
            )
        ):
            raise ValueError("Quota reconciliation cursor is invalid.")
        try:
            padding = "=" * (-len(cursor) % 4)
            decoded = base64.urlsafe_b64decode(cursor + padding)
            if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != cursor:
                raise ValueError
            payload = json.loads(decoded)
        except (ValueError, UnicodeError, json.JSONDecodeError):
            raise ValueError("Quota reconciliation cursor is invalid.") from None
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema_version", "family", "key_scan", "target", "member_scan"}
            or payload.get("schema_version") != 1
            or payload.get("family") not in {"records", "replays"}
            or type(payload.get("key_scan")) is not int
            or payload["key_scan"] != 0
            or payload.get("target") is not None
            or type(payload.get("member_scan")) is not int
            or payload["member_scan"] != 0
        ):
            raise ValueError("Quota reconciliation cursor is invalid.")
        return payload["family"]

    async def reconcile_quota_state(
        self,
        *,
        epoch: int,
        cursor: str | None,
        limit: int,
        apply: bool,
        operation_id: str | None = None,
    ) -> QuotaReconciliationResult:
        requested_epoch = validate_epoch(epoch)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 256:
            raise ValueError("Quota reconciliation limit is invalid.")
        if not isinstance(apply, bool):
            raise ValueError("Quota reconciliation mode is invalid.")
        if operation_id is not None:
            validate_operation_id(operation_id)
        family = self._decode_quota_reconciliation_cursor(cursor)
        async with self._async_lock:
            self._ensure_open_locked()
            if (
                self._epoch.epoch != requested_epoch
                or self._epoch.state is not EpochState.RECONCILING
            ):
                raise CoordinationUnavailableError("Coordination epoch is not reconciling.")
            replay_fingerprint = (requested_epoch, cursor, limit)
            if operation_id is not None:
                replay = self._quota_reconciliation_replays.get(operation_id)
                if replay is not None:
                    if replay[0] != replay_fingerprint:
                        raise CoordinationCorruptError(
                            "Quota reconciliation operation conflicts with prior evidence."
                        )
                    return replay[1]

            def result(
                scanned: int,
                complete: bool,
                next_cursor: str | None,
                snapshot: object,
            ) -> QuotaReconciliationResult:
                digest = hashlib.sha256(
                    b"polaris-quota-reconciliation-snapshot-v1\x00"
                    + json.dumps(
                        {
                            "epoch": requested_epoch,
                            "input_cursor": cursor,
                            "limit": limit,
                            "snapshot": snapshot,
                            "scanned": scanned,
                            "complete": complete,
                            "next_cursor": next_cursor,
                        },
                        allow_nan=False,
                        default=str,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()
                value = QuotaReconciliationResult(scanned, complete, next_cursor, digest)
                if apply and operation_id is not None:
                    self._quota_reconciliation_replays[operation_id] = (
                        replay_fingerprint,
                        value,
                    )
                return value

            if requested_epoch in self._quota_reconciled_epochs:
                return result(0, True, None, {"already_complete": True})

            # A cursor is progress, not authority. A forged or stale replay-family
            # cursor may never bypass lifecycle validation.
            if family == "replays" and self._quota_records:
                family = "records"

            scanned = 0
            record_snapshot: list[object] = []
            if family == "records":
                identifiers = sorted(
                    self._quota_records,
                    key=lambda identifier: (
                        self._quota_records[identifier].request.key_id,
                        identifier,
                    ),
                )[:limit]
                record_snapshot = [
                    {
                        "reservation_id": identifier,
                        "request": asdict(self._quota_records[identifier].request),
                        "state": self._quota_records[identifier].state,
                        "accepted_at": self._quota_records[identifier].accepted_at,
                        "active_expires_at": self._quota_records[identifier].active_expires_at,
                        "retained_until": self._quota_records[identifier].retained_until,
                        "next_expiry_at": self._quota_records[identifier].next_expiry_at,
                    }
                    for identifier in identifiers
                ]
                now = self._clock()
                for identifier in identifiers:
                    record = self._quota_records[identifier]
                    if record.state == "active" and record.active_expires_at > now:
                        raise CoordinationReconciliationRequiredError(
                            "Active quota reservations must drain before reconciliation."
                        )
                if apply:
                    for identifier in identifiers:
                        self._remove_quota_record_locked(identifier)
                scanned = len(identifiers)
                records_remain = (
                    len(self._quota_records) > len(identifiers)
                    if not apply
                    else bool(self._quota_records)
                )
                if records_remain:
                    return result(
                        scanned,
                        False,
                        self._quota_reconciliation_cursor("records"),
                        {"family": "records", "records": record_snapshot},
                    )
                family = "replays"

            replay_keys = sorted(self._quota_replays)[: limit - scanned]
            replay_snapshot = [
                {
                    "operation": replay_key,
                    "key_id": str(self._quota_replays[replay_key].key_id),
                    "fingerprint_digest": hashlib.sha256(
                        repr(self._quota_replays[replay_key].fingerprint).encode("utf-8")
                    ).hexdigest(),
                    "result_digest": hashlib.sha256(
                        repr(self._quota_replays[replay_key].result).encode("utf-8")
                    ).hexdigest(),
                    "expires_at": self._quota_replays[replay_key].expires_at,
                }
                for replay_key in replay_keys
            ]
            if apply:
                for replay_key in replay_keys:
                    replay = self._quota_replays.pop(replay_key)
                    remaining = self._quota_replay_counts.get(replay.key_id, 0) - 1
                    if remaining > 0:
                        self._quota_replay_counts[replay.key_id] = remaining
                    else:
                        self._quota_replay_counts.pop(replay.key_id, None)
            scanned += len(replay_keys)
            replays_remain = (
                len(self._quota_replays) > len(replay_keys)
                if not apply
                else bool(self._quota_replays)
            )
            if replays_remain:
                return result(
                    scanned,
                    False,
                    self._quota_reconciliation_cursor("replays"),
                    {
                        "family": "replays",
                        "records": record_snapshot,
                        "replays": replay_snapshot,
                    },
                )
            if apply:
                self._quota_ids_by_key.clear()
                self._quota_rate_windows.clear()
                self._quota_lifecycle_expiries.clear()
                self._quota_replay_expiries.clear()
                self._quota_replay_counts.clear()
                self._quota_reconciled_epochs.add(requested_epoch)
            return result(
                scanned,
                True,
                None,
                {
                    "family": "complete",
                    "records": record_snapshot,
                    "replays": replay_snapshot,
                },
            )

    async def issue_security_session(self, request: SessionIssueRequest) -> SessionMutationResult:
        async with self._async_lock:
            self._ensure_open_locked()
            self._require_admission_locked()
            denial = self._security_epoch_denial_locked(request.fencing_epoch)
            if denial is not None:
                return SessionMutationResult(False, None, denial)
            now = self._security_now_locked()
            try:
                self._cleanup_security_sessions_locked(now)
            except CoordinationReconciliationRequiredError:
                return SessionMutationResult(False, None, "reconciliation_required")

            operation_key = f"issue:{request.operation_id}"
            fingerprint = self._session_issue_fingerprint(request)
            replay = self._security_session_replays.get(operation_key)
            if replay is not None:
                if replay.fingerprint != fingerprint:
                    return SessionMutationResult(False, None, "conflict")
                result = replay.result
                assert isinstance(result, SessionMutationResult)
                if result.applied:
                    current = self._security_sessions.get(request.session_digest)
                    if current is None or not self._same_security_session_evidence(
                        current, result.session
                    ):
                        return SessionMutationResult(False, None, "conflict")
                    current = self._validate_security_session_locked(request.session_digest)
                    return SessionMutationResult(True, current, idempotent=True)
                return SessionMutationResult(
                    result.applied,
                    result.session,
                    result.reason,
                    idempotent=True,
                )

            collision_digest = request.session_digest in self._security_sessions
            collision_reference = self._security_digest_by_reference.get(request.session_reference)
            if collision_digest:
                self._validate_security_session_locked(request.session_digest)
            if collision_reference is not None:
                self._validate_security_session_locked(collision_reference)
            if collision_digest or collision_reference is not None:
                result = SessionMutationResult(False, None, "conflict")
                if not self._store_security_replay_locked(
                    self._security_session_replays,
                    self._security_session_replay_expiries,
                    operation_key,
                    fingerprint,
                    result,
                    now + request.absolute_ttl_seconds,
                ):
                    return SessionMutationResult(False, None, "reconciliation_required")
                return result
            if len(self._security_sessions) >= self._security_session_limit:
                result = SessionMutationResult(False, None, "capacity")
                if not self._store_security_replay_locked(
                    self._security_session_replays,
                    self._security_session_replay_expiries,
                    operation_key,
                    fingerprint,
                    result,
                    now + request.absolute_ttl_seconds,
                ):
                    return SessionMutationResult(False, None, "reconciliation_required")
                return result

            session = self._session_from_issue(request, now)
            result = SessionMutationResult(True, session)
            if not self._store_security_replay_locked(
                self._security_session_replays,
                self._security_session_replay_expiries,
                operation_key,
                fingerprint,
                result,
                session.absolute_expires_at,
            ):
                return SessionMutationResult(False, None, "reconciliation_required")
            self._add_security_session_locked(session)
            return result

    async def resolve_security_session(
        self, request: SessionResolveRequest
    ) -> SessionResolveResult:
        async with self._async_lock:
            self._ensure_open_locked()
            self._require_admission_locked()
            denial = self._security_epoch_denial_locked(request.fencing_epoch)
            if denial is not None:
                return SessionResolveResult(False, None, denial)
            now = self._security_now_locked()
            existing = self._security_sessions.get(request.session_digest)
            was_expired = (
                existing is not None
                and min(existing.idle_expires_at, existing.absolute_expires_at) <= now
            )
            try:
                self._cleanup_security_sessions_locked(now)
            except CoordinationReconciliationRequiredError:
                return SessionResolveResult(False, None, "reconciliation_required")

            operation_key = f"resolve:{request.operation_id}"
            fingerprint = (
                request.session_digest,
                request.idle_ttl_seconds,
                request.fencing_epoch,
            )
            replay = self._security_session_replays.get(operation_key)
            if replay is not None:
                if replay.fingerprint != fingerprint:
                    return SessionResolveResult(False, None, "reconciliation_required")
                result = replay.result
                assert isinstance(result, SessionResolveResult)
                if result.resolved:
                    current = self._security_sessions.get(request.session_digest)
                    if current is None:
                        return SessionResolveResult(False, None, "not_found")
                    current = self._validate_security_session_locked(request.session_digest)
                    return SessionResolveResult(True, current, idempotent=True)
                return SessionResolveResult(
                    result.resolved,
                    result.session,
                    result.reason,
                    idempotent=True,
                )

            session = self._security_sessions.get(request.session_digest)
            if session is None:
                result = SessionResolveResult(
                    False,
                    None,
                    "expired" if was_expired else "not_found",
                )
                if not self._store_security_replay_locked(
                    self._security_session_replays,
                    self._security_session_replay_expiries,
                    operation_key,
                    fingerprint,
                    result,
                    now + request.idle_ttl_seconds,
                ):
                    return SessionResolveResult(False, None, "reconciliation_required")
                return result

            session = self._validate_security_session_locked(request.session_digest)
            idle_expires_at = min(
                now + request.idle_ttl_seconds,
                session.absolute_expires_at,
            )
            if idle_expires_at <= now:
                raise CoordinationCorruptError("Coordination state is invalid.")
            touched = SecuritySessionState(
                session.session_digest,
                session.session_reference,
                session.principal_index,
                session.principal_type,
                session.payload,
                session.issued_at,
                now,
                idle_expires_at,
                session.absolute_expires_at,
            )
            result = SessionResolveResult(True, touched)
            if not self._store_security_replay_locked(
                self._security_session_replays,
                self._security_session_replay_expiries,
                operation_key,
                fingerprint,
                result,
                touched.idle_expires_at,
            ):
                return SessionResolveResult(False, None, "reconciliation_required")
            self._security_sessions[request.session_digest] = touched
            self._security_session_expiries.replace(
                request.session_digest,
                min(touched.idle_expires_at, touched.absolute_expires_at),
            )
            return result

    async def rotate_security_session(self, request: SessionRotateRequest) -> SessionMutationResult:
        async with self._async_lock:
            self._ensure_open_locked()
            self._require_admission_locked()
            denial = self._security_epoch_denial_locked(request.fencing_epoch)
            if denial is not None:
                return SessionMutationResult(False, None, denial)
            now = self._security_now_locked()
            try:
                self._cleanup_security_sessions_locked(now)
            except CoordinationReconciliationRequiredError:
                return SessionMutationResult(False, None, "reconciliation_required")

            operation_key = f"rotate:{request.operation_id}"
            fingerprint = (
                request.current_session_digest,
                self._session_issue_fingerprint(request.replacement),
                request.fencing_epoch,
            )
            replay = self._security_session_replays.get(operation_key)
            if replay is not None:
                if replay.fingerprint != fingerprint:
                    return SessionMutationResult(False, None, "conflict")
                result = replay.result
                assert isinstance(result, SessionMutationResult)
                if result.applied:
                    current = self._security_sessions.get(request.replacement.session_digest)
                    if current is None or not self._same_security_session_evidence(
                        current, result.session
                    ):
                        return SessionMutationResult(False, None, "not_found")
                    current = self._validate_security_session_locked(
                        request.replacement.session_digest
                    )
                    return SessionMutationResult(True, current, idempotent=True)
                return SessionMutationResult(
                    result.applied,
                    result.session,
                    result.reason,
                    idempotent=True,
                )

            current = self._security_sessions.get(request.current_session_digest)
            if current is None:
                result = SessionMutationResult(False, None, "not_found")
                if not self._store_security_replay_locked(
                    self._security_session_replays,
                    self._security_session_replay_expiries,
                    operation_key,
                    fingerprint,
                    result,
                    now + request.replacement.absolute_ttl_seconds,
                ):
                    return SessionMutationResult(False, None, "reconciliation_required")
                return result
            current = self._validate_security_session_locked(request.current_session_digest)
            replacement_digest = self._security_sessions.get(request.replacement.session_digest)
            replacement_reference_digest = self._security_digest_by_reference.get(
                request.replacement.session_reference
            )
            if replacement_digest is not None:
                self._validate_security_session_locked(request.replacement.session_digest)
            if (
                replacement_reference_digest is not None
                and replacement_reference_digest != request.current_session_digest
            ):
                self._validate_security_session_locked(replacement_reference_digest)
            if replacement_digest is not None or (
                replacement_reference_digest is not None
                and replacement_reference_digest != request.current_session_digest
            ):
                result = SessionMutationResult(False, None, "conflict")
                if not self._store_security_replay_locked(
                    self._security_session_replays,
                    self._security_session_replay_expiries,
                    operation_key,
                    fingerprint,
                    result,
                    now + request.replacement.absolute_ttl_seconds,
                ):
                    return SessionMutationResult(False, None, "reconciliation_required")
                return result

            replacement = self._session_from_issue(request.replacement, now)
            result = SessionMutationResult(True, replacement)
            if not self._store_security_replay_locked(
                self._security_session_replays,
                self._security_session_replay_expiries,
                operation_key,
                fingerprint,
                result,
                replacement.absolute_expires_at,
            ):
                return SessionMutationResult(False, None, "reconciliation_required")
            self._remove_security_session_locked(current.session_digest)
            self._add_security_session_locked(replacement)
            return result

    async def revoke_security_sessions(self, request: SessionRevokeRequest) -> SessionRevokeResult:
        async with self._async_lock:
            self._ensure_open_locked()
            self._require_admission_locked()
            self._require_security_epoch_locked(request.fencing_epoch)
            now = self._security_now_locked()
            self._cleanup_security_sessions_locked(now)
            self._validate_security_session_indexes_locked()
            operation_key = f"revoke:{request.operation_id}"
            fingerprint = (
                request.target,
                request.target_value,
                request.fencing_epoch,
                request.replay_ttl_seconds,
            )
            replay = self._security_session_replays.get(operation_key)
            if replay is not None:
                if replay.fingerprint != fingerprint:
                    raise CoordinationUnavailableError("Coordination operation conflicts.")
                result = replay.result
                assert isinstance(result, SessionRevokeResult)
                return SessionRevokeResult(result.revoked_count, idempotent=True)

            if request.target is SessionRevokeTarget.DIGEST:
                digests = (
                    {request.target_value}
                    if request.target_value in self._security_sessions
                    else set()
                )
            elif request.target is SessionRevokeTarget.REFERENCE:
                digest = self._security_digest_by_reference.get(request.target_value)
                digests = {digest} if digest is not None else set()
            elif request.target is SessionRevokeTarget.PRINCIPAL:
                digests = set(self._security_digests_by_principal.get(request.target_value, ()))
            else:
                principal_type = SecurityPrincipalType(request.target_value)
                digests = set(self._security_digests_by_principal_type.get(principal_type, ()))
            for digest in sorted(digests):
                self._validate_security_session_locked(digest)

            result = SessionRevokeResult(len(digests))
            if not self._store_security_replay_locked(
                self._security_session_replays,
                self._security_session_replay_expiries,
                operation_key,
                fingerprint,
                result,
                now + request.replay_ttl_seconds,
            ):
                raise CoordinationReconciliationRequiredError("Reconciliation is required.")
            for digest in sorted(digests):
                self._remove_security_session_locked(digest)
            return result

    async def list_security_sessions(self, request: SessionListRequest) -> SessionPage:
        async with self._async_lock:
            self._ensure_open_locked()
            self._require_security_epoch_locked(request.fencing_epoch)
            now = self._security_now_locked()
            self._cleanup_security_sessions_locked(now)
            self._validate_security_session_indexes_locked()
            sessions = list(self._security_sessions.values())
            sessions.sort(key=lambda item: item.session_reference)
            if request.after_reference is not None:
                sessions = [
                    item for item in sessions if item.session_reference >= request.after_reference
                ]
            page = tuple(sessions[: request.limit])
            next_reference = (
                sessions[request.limit].session_reference if len(sessions) > request.limit else None
            )
            return SessionPage(page, next_reference)

    async def read_session_reconciliation(self, *, epoch: int) -> SessionReconciliationSnapshot:
        async with self._async_lock:
            self._ensure_open_locked()
            requested = validate_epoch(epoch)
            if self._epoch != Epoch(requested, EpochState.RECONCILING):
                raise CoordinationUnavailableError("Coordination store is not reconciling.")
            self._validate_security_session_indexes_locked()
            payload = json.dumps(
                [
                    (session.session_reference, session.principal_type.value)
                    for session in sorted(
                        self._security_sessions.values(),
                        key=lambda item: item.session_reference,
                    )
                ],
                separators=(",", ":"),
            ).encode("utf-8")
            digest = hashlib.sha256(b"polaris-session-reconciliation-v1\x00" + payload).hexdigest()
            return SessionReconciliationSnapshot(len(self._security_sessions), digest)

    async def reserve_security_attempt(
        self, request: AttemptReservationRequest
    ) -> AttemptReservationDecision:
        async with self._async_lock:
            self._ensure_open_locked()
            self._require_admission_locked()
            denial = self._security_epoch_denial_locked(request.fencing_epoch)
            if denial is not None:
                return AttemptReservationDecision(False, 0, 0, denial)
            now = self._security_now_locked()
            try:
                self._cleanup_security_attempts_locked(request.category, now)
            except CoordinationReconciliationRequiredError:
                return AttemptReservationDecision(False, 0, 0, "reconciliation_required")

            records = self._security_attempts[request.category]
            replays = self._security_attempt_replays[request.category]
            replay_heap = self._security_attempt_replay_expiries[request.category]
            operation_key = f"reserve:{request.operation_id}"
            fingerprint = (
                request.client_index,
                request.limit,
                request.window_seconds,
                request.fencing_epoch,
            )
            replay = replays.get(operation_key)
            if replay is not None:
                if replay.fingerprint != fingerprint:
                    return AttemptReservationDecision(False, 0, 0, "reconciliation_required")
                result = replay.result
                assert isinstance(result, AttemptReservationDecision)
                return AttemptReservationDecision(
                    result.allowed,
                    result.remaining_attempts,
                    result.retry_after_seconds,
                    result.reason,
                    idempotent=True,
                )

            record = records.get(request.client_index)
            if (
                record is not None
                and self._security_attempt_expiries[request.category].expiry_for(
                    request.client_index
                )
                != record.expires_at
            ):
                raise CoordinationCorruptError("Coordination state is invalid.")
            expires_at = record.expires_at if record is not None else now + request.window_seconds
            if record is None and len(records) >= self._security_attempt_limit:
                result = AttemptReservationDecision(False, 0, 0, "capacity")
            elif record is not None and record.count >= request.limit:
                result = AttemptReservationDecision(
                    False,
                    0,
                    max(1, math.ceil(record.expires_at - now)),
                    "limited",
                )
            else:
                count = 1 if record is None else record.count + 1
                result = AttemptReservationDecision(
                    True,
                    max(0, request.limit - count),
                    0,
                )
            if not self._store_security_replay_locked(
                replays,
                replay_heap,
                operation_key,
                fingerprint,
                result,
                expires_at,
            ):
                return AttemptReservationDecision(False, 0, 0, "reconciliation_required")
            if result.allowed:
                records[request.client_index] = _SecurityAttemptRecord(
                    1 if record is None else record.count + 1,
                    expires_at,
                )
                self._security_attempt_expiries[request.category].replace(
                    request.client_index,
                    expires_at,
                )
            return result

    async def clear_security_attempts(self, request: AttemptClearRequest) -> AttemptClearResult:
        async with self._async_lock:
            self._ensure_open_locked()
            self._require_admission_locked()
            self._require_security_epoch_locked(request.fencing_epoch)
            now = self._security_now_locked()
            self._cleanup_security_attempts_locked(request.category, now)
            records = self._security_attempts[request.category]
            replays = self._security_attempt_replays[request.category]
            replay_heap = self._security_attempt_replay_expiries[request.category]
            operation_key = f"clear:{request.operation_id}"
            fingerprint = (request.client_index, request.fencing_epoch)
            replay = replays.get(operation_key)
            if replay is not None:
                if replay.fingerprint != fingerprint:
                    raise CoordinationUnavailableError("Coordination operation conflicts.")
                result = replay.result
                assert isinstance(result, AttemptClearResult)
                return AttemptClearResult(result.cleared, idempotent=True)

            record = records.get(request.client_index)
            if (
                record is not None
                and self._security_attempt_expiries[request.category].expiry_for(
                    request.client_index
                )
                != record.expires_at
            ):
                raise CoordinationCorruptError("Coordination state is invalid.")
            result = AttemptClearResult(record is not None)
            expires_at = (
                record.expires_at
                if record is not None
                else now + MIN_SECURITY_ATTEMPT_WINDOW_SECONDS
            )
            if not self._store_security_replay_locked(
                replays,
                replay_heap,
                operation_key,
                fingerprint,
                result,
                expires_at,
            ):
                raise CoordinationReconciliationRequiredError("Reconciliation is required.")
            if record is not None:
                records.pop(request.client_index, None)
                self._security_attempt_expiries[request.category].discard(request.client_index)
            return result

    async def create_oidc_transaction(
        self, request: OidcTransactionCreateRequest
    ) -> TransactionCreateResult:
        async with self._async_lock:
            self._ensure_open_locked()
            self._require_admission_locked()
            denial = self._security_epoch_denial_locked(request.fencing_epoch)
            if denial is not None:
                return TransactionCreateResult(False, denial)
            now = self._security_now_locked()
            try:
                self._cleanup_oidc_transactions_locked(now)
            except CoordinationReconciliationRequiredError:
                return TransactionCreateResult(False, "reconciliation_required")

            operation_key = f"create:{request.operation_id}"
            fingerprint = (
                request.state_index,
                request.browser_index,
                request.payload,
                request.ttl_seconds,
                request.fencing_epoch,
            )
            replay = self._oidc_transaction_replays.get(operation_key)
            if replay is not None:
                if replay.fingerprint != fingerprint:
                    return TransactionCreateResult(False, "conflict")
                result = replay.result
                assert isinstance(result, TransactionCreateResult)
                if result.applied:
                    expected = _OidcTransactionRecord(
                        request.browser_index,
                        request.payload,
                        replay.expires_at,
                    )
                    if self._oidc_transactions.get(request.state_index) != expected:
                        return TransactionCreateResult(False, "conflict")
                    self._validate_oidc_transaction_locked(request.state_index)
                return TransactionCreateResult(
                    result.applied,
                    result.reason,
                    idempotent=True,
                )

            if request.state_index in self._oidc_transactions:
                self._validate_oidc_transaction_locked(request.state_index)
                result = TransactionCreateResult(False, "conflict")
            elif len(self._oidc_transactions) >= self._oidc_transaction_limit:
                result = TransactionCreateResult(False, "capacity")
            else:
                result = TransactionCreateResult(True)
            expires_at = now + request.ttl_seconds
            if not self._store_security_replay_locked(
                self._oidc_transaction_replays,
                self._oidc_transaction_replay_expiries,
                operation_key,
                fingerprint,
                result,
                expires_at,
            ):
                return TransactionCreateResult(False, "reconciliation_required")
            if result.applied:
                self._oidc_transactions[request.state_index] = _OidcTransactionRecord(
                    request.browser_index,
                    request.payload,
                    expires_at,
                )
                self._oidc_transaction_expiries.replace(
                    request.state_index,
                    expires_at,
                )
            return result

    async def consume_oidc_transaction(
        self, request: OidcTransactionConsumeRequest
    ) -> OidcTransactionConsumeResult:
        async with self._async_lock:
            self._ensure_open_locked()
            fence = self._admission_fence_locked()
            denial = self._security_epoch_denial_locked(request.fencing_epoch)
            if denial is not None:
                return OidcTransactionConsumeResult(False, None, denial)
            now = self._security_now_locked()
            existing = self._oidc_transactions.get(request.state_index)
            if existing is not None:
                existing = self._validate_oidc_transaction_locked(request.state_index)
            was_expired = existing is not None and existing.expires_at <= now
            try:
                self._cleanup_oidc_transactions_locked(now)
            except CoordinationReconciliationRequiredError:
                return OidcTransactionConsumeResult(False, None, "reconciliation_required")

            operation_key = f"consume:{request.operation_id}"
            fingerprint = (
                request.state_index,
                request.browser_index,
                request.fencing_epoch,
            )
            replay = self._oidc_transaction_replays.get(operation_key)
            if replay is not None:
                if replay.fingerprint != fingerprint:
                    return OidcTransactionConsumeResult(False, None, "reconciliation_required")
                result = replay.result
                assert isinstance(result, OidcTransactionConsumeResult)
                if result.consumed:
                    return OidcTransactionConsumeResult(
                        False,
                        None,
                        "not_found",
                        idempotent=True,
                    )
                return OidcTransactionConsumeResult(
                    result.consumed,
                    result.payload,
                    result.reason,
                    idempotent=True,
                )

            transaction = self._oidc_transactions.get(request.state_index)
            if transaction is None:
                result = OidcTransactionConsumeResult(
                    False,
                    None,
                    "expired" if was_expired else "not_found",
                )
                expires_at = now + MAX_OIDC_TRANSACTION_TTL_SECONDS
            elif not hmac.compare_digest(
                transaction.browser_index,
                request.browser_index,
            ):
                result = OidcTransactionConsumeResult(False, None, "browser_mismatch")
                expires_at = transaction.expires_at
            else:
                result = OidcTransactionConsumeResult(True, transaction.payload)
                expires_at = transaction.expires_at
            if fence is not None and not result.consumed:
                return result
            if not self._store_security_replay_locked(
                self._oidc_transaction_replays,
                self._oidc_transaction_replay_expiries,
                operation_key,
                fingerprint,
                result,
                expires_at,
            ):
                return OidcTransactionConsumeResult(False, None, "reconciliation_required")
            if result.consumed:
                self._oidc_transactions.pop(request.state_index, None)
                self._oidc_transaction_expiries.discard(request.state_index)
            return result

    async def close(self) -> None:
        async with self._async_lock:
            self._closed = True
