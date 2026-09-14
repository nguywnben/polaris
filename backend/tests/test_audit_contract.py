"""Contract tests for append-only, redacted enterprise audit events."""

from __future__ import annotations

import dataclasses
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.audit import (
    AUDIT_SCHEMA_VERSION,
    AuditEvent,
    AuditQuery,
    AuditRepository,
    AuditRetentionPolicy,
    create_audit_event,
    decode_audit_cursor,
    encode_audit_cursor,
)

FINGERPRINT_KEY = b"audit-contract-fingerprint-key-32b"
CURSOR_KEY = b"audit-contract-cursor-signing-key-32"


class AuditEventContractTests(unittest.TestCase):
    def test_event_is_versioned_immutable_and_contains_only_redacted_identifiers(self):
        event = create_audit_event(
            request_id="request-123",
            actor_type="panel_session",
            actor_identifier="owner@example.com",
            action="credential.delete",
            target_type="credential",
            target_identifier="private-key-file.json",
            outcome="succeeded",
            change_codes=("deleted",),
            fingerprint_key=FINGERPRINT_KEY,
            occurred_at=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
        )

        payload = event.to_record()
        serialized = json.dumps(payload, sort_keys=True)

        self.assertEqual(payload["schema_version"], AUDIT_SCHEMA_VERSION)
        self.assertEqual(payload["request_id"], "request-123")
        self.assertEqual(payload["change_codes"], ["deleted"])
        self.assertRegex(payload["actor_fingerprint"], r"^[0-9a-f]{20}$")
        self.assertRegex(payload["target_fingerprint"], r"^[0-9a-f]{20}$")
        self.assertNotIn("owner@example.com", serialized)
        self.assertNotIn("private-key-file.json", serialized)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            event.outcome = "failed"

    def test_unrecognized_vocabularies_and_unbounded_identifiers_fail_closed(self):
        base = {
            "request_id": "request-123",
            "actor_type": "panel_session",
            "actor_identifier": "panel-owner",
            "action": "credential.delete",
            "target_type": "credential",
            "target_identifier": "credential.json",
            "outcome": "succeeded",
            "change_codes": ("deleted",),
            "fingerprint_key": FINGERPRINT_KEY,
        }
        invalid_patches = (
            {"actor_type": "administrator"},
            {"action": "credential.exfiltrate"},
            {"target_type": "plaintext_secret"},
            {"outcome": "mostly_ok"},
            {"change_codes": ("raw_secret_changed",)},
            {"request_id": "contains whitespace"},
            {"target_identifier": "x" * 513},
            {"fingerprint_key": b"too-short"},
        )

        for patch in invalid_patches:
            with self.subTest(patch=patch):
                with self.assertRaises(ValueError):
                    create_audit_event(**(base | patch))

    def test_oidc_actor_and_identity_target_are_hmac_redacted(self):
        stable_actor = "https://idp.example/tenant\0subject-123"
        identity_id = "idn_0123456789abcdef0123456789abcdef"

        event = create_audit_event(
            request_id="request-identity-update",
            actor_type="oidc_user",
            actor_identifier=stable_actor,
            action="identity.update",
            target_type="identity",
            target_identifier=identity_id,
            outcome="succeeded",
            change_codes=("updated",),
            fingerprint_key=FINGERPRINT_KEY,
        )

        serialized = json.dumps(event.to_record(), sort_keys=True)
        self.assertNotIn(stable_actor, serialized)
        self.assertNotIn("subject-123", serialized)
        self.assertNotIn(identity_id, serialized)
        self.assertRegex(event.actor_fingerprint, r"^[0-9a-f]{20}$")

    def test_direct_event_construction_cannot_bypass_redaction_validation(self):
        with self.assertRaises(ValueError):
            AuditEvent(
                schema_version=AUDIT_SCHEMA_VERSION,
                event_id="a" * 32,
                occurred_at="2026-08-24T12:00:00+00:00",
                request_id="request-123",
                actor_type="panel_session",
                actor_fingerprint="owner@example.com",
                action="credential.delete",
                target_type="credential",
                target_fingerprint="private-key-file.json",
                outcome="succeeded",
                change_codes=("deleted",),
            )

    def test_change_summary_is_bounded_deduplicated_and_ordered(self):
        event = create_audit_event(
            request_id="request-123",
            actor_type="panel_session",
            actor_identifier="panel-owner",
            action="virtual_key.update",
            target_type="virtual_key",
            target_identifier="vk_private",
            outcome="succeeded",
            change_codes=("limits_changed", "scopes_changed", "limits_changed"),
            fingerprint_key=FINGERPRINT_KEY,
        )

        self.assertEqual(event.change_codes, ("limits_changed", "scopes_changed"))
        with self.assertRaises(ValueError):
            create_audit_event(
                request_id="request-123",
                actor_type="panel_session",
                actor_identifier="panel-owner",
                action="virtual_key.update",
                target_type="virtual_key",
                target_identifier="vk_private",
                outcome="succeeded",
                change_codes=("updated",) * 17,
                fingerprint_key=FINGERPRINT_KEY,
            )


class AuditQueryContractTests(unittest.TestCase):
    def test_query_and_retention_bounds_are_explicit(self):
        query = AuditQuery(
            actor_fingerprints=("a" * 20,),
            actions=("credential.delete",),
            outcomes=("failed", "succeeded"),
            target_fingerprints=("b" * 20,),
            page_size=200,
        )
        policy = AuditRetentionPolicy(retention_days=90, max_events=1_000_000)

        self.assertEqual(query.page_size, 200)
        self.assertEqual(query.actor_fingerprints, ("a" * 20,))
        self.assertEqual(query.target_fingerprints, ("b" * 20,))
        self.assertEqual(policy.retention_days, 90)
        for invalid_size in (0, 201):
            with self.assertRaises(ValueError):
                AuditQuery(page_size=invalid_size)
        for invalid_days in (6, 3651):
            with self.assertRaises(ValueError):
                AuditRetentionPolicy(retention_days=invalid_days)

    def test_filter_vocabularies_fail_closed(self):
        with self.assertRaises(ValueError):
            AuditQuery(actions=("unknown.action",))
        with self.assertRaises(ValueError):
            AuditQuery(outcomes=("successful-ish",))
        with self.assertRaises(ValueError):
            AuditQuery(request_id="unsafe request id")
        with self.assertRaises(ValueError):
            AuditQuery(actor_fingerprints=("owner@example.com",))
        with self.assertRaises(ValueError):
            AuditQuery(target_fingerprints=("raw-target",))

    def test_cursor_is_opaque_round_trippable_and_tamper_evident(self):
        cursor = encode_audit_cursor(
            occurred_at="2026-08-24T12:00:00+00:00",
            event_id="a" * 32,
            signing_key=CURSOR_KEY,
        )

        self.assertNotIn("2026-08-24", cursor)
        self.assertEqual(
            decode_audit_cursor(cursor, signing_key=CURSOR_KEY),
            ("2026-08-24T12:00:00+00:00", "a" * 32),
        )
        replacement = "A" if cursor[-1] != "A" else "B"
        with self.assertRaises(ValueError):
            decode_audit_cursor(cursor[:-1] + replacement, signing_key=CURSOR_KEY)

    def test_repository_surface_is_append_query_and_policy_prune_only(self):
        members = set(AuditRepository.__dict__)

        self.assertTrue({"append", "query", "prune"}.issubset(members))
        self.assertNotIn("update", members)
        self.assertNotIn("delete", members)


if __name__ == "__main__":
    unittest.main()
