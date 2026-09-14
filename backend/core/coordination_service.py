"""Observed access to the standalone runtime's process-local coordination store."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from core.coordination import (
    AdmissionFence,
    CasRequest,
    CasResult,
    CasSnapshot,
    CoordinationCorruptError,
    CoordinationReconciliationRequiredError,
    CoordinationTime,
    CoordinationUnavailableError,
    Epoch,
    InvalidationGeneration,
    InvalidationRequest,
    InvalidationResult,
    QuotaCommitRequest,
    QuotaCommitResult,
    QuotaReservationDecision,
    QuotaReservationRequest,
)
from core.security_coordination import (
    AttemptClearRequest,
    AttemptClearResult,
    AttemptReservationDecision,
    AttemptReservationRequest,
    OidcTransactionConsumeRequest,
    OidcTransactionConsumeResult,
    OidcTransactionCreateRequest,
    SessionIssueRequest,
    SessionListRequest,
    SessionMutationResult,
    SessionPage,
    SessionResolveRequest,
    SessionResolveResult,
    SessionRevokeRequest,
    SessionRevokeResult,
    SessionRotateRequest,
    TransactionCreateResult,
)

_Result = TypeVar("_Result")

_BACKENDS = frozenset({"in_memory", "unknown"})
_OPERATIONS = frozenset(
    {
        "get",
        "set",
        "delete",
        "increment",
        "acquire_lock",
        "release_lock",
        "initialize_epoch",
        "read_epoch",
        "read_coordination_time",
        "advance_epoch",
        "mark_epoch_ready",
        "complete_admission_drain",
        "compare_and_set",
        "read_cas",
        "invalidate",
        "read_invalidation_generation",
        "reserve_quota",
        "commit_quota",
        "release_quota",
        "issue_security_session",
        "resolve_security_session",
        "rotate_security_session",
        "revoke_security_sessions",
        "list_security_sessions",
        "reserve_security_attempt",
        "clear_security_attempts",
        "create_oidc_transaction",
        "consume_oidc_transaction",
        "close",
    }
)
_RESULTS = frozenset(
    {
        "success",
        "rejected",
        "idempotent",
        "unavailable",
        "corrupt",
        "reconciliation_required",
        "unexpected",
    }
)
_METRICS_LOCK = threading.Lock()
_OPERATION_METRICS: dict[tuple[str, str, str], int] = {}


def _backend_name(store: object) -> str:
    name = type(store).__name__.lower()
    if "inmemory" in name:
        return "in_memory"
    return "unknown"


def _bounded_backend(value: object) -> str:
    return value if isinstance(value, str) and value in _BACKENDS else "unknown"


def _bounded_operation(value: object) -> str:
    return value if isinstance(value, str) and value in _OPERATIONS else "close"


def _bounded_result(value: object) -> str:
    return value if isinstance(value, str) and value in _RESULTS else "unexpected"


def _increment_operation_metric(backend: object, operation: object, result: object) -> None:
    key = (_bounded_backend(backend), _bounded_operation(operation), _bounded_result(result))
    with _METRICS_LOCK:
        _OPERATION_METRICS[key] = _OPERATION_METRICS.get(key, 0) + 1


def render_coordination_operation_metrics() -> str:
    """Render fixed-cardinality coordination operation counters."""

    with _METRICS_LOCK:
        snapshot = dict(_OPERATION_METRICS)
    lines = [
        "# HELP polaris_coordination_operations_total Coordination store operations.",
        "# TYPE polaris_coordination_operations_total counter",
    ]
    for (backend, operation, result), count in sorted(snapshot.items()):
        lines.append(
            "polaris_coordination_operations_total"
            f'{{backend="{backend}",operation="{operation}",result="{result}"}} {count}'
        )
    return "\n".join(lines) + "\n"


def clear_coordination_operation_metrics_for_testing() -> None:
    with _METRICS_LOCK:
        _OPERATION_METRICS.clear()


def record_coordination_operation_for_testing(
    backend: object, operation: object, result: object
) -> None:
    """Exercise normalization through the public renderer tests."""

    _increment_operation_metric(backend, operation, result)


def _error_category(exc: BaseException) -> str:
    if isinstance(exc, CoordinationReconciliationRequiredError):
        return "reconciliation_required"
    if isinstance(exc, CoordinationUnavailableError):
        return "unavailable"
    if isinstance(exc, CoordinationCorruptError):
        return "corrupt"
    return "unexpected"


def _result_category(result: object) -> str:
    if bool(getattr(result, "idempotent", False)):
        return "idempotent"
    if hasattr(result, "committed") and not bool(getattr(result, "committed")):
        return "rejected"
    if hasattr(result, "accepted") and not bool(getattr(result, "accepted")):
        return "rejected"
    if hasattr(result, "applied") and not bool(getattr(result, "applied")):
        return "rejected"
    if hasattr(result, "resolved") and not bool(getattr(result, "resolved")):
        return "rejected"
    if hasattr(result, "allowed") and not bool(getattr(result, "allowed")):
        return "rejected"
    if hasattr(result, "consumed") and not bool(getattr(result, "consumed")):
        return "rejected"
    if isinstance(result, bool) and not result:
        return "rejected"
    return "success"


class CoordinationService:
    """Observe one process-local coordination store without exposing record contents."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._backend = _backend_name(store)
        self._available = True
        self._closed = False
        self._closing = False
        self._failure_count = 0
        self._last_error_category = ""
        self._last_failure_at: float | None = None
        self._recovered_at: float | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._close_task: asyncio.Task[None] | None = None

    def health_snapshot(self) -> dict[str, object]:
        """Return attribution-free lifecycle evidence suitable for diagnostics."""

        return {
            "backend": self._backend,
            "available": self._available,
            "closed": self._closed,
            "failure_count": self._failure_count,
            "last_error_category": self._last_error_category,
            "last_failure_at": self._last_failure_at,
            "recovered_at": self._recovered_at,
        }

    async def _run(
        self,
        operation_name: str,
        operation: Callable[..., Awaitable[_Result]],
        *args: object,
        **kwargs: object,
    ) -> _Result:
        if self._closed or self._closing:
            error = CoordinationUnavailableError("Coordination service is closed.")
            self._record_failure(operation_name, error)
            raise error
        try:
            result = await operation(*args, **kwargs)
        except Exception as exc:
            self._record_failure(operation_name, exc)
            raise
        if not self._available:
            self._recovered_at = time.time()
        self._available = True
        _increment_operation_metric(self._backend, operation_name, _result_category(result))
        return result

    def _record_failure(self, operation_name: str, exc: BaseException) -> None:
        category = _error_category(exc)
        self._available = False
        self._failure_count += 1
        self._last_error_category = category
        self._last_failure_at = time.time()
        _increment_operation_metric(self._backend, operation_name, category)

    async def get(self, key: str) -> Any:
        return await self._run("get", self._store.get, key)

    async def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        await self._run("set", self._store.set, key, value, ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._run("delete", self._store.delete, key)

    async def increment(self, key: str, amount: int = 1, ttl_seconds: float | None = None) -> int:
        return await self._run("increment", self._store.increment, key, amount, ttl_seconds)

    async def acquire_lock(self, lock_key: str, ttl_seconds: float = 10.0) -> bool:
        return await self._run("acquire_lock", self._store.acquire_lock, lock_key, ttl_seconds)

    async def release_lock(self, lock_key: str) -> None:
        await self._run("release_lock", self._store.release_lock, lock_key)

    async def read_epoch(self) -> Epoch:
        return await self._run("read_epoch", self._store.read_epoch)

    async def initialize_epoch(self) -> Epoch:
        return await self._run("initialize_epoch", self._store.initialize_epoch)

    async def complete_admission_drain(
        self, fence: AdmissionFence, *, epoch: int, operation_id: str
    ) -> None:
        await self._run(
            "complete_admission_drain",
            self._store.complete_admission_drain,
            fence,
            epoch=epoch,
            operation_id=operation_id,
        )

    async def read_coordination_time(self, *, epoch: int) -> CoordinationTime:
        return await self._run(
            "read_coordination_time", self._store.read_coordination_time, epoch=epoch
        )

    async def advance_epoch(self, expected_epoch: int, operation_id: str) -> Epoch:
        return await self._run(
            "advance_epoch", self._store.advance_epoch, expected_epoch, operation_id
        )

    async def mark_epoch_ready(self, epoch: int, operation_id: str) -> Epoch:
        return await self._run(
            "mark_epoch_ready", self._store.mark_epoch_ready, epoch, operation_id
        )

    async def compare_and_set(self, request: CasRequest) -> CasResult:
        return await self._run("compare_and_set", self._store.compare_and_set, request)

    async def read_cas(self, key: str, *, epoch: int) -> CasSnapshot:
        return await self._run("read_cas", self._store.read_cas, key, epoch=epoch)

    async def invalidate(self, request: InvalidationRequest) -> InvalidationResult:
        return await self._run("invalidate", self._store.invalidate, request)

    async def read_invalidation_generation(self, scope: str) -> InvalidationGeneration:
        return await self._run(
            "read_invalidation_generation", self._store.read_invalidation_generation, scope
        )

    async def reserve_quota(self, request: QuotaReservationRequest) -> QuotaReservationDecision:
        return await self._run("reserve_quota", self._store.reserve_quota, request)

    async def commit_quota(self, request: QuotaCommitRequest) -> QuotaCommitResult:
        return await self._run("commit_quota", self._store.commit_quota, request)

    async def release_quota(self, reservation_id: str, **kwargs: object) -> bool:
        return await self._run("release_quota", self._store.release_quota, reservation_id, **kwargs)

    async def issue_security_session(self, request: SessionIssueRequest) -> SessionMutationResult:
        return await self._run(
            "issue_security_session", self._store.issue_security_session, request
        )

    async def resolve_security_session(
        self, request: SessionResolveRequest
    ) -> SessionResolveResult:
        return await self._run(
            "resolve_security_session", self._store.resolve_security_session, request
        )

    async def rotate_security_session(self, request: SessionRotateRequest) -> SessionMutationResult:
        return await self._run(
            "rotate_security_session", self._store.rotate_security_session, request
        )

    async def revoke_security_sessions(self, request: SessionRevokeRequest) -> SessionRevokeResult:
        return await self._run(
            "revoke_security_sessions", self._store.revoke_security_sessions, request
        )

    async def list_security_sessions(self, request: SessionListRequest) -> SessionPage:
        return await self._run(
            "list_security_sessions", self._store.list_security_sessions, request
        )

    async def reserve_security_attempt(
        self, request: AttemptReservationRequest
    ) -> AttemptReservationDecision:
        return await self._run(
            "reserve_security_attempt", self._store.reserve_security_attempt, request
        )

    async def clear_security_attempts(self, request: AttemptClearRequest) -> AttemptClearResult:
        return await self._run(
            "clear_security_attempts", self._store.clear_security_attempts, request
        )

    async def create_oidc_transaction(
        self, request: OidcTransactionCreateRequest
    ) -> TransactionCreateResult:
        return await self._run(
            "create_oidc_transaction", self._store.create_oidc_transaction, request
        )

    async def consume_oidc_transaction(
        self, request: OidcTransactionConsumeRequest
    ) -> OidcTransactionConsumeResult:
        return await self._run(
            "consume_oidc_transaction", self._store.consume_oidc_transaction, request
        )

    async def close(self) -> None:
        """Close the supplied backend once, without letting waiter cancellation abort it."""

        async with self._lifecycle_lock:
            if self._closed:
                _increment_operation_metric(self._backend, "close", "idempotent")
                return
            if self._close_task is None:
                self._closing = True
                self._close_task = asyncio.create_task(self._close_backend())
            close_task = self._close_task
        await asyncio.shield(close_task)

    async def _close_backend(self) -> None:
        try:
            await self._store.close()
        except BaseException as exc:
            async with self._lifecycle_lock:
                self._closing = False
                self._close_task = None
                self._record_failure("close", exc)
            raise

        async with self._lifecycle_lock:
            if not self._available:
                self._recovered_at = time.time()
            self._available = True
            self._closed = True
            self._closing = False
            self._close_task = None
            _increment_operation_metric(self._backend, "close", "success")
