"""Redacted audit and bounded credential-operation telemetry tests."""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.credential_batch_coordination import (
    CredentialBatchCoordinationService,
    configure_credential_batch_coordination_service,
)
from core.credential_operation_evidence import (
    clear_credential_operation_evidence_for_testing,
    get_credential_audit_events,
    record_credential_mutation,
    record_durable_credential_mutation,
    render_credential_operation_metrics,
)
from core.models import CredFileActionRequest, CredFileBatchActionRequest
from core.panel.credentials import creds_action, creds_batch_action
from core.request_context import request_scope
from core.state_store import InMemoryStateStore


class CredentialOperationEvidenceDomainTests(unittest.TestCase):
    def setUp(self):
        clear_credential_operation_evidence_for_testing()

    def test_event_is_allowlisted_correlated_and_target_is_non_reversible(self):
        with request_scope("request-123"):
            event = record_credential_mutation(
                action="disable",
                operation="toggle",
                mode="primary",
                filename="person@example.com-sk-secret.json",
                variant_id="google_ai_studio",
                outcome="succeeded",
                duration_ms=12.5,
                summary_code="operation_succeeded",
            )

        self.assertEqual(event["request_id"], "request-123")
        self.assertEqual(event["actor"], "panel_session")
        self.assertEqual(event["variant_id"], "google_ai_studio")
        self.assertEqual(len(event["target_fingerprint"]), 20)
        serialized = json.dumps(event)
        self.assertNotIn("person@example.com", serialized)
        self.assertNotIn("sk-secret", serialized)
        self.assertEqual(
            set(event),
            {
                "schema_version",
                "event_id",
                "occurred_at",
                "request_id",
                "actor",
                "action",
                "operation",
                "mode",
                "target_fingerprint",
                "variant_id",
                "outcome",
                "duration_ms",
                "summary_code",
            },
        )

    def test_unknown_labels_are_collapsed_and_metrics_have_bounded_dimensions(self):
        record_credential_mutation(
            action="attacker-action",
            operation="attacker-operation",
            mode="attacker-mode",
            filename="credential.json",
            variant_id="attacker-variant",
            outcome="attacker-outcome",
            duration_ms=999999999,
            summary_code="attacker summary with unbounded text",
        )

        event = get_credential_audit_events()[-1]
        self.assertEqual(event["action"], "unknown")
        self.assertEqual(event["operation"], "unknown")
        self.assertEqual(event["mode"], "unknown")
        self.assertEqual(event["variant_id"], "unknown")
        self.assertEqual(event["outcome"], "unknown")
        self.assertEqual(event["summary_code"], "unknown")
        metrics = render_credential_operation_metrics()
        self.assertIn('operation="unknown"', metrics)
        self.assertNotIn("attacker-", metrics)

    def test_audit_retention_is_bounded_and_events_are_unique(self):
        event_ids = set()
        with patch("core.credential_operation_evidence.log.info"):
            for index in range(1005):
                event = record_credential_mutation(
                    action="disable",
                    operation="toggle",
                    mode="primary",
                    filename=f"credential-{index}.json",
                    variant_id="google_ai_studio",
                    outcome="succeeded",
                    duration_ms=1,
                    summary_code="operation_succeeded",
                )
                event_ids.add(event["event_id"])

        events = get_credential_audit_events()
        self.assertEqual(len(events), 1000)
        self.assertEqual(len(event_ids), 1005)

    def test_structured_log_is_machine_readable_and_contains_no_target_name(self):
        with patch("core.credential_operation_evidence.log.info") as emit:
            record_credential_mutation(
                action="delete",
                operation="delete",
                mode="primary",
                filename="private-person@example.com.json",
                variant_id="google_ai_studio",
                outcome="succeeded",
                duration_ms=2,
                summary_code="operation_succeeded",
            )

        payload = json.loads(emit.call_args.args[0])
        self.assertEqual(payload["event"], "credential_mutation")
        self.assertEqual(payload["outcome"], "succeeded")
        self.assertNotIn("private-person", emit.call_args.args[0])
        self.assertNotIn("@example.com", emit.call_args.args[0])


class CredentialOperationEvidenceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_credential_operation_evidence_for_testing()

    async def asyncSetUp(self) -> None:
        self.coordination_store = InMemoryStateStore()
        configure_credential_batch_coordination_service(
            CredentialBatchCoordinationService(
                self.coordination_store,
                key=b"e" * 32,
                fencing_epoch=1,
            )
        )

    async def asyncTearDown(self) -> None:
        configure_credential_batch_coordination_service(None)
        await self.coordination_store.close()

    async def test_durable_bridge_is_awaited_once_without_changing_w2_telemetry(self):
        durable_append = AsyncMock()
        with (
            request_scope("bridge-request"),
            patch(
                "core.audit_service.record_credential_response",
                durable_append,
            ),
        ):
            event = await record_durable_credential_mutation(
                action="disable",
                operation="toggle",
                mode="provider",
                filename="private.json",
                variant_id="google_ai_studio",
                outcome="succeeded",
                duration_ms=1,
                summary_code="operation_succeeded",
            )

        durable_append.assert_awaited_once_with(
            request_id="bridge-request",
            action="disable",
            mode="provider",
            filename="private.json",
            outcome="succeeded",
        )
        self.assertEqual(get_credential_audit_events(), (event,))

    async def test_durable_outage_is_secret_free_and_does_not_duplicate_legacy_event(self):
        with (
            request_scope("outage-request"),
            patch(
                "core.audit_service.record_credential_response",
                AsyncMock(side_effect=RuntimeError("database contains private.json")),
            ),
            patch("core.credential_operation_evidence.log.critical") as critical,
        ):
            await record_durable_credential_mutation(
                action="delete",
                operation="delete",
                mode="provider",
                filename="private.json",
                variant_id="google_ai_studio",
                outcome="succeeded",
                duration_ms=1,
                summary_code="operation_succeeded",
            )

        self.assertEqual(len(get_credential_audit_events()), 1)
        self.assertNotIn("private.json", critical.call_args.args[0])

    async def test_single_mutation_emits_exactly_one_redacted_event(self):
        storage = AsyncMock()
        storage.get_credential.return_value = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "must-not-leak",
        }
        with (
            request_scope("single-request-1"),
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credentials.credential_manager.set_cred_disabled",
                new=AsyncMock(return_value=True),
            ),
        ):
            await creds_action(
                CredFileActionRequest(filename="studio.json", action="disable"),
                token="session-secret",
                mode="provider",
            )

        events = get_credential_audit_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["outcome"], "succeeded")
        self.assertEqual(events[0]["request_id"], "single-request-1")
        self.assertNotIn("session-secret", json.dumps(events))
        self.assertNotIn("must-not-leak", json.dumps(events))

    async def test_idempotent_batch_retry_does_not_emit_a_duplicate_event(self):
        storage = AsyncMock()
        storage.get_credential.return_value = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "must-not-leak",
        }
        request = CredFileBatchActionRequest(
            action="disable",
            filenames=["studio.json"],
            idempotency_key="evidence-retry-001",
        )
        durable_append = AsyncMock()
        with (
            request_scope("batch-request-1"),
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credentials.credential_manager.set_cred_disabled",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "core.audit_service.record_credential_response",
                durable_append,
            ),
        ):
            await creds_batch_action(request, token="session", mode="provider")
            await creds_batch_action(request, token="session", mode="provider")

        events = get_credential_audit_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["outcome"], "succeeded")
        durable_append.assert_awaited_once()

    async def test_unsupported_mutation_emits_one_typed_event_without_secrets(self):
        storage = AsyncMock()
        storage.get_credential.return_value = {
            "provider": "unregistered-provider",
            "credential_type": "api_key",
            "api_key": "must-not-leak",
        }
        with patch(
            "core.panel.credentials.get_storage_adapter",
            AsyncMock(return_value=storage),
        ):
            response = await creds_action(
                CredFileActionRequest(filename="unknown.json", action="disable"),
                token="session",
                mode="provider",
            )

        self.assertEqual(response.status_code, 422)
        events = get_credential_audit_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["outcome"], "unsupported")
        self.assertEqual(events[0]["summary_code"], "credential_operation_unsupported")
        self.assertNotIn("must-not-leak", json.dumps(events))

    async def test_batch_timeout_emits_timed_out_not_cancelled(self):
        storage = AsyncMock()
        storage.get_credential.return_value = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "must-not-leak",
        }

        async def slow_operation(*_args, **_kwargs):
            await asyncio.sleep(0.05)

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch("core.panel.credentials.BATCH_ITEM_TIMEOUT_SECONDS", 0.001),
            patch("core.panel.credentials._apply_credential_action", slow_operation),
        ):
            response = await creds_batch_action(
                CredFileBatchActionRequest(action="disable", filenames=["studio.json"]),
                token="session",
                mode="provider",
            )

        self.assertEqual(json.loads(response.body)["results"][0]["status"], "timed_out")
        events = get_credential_audit_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["outcome"], "timed_out")

    async def test_storage_failure_still_emits_one_safe_failed_event(self):
        with patch(
            "core.panel.credentials.get_storage_adapter",
            AsyncMock(side_effect=RuntimeError("database-password-must-not-leak")),
        ):
            with self.assertRaises(Exception):
                await creds_action(
                    CredFileActionRequest(filename="studio.json", action="disable"),
                    token="session",
                    mode="provider",
                )

        events = get_credential_audit_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["outcome"], "failed")
        self.assertEqual(events[0]["summary_code"], "operation_failed")
        self.assertNotIn("database-password", json.dumps(events))

    async def test_batch_planning_failure_emits_failed_event_for_each_target(self):
        with patch(
            "core.panel.credentials.get_storage_adapter",
            AsyncMock(side_effect=RuntimeError("storage-secret-must-not-leak")),
        ):
            with self.assertRaises(Exception):
                await creds_batch_action(
                    CredFileBatchActionRequest(
                        action="disable",
                        filenames=["first.json", "second.json"],
                    ),
                    token="session",
                    mode="provider",
                )

        events = get_credential_audit_events()
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event["outcome"] == "failed" for event in events))
        self.assertNotIn("storage-secret", json.dumps(events))


if __name__ == "__main__":
    unittest.main()
