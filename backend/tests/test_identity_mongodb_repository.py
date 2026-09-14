"""MongoDB boundary tests for the durable identity repository."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pymongo.errors import DuplicateKeyError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import ManagementRole, PrincipalType
from core.identity.repository import (
    IDENTITY_MIGRATION_ID,
    IDENTITY_SCHEMA_VERSION,
    LOCAL_OWNER_ID,
    IdentityAlreadyExists,
    IdentityOwnerInvariant,
    IdentityRevisionConflict,
    IdentityStoreCorrupt,
    RoleBindingSource,
)
from core.storage.identity_mongodb import MongoDBIdentityRepository

NOW = datetime(2026, 8, 27, 3, 0, tzinfo=timezone.utc)


class _UpdateResult:
    def __init__(self, *, matched_count=1):
        self.matched_count = matched_count


class _FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)
        self.sort_spec = None
        self.limit_count = None

    def sort(self, spec):
        self.sort_spec = spec
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def __aiter__(self):
        documents = self.documents[: self.limit_count] if self.limit_count else self.documents

        async def iterate():
            for document in documents:
                yield document

        return iterate()


class _FakeCollection:
    def __init__(self):
        self.indexes = []
        self.inserted = []
        self.insert_error = None
        self.update_calls = []
        self.find_calls = []
        self.find_one_calls = []
        self.find_one_results = []
        self.find_one_and_update_calls = []
        self.find_one_and_update_results = []
        self.find_documents = []
        self.counts = []
        self.last_cursor = None

    async def create_indexes(self, indexes):
        self.indexes.extend(indexes)

    async def update_one(self, query, update, **kwargs):
        self.update_calls.append((query, update, kwargs))
        return _UpdateResult()

    async def insert_one(self, document):
        if self.insert_error is not None:
            raise self.insert_error
        self.inserted.append(document)

    def find(self, query, projection=None):
        self.find_calls.append((query, projection))
        self.last_cursor = _FakeCursor(self.find_documents)
        return self.last_cursor

    async def find_one(self, query, projection=None, **kwargs):
        self.find_one_calls.append((query, projection, kwargs))
        return self.find_one_results.pop(0)

    async def find_one_and_update(self, query, update, **kwargs):
        self.find_one_and_update_calls.append((query, update, kwargs))
        return self.find_one_and_update_results.pop(0)

    async def count_documents(self, query):
        self.find_calls.append((query, None))
        return self.counts.pop(0)


def _identity_document(
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
        binding_id = "binding-local-owner"
        role = "owner"
        source = "local_bootstrap"
    timestamp = NOW.isoformat()
    return {
        "_id": identity_id,
        "document_type": "managed_identity",
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "identity": {
            "schema_version": IDENTITY_SCHEMA_VERSION,
            "identity_id": identity_id,
            "principal_type": principal_type,
            "issuer": issuer,
            "subject": subject,
            "enabled": enabled,
            "revision": identity_revision,
            "authorization_epoch": identity_revision,
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        "binding": {
            "schema_version": IDENTITY_SCHEMA_VERSION,
            "binding_id": binding_id,
            "identity_id": identity_id,
            "role": role,
            "source": source,
            "revision": binding_revision,
            "created_at": timestamp,
            "updated_at": timestamp,
        },
    }


def _policy_document():
    return {
        "_id": "oidc-policy-revision",
        "document_type": "oidc_policy_revision",
        "record": {
            "schema_version": IDENTITY_SCHEMA_VERSION,
            "revision": 1,
            "authorization_epoch": 1,
            "updated_at": NOW.isoformat(),
        },
    }


def _migration_document():
    return {
        "_id": IDENTITY_MIGRATION_ID,
        "document_type": "identity_migration",
        "record": {
            "migration_id": IDENTITY_MIGRATION_ID,
            "schema_version": IDENTITY_SCHEMA_VERSION,
            "applied_at": NOW.isoformat(),
        },
    }


class MongoDBIdentityRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.collection = _FakeCollection()
        self.collection.find_documents = [_identity_document(identity_id=LOCAL_OWNER_ID)]
        self.collection.counts = [1]
        self.collection.find_one_results = [_policy_document(), _migration_document()]
        self.repository = MongoDBIdentityRepository(self.collection, clock=lambda: NOW)
        await self.repository.initialize()

    async def test_initialize_builds_partial_unique_and_order_indexes_without_ttl(self):
        indexes = {index.document["name"]: index.document for index in self.collection.indexes}
        stable = indexes["idx_management_identity_oidc_unique"]

        self.assertTrue(stable["unique"])
        self.assertEqual(
            stable["partialFilterExpression"],
            {"document_type": "managed_identity", "identity.principal_type": "oidc_user"},
        )
        self.assertIn("idx_management_identity_order", indexes)
        self.assertTrue(all("expireAfterSeconds" not in index for index in indexes.values()))
        self.assertTrue(all(call[2].get("upsert") for call in self.collection.update_calls))

    async def test_create_stores_atomic_document_and_normalizes_duplicates(self):
        created = await self.repository.create_oidc_identity(
            issuer="https://idp.example/Tenant",
            subject="User-123",
            role=ManagementRole.OPERATOR,
        )

        document = self.collection.inserted[-1]
        self.assertEqual(document["identity"]["subject"], "User-123")
        self.assertEqual(document["binding"]["identity_id"], created.identity.identity_id)
        self.assertNotIn("User-123", repr(self.collection.indexes))

        self.collection.insert_error = DuplicateKeyError("duplicate")
        with self.assertRaises(IdentityAlreadyExists) as raised:
            await self.repository.create_oidc_identity(
                issuer="https://idp.example/Tenant",
                subject="User-123",
                role=ManagementRole.OPERATOR,
            )
        self.assertNotIn("User-123", str(raised.exception))

    async def test_exact_lookup_and_list_use_simple_collation_stable_bounded_order(self):
        self.collection.find_one_results = [_identity_document()]
        found = await self.repository.get_identity_by_oidc(
            issuer="https://idp.example", subject="subject-1"
        )

        query, _projection, options = self.collection.find_one_calls[-1]
        self.assertEqual(query["identity.issuer"], "https://idp.example")
        self.assertEqual(query["identity.subject"], "subject-1")
        self.assertEqual(options["collation"].document["locale"], "simple")
        self.assertIs(found.identity.principal_type, PrincipalType.OIDC_USER)

        self.collection.find_documents = [_identity_document()]
        identities = await self.repository.list_identities(limit=25)
        self.assertEqual(
            self.collection.last_cursor.sort_spec,
            [("identity.created_at", 1), ("identity.identity_id", 1)],
        )
        self.assertEqual(self.collection.last_cursor.limit_count, 25)
        self.assertEqual(len(identities), 1)
        with self.assertRaises(ValueError):
            await self.repository.list_identities(limit=201)

    async def test_enable_update_uses_single_document_revision_cas(self):
        identity_id = "idn_0123456789abcdef0123456789abcdef"
        self.collection.find_one_and_update_results = [None]
        self.collection.find_one_results = [_identity_document(identity_revision=2)]

        with self.assertRaises(IdentityRevisionConflict):
            await self.repository.set_identity_enabled(
                identity_id=identity_id,
                enabled=False,
                expected_revision=1,
            )

        query, update, options = self.collection.find_one_and_update_calls[-1]
        self.assertEqual(query["identity.revision"], 1)
        self.assertEqual(update["$inc"]["identity.revision"], 1)
        self.assertEqual(update["$inc"]["identity.authorization_epoch"], 1)
        self.assertIn("return_document", options)

    async def test_role_update_advances_binding_and_identity_in_one_document(self):
        self.collection.find_one_and_update_results = [
            _identity_document(
                identity_revision=2,
                binding_revision=2,
                role="operator",
                source="direct_binding",
            )
        ]
        updated = await self.repository.set_role(
            identity_id="idn_0123456789abcdef0123456789abcdef",
            role=ManagementRole.OPERATOR,
            source=RoleBindingSource.DIRECT_BINDING,
            expected_revision=1,
        )

        _query, update, _options = self.collection.find_one_and_update_calls[-1]
        self.assertEqual(update["$set"]["binding.role"], "operator")
        self.assertEqual(update["$inc"]["binding.revision"], 1)
        self.assertEqual(update["$inc"]["identity.authorization_epoch"], 1)
        self.assertEqual(updated.binding.role, ManagementRole.OPERATOR)

    async def test_owner_invariants_fail_before_storage_mutation(self):
        before = len(self.collection.find_one_and_update_calls)
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
        self.assertEqual(len(self.collection.find_one_and_update_calls), before)

    async def test_corrupted_document_fails_closed_without_raw_identity(self):
        corrupted = _identity_document()
        corrupted["binding"]["source"] = "unexpected"
        self.collection.find_one_results = [corrupted]

        with self.assertRaises(IdentityStoreCorrupt) as raised:
            await self.repository.get_identity(corrupted["_id"])
        self.assertNotIn("subject-1", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
