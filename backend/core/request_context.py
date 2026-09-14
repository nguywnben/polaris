"""Request-scoped metadata for safe routing and usage telemetry."""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_request_started_at: ContextVar[float] = ContextVar("request_started_at", default=0.0)
_api_key_id: ContextVar[str] = ContextVar("api_key_id", default="")
_virtual_key_reservation_id: ContextVar[str] = ContextVar("virtual_key_reservation_id", default="")
_key_compression_policy: ContextVar[str] = ContextVar("key_compression_policy", default="inherit")
_request_compression_policy: ContextVar[str] = ContextVar(
    "request_compression_policy", default="inherit"
)
_operation_replay_required: ContextVar[bool] = ContextVar(
    "operation_replay_required", default=False
)


@contextmanager
def request_scope(request_id: str) -> Iterator[None]:
    """Attach a sanitized request ID to work performed in this async context."""
    request_token: Token[str] = _request_id.set(str(request_id or ""))
    start_token: Token[float] = _request_started_at.set(time.perf_counter())
    api_key_token: Token[str] = _api_key_id.set("")
    reservation_token: Token[str] = _virtual_key_reservation_id.set("")
    key_compression_token: Token[str] = _key_compression_policy.set("inherit")
    request_compression_token: Token[str] = _request_compression_policy.set("inherit")
    replay_token: Token[bool] = _operation_replay_required.set(False)
    try:
        yield
    finally:
        _operation_replay_required.reset(replay_token)
        _request_compression_policy.reset(request_compression_token)
        _key_compression_policy.reset(key_compression_token)
        _virtual_key_reservation_id.reset(reservation_token)
        _api_key_id.reset(api_key_token)
        _request_id.reset(request_token)
        _request_started_at.reset(start_token)


def get_request_id() -> str:
    return _request_id.get()


def get_request_elapsed_ms() -> int:
    started_at = _request_started_at.get()
    if not started_at:
        return 0
    return max(0, round((time.perf_counter() - started_at) * 1000))


def set_api_key_id(api_key_id: str) -> None:
    """Attribute the current request to a virtual API key for the ledger."""
    _api_key_id.set(str(api_key_id or ""))


def get_api_key_id() -> str:
    return _api_key_id.get()


def set_virtual_key_reservation_id(reservation_id: str) -> None:
    """Attach the internal quota reservation to the current request context."""
    _virtual_key_reservation_id.set(str(reservation_id or ""))


def get_virtual_key_reservation_id() -> str:
    return _virtual_key_reservation_id.get()


def set_key_compression_policy(policy: str) -> None:
    _key_compression_policy.set(str(policy or "inherit"))


def get_key_compression_policy() -> str:
    return _key_compression_policy.get()


def set_request_compression_policy(policy: str) -> None:
    _request_compression_policy.set(str(policy or "inherit"))


def get_request_compression_policy() -> str:
    return _request_compression_policy.get()


def set_operation_replay_required(required: bool) -> None:
    """Require the request path to return coordinated cached content or fail closed."""

    _operation_replay_required.set(bool(required))


def is_operation_replay_required() -> bool:
    return _operation_replay_required.get()
