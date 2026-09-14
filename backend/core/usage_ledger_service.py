"""Lifecycle and selected-backend boundary for durable usage and hard budgets."""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from collections.abc import Awaitable
from typing import Any, TypeVar

from core.usage_ledger import (
    BudgetCommitResult,
    BudgetReleaseResult,
    BudgetReservationDecision,
    BudgetReservationRequest,
    CredentialUsageAggregate,
    ProviderUsageAggregate,
    SpendSnapshot,
    UsageAppendResult,
    UsageLedgerConflict,
    UsageLedgerEntry,
    UsageLedgerRepository,
    UsageLedgerStateConflict,
    UsageLiabilityPage,
    UsageTimeBucket,
)

_Result = TypeVar("_Result")
_METRICS_LOCK = threading.Lock()
_OPERATION_METRICS: dict[tuple[str, str, str], int] = {}


def _repository_backend(repository: UsageLedgerRepository) -> str:
    name = type(repository).__name__.lower()
    for backend in ("sqlite", "postgresql", "mongodb"):
        if backend in name:
            return backend
    return "unknown"


def _increment_operation_metric(backend: str, operation: str, result: str) -> None:
    with _METRICS_LOCK:
        key = (backend, operation, result)
        _OPERATION_METRICS[key] = _OPERATION_METRICS.get(key, 0) + 1


def render_usage_ledger_metrics() -> str:
    """Render bounded, attribution-free selected-ledger operation counters."""

    with _METRICS_LOCK:
        snapshot = dict(_OPERATION_METRICS)
    lines = [
        "# HELP polaris_usage_ledger_operations_total Durable usage ledger operations.",
        "# TYPE polaris_usage_ledger_operations_total counter",
    ]
    for (backend, operation, result), count in sorted(snapshot.items()):
        lines.append(
            "polaris_usage_ledger_operations_total"
            f'{{backend="{backend}",operation="{operation}",result="{result}"}} {count}'
        )
    return "\n".join(lines) + "\n"


class UsageLedgerService:
    """Expose one repository while retaining content-free availability evidence."""

    def __init__(self, repository: UsageLedgerRepository) -> None:
        self._repository = repository
        self._backend = _repository_backend(repository)
        self._available = True
        self._failure_count = 0
        self._last_error_type = ""
        self._last_failure_at: float | None = None
        self._recovered_at: float | None = None

    @classmethod
    async def create(cls, storage: Any) -> "UsageLedgerService":
        repository = await storage.create_usage_ledger_repository()
        return cls(repository)

    def health_snapshot(self) -> dict[str, object]:
        return {
            "available": self._available,
            "failure_count": self._failure_count,
            "last_error_type": self._last_error_type,
            "last_failure_at": self._last_failure_at,
            "recovered_at": self._recovered_at,
        }

    async def check_available(self) -> None:
        await self._run("health", self._repository.check_available())

    async def close(self) -> None:
        close = getattr(self._repository, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result

    async def append_usage(self, entry: UsageLedgerEntry) -> UsageAppendResult:
        return await self._run("append", self._repository.append_usage(entry))

    async def reserve_budget(self, request: BudgetReservationRequest) -> BudgetReservationDecision:
        return await self._run("reserve", self._repository.reserve_budget(request))

    async def commit_reservation(
        self,
        reservation_id: str,
        usage: UsageLedgerEntry,
        *,
        transitioned_at: float,
    ) -> BudgetCommitResult:
        return await self._run(
            "commit",
            self._repository.commit_reservation(
                reservation_id,
                usage,
                transitioned_at=transitioned_at,
            ),
        )

    async def release_reservation(
        self,
        reservation_id: str,
        *,
        transitioned_at: float,
    ) -> BudgetReleaseResult:
        return await self._run(
            "release",
            self._repository.release_reservation(
                reservation_id,
                transitioned_at=transitioned_at,
            ),
        )

    async def reconcile_expired(self, *, now: float, limit: int) -> int:
        return await self._run(
            "reconcile", self._repository.reconcile_expired(now=now, limit=limit)
        )

    async def reconciliation_page(self, *, after: str | None, limit: int) -> UsageLiabilityPage:
        return await self._run(
            "reconciliation_page",
            self._repository.reconciliation_page(after=after, limit=limit),
        )

    async def get_spend(self, *, since: float, api_key_id: str = "") -> SpendSnapshot:
        return await self._run(
            "spend", self._repository.get_spend(since=since, api_key_id=api_key_id)
        )

    async def aggregate_credentials(
        self, *, since: float | None = None
    ) -> list[CredentialUsageAggregate]:
        return await self._run(
            "report_credentials", self._repository.aggregate_credentials(since=since)
        )

    async def aggregate_providers(self) -> list[ProviderUsageAggregate]:
        return await self._run("report_providers", self._repository.aggregate_providers())

    async def aggregate_time_series(
        self, *, since: float, until: float, points: int
    ) -> list[UsageTimeBucket]:
        return await self._run(
            "report_time_series",
            self._repository.aggregate_time_series(since=since, until=until, points=points),
        )

    async def retire_credential(
        self,
        credential_ref: str,
        replacement_ref: str,
        *,
        provider: str,
        limit: int,
    ) -> int:
        return await self._run(
            "retire_credential",
            self._repository.retire_credential(
                credential_ref,
                replacement_ref,
                provider=provider,
                limit=limit,
            ),
        )

    async def _run(self, operation_name: str, operation: Awaitable[_Result]) -> _Result:
        try:
            result = await operation
        except Exception as exc:
            self._available = False
            self._failure_count += 1
            self._last_error_type = type(exc).__name__
            self._last_failure_at = time.time()
            if isinstance(exc, UsageLedgerConflict):
                metric_result = "conflict"
            elif isinstance(exc, UsageLedgerStateConflict):
                metric_result = "state_conflict"
            else:
                metric_result = "error"
            _increment_operation_metric(self._backend, operation_name, metric_result)
            raise
        if not self._available:
            self._recovered_at = time.time()
        self._available = True
        metric_result = "idempotent" if bool(getattr(result, "idempotent", False)) else "success"
        if hasattr(result, "accepted") and not bool(getattr(result, "accepted")):
            metric_result = "rejected"
        _increment_operation_metric(self._backend, operation_name, metric_result)
        return result


_usage_ledger_service: UsageLedgerService | None = None
_usage_ledger_service_lock = asyncio.Lock()


async def initialize_usage_ledger_service(storage: Any | None = None) -> UsageLedgerService:
    global _usage_ledger_service
    async with _usage_ledger_service_lock:
        if _usage_ledger_service is None:
            if storage is None:
                from core.storage_adapter import get_storage_adapter

                storage = await get_storage_adapter()
            _usage_ledger_service = await UsageLedgerService.create(storage)
        return _usage_ledger_service


def get_usage_ledger_service() -> UsageLedgerService:
    if _usage_ledger_service is None:
        raise RuntimeError("Usage ledger service is not initialized.")
    return _usage_ledger_service


async def close_usage_ledger_service() -> None:
    global _usage_ledger_service
    async with _usage_ledger_service_lock:
        service = _usage_ledger_service
        _usage_ledger_service = None
        if service is not None:
            await service.close()
