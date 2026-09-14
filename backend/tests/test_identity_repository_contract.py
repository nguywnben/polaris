"""Strict domain contract for durable management identities and role bindings."""

from __future__ import annotations

import dataclasses
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import ManagementRole, PrincipalType
from core.identity.repository import (
    IDENTITY_MIGRATION_ID,
    IDENTITY_SCHEMA_VERSION,
    LOCAL_OWNER_BINDING_ID,
    LOCAL_OWNER_ID,
    IdentityMigrationRecord,
    IdentityRecord,
    ManagedIdentity,
    OidcPolicyRevisionRecord,
    RoleBindingRecord,
    RoleBindingSource,
    identity_from_record,
    migration_from_record,
    oidc_policy_revision_from_record,
    role_binding_from_record,
)

NOW = datetime(2026, 8, 26, 16, 0, tzinfo=timezone.utc)


def _identity(**overrides) -> IdentityRecord:
    values = {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "identity_id": "idn_0123456789abcdef0123456789abcdef",
        "principal_type": PrincipalType.OIDC_USER,
        "issuer": "https://idp.example/tenant-a",
        "subject": "subject-123",
        "enabled": True,
        "revision": 1,
        "authorization_epoch": 1,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    values.update(overrides)
    return IdentityRecord(**values)


def _binding(**overrides) -> RoleBindingRecord:
    values = {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "binding_id": "rbd_0123456789abcdef0123456789abcdef",
        "identity_id": "idn_0123456789abcdef0123456789abcdef",
        "role": ManagementRole.VIEWER,
        "source": RoleBindingSource.DIRECT_BINDING,
        "revision": 1,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    values.update(overrides)
    return RoleBindingRecord(**values)


class IdentityRecordContractTests(unittest.TestCase):
    def test_oidc_identity_uses_only_exact_issuer_and_subject_as_stable_identity(self):
        identity = _identity()

        self.assertEqual(
            identity.stable_identity,
            ("https://idp.example/tenant-a", "subject-123"),
        )
        self.assertNotIn("email", {field.name for field in dataclasses.fields(identity)})
        self.assertNotIn("subject-123", repr(identity))
        self.assertNotIn("idp.example", repr(identity))

    def test_local_owner_shape_is_fixed_and_cannot_carry_oidc_identity(self):
        owner = IdentityRecord.local_owner(now=NOW)

        self.assertEqual(owner.identity_id, LOCAL_OWNER_ID)
        self.assertIs(owner.principal_type, PrincipalType.LOCAL_OWNER)
        self.assertEqual(owner.stable_identity, LOCAL_OWNER_ID)
        self.assertTrue(owner.enabled)
        self.assertIsNone(owner.issuer)
        self.assertIsNone(owner.subject)

        with self.assertRaises(ValueError):
            IdentityRecord.local_owner(now=NOW, identity_id="spoofed-owner")

    def test_unknown_versions_invalid_types_and_malformed_identifiers_fail_closed(self):
        invalid = (
            {"schema_version": 2},
            {"schema_version": True},
            {"enabled": 1},
            {"revision": 0},
            {"authorization_epoch": 0},
            {"identity_id": "subject@example.com"},
            {"issuer": " https://idp.example"},
            {"subject": "subject\nspoof"},
            {"updated_at": (NOW - timedelta(seconds=1)).isoformat()},
        )

        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                _identity(**overrides)

    def test_stored_identity_requires_an_exact_shape_and_revalidates_types(self):
        record = _identity().to_record()
        self.assertEqual(identity_from_record(record), _identity())

        with self.assertRaises(ValueError):
            identity_from_record({**record, "email": "owner@example.com"})
        with self.assertRaises(ValueError):
            identity_from_record({**record, "enabled": 1})


class RoleBindingContractTests(unittest.TestCase):
    def test_local_owner_binding_is_fixed_owner_bootstrap(self):
        binding = RoleBindingRecord.local_owner(now=NOW)

        self.assertEqual(binding.binding_id, LOCAL_OWNER_BINDING_ID)
        self.assertEqual(binding.identity_id, LOCAL_OWNER_ID)
        self.assertIs(binding.role, ManagementRole.OWNER)
        self.assertIs(binding.source, RoleBindingSource.LOCAL_BOOTSTRAP)

    def test_claim_mapping_can_never_assign_owner(self):
        with self.assertRaises(ValueError):
            _binding(
                role=ManagementRole.OWNER,
                source=RoleBindingSource.CLAIM_MAPPING,
            )

    def test_binding_identity_must_match_its_managed_identity(self):
        with self.assertRaises(ValueError):
            ManagedIdentity(
                identity=_identity(),
                binding=_binding(identity_id="idn_ffffffffffffffffffffffffffffffff"),
            )

    def test_stored_binding_requires_exact_typed_vocabulary(self):
        record = _binding().to_record()
        self.assertEqual(role_binding_from_record(record), _binding())

        with self.assertRaises(ValueError):
            role_binding_from_record({**record, "role": "super_admin"})
        with self.assertRaises(ValueError):
            role_binding_from_record({**record, "source": "email_domain"})


class IdentityMetadataContractTests(unittest.TestCase):
    def test_oidc_policy_revision_is_monotonic_and_strict(self):
        policy = OidcPolicyRevisionRecord.initial(now=NOW)

        self.assertEqual(policy.revision, 1)
        self.assertEqual(policy.authorization_epoch, 1)
        self.assertEqual(oidc_policy_revision_from_record(policy.to_record()), policy)

        with self.assertRaises(ValueError):
            OidcPolicyRevisionRecord(
                schema_version=IDENTITY_SCHEMA_VERSION,
                revision=True,
                authorization_epoch=1,
                updated_at=NOW.isoformat(),
            )

    def test_migration_record_is_fixed_versioned_and_contains_no_legacy_secret(self):
        migration = IdentityMigrationRecord.applied(now=NOW)

        self.assertEqual(migration.migration_id, IDENTITY_MIGRATION_ID)
        self.assertEqual(migration.schema_version, IDENTITY_SCHEMA_VERSION)
        self.assertEqual(migration_from_record(migration.to_record()), migration)
        serialized = repr(migration.to_record()).lower()
        self.assertNotIn("password", serialized)
        self.assertNotIn("secret", serialized)


if __name__ == "__main__":
    unittest.main()
