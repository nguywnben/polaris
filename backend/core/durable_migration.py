"""Versioned W4.13 durable-record inventory and migration domain contract.

The module is deliberately side-effect free. It defines strict records, checkpoint invariants,
and keyed content verification without selecting a backend or switching runtime authority.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

MIGRATION_SCHEMA_VERSION = 1
DURABLE_MANIFEST_VERSION = 2
_PLAN_ID = re.compile(r"dmg_[0-9a-f]{32}")
_LOGICAL_ID = re.compile(r"[a-z]{3}_[0-9a-f]{16,64}")
_INSTANCE_ID = re.compile(r"ins_[0-9a-f]{32}")
_BARRIER_ID = re.compile(r"bar_[0-9a-f]{32}")
_FAILURE_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_CHECKSUM = re.compile(r"[0-9a-f]{64}")


class DurableBackend(StrEnum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MONGODB = "mongodb"


class DurableFamily(StrEnum):
    CONFIGURATION = "configuration"
    PROVIDER_CREDENTIAL = "provider_credential"
    PRIMARY_CREDENTIAL = "primary_credential"
    VIRTUAL_KEY = "virtual_key"
    IDENTITY = "identity"
    ROLE_BINDING = "role_binding"
    OIDC_POLICY_REVISION = "oidc_policy_revision"
    IDENTITY_SCHEMA_EVIDENCE = "identity_schema_evidence"
    AUDIT_EVENT = "audit_event"
    REQUEST_TRACE = "request_trace"
    USAGE_LEDGER = "usage_ledger"
    HARD_BUDGET_RESERVATION = "hard_budget_reservation"
    MIGRATION_CHECKPOINT = "migration_checkpoint"


class MigrationPhase(StrEnum):
    PLANNED = "planned"
    COPYING = "copying"
    VERIFYING = "verifying"
    READY_TO_SWITCH = "ready_to_switch"
    TARGET_AUTHORITATIVE = "target_authoritative"
    ROLLBACK_READY = "rollback_ready"
    ROLLED_BACK = "rolled_back"


class AuthoritySide(StrEnum):
    SOURCE = "source"
    TARGET = "target"


@dataclass(frozen=True, slots=True)
class DurableInventoryEntry:
    family: DurableFamily
    current_owner: str
    switch_ready: bool
    copy_required: bool
    contains_sensitive_payload: bool
    implementation_note: str

    def __post_init__(self) -> None:
        if type(self.family) is not DurableFamily:
            raise ValueError("Durable family is invalid.")
        if not isinstance(self.current_owner, str) or not self.current_owner.strip():
            raise ValueError("Durable owner is invalid.")
        if type(self.switch_ready) is not bool:
            raise ValueError("Durable readiness is invalid.")
        if type(self.copy_required) is not bool:
            raise ValueError("Durable copy requirement is invalid.")
        if type(self.contains_sensitive_payload) is not bool:
            raise ValueError("Durable sensitivity is invalid.")
        if not isinstance(self.implementation_note, str) or not self.implementation_note.strip():
            raise ValueError("Durable implementation note is invalid.")


DURABLE_INVENTORY = (
    DurableInventoryEntry(
        DurableFamily.CONFIGURATION,
        "selected_backend.config",
        True,
        True,
        True,
        "Versioned configuration and internal key material.",
    ),
    DurableInventoryEntry(
        DurableFamily.PROVIDER_CREDENTIAL,
        "selected_backend.credentials",
        True,
        True,
        True,
        "Provider-pool credential payload and current stored state.",
    ),
    DurableInventoryEntry(
        DurableFamily.PRIMARY_CREDENTIAL,
        "selected_backend.primary_credentials",
        True,
        True,
        True,
        "Primary credential payload and current stored state.",
    ),
    DurableInventoryEntry(
        DurableFamily.VIRTUAL_KEY,
        "selected_backend.config.virtual_keys",
        True,
        True,
        True,
        "Authorization and billing metadata currently stored as a versioned config document.",
    ),
    DurableInventoryEntry(
        DurableFamily.IDENTITY,
        "identity_repository.identities",
        True,
        True,
        True,
        "Management identities and authorization epochs.",
    ),
    DurableInventoryEntry(
        DurableFamily.ROLE_BINDING,
        "identity_repository.role_bindings",
        True,
        True,
        True,
        "Explicit role bindings and revisions.",
    ),
    DurableInventoryEntry(
        DurableFamily.OIDC_POLICY_REVISION,
        "identity_repository.oidc_policy_revision",
        True,
        True,
        False,
        "OIDC policy and authorization epoch only; client secrets are environment-owned.",
    ),
    DurableInventoryEntry(
        DurableFamily.IDENTITY_SCHEMA_EVIDENCE,
        "identity_repository.identity_migrations",
        True,
        True,
        False,
        "Additive management-identity schema evidence.",
    ),
    DurableInventoryEntry(
        DurableFamily.AUDIT_EVENT,
        "audit_repository",
        True,
        True,
        False,
        "Append-only redacted management evidence.",
    ),
    DurableInventoryEntry(
        DurableFamily.REQUEST_TRACE,
        "request_trace_repository",
        True,
        True,
        False,
        "Bounded request decision evidence without prompts or bodies.",
    ),
    DurableInventoryEntry(
        DurableFamily.USAGE_LEDGER,
        "standalone_usage_stats_db",
        True,
        True,
        True,
        "Usage and cost events in the selected backend durable ledger.",
    ),
    DurableInventoryEntry(
        DurableFamily.HARD_BUDGET_RESERVATION,
        "not_implemented",
        True,
        True,
        True,
        "Reservation rows in the selected backend durable usage ledger.",
    ),
    DurableInventoryEntry(
        DurableFamily.MIGRATION_CHECKPOINT,
        "migration_checkpoint_repository",
        True,
        False,
        False,
        "Versioned metadata-only resumability evidence.",
    ),
)


def _manifest_checksum() -> str:
    payload = [
        {
            "family": entry.family.value,
            "current_owner": entry.current_owner,
            "switch_ready": entry.switch_ready,
            "copy_required": entry.copy_required,
            "contains_sensitive_payload": entry.contains_sensitive_payload,
        }
        for entry in DURABLE_INVENTORY
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


DURABLE_MANIFEST_CHECKSUM = _manifest_checksum()
DURABLE_COPY_FAMILIES = tuple(entry.family for entry in DURABLE_INVENTORY if entry.copy_required)


@dataclass(frozen=True, slots=True)
class DurableFamilyAdapterSpec:
    """Closed mapping from one manifest family to its real application table."""

    table: str
    columns: tuple[str, ...]
    key_columns: tuple[str, ...]
    logical_prefix: str
    predicate: str = ""
    json_columns: tuple[str, ...] = ()
    boolean_columns: tuple[str, ...] = ()
    timestamp_columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        identifiers = (self.table, *self.columns, *self.key_columns)
        if any(
            not isinstance(value, str) or not value.replace("_", "").isalnum()
            for value in identifiers
        ):
            raise ValueError("Durable adapter identifier is invalid.")
        if (
            not self.columns
            or not self.key_columns
            or not set(self.key_columns) <= set(self.columns)
        ):
            raise ValueError("Durable adapter columns are invalid.")
        if not re.fullmatch(r"[a-z]{3}", self.logical_prefix):
            raise ValueError("Durable adapter logical prefix is invalid.")
        if not set(self.json_columns + self.boolean_columns + self.timestamp_columns) <= set(
            self.columns
        ):
            raise ValueError("Durable adapter normalization columns are invalid.")


def durable_logical_id(
    family: DurableFamily, spec: DurableFamilyAdapterSpec, row: Mapping[str, Any]
) -> str:
    """Return a non-secret stable identity derived from the actual table key."""

    try:
        key = json.dumps(
            [row[column] for column in spec.key_columns],
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Durable adapter record key is invalid.") from exc
    digest = hashlib.sha256(family.value.encode("ascii") + b"\0" + key).hexdigest()[:32]
    return f"{spec.logical_prefix}_{digest}"


def durable_ordering_key(spec: DurableFamilyAdapterSpec, row: Mapping[str, Any]) -> str:
    """Return the private application-key order shared by both migration adapters."""

    try:
        return json.dumps(
            [row[column] for column in spec.key_columns],
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Durable adapter record key is invalid.") from exc


@dataclass(frozen=True, slots=True)
class MigrationEndpointDescriptor:
    backend: DurableBackend
    instance_id: str
    revision: int = 1

    def __post_init__(self) -> None:
        if type(self.backend) is not DurableBackend:
            raise ValueError("Migration endpoint backend is invalid.")
        if not isinstance(self.instance_id, str) or not _INSTANCE_ID.fullmatch(self.instance_id):
            raise ValueError("Migration endpoint instance ID is invalid.")
        _strict_positive_int(self.revision, "Migration endpoint revision")


def _strict_non_negative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} is invalid.")
    return value


def _strict_positive_int(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} is invalid.")
    return value


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 40:
        raise ValueError(f"{label} is invalid.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} is invalid.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be UTC.")
    return parsed


def _json_compatible(value: object) -> object:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Durable payload contains a non-finite number.")
        return value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Durable payload keys must be strings.")
            result[key] = _json_compatible(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    raise ValueError("Durable payload contains an unsupported value.")


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def durable_record_payload(record: DurableRecord) -> dict[str, Any]:
    """Return a mutable JSON-compatible copy for a backend write boundary."""

    if type(record) is not DurableRecord:
        raise ValueError("Durable record is invalid.")
    value = _thaw_json(record.payload)
    if not isinstance(value, dict):
        raise ValueError("Durable record payload is invalid.")
    return value


def _canonical_record(record: DurableRecord) -> bytes:
    return json.dumps(
        {
            "family": record.family.value,
            "logical_id": record.logical_id,
            "schema_version": record.schema_version,
            "ordering_key_digest": hashlib.sha256(record.ordering_key.encode("utf-8")).hexdigest(),
            "payload": _thaw_json(record.payload),
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class DurableRecord:
    family: DurableFamily
    logical_id: str
    schema_version: int
    payload: Mapping[str, Any]
    ordering_key: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if type(self.family) is not DurableFamily:
            raise ValueError("Durable record family is invalid.")
        if not isinstance(self.logical_id, str) or not _LOGICAL_ID.fullmatch(self.logical_id):
            raise ValueError("Durable logical ID is invalid.")
        _strict_positive_int(self.schema_version, "Durable record schema version")
        if not isinstance(self.payload, Mapping):
            raise ValueError("Durable record payload is invalid.")
        normalized = _json_compatible(self.payload)
        object.__setattr__(self, "payload", _freeze_json(normalized))
        if not isinstance(self.ordering_key, str) or len(self.ordering_key.encode("utf-8")) > 4096:
            raise ValueError("Durable record ordering key is invalid.")

    def __repr__(self) -> str:
        return (
            "DurableRecord("
            f"family={self.family!r}, logical_id={self.logical_id!r}, "
            f"schema_version={self.schema_version!r}, payload=<redacted>)"
        )


def compute_records_digest(
    records: tuple[DurableRecord, ...] | list[DurableRecord], *, integrity_key: bytes
) -> str:
    ordered = sorted(
        records, key=lambda item: (item.family.value, item.ordering_key or item.logical_id)
    )
    digest = MigrationDigest(integrity_key=integrity_key)
    for record in ordered:
        digest.add(record)
    return digest.hexdigest()


class MigrationDigest:
    """Incremental keyed digest over strictly ordered durable records."""

    def __init__(self, *, integrity_key: bytes) -> None:
        if not isinstance(integrity_key, bytes) or len(integrity_key) < 32:
            raise ValueError("Migration integrity key is too short.")
        self._digest = hmac.new(integrity_key, digestmod=hashlib.sha256)
        self._last_identity: tuple[str, str] | None = None
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    def add(self, record: DurableRecord) -> None:
        if type(record) is not DurableRecord:
            raise ValueError("Migration digest record is invalid.")
        identity = (record.family.value, record.ordering_key or record.logical_id)
        if self._last_identity is not None and identity <= self._last_identity:
            raise ValueError("Migration digest records are duplicated or out of order.")
        encoded = _canonical_record(record)
        self._digest.update(len(encoded).to_bytes(8, "big"))
        self._digest.update(encoded)
        self._last_identity = identity
        self._count += 1

    def hexdigest(self) -> str:
        return self._digest.hexdigest()


@dataclass(frozen=True, slots=True)
class FamilyProgress:
    family: DurableFamily
    copy_offset: int
    copied_count: int
    copy_complete: bool
    explicitly_empty: bool
    source_count: int | None
    target_count: int | None
    source_checksum: str | None
    target_checksum: str | None
    verified: bool

    def __post_init__(self) -> None:
        if type(self.family) is not DurableFamily:
            raise ValueError("Migration family is invalid.")
        _strict_non_negative_int(self.copy_offset, "Migration copy offset")
        _strict_non_negative_int(self.copied_count, "Migration copied count")
        if (
            type(self.copy_complete) is not bool
            or type(self.explicitly_empty) is not bool
            or type(self.verified) is not bool
        ):
            raise ValueError("Migration progress flag is invalid.")
        if self.copy_offset != self.copied_count:
            raise ValueError("Migration copy position is inconsistent.")
        for count, label in (
            (self.source_count, "Migration source count"),
            (self.target_count, "Migration target count"),
        ):
            if count is not None:
                _strict_non_negative_int(count, label)
        for checksum in (self.source_checksum, self.target_checksum):
            if checksum is not None and (
                not isinstance(checksum, str) or not _CHECKSUM.fullmatch(checksum)
            ):
                raise ValueError("Migration checksum is invalid.")
        verification_values = (
            self.source_count,
            self.target_count,
            self.source_checksum,
            self.target_checksum,
        )
        if any(value is not None for value in verification_values) and any(
            value is None for value in verification_values
        ):
            raise ValueError("Migration verification evidence is incomplete.")
        if self.verified and (
            not self.copy_complete
            or self.source_count != self.target_count
            or self.source_checksum != self.target_checksum
            or self.source_count is None
            or (self.source_count == 0) != self.explicitly_empty
        ):
            raise ValueError("Migration verification evidence does not match.")

    def to_record(self) -> dict[str, object]:
        return {
            "family": self.family.value,
            "copy_offset": self.copy_offset,
            "copied_count": self.copied_count,
            "copy_complete": self.copy_complete,
            "explicitly_empty": self.explicitly_empty,
            "source_count": self.source_count,
            "target_count": self.target_count,
            "source_checksum": self.source_checksum,
            "target_checksum": self.target_checksum,
            "verified": self.verified,
        }


_SOURCE_PHASES = {
    MigrationPhase.PLANNED,
    MigrationPhase.COPYING,
    MigrationPhase.VERIFYING,
    MigrationPhase.READY_TO_SWITCH,
    MigrationPhase.ROLLED_BACK,
}
_TARGET_PHASES = {MigrationPhase.TARGET_AUTHORITATIVE, MigrationPhase.ROLLBACK_READY}
_VERIFIED_PHASES = {
    MigrationPhase.READY_TO_SWITCH,
    MigrationPhase.TARGET_AUTHORITATIVE,
    MigrationPhase.ROLLBACK_READY,
    MigrationPhase.ROLLED_BACK,
}


@dataclass(frozen=True, slots=True)
class MigrationCheckpoint:
    schema_version: int
    manifest_version: int
    manifest_checksum: str
    plan_id: str
    source_backend: DurableBackend
    target_backend: DurableBackend
    source_instance_id: str
    target_instance_id: str
    source_revision: int
    target_revision: int
    source_barrier_id: str
    phase: MigrationPhase
    authority: AuthoritySide
    revision: int
    families: tuple[FamilyProgress, ...]
    failure_code: str | None
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != MIGRATION_SCHEMA_VERSION:
            raise ValueError("Migration checkpoint schema version is unsupported.")
        if (
            type(self.manifest_version) is not int
            or self.manifest_version != DURABLE_MANIFEST_VERSION
            or self.manifest_checksum != DURABLE_MANIFEST_CHECKSUM
        ):
            raise ValueError("Migration manifest is unsupported.")
        if not isinstance(self.plan_id, str) or not _PLAN_ID.fullmatch(self.plan_id):
            raise ValueError("Migration plan ID is invalid.")
        if (
            type(self.source_backend) is not DurableBackend
            or type(self.target_backend) is not DurableBackend
        ):
            raise ValueError("Migration backend is invalid.")
        for instance_id in (self.source_instance_id, self.target_instance_id):
            if not isinstance(instance_id, str) or not _INSTANCE_ID.fullmatch(instance_id):
                raise ValueError("Migration endpoint instance ID is invalid.")
        if self.source_instance_id == self.target_instance_id:
            raise ValueError("Migration source and target instances must differ.")
        _strict_positive_int(self.source_revision, "Migration source revision")
        _strict_positive_int(self.target_revision, "Migration target revision")
        if not isinstance(self.source_barrier_id, str) or not _BARRIER_ID.fullmatch(
            self.source_barrier_id
        ):
            raise ValueError("Migration source barrier ID is invalid.")
        if type(self.phase) is not MigrationPhase or type(self.authority) is not AuthoritySide:
            raise ValueError("Migration phase or authority is invalid.")
        if self.phase in _SOURCE_PHASES and self.authority is not AuthoritySide.SOURCE:
            raise ValueError("Migration source must be the sole authority in this phase.")
        if self.phase in _TARGET_PHASES and self.authority is not AuthoritySide.TARGET:
            raise ValueError("Migration target must be the sole authority in this phase.")
        _strict_positive_int(self.revision, "Migration checkpoint revision")
        if not isinstance(self.families, tuple) or not self.families:
            raise ValueError("Migration families are invalid.")
        if any(type(progress) is not FamilyProgress for progress in self.families):
            raise ValueError("Migration family progress is invalid.")
        family_names = [progress.family for progress in self.families]
        if len(set(family_names)) != len(family_names):
            raise ValueError("Migration families contain a duplicate.")
        if tuple(family_names) != DURABLE_COPY_FAMILIES:
            raise ValueError("Migration checkpoint does not cover the canonical manifest.")
        if self.phase in _VERIFIED_PHASES and not all(
            progress.verified for progress in self.families
        ):
            raise ValueError("Migration phase requires complete verification.")
        if self.phase in _VERIFIED_PHASES and not all(
            entry.switch_ready for entry in DURABLE_INVENTORY
        ):
            raise ValueError("Migration manifest is not ready for authority transition.")
        if self.failure_code is not None and (
            not isinstance(self.failure_code, str) or not _FAILURE_CODE.fullmatch(self.failure_code)
        ):
            raise ValueError("Migration failure code is invalid.")
        created_at = _timestamp(self.created_at, "Migration creation timestamp")
        updated_at = _timestamp(self.updated_at, "Migration update timestamp")
        if updated_at < created_at:
            raise ValueError("Migration update precedes creation.")

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "manifest_version": self.manifest_version,
            "manifest_checksum": self.manifest_checksum,
            "plan_id": self.plan_id,
            "source_backend": self.source_backend.value,
            "target_backend": self.target_backend.value,
            "source_instance_id": self.source_instance_id,
            "target_instance_id": self.target_instance_id,
            "source_revision": self.source_revision,
            "target_revision": self.target_revision,
            "source_barrier_id": self.source_barrier_id,
            "phase": self.phase.value,
            "authority": self.authority.value,
            "revision": self.revision,
            "families": [progress.to_record() for progress in self.families],
            "failure_code": self.failure_code,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _exact_record(record: object, expected_fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(record, Mapping) or set(record) != expected_fields:
        raise ValueError(f"Stored {label} is invalid.")
    return dict(record)


def _progress_from_record(record: object) -> FamilyProgress:
    expected = {field.name for field in fields(FamilyProgress)}
    values = _exact_record(record, expected, "migration family progress")
    try:
        values["family"] = DurableFamily(values["family"])
        return FamilyProgress(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored migration family progress is invalid.") from exc


@dataclass(frozen=True, slots=True)
class HistoricalMigrationCheckpoint:
    """Strictly decoded v1 evidence retained for audit, never for HA admission."""

    plan_id: str
    manifest_version: int
    manifest_checksum: str
    revision: int
    record: Mapping[str, Any] = field(repr=False)

    @property
    def eligible_for_binding(self) -> bool:
        return False


_V1_CHECKPOINT_FIELDS = {
    "schema_version",
    "manifest_version",
    "manifest_checksum",
    "plan_id",
    "source_backend",
    "target_backend",
    "source_instance_id",
    "target_instance_id",
    "source_barrier_id",
    "phase",
    "authority",
    "revision",
    "families",
    "failure_code",
    "created_at",
    "updated_at",
}


def _historical_checkpoint_from_record(record: object) -> HistoricalMigrationCheckpoint:
    values = _exact_record(record, _V1_CHECKPOINT_FIELDS, "migration checkpoint")
    if (
        values.get("schema_version") != 1
        or values.get("manifest_version") != 1
        or not isinstance(values.get("manifest_checksum"), str)
        or not _CHECKSUM.fullmatch(values["manifest_checksum"])
        or not isinstance(values.get("plan_id"), str)
        or not _PLAN_ID.fullmatch(values["plan_id"])
    ):
        raise ValueError("Stored migration checkpoint is invalid.")
    # Revalidate all historical family records and the bounded structural fields. Historical
    # evidence remains inspectable, but its old manifest meaning can never open HA readiness.
    raw_families = values.get("families")
    if not isinstance(raw_families, list) or not raw_families:
        raise ValueError("Stored migration checkpoint is invalid.")
    tuple(_progress_from_record(item) for item in raw_families)
    try:
        DurableBackend(values["source_backend"])
        DurableBackend(values["target_backend"])
        MigrationPhase(values["phase"])
        AuthoritySide(values["authority"])
        _strict_positive_int(values["revision"], "Migration checkpoint revision")
        _timestamp(values["created_at"], "Migration creation timestamp")
        _timestamp(values["updated_at"], "Migration update timestamp")
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored migration checkpoint is invalid.") from exc
    return HistoricalMigrationCheckpoint(
        plan_id=values["plan_id"],
        manifest_version=1,
        manifest_checksum=values["manifest_checksum"],
        revision=values["revision"],
        record=MappingProxyType(values),
    )


def checkpoint_from_record(record: object) -> MigrationCheckpoint | HistoricalMigrationCheckpoint:
    if isinstance(record, Mapping) and record.get("manifest_version") == 1:
        return _historical_checkpoint_from_record(record)
    expected = {field.name for field in fields(MigrationCheckpoint)}
    values = _exact_record(record, expected, "migration checkpoint")
    try:
        raw_families = values["families"]
        if not isinstance(raw_families, list):
            raise ValueError
        values["source_backend"] = DurableBackend(values["source_backend"])
        values["target_backend"] = DurableBackend(values["target_backend"])
        values["phase"] = MigrationPhase(values["phase"])
        values["authority"] = AuthoritySide(values["authority"])
        values["families"] = tuple(_progress_from_record(item) for item in raw_families)
        return MigrationCheckpoint(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored migration checkpoint is invalid.") from exc


def checkpoint_evidence_checksum(checkpoint: MigrationCheckpoint) -> str:
    """Hash the complete, canonical checkpoint without exposing family payloads."""

    if type(checkpoint) is not MigrationCheckpoint:
        raise ValueError("Migration checkpoint evidence is invalid.")
    encoded = json.dumps(
        checkpoint.to_record(),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def binding_eligible_checkpoint(checkpoint: object) -> bool:
    """Return whether immutable migration evidence may back a coordinated binding."""

    return bool(
        type(checkpoint) is MigrationCheckpoint
        and checkpoint.manifest_version == DURABLE_MANIFEST_VERSION
        and checkpoint.manifest_checksum == DURABLE_MANIFEST_CHECKSUM
        and checkpoint.source_backend is DurableBackend.SQLITE
        and checkpoint.target_backend is DurableBackend.POSTGRESQL
        and checkpoint.phase is MigrationPhase.TARGET_AUTHORITATIVE
        and checkpoint.authority is AuthoritySide.TARGET
        and checkpoint.families
        and tuple(item.family for item in checkpoint.families) == DURABLE_COPY_FAMILIES
        and all(
            item.verified
            and item.copy_complete
            and item.source_count == item.target_count
            and item.source_checksum == item.target_checksum
            and item.source_count is not None
            for item in checkpoint.families
        )
    )
