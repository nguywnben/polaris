"""Versioned, append-only audit event contracts.

This module is deliberately storage-agnostic.  Raw actor and target identifiers are
converted to stable HMAC fingerprints before an event may cross the repository
boundary.  Durable backend implementations land in W3.2 against this contract.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

AUDIT_SCHEMA_VERSION = 1
AUDIT_CURSOR_VERSION = 1
MAX_IDENTIFIER_LENGTH = 512
MAX_CHANGE_CODES = 16
MIN_RETENTION_DAYS = 7
MAX_RETENTION_DAYS = 3650
MIN_RETENTION_EVENTS = 1000
MAX_RETENTION_EVENTS = 10_000_000

AUDIT_ACTOR_TYPES = frozenset(
    {
        "local_owner",
        "oidc_user",
        "panel_session",
        "root_key",
        "virtual_key",
        "system",
    }
)
AUDIT_ACTIONS = frozenset(
    {
        "auth.login",
        "auth.logout",
        "auth.recovery",
        "auth.setup",
        "config.update",
        "config.reset",
        "root_key.rotate",
        "provider.create",
        "provider.update",
        "provider.delete",
        "credential.create",
        "credential.update",
        "credential.delete",
        "credential.verify",
        "credential.test",
        "credential.quota",
        "credential.toggle",
        "credential.export",
        "credential.credit_mode",
        "credential.batch",
        "credential.import",
        "credential.email_refresh",
        "virtual_key.create",
        "virtual_key.update",
        "virtual_key.rotate",
        "virtual_key.revoke",
        "quality_policy.update",
        "backup.create",
        "backup.restore",
        "backup.export",
        "audit.retention_update",
        "audit.export",
        "trace.retention_update",
        "trace.export",
        "model_blacklist.clear",
        "model_pool.update",
        "logs.clear",
        "identity.create",
        "identity.update",
        "role_binding.update",
        "session.revoke",
        "oidc_policy.advance",
        "management.access_denied",
        "inference.execute",
    }
)
AUDIT_TARGET_TYPES = frozenset(
    {
        "session",
        "configuration",
        "provider",
        "credential",
        "virtual_key",
        "quality_policy",
        "backup",
        "audit_policy",
        "trace_policy",
        "root_key",
        "model_blacklist",
        "model_pool",
        "log_store",
        "identity",
        "role_binding",
        "oidc_policy",
        "management_route",
        "inference_route",
    }
)
AUDIT_OUTCOMES = frozenset(
    {
        "succeeded",
        "denied",
        "failed",
        "not_found",
        "conflict",
        "invalid",
        "timed_out",
        "cancelled",
    }
)
AUDIT_CHANGE_CODES = frozenset(
    {
        "created",
        "updated",
        "deleted",
        "enabled",
        "disabled",
        "rotated",
        "revoked",
        "verified",
        "settings_changed",
        "scopes_changed",
        "limits_changed",
        "budget_changed",
        "expiry_changed",
        "models_changed",
        "credentials_changed",
        "policy_changed",
        "restored",
        "exported",
        "retention_changed",
        "no_change",
    }
)

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_EVENT_ID = re.compile(r"^[0-9a-f]{32}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{20}$")
_FINGERPRINT_LENGTH = 20
_MIN_SIGNING_KEY_BYTES = 32


class AuditEventAlreadyExistsError(RuntimeError):
    """Raised when an append would reuse an immutable audit event ID."""


def _require_vocabulary(value: str, vocabulary: frozenset[str], field_name: str) -> str:
    candidate = str(value or "")
    if candidate not in vocabulary:
        raise ValueError(f"Unsupported audit {field_name}.")
    return candidate


def _require_request_id(value: str) -> str:
    candidate = str(value or "")
    if not _SAFE_REQUEST_ID.fullmatch(candidate):
        raise ValueError("Invalid audit request ID.")
    return candidate


def _require_identifier(value: str, field_name: str) -> str:
    candidate = str(value or "")
    if not candidate or len(candidate) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(f"Invalid audit {field_name} identifier.")
    return candidate


def _require_key(value: bytes, field_name: str) -> bytes:
    if not isinstance(value, bytes) or len(value) < _MIN_SIGNING_KEY_BYTES:
        raise ValueError(f"Audit {field_name} key must contain at least 32 bytes.")
    return value


def _fingerprint(*, domain: str, identifier: str, key: bytes) -> str:
    material = f"{domain}\0{identifier}".encode("utf-8", errors="strict")
    return hmac.new(key, material, hashlib.sha256).hexdigest()[:_FINGERPRINT_LENGTH]


def _normalize_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"Audit {field_name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _normalize_change_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values or len(values) > MAX_CHANGE_CODES:
        raise ValueError("Audit change summary must contain 1 to 16 codes.")
    normalized: list[str] = []
    for value in values:
        candidate = _require_vocabulary(value, AUDIT_CHANGE_CODES, "change code")
        if candidate not in normalized:
            normalized.append(candidate)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Immutable repository record containing no raw actor or target identifier."""

    schema_version: int
    event_id: str
    occurred_at: str
    request_id: str
    actor_type: str
    actor_fingerprint: str
    action: str
    target_type: str
    target_fingerprint: str
    outcome: str
    change_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != AUDIT_SCHEMA_VERSION:
            raise ValueError("Unsupported audit event schema version.")
        if not _EVENT_ID.fullmatch(str(self.event_id or "")):
            raise ValueError("Invalid audit event ID.")
        try:
            timestamp = datetime.fromisoformat(str(self.occurred_at or ""))
        except ValueError as exc:
            raise ValueError("Invalid audit event timestamp.") from exc
        object.__setattr__(
            self,
            "occurred_at",
            _normalize_datetime(timestamp, "event timestamp").isoformat(),
        )
        object.__setattr__(self, "request_id", _require_request_id(self.request_id))
        object.__setattr__(
            self,
            "actor_type",
            _require_vocabulary(self.actor_type, AUDIT_ACTOR_TYPES, "actor type"),
        )
        object.__setattr__(
            self,
            "action",
            _require_vocabulary(self.action, AUDIT_ACTIONS, "action"),
        )
        object.__setattr__(
            self,
            "target_type",
            _require_vocabulary(self.target_type, AUDIT_TARGET_TYPES, "target type"),
        )
        object.__setattr__(
            self,
            "outcome",
            _require_vocabulary(self.outcome, AUDIT_OUTCOMES, "outcome"),
        )
        if not _FINGERPRINT.fullmatch(str(self.actor_fingerprint or "")):
            raise ValueError("Invalid audit actor fingerprint.")
        if not _FINGERPRINT.fullmatch(str(self.target_fingerprint or "")):
            raise ValueError("Invalid audit target fingerprint.")
        object.__setattr__(self, "change_codes", _normalize_change_codes(self.change_codes))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "occurred_at": self.occurred_at,
            "request_id": self.request_id,
            "actor_type": self.actor_type,
            "actor_fingerprint": self.actor_fingerprint,
            "action": self.action,
            "target_type": self.target_type,
            "target_fingerprint": self.target_fingerprint,
            "outcome": self.outcome,
            "change_codes": list(self.change_codes),
        }


def audit_event_from_record(record: Mapping[str, Any]) -> AuditEvent:
    """Revalidate an untrusted storage record before returning it to callers."""

    expected_fields = {
        "schema_version",
        "event_id",
        "occurred_at",
        "request_id",
        "actor_type",
        "actor_fingerprint",
        "action",
        "target_type",
        "target_fingerprint",
        "outcome",
        "change_codes",
    }
    if not isinstance(record, Mapping) or set(record) != expected_fields:
        raise ValueError("Invalid stored audit event shape.")
    change_codes = record["change_codes"]
    if not isinstance(change_codes, (list, tuple)):
        raise ValueError("Invalid stored audit change summary.")
    return AuditEvent(
        schema_version=record["schema_version"],
        event_id=record["event_id"],
        occurred_at=record["occurred_at"],
        request_id=record["request_id"],
        actor_type=record["actor_type"],
        actor_fingerprint=record["actor_fingerprint"],
        action=record["action"],
        target_type=record["target_type"],
        target_fingerprint=record["target_fingerprint"],
        outcome=record["outcome"],
        change_codes=tuple(change_codes),
    )


def create_audit_event(
    *,
    request_id: str,
    actor_type: str,
    actor_identifier: str,
    action: str,
    target_type: str,
    target_identifier: str,
    outcome: str,
    change_codes: tuple[str, ...],
    fingerprint_key: bytes,
    occurred_at: datetime | None = None,
) -> AuditEvent:
    """Validate and redact an event before it reaches durable storage."""

    safe_key = _require_key(fingerprint_key, "fingerprint")
    safe_actor_type = _require_vocabulary(actor_type, AUDIT_ACTOR_TYPES, "actor type")
    safe_target_type = _require_vocabulary(target_type, AUDIT_TARGET_TYPES, "target type")
    safe_action = _require_vocabulary(action, AUDIT_ACTIONS, "action")
    safe_outcome = _require_vocabulary(outcome, AUDIT_OUTCOMES, "outcome")
    safe_actor_identifier = _require_identifier(actor_identifier, "actor")
    safe_target_identifier = _require_identifier(target_identifier, "target")
    safe_occurred_at = _normalize_datetime(
        occurred_at or datetime.now(timezone.utc),
        "occurrence timestamp",
    )

    return AuditEvent(
        schema_version=AUDIT_SCHEMA_VERSION,
        event_id=uuid.uuid4().hex,
        occurred_at=safe_occurred_at.isoformat(),
        request_id=_require_request_id(request_id),
        actor_type=safe_actor_type,
        actor_fingerprint=_fingerprint(
            domain=f"actor:{safe_actor_type}",
            identifier=safe_actor_identifier,
            key=safe_key,
        ),
        action=safe_action,
        target_type=safe_target_type,
        target_fingerprint=_fingerprint(
            domain=f"target:{safe_target_type}",
            identifier=safe_target_identifier,
            key=safe_key,
        ),
        outcome=safe_outcome,
        change_codes=_normalize_change_codes(change_codes),
    )


def _normalize_filter(
    values: tuple[str, ...],
    vocabulary: frozenset[str],
    field_name: str,
) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) > 32:
        raise ValueError(f"Invalid audit {field_name} filter.")
    normalized: list[str] = []
    for value in values:
        candidate = _require_vocabulary(value, vocabulary, field_name)
        if candidate not in normalized:
            normalized.append(candidate)
    return tuple(normalized)


def _normalize_fingerprint_filter(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) > 32:
        raise ValueError(f"Invalid audit {field_name} filter.")
    normalized: list[str] = []
    for value in values:
        candidate = str(value or "")
        if not _FINGERPRINT.fullmatch(candidate):
            raise ValueError(f"Invalid audit {field_name} filter.")
        if candidate not in normalized:
            normalized.append(candidate)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class AuditQuery:
    """Bounded repository query; cursors remain opaque to API consumers."""

    actor_types: tuple[str, ...] = ()
    actor_fingerprints: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    target_types: tuple[str, ...] = ()
    target_fingerprints: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    request_id: str | None = None
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None
    page_size: int = 50
    cursor: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "actor_types",
            _normalize_filter(self.actor_types, AUDIT_ACTOR_TYPES, "actor type"),
        )
        object.__setattr__(
            self,
            "actor_fingerprints",
            _normalize_fingerprint_filter(self.actor_fingerprints, "actor fingerprint"),
        )
        object.__setattr__(
            self,
            "actions",
            _normalize_filter(self.actions, AUDIT_ACTIONS, "action"),
        )
        object.__setattr__(
            self,
            "target_types",
            _normalize_filter(self.target_types, AUDIT_TARGET_TYPES, "target type"),
        )
        object.__setattr__(
            self,
            "target_fingerprints",
            _normalize_fingerprint_filter(self.target_fingerprints, "target fingerprint"),
        )
        object.__setattr__(
            self,
            "outcomes",
            _normalize_filter(self.outcomes, AUDIT_OUTCOMES, "outcome"),
        )
        if self.request_id is not None:
            object.__setattr__(self, "request_id", _require_request_id(self.request_id))
        if not isinstance(self.page_size, int) or not 1 <= self.page_size <= 200:
            raise ValueError("Audit query page size must be between 1 and 200.")
        if self.cursor is not None and (
            not isinstance(self.cursor, str) or not 1 <= len(self.cursor) <= 1024
        ):
            raise ValueError("Invalid audit query cursor.")
        after = (
            _normalize_datetime(self.occurred_after, "start timestamp")
            if self.occurred_after is not None
            else None
        )
        before = (
            _normalize_datetime(self.occurred_before, "end timestamp")
            if self.occurred_before is not None
            else None
        )
        if after is not None:
            object.__setattr__(self, "occurred_after", after)
        if before is not None:
            object.__setattr__(self, "occurred_before", before)
        if after is not None and before is not None and after > before:
            raise ValueError("Audit query start timestamp must not exceed the end timestamp.")


@dataclass(frozen=True, slots=True)
class AuditRetentionPolicy:
    retention_days: int = 90
    max_events: int = 1_000_000

    def __post_init__(self) -> None:
        if not isinstance(self.retention_days, int) or not (
            MIN_RETENTION_DAYS <= self.retention_days <= MAX_RETENTION_DAYS
        ):
            raise ValueError("Audit retention days must be between 7 and 3650.")
        if not isinstance(self.max_events, int) or not (
            MIN_RETENTION_EVENTS <= self.max_events <= MAX_RETENTION_EVENTS
        ):
            raise ValueError("Audit retention event limit is outside supported bounds.")


@dataclass(frozen=True, slots=True)
class AuditPage:
    events: tuple[AuditEvent, ...]
    next_cursor: str | None = None


class AuditRepository(Protocol):
    """Append-only durable boundary; individual event mutation is intentionally absent."""

    async def append(self, event: AuditEvent) -> None: ...

    async def query(self, query: AuditQuery) -> AuditPage: ...

    async def prune(self, policy: AuditRetentionPolicy, *, now: datetime) -> int: ...


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid audit cursor encoding.") from exc


def encode_audit_cursor(*, occurred_at: str, event_id: str, signing_key: bytes) -> str:
    safe_key = _require_key(signing_key, "cursor signing")
    try:
        timestamp = datetime.fromisoformat(str(occurred_at or ""))
    except ValueError as exc:
        raise ValueError("Invalid audit cursor timestamp.") from exc
    safe_timestamp = _normalize_datetime(timestamp, "cursor timestamp").isoformat()
    safe_event_id = str(event_id or "")
    if not _EVENT_ID.fullmatch(safe_event_id):
        raise ValueError("Invalid audit cursor event ID.")
    payload = json.dumps(
        {"v": AUDIT_CURSOR_VERSION, "t": safe_timestamp, "i": safe_event_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    signature = hmac.new(safe_key, payload, hashlib.sha256).digest()
    return _encode_base64url(payload + signature)


def decode_audit_cursor(cursor: str, *, signing_key: bytes) -> tuple[str, str]:
    safe_key = _require_key(signing_key, "cursor signing")
    if not isinstance(cursor, str) or not 1 <= len(cursor) <= 1024:
        raise ValueError("Invalid audit cursor.")
    packed = _decode_base64url(cursor)
    if _encode_base64url(packed) != cursor or len(packed) <= hashlib.sha256().digest_size:
        raise ValueError("Invalid audit cursor.")
    payload = packed[: -hashlib.sha256().digest_size]
    supplied_signature = packed[-hashlib.sha256().digest_size :]
    expected_signature = hmac.new(safe_key, payload, hashlib.sha256).digest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise ValueError("Invalid audit cursor signature.")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid audit cursor payload.") from exc
    if not isinstance(decoded, dict) or set(decoded) != {"v", "t", "i"}:
        raise ValueError("Invalid audit cursor payload.")
    if decoded["v"] != AUDIT_CURSOR_VERSION:
        raise ValueError("Unsupported audit cursor version.")
    event_id = str(decoded["i"] or "")
    if not _EVENT_ID.fullmatch(event_id):
        raise ValueError("Invalid audit cursor event ID.")
    try:
        timestamp = datetime.fromisoformat(str(decoded["t"] or ""))
    except ValueError as exc:
        raise ValueError("Invalid audit cursor timestamp.") from exc
    occurred_at = _normalize_datetime(timestamp, "cursor timestamp").isoformat()
    return occurred_at, event_id
