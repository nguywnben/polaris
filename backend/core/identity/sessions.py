"""Opaque, revocable management-session contract and standalone implementation."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import time
from collections import Counter
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Protocol

from core.coordination import CoordinationError
from core.identity.authorization import (
    ManagementPrincipal,
    ManagementRole,
    OidcRoleSource,
    PrincipalType,
)
from core.identity.oidc_identity import ResolvedOidcIdentity
from core.identity.repository import LOCAL_OWNER_ID, ManagedIdentity, RoleBindingSource
from core.security_coordination import (
    IdentitySecurityCoordinationStore,
    SecurityPrincipalType,
    SecuritySessionState,
    SessionIssueRequest,
    SessionListRequest,
    SessionResolveRequest,
    SessionRevokeRequest,
    SessionRevokeTarget,
    SessionRotateRequest,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SESSION_SCHEMA_VERSION = 2
SESSION_TOKEN_PREFIX = "ogs_"
SESSION_TOKEN_BYTES = 32
MIN_SESSION_TTL_SECONDS = 300
MAX_SESSION_TTL_SECONDS = 2_592_000
MIN_ACTIVE_SESSIONS = 1
MAX_ACTIVE_SESSIONS = 100_000

_SESSION_TOKEN_PATTERN = re.compile(r"^ogs_[A-Za-z0-9_-]{43}$")
_SESSION_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SESSION_REFERENCE_PATTERN = re.compile(r"^ssr_[0-9a-f]{32}$")
_SESSION_HMAC_DOMAIN = b"polaris:management-session:v1\0"
_SESSION_REFERENCE_DOMAIN = b"polaris:management-session-reference:v1\0"
_SESSION_MASTER_KEY_CONFIG = "_internal_session_master_key_v1"
_SESSION_MASTER_KEY_BYTES = 32
_SESSION_PAYLOAD_AAD = b"polaris:management-session-payload:v1"
_SESSION_PAYLOAD_KEY_DOMAIN = b"polaris:management-session-payload-key:v1\0"
_SESSION_PRINCIPAL_INDEX_DOMAIN = b"polaris:management-session-principal:v1\0"
_SESSION_METRIC_ACTIONS = frozenset({"issue", "resolve", "revoke", "revoke_principal"})
_SESSION_METRIC_OUTCOMES = frozenset({"succeeded", "not_found", "expired", "stale", "failed"})
_session_metric_lock = threading.Lock()
_session_metrics: Counter[tuple[str, str]] = Counter()


class SessionError(RuntimeError):
    """Base error for a session that cannot authorize a request."""


class SessionNotFound(SessionError):
    pass


class SessionExpired(SessionError):
    pass


class SessionStale(SessionError):
    pass


class SessionAuthenticationMethod(StrEnum):
    LOCAL_PASSWORD = "local_password"
    OIDC = "oidc"


def _record_session_metric(action: str, outcome: str) -> None:
    if action not in _SESSION_METRIC_ACTIONS or outcome not in _SESSION_METRIC_OUTCOMES:
        raise ValueError("Session metric dimensions are invalid.")
    with _session_metric_lock:
        _session_metrics[(action, outcome)] += 1


def render_management_session_metrics() -> str:
    """Render only closed low-cardinality management-session outcomes."""
    with _session_metric_lock:
        snapshot = dict(_session_metrics)
    lines = [
        "# HELP polaris_management_session_operations_total Management session lifecycle outcomes.",
        "# TYPE polaris_management_session_operations_total counter",
    ]
    for (action, outcome), count in sorted(snapshot.items()):
        lines.append(
            "polaris_management_session_operations_total"
            f'{{action="{action}",outcome="{outcome}"}} {count}'
        )
    return "\n".join(lines) + "\n"


def _strict_timestamp(value: object, label: str) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{label} is invalid.")
    timestamp = float(value)
    if not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError(f"{label} is invalid.")
    return timestamp


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    idle_ttl_seconds: int
    absolute_ttl_seconds: int
    max_active_sessions: int = 10_000

    def __post_init__(self) -> None:
        if type(self.idle_ttl_seconds) is not int or not (
            MIN_SESSION_TTL_SECONDS <= self.idle_ttl_seconds <= MAX_SESSION_TTL_SECONDS
        ):
            raise ValueError("Session idle lifetime is invalid.")
        if type(self.absolute_ttl_seconds) is not int or not (
            MIN_SESSION_TTL_SECONDS <= self.absolute_ttl_seconds <= MAX_SESSION_TTL_SECONDS
        ):
            raise ValueError("Session absolute lifetime is invalid.")
        if self.absolute_ttl_seconds <= self.idle_ttl_seconds:
            raise ValueError("Session absolute lifetime must exceed its idle lifetime.")
        if type(self.max_active_sessions) is not int or not (
            MIN_ACTIVE_SESSIONS <= self.max_active_sessions <= MAX_ACTIVE_SESSIONS
        ):
            raise ValueError("Session capacity is invalid.")


@dataclass(frozen=True, slots=True)
class SessionRecord:
    schema_version: int
    digest: str
    principal: ManagementPrincipal
    issued_at: float
    last_seen_at: float
    idle_expires_at: float
    absolute_expires_at: float
    authentication_method: SessionAuthenticationMethod
    authorization_epoch: int
    oidc_policy_authorization_epoch: int | None = None

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SESSION_SCHEMA_VERSION:
            raise ValueError("Session schema version is unsupported.")
        if type(self.digest) is not str or not _SESSION_DIGEST_PATTERN.fullmatch(self.digest):
            raise ValueError("Session digest is invalid.")
        if type(self.principal) is not ManagementPrincipal:
            raise ValueError("Session principal is invalid.")
        if type(self.authentication_method) is not SessionAuthenticationMethod:
            raise ValueError("Session authentication method is invalid.")
        if type(self.authorization_epoch) is not int or self.authorization_epoch < 1:
            raise ValueError("Session authorization epoch is invalid.")
        if self.authentication_method is SessionAuthenticationMethod.LOCAL_PASSWORD:
            if (
                self.principal.principal_type is not PrincipalType.LOCAL_OWNER
                or self.oidc_policy_authorization_epoch is not None
            ):
                raise ValueError("Local session authorization snapshot is invalid.")
        elif (
            self.principal.principal_type is not PrincipalType.OIDC_USER
            or type(self.oidc_policy_authorization_epoch) is not int
            or self.oidc_policy_authorization_epoch < 1
        ):
            raise ValueError("OIDC session authorization snapshot is invalid.")
        issued_at = _strict_timestamp(self.issued_at, "Session issue timestamp")
        last_seen_at = _strict_timestamp(self.last_seen_at, "Session last-seen timestamp")
        idle_expires_at = _strict_timestamp(self.idle_expires_at, "Session idle expiry")
        absolute_expires_at = _strict_timestamp(
            self.absolute_expires_at,
            "Session absolute expiry",
        )
        if not (
            issued_at <= last_seen_at < idle_expires_at <= absolute_expires_at
            and issued_at < absolute_expires_at
        ):
            raise ValueError("Session timestamps are inconsistent.")

    def __repr__(self) -> str:
        return (
            "SessionRecord("
            f"schema_version={self.schema_version!r}, principal={self.principal!r}, "
            f"issued_at={self.issued_at!r}, last_seen_at={self.last_seen_at!r}, "
            f"idle_expires_at={self.idle_expires_at!r}, "
            f"absolute_expires_at={self.absolute_expires_at!r}, "
            f"authentication_method={self.authentication_method!r}, "
            f"authorization_epoch={self.authorization_epoch!r}, "
            "oidc_policy_authorization_epoch="
            f"{self.oidc_policy_authorization_epoch!r})"
        )


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    session: SessionRecord

    def __repr__(self) -> str:
        return f"IssuedSession(token='<redacted>', session={self.session!r})"


@dataclass(frozen=True, slots=True)
class ManagedSession:
    """A non-secret management view that can be used for bounded revocation."""

    reference: str
    principal: ManagementPrincipal
    issued_at: float
    last_seen_at: float
    idle_expires_at: float
    absolute_expires_at: float
    authentication_method: SessionAuthenticationMethod

    def __post_init__(self) -> None:
        if not _SESSION_REFERENCE_PATTERN.fullmatch(self.reference):
            raise ValueError("Session reference is invalid.")
        if type(self.principal) is not ManagementPrincipal:
            raise ValueError("Session principal is invalid.")
        if type(self.authentication_method) is not SessionAuthenticationMethod:
            raise ValueError("Session authentication method is invalid.")
        _strict_timestamp(self.issued_at, "Session issue timestamp")
        _strict_timestamp(self.last_seen_at, "Session last-seen timestamp")
        _strict_timestamp(self.idle_expires_at, "Session idle expiry")
        _strict_timestamp(self.absolute_expires_at, "Session absolute expiry")


class SessionStore(Protocol):
    async def issue(
        self,
        *,
        principal: ManagementPrincipal,
        authentication_method: SessionAuthenticationMethod,
        authorization_epoch: int,
        oidc_policy_authorization_epoch: int | None = None,
        now: float,
    ) -> IssuedSession: ...

    async def resolve(
        self,
        token: str,
        *,
        current_authorization_epoch: int,
        current_oidc_policy_authorization_epoch: int | None = None,
        now: float,
    ) -> SessionRecord: ...

    async def inspect(self, token: str, *, now: float) -> SessionRecord: ...

    async def rotate(
        self,
        token: str,
        *,
        principal: ManagementPrincipal,
        authentication_method: SessionAuthenticationMethod,
        authorization_epoch: int,
        oidc_policy_authorization_epoch: int | None = None,
        now: float,
    ) -> IssuedSession: ...

    async def revoke(self, token: str) -> bool: ...

    async def revoke_principal(self, principal: ManagementPrincipal) -> int: ...

    async def revoke_principal_type(self, principal_type: PrincipalType) -> int: ...

    async def list_active(
        self,
        *,
        limit: int,
        now: float,
        after_reference: str | None = None,
    ) -> list[ManagedSession]: ...

    async def reference_for_token(self, token: str, *, now: float) -> str: ...

    async def managed_for_token(self, token: str, *, now: float) -> ManagedSession: ...

    async def revoke_reference(self, reference: str) -> bool: ...


class InProcessSessionStore:
    """Atomic single-process store that never retains a plaintext session token."""

    def __init__(self, *, hmac_key: bytes, policy: SessionPolicy) -> None:
        if type(hmac_key) is not bytes or len(hmac_key) < 32:
            raise ValueError("Session HMAC key must contain at least 32 bytes.")
        if type(policy) is not SessionPolicy:
            raise ValueError("A validated session policy is required.")
        self._hmac_key = hmac_key
        self._policy = policy
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = asyncio.Lock()

    def __repr__(self) -> str:
        return (
            "InProcessSessionStore("
            f"policy={self._policy!r}, active_sessions={len(self._sessions)!r})"
        )

    def _digest(self, token: str) -> str:
        return hmac.digest(
            self._hmac_key,
            _SESSION_HMAC_DOMAIN + token.encode("ascii"),
            hashlib.sha256,
        ).hex()

    def _reference(self, digest: str) -> str:
        return (
            "ssr_"
            + hmac.digest(
                self._hmac_key,
                _SESSION_REFERENCE_DOMAIN + digest.encode("ascii"),
                hashlib.sha256,
            ).hex()[:32]
        )

    @staticmethod
    def _managed_session(reference: str, record: SessionRecord) -> ManagedSession:
        return ManagedSession(
            reference=reference,
            principal=record.principal,
            issued_at=record.issued_at,
            last_seen_at=record.last_seen_at,
            idle_expires_at=record.idle_expires_at,
            absolute_expires_at=record.absolute_expires_at,
            authentication_method=record.authentication_method,
        )

    @staticmethod
    def _validated_token(token: object) -> str:
        if type(token) is not str or not _SESSION_TOKEN_PATTERN.fullmatch(token):
            raise SessionNotFound("Session is unavailable.")
        return token

    @staticmethod
    def _validated_issue_inputs(
        principal: object,
        authentication_method: object,
        authorization_epoch: object,
        oidc_policy_authorization_epoch: object,
        now: object,
    ) -> tuple[ManagementPrincipal, SessionAuthenticationMethod, int, int | None, float]:
        if type(principal) is not ManagementPrincipal:
            raise ValueError("A validated session principal is required.")
        if type(authentication_method) is not SessionAuthenticationMethod:
            raise ValueError("A validated session authentication method is required.")
        if type(authorization_epoch) is not int or authorization_epoch < 1:
            raise ValueError("Session authorization epoch is invalid.")
        if authentication_method is SessionAuthenticationMethod.LOCAL_PASSWORD:
            if (
                principal.principal_type is not PrincipalType.LOCAL_OWNER
                or oidc_policy_authorization_epoch is not None
            ):
                raise ValueError("Local session authorization snapshot is invalid.")
        elif (
            principal.principal_type is not PrincipalType.OIDC_USER
            or type(oidc_policy_authorization_epoch) is not int
            or oidc_policy_authorization_epoch < 1
        ):
            raise ValueError("OIDC session authorization snapshot is invalid.")
        return (
            principal,
            authentication_method,
            authorization_epoch,
            oidc_policy_authorization_epoch,
            _strict_timestamp(now, "Session timestamp"),
        )

    def _issue_locked(
        self,
        *,
        principal: ManagementPrincipal,
        authentication_method: SessionAuthenticationMethod,
        authorization_epoch: int,
        oidc_policy_authorization_epoch: int | None,
        now: float,
    ) -> IssuedSession:
        expired = [
            digest
            for digest, record in self._sessions.items()
            if now >= record.idle_expires_at or now >= record.absolute_expires_at
        ]
        for digest in expired:
            self._sessions.pop(digest, None)
        while len(self._sessions) >= self._policy.max_active_sessions:
            least_recent_digest = min(
                self._sessions,
                key=lambda digest: (
                    self._sessions[digest].last_seen_at,
                    self._sessions[digest].issued_at,
                    digest,
                ),
            )
            self._sessions.pop(least_recent_digest, None)
        for _attempt in range(4):
            token = SESSION_TOKEN_PREFIX + secrets.token_urlsafe(SESSION_TOKEN_BYTES)
            digest = self._digest(token)
            if digest not in self._sessions:
                break
        else:
            raise RuntimeError("Unable to allocate a unique session.")
        absolute_expires_at = now + self._policy.absolute_ttl_seconds
        record = SessionRecord(
            schema_version=SESSION_SCHEMA_VERSION,
            digest=digest,
            principal=principal,
            issued_at=now,
            last_seen_at=now,
            idle_expires_at=min(
                now + self._policy.idle_ttl_seconds,
                absolute_expires_at,
            ),
            absolute_expires_at=absolute_expires_at,
            authentication_method=authentication_method,
            authorization_epoch=authorization_epoch,
            oidc_policy_authorization_epoch=oidc_policy_authorization_epoch,
        )
        self._sessions[digest] = record
        return IssuedSession(token=token, session=record)

    def _resolve_locked(
        self,
        token: str,
        *,
        current_authorization_epoch: int | None,
        current_oidc_policy_authorization_epoch: int | None,
        now: float,
        touch: bool,
    ) -> SessionRecord:
        digest = self._digest(token)
        record = self._sessions.get(digest)
        if record is None:
            raise SessionNotFound("Session is unavailable.")
        if now >= record.idle_expires_at or now >= record.absolute_expires_at:
            self._sessions.pop(digest, None)
            raise SessionExpired("Session expired.")
        if (
            current_authorization_epoch is not None
            and current_authorization_epoch != record.authorization_epoch
        ):
            self._sessions.pop(digest, None)
            raise SessionStale("Session authorization is stale.")
        if (
            current_authorization_epoch is not None
            and record.authentication_method is SessionAuthenticationMethod.OIDC
            and current_oidc_policy_authorization_epoch != record.oidc_policy_authorization_epoch
        ):
            self._sessions.pop(digest, None)
            raise SessionStale("Session authorization is stale.")
        if not touch:
            return record
        updated = replace(
            record,
            last_seen_at=now,
            idle_expires_at=min(
                now + self._policy.idle_ttl_seconds,
                record.absolute_expires_at,
            ),
        )
        self._sessions[digest] = updated
        return updated

    async def issue(
        self,
        *,
        principal: ManagementPrincipal,
        authentication_method: SessionAuthenticationMethod,
        authorization_epoch: int,
        oidc_policy_authorization_epoch: int | None = None,
        now: float,
    ) -> IssuedSession:
        (
            principal,
            authentication_method,
            authorization_epoch,
            oidc_policy_authorization_epoch,
            now,
        ) = self._validated_issue_inputs(
            principal,
            authentication_method,
            authorization_epoch,
            oidc_policy_authorization_epoch,
            now,
        )
        async with self._lock:
            return self._issue_locked(
                principal=principal,
                authentication_method=authentication_method,
                authorization_epoch=authorization_epoch,
                oidc_policy_authorization_epoch=oidc_policy_authorization_epoch,
                now=now,
            )

    async def resolve(
        self,
        token: str,
        *,
        current_authorization_epoch: int,
        current_oidc_policy_authorization_epoch: int | None = None,
        now: float,
    ) -> SessionRecord:
        token = self._validated_token(token)
        if type(current_authorization_epoch) is not int or current_authorization_epoch < 1:
            raise ValueError("Session authorization epoch is invalid.")
        if current_oidc_policy_authorization_epoch is not None and (
            type(current_oidc_policy_authorization_epoch) is not int
            or current_oidc_policy_authorization_epoch < 1
        ):
            raise ValueError("OIDC policy authorization epoch is invalid.")
        now = _strict_timestamp(now, "Session timestamp")
        async with self._lock:
            return self._resolve_locked(
                token,
                current_authorization_epoch=current_authorization_epoch,
                current_oidc_policy_authorization_epoch=current_oidc_policy_authorization_epoch,
                now=now,
                touch=True,
            )

    async def inspect(self, token: str, *, now: float) -> SessionRecord:
        token = self._validated_token(token)
        now = _strict_timestamp(now, "Session timestamp")
        async with self._lock:
            return self._resolve_locked(
                token,
                current_authorization_epoch=None,
                current_oidc_policy_authorization_epoch=None,
                now=now,
                touch=False,
            )

    async def rotate(
        self,
        token: str,
        *,
        principal: ManagementPrincipal,
        authentication_method: SessionAuthenticationMethod,
        authorization_epoch: int,
        oidc_policy_authorization_epoch: int | None = None,
        now: float,
    ) -> IssuedSession:
        token = self._validated_token(token)
        (
            principal,
            authentication_method,
            authorization_epoch,
            oidc_policy_authorization_epoch,
            now,
        ) = self._validated_issue_inputs(
            principal,
            authentication_method,
            authorization_epoch,
            oidc_policy_authorization_epoch,
            now,
        )
        async with self._lock:
            existing = self._resolve_locked(
                token,
                current_authorization_epoch=None,
                current_oidc_policy_authorization_epoch=None,
                now=now,
                touch=False,
            )
            self._sessions.pop(existing.digest, None)
            return self._issue_locked(
                principal=principal,
                authentication_method=authentication_method,
                authorization_epoch=authorization_epoch,
                oidc_policy_authorization_epoch=oidc_policy_authorization_epoch,
                now=now,
            )

    async def revoke(self, token: str) -> bool:
        try:
            token = self._validated_token(token)
        except SessionNotFound:
            return False
        async with self._lock:
            return self._sessions.pop(self._digest(token), None) is not None

    async def revoke_principal(self, principal: ManagementPrincipal) -> int:
        if type(principal) is not ManagementPrincipal:
            raise ValueError("A validated session principal is required.")
        async with self._lock:
            digests = [
                digest for digest, record in self._sessions.items() if record.principal == principal
            ]
            for digest in digests:
                self._sessions.pop(digest, None)
            return len(digests)

    async def revoke_principal_type(self, principal_type: PrincipalType) -> int:
        if type(principal_type) is not PrincipalType:
            raise ValueError("A validated principal type is required.")
        async with self._lock:
            digests = [
                digest
                for digest, record in self._sessions.items()
                if record.principal.principal_type is principal_type
            ]
            for digest in digests:
                self._sessions.pop(digest, None)
            return len(digests)

    async def list_active(
        self,
        *,
        limit: int,
        now: float,
        after_reference: str | None = None,
    ) -> list[ManagedSession]:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Session page size is invalid.")
        now = _strict_timestamp(now, "Session timestamp")
        if after_reference is not None and (
            type(after_reference) is not str
            or not _SESSION_REFERENCE_PATTERN.fullmatch(after_reference)
        ):
            raise ValueError("Session cursor is invalid.")
        async with self._lock:
            expired = [
                digest
                for digest, record in self._sessions.items()
                if now >= record.idle_expires_at or now >= record.absolute_expires_at
            ]
            for digest in expired:
                self._sessions.pop(digest, None)
            inventory = sorted(
                (
                    self._reference(digest),
                    record,
                )
                for digest, record in self._sessions.items()
            )
            if after_reference is not None:
                inventory = [item for item in inventory if item[0] > after_reference]
            return [
                self._managed_session(reference, record) for reference, record in inventory[:limit]
            ]

    async def reference_for_token(self, token: str, *, now: float) -> str:
        token = self._validated_token(token)
        now = _strict_timestamp(now, "Session timestamp")
        async with self._lock:
            record = self._resolve_locked(
                token,
                current_authorization_epoch=None,
                current_oidc_policy_authorization_epoch=None,
                now=now,
                touch=False,
            )
            return self._reference(record.digest)

    async def managed_for_token(self, token: str, *, now: float) -> ManagedSession:
        token = self._validated_token(token)
        now = _strict_timestamp(now, "Session timestamp")
        async with self._lock:
            record = self._resolve_locked(
                token,
                current_authorization_epoch=None,
                current_oidc_policy_authorization_epoch=None,
                now=now,
                touch=False,
            )
            return self._managed_session(self._reference(record.digest), record)

    async def revoke_reference(self, reference: str) -> bool:
        if type(reference) is not str or not _SESSION_REFERENCE_PATTERN.fullmatch(reference):
            return False
        async with self._lock:
            digest = next(
                (
                    candidate
                    for candidate in self._sessions
                    if hmac.compare_digest(self._reference(candidate), reference)
                ),
                None,
            )
            if digest is None:
                return False
            self._sessions.pop(digest, None)
            return True


class CoordinatedSessionStore:
    """Authenticated session adapter over the fenced security coordination boundary."""

    def __init__(
        self,
        coordination: IdentitySecurityCoordinationStore,
        *,
        hmac_key: bytes,
        policy: SessionPolicy,
        fencing_epoch: int = 1,
    ) -> None:
        if coordination is None or any(
            not callable(getattr(coordination, method, None))
            for method in (
                "issue_security_session",
                "resolve_security_session",
                "rotate_security_session",
                "revoke_security_sessions",
                "list_security_sessions",
            )
        ):
            raise ValueError("A security coordination store is required.")
        if type(hmac_key) is not bytes or len(hmac_key) < 32:
            raise ValueError("Session HMAC key must contain at least 32 bytes.")
        if type(policy) is not SessionPolicy:
            raise ValueError("A validated session policy is required.")
        if type(fencing_epoch) is not int or fencing_epoch < 1:
            raise ValueError("Session fencing epoch is invalid.")
        self._coordination = coordination
        self._hmac_key = hmac_key
        self._policy = policy
        self._fencing_epoch = fencing_epoch
        self._payload_key = hmac.digest(
            hmac_key,
            _SESSION_PAYLOAD_KEY_DOMAIN,
            hashlib.sha256,
        )

    def __repr__(self) -> str:
        return (
            "CoordinatedSessionStore("
            f"policy={self._policy!r}, fencing_epoch={self._fencing_epoch!r})"
        )

    def _digest(self, token: str) -> str:
        return hmac.digest(
            self._hmac_key,
            _SESSION_HMAC_DOMAIN + token.encode("ascii"),
            hashlib.sha256,
        ).hex()

    def _reference(self, digest: str) -> str:
        return (
            "ssr_"
            + hmac.digest(
                self._hmac_key,
                _SESSION_REFERENCE_DOMAIN + digest.encode("ascii"),
                hashlib.sha256,
            ).hex()[:32]
        )

    def _principal_index(self, principal: ManagementPrincipal) -> str:
        if principal.principal_type is PrincipalType.LOCAL_OWNER:
            identity = f"local_owner\0{principal.principal_id}"
        elif principal.principal_type is PrincipalType.OIDC_USER:
            identity = f"oidc_user\0{principal.issuer}\0{principal.subject}"
        else:
            raise ValueError("Session principal type is invalid.")
        return hmac.digest(
            self._hmac_key,
            _SESSION_PRINCIPAL_INDEX_DOMAIN + identity.encode("utf-8"),
            hashlib.sha256,
        ).hex()

    @staticmethod
    def _security_principal_type(principal_type: PrincipalType) -> SecurityPrincipalType:
        if principal_type is PrincipalType.LOCAL_OWNER:
            return SecurityPrincipalType.LOCAL_OWNER
        if principal_type is PrincipalType.OIDC_USER:
            return SecurityPrincipalType.OIDC_USER
        raise ValueError("Session principal type is invalid.")

    @staticmethod
    def _operation_id(action: str) -> str:
        return f"session-{action}-{secrets.token_hex(16)}"

    @staticmethod
    def _validated_token(token: object) -> str:
        return InProcessSessionStore._validated_token(token)

    @staticmethod
    def _validated_issue_inputs(
        principal: object,
        authentication_method: object,
        authorization_epoch: object,
        oidc_policy_authorization_epoch: object,
        now: object,
    ) -> tuple[ManagementPrincipal, SessionAuthenticationMethod, int, int | None, float]:
        return InProcessSessionStore._validated_issue_inputs(
            principal,
            authentication_method,
            authorization_epoch,
            oidc_policy_authorization_epoch,
            now,
        )

    def _encode_payload(
        self,
        *,
        session_digest: str,
        session_reference: str,
        principal_index: str,
        principal_type: SecurityPrincipalType,
        principal: ManagementPrincipal,
        authentication_method: SessionAuthenticationMethod,
        authorization_epoch: int,
        oidc_policy_authorization_epoch: int | None,
    ) -> bytes:
        body = json.dumps(
            {
                "authentication_method": authentication_method.value,
                "authorization_epoch": authorization_epoch,
                "issuer": principal.issuer,
                "oidc_policy_authorization_epoch": oidc_policy_authorization_epoch,
                "principal_id": principal.principal_id,
                "principal_type": principal.principal_type.value,
                "role": None if principal.role is None else principal.role.value,
                "role_source": (
                    None if principal.role_source is None else principal.role_source.value
                ),
                "schema_version": 1,
                "subject": principal.subject,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        nonce = secrets.token_bytes(12)
        return (
            b"\x01"
            + nonce
            + AESGCM(self._payload_key).encrypt(
                nonce,
                body,
                self._payload_aad(
                    session_digest,
                    session_reference,
                    principal_index,
                    principal_type,
                ),
            )
        )

    @staticmethod
    def _payload_aad(
        session_digest: str,
        session_reference: str,
        principal_index: str,
        principal_type: SecurityPrincipalType,
    ) -> bytes:
        return b"\0".join(
            (
                _SESSION_PAYLOAD_AAD,
                session_digest.encode("ascii"),
                session_reference.encode("ascii"),
                principal_index.encode("ascii"),
                principal_type.value.encode("ascii"),
            )
        )

    def _decode_payload(
        self, state: SecuritySessionState
    ) -> tuple[ManagementPrincipal, SessionAuthenticationMethod, int, int | None]:
        try:
            if len(state.payload) < 30 or state.payload[0] != 1:
                raise ValueError
            nonce = state.payload[1:13]
            plaintext = AESGCM(self._payload_key).decrypt(
                nonce,
                state.payload[13:],
                self._payload_aad(
                    state.session_digest,
                    state.session_reference,
                    state.principal_index,
                    state.principal_type,
                ),
            )
            data = json.loads(plaintext)
            if type(data) is not dict or set(data) != {
                "authentication_method",
                "authorization_epoch",
                "issuer",
                "oidc_policy_authorization_epoch",
                "principal_id",
                "principal_type",
                "role",
                "role_source",
                "schema_version",
                "subject",
            }:
                raise ValueError
            if data["schema_version"] != 1:
                raise ValueError
            principal_type = PrincipalType(data["principal_type"])
            role = None if data["role"] is None else ManagementRole(data["role"])
            role_source = (
                None if data["role_source"] is None else OidcRoleSource(data["role_source"])
            )
            principal = ManagementPrincipal(
                principal_type=principal_type,
                principal_id=data["principal_id"],
                role=role,
                issuer=data["issuer"],
                subject=data["subject"],
                role_source=role_source,
            )
            authentication_method = SessionAuthenticationMethod(data["authentication_method"])
            validated = self._validated_issue_inputs(
                principal,
                authentication_method,
                data["authorization_epoch"],
                data["oidc_policy_authorization_epoch"],
                state.issued_at,
            )
            if self._principal_index(principal) != state.principal_index:
                raise ValueError
            if self._security_principal_type(principal_type) is not state.principal_type:
                raise ValueError
            return validated[:4]
        except Exception as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise SessionNotFound("Session is unavailable.") from None

    def _record(self, state: SecuritySessionState) -> SessionRecord:
        principal, authentication_method, authorization_epoch, policy_epoch = self._decode_payload(
            state
        )
        try:
            return SessionRecord(
                SESSION_SCHEMA_VERSION,
                state.session_digest,
                principal,
                state.issued_at,
                state.last_seen_at,
                state.idle_expires_at,
                state.absolute_expires_at,
                authentication_method,
                authorization_epoch,
                policy_epoch,
            )
        except ValueError:
            raise SessionNotFound("Session is unavailable.") from None

    def _managed(self, state: SecuritySessionState) -> ManagedSession:
        record = self._record(state)
        return ManagedSession(
            state.session_reference,
            record.principal,
            record.issued_at,
            record.last_seen_at,
            record.idle_expires_at,
            record.absolute_expires_at,
            record.authentication_method,
        )

    async def _issue(
        self,
        *,
        principal: ManagementPrincipal,
        authentication_method: SessionAuthenticationMethod,
        authorization_epoch: int,
        oidc_policy_authorization_epoch: int | None,
        current_digest: str | None = None,
    ) -> IssuedSession:
        for _attempt in range(4):
            token = SESSION_TOKEN_PREFIX + secrets.token_urlsafe(SESSION_TOKEN_BYTES)
            digest = self._digest(token)
            reference = self._reference(digest)
            principal_index = self._principal_index(principal)
            principal_type = self._security_principal_type(principal.principal_type)
            payload = self._encode_payload(
                session_digest=digest,
                session_reference=reference,
                principal_index=principal_index,
                principal_type=principal_type,
                principal=principal,
                authentication_method=authentication_method,
                authorization_epoch=authorization_epoch,
                oidc_policy_authorization_epoch=oidc_policy_authorization_epoch,
            )
            issue = SessionIssueRequest(
                digest,
                reference,
                principal_index,
                principal_type,
                payload,
                self._policy.idle_ttl_seconds,
                self._policy.absolute_ttl_seconds,
                self._fencing_epoch,
                self._operation_id("rotate" if current_digest is not None else "issue"),
            )
            if current_digest is None:
                result = await self._coordination.issue_security_session(issue)
            else:
                result = await self._coordination.rotate_security_session(
                    SessionRotateRequest(
                        current_digest,
                        issue,
                        self._fencing_epoch,
                        issue.operation_id,
                    )
                )
            if result.applied and result.session is not None:
                if (
                    result.session.session_digest != digest
                    or result.session.session_reference != reference
                    or result.session.principal_index != principal_index
                    or result.session.principal_type is not principal_type
                    or result.session.payload != payload
                ):
                    raise SessionError("Session is unavailable.")
                return IssuedSession(token, self._record(result.session))
            if result.reason != "conflict" or current_digest is not None:
                break
        if current_digest is not None and result.reason == "not_found":
            raise SessionNotFound("Session is unavailable.")
        raise SessionError("Session is unavailable.")

    async def issue(
        self,
        *,
        principal: ManagementPrincipal,
        authentication_method: SessionAuthenticationMethod,
        authorization_epoch: int,
        oidc_policy_authorization_epoch: int | None = None,
        now: float,
    ) -> IssuedSession:
        principal, authentication_method, authorization_epoch, policy_epoch, _ = (
            self._validated_issue_inputs(
                principal,
                authentication_method,
                authorization_epoch,
                oidc_policy_authorization_epoch,
                now,
            )
        )
        return await self._issue(
            principal=principal,
            authentication_method=authentication_method,
            authorization_epoch=authorization_epoch,
            oidc_policy_authorization_epoch=policy_epoch,
        )

    async def _resolve_state(self, token: str) -> SecuritySessionState:
        digest = self._digest(token)
        result = await self._coordination.resolve_security_session(
            SessionResolveRequest(
                digest,
                self._policy.idle_ttl_seconds,
                self._fencing_epoch,
                self._operation_id("resolve"),
            )
        )
        if result.resolved and result.session is not None:
            if (
                result.session.session_digest != digest
                or result.session.session_reference != self._reference(digest)
            ):
                raise SessionNotFound("Session is unavailable.")
            try:
                self._decode_payload(result.session)
            except SessionNotFound:
                try:
                    await self.revoke(token)
                except CoordinationError:
                    pass
                raise
            return result.session
        if result.reason == "expired":
            raise SessionExpired("Session expired.")
        raise SessionNotFound("Session is unavailable.")

    async def resolve(
        self,
        token: str,
        *,
        current_authorization_epoch: int,
        current_oidc_policy_authorization_epoch: int | None = None,
        now: float,
    ) -> SessionRecord:
        token = self._validated_token(token)
        if type(current_authorization_epoch) is not int or current_authorization_epoch < 1:
            raise ValueError("Session authorization epoch is invalid.")
        if current_oidc_policy_authorization_epoch is not None and (
            type(current_oidc_policy_authorization_epoch) is not int
            or current_oidc_policy_authorization_epoch < 1
        ):
            raise ValueError("OIDC policy authorization epoch is invalid.")
        _strict_timestamp(now, "Session timestamp")
        state = await self._resolve_state(token)
        record = self._record(state)
        if record.authorization_epoch != current_authorization_epoch or (
            record.authentication_method is SessionAuthenticationMethod.OIDC
            and record.oidc_policy_authorization_epoch != current_oidc_policy_authorization_epoch
        ):
            await self.revoke(token)
            raise SessionStale("Session authorization is stale.")
        return record

    async def inspect(self, token: str, *, now: float) -> SessionRecord:
        token = self._validated_token(token)
        _strict_timestamp(now, "Session timestamp")
        return self._record(await self._resolve_state(token))

    async def rotate(
        self,
        token: str,
        *,
        principal: ManagementPrincipal,
        authentication_method: SessionAuthenticationMethod,
        authorization_epoch: int,
        oidc_policy_authorization_epoch: int | None = None,
        now: float,
    ) -> IssuedSession:
        token = self._validated_token(token)
        principal, authentication_method, authorization_epoch, policy_epoch, _ = (
            self._validated_issue_inputs(
                principal,
                authentication_method,
                authorization_epoch,
                oidc_policy_authorization_epoch,
                now,
            )
        )
        return await self._issue(
            principal=principal,
            authentication_method=authentication_method,
            authorization_epoch=authorization_epoch,
            oidc_policy_authorization_epoch=policy_epoch,
            current_digest=self._digest(token),
        )

    async def revoke(self, token: str) -> bool:
        try:
            token = self._validated_token(token)
        except SessionNotFound:
            return False
        result = await self._coordination.revoke_security_sessions(
            SessionRevokeRequest(
                SessionRevokeTarget.DIGEST,
                self._digest(token),
                self._fencing_epoch,
                self._operation_id("revoke"),
            )
        )
        return result.revoked_count == 1

    async def revoke_principal(self, principal: ManagementPrincipal) -> int:
        if type(principal) is not ManagementPrincipal:
            raise ValueError("A validated session principal is required.")
        result = await self._coordination.revoke_security_sessions(
            SessionRevokeRequest(
                SessionRevokeTarget.PRINCIPAL,
                self._principal_index(principal),
                self._fencing_epoch,
                self._operation_id("revoke-principal"),
            )
        )
        return result.revoked_count

    async def revoke_principal_type(self, principal_type: PrincipalType) -> int:
        if type(principal_type) is not PrincipalType:
            raise ValueError("A validated principal type is required.")
        result = await self._coordination.revoke_security_sessions(
            SessionRevokeRequest(
                SessionRevokeTarget.PRINCIPAL_TYPE,
                self._security_principal_type(principal_type).value,
                self._fencing_epoch,
                self._operation_id("revoke-type"),
            )
        )
        return result.revoked_count

    async def list_active(
        self,
        *,
        limit: int,
        now: float,
        after_reference: str | None = None,
    ) -> list[ManagedSession]:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Session page size is invalid.")
        _strict_timestamp(now, "Session timestamp")
        try:
            page = await self._coordination.list_security_sessions(
                SessionListRequest(limit, self._fencing_epoch, after_reference)
            )
            return [self._managed(state) for state in page.sessions]
        except SessionNotFound:
            raise SessionError("Session inventory is unavailable.") from None

    async def reference_for_token(self, token: str, *, now: float) -> str:
        token = self._validated_token(token)
        _strict_timestamp(now, "Session timestamp")
        return (await self._resolve_state(token)).session_reference

    async def managed_for_token(self, token: str, *, now: float) -> ManagedSession:
        token = self._validated_token(token)
        _strict_timestamp(now, "Session timestamp")
        return self._managed(await self._resolve_state(token))

    async def revoke_reference(self, reference: str) -> bool:
        if type(reference) is not str or not _SESSION_REFERENCE_PATTERN.fullmatch(reference):
            return False
        result = await self._coordination.revoke_security_sessions(
            SessionRevokeRequest(
                SessionRevokeTarget.REFERENCE,
                reference,
                self._fencing_epoch,
                self._operation_id("revoke-reference"),
            )
        )
        return result.revoked_count == 1


def _encode_master_key(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _decode_master_key(value: Any) -> bytes:
    if not isinstance(value, str) or len(value) > 128:
        raise RuntimeError("Stored session master key is invalid.")
    try:
        decoded = base64.b64decode(value, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("Stored session master key is invalid.") from exc
    if len(decoded) != _SESSION_MASTER_KEY_BYTES or _encode_master_key(decoded) != value:
        raise RuntimeError("Stored session master key is invalid.")
    return decoded


def _env_lifetime(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def get_session_policy() -> SessionPolicy:
    """Build the bounded standalone policy while retaining the legacy TTL setting."""

    absolute_ttl = _env_lifetime(
        "PANEL_SESSION_TTL_SECONDS",
        86_400,
        MIN_SESSION_TTL_SECONDS + 1,
        MAX_SESSION_TTL_SECONDS,
    )
    idle_ttl = _env_lifetime(
        "PANEL_SESSION_IDLE_TTL_SECONDS",
        1_800,
        MIN_SESSION_TTL_SECONDS,
        absolute_ttl - 1,
    )
    max_active_sessions = _env_lifetime(
        "PANEL_SESSION_MAX_ACTIVE",
        10_000,
        MIN_ACTIVE_SESSIONS,
        MAX_ACTIVE_SESSIONS,
    )
    return SessionPolicy(
        idle_ttl_seconds=idle_ttl,
        absolute_ttl_seconds=absolute_ttl,
        max_active_sessions=max_active_sessions,
    )


class SessionService:
    """Bind opaque runtime sessions to durable identity authorization epochs."""

    def __init__(self, store: SessionStore, *, identity_repository: Any) -> None:
        self._store = store
        self._identity_repository = identity_repository

    def __repr__(self) -> str:
        return f"SessionService(store={self._store!r})"

    @classmethod
    async def create(
        cls,
        storage: Any,
        *,
        policy: SessionPolicy | None = None,
        coordination: IdentitySecurityCoordinationStore | None = None,
        fencing_epoch: int = 1,
        hmac_key: bytes | None = None,
    ) -> SessionService:
        selected_policy = policy or get_session_policy()
        if type(fencing_epoch) is not int or fencing_epoch < 1:
            raise ValueError("Session fencing epoch is invalid.")
        if hmac_key is None:
            encoded_master = await storage.get_config(_SESSION_MASTER_KEY_CONFIG, None)
            if encoded_master is None:
                generated = _encode_master_key(secrets.token_bytes(_SESSION_MASTER_KEY_BYTES))
                if not await storage.set_config(_SESSION_MASTER_KEY_CONFIG, generated):
                    raise RuntimeError("Unable to persist the session master key.")
                encoded_master = await storage.get_config(_SESSION_MASTER_KEY_CONFIG, None)
            master_key = _decode_master_key(encoded_master)
            session_key = hmac.digest(
                master_key,
                _SESSION_HMAC_DOMAIN + b"index-key",
                hashlib.sha256,
            )
        else:
            if type(hmac_key) is not bytes or len(hmac_key) != _SESSION_MASTER_KEY_BYTES:
                raise ValueError("Session HMAC key is invalid.")
            session_key = hmac_key
        identity_repository = await storage.create_identity_repository()
        if coordination is None:
            from core.state_store import InMemoryStateStore

            coordination = InMemoryStateStore(
                clock=time.time,
                _security_session_limit_for_testing=selected_policy.max_active_sessions,
            )
        return cls(
            CoordinatedSessionStore(
                coordination,
                hmac_key=session_key,
                policy=selected_policy,
                fencing_epoch=fencing_epoch,
            ),
            identity_repository=identity_repository,
        )

    async def _local_owner(self) -> ManagedIdentity:
        owner = await self._identity_repository.get_identity(LOCAL_OWNER_ID)
        if type(owner) is not ManagedIdentity or not owner.identity.enabled:
            raise RuntimeError("The local-owner recovery identity is unavailable.")
        return owner

    async def issue_local_owner(self, *, now: float) -> IssuedSession:
        try:
            owner = await self._local_owner()
            issued = await self._store.issue(
                principal=ManagementPrincipal.local_owner(owner.identity.identity_id),
                authentication_method=SessionAuthenticationMethod.LOCAL_PASSWORD,
                authorization_epoch=owner.identity.authorization_epoch,
                now=now,
            )
        except Exception:
            _record_session_metric("issue", "failed")
            raise
        _record_session_metric("issue", "succeeded")
        return issued

    @staticmethod
    def _expected_role_source(source: RoleBindingSource) -> OidcRoleSource:
        if source is RoleBindingSource.DIRECT_BINDING:
            return OidcRoleSource.DIRECT_BINDING
        if source is RoleBindingSource.CLAIM_MAPPING:
            return OidcRoleSource.CLAIM_MAPPING
        raise SessionStale("Session authorization is stale.")

    async def _oidc_authorization_snapshot(
        self,
        principal: ManagementPrincipal,
    ) -> tuple[ManagedIdentity, int, int]:
        if (
            type(principal) is not ManagementPrincipal
            or principal.principal_type is not PrincipalType.OIDC_USER
            or principal.issuer is None
            or principal.subject is None
        ):
            raise SessionStale("Session authorization is stale.")
        managed = await self._identity_repository.get_identity_by_oidc(
            issuer=principal.issuer,
            subject=principal.subject,
        )
        policy = await self._identity_repository.get_oidc_policy_revision()
        if (
            type(managed) is not ManagedIdentity
            or not managed.identity.enabled
            or managed.identity.issuer != principal.issuer
            or managed.identity.subject != principal.subject
            or managed.binding.role is not principal.role
            or self._expected_role_source(managed.binding.source) is not principal.role_source
        ):
            raise SessionStale("Session authorization is stale.")
        return managed, policy.revision, policy.authorization_epoch

    async def issue_oidc(
        self,
        resolved_identity: ResolvedOidcIdentity,
        *,
        now: float,
    ) -> IssuedSession:
        try:
            if type(resolved_identity) is not ResolvedOidcIdentity:
                raise ValueError("A resolved OIDC identity is required.")
            managed, policy_revision, policy_epoch = await self._oidc_authorization_snapshot(
                resolved_identity.principal
            )
            if (
                managed.identity.identity_id != resolved_identity.identity_id
                or managed.identity.authorization_epoch
                != resolved_identity.identity_authorization_epoch
                or managed.binding.revision != resolved_identity.binding_revision
                or policy_revision != resolved_identity.policy_revision
                or policy_epoch != resolved_identity.policy_authorization_epoch
            ):
                raise SessionStale("Session authorization is stale.")
            issued = await self._store.issue(
                principal=resolved_identity.principal,
                authentication_method=SessionAuthenticationMethod.OIDC,
                authorization_epoch=resolved_identity.identity_authorization_epoch,
                oidc_policy_authorization_epoch=resolved_identity.policy_authorization_epoch,
                now=now,
            )
        except Exception:
            _record_session_metric("issue", "failed")
            raise
        _record_session_metric("issue", "succeeded")
        return issued

    async def resolve(self, token: str, *, now: float) -> SessionRecord:
        try:
            inspected = await self._store.inspect(token, now=now)
            if inspected.authentication_method is SessionAuthenticationMethod.LOCAL_PASSWORD:
                owner = await self._local_owner()
                if inspected.principal != ManagementPrincipal.local_owner(
                    owner.identity.identity_id
                ):
                    await self._store.revoke(token)
                    raise SessionStale("Session authorization is stale.")
                identity_epoch = owner.identity.authorization_epoch
                policy_epoch = None
            elif inspected.authentication_method is SessionAuthenticationMethod.OIDC:
                try:
                    (
                        managed,
                        _policy_revision,
                        policy_epoch,
                    ) = await self._oidc_authorization_snapshot(inspected.principal)
                except SessionStale:
                    await self._store.revoke(token)
                    raise
                identity_epoch = managed.identity.authorization_epoch
            else:  # pragma: no cover - SessionRecord construction guards this
                await self._store.revoke(token)
                raise SessionStale("Session authorization is stale.")
            resolved = await self._store.resolve(
                token,
                current_authorization_epoch=identity_epoch,
                current_oidc_policy_authorization_epoch=policy_epoch,
                now=now,
            )
        except SessionExpired:
            _record_session_metric("resolve", "expired")
            raise
        except SessionStale:
            _record_session_metric("resolve", "stale")
            raise
        except SessionNotFound:
            _record_session_metric("resolve", "not_found")
            raise
        except Exception:
            _record_session_metric("resolve", "failed")
            raise
        _record_session_metric("resolve", "succeeded")
        return resolved

    async def revoke(self, token: str) -> bool:
        try:
            revoked = await self._store.revoke(token)
        except Exception:
            _record_session_metric("revoke", "failed")
            raise
        _record_session_metric("revoke", "succeeded" if revoked else "not_found")
        return revoked

    async def list_active(
        self,
        *,
        limit: int,
        now: float,
        after_reference: str | None = None,
    ) -> list[ManagedSession]:
        return await self._store.list_active(
            limit=limit,
            now=now,
            after_reference=after_reference,
        )

    async def reference_for_token(self, token: str, *, now: float) -> str:
        return await self._store.reference_for_token(token, now=now)

    async def managed_for_token(self, token: str, *, now: float) -> ManagedSession:
        return await self._store.managed_for_token(token, now=now)

    async def revoke_reference(self, reference: str) -> bool:
        try:
            revoked = await self._store.revoke_reference(reference)
        except Exception:
            _record_session_metric("revoke", "failed")
            raise
        _record_session_metric("revoke", "succeeded" if revoked else "not_found")
        return revoked

    async def revoke_local_owner_sessions(self) -> int:
        try:
            owner = await self._local_owner()
            revoked = await self._store.revoke_principal(
                ManagementPrincipal.local_owner(owner.identity.identity_id)
            )
        except Exception:
            _record_session_metric("revoke_principal", "failed")
            raise
        _record_session_metric("revoke_principal", "succeeded")
        return revoked

    async def revoke_principal(self, principal: ManagementPrincipal) -> int:
        try:
            revoked = await self._store.revoke_principal(principal)
        except Exception:
            _record_session_metric("revoke_principal", "failed")
            raise
        _record_session_metric("revoke_principal", "succeeded")
        return revoked

    async def revoke_oidc_sessions(self) -> int:
        try:
            revoked = await self._store.revoke_principal_type(PrincipalType.OIDC_USER)
        except Exception:
            _record_session_metric("revoke_principal", "failed")
            raise
        _record_session_metric("revoke_principal", "succeeded")
        return revoked


_session_service: SessionService | None = None
_session_service_lock = asyncio.Lock()


async def initialize_session_service(
    storage: Any | None = None,
    *,
    coordination: IdentitySecurityCoordinationStore | None = None,
    fencing_epoch: int = 1,
    hmac_key: bytes | None = None,
) -> SessionService:
    global _session_service
    async with _session_service_lock:
        if _session_service is None:
            if storage is None:
                from core.storage_adapter import get_storage_adapter

                storage = await get_storage_adapter()
            _session_service = await SessionService.create(
                storage,
                coordination=coordination,
                fencing_epoch=fencing_epoch,
                hmac_key=hmac_key,
            )
        return _session_service


def get_session_service() -> SessionService:
    if _session_service is None:
        raise RuntimeError("Session service is not initialized.")
    return _session_service


async def close_session_service() -> None:
    global _session_service
    async with _session_service_lock:
        _session_service = None
