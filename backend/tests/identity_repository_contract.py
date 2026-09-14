"""Reusable behavioral contract for every durable identity repository backend."""

from __future__ import annotations

import asyncio

from core.identity import ManagementRole, PrincipalType
from core.identity.repository import (
    IDENTITY_MIGRATION_ID,
    LOCAL_OWNER_ID,
    IdentityAlreadyExists,
    IdentityOwnerInvariant,
    IdentityPageCursor,
    IdentityRevisionConflict,
    RoleBindingSource,
)


class IdentityRepositoryParityMixin:
    """Backend-neutral identity semantics; concrete tests provide repository setup."""

    repository = None

    async def restart_repository(self):
        raise NotImplementedError

    async def test_parity_bootstraps_the_fixed_local_owner_and_metadata(self):
        owner = await self.repository.get_identity(LOCAL_OWNER_ID)
        migration = await self.repository.get_migration()
        policy = await self.repository.get_oidc_policy_revision()

        self.assertIs(owner.identity.principal_type, PrincipalType.LOCAL_OWNER)
        self.assertIs(owner.binding.role, ManagementRole.OWNER)
        self.assertTrue(owner.identity.enabled)
        self.assertEqual(migration.migration_id, IDENTITY_MIGRATION_ID)
        self.assertEqual((policy.revision, policy.authorization_epoch), (1, 1))

    async def test_parity_uses_exact_oidc_identity_and_generic_duplicate_errors(self):
        first = await self.repository.create_oidc_identity(
            issuer="https://idp.example/Tenant",
            subject="User-123",
            role=ManagementRole.VIEWER,
        )
        second = await self.repository.create_oidc_identity(
            issuer="https://idp.example/tenant",
            subject="user-123",
            role=ManagementRole.OPERATOR,
        )

        self.assertNotEqual(first.identity.identity_id, second.identity.identity_id)
        self.assertEqual(
            await self.repository.get_identity_by_oidc(
                issuer="https://idp.example/Tenant", subject="User-123"
            ),
            first,
        )
        with self.assertRaises(IdentityAlreadyExists) as raised:
            await self.repository.create_oidc_identity(
                issuer="https://idp.example/Tenant",
                subject="User-123",
                role=ManagementRole.VIEWER,
            )
        self.assertNotIn("User-123", str(raised.exception))

    async def test_parity_orders_and_bounds_identity_lists(self):
        first = await self.repository.create_oidc_identity(
            issuer="https://idp.example", subject="subject-a", role=ManagementRole.VIEWER
        )
        second = await self.repository.create_oidc_identity(
            issuer="https://idp.example", subject="subject-b", role=ManagementRole.VIEWER
        )

        identities = await self.repository.list_identities(limit=200)
        self.assertEqual(
            [item.identity.identity_id for item in identities],
            [
                item.identity.identity_id
                for item in sorted(
                    identities,
                    key=lambda item: (
                        item.identity.created_at,
                        item.identity.identity_id,
                    ),
                )
            ],
        )
        self.assertEqual(
            {item.identity.identity_id for item in identities},
            {LOCAL_OWNER_ID, first.identity.identity_id, second.identity.identity_id},
        )
        for invalid_limit in (0, 201, True, "10"):
            with self.subTest(limit=invalid_limit), self.assertRaises(ValueError):
                await self.repository.list_identities(limit=invalid_limit)

        first_page = await self.repository.list_identities(limit=2)
        second_page = await self.repository.list_identities(
            limit=2,
            after=IdentityPageCursor.from_identity(first_page[-1].identity),
        )
        self.assertEqual(first_page + second_page, identities)
        with self.assertRaises(ValueError):
            await self.repository.list_identities(limit=2, after="not-a-cursor")

    async def test_parity_identity_and_binding_revisions_are_independent(self):
        created = await self.repository.create_oidc_identity(
            issuer="https://idp.example",
            subject="subject-revisions",
            role=ManagementRole.VIEWER,
        )
        disabled = await self.repository.set_identity_enabled(
            identity_id=created.identity.identity_id,
            enabled=False,
            expected_revision=1,
        )
        updated = await self.repository.set_role(
            identity_id=created.identity.identity_id,
            role=ManagementRole.SECURITY_ADMIN,
            source=RoleBindingSource.DIRECT_BINDING,
            expected_revision=1,
        )

        self.assertEqual((disabled.identity.revision, disabled.binding.revision), (2, 1))
        self.assertEqual((updated.identity.revision, updated.binding.revision), (3, 2))
        self.assertEqual(updated.identity.authorization_epoch, 3)
        with self.assertRaises(IdentityRevisionConflict):
            await self.repository.set_role(
                identity_id=created.identity.identity_id,
                role=ManagementRole.VIEWER,
                source=RoleBindingSource.DIRECT_BINDING,
                expected_revision=1,
            )

    async def test_parity_concurrent_identity_writers_have_one_winner(self):
        created = await self.repository.create_oidc_identity(
            issuer="https://idp.example", subject="subject-race", role=ManagementRole.VIEWER
        )

        outcomes = await asyncio.gather(
            self.repository.set_identity_enabled(
                identity_id=created.identity.identity_id,
                enabled=False,
                expected_revision=1,
            ),
            self.repository.set_identity_enabled(
                identity_id=created.identity.identity_id,
                enabled=False,
                expected_revision=1,
            ),
            return_exceptions=True,
        )

        winners = [item for item in outcomes if not isinstance(item, Exception)]
        conflicts = [item for item in outcomes if isinstance(item, IdentityRevisionConflict)]
        self.assertEqual((len(winners), len(conflicts)), (1, 1))

    async def test_parity_owner_and_policy_invariants_fail_closed(self):
        with self.assertRaises(IdentityOwnerInvariant):
            await self.repository.set_identity_enabled(
                identity_id=LOCAL_OWNER_ID,
                enabled=False,
                expected_revision=1,
            )
        with self.assertRaises(IdentityOwnerInvariant):
            await self.repository.set_role(
                identity_id=LOCAL_OWNER_ID,
                role=ManagementRole.VIEWER,
                source=RoleBindingSource.DIRECT_BINDING,
                expected_revision=1,
            )
        with self.assertRaises(ValueError):
            await self.repository.create_oidc_identity(
                issuer="https://idp.example",
                subject="claim-owner",
                role=ManagementRole.OWNER,
                source=RoleBindingSource.CLAIM_MAPPING,
            )

        policy = await self.repository.advance_oidc_policy_revision(expected_revision=1)
        self.assertEqual((policy.revision, policy.authorization_epoch), (2, 2))
        with self.assertRaises(IdentityRevisionConflict):
            await self.repository.advance_oidc_policy_revision(expected_revision=1)

    async def test_parity_restart_preserves_records(self):
        created = await self.repository.create_oidc_identity(
            issuer="https://idp.example",
            subject="subject-restart",
            role=ManagementRole.OPERATOR,
        )

        restarted = await self.restart_repository()

        self.assertEqual(await restarted.get_identity(created.identity.identity_id), created)
