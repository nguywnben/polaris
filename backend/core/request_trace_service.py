"""Request-scoped trace collection and durable lifecycle service."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any, Iterator

from core.request_trace import (
    MAX_TRACE_DECISIONS,
    REQUEST_TRACE_SCHEMA_VERSION,
    RequestDecision,
    RequestTrace,
    RequestTracePage,
    RequestTraceQuery,
    RequestTraceRetentionPolicy,
)

REQUEST_TRACE_MASTER_KEY_CONFIG = "request_trace_master_key_v1"
REQUEST_TRACE_RETENTION_CONFIG = "request_trace_retention_v1"
_CURSOR_DOMAIN = b"polaris/request-trace/cursor/v1"
_MASTER_KEY_BYTES = 32
_RETENTION_PRUNE_INTERVAL_SECONDS = 60.0
_RETENTION_PRUNE_RECORD_INTERVAL = 256
_current_collector: ContextVar[RequestTraceCollector | None] = ContextVar(
    "request_trace_collector", default=None
)


def _encode_key(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _decode_key(value: Any) -> bytes:
    if not isinstance(value, str):
        raise RuntimeError("Stored request trace master key is invalid.")
    try:
        decoded = base64.b64decode(value, altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Stored request trace master key is invalid.") from exc
    if len(decoded) != _MASTER_KEY_BYTES or _encode_key(decoded) != value:
        raise RuntimeError("Stored request trace master key is invalid.")
    return decoded


def _decode_retention(value: Any) -> RequestTraceRetentionPolicy:
    if value is None:
        return RequestTraceRetentionPolicy()
    if not isinstance(value, dict) or set(value) != {"retention_days", "max_traces"}:
        raise RuntimeError("Stored request trace retention policy is invalid.")
    if type(value["retention_days"]) is not int or type(value["max_traces"]) is not int:
        raise RuntimeError("Stored request trace retention policy is invalid.")
    try:
        return RequestTraceRetentionPolicy(**value)
    except ValueError as exc:
        raise RuntimeError("Stored request trace retention policy is invalid.") from exc


def _outcome_for_status(status_code: int, decisions: tuple[RequestDecision, ...]) -> str:
    upstream_decisions = tuple(
        decision for decision in decisions if decision.category == "upstream"
    )
    # A failed attempt followed by a successful retry/failover is a successful
    # logical request. Conversely, a streaming response can have already sent a
    # 2xx status before its only upstream attempt fails, so status alone is not
    # sufficient for classifying the final outcome.
    if status_code < 400:
        if upstream_decisions and not any(
            decision.result == "succeeded" for decision in upstream_decisions
        ):
            return "upstream_error"
        return "succeeded"
    if any(decision.result == "failed" for decision in upstream_decisions):
        return "upstream_error"
    if status_code in {401, 403}:
        return "denied"
    if status_code == 429:
        return "rate_limited"
    if status_code in {502, 504}:
        return "upstream_error"
    if status_code == 503:
        return "unavailable"
    if status_code < 500:
        return "client_error"
    return "internal_error"


class RequestTraceCollector:
    """Mutable request-local collector that can only emit the strict domain contract."""

    def __init__(self, request_id: str, protocol: str) -> None:
        self.request_id = request_id
        self.protocol = protocol
        self._started_at = datetime.now(timezone.utc)
        self._started_perf = time.perf_counter()
        self._decisions: list[RequestDecision] = []
        self._truncated = False
        self._requested_model = ""
        self._selected_provider = ""
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost_usd = 0.0
        self.record(
            category="request",
            action="accepted",
            result="succeeded",
            reason="request_received",
        )

    @property
    def decisions(self) -> tuple[RequestDecision, ...]:
        return tuple(self._decisions)

    def record(self, **fields: Any) -> bool:
        if len(self._decisions) >= MAX_TRACE_DECISIONS:
            self._truncated = True
            return False
        decision = RequestDecision(
            sequence=len(self._decisions) + 1,
            elapsed_ms=min(
                86_400_000, max(0, round((time.perf_counter() - self._started_perf) * 1000))
            ),
            **fields,
        )
        self._decisions.append(decision)
        if decision.model and not self._requested_model:
            self._requested_model = decision.model
        if decision.provider:
            self._selected_provider = decision.provider
        if decision.input_tokens or decision.output_tokens or decision.cost_usd:
            self.set_usage(
                input_tokens=decision.input_tokens,
                output_tokens=decision.output_tokens,
                cost_usd=decision.cost_usd,
            )
        return True

    def set_usage(self, *, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        self._input_tokens = max(self._input_tokens, input_tokens)
        self._output_tokens = max(self._output_tokens, output_tokens)
        self._cost_usd = max(self._cost_usd, cost_usd)

    def complete(self, *, status_code: int, cancelled: bool = False) -> RequestTrace:
        outcome = "cancelled" if cancelled else _outcome_for_status(status_code, self.decisions)
        reason = (
            "cancelled"
            if cancelled
            else "completed"
            if outcome == "succeeded"
            else "client_error"
            if outcome in {"client_error", "denied"}
            else "rate_limited"
            if outcome == "rate_limited"
            else "provider_error"
            if outcome == "upstream_error"
            else "server_error"
        )
        self.record(
            category="outcome",
            action="cancelled" if cancelled else "completed",
            result="succeeded" if outcome == "succeeded" else "failed",
            reason=reason,
            status_code=status_code,
        )
        completed_at = datetime.now(timezone.utc)
        duration_ms = min(
            86_400_000,
            max(0, round((time.perf_counter() - self._started_perf) * 1000)),
        )
        return RequestTrace(
            schema_version=REQUEST_TRACE_SCHEMA_VERSION,
            trace_id=uuid.uuid4().hex,
            request_id=self.request_id,
            protocol=self.protocol,
            started_at=self._started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            outcome=outcome,
            status_code=status_code,
            duration_ms=duration_ms,
            requested_model=self._requested_model,
            selected_provider=self._selected_provider,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            total_tokens=self._input_tokens + self._output_tokens,
            cost_usd=self._cost_usd,
            decisions=self.decisions,
            decisions_truncated=self._truncated,
        )


@contextmanager
def request_trace_scope(request_id: str, protocol: str) -> Iterator[RequestTraceCollector]:
    collector = RequestTraceCollector(request_id, protocol)
    token: Token[RequestTraceCollector | None] = _current_collector.set(collector)
    try:
        yield collector
    finally:
        _current_collector.reset(token)


def get_request_trace_collector() -> RequestTraceCollector | None:
    return _current_collector.get()


@contextmanager
def bind_request_trace_collector(
    collector: RequestTraceCollector | None,
) -> Iterator[None]:
    """Restore a captured collector while a deferred streaming body executes."""
    token: Token[RequestTraceCollector | None] = _current_collector.set(collector)
    try:
        yield
    finally:
        _current_collector.reset(token)


def trace_decision(**fields: Any) -> bool:
    """Best-effort instrumentation that can never change request behavior."""
    collector = get_request_trace_collector()
    if collector is None:
        return False
    try:
        return collector.record(**fields)
    except (TypeError, ValueError):
        return False


class RequestTraceService:
    def __init__(
        self,
        repository: Any,
        *,
        storage: Any,
        retention_policy: RequestTraceRetentionPolicy,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._retention_policy = retention_policy
        self._retention_lock = asyncio.Lock()
        self._records_since_prune = 0
        self._last_prune_monotonic = 0.0

    @classmethod
    async def create(cls, storage: Any) -> "RequestTraceService":
        retention = _decode_retention(
            await storage.get_config(REQUEST_TRACE_RETENTION_CONFIG, None)
        )
        encoded_master = await storage.get_config(REQUEST_TRACE_MASTER_KEY_CONFIG, None)
        if encoded_master is None:
            encoded_master = _encode_key(secrets.token_bytes(_MASTER_KEY_BYTES))
            if not await storage.set_config(REQUEST_TRACE_MASTER_KEY_CONFIG, encoded_master):
                raise RuntimeError("Unable to persist the request trace master key.")
            encoded_master = await storage.get_config(REQUEST_TRACE_MASTER_KEY_CONFIG, None)
        master = _decode_key(encoded_master)
        cursor_key = hmac.new(master, _CURSOR_DOMAIN, hashlib.sha256).digest()
        repository = await storage.create_request_trace_repository(cursor_signing_key=cursor_key)
        return cls(repository, storage=storage, retention_policy=retention)

    @property
    def retention_policy(self) -> RequestTraceRetentionPolicy:
        return self._retention_policy

    async def record(self, trace: RequestTrace) -> None:
        if not isinstance(trace, RequestTrace):
            raise ValueError("A validated RequestTrace is required.")
        # Durable inserts are independent and must not queue behind a global
        # retention scan. One worker amortizes pruning while concurrent writers
        # continue; the bounded record interval also caps burst overshoot.
        await self._repository.append(trace)
        self._records_since_prune += 1
        now_monotonic = time.monotonic()
        due = (
            self._records_since_prune >= _RETENTION_PRUNE_RECORD_INTERVAL
            or now_monotonic - self._last_prune_monotonic >= _RETENTION_PRUNE_INTERVAL_SECONDS
        )
        if not due or self._retention_lock.locked():
            return
        async with self._retention_lock:
            now_monotonic = time.monotonic()
            if (
                self._records_since_prune < _RETENTION_PRUNE_RECORD_INTERVAL
                and now_monotonic - self._last_prune_monotonic < _RETENTION_PRUNE_INTERVAL_SECONDS
            ):
                return
            await self._repository.prune(self._retention_policy, now=datetime.now(timezone.utc))
            self._records_since_prune = 0
            self._last_prune_monotonic = now_monotonic

    async def query(self, query: RequestTraceQuery) -> RequestTracePage:
        if not isinstance(query, RequestTraceQuery):
            raise ValueError("A validated RequestTraceQuery is required.")
        return await self._repository.query(query)

    async def update_retention(
        self,
        policy: RequestTraceRetentionPolicy,
        *,
        now: datetime | None = None,
    ) -> int:
        if not isinstance(policy, RequestTraceRetentionPolicy):
            raise ValueError("A validated RequestTraceRetentionPolicy is required.")
        prune_time = now or datetime.now(timezone.utc)
        if prune_time.tzinfo is None:
            raise ValueError("Request trace prune timestamp must be timezone-aware.")
        record = {"retention_days": policy.retention_days, "max_traces": policy.max_traces}
        async with self._retention_lock:
            if not await self._storage.set_config(REQUEST_TRACE_RETENTION_CONFIG, record):
                raise RuntimeError("Unable to persist the request trace retention policy.")
            self._retention_policy = policy
            removed = await self._repository.prune(policy, now=prune_time.astimezone(timezone.utc))
            self._records_since_prune = 0
            self._last_prune_monotonic = time.monotonic()
            return removed


_request_trace_service: RequestTraceService | None = None
_request_trace_service_lock = asyncio.Lock()


async def initialize_request_trace_service(storage: Any | None = None) -> RequestTraceService:
    global _request_trace_service
    async with _request_trace_service_lock:
        if _request_trace_service is None:
            if storage is None:
                from core.storage_adapter import get_storage_adapter

                storage = await get_storage_adapter()
            _request_trace_service = await RequestTraceService.create(storage)
        return _request_trace_service


def get_request_trace_service() -> RequestTraceService:
    if _request_trace_service is None:
        raise RuntimeError("Request trace service is not initialized.")
    return _request_trace_service


async def close_request_trace_service() -> None:
    global _request_trace_service
    async with _request_trace_service_lock:
        _request_trace_service = None
