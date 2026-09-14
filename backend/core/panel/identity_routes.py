"""Bounded enterprise identity and session management resources."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import time
from dataclasses import dataclass
from typing import Annotated, Literal

import config
from core.identity import (
    SESSION_TOKEN_PREFIX,
    AuthorizationDenied,
    IdentityAlreadyExists,
    IdentityNotFound,
    IdentityOwnerInvariant,
    IdentityPageCursor,
    IdentityRevisionConflict,
    ManagedIdentity,
    ManagedSession,
    ManagementPermission,
    ManagementPrincipal,
    ManagementRole,
    OidcConfigurationError,
    OidcRoleSource,
    PrincipalType,
    RoleBindingSource,
    get_session_service,
    load_oidc_configuration,
    require_permission,
)
from core.storage_adapter import get_storage_adapter
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from log import log
from pydantic import BaseModel, ConfigDict, Field

from .auth_support import recovery_local_only_enabled

router = APIRouter(prefix="/api/identity", tags=["identity"])

MAX_IDENTITY_API_PAGE_SIZE = 100
MAX_SESSION_API_PAGE_SIZE = 100
_IDENTITY_CURSOR_MAX_LENGTH = 512


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrincipalResponse(_StrictModel):
    identity_id: str
    principal_type: str
    role: str
    role_source: str
    permissions: list[str]


class SessionResponse(_StrictModel):
    reference: str
    identity_id: str
    principal_type: str
    role: str
    role_source: str
    authentication_method: str
    issued_at: float
    last_seen_at: float
    idle_expires_at: float
    absolute_expires_at: float
    current: bool = False


class SessionPageResponse(_StrictModel):
    sessions: list[SessionResponse]
    next_cursor: str | None
    page_size: int
    has_more: bool


class IdentityResponse(_StrictModel):
    identity_id: str
    principal_type: str
    issuer: str | None
    subject: str | None
    enabled: bool
    revision: int
    authorization_epoch: int
    created_at: str
    updated_at: str
    binding_id: str
    role: str
    role_source: str
    binding_revision: int


class IdentityPageResponse(_StrictModel):
    identities: list[IdentityResponse]
    next_cursor: str | None
    page_size: int
    has_more: bool


class CurrentSessionResponse(_StrictModel):
    principal: PrincipalResponse
    authentication_context: Literal["opaque_session", "legacy_session", "virtual_key"]
    session: SessionResponse | None


class OidcPolicyResponse(_StrictModel):
    enabled: bool
    readiness: Literal["disabled", "ready", "invalid"]
    secret_configured: bool
    revision: int
    authorization_epoch: int
    issuer: str | None = None
    redirect_uri: str | None = None
    scopes: list[str] = Field(default_factory=list)
    role_mapping_count: int = 0
    updated_at: str


class RecoveryStatusResponse(_StrictModel):
    local_owner_enabled: bool
    password_configured: bool
    ingress_policy: Literal["direct_loopback_only", "network_reachable"]
    ready: bool


class CreateIdentityRequest(_StrictModel):
    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(min_length=1, max_length=255)
    role: ManagementRole


class SetIdentityEnabledRequest(_StrictModel):
    enabled: bool = Field(strict=True)
    expected_revision: int = Field(ge=1, strict=True)


class SetRoleBindingRequest(_StrictModel):
    role: ManagementRole
    expected_revision: int = Field(ge=1, strict=True)


class AdvanceOidcPolicyRequest(_StrictModel):
    expected_revision: int = Field(ge=1, strict=True)


class OidcPolicyAdvanceResponse(_StrictModel):
    revision: int
    authorization_epoch: int
    updated_at: str
    revoked_sessions: int
    revocation_complete: bool


class SessionRevocationResponse(_StrictModel):
    revoked: bool


@dataclass(frozen=True, slots=True)
class _ManagementContext:
    token: str
    principal: ManagementPrincipal


async def _management_context(
    request: Request,
    token: str = Depends(verify_panel_token),
) -> _ManagementContext:
    principal = getattr(request.state, "management_principal", None)
    if type(principal) is not ManagementPrincipal:
        raise HTTPException(status_code=500, detail="Management identity is unavailable.")
    return _ManagementContext(token=str(token), principal=principal)


ManagementContext = Annotated[_ManagementContext, Depends(_management_context)]


async def _identity_repository():
    storage = await get_storage_adapter()
    return await storage.create_identity_repository()


def _require_owner_management(principal: ManagementPrincipal) -> None:
    try:
        require_permission(principal, ManagementPermission.OWNERS_MANAGE)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail="Management permission denied.") from exc


def _identity_response(managed: ManagedIdentity) -> IdentityResponse:
    identity = managed.identity
    binding = managed.binding
    return IdentityResponse(
        identity_id=identity.identity_id,
        principal_type=identity.principal_type.value,
        issuer=identity.issuer,
        subject=identity.subject,
        enabled=identity.enabled,
        revision=identity.revision,
        authorization_epoch=identity.authorization_epoch,
        created_at=identity.created_at,
        updated_at=identity.updated_at,
        binding_id=binding.binding_id,
        role=binding.role.value,
        role_source=binding.source.value,
        binding_revision=binding.revision,
    )


def _encode_identity_cursor(managed: ManagedIdentity) -> str:
    payload = json.dumps(
        [managed.identity.created_at, managed.identity.identity_id],
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_identity_cursor(value: str | None) -> IdentityPageCursor | None:
    if value is None:
        return None
    if type(value) is not str or not 1 <= len(value) <= _IDENTITY_CURSOR_MAX_LENGTH:
        raise HTTPException(status_code=400, detail="Identity cursor is invalid.")
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = base64.b64decode(padded, altchars=b"-_", validate=True)
        decoded = json.loads(payload)
        if type(decoded) is not list or len(decoded) != 2:
            raise ValueError
        return IdentityPageCursor(decoded[0], decoded[1])
    except (binascii.Error, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Identity cursor is invalid.") from None


def _principal_from_managed(managed: ManagedIdentity) -> ManagementPrincipal:
    if managed.identity.principal_type is PrincipalType.LOCAL_OWNER:
        return ManagementPrincipal.local_owner(managed.identity.identity_id)
    return ManagementPrincipal.oidc_user(
        issuer=managed.identity.issuer or "",
        subject=managed.identity.subject or "",
        role=managed.binding.role,
        role_source=(
            OidcRoleSource.DIRECT_BINDING
            if managed.binding.source is RoleBindingSource.DIRECT_BINDING
            else OidcRoleSource.CLAIM_MAPPING
        ),
    )


async def _identity_id_for_principal(repository, principal: ManagementPrincipal) -> str:
    if principal.principal_type is PrincipalType.LOCAL_OWNER:
        return principal.principal_id
    if principal.principal_type is PrincipalType.OIDC_USER:
        managed = await repository.get_identity_by_oidc(
            issuer=principal.issuer or "",
            subject=principal.subject or "",
        )
        if type(managed) is ManagedIdentity:
            return managed.identity.identity_id
    raise HTTPException(status_code=409, detail="Session identity is unavailable.")


def _role_source(principal: ManagementPrincipal) -> str:
    return principal.role_source.value if principal.role_source is not None else "local_bootstrap"


async def _session_response(
    repository,
    managed: ManagedSession,
    *,
    current_reference: str = "",
) -> SessionResponse:
    identity_id = await _identity_id_for_principal(repository, managed.principal)
    return SessionResponse(
        reference=managed.reference,
        identity_id=identity_id,
        principal_type=managed.principal.principal_type.value,
        role=managed.principal.role.value if managed.principal.role is not None else "",
        role_source=_role_source(managed.principal),
        authentication_method=managed.authentication_method.value,
        issued_at=managed.issued_at,
        last_seen_at=managed.last_seen_at,
        idle_expires_at=managed.idle_expires_at,
        absolute_expires_at=managed.absolute_expires_at,
        current=hmac_compare(managed.reference, current_reference),
    )


def hmac_compare(left: str, right: str) -> bool:
    import hmac

    return bool(right) and hmac.compare_digest(left, right)


def _raise_identity_error(exc: Exception) -> None:
    if isinstance(exc, IdentityAlreadyExists):
        raise HTTPException(status_code=409, detail="Management identity already exists.")
    if isinstance(exc, IdentityNotFound):
        raise HTTPException(status_code=404, detail="Management identity was not found.")
    if isinstance(exc, IdentityRevisionConflict):
        raise HTTPException(status_code=409, detail="Management identity revision conflict.")
    if isinstance(exc, IdentityOwnerInvariant):
        raise HTTPException(status_code=409, detail="Owner safety policy rejected the change.")
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail="Identity request is invalid.")
    log.error(f"Identity management operation failed: {type(exc).__name__}")
    raise HTTPException(status_code=503, detail="Identity service is unavailable.")


async def _revoke_principal_sessions(principal: ManagementPrincipal) -> None:
    """Eagerly remove sessions; the durable authorization epoch remains the fail-safe."""

    try:
        await get_session_service().revoke_principal(principal)
    except Exception as exc:
        log.error(f"Eager identity-session revocation failed: {type(exc).__name__}")


@router.get("/session", response_model=CurrentSessionResponse)
async def get_current_session(context: ManagementContext):
    try:
        repository = await _identity_repository()
        if context.principal.principal_type is PrincipalType.VIRTUAL_KEY:
            identity_id = context.principal.principal_id
        else:
            identity_id = await _identity_id_for_principal(repository, context.principal)
        principal = PrincipalResponse(
            identity_id=identity_id,
            principal_type=context.principal.principal_type.value,
            role=context.principal.role.value if context.principal.role is not None else "",
            role_source=_role_source(context.principal),
            permissions=sorted(permission.value for permission in context.principal.permissions),
        )
        if context.principal.principal_type is PrincipalType.VIRTUAL_KEY:
            return CurrentSessionResponse(
                principal=principal,
                authentication_context="virtual_key",
                session=None,
            )
        if not context.token.startswith(SESSION_TOKEN_PREFIX):
            return CurrentSessionResponse(
                principal=principal,
                authentication_context="legacy_session",
                session=None,
            )
        managed = await get_session_service().managed_for_token(context.token, now=time.time())
        session = await _session_response(
            repository,
            managed,
            current_reference=managed.reference,
        )
        return CurrentSessionResponse(
            principal=principal,
            authentication_context="opaque_session",
            session=session,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _raise_identity_error(exc)


@router.get("/identities", response_model=IdentityPageResponse)
async def list_identities(
    context: ManagementContext,
    page_size: int = Query(default=50, ge=1, le=MAX_IDENTITY_API_PAGE_SIZE),
    cursor: str | None = Query(default=None, min_length=1, max_length=512),
):
    del context
    try:
        repository = await _identity_repository()
        managed = await repository.list_identities(
            limit=page_size + 1,
            after=_decode_identity_cursor(cursor),
        )
        has_more = len(managed) > page_size
        page = managed[:page_size]
        return IdentityPageResponse(
            identities=[_identity_response(item) for item in page],
            next_cursor=_encode_identity_cursor(page[-1]) if has_more and page else None,
            page_size=page_size,
            has_more=has_more,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _raise_identity_error(exc)


@router.post("/identities", response_model=IdentityResponse, status_code=201)
async def create_identity(payload: CreateIdentityRequest, context: ManagementContext):
    if payload.role is ManagementRole.OWNER:
        _require_owner_management(context.principal)
    try:
        repository = await _identity_repository()
        created = await repository.create_oidc_identity(
            issuer=payload.issuer,
            subject=payload.subject,
            role=payload.role,
            source=RoleBindingSource.DIRECT_BINDING,
        )
        return _identity_response(created)
    except Exception as exc:
        _raise_identity_error(exc)


@router.patch("/identities/{identity_id}", response_model=IdentityResponse)
async def set_identity_enabled(
    payload: SetIdentityEnabledRequest,
    context: ManagementContext,
    identity_id: str = Path(min_length=1, max_length=64),
):
    try:
        repository = await _identity_repository()
        current = await repository.get_identity(identity_id)
        if current is None:
            raise IdentityNotFound("Management identity was not found.")
        if current.binding.role is ManagementRole.OWNER:
            _require_owner_management(context.principal)
        updated = await repository.set_identity_enabled(
            identity_id=identity_id,
            enabled=payload.enabled,
            expected_revision=payload.expected_revision,
        )
        await _revoke_principal_sessions(_principal_from_managed(current))
        return _identity_response(updated)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_identity_error(exc)


@router.put("/identities/{identity_id}/role-binding", response_model=IdentityResponse)
async def set_role_binding(
    payload: SetRoleBindingRequest,
    context: ManagementContext,
    identity_id: str = Path(min_length=1, max_length=64),
):
    try:
        repository = await _identity_repository()
        current = await repository.get_identity(identity_id)
        if current is None:
            raise IdentityNotFound("Management identity was not found.")
        if ManagementRole.OWNER in {current.binding.role, payload.role}:
            _require_owner_management(context.principal)
        updated = await repository.set_role(
            identity_id=identity_id,
            role=payload.role,
            source=RoleBindingSource.DIRECT_BINDING,
            expected_revision=payload.expected_revision,
        )
        await _revoke_principal_sessions(_principal_from_managed(current))
        return _identity_response(updated)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_identity_error(exc)


@router.get("/sessions", response_model=SessionPageResponse)
async def list_sessions(
    context: ManagementContext,
    page_size: int = Query(default=50, ge=1, le=MAX_SESSION_API_PAGE_SIZE),
    cursor: str | None = Query(default=None, min_length=1, max_length=64),
):
    try:
        service = get_session_service()
        current_reference = (
            await service.reference_for_token(context.token, now=time.time())
            if context.token.startswith(SESSION_TOKEN_PREFIX)
            else ""
        )
        managed = await service.list_active(
            limit=page_size + 1,
            after_reference=cursor,
            now=time.time(),
        )
        has_more = len(managed) > page_size
        page = managed[:page_size]
        repository = await _identity_repository()
        semaphore = asyncio.Semaphore(8)

        async def render(item: ManagedSession) -> SessionResponse:
            async with semaphore:
                return await _session_response(
                    repository,
                    item,
                    current_reference=current_reference,
                )

        sessions = await asyncio.gather(*(render(item) for item in page))
        return SessionPageResponse(
            sessions=list(sessions),
            next_cursor=page[-1].reference if has_more and page else None,
            page_size=page_size,
            has_more=has_more,
        )
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Session cursor is invalid.") from None
    except Exception as exc:
        log.error(f"Session inventory operation failed: {type(exc).__name__}")
        raise HTTPException(status_code=503, detail="Session service is unavailable.") from None


@router.post(
    "/sessions/{session_reference}/revoke",
    response_model=SessionRevocationResponse,
)
async def revoke_session(
    context: ManagementContext,
    session_reference: str = Path(pattern=r"^ssr_[0-9a-f]{32}$"),
):
    del context
    try:
        revoked = await get_session_service().revoke_reference(session_reference)
        if not revoked:
            raise HTTPException(status_code=404, detail="Management session was not found.")
        return SessionRevocationResponse(revoked=True)
    except HTTPException:
        raise
    except Exception as exc:
        log.error(f"Session revocation failed: {type(exc).__name__}")
        raise HTTPException(status_code=503, detail="Session service is unavailable.") from None


def _secret_configured_marker() -> bool:
    sources = (
        bool(os.getenv("OIDC_CLIENT_SECRET")),
        bool(os.getenv("OIDC_CLIENT_SECRET_FILE")),
    )
    return sum(sources) == 1


@router.get("/oidc-policy", response_model=OidcPolicyResponse)
async def get_oidc_policy(context: ManagementContext):
    del context
    try:
        repository = await _identity_repository()
        revision = await repository.get_oidc_policy_revision()
        try:
            configuration = load_oidc_configuration(revision)
        except OidcConfigurationError:
            return OidcPolicyResponse(
                enabled=os.getenv("OIDC_ENABLED", "false").strip().lower() == "true",
                readiness="invalid",
                secret_configured=_secret_configured_marker(),
                revision=revision.revision,
                authorization_epoch=revision.authorization_epoch,
                updated_at=revision.updated_at,
            )
        policy = configuration.policy
        return OidcPolicyResponse(
            enabled=policy.enabled,
            readiness="ready" if policy.enabled else "disabled",
            secret_configured=_secret_configured_marker(),
            revision=policy.revision,
            authorization_epoch=policy.authorization_epoch,
            issuer=policy.issuer,
            redirect_uri=policy.redirect_uri,
            scopes=list(policy.scopes),
            role_mapping_count=len(policy.role_mappings),
            updated_at=revision.updated_at,
        )
    except Exception as exc:
        _raise_identity_error(exc)


@router.post("/oidc-policy/advance", response_model=OidcPolicyAdvanceResponse)
async def advance_oidc_policy(
    payload: AdvanceOidcPolicyRequest,
    context: ManagementContext,
):
    del context
    try:
        repository = await _identity_repository()
        revision = await repository.advance_oidc_policy_revision(
            expected_revision=payload.expected_revision
        )
        try:
            revoked = await get_session_service().revoke_oidc_sessions()
            revocation_complete = True
        except Exception as exc:
            log.error(f"Eager OIDC-session revocation failed: {type(exc).__name__}")
            revoked = 0
            revocation_complete = False
        return OidcPolicyAdvanceResponse(
            revision=revision.revision,
            authorization_epoch=revision.authorization_epoch,
            updated_at=revision.updated_at,
            revoked_sessions=revoked,
            revocation_complete=revocation_complete,
        )
    except Exception as exc:
        _raise_identity_error(exc)


@router.get("/recovery", response_model=RecoveryStatusResponse)
async def get_recovery_status(context: ManagementContext):
    del context
    try:
        repository = await _identity_repository()
        owner = await repository.get_identity("local-owner")
        enabled = type(owner) is ManagedIdentity and owner.identity.enabled
        configured = await config.has_password_configured()
        ingress_policy = (
            "direct_loopback_only" if recovery_local_only_enabled() else "network_reachable"
        )
        return RecoveryStatusResponse(
            local_owner_enabled=enabled,
            password_configured=configured,
            ingress_policy=ingress_policy,
            ready=enabled and configured,
        )
    except Exception as exc:
        _raise_identity_error(exc)
