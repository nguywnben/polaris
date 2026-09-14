"""Storage-agnostic contracts for durable management identities.

The records in this module are deliberately small and strict.  They contain only
authorization identity data; profile attributes such as email and display name
must never become identity keys or durable authorization inputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol

from core.identity.authorization import ManagementRole, PrincipalType

IDENTITY_SCHEMA_VERSION = 1
IDENTITY_MIGRATION_ID = "management_identity_v1"
LOCAL_OWNER_ID = "local-owner"
LOCAL_OWNER_BINDING_ID = "binding-local-owner"
MAX_IDENTITY_PAGE_SIZE = 200

_MAX_ISSUER_LENGTH = 2048
_MAX_SUBJECT_LENGTH = 255
_MAX_TIMESTAMP_LENGTH = 64
_OPAQUE_ID_PATTERN = re.compile(r"^(?:idn|rbd)_[0-9a-f]{32}$")


class RoleBindingSource(StrEnum):
    LOCAL_BOOTSTRAP = "local_bootstrap"
    DIRECT_BINDING = "direct_binding"
    CLAIM_MAPPING = "claim_mapping"


class IdentityRepositoryError(RuntimeError):
    """Base error safe to report without leaking identity attributes."""


class IdentityAlreadyExists(IdentityRepositoryError):
    pass


class IdentityNotFound(IdentityRepositoryError):
    pass


class IdentityRevisionConflict(IdentityRepositoryError):
    pass


class IdentityOwnerInvariant(IdentityRepositoryError):
    pass


class IdentityStoreCorrupt(IdentityRepositoryError):
    pass


def _strict_positive_int(value: object, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} is invalid.")
    return value


def _identifier(value: object, *, prefix: str, label: str) -> str:
    if type(value) is not str or not _OPAQUE_ID_PATTERN.fullmatch(value):
        raise ValueError(f"{label} is invalid.")
    if not value.startswith(prefix):
        raise ValueError(f"{label} is invalid.")
    return value


def _identity_attribute(value: object, *, label: str, maximum: int) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise ValueError(f"{label} is invalid.")
    if value != value.strip() or any(ord(character) < 32 for character in value):
        raise ValueError(f"{label} is invalid.")
    return value


def _timestamp(value: object, label: str) -> str:
    if type(value) is not str or not value or len(value) > _MAX_TIMESTAMP_LENGTH:
        raise ValueError(f"{label} is invalid.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} is invalid.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} is invalid.")
    if parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"{label} must use UTC.")
    return value


def _now_text(now: datetime) -> str:
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Timestamp is invalid.")
    return now.astimezone(timezone.utc).isoformat()


def _exact_record(record: object, record_type: type) -> dict[str, object]:
    if type(record) is not dict:
        raise ValueError("Stored identity record is invalid.")
    expected = {field.name for field in fields(record_type)}
    if set(record) != expected:
        raise ValueError("Stored identity record is invalid.")
    return record


@dataclass(frozen=True, slots=True)
class IdentityRecord:
    schema_version: int
    identity_id: str
    principal_type: PrincipalType
    issuer: str | None = None
    subject: str | None = None
    enabled: bool = True
    revision: int = 1
    authorization_epoch: int = 1
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != IDENTITY_SCHEMA_VERSION:
            raise ValueError("Identity schema version is unsupported.")
        if type(self.principal_type) is not PrincipalType:
            raise ValueError("Principal type is invalid.")
        if type(self.enabled) is not bool:
            raise ValueError("Identity enabled state is invalid.")
        _strict_positive_int(self.revision, "Identity revision")
        _strict_positive_int(self.authorization_epoch, "Authorization epoch")
        created_at = _timestamp(self.created_at, "Created timestamp")
        updated_at = _timestamp(self.updated_at, "Updated timestamp")
        if datetime.fromisoformat(updated_at) < datetime.fromisoformat(created_at):
            raise ValueError("Identity timestamps are inconsistent.")

        if self.principal_type is PrincipalType.LOCAL_OWNER:
            if self.identity_id != LOCAL_OWNER_ID:
                raise ValueError("Local-owner identity is invalid.")
            if self.issuer is not None or self.subject is not None or not self.enabled:
                raise ValueError("Local-owner identity is inconsistent.")
        elif self.principal_type is PrincipalType.OIDC_USER:
            _identifier(self.identity_id, prefix="idn_", label="Identity identifier")
            _identity_attribute(self.issuer, label="OIDC issuer", maximum=_MAX_ISSUER_LENGTH)
            _identity_attribute(self.subject, label="OIDC subject", maximum=_MAX_SUBJECT_LENGTH)
        else:
            raise ValueError("Durable principal type is unsupported.")

    @classmethod
    def local_owner(
        cls,
        *,
        now: datetime,
        identity_id: str = LOCAL_OWNER_ID,
    ) -> IdentityRecord:
        timestamp = _now_text(now)
        return cls(
            schema_version=IDENTITY_SCHEMA_VERSION,
            identity_id=identity_id,
            principal_type=PrincipalType.LOCAL_OWNER,
            enabled=True,
            revision=1,
            authorization_epoch=1,
            created_at=timestamp,
            updated_at=timestamp,
        )

    @classmethod
    def oidc_user(
        cls,
        *,
        identity_id: str,
        issuer: str,
        subject: str,
        now: datetime,
    ) -> IdentityRecord:
        timestamp = _now_text(now)
        return cls(
            schema_version=IDENTITY_SCHEMA_VERSION,
            identity_id=identity_id,
            principal_type=PrincipalType.OIDC_USER,
            issuer=issuer,
            subject=subject,
            enabled=True,
            revision=1,
            authorization_epoch=1,
            created_at=timestamp,
            updated_at=timestamp,
        )

    @property
    def stable_identity(self) -> str | tuple[str, str]:
        if self.principal_type is PrincipalType.OIDC_USER:
            return (self.issuer or "", self.subject or "")
        return self.identity_id

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "identity_id": self.identity_id,
            "principal_type": self.principal_type.value,
            "issuer": self.issuer,
            "subject": self.subject,
            "enabled": self.enabled,
            "revision": self.revision,
            "authorization_epoch": self.authorization_epoch,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def __repr__(self) -> str:
        return (
            "IdentityRecord("
            f"identity_id={self.identity_id!r}, principal_type={self.principal_type!r}, "
            f"enabled={self.enabled!r}, revision={self.revision!r}, "
            f"authorization_epoch={self.authorization_epoch!r})"
        )


@dataclass(frozen=True, slots=True)
class RoleBindingRecord:
    schema_version: int
    binding_id: str
    identity_id: str
    role: ManagementRole
    source: RoleBindingSource
    revision: int
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != IDENTITY_SCHEMA_VERSION:
            raise ValueError("Role-binding schema version is unsupported.")
        if type(self.role) is not ManagementRole:
            raise ValueError("Role is invalid.")
        if type(self.source) is not RoleBindingSource:
            raise ValueError("Role-binding source is invalid.")
        _strict_positive_int(self.revision, "Role-binding revision")
        created_at = _timestamp(self.created_at, "Created timestamp")
        updated_at = _timestamp(self.updated_at, "Updated timestamp")
        if datetime.fromisoformat(updated_at) < datetime.fromisoformat(created_at):
            raise ValueError("Role-binding timestamps are inconsistent.")

        if self.source is RoleBindingSource.LOCAL_BOOTSTRAP:
            if (
                self.binding_id != LOCAL_OWNER_BINDING_ID
                or self.identity_id != LOCAL_OWNER_ID
                or self.role is not ManagementRole.OWNER
            ):
                raise ValueError("Local-owner role binding is inconsistent.")
        else:
            _identifier(self.binding_id, prefix="rbd_", label="Binding identifier")
            _identifier(self.identity_id, prefix="idn_", label="Identity identifier")
            if self.source is RoleBindingSource.CLAIM_MAPPING and self.role is ManagementRole.OWNER:
                raise ValueError("OIDC claims cannot assign the owner role.")

    @classmethod
    def local_owner(cls, *, now: datetime) -> RoleBindingRecord:
        timestamp = _now_text(now)
        return cls(
            schema_version=IDENTITY_SCHEMA_VERSION,
            binding_id=LOCAL_OWNER_BINDING_ID,
            identity_id=LOCAL_OWNER_ID,
            role=ManagementRole.OWNER,
            source=RoleBindingSource.LOCAL_BOOTSTRAP,
            revision=1,
            created_at=timestamp,
            updated_at=timestamp,
        )

    @classmethod
    def oidc_user(
        cls,
        *,
        binding_id: str,
        identity_id: str,
        role: ManagementRole,
        source: RoleBindingSource,
        now: datetime,
    ) -> RoleBindingRecord:
        timestamp = _now_text(now)
        return cls(
            schema_version=IDENTITY_SCHEMA_VERSION,
            binding_id=binding_id,
            identity_id=identity_id,
            role=role,
            source=source,
            revision=1,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "binding_id": self.binding_id,
            "identity_id": self.identity_id,
            "role": self.role.value,
            "source": self.source.value,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class ManagedIdentity:
    identity: IdentityRecord
    binding: RoleBindingRecord

    def __post_init__(self) -> None:
        if type(self.identity) is not IdentityRecord:
            raise ValueError("Managed identity record is invalid.")
        if type(self.binding) is not RoleBindingRecord:
            raise ValueError("Managed role binding is invalid.")
        if self.identity.identity_id != self.binding.identity_id:
            raise ValueError("Managed identity and role binding do not match.")


@dataclass(frozen=True, slots=True)
class IdentityPageCursor:
    created_at: str
    identity_id: str

    def __post_init__(self) -> None:
        _timestamp(self.created_at, "Identity cursor timestamp")
        if self.identity_id != LOCAL_OWNER_ID:
            _identifier(self.identity_id, prefix="idn_", label="Identity cursor identifier")

    @classmethod
    def from_identity(cls, identity: IdentityRecord) -> IdentityPageCursor:
        if type(identity) is not IdentityRecord:
            raise ValueError("Identity cursor source is invalid.")
        return cls(identity.created_at, identity.identity_id)


@dataclass(frozen=True, slots=True)
class OidcPolicyRevisionRecord:
    schema_version: int
    revision: int
    authorization_epoch: int
    updated_at: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != IDENTITY_SCHEMA_VERSION:
            raise ValueError("OIDC policy schema version is unsupported.")
        _strict_positive_int(self.revision, "OIDC policy revision")
        _strict_positive_int(self.authorization_epoch, "Authorization epoch")
        _timestamp(self.updated_at, "Updated timestamp")

    @classmethod
    def initial(cls, *, now: datetime) -> OidcPolicyRevisionRecord:
        return cls(IDENTITY_SCHEMA_VERSION, 1, 1, _now_text(now))

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "authorization_epoch": self.authorization_epoch,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class IdentityMigrationRecord:
    migration_id: str
    schema_version: int
    applied_at: str

    def __post_init__(self) -> None:
        if self.migration_id != IDENTITY_MIGRATION_ID:
            raise ValueError("Identity migration is invalid.")
        if type(self.schema_version) is not int or self.schema_version != IDENTITY_SCHEMA_VERSION:
            raise ValueError("Identity migration version is unsupported.")
        _timestamp(self.applied_at, "Migration timestamp")

    @classmethod
    def applied(cls, *, now: datetime) -> IdentityMigrationRecord:
        return cls(IDENTITY_MIGRATION_ID, IDENTITY_SCHEMA_VERSION, _now_text(now))

    def to_record(self) -> dict[str, object]:
        return {
            "migration_id": self.migration_id,
            "schema_version": self.schema_version,
            "applied_at": self.applied_at,
        }


def identity_from_record(record: object) -> IdentityRecord:
    values = _exact_record(record, IdentityRecord)
    try:
        return IdentityRecord(
            **{
                **values,
                "principal_type": PrincipalType(values["principal_type"]),
            }
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored identity record is invalid.") from exc


def role_binding_from_record(record: object) -> RoleBindingRecord:
    values = _exact_record(record, RoleBindingRecord)
    try:
        return RoleBindingRecord(
            **{
                **values,
                "role": ManagementRole(values["role"]),
                "source": RoleBindingSource(values["source"]),
            }
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored role-binding record is invalid.") from exc


def oidc_policy_revision_from_record(record: object) -> OidcPolicyRevisionRecord:
    values = _exact_record(record, OidcPolicyRevisionRecord)
    try:
        return OidcPolicyRevisionRecord(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored OIDC policy record is invalid.") from exc


def migration_from_record(record: object) -> IdentityMigrationRecord:
    values = _exact_record(record, IdentityMigrationRecord)
    try:
        return IdentityMigrationRecord(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored identity migration is invalid.") from exc


class IdentityRepository(Protocol):
    async def initialize(self) -> None: ...

    async def get_identity(self, identity_id: str) -> ManagedIdentity | None: ...

    async def get_identity_by_oidc(
        self, *, issuer: str, subject: str
    ) -> ManagedIdentity | None: ...

    async def list_identities(
        self,
        *,
        limit: int = 100,
        after: IdentityPageCursor | None = None,
    ) -> list[ManagedIdentity]: ...

    async def create_oidc_identity(
        self,
        *,
        issuer: str,
        subject: str,
        role: ManagementRole,
        source: RoleBindingSource = RoleBindingSource.DIRECT_BINDING,
    ) -> ManagedIdentity: ...

    async def set_identity_enabled(
        self, *, identity_id: str, enabled: bool, expected_revision: int
    ) -> ManagedIdentity: ...

    async def set_role(
        self,
        *,
        identity_id: str,
        role: ManagementRole,
        source: RoleBindingSource,
        expected_revision: int,
    ) -> ManagedIdentity: ...

    async def get_oidc_policy_revision(self) -> OidcPolicyRevisionRecord: ...

    async def advance_oidc_policy_revision(
        self, *, expected_revision: int
    ) -> OidcPolicyRevisionRecord: ...

    async def get_migration(self) -> IdentityMigrationRecord: ...
