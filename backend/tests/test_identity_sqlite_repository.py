"""SQLite tests for durable management identities and owner invariants."""

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import ManagementRole, PrincipalType
from core.identity.repository import (
    IDENTITY_MIGRATION_ID,
    LOCAL_OWNER_ID,
    IdentityAlreadyExists,
    IdentityOwnerInvariant,
    IdentityRevisionConflict,
    IdentityStoreCorrupt,
    RoleBindingSource,
)
from core.storage.identity_sqlite import SQLiteIdentityRepository
from tests.identity_repository_contract import IdentityRepositoryParityMixin
from tests.support import workspace_temp_directory

NOW = datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc)


class SQLiteIdentityRepositoryTests(
    IdentityRepositoryParityMixin,
    unittest.IsolatedAsyncioTestCase,
):
    async def asyncSetUp(self):
        self.temp_dir = workspace_temp_directory()
        temp_path = self.temp_dir.__enter__()
        self.addCleanup(self.temp_dir.__exit__, None, None, None)
        self.db_path = Path(temp_path) / "credentials.db"
        self.repository = SQLiteIdentityRepository(self.db_path, clock=lambda: NOW)
        await self.repository.initialize()

    async def restart_repository(self):
        restarted = SQLiteIdentityRepository(self.db_path, clock=lambda: NOW)
        await restarted.initialize()
        return restarted

    async def test_initialize_is_additive_idempotent_and_bootstraps_local_owner(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("CREATE TABLE existing_config (value TEXT NOT NULL)")
            await db.execute("INSERT INTO existing_config(value) VALUES (?)", ("preserved",))
            await db.commit()

        await self.repository.initialize()

        owner = await self.repository.get_identity(LOCAL_OWNER_ID)
        migration = await self.repository.get_migration()
        policy = await self.repository.get_oidc_policy_revision()
        self.assertIsNotNone(owner)
        self.assertIs(owner.identity.principal_type, PrincipalType.LOCAL_OWNER)
        self.assertIs(owner.binding.role, ManagementRole.OWNER)
        self.assertTrue(owner.identity.enabled)
        self.assertEqual(migration.migration_id, IDENTITY_MIGRATION_ID)
        self.assertEqual((policy.revision, policy.authorization_epoch), (1, 1))
        async with aiosqlite.connect(self.db_path) as db:
            row = await (await db.execute("SELECT value FROM existing_config")).fetchone()
            indexes = await (
                await db.execute("PRAGMA index_list('management_identities')")
            ).fetchall()
        self.assertEqual(row[0], "preserved")
        self.assertIn("idx_management_identity_order", {index[1] for index in indexes})

    async def test_exact_oidc_identity_is_case_sensitive_and_duplicate_safe(self):
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
        found = await self.repository.get_identity_by_oidc(
            issuer="https://idp.example/Tenant", subject="User-123"
        )
        self.assertEqual(found, first)
        with self.assertRaises(IdentityAlreadyExists) as raised:
            await self.repository.create_oidc_identity(
                issuer="https://idp.example/Tenant",
                subject="User-123",
                role=ManagementRole.VIEWER,
            )
        self.assertNotIn("User-123", str(raised.exception))

    async def test_restart_preserves_managed_identities_and_never_removes_legacy_data(self):
        created = await self.repository.create_oidc_identity(
            issuer="https://idp.example", subject="subject-1", role=ManagementRole.OPERATOR
        )

        restarted = SQLiteIdentityRepository(self.db_path, clock=lambda: NOW)
        await restarted.initialize()
        found = await restarted.get_identity(created.identity.identity_id)

        self.assertEqual(found, created)
        self.assertEqual(len(await restarted.list_identities(limit=200)), 2)

    async def test_optimistic_enable_update_rejects_stale_revision(self):
        created = await self.repository.create_oidc_identity(
            issuer="https://idp.example", subject="subject-2", role=ManagementRole.VIEWER
        )
        updated = await self.repository.set_identity_enabled(
            identity_id=created.identity.identity_id,
            enabled=False,
            expected_revision=1,
        )

        self.assertFalse(updated.identity.enabled)
        self.assertEqual(updated.identity.revision, 2)
        self.assertEqual(updated.identity.authorization_epoch, 2)
        with self.assertRaises(IdentityRevisionConflict):
            await self.repository.set_identity_enabled(
                identity_id=created.identity.identity_id,
                enabled=True,
                expected_revision=1,
            )

    async def test_concurrent_writers_allow_exactly_one_revision_winner(self):
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
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(winners[0].identity.revision, 2)

    async def test_role_update_is_atomic_and_claim_mapping_cannot_create_owner(self):
        created = await self.repository.create_oidc_identity(
            issuer="https://idp.example", subject="subject-3", role=ManagementRole.VIEWER
        )
        updated = await self.repository.set_role(
            identity_id=created.identity.identity_id,
            role=ManagementRole.SECURITY_ADMIN,
            source=RoleBindingSource.DIRECT_BINDING,
            expected_revision=1,
        )

        self.assertIs(updated.binding.role, ManagementRole.SECURITY_ADMIN)
        self.assertEqual(updated.binding.revision, 2)
        self.assertEqual(updated.identity.revision, 2)
        self.assertEqual(updated.identity.authorization_epoch, 2)
        with self.assertRaises(ValueError):
            await self.repository.set_role(
                identity_id=created.identity.identity_id,
                role=ManagementRole.OWNER,
                source=RoleBindingSource.CLAIM_MAPPING,
                expected_revision=2,
            )

    async def test_identity_and_binding_revisions_are_independent_resources(self):
        created = await self.repository.create_oidc_identity(
            issuer="https://idp.example",
            subject="subject-independent-revisions",
            role=ManagementRole.VIEWER,
        )
        disabled = await self.repository.set_identity_enabled(
            identity_id=created.identity.identity_id,
            enabled=False,
            expected_revision=1,
        )
        updated = await self.repository.set_role(
            identity_id=created.identity.identity_id,
            role=ManagementRole.OPERATOR,
            source=RoleBindingSource.DIRECT_BINDING,
            expected_revision=1,
        )

        self.assertEqual(disabled.identity.revision, 2)
        self.assertEqual(disabled.binding.revision, 1)
        self.assertEqual(updated.identity.revision, 3)
        self.assertEqual(updated.identity.authorization_epoch, 3)
        self.assertEqual(updated.binding.revision, 2)

    async def test_local_owner_cannot_be_disabled_or_demoted_and_state_is_unchanged(self):

        with self.assertRaises(IdentityOwnerInvariant):
            await self.repository.set_identity_enabled(
                identity_id=LOCAL_OWNER_ID, enabled=False, expected_revision=1
            )
        with self.assertRaises(IdentityOwnerInvariant):
            await self.repository.set_role(
                identity_id=LOCAL_OWNER_ID,
                role=ManagementRole.VIEWER,
                source=RoleBindingSource.DIRECT_BINDING,
                expected_revision=1,
            )

        owner = await self.repository.get_identity(LOCAL_OWNER_ID)
        self.assertTrue(owner.identity.enabled)
        self.assertIs(owner.binding.role, ManagementRole.OWNER)
        self.assertEqual(owner.identity.revision, 1)

    async def test_policy_revision_uses_optimistic_concurrency(self):
        updated = await self.repository.advance_oidc_policy_revision(expected_revision=1)

        self.assertEqual((updated.revision, updated.authorization_epoch), (2, 2))
        with self.assertRaises(IdentityRevisionConflict):
            await self.repository.advance_oidc_policy_revision(expected_revision=1)

    async def test_list_limit_is_bounded_and_strictly_typed(self):

        for limit in (0, 201, True, "10"):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                await self.repository.list_identities(limit=limit)

    async def test_corruption_fails_closed_on_read_and_restart(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE management_role_bindings SET source = ? WHERE identity_id = ?",
                (RoleBindingSource.DIRECT_BINDING.value, LOCAL_OWNER_ID),
            )
            await db.commit()

        with self.assertRaises(IdentityStoreCorrupt):
            await self.repository.get_identity(LOCAL_OWNER_ID)
        restarted = SQLiteIdentityRepository(self.db_path, clock=lambda: NOW)
        with self.assertRaises(IdentityStoreCorrupt):
            await restarted.initialize()


if __name__ == "__main__":
    unittest.main()
