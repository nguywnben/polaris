"""Closed W4.13 durable-record and authority migration contract."""

from __future__ import annotations

import dataclasses
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.durable_migration import (
    DURABLE_COPY_FAMILIES,
    DURABLE_INVENTORY,
    DURABLE_MANIFEST_CHECKSUM,
    DURABLE_MANIFEST_VERSION,
    MIGRATION_SCHEMA_VERSION,
    AuthoritySide,
    DurableBackend,
    DurableFamily,
    DurableRecord,
    FamilyProgress,
    HistoricalMigrationCheckpoint,
    MigrationCheckpoint,
    MigrationDigest,
    MigrationPhase,
    checkpoint_from_record,
    compute_records_digest,
)

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)


def _progress(**overrides) -> FamilyProgress:
    values = {
        "family": DurableFamily.CONFIGURATION,
        "copy_offset": 0,
        "copied_count": 0,
        "copy_complete": False,
        "explicitly_empty": False,
        "source_count": None,
        "target_count": None,
        "source_checksum": None,
        "target_checksum": None,
        "verified": False,
    }
    values.update(overrides)
    return FamilyProgress(**values)


def _checkpoint(**overrides) -> MigrationCheckpoint:
    values = {
        "schema_version": MIGRATION_SCHEMA_VERSION,
        "manifest_version": DURABLE_MANIFEST_VERSION,
        "manifest_checksum": DURABLE_MANIFEST_CHECKSUM,
        "plan_id": "dmg_0123456789abcdef0123456789abcdef",
        "source_backend": DurableBackend.SQLITE,
        "target_backend": DurableBackend.POSTGRESQL,
        "source_instance_id": "ins_11111111111111111111111111111111",
        "target_instance_id": "ins_22222222222222222222222222222222",
        "source_revision": 1,
        "target_revision": 1,
        "source_barrier_id": "bar_33333333333333333333333333333333",
        "phase": MigrationPhase.PLANNED,
        "authority": AuthoritySide.SOURCE,
        "revision": 1,
        "families": tuple(_progress(family=family) for family in DURABLE_COPY_FAMILIES),
        "failure_code": None,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    values.update(overrides)
    return MigrationCheckpoint(**values)


class DurableInventoryContractTests(unittest.TestCase):
    def test_inventory_is_closed_complete_and_switch_ready_in_manifest_v2(self):
        expected = {
            DurableFamily.CONFIGURATION,
            DurableFamily.PROVIDER_CREDENTIAL,
            DurableFamily.PRIMARY_CREDENTIAL,
            DurableFamily.VIRTUAL_KEY,
            DurableFamily.IDENTITY,
            DurableFamily.ROLE_BINDING,
            DurableFamily.OIDC_POLICY_REVISION,
            DurableFamily.IDENTITY_SCHEMA_EVIDENCE,
            DurableFamily.AUDIT_EVENT,
            DurableFamily.REQUEST_TRACE,
            DurableFamily.USAGE_LEDGER,
            DurableFamily.HARD_BUDGET_RESERVATION,
            DurableFamily.MIGRATION_CHECKPOINT,
        }

        self.assertEqual({entry.family for entry in DURABLE_INVENTORY}, expected)
        self.assertEqual(len(DURABLE_INVENTORY), len(expected))
        readiness = {entry.family: entry.switch_ready for entry in DURABLE_INVENTORY}
        copy_required = {entry.family: entry.copy_required for entry in DURABLE_INVENTORY}
        self.assertEqual(DURABLE_MANIFEST_VERSION, 2)
        self.assertTrue(all(readiness.values()))
        self.assertFalse(copy_required[DurableFamily.MIGRATION_CHECKPOINT])

    def test_every_manifest_family_has_concrete_sqlite_and_postgresql_adapter(self):
        from core.storage.durable_family_postgresql import (
            POSTGRESQL_DURABLE_FAMILY_ADAPTERS,
        )
        from core.storage.durable_family_sqlite import SQLITE_DURABLE_FAMILY_ADAPTERS

        expected = {entry.family for entry in DURABLE_INVENTORY}
        self.assertEqual(set(SQLITE_DURABLE_FAMILY_ADAPTERS), expected)
        self.assertEqual(set(POSTGRESQL_DURABLE_FAMILY_ADAPTERS), expected)

    def test_inventory_and_checkpoint_metadata_have_no_payload_or_secret_fields(self):
        inventory_fields = {field.name for field in dataclasses.fields(DURABLE_INVENTORY[0])}
        checkpoint_fields = {field.name for field in dataclasses.fields(MigrationCheckpoint)}
        family_fields = {field.name for field in dataclasses.fields(FamilyProgress)}

        for fields in (inventory_fields, checkpoint_fields, family_fields):
            self.assertFalse(
                fields
                & {
                    "payload",
                    "record",
                    "credential",
                    "prompt",
                    "subject",
                    "filename",
                    "secret",
                    "token",
                }
            )


class DurableRecordContractTests(unittest.TestCase):
    def test_payload_is_closed_json_and_hidden_from_representations(self):
        record = DurableRecord(
            family=DurableFamily.CONFIGURATION,
            logical_id="cfg_0123456789abcdef",
            schema_version=1,
            payload={"panel_password": "sensitive-value", "enabled": True},
        )

        self.assertNotIn("sensitive-value", repr(record))
        self.assertNotIn("panel_password", repr(record))
        with self.assertRaises(ValueError):
            DurableRecord(
                family=DurableFamily.CONFIGURATION,
                logical_id="cfg_0123456789abcdef",
                schema_version=1,
                payload={"bad": float("nan")},
            )
        with self.assertRaises(ValueError):
            DurableRecord(
                family=DurableFamily.CONFIGURATION,
                logical_id="raw filename.json",
                schema_version=1,
                payload={},
            )

    def test_keyed_digest_is_stable_order_independent_and_content_sensitive(self):
        key = b"k" * 32
        first = DurableRecord(
            family=DurableFamily.AUDIT_EVENT,
            logical_id="aud_1111111111111111",
            schema_version=1,
            payload={"count": 1, "nested": {"ok": True}},
        )
        second = DurableRecord(
            family=DurableFamily.AUDIT_EVENT,
            logical_id="aud_2222222222222222",
            schema_version=1,
            payload={"count": 2},
        )

        digest = compute_records_digest((first, second), integrity_key=key)
        self.assertEqual(digest, compute_records_digest((second, first), integrity_key=key))
        changed = dataclasses.replace(second, payload={"count": 3})
        self.assertNotEqual(digest, compute_records_digest((first, changed), integrity_key=key))
        with self.assertRaises(ValueError):
            compute_records_digest((first,), integrity_key=b"short")

    def test_streaming_digest_rejects_duplicate_or_unstable_order_without_buffering(self):
        first = DurableRecord(
            family=DurableFamily.AUDIT_EVENT,
            logical_id="aud_1111111111111111",
            schema_version=1,
            payload={"count": 1},
        )
        second = DurableRecord(
            family=DurableFamily.AUDIT_EVENT,
            logical_id="aud_2222222222222222",
            schema_version=1,
            payload={"count": 2},
        )
        digest = MigrationDigest(integrity_key=b"k" * 32)
        digest.add(first)
        digest.add(second)

        self.assertEqual(digest.count, 2)
        self.assertEqual(
            digest.hexdigest(),
            compute_records_digest((first, second), integrity_key=b"k" * 32),
        )
        with self.assertRaises(ValueError):
            digest.add(first)


class MigrationCheckpointContractTests(unittest.TestCase):
    def test_historical_manifest_v1_checkpoint_remains_parseable_but_ineligible(self):
        record = _checkpoint().to_record()
        record["manifest_version"] = 1
        record["manifest_checksum"] = "9" * 64
        record.pop("source_revision")
        record.pop("target_revision")

        restored = checkpoint_from_record(record)

        self.assertIsInstance(restored, HistoricalMigrationCheckpoint)
        self.assertFalse(restored.eligible_for_binding)

    def test_checkpoint_requires_one_authority_and_valid_phase_invariants(self):
        with self.assertRaises(ValueError):
            _checkpoint(authority=AuthoritySide.TARGET)

        verified = _progress(
            copy_offset=2,
            copy_complete=True,
            copied_count=2,
            source_count=2,
            target_count=2,
            source_checksum="a" * 64,
            target_checksum="a" * 64,
            verified=True,
        )
        ready = _checkpoint(
            phase=MigrationPhase.READY_TO_SWITCH,
            families=tuple(
                dataclasses.replace(verified, family=family) for family in DURABLE_COPY_FAMILIES
            ),
            revision=4,
            updated_at=(NOW + timedelta(minutes=1)).isoformat(),
        )
        self.assertIs(ready.authority, AuthoritySide.SOURCE)
        with self.assertRaises(ValueError):
            dataclasses.replace(
                _checkpoint(),
                phase=MigrationPhase.TARGET_AUTHORITATIVE,
                authority=AuthoritySide.SOURCE,
            )

    def test_stored_checkpoint_is_exact_revalidated_and_secret_free(self):
        checkpoint = _checkpoint()
        restored = checkpoint_from_record(checkpoint.to_record())
        self.assertEqual(restored, checkpoint)

        with self.assertRaises(ValueError):
            checkpoint_from_record({**checkpoint.to_record(), "secret": "leak"})
        with self.assertRaises(ValueError):
            checkpoint_from_record({**checkpoint.to_record(), "revision": True})
        with self.assertRaises(ValueError):
            checkpoint_from_record({**checkpoint.to_record(), "phase": "dual_authoritative"})

        serialized = repr(checkpoint.to_record()).lower()
        self.assertNotIn("password", serialized)
        self.assertNotIn("prompt", serialized)
        self.assertNotIn("payload", serialized)

    def test_copy_position_and_failure_code_are_bounded_machine_values(self):
        with self.assertRaises(ValueError):
            _progress(copy_offset=-1)
        with self.assertRaises(ValueError):
            _checkpoint(failure_code="database said password=secret")


if __name__ == "__main__":
    unittest.main()
