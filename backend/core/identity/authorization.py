"""Pure management principal and permission contracts.

This module deliberately has no FastAPI, storage, or session dependency. Request
authentication adapters construct a typed principal; route integration then asks
this module for an authorization decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class PrincipalType(StrEnum):
    LOCAL_OWNER = "local_owner"
    OIDC_USER = "oidc_user"
    VIRTUAL_KEY = "virtual_key"
    SYSTEM = "system"


class ManagementRole(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    SECURITY_ADMIN = "security_admin"
    OWNER = "owner"


class ManagementPermission(StrEnum):
    DASHBOARD_READ = "dashboard.read"
    CONFIGURATION_READ = "configuration.read"
    CONFIGURATION_MANAGE = "configuration.manage"
    CREDENTIALS_READ = "credentials.read"
    CREDENTIALS_OPERATE = "credentials.operate"
    CREDENTIALS_MANAGE = "credentials.manage"
    CREDENTIALS_EXPORT = "credentials.export"
    PROVIDERS_READ = "providers.read"
    PROVIDERS_MANAGE = "providers.manage"
    ROUTING_MANAGE = "routing.manage"
    QUALITY_READ = "quality.read"
    QUALITY_MANAGE = "quality.manage"
    ACCESS_READ = "access.read"
    ACCESS_MANAGE = "access.manage"
    AUDIT_READ = "audit.read"
    AUDIT_MANAGE = "audit.manage"
    AUDIT_EXPORT = "audit.export"
    TRACES_READ = "traces.read"
    TRACES_MANAGE = "traces.manage"
    TRACES_EXPORT = "traces.export"
    LOGS_READ = "logs.read"
    LOGS_MANAGE = "logs.manage"
    IDENTITY_READ = "identity.read"
    IDENTITY_MANAGE = "identity.manage"
    SESSIONS_MANAGE = "sessions.manage"
    OIDC_MANAGE = "oidc.manage"
    BACKUP_EXPORT = "backup.export"
    BACKUP_RESTORE = "backup.restore"
    ROOT_KEY_READ = "root_key.read"
    ROOT_KEY_ROTATE = "root_key.rotate"
    OWNERS_MANAGE = "owners.manage"
    RECOVERY_MANAGE = "recovery.manage"


class OidcRoleSource(StrEnum):
    DIRECT_BINDING = "direct_binding"
    CLAIM_MAPPING = "claim_mapping"


class AuthorizationReason(StrEnum):
    ROLE_PERMISSION = "role_permission"
    GRANULAR_PERMISSION = "granular_permission"
    LEGACY_MANAGEMENT_SCOPE = "legacy_management_scope"
    PERMISSION_NOT_GRANTED = "permission_not_granted"
    INVALID_PERMISSION = "invalid_permission"
    INVALID_PRINCIPAL = "invalid_principal"
    SYSTEM_PRINCIPAL_DENIED = "system_principal_denied"


class InvalidPrincipal(ValueError):
    """Raised when a principal cannot satisfy the closed domain contract."""


_VIEWER_PERMISSIONS = frozenset(
    {
        ManagementPermission.DASHBOARD_READ,
        ManagementPermission.CONFIGURATION_READ,
        ManagementPermission.CREDENTIALS_READ,
        ManagementPermission.PROVIDERS_READ,
        ManagementPermission.QUALITY_READ,
        ManagementPermission.ACCESS_READ,
        ManagementPermission.AUDIT_READ,
        ManagementPermission.TRACES_READ,
        ManagementPermission.LOGS_READ,
        ManagementPermission.IDENTITY_READ,
    }
)
_OPERATOR_PERMISSIONS = _VIEWER_PERMISSIONS | {
    ManagementPermission.CREDENTIALS_OPERATE,
    ManagementPermission.ROUTING_MANAGE,
    ManagementPermission.QUALITY_MANAGE,
    ManagementPermission.LOGS_MANAGE,
}
_SECURITY_ADMIN_PERMISSIONS = _VIEWER_PERMISSIONS | {
    ManagementPermission.CREDENTIALS_OPERATE,
    ManagementPermission.CREDENTIALS_MANAGE,
    ManagementPermission.CREDENTIALS_EXPORT,
    ManagementPermission.PROVIDERS_MANAGE,
    ManagementPermission.ACCESS_MANAGE,
    ManagementPermission.AUDIT_MANAGE,
    ManagementPermission.AUDIT_EXPORT,
    ManagementPermission.TRACES_MANAGE,
    ManagementPermission.TRACES_EXPORT,
    ManagementPermission.IDENTITY_MANAGE,
    ManagementPermission.SESSIONS_MANAGE,
    ManagementPermission.OIDC_MANAGE,
    ManagementPermission.BACKUP_EXPORT,
}
_OWNER_PERMISSIONS = (
    _OPERATOR_PERMISSIONS
    | _SECURITY_ADMIN_PERMISSIONS
    | {
        ManagementPermission.CONFIGURATION_MANAGE,
        ManagementPermission.ROOT_KEY_READ,
        ManagementPermission.ROOT_KEY_ROTATE,
        ManagementPermission.BACKUP_RESTORE,
        ManagementPermission.OWNERS_MANAGE,
        ManagementPermission.RECOVERY_MANAGE,
    }
)

_ROLE_PERMISSIONS = {
    ManagementRole.VIEWER: _VIEWER_PERMISSIONS,
    ManagementRole.OPERATOR: _OPERATOR_PERMISSIONS,
    ManagementRole.SECURITY_ADMIN: _SECURITY_ADMIN_PERMISSIONS,
    ManagementRole.OWNER: _OWNER_PERMISSIONS,
}

# These sets preserve only the routes that existed before Wave 4. They are
# intentionally explicit so a future permission cannot leak into a broad key.
_LEGACY_READ_PERMISSIONS = (
    _VIEWER_PERMISSIONS
    | {
        ManagementPermission.CREDENTIALS_EXPORT,
        ManagementPermission.AUDIT_EXPORT,
        ManagementPermission.TRACES_EXPORT,
        ManagementPermission.ROOT_KEY_READ,
    }
) - {ManagementPermission.IDENTITY_READ}
_LEGACY_WRITE_PERMISSIONS = _LEGACY_READ_PERMISSIONS | {
    ManagementPermission.CONFIGURATION_MANAGE,
    ManagementPermission.CREDENTIALS_OPERATE,
    ManagementPermission.CREDENTIALS_MANAGE,
    ManagementPermission.CREDENTIALS_EXPORT,
    ManagementPermission.PROVIDERS_MANAGE,
    ManagementPermission.ROUTING_MANAGE,
    ManagementPermission.QUALITY_MANAGE,
    ManagementPermission.ACCESS_MANAGE,
    ManagementPermission.AUDIT_MANAGE,
    ManagementPermission.AUDIT_EXPORT,
    ManagementPermission.TRACES_MANAGE,
    ManagementPermission.TRACES_EXPORT,
    ManagementPermission.LOGS_MANAGE,
    ManagementPermission.BACKUP_EXPORT,
    ManagementPermission.BACKUP_RESTORE,
    ManagementPermission.ROOT_KEY_ROTATE,
}

LEGACY_MANAGEMENT_READ_SCOPE = "management:read"
LEGACY_MANAGEMENT_WRITE_SCOPE = "management:write"
MANAGEMENT_PERMISSION_SCOPE_PREFIX = "management:permission:"
_MAX_PRINCIPAL_ID_LENGTH = 128
_MAX_ISSUER_LENGTH = 2048
_MAX_SUBJECT_LENGTH = 255
_MAX_SCOPES = 64
_MAX_SCOPE_LENGTH = 160


def permissions_for_role(role: object) -> frozenset[ManagementPermission]:
    """Return a role's immutable bundle; untyped or unknown values get no rights."""
    if type(role) is not ManagementRole:
        return frozenset()
    return _ROLE_PERMISSIONS.get(role, frozenset())


def permission_scope(permission: ManagementPermission) -> str:
    """Return the additive granular virtual-key scope for one permission."""
    if type(permission) is not ManagementPermission:
        raise ValueError("A typed management permission is required.")
    return f"{MANAGEMENT_PERMISSION_SCOPE_PREFIX}{permission.value}"


def _validate_identifier(value: object, *, label: str, maximum: int) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise InvalidPrincipal(f"{label} is invalid.")
    if value != value.strip() or any(ord(character) < 32 for character in value):
        raise InvalidPrincipal(f"{label} is invalid.")
    return value


def _virtual_key_permissions(scopes: tuple[str, ...]) -> frozenset[ManagementPermission]:
    if type(scopes) is not tuple or len(scopes) > _MAX_SCOPES:
        raise InvalidPrincipal("Virtual-key scopes are invalid.")

    permissions: set[ManagementPermission] = set()
    normalized: set[str] = set()
    for scope in scopes:
        if type(scope) is not str or not scope or len(scope) > _MAX_SCOPE_LENGTH:
            raise InvalidPrincipal("Virtual-key scopes are invalid.")
        if scope != scope.strip() or any(ord(character) < 32 for character in scope):
            raise InvalidPrincipal("Virtual-key scopes are invalid.")
        normalized.add(scope)
        if not scope.startswith("management:"):
            continue
        if scope == LEGACY_MANAGEMENT_READ_SCOPE:
            permissions.update(_LEGACY_READ_PERMISSIONS)
            continue
        if scope == LEGACY_MANAGEMENT_WRITE_SCOPE:
            permissions.update(_LEGACY_WRITE_PERMISSIONS)
            continue
        if scope.startswith(MANAGEMENT_PERMISSION_SCOPE_PREFIX):
            value = scope.removeprefix(MANAGEMENT_PERMISSION_SCOPE_PREFIX)
            try:
                permissions.add(ManagementPermission(value))
            except ValueError as exc:
                raise InvalidPrincipal("Virtual-key scopes are invalid.") from exc
            continue
        raise InvalidPrincipal("Virtual-key scopes are invalid.")

    if (
        LEGACY_MANAGEMENT_WRITE_SCOPE in normalized
        and LEGACY_MANAGEMENT_READ_SCOPE not in normalized
    ):
        raise InvalidPrincipal("Legacy management write requires read scope.")
    return frozenset(permissions)


@dataclass(frozen=True, slots=True)
class ManagementPrincipal:
    """A validated identity with permissions derived only from trusted source data."""

    principal_type: PrincipalType
    principal_id: str = ""
    role: ManagementRole | None = None
    issuer: str | None = None
    subject: str | None = None
    role_source: OidcRoleSource | None = None
    scopes: tuple[str, ...] = ()
    permissions: frozenset[ManagementPermission] = field(init=False, repr=False)
    uses_legacy_management_scope: bool = field(init=False)

    def __post_init__(self) -> None:
        if type(self.principal_type) is not PrincipalType:
            raise InvalidPrincipal("Principal type is invalid.")
        if self.role is not None and type(self.role) is not ManagementRole:
            raise InvalidPrincipal("Principal role is invalid.")
        if self.role_source is not None and type(self.role_source) is not OidcRoleSource:
            raise InvalidPrincipal("OIDC role source is invalid.")

        permissions: frozenset[ManagementPermission]
        uses_legacy_scope = False
        if self.principal_type is PrincipalType.LOCAL_OWNER:
            _validate_identifier(
                self.principal_id,
                label="Local-owner identifier",
                maximum=_MAX_PRINCIPAL_ID_LENGTH,
            )
            if self.role is not ManagementRole.OWNER or any(
                value is not None for value in (self.issuer, self.subject, self.role_source)
            ):
                raise InvalidPrincipal("Local-owner principal is inconsistent.")
            if self.scopes:
                raise InvalidPrincipal("Local-owner principal cannot carry scopes.")
            permissions = permissions_for_role(self.role)
        elif self.principal_type is PrincipalType.OIDC_USER:
            if self.principal_id:
                raise InvalidPrincipal("OIDC principal uses issuer and subject identity.")
            _validate_identifier(
                self.issuer,
                label="OIDC issuer",
                maximum=_MAX_ISSUER_LENGTH,
            )
            _validate_identifier(
                self.subject,
                label="OIDC subject",
                maximum=_MAX_SUBJECT_LENGTH,
            )
            if self.role is None or self.role_source is None or self.scopes:
                raise InvalidPrincipal("OIDC principal is incomplete.")
            if (
                self.role_source is OidcRoleSource.CLAIM_MAPPING
                and self.role is ManagementRole.OWNER
            ):
                raise InvalidPrincipal("OIDC claims cannot assign the owner role.")
            permissions = permissions_for_role(self.role)
        elif self.principal_type is PrincipalType.VIRTUAL_KEY:
            _validate_identifier(
                self.principal_id,
                label="Virtual-key identifier",
                maximum=_MAX_PRINCIPAL_ID_LENGTH,
            )
            if self.role is not None or any(
                value is not None for value in (self.issuer, self.subject, self.role_source)
            ):
                raise InvalidPrincipal("Virtual-key principal is inconsistent.")
            permissions = _virtual_key_permissions(self.scopes)
            uses_legacy_scope = any(
                scope in {LEGACY_MANAGEMENT_READ_SCOPE, LEGACY_MANAGEMENT_WRITE_SCOPE}
                for scope in self.scopes
            )
        else:
            _validate_identifier(
                self.principal_id,
                label="System identifier",
                maximum=_MAX_PRINCIPAL_ID_LENGTH,
            )
            if (
                self.role is not None
                or self.scopes
                or any(value is not None for value in (self.issuer, self.subject, self.role_source))
            ):
                raise InvalidPrincipal("System principal is inconsistent.")
            permissions = frozenset()

        object.__setattr__(self, "permissions", permissions)
        object.__setattr__(self, "uses_legacy_management_scope", uses_legacy_scope)

    @classmethod
    def local_owner(cls, principal_id: str = "local-owner") -> ManagementPrincipal:
        return cls(
            principal_type=PrincipalType.LOCAL_OWNER,
            principal_id=principal_id,
            role=ManagementRole.OWNER,
        )

    @classmethod
    def oidc_user(
        cls,
        *,
        issuer: str,
        subject: str,
        role: ManagementRole,
        role_source: OidcRoleSource = OidcRoleSource.DIRECT_BINDING,
    ) -> ManagementPrincipal:
        return cls(
            principal_type=PrincipalType.OIDC_USER,
            role=role,
            issuer=issuer,
            subject=subject,
            role_source=role_source,
        )

    @classmethod
    def virtual_key(
        cls,
        key_id: str,
        *,
        scopes: tuple[str, ...] | list[str],
    ) -> ManagementPrincipal:
        if type(scopes) not in {tuple, list}:
            raise InvalidPrincipal("Virtual-key scopes are invalid.")
        return cls(
            principal_type=PrincipalType.VIRTUAL_KEY,
            principal_id=key_id,
            scopes=tuple(scopes),
        )

    @classmethod
    def system(cls, principal_id: str) -> ManagementPrincipal:
        return cls(principal_type=PrincipalType.SYSTEM, principal_id=principal_id)

    @property
    def stable_identity(self) -> str | tuple[str, str]:
        if self.principal_type is PrincipalType.OIDC_USER:
            return (self.issuer or "", self.subject or "")
        return self.principal_id


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    reason: AuthorizationReason
    principal_type: PrincipalType | None
    permission: ManagementPermission | None
    uses_legacy_management_scope: bool = False


class AuthorizationDenied(PermissionError):
    """A generic denial safe to translate at the HTTP boundary."""

    def __init__(self, decision: AuthorizationDecision) -> None:
        super().__init__("Management permission denied.")
        self.decision = decision
        self.reason = decision.reason


def evaluate_permission(
    principal: object,
    permission: object,
) -> AuthorizationDecision:
    """Evaluate one allowlisted permission without side effects or exceptions."""
    if type(principal) is not ManagementPrincipal:
        return AuthorizationDecision(
            allowed=False,
            reason=AuthorizationReason.INVALID_PRINCIPAL,
            principal_type=None,
            permission=None,
        )
    if type(permission) is not ManagementPermission:
        return AuthorizationDecision(
            allowed=False,
            reason=AuthorizationReason.INVALID_PERMISSION,
            principal_type=principal.principal_type,
            permission=None,
            uses_legacy_management_scope=principal.uses_legacy_management_scope,
        )
    if principal.principal_type is PrincipalType.SYSTEM:
        return AuthorizationDecision(
            allowed=False,
            reason=AuthorizationReason.SYSTEM_PRINCIPAL_DENIED,
            principal_type=principal.principal_type,
            permission=permission,
        )
    if permission not in principal.permissions:
        return AuthorizationDecision(
            allowed=False,
            reason=AuthorizationReason.PERMISSION_NOT_GRANTED,
            principal_type=principal.principal_type,
            permission=permission,
            uses_legacy_management_scope=principal.uses_legacy_management_scope,
        )

    if principal.principal_type is not PrincipalType.VIRTUAL_KEY:
        reason = AuthorizationReason.ROLE_PERMISSION
    elif permission_scope(permission) in principal.scopes:
        reason = AuthorizationReason.GRANULAR_PERMISSION
    else:
        reason = AuthorizationReason.LEGACY_MANAGEMENT_SCOPE
    return AuthorizationDecision(
        allowed=True,
        reason=reason,
        principal_type=principal.principal_type,
        permission=permission,
        uses_legacy_management_scope=principal.uses_legacy_management_scope,
    )


def require_permission(
    principal: object,
    permission: object,
) -> AuthorizationDecision:
    """Return the allow decision or raise a generic typed denial."""
    decision = evaluate_permission(principal, permission)
    if not decision.allowed:
        raise AuthorizationDenied(decision)
    return decision
