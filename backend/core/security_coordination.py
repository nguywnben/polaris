"""Strict opaque identity/security coordination contract for W4.16.

The domain is transport-neutral. Identity adapters own HMAC/encryption codecs;
coordination backends own fencing, atomicity, store time, expiry, and bounds.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from core.coordination import (
    MAX_COORDINATION_INTEGER,
    CoordinationStore,
    validate_epoch,
    validate_operation_id,
)

SECURITY_COORDINATION_SCHEMA_VERSION = 1
MAX_SECURITY_PAYLOAD_BYTES = 8 * 1024
MAX_SECURITY_TIMESTAMP = 2**53 - 1
MIN_SECURITY_SESSION_TTL_SECONDS = 300.0
MAX_SECURITY_SESSION_TTL_SECONDS = 30.0 * 86_400.0
MIN_SECURITY_ATTEMPT_WINDOW_SECONDS = 30.0
MAX_SECURITY_ATTEMPT_WINDOW_SECONDS = 7_200.0
MAX_SECURITY_ATTEMPT_LIMIT = 1_000
MIN_OIDC_TRANSACTION_TTL_SECONDS = 60.0
MAX_OIDC_TRANSACTION_TTL_SECONDS = 900.0
MAX_SECURITY_PAGE_SIZE = 1_000

_HMAC_INDEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SESSION_REFERENCE_PATTERN = re.compile(r"^ssr_[0-9a-f]{32}$")


class SecurityPrincipalType(StrEnum):
    LOCAL_OWNER = "local_owner"
    OIDC_USER = "oidc_user"


class SecurityAttemptCategory(StrEnum):
    LOGIN = "login"
    RECOVERY = "recovery"
    OIDC_START = "oidc_start"


class SessionRevokeTarget(StrEnum):
    DIGEST = "digest"
    REFERENCE = "reference"
    PRINCIPAL = "principal"
    PRINCIPAL_TYPE = "principal_type"


def _strict_int(value: object, label: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} is invalid.")
    return value


def _strict_float(value: object, label: str, *, minimum: float, maximum: float) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{label} is invalid.")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{label} is invalid.")
    return number


def _hmac_index(value: object, label: str) -> str:
    if type(value) is not str or not _HMAC_INDEX_PATTERN.fullmatch(value):
        raise ValueError(f"{label} is invalid.")
    return value


def _session_reference(value: object) -> str:
    if type(value) is not str or not _SESSION_REFERENCE_PATTERN.fullmatch(value):
        raise ValueError("Session reference is invalid.")
    return value


def _payload(value: object, label: str) -> bytes:
    if type(value) is not bytes or not 1 <= len(value) <= MAX_SECURITY_PAYLOAD_BYTES:
        raise ValueError(f"{label} is invalid.")
    return value


def _session_ttls(idle: object, absolute: object) -> tuple[float, float]:
    idle_value = _strict_float(
        idle,
        "Session idle lifetime",
        minimum=MIN_SECURITY_SESSION_TTL_SECONDS,
        maximum=MAX_SECURITY_SESSION_TTL_SECONDS,
    )
    absolute_value = _strict_float(
        absolute,
        "Session absolute lifetime",
        minimum=MIN_SECURITY_SESSION_TTL_SECONDS,
        maximum=MAX_SECURITY_SESSION_TTL_SECONDS,
    )
    if absolute_value <= idle_value:
        raise ValueError("Session absolute lifetime must exceed its idle lifetime.")
    return idle_value, absolute_value


@dataclass(frozen=True, slots=True)
class SessionIssueRequest:
    session_digest: str = field(repr=False)
    session_reference: str
    principal_index: str = field(repr=False)
    principal_type: SecurityPrincipalType
    payload: bytes = field(repr=False)
    idle_ttl_seconds: float
    absolute_ttl_seconds: float
    fencing_epoch: int
    operation_id: str = field(repr=False)

    def __post_init__(self) -> None:
        _hmac_index(self.session_digest, "Session digest")
        _session_reference(self.session_reference)
        _hmac_index(self.principal_index, "Principal index")
        if type(self.principal_type) is not SecurityPrincipalType:
            raise ValueError("Security principal type is invalid.")
        _payload(self.payload, "Session payload")
        _session_ttls(self.idle_ttl_seconds, self.absolute_ttl_seconds)
        validate_epoch(self.fencing_epoch)
        validate_operation_id(self.operation_id)


@dataclass(frozen=True, slots=True)
class SecuritySessionState:
    session_digest: str = field(repr=False)
    session_reference: str
    principal_index: str = field(repr=False)
    principal_type: SecurityPrincipalType
    payload: bytes = field(repr=False)
    issued_at: float
    last_seen_at: float
    idle_expires_at: float
    absolute_expires_at: float

    def __post_init__(self) -> None:
        _hmac_index(self.session_digest, "Session digest")
        _session_reference(self.session_reference)
        _hmac_index(self.principal_index, "Principal index")
        if type(self.principal_type) is not SecurityPrincipalType:
            raise ValueError("Security principal type is invalid.")
        _payload(self.payload, "Session payload")
        issued_at = _strict_float(
            self.issued_at, "Session issue timestamp", minimum=0.0, maximum=MAX_SECURITY_TIMESTAMP
        )
        last_seen_at = _strict_float(
            self.last_seen_at,
            "Session last-seen timestamp",
            minimum=0.0,
            maximum=MAX_SECURITY_TIMESTAMP,
        )
        idle_expires_at = _strict_float(
            self.idle_expires_at,
            "Session idle expiry",
            minimum=0.0,
            maximum=MAX_SECURITY_TIMESTAMP,
        )
        absolute_expires_at = _strict_float(
            self.absolute_expires_at,
            "Session absolute expiry",
            minimum=0.0,
            maximum=MAX_SECURITY_TIMESTAMP,
        )
        if not (
            issued_at <= last_seen_at < idle_expires_at <= absolute_expires_at
            and issued_at < absolute_expires_at
        ):
            raise ValueError("Session timestamps are inconsistent.")


_SESSION_MUTATION_DENIALS = frozenset(
    {"not_found", "conflict", "capacity", "stale_epoch", "reconciling", "reconciliation_required"}
)


@dataclass(frozen=True, slots=True)
class SessionMutationResult:
    applied: bool
    session: SecuritySessionState | None
    reason: str = ""
    idempotent: bool = False

    def __post_init__(self) -> None:
        if type(self.applied) is not bool or type(self.idempotent) is not bool:
            raise ValueError("Session mutation result is invalid.")
        if self.applied:
            if type(self.session) is not SecuritySessionState or self.reason:
                raise ValueError("Session mutation result is invalid.")
        elif self.session is not None or self.reason not in _SESSION_MUTATION_DENIALS:
            raise ValueError("Session mutation result is invalid.")


@dataclass(frozen=True, slots=True)
class SessionResolveRequest:
    session_digest: str = field(repr=False)
    idle_ttl_seconds: float
    fencing_epoch: int
    operation_id: str = field(repr=False)

    def __post_init__(self) -> None:
        _hmac_index(self.session_digest, "Session digest")
        _strict_float(
            self.idle_ttl_seconds,
            "Session idle lifetime",
            minimum=MIN_SECURITY_SESSION_TTL_SECONDS,
            maximum=MAX_SECURITY_SESSION_TTL_SECONDS,
        )
        validate_epoch(self.fencing_epoch)
        validate_operation_id(self.operation_id)


_SESSION_RESOLVE_DENIALS = frozenset(
    {"not_found", "expired", "stale_epoch", "reconciling", "reconciliation_required"}
)


@dataclass(frozen=True, slots=True)
class SessionResolveResult:
    resolved: bool
    session: SecuritySessionState | None
    reason: str = ""
    idempotent: bool = False

    def __post_init__(self) -> None:
        if type(self.resolved) is not bool or type(self.idempotent) is not bool:
            raise ValueError("Session resolve result is invalid.")
        if self.resolved:
            if type(self.session) is not SecuritySessionState or self.reason:
                raise ValueError("Session resolve result is invalid.")
        elif self.session is not None or self.reason not in _SESSION_RESOLVE_DENIALS:
            raise ValueError("Session resolve result is invalid.")


@dataclass(frozen=True, slots=True)
class SessionRotateRequest:
    current_session_digest: str = field(repr=False)
    replacement: SessionIssueRequest
    fencing_epoch: int
    operation_id: str = field(repr=False)

    def __post_init__(self) -> None:
        _hmac_index(self.current_session_digest, "Session digest")
        if type(self.replacement) is not SessionIssueRequest:
            raise ValueError("Replacement session is invalid.")
        validate_epoch(self.fencing_epoch)
        validate_operation_id(self.operation_id)
        if (
            self.current_session_digest == self.replacement.session_digest
            or self.replacement.fencing_epoch != self.fencing_epoch
            or self.replacement.operation_id != self.operation_id
        ):
            raise ValueError("Session rotation is invalid.")


@dataclass(frozen=True, slots=True)
class SessionRevokeRequest:
    target: SessionRevokeTarget
    target_value: str = field(repr=False)
    fencing_epoch: int
    operation_id: str = field(repr=False)
    replay_ttl_seconds: float = MIN_SECURITY_SESSION_TTL_SECONDS

    def __post_init__(self) -> None:
        if type(self.target) is not SessionRevokeTarget:
            raise ValueError("Session revocation target is invalid.")
        if self.target is SessionRevokeTarget.REFERENCE:
            _session_reference(self.target_value)
        elif self.target is SessionRevokeTarget.PRINCIPAL_TYPE:
            try:
                SecurityPrincipalType(self.target_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("Session revocation target is invalid.") from exc
        else:
            _hmac_index(self.target_value, "Session revocation target")
        validate_epoch(self.fencing_epoch)
        validate_operation_id(self.operation_id)
        _strict_float(
            self.replay_ttl_seconds,
            "Session replay lifetime",
            minimum=1.0,
            maximum=MAX_SECURITY_SESSION_TTL_SECONDS,
        )


@dataclass(frozen=True, slots=True)
class SessionRevokeResult:
    revoked_count: int
    idempotent: bool = False

    def __post_init__(self) -> None:
        _strict_int(
            self.revoked_count,
            "Revoked session count",
            minimum=0,
            maximum=MAX_COORDINATION_INTEGER,
        )
        if type(self.idempotent) is not bool:
            raise ValueError("Session revocation result is invalid.")


@dataclass(frozen=True, slots=True)
class SessionListRequest:
    limit: int
    fencing_epoch: int
    after_reference: str | None = None

    def __post_init__(self) -> None:
        _strict_int(self.limit, "Session page size", minimum=1, maximum=MAX_SECURITY_PAGE_SIZE)
        validate_epoch(self.fencing_epoch)
        if self.after_reference is not None:
            _session_reference(self.after_reference)


@dataclass(frozen=True, slots=True)
class SessionPage:
    sessions: tuple[SecuritySessionState, ...]
    next_reference: str | None

    def __post_init__(self) -> None:
        if type(self.sessions) is not tuple or any(
            type(session) is not SecuritySessionState for session in self.sessions
        ):
            raise ValueError("Session page is invalid.")
        references = [session.session_reference for session in self.sessions]
        if references != sorted(set(references)):
            raise ValueError("Session page is invalid.")
        if self.next_reference is not None:
            _session_reference(self.next_reference)
            if not references or self.next_reference <= references[-1]:
                raise ValueError("Session page is invalid.")


@dataclass(frozen=True, slots=True)
class SessionReconciliationSnapshot:
    active_count: int
    digest: str

    def __post_init__(self) -> None:
        _strict_int(
            self.active_count,
            "Session reconciliation count",
            minimum=0,
            maximum=MAX_COORDINATION_INTEGER,
        )
        if type(self.digest) is not str or not _HMAC_INDEX_PATTERN.fullmatch(self.digest):
            raise ValueError("Session reconciliation digest is invalid.")


@dataclass(frozen=True, slots=True)
class AttemptReservationRequest:
    category: SecurityAttemptCategory
    client_index: str = field(repr=False)
    limit: int
    window_seconds: float
    fencing_epoch: int
    operation_id: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.category) is not SecurityAttemptCategory:
            raise ValueError("Security attempt category is invalid.")
        _hmac_index(self.client_index, "Security client index")
        _strict_int(
            self.limit, "Security attempt limit", minimum=1, maximum=MAX_SECURITY_ATTEMPT_LIMIT
        )
        _strict_float(
            self.window_seconds,
            "Security attempt window",
            minimum=MIN_SECURITY_ATTEMPT_WINDOW_SECONDS,
            maximum=MAX_SECURITY_ATTEMPT_WINDOW_SECONDS,
        )
        validate_epoch(self.fencing_epoch)
        validate_operation_id(self.operation_id)


_ATTEMPT_DENIALS = frozenset(
    {"limited", "capacity", "stale_epoch", "reconciling", "reconciliation_required"}
)


@dataclass(frozen=True, slots=True)
class AttemptReservationDecision:
    allowed: bool
    remaining_attempts: int
    retry_after_seconds: int
    reason: str = ""
    idempotent: bool = False

    def __post_init__(self) -> None:
        if type(self.allowed) is not bool or type(self.idempotent) is not bool:
            raise ValueError("Security attempt decision is invalid.")
        remaining = _strict_int(
            self.remaining_attempts,
            "Remaining attempts",
            minimum=0,
            maximum=MAX_SECURITY_ATTEMPT_LIMIT,
        )
        retry_after = _strict_int(
            self.retry_after_seconds,
            "Retry-after",
            minimum=0,
            maximum=MAX_COORDINATION_INTEGER,
        )
        if self.allowed:
            if self.reason or retry_after:
                raise ValueError("Security attempt decision is invalid.")
        elif (
            self.reason not in _ATTEMPT_DENIALS
            or remaining != 0
            or ((self.reason == "limited") != (retry_after > 0))
        ):
            raise ValueError("Security attempt decision is invalid.")


@dataclass(frozen=True, slots=True)
class AttemptClearRequest:
    category: SecurityAttemptCategory
    client_index: str = field(repr=False)
    fencing_epoch: int
    operation_id: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.category) is not SecurityAttemptCategory:
            raise ValueError("Security attempt category is invalid.")
        _hmac_index(self.client_index, "Security client index")
        validate_epoch(self.fencing_epoch)
        validate_operation_id(self.operation_id)


@dataclass(frozen=True, slots=True)
class AttemptClearResult:
    cleared: bool
    idempotent: bool = False

    def __post_init__(self) -> None:
        if type(self.cleared) is not bool or type(self.idempotent) is not bool:
            raise ValueError("Security attempt clear result is invalid.")


@dataclass(frozen=True, slots=True)
class OidcTransactionCreateRequest:
    state_index: str = field(repr=False)
    browser_index: str = field(repr=False)
    payload: bytes = field(repr=False)
    ttl_seconds: float
    fencing_epoch: int
    operation_id: str = field(repr=False)

    def __post_init__(self) -> None:
        _hmac_index(self.state_index, "OIDC state index")
        _hmac_index(self.browser_index, "OIDC browser index")
        if self.state_index == self.browser_index:
            raise ValueError("OIDC transaction indexes are invalid.")
        _payload(self.payload, "OIDC transaction payload")
        _strict_float(
            self.ttl_seconds,
            "OIDC transaction lifetime",
            minimum=MIN_OIDC_TRANSACTION_TTL_SECONDS,
            maximum=MAX_OIDC_TRANSACTION_TTL_SECONDS,
        )
        validate_epoch(self.fencing_epoch)
        validate_operation_id(self.operation_id)


_TRANSACTION_CREATE_DENIALS = frozenset(
    {"conflict", "capacity", "stale_epoch", "reconciling", "reconciliation_required"}
)


@dataclass(frozen=True, slots=True)
class TransactionCreateResult:
    applied: bool
    reason: str = ""
    idempotent: bool = False

    def __post_init__(self) -> None:
        if type(self.applied) is not bool or type(self.idempotent) is not bool:
            raise ValueError("OIDC transaction create result is invalid.")
        if (self.applied and self.reason) or (
            not self.applied and self.reason not in _TRANSACTION_CREATE_DENIALS
        ):
            raise ValueError("OIDC transaction create result is invalid.")


@dataclass(frozen=True, slots=True)
class OidcTransactionConsumeRequest:
    state_index: str = field(repr=False)
    browser_index: str = field(repr=False)
    fencing_epoch: int
    operation_id: str = field(repr=False)

    def __post_init__(self) -> None:
        _hmac_index(self.state_index, "OIDC state index")
        _hmac_index(self.browser_index, "OIDC browser index")
        validate_epoch(self.fencing_epoch)
        validate_operation_id(self.operation_id)


_TRANSACTION_CONSUME_DENIALS = frozenset(
    {
        "not_found",
        "expired",
        "browser_mismatch",
        "stale_epoch",
        "reconciling",
        "reconciliation_required",
    }
)


@dataclass(frozen=True, slots=True)
class OidcTransactionConsumeResult:
    consumed: bool
    payload: bytes | None = field(default=None, repr=False)
    reason: str = ""
    idempotent: bool = False

    def __post_init__(self) -> None:
        if type(self.consumed) is not bool or type(self.idempotent) is not bool:
            raise ValueError("OIDC transaction consume result is invalid.")
        if self.consumed:
            if self.payload is None or self.reason:
                raise ValueError("OIDC transaction consume result is invalid.")
            _payload(self.payload, "OIDC transaction payload")
        elif self.payload is not None or self.reason not in _TRANSACTION_CONSUME_DENIALS:
            raise ValueError("OIDC transaction consume result is invalid.")


class IdentitySecurityCoordinationStore(CoordinationStore, Protocol):
    """Fenced identity/security operations implemented by every coordination backend."""

    async def issue_security_session(
        self, request: SessionIssueRequest
    ) -> SessionMutationResult: ...

    async def resolve_security_session(
        self, request: SessionResolveRequest
    ) -> SessionResolveResult: ...

    async def rotate_security_session(
        self, request: SessionRotateRequest
    ) -> SessionMutationResult: ...

    async def revoke_security_sessions(
        self, request: SessionRevokeRequest
    ) -> SessionRevokeResult: ...

    async def list_security_sessions(self, request: SessionListRequest) -> SessionPage: ...

    async def read_session_reconciliation(self, *, epoch: int) -> SessionReconciliationSnapshot: ...

    async def reserve_security_attempt(
        self, request: AttemptReservationRequest
    ) -> AttemptReservationDecision: ...

    async def clear_security_attempts(self, request: AttemptClearRequest) -> AttemptClearResult: ...

    async def create_oidc_transaction(
        self, request: OidcTransactionCreateRequest
    ) -> TransactionCreateResult: ...

    async def consume_oidc_transaction(
        self, request: OidcTransactionConsumeRequest
    ) -> OidcTransactionConsumeResult: ...
