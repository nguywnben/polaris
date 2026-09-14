"""Fail-closed resolution from verified OIDC subjects to management principals."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from core.identity.authorization import ManagementPrincipal, ManagementRole, OidcRoleSource
from core.identity.oidc_id_token import VerifiedOidcIdToken
from core.identity.oidc_policy import OidcPolicy
from core.identity.repository import (
    IdentityAlreadyExists,
    IdentityRepository,
    IdentityRevisionConflict,
    ManagedIdentity,
    OidcPolicyRevisionRecord,
    RoleBindingSource,
)

_MAX_GROUPS = 128
_MAX_GROUP_LENGTH = 256


class OidcIdentityResolutionError(RuntimeError):
    """Content-free boundary for every OIDC authorization resolution failure."""

    def __init__(self) -> None:
        super().__init__("OIDC identity resolution failed.")


@dataclass(frozen=True, slots=True)
class ResolvedOidcIdentity:
    """Authorization snapshot used to issue a revision-bound management session."""

    principal: ManagementPrincipal
    identity_id: str
    identity_authorization_epoch: int
    binding_revision: int
    policy_revision: int
    policy_authorization_epoch: int

    def __post_init__(self) -> None:
        if (
            type(self.principal) is not ManagementPrincipal
            or self.principal.role is None
            or type(self.identity_id) is not str
            or not self.identity_id
            or any(
                type(value) is not int or value < 1
                for value in (
                    self.identity_authorization_epoch,
                    self.binding_revision,
                    self.policy_revision,
                    self.policy_authorization_epoch,
                )
            )
        ):
            raise ValueError("Resolved OIDC identity is invalid.")


def _claim_mapped_role(policy: OidcPolicy, groups: object) -> ManagementRole:
    if (
        type(groups) is not tuple
        or len(groups) > _MAX_GROUPS
        or any(
            type(group) is not str
            or not group
            or group != group.strip()
            or len(group) > _MAX_GROUP_LENGTH
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in group)
            for group in groups
        )
    ):
        raise OidcIdentityResolutionError
    mappings = dict(policy.role_mappings)
    roles = {mappings[group] for group in groups if group in mappings}
    if len(roles) != 1:
        raise OidcIdentityResolutionError
    try:
        role = ManagementRole(roles.pop())
    except ValueError as exc:  # pragma: no cover - policy construction guards this
        raise OidcIdentityResolutionError from exc
    if role is ManagementRole.OWNER:
        raise OidcIdentityResolutionError
    return role


def _role_source(source: RoleBindingSource) -> OidcRoleSource:
    if source is RoleBindingSource.DIRECT_BINDING:
        return OidcRoleSource.DIRECT_BINDING
    if source is RoleBindingSource.CLAIM_MAPPING:
        return OidcRoleSource.CLAIM_MAPPING
    raise OidcIdentityResolutionError


class OidcIdentityResolver:
    """Resolve exact subjects, with direct bindings taking precedence over claim mappings."""

    __slots__ = ("_policy", "_repository")

    def __init__(self, policy: OidcPolicy, repository: IdentityRepository) -> None:
        if type(policy) is not OidcPolicy or not policy.enabled or policy.issuer is None:
            raise OidcIdentityResolutionError
        self._policy = policy
        self._repository = repository

    def __repr__(self) -> str:
        return (
            "OidcIdentityResolver("
            f"issuer={self._policy.issuer!r}, policy_revision={self._policy.revision!r})"
        )

    async def _policy_revision(self) -> OidcPolicyRevisionRecord:
        revision = await self._repository.get_oidc_policy_revision()
        if (
            type(revision) is not OidcPolicyRevisionRecord
            or revision.revision != self._policy.revision
            or revision.authorization_epoch != self._policy.authorization_epoch
        ):
            raise OidcIdentityResolutionError
        return revision

    async def _invalidate_claim_sessions(self, managed: ManagedIdentity) -> None:
        """Advance the identity epoch after a denied claim-mapped re-evaluation."""
        try:
            await self._repository.set_role(
                identity_id=managed.identity.identity_id,
                role=managed.binding.role,
                source=RoleBindingSource.CLAIM_MAPPING,
                expected_revision=managed.binding.revision,
            )
        except IdentityRevisionConflict:
            # A concurrent authorization mutation already advanced the epoch.
            return

    def _resolved(
        self,
        managed: ManagedIdentity,
        policy_revision: OidcPolicyRevisionRecord,
    ) -> ResolvedOidcIdentity:
        identity = managed.identity
        binding = managed.binding
        if (
            type(managed) is not ManagedIdentity
            or not identity.enabled
            or identity.issuer != self._policy.issuer
            or identity.subject is None
        ):
            raise OidcIdentityResolutionError
        role_source = _role_source(binding.source)
        principal = ManagementPrincipal.oidc_user(
            issuer=identity.issuer,
            subject=identity.subject,
            role=binding.role,
            role_source=role_source,
        )
        return ResolvedOidcIdentity(
            principal=principal,
            identity_id=identity.identity_id,
            identity_authorization_epoch=identity.authorization_epoch,
            binding_revision=binding.revision,
            policy_revision=policy_revision.revision,
            policy_authorization_epoch=policy_revision.authorization_epoch,
        )

    async def resolve(self, token: VerifiedOidcIdToken) -> ResolvedOidcIdentity:
        """Resolve one fully verified token without trusting profile claims as identity keys."""
        try:
            if (
                type(token) is not VerifiedOidcIdToken
                or token.issuer != self._policy.issuer
                or token.policy_revision != self._policy.revision
            ):
                raise OidcIdentityResolutionError
            policy_revision = await self._policy_revision()
            managed = await self._repository.get_identity_by_oidc(
                issuer=token.issuer,
                subject=token.subject,
            )

            if managed is None:
                role = _claim_mapped_role(self._policy, token.groups)
                try:
                    managed = await self._repository.create_oidc_identity(
                        issuer=token.issuer,
                        subject=token.subject,
                        role=role,
                        source=RoleBindingSource.CLAIM_MAPPING,
                    )
                except IdentityAlreadyExists:
                    managed = await self._repository.get_identity_by_oidc(
                        issuer=token.issuer,
                        subject=token.subject,
                    )
                    if managed is None:
                        raise OidcIdentityResolutionError

            if not managed.identity.enabled:
                raise OidcIdentityResolutionError
            if managed.binding.source is RoleBindingSource.CLAIM_MAPPING:
                try:
                    role = _claim_mapped_role(self._policy, token.groups)
                except OidcIdentityResolutionError:
                    await self._invalidate_claim_sessions(managed)
                    raise
                if managed.binding.role is not role:
                    try:
                        managed = await self._repository.set_role(
                            identity_id=managed.identity.identity_id,
                            role=role,
                            source=RoleBindingSource.CLAIM_MAPPING,
                            expected_revision=managed.binding.revision,
                        )
                    except IdentityRevisionConflict:
                        managed = await self._repository.get_identity_by_oidc(
                            issuer=token.issuer,
                            subject=token.subject,
                        )
                        if (
                            managed is None
                            or not managed.identity.enabled
                            or managed.binding.source is RoleBindingSource.CLAIM_MAPPING
                            and managed.binding.role is not role
                        ):
                            raise OidcIdentityResolutionError

            policy_revision = await self._policy_revision()
            return self._resolved(managed, policy_revision)
        except asyncio.CancelledError:
            raise
        except OidcIdentityResolutionError:
            raise OidcIdentityResolutionError from None
        except Exception:
            raise OidcIdentityResolutionError from None
