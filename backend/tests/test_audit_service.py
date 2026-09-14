"""Audit service lifecycle, key management, and redaction tests."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.audit import AuditPage, AuditQuery, AuditRetentionPolicy
from core.audit_service import (
    AUDIT_MASTER_KEY_CONFIG,
    AUDIT_RETENTION_CONFIG,
    AuditService,
    record_credential_response,
)
from core.management_audit import classify_management_mutation


class _Repository:
    def __init__(self):
        self.events = []
        self.queries = []
        self.prune_calls = []
        self.page = AuditPage(events=())
        self.removed_events = 0

    async def append(self, event):
        self.events.append(event)

    async def query(self, query):
        self.queries.append(query)
        return self.page

    async def prune(self, policy, *, now):
        self.prune_calls.append((policy, now))
        return self.removed_events


class _Storage:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.set_calls = []
        self.cursor_keys = []
        self.repositories = []
        self.set_result = True

    async def get_config(self, key, default=None):
        return self.values.get(key, default)

    async def set_config(self, key, value):
        self.set_calls.append((key, value))
        if not self.set_result:
            return False
        self.values[key] = value
        return True

    async def create_audit_repository(self, *, cursor_signing_key):
        self.cursor_keys.append(cursor_signing_key)
        repository = _Repository()
        self.repositories.append(repository)
        return repository


class AuditServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_start_persists_internal_master_and_redacts_before_append(self):
        storage = _Storage()
        service = await AuditService.create(storage)
        mutation = classify_management_mutation(
            "DELETE",
            "/api/virtual-keys/vk_plaintext-target",
        )

        event = await service.record(
            mutation,
            request_id="request-123",
            actor_type="panel_session",
            actor_identifier="panel-owner",
            outcome="succeeded",
        )

        self.assertEqual(storage.set_calls[0][0], AUDIT_MASTER_KEY_CONFIG)
        self.assertEqual(len(storage.cursor_keys[0]), 32)
        self.assertEqual(storage.repositories[0].events, [event])
        self.assertEqual(
            storage.repositories[0].prune_calls[0][0],
            AuditRetentionPolicy(),
        )
        self.assertEqual(storage.repositories[0].prune_calls[0][1].tzinfo, timezone.utc)
        self.assertNotIn("vk_plaintext-target", repr(event.to_record()))
        self.assertNotIn("panel-owner", repr(event.to_record()))

    async def test_restart_reuses_master_for_stable_fingerprints_and_cursors(self):
        storage = _Storage()
        first = await AuditService.create(storage)
        second = await AuditService.create(storage)
        mutation = classify_management_mutation("POST", "/api/config/save")

        first_event = await first.record(
            mutation,
            request_id="first",
            actor_type="panel_session",
            actor_identifier="panel-owner",
            outcome="succeeded",
        )
        second_event = await second.record(
            mutation,
            request_id="second",
            actor_type="panel_session",
            actor_identifier="panel-owner",
            outcome="succeeded",
        )

        self.assertEqual(len(storage.set_calls), 1)
        self.assertEqual(storage.cursor_keys[0], storage.cursor_keys[1])
        self.assertEqual(first_event.actor_fingerprint, second_event.actor_fingerprint)
        self.assertEqual(first_event.target_fingerprint, second_event.target_fingerprint)

    async def test_corrupted_internal_master_fails_closed(self):
        storage = _Storage({AUDIT_MASTER_KEY_CONFIG: "not-a-valid-key"})

        with self.assertRaisesRegex(RuntimeError, "audit master key"):
            await AuditService.create(storage)

    async def test_query_delegates_only_validated_domain_contract(self):
        storage = _Storage()
        service = await AuditService.create(storage)
        query = AuditQuery(actions=("credential.delete",), page_size=25)

        page = await service.query(query)

        self.assertIs(page, storage.repositories[0].page)
        self.assertEqual(storage.repositories[0].queries, [query])
        with self.assertRaisesRegex(ValueError, "AuditQuery"):
            await service.query(object())

    async def test_retention_policy_is_loaded_strictly_and_exposed_without_mutation(self):
        stored = {"retention_days": 180, "max_events": 250_000}
        storage = _Storage({AUDIT_RETENTION_CONFIG: stored})

        service = await AuditService.create(storage)

        self.assertEqual(
            service.retention_policy,
            AuditRetentionPolicy(retention_days=180, max_events=250_000),
        )
        self.assertEqual(storage.repositories[0].prune_calls, [])

    async def test_corrupted_retention_policy_fails_closed_before_repository_creation(self):
        invalid_policies = (
            {"retention_days": 90, "max_events": 1_000, "unexpected": True},
            {"retention_days": "90", "max_events": 1_000},
            {"retention_days": 6, "max_events": 1_000},
        )

        for stored in invalid_policies:
            with self.subTest(stored=stored):
                storage = _Storage({AUDIT_RETENTION_CONFIG: stored})
                with self.assertRaisesRegex(RuntimeError, "retention policy"):
                    await AuditService.create(storage)
                self.assertEqual(storage.repositories, [])
                self.assertEqual(storage.set_calls, [])

    async def test_retention_update_persists_policy_before_exact_prune(self):
        storage = _Storage()
        service = await AuditService.create(storage)
        policy = AuditRetentionPolicy(retention_days=30, max_events=5_000)
        now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
        storage.repositories[0].removed_events = 17

        removed = await service.update_retention(policy, now=now)

        self.assertEqual(removed, 17)
        self.assertEqual(
            storage.values[AUDIT_RETENTION_CONFIG],
            {"retention_days": 30, "max_events": 5_000},
        )
        self.assertEqual(storage.repositories[0].prune_calls, [(policy, now)])
        self.assertEqual(service.retention_policy, policy)

        mutation = classify_management_mutation("POST", "/api/config/save")
        await service.record(
            mutation,
            request_id="request-after-policy-update",
            actor_type="panel_session",
            actor_identifier="panel-owner",
            outcome="succeeded",
        )
        self.assertEqual(storage.repositories[0].prune_calls[-1][0], policy)

    async def test_retention_update_does_not_prune_when_policy_cannot_be_persisted(self):
        storage = _Storage()
        service = await AuditService.create(storage)
        storage.set_result = False
        policy = AuditRetentionPolicy(retention_days=30, max_events=5_000)

        with self.assertRaisesRegex(RuntimeError, "retention policy"):
            await service.update_retention(policy)

        self.assertEqual(storage.repositories[0].prune_calls, [])
        self.assertEqual(service.retention_policy, AuditRetentionPolicy())

    async def test_inference_audit_is_redacted_and_prunes_in_bounded_batches(self):
        storage = _Storage()
        service = await AuditService.create(storage)

        for index in range(256):
            event = await service.record_inference(
                request_id=f"inference-{index}",
                protocol="openai_chat",
                status_code=200,
            )

        repository = storage.repositories[0]
        self.assertEqual(len(repository.events), 256)
        self.assertEqual(len(repository.prune_calls), 1)
        self.assertEqual(event.action, "inference.execute")
        self.assertEqual(event.target_type, "inference_route")
        self.assertNotIn("openai_chat", repr(event.to_record()))

    async def test_credential_evidence_maps_to_canonical_durable_contract(self):
        storage = _Storage()
        service = await AuditService.create(storage)

        with patch(
            "core.audit_service.get_audit_service",
            return_value=service,
        ):
            event = await record_credential_response(
                request_id="credential-request",
                action="disable",
                mode="provider",
                filename="customer-secret.json",
                outcome="unsupported",
            )

        self.assertEqual(event.action, "credential.toggle")
        self.assertEqual(event.outcome, "invalid")
        self.assertEqual(event.change_codes, ("disabled",))
        self.assertNotIn("customer-secret.json", repr(event.to_record()))


if __name__ == "__main__":
    unittest.main()
