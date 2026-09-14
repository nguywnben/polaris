"""Safe, stable diagnostics for bounded provider connection tests."""

from __future__ import annotations

import asyncio
import json
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any, Literal, TypeVar

import httpx

CONNECTION_DIAGNOSTIC_SCHEMA_VERSION = 1
CONNECTION_TEST_TIMEOUT_SECONDS = 30.0
MAX_PROVIDER_ERROR_BODY_CHARS = 32_768

DiagnosticCategory = Literal[
    "credential",
    "permission",
    "quota",
    "rate_limit",
    "network",
    "proxy",
    "tls",
    "upstream",
    "invalid_model",
    "unsupported_operation",
    "timeout",
    "cancelled",
    "internal",
]

_SAFE_PROVIDER_CODES = frozenset(
    {
        "access_denied",
        "api_error",
        "authentication_error",
        "billing_hard_limit_reached",
        "forbidden",
        "insufficient_quota",
        "invalid_api_key",
        "invalid_request_error",
        "model_not_found",
        "not_found",
        "not_found_error",
        "overloaded_error",
        "permission_denied",
        "permission_error",
        "quota_exceeded",
        "rate_limit_error",
        "rate_limit_exceeded",
        "resource_exhausted",
        "server_error",
        "unauthenticated",
        "unavailable",
        "unsupported",
        "unsupported_operation",
    }
)

_CATEGORY_COPY: dict[DiagnosticCategory, tuple[str, str, bool]] = {
    "credential": (
        "The provider rejected this credential.",
        "Check or refresh the credential, then run the test again.",
        False,
    ),
    "permission": (
        "The credential does not have permission to use this provider resource.",
        "Review the provider account, project, and model permissions, then retry.",
        False,
    ),
    "quota": (
        "The provider reports that this account has no available quota.",
        "Review billing or quota for the provider account before retrying.",
        False,
    ),
    "rate_limit": (
        "The provider is temporarily rate limiting this credential.",
        "Wait for the provider limit to reset or use another healthy credential.",
        True,
    ),
    "network": (
        "Polaris could not reach the provider.",
        "Check outbound connectivity, DNS, and the configured provider endpoint.",
        True,
    ),
    "proxy": (
        "The outbound proxy could not connect to the provider.",
        "Check the proxy address, credentials, and network access in Settings.",
        True,
    ),
    "tls": (
        "A secure TLS connection to the provider could not be established.",
        "Check the system clock, CA certificates, proxy inspection, and provider endpoint.",
        False,
    ),
    "upstream": (
        "The provider rejected the test request or returned an upstream error.",
        "Check provider status and account settings, then retry the test.",
        True,
    ),
    "invalid_model": (
        "The selected model is not available from this credential.",
        "Refresh available models and select a model exposed by this credential.",
        False,
    ),
    "unsupported_operation": (
        "This credential variant does not support the requested operation.",
        "Choose an operation supported by this credential variant.",
        False,
    ),
    "timeout": (
        "The provider connection test reached its 30-second limit.",
        "Check provider reachability and proxy settings, then retry.",
        True,
    ),
    "cancelled": (
        "The provider connection test was cancelled.",
        "Run the test again when you are ready.",
        True,
    ),
    "internal": (
        "The provider connection test could not be completed.",
        "Retry once; if the problem continues, review the Polaris logs.",
        True,
    ),
}


@dataclass(frozen=True)
class ProviderConnectionDiagnostic:
    """Public connection-test result with no raw upstream content."""

    code: str
    category: DiagnosticCategory
    message: str
    remediation: str
    retryable: bool
    provider_status: int | None = None
    provider_code: str | None = None
    schema_version: int = CONNECTION_DIAGNOSTIC_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


class ConnectionTestTimedOut(TimeoutError):
    """The complete credential test exceeded its hard deadline."""


class ConnectionTestDisconnected(RuntimeError):
    """The management client disconnected while a credential test was running."""


def connection_diagnostic(
    category: DiagnosticCategory,
    *,
    provider_status: int | None = None,
    provider_code: str | None = None,
) -> ProviderConnectionDiagnostic:
    message, remediation, retryable = _CATEGORY_COPY[category]
    if category == "upstream" and provider_status is not None and provider_status < 500:
        retryable = False
    return ProviderConnectionDiagnostic(
        code=f"provider_connection_{category}",
        category=category,
        message=message,
        remediation=remediation,
        retryable=retryable,
        provider_status=provider_status,
        provider_code=provider_code,
    )


def _safe_provider_code(response_body: object) -> str | None:
    """Extract only a small allowlist of useful provider codes from JSON."""
    payload: Any
    if isinstance(response_body, (bytes, bytearray)):
        if len(response_body) > MAX_PROVIDER_ERROR_BODY_CHARS:
            return None
        try:
            response_body = bytes(response_body).decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(response_body, str):
        if len(response_body) > MAX_PROVIDER_ERROR_BODY_CHARS:
            return None
        try:
            payload = json.loads(response_body)
        except (TypeError, ValueError):
            return None
    elif isinstance(response_body, dict):
        payload = response_body
    else:
        return None

    error = payload.get("error") if isinstance(payload, dict) else None
    candidates: list[object] = []
    if isinstance(error, dict):
        candidates.extend((error.get("code"), error.get("type"), error.get("status")))
    if isinstance(payload, dict):
        candidates.extend((payload.get("code"), payload.get("type"), payload.get("status")))

    for candidate in candidates:
        normalized = str(candidate or "").strip().lower().replace("-", "_")
        if normalized in _SAFE_PROVIDER_CODES:
            return normalized
    return None


def _category_for_status(status_code: int, provider_code: str | None) -> DiagnosticCategory:
    if provider_code in {
        "authentication_error",
        "invalid_api_key",
        "unauthenticated",
    }:
        return "credential"
    if provider_code in {"access_denied", "forbidden", "permission_denied", "permission_error"}:
        return "permission"
    if provider_code in {"billing_hard_limit_reached", "insufficient_quota", "quota_exceeded"}:
        return "quota"
    if provider_code in {"rate_limit_error", "rate_limit_exceeded"}:
        return "rate_limit"
    if provider_code in {"model_not_found", "not_found", "not_found_error"}:
        return "invalid_model"
    if provider_code in {"unsupported", "unsupported_operation"}:
        return "unsupported_operation"
    if status_code == 401:
        return "credential"
    if status_code == 403:
        return "permission"
    if status_code == 402:
        return "quota"
    if status_code == 429:
        return "rate_limit"
    if status_code == 404:
        return "invalid_model"
    if status_code in {405, 501}:
        return "unsupported_operation"
    if status_code in {408, 504}:
        return "timeout"
    return "upstream"


def classify_provider_response(
    status_code: int,
    response_body: object = None,
) -> ProviderConnectionDiagnostic:
    """Normalize one provider HTTP failure without returning its response body."""
    bounded_status = status_code if 100 <= status_code <= 599 else 502
    provider_code = _safe_provider_code(response_body)
    category = _category_for_status(bounded_status, provider_code)
    return connection_diagnostic(
        category,
        provider_status=bounded_status,
        provider_code=provider_code,
    )


def _exception_chain(error: BaseException) -> list[BaseException]:
    values: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in values and len(values) < 8:
        values.append(current)
        current = current.__cause__ or current.__context__
    return values


def classify_provider_exception(error: BaseException) -> ProviderConnectionDiagnostic:
    """Normalize transport/provider exceptions without exposing exception text."""
    chain = _exception_chain(error)
    if any(isinstance(item, httpx.ProxyError) for item in chain):
        return connection_diagnostic("proxy")
    if any(isinstance(item, ssl.SSLError) for item in chain):
        return connection_diagnostic("tls")
    if any(isinstance(item, (httpx.TimeoutException, TimeoutError)) for item in chain):
        return connection_diagnostic("timeout")
    if any(isinstance(item, (httpx.NetworkError, OSError)) for item in chain):
        return connection_diagnostic("network")

    raw_status = getattr(error, "status_code", None)
    if isinstance(raw_status, int):
        return classify_provider_response(raw_status)
    if isinstance(error, ValueError):
        return connection_diagnostic("credential", provider_status=400)
    return connection_diagnostic("internal")


def build_connection_test_failure(
    diagnostic: ProviderConnectionDiagnostic,
    *,
    filename: str,
    provider: str = "",
    credential_type: object = None,
    model: str = "",
    status_code: int | None = None,
) -> dict[str, Any]:
    """Build an additive response that retains the legacy string error fields."""
    payload: dict[str, Any] = {
        "success": False,
        "status_code": status_code
        or diagnostic.provider_status
        or _http_status(diagnostic.category),
        "message": "Model test failed.",
        "error": diagnostic.message,
        "detail": diagnostic.message,
        "diagnostic": diagnostic.as_dict(),
        "filename": filename,
    }
    if provider:
        payload["provider"] = provider
    if credential_type:
        payload["credential_type"] = credential_type
    if model:
        payload["model"] = model
    return payload


def _http_status(category: DiagnosticCategory) -> int:
    if category == "timeout":
        return 504
    if category == "cancelled":
        return 499
    if category == "internal":
        return 500
    if category in {"network", "proxy", "tls", "upstream"}:
        return 502
    if category == "unsupported_operation":
        return 422
    return 400


_T = TypeVar("_T")


async def _cancel_task(task: asyncio.Task[Any] | None) -> None:
    if task is None or task.done():
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def _wait_for_disconnect(
    is_disconnected: Callable[[], Awaitable[bool]],
    poll_seconds: float,
) -> None:
    poll = asyncio.Event()
    while not await is_disconnected():
        try:
            await asyncio.wait_for(poll.wait(), timeout=max(0.001, poll_seconds))
        except TimeoutError:
            pass


async def run_bounded_connection_test(
    operation: Awaitable[_T],
    *,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    timeout_seconds: float = CONNECTION_TEST_TIMEOUT_SECONDS,
    disconnect_poll_seconds: float = 0.1,
) -> _T:
    """Run a test under one deadline and cancel it when the client disconnects."""
    operation_task = asyncio.create_task(operation)
    disconnect_task = (
        asyncio.create_task(
            _wait_for_disconnect(is_disconnected, max(0.0, disconnect_poll_seconds))
        )
        if is_disconnected is not None
        else None
    )
    wait_for = {operation_task}
    if disconnect_task is not None:
        wait_for.add(disconnect_task)

    try:
        done, _pending = await asyncio.wait(
            wait_for,
            timeout=max(0.001, min(float(timeout_seconds), CONNECTION_TEST_TIMEOUT_SECONDS)),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if operation_task in done:
            return await operation_task
        await _cancel_task(operation_task)
        if disconnect_task is not None and disconnect_task in done:
            await disconnect_task
            raise ConnectionTestDisconnected()
        raise ConnectionTestTimedOut()
    except asyncio.CancelledError:
        await _cancel_task(operation_task)
        raise
    finally:
        await _cancel_task(disconnect_task)
