"""Shared control-panel authentication policies and response shaping."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import secrets
from typing import Any, Dict

import config
from core.coordination import CoordinationError
from core.security_coordination import (
    AttemptClearRequest,
    AttemptReservationRequest,
    IdentitySecurityCoordinationStore,
    SecurityAttemptCategory,
)
from core.state_store import InMemoryStateStore
from fastapi import HTTPException, Request


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


LOGIN_WINDOW_SECONDS = _env_int("PANEL_LOGIN_WINDOW_SECONDS", 300, 30, 3600)
LOGIN_MAX_ATTEMPTS = _env_int("PANEL_LOGIN_MAX_ATTEMPTS", 10, 3, 100)
LOGIN_MAX_TRACKED_CLIENTS = _env_int("PANEL_LOGIN_MAX_TRACKED_CLIENTS", 10_000, 100, 100_000)
RECOVERY_WINDOW_SECONDS = _env_int("PANEL_RECOVERY_WINDOW_SECONDS", 900, 60, 7200)
RECOVERY_MAX_ATTEMPTS = _env_int("PANEL_RECOVERY_MAX_ATTEMPTS", 5, 3, 20)
RECOVERY_MAX_TRACKED_CLIENTS = _env_int("PANEL_RECOVERY_MAX_TRACKED_CLIENTS", 10_000, 100, 100_000)
OIDC_START_WINDOW_SECONDS = _env_int("OIDC_START_WINDOW_SECONDS", 300, 30, 3600)
OIDC_START_MAX_ATTEMPTS = _env_int("OIDC_START_MAX_ATTEMPTS", 20, 3, 100)
OIDC_START_MAX_TRACKED_CLIENTS = _env_int("OIDC_START_MAX_TRACKED_CLIENTS", 10_000, 100, 100_000)
_ATTEMPT_HMAC_DOMAIN = b"polaris:authentication-attempt-client:v1\0"


class AuthenticationAttemptService:
    """Atomically admit authentication work without retaining raw client identities."""

    def __init__(
        self,
        coordination: IdentitySecurityCoordinationStore,
        *,
        hmac_key: bytes,
        fencing_epoch: int = 1,
    ) -> None:
        if coordination is None or any(
            not callable(getattr(coordination, method, None))
            for method in ("reserve_security_attempt", "clear_security_attempts")
        ):
            raise ValueError("A security coordination store is required.")
        if type(hmac_key) is not bytes or len(hmac_key) < 32:
            raise ValueError("Authentication-attempt HMAC key is invalid.")
        if type(fencing_epoch) is not int or fencing_epoch < 1:
            raise ValueError("Authentication-attempt fencing epoch is invalid.")
        self._coordination = coordination
        self._hmac_key = hmac_key
        self._fencing_epoch = fencing_epoch

    def __repr__(self) -> str:
        return f"AuthenticationAttemptService(fencing_epoch={self._fencing_epoch!r})"

    def _client_index(self, client_identity: str) -> str:
        if type(client_identity) is not str or not client_identity:
            raise ValueError("Authentication client identity is invalid.")
        return hmac.digest(
            self._hmac_key,
            _ATTEMPT_HMAC_DOMAIN + client_identity.encode("utf-8"),
            hashlib.sha256,
        ).hex()

    @staticmethod
    def _operation_id(action: str) -> str:
        return f"auth-{action}-{secrets.token_hex(16)}"

    async def reserve(
        self,
        category: SecurityAttemptCategory,
        client_identity: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> None:
        try:
            decision = await self._coordination.reserve_security_attempt(
                AttemptReservationRequest(
                    category,
                    self._client_index(client_identity),
                    limit,
                    window_seconds,
                    self._fencing_epoch,
                    self._operation_id("reserve"),
                )
            )
        except CoordinationError:
            raise HTTPException(
                status_code=503,
                detail="Authentication admission is unavailable.",
            ) from None
        if decision.allowed:
            return
        if decision.reason == "limited":
            raise HTTPException(
                status_code=429,
                detail="Too many authentication attempts. Please wait before trying again.",
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )
        raise HTTPException(
            status_code=503,
            detail="Authentication admission is unavailable.",
        )

    async def clear(
        self,
        category: SecurityAttemptCategory,
        client_identity: str,
    ) -> None:
        try:
            await self._coordination.clear_security_attempts(
                AttemptClearRequest(
                    category,
                    self._client_index(client_identity),
                    self._fencing_epoch,
                    self._operation_id("clear"),
                )
            )
        except CoordinationError:
            raise HTTPException(
                status_code=503,
                detail="Authentication admission is unavailable.",
            ) from None


def _new_process_local_attempt_service() -> AuthenticationAttemptService:
    return AuthenticationAttemptService(
        InMemoryStateStore(
            _security_attempt_limit_for_testing=min(
                LOGIN_MAX_TRACKED_CLIENTS,
                RECOVERY_MAX_TRACKED_CLIENTS,
                OIDC_START_MAX_TRACKED_CLIENTS,
            )
        ),
        hmac_key=secrets.token_bytes(32),
    )


_attempt_service = _new_process_local_attempt_service()


def set_authentication_attempt_service_for_testing(
    service: AuthenticationAttemptService,
) -> AuthenticationAttemptService:
    """Swap the process-local adapter in tests and return the previous instance."""

    global _attempt_service
    if type(service) is not AuthenticationAttemptService:
        raise ValueError("Authentication-attempt service is invalid.")
    previous = _attempt_service
    _attempt_service = service
    return previous


def configure_authentication_attempt_service(
    service: AuthenticationAttemptService,
) -> None:
    """Bind the lifecycle-owned authentication admission service."""

    global _attempt_service
    if type(service) is not AuthenticationAttemptService:
        raise ValueError("Authentication-attempt service is invalid.")
    _attempt_service = service


def reset_authentication_attempt_service() -> None:
    """Restore a usable process-local service after runtime shutdown."""

    global _attempt_service
    _attempt_service = _new_process_local_attempt_service()


def _client_identity(request: Request) -> str:
    if config.trust_proxy_headers_enabled():
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


async def _assert_login_allowed(client_id: str) -> None:
    await _attempt_service.reserve(
        SecurityAttemptCategory.LOGIN,
        client_id,
        limit=LOGIN_MAX_ATTEMPTS,
        window_seconds=LOGIN_WINDOW_SECONDS,
    )


async def _clear_login_failures(client_id: str) -> None:
    await _attempt_service.clear(SecurityAttemptCategory.LOGIN, client_id)


async def _assert_recovery_allowed(client_id: str) -> None:
    await _attempt_service.reserve(
        SecurityAttemptCategory.RECOVERY,
        client_id,
        limit=RECOVERY_MAX_ATTEMPTS,
        window_seconds=RECOVERY_WINDOW_SECONDS,
    )


async def _clear_recovery_failures(client_id: str) -> None:
    await _attempt_service.clear(SecurityAttemptCategory.RECOVERY, client_id)


async def _assert_and_record_oidc_start(client_id: str) -> None:
    """Bound transaction allocation per client before any IdP network work occurs."""

    await _attempt_service.reserve(
        SecurityAttemptCategory.OIDC_START,
        client_id,
        limit=OIDC_START_MAX_ATTEMPTS,
        window_seconds=OIDC_START_WINDOW_SECONDS,
    )


def recovery_local_only_enabled() -> bool:
    """Return the effective recovery ingress policy without trusting proxy metadata."""

    return os.getenv("PANEL_RECOVERY_LOCAL_ONLY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _assert_recovery_ingress(request: Request) -> None:
    if not recovery_local_only_enabled():
        return
    hostname = (request.url.hostname or "").strip().lower()
    peer = request.client.host if request.client else ""
    try:
        peer_is_loopback = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        peer_is_loopback = False
    if hostname not in {"localhost", "127.0.0.1", "::1"} or not peer_is_loopback:
        raise HTTPException(
            status_code=403,
            detail="Local-owner recovery is restricted to direct loopback access.",
        )


def _credential_result_message(result: Dict[str, Any]) -> str:
    action = result.get("credential_action")
    if action == "replaced":
        return "Authentication completed. The existing credential was renewed with a later expiry."
    if action == "skipped":
        return "Authentication completed, but the credential was not added because the pool already has the same email with an equal or later expiry."
    return "Authentication completed. Credential saved."


def _auth_success_content(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "credentials": result["credentials"],
        "file_path": result["file_path"],
        "message": _credential_result_message(result),
        "auto_detected_project": result.get("auto_detected_project", False),
        "credential_saved": result.get("credential_saved", True),
        "credential_action": result.get("credential_action", "created"),
        "credential_message": result.get("credential_message"),
        "email": result.get("email"),
        "existing_expiry": result.get("existing_expiry"),
        "incoming_expiry": result.get("incoming_expiry"),
        "deleted_duplicates": result.get("deleted_duplicates", []),
    }
