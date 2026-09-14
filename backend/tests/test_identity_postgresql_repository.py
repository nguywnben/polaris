"""PostgreSQL boundary tests for the durable identity repository."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import ManagementRole, PrincipalType
from core.identity.repository import (
    IDENTITY_MIGRATION_ID,
    IDENTITY_SCHEMA_VERSION,
    LOCAL_OWNER_BINDING_ID,
    LOCAL_OWNER_ID,
    IdentityAlreadyExists,
    IdentityOwnerInvariant,
    IdentityRevisionConflict,
    IdentityStoreCorrupt,
    RoleBindingSource,
)
from core.storage.identity_postgresql import PostgreSQLIdentityRepository

NOW = datetime(2026, 8, 27, 2, 0, tzinfo=timezone.utc)


class _AcquireContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


class _TransactionContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        self.connection.transaction_entries += 1
        return self

    async def __aexit__(self, *_args):
        return False


class _FakeConnection:
    def __init__(self):
        self.executions = []
        self.fetches = []
        self.fetchrows = []
        self.fetchvalues = []
        self.fetch_results = []
        self.fetchrow_results = []
        self.fetchval_results = []
        self.execute_error = None
        self.transaction_entries = 0

    async def execute(self, sql, *args):
        if self.execute_error is not None:
            raise self.execute_error
        self.executions.append((sql, args))
        return "OK"

    async def fetch(self, sql, *args):
        self.fetches.append((sql, args))
        return self.fetch_results.pop(0)

    async def fetchrow(self, sql, *args):
        self.fetchrows.append((sql, args))
        return self.fetchrow_results.pop(0)

    async def fetchval(self, sql, *args):
        self.fetchvalues.append((sql, args))
        return self.fetchval_results.pop(0)

    def transaction(self):
        return _TransactionContext(self)


class _FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _AcquireContext(self.connection)


def _joined_row(
    *,
    identity_id="idn_0123456789abcdef0123456789abcdef",
    issuer="https://idp.example",
    subject="subject-1",
    enabled=True,
    identity_revision=1,
    binding_revision=1,
    role="viewer",
    source="direct_binding",
):
    principal_type = "oidc_user"
    binding_id = "rbd_0123456789abcdef0123456789abcdef"
    if identity_id == LOCAL_OWNER_ID:
        principal_type = "local_owner"
        issuer = None
        subject = None
        enabled = True
        binding_id = LOCAL_OWNER_BINDING_ID
        role = "owner"
        source = "local_bootstrap"
    return {
        "i_schema_version": IDENTITY_SCHEMA_VERSION,
        "i_identity_id": identity_id,
        "i_principal_type": principal_type,
        "i_issuer": issuer,
        "i_subject": subject,
        "i_enabled": enabled,
        "i_revision": identity_revision,
        "i_authorization_epoch": identity_revision,
        "i_created_at": NOW,
        "i_updated_at": NOW,
        "b_schema_version": IDENTITY_SCHEMA_VERSION,
        "b_binding_id": binding_id,
        "b_identity_id": identity_id,
        "b_role": role,
        "b_source": source,
        "b_revision": binding_revision,
        "b_created_at": NOW,
        "b_updated_at": NOW,
    }


def _policy_row(revision=1):
    return {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "revision": revision,
        "authorization_epoch": revision,
        "updated_at": NOW,
    }


def _migration_row():
    return {
        "migration_id": IDENTITY_MIGRATION_ID,
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "applied_at": NOW,
    }


class PostgreSQLIdentityRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = _FakeConnection()
        self.repository = PostgreSQLIdentityRepository(
            _FakePool(self.connection), clock=lambda: NOW
        )
        self.connection.fetch_results = [[_joined_row(identity_id=LOCAL_OWNER_ID)]]
        self.connection.fetchval_results = [1]
        self.connection.fetchrow_results = [_policy_row(), _migration_row()]
        await self.repository.initialize()

    async def test_initialize_is_additive_transactional_and_bootstraps_metadata(self):
        schema = "\n".join(sql for sql, _args in self.connection.executions)

        first_sql, first_args = self.connection.executions[0]
        self.assertIn("pg_advisory_xact_lock", first_sql)
        self.assertEqual(first_args, (0x4F4D4E4949445631,))
        self.assertIn("CREATE TABLE IF NOT EXISTS management_identities", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS management_role_bindings", schema)
        self.assertIn("ON CONFLICT DO NOTHING", schema)
        self.assertIn("UNIQUE (issuer, subject)", schema)
        self.assertIn("'security_admin'", schema)
        self.assertNotIn("DROP ", schema.upper())
        self.assertNotIn("TRUNCATE ", schema.upper())
        self.assertEqual(self.connection.transaction_entries, 1)

    async def test_create_is_parameterized_atomic_and_normalizes_duplicates(self):
        self.connection.executions.clear()
        await self.repository.create_oidc_identity(
            issuer="https://idp.example/Tenant",
            subject="User-123",
            role=ManagementRole.OPERATOR,
        )

        sql = "\n".join(statement for statement, _args in self.connection.executions)
        args = tuple(arg for _statement, values in self.connection.executions for arg in values)
        self.assertIn("VALUES ($1, $2", sql)
        self.assertNotIn("User-123", sql)
        self.assertIn("User-123", args)
        self.assertEqual(
            [value.tzinfo for value in args if isinstance(value, datetime)],
            [timezone.utc, timezone.utc, timezone.utc, timezone.utc],
        )
        self.assertEqual(self.connection.transaction_entries, 2)

        self.connection.execute_error = asyncpg.UniqueViolationError("duplicate")
        with self.assertRaises(IdentityAlreadyExists) as raised:
            await self.repository.create_oidc_identity(
                issuer="https://idp.example/Tenant",
                subject="User-123",
                role=ManagementRole.OPERATOR,
            )
        self.assertNotIn("User-123", str(raised.exception))

    async def test_list_is_bounded_stably_ordered_and_revalidates_rows(self):
        self.connection.fetch_results = [[_joined_row()]]
        identities = await self.repository.list_identities(limit=25)

        sql, args = self.connection.fetches[-1]
        self.assertIn("ORDER BY i.created_at ASC, i.identity_id ASC", sql)
        self.assertEqual(args, (25,))
        self.assertIs(identities[0].identity.principal_type, PrincipalType.OIDC_USER)
        with self.assertRaises(ValueError):
            await self.repository.list_identities(limit=201)

    async def test_enable_update_uses_conditional_revision_and_normalizes_conflict(self):
        identity_id = "idn_0123456789abcdef0123456789abcdef"
        self.connection.fetchrow_results = [None, {"revision": 2}]

        with self.assertRaises(IdentityRevisionConflict):
            await self.repository.set_identity_enabled(
                identity_id=identity_id,
                enabled=False,
                expected_revision=1,
            )

        sql, args = self.connection.fetchrows[-2]
        self.assertIn("WHERE identity_id = $3 AND revision = $4", sql)
        self.assertEqual(args[-2:], (identity_id, 1))

    async def test_local_owner_and_claim_owner_fail_before_storage_mutation(self):
        before = len(self.connection.executions)

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
        self.assertEqual(len(self.connection.executions), before)

    async def test_corrupted_joined_row_fails_closed_without_raw_identity(self):
        corrupted = _joined_row(identity_id=LOCAL_OWNER_ID)
        corrupted["b_source"] = "direct_binding"
        self.connection.fetchrow_results = [corrupted]

        with self.assertRaises(IdentityStoreCorrupt) as raised:
            await self.repository.get_identity(LOCAL_OWNER_ID)
        self.assertNotIn("subject", str(raised.exception).lower())


if __name__ == "__main__":
    unittest.main()
