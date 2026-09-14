"""Production self-host capability registry contract tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.capability_registry import (
    CapabilityState,
    SupportTier,
    get_capability_snapshot,
)


class ProductCapabilityRegistryTests(unittest.TestCase):
    def test_default_snapshot_activates_only_core_capabilities(self) -> None:
        snapshot = get_capability_snapshot({})

        self.assertEqual(snapshot.schema_version, 1)
        self.assertEqual(snapshot.profile, "self_hosted")
        self.assertEqual(
            {capability.tier for capability in snapshot.capabilities},
            {SupportTier.CORE, SupportTier.ADVANCED, SupportTier.COMPATIBILITY},
        )
        active = [
            capability
            for capability in snapshot.capabilities
            if capability.state is CapabilityState.ACTIVE
        ]
        self.assertTrue(active)
        self.assertEqual({capability.tier for capability in active}, {SupportTier.CORE})
        self.assertIn("runtime.standalone", {capability.id for capability in active})
        self.assertIn("storage.sqlite", {capability.id for capability in active})

    def test_registry_is_stable_unique_and_covers_advertised_boundaries(self) -> None:
        snapshot = get_capability_snapshot({})
        identifiers = [capability.id for capability in snapshot.capabilities]

        self.assertEqual(identifiers, sorted(identifiers))
        self.assertEqual(len(identifiers), len(set(identifiers)))
        expected = {
            "deployment.docker_compose",
            "identity.local_owner",
            "identity.oidc",
            "protocol.anthropic_messages",
            "protocol.gemini_native",
            "protocol.openai_chat_completions",
            "protocol.openai_responses",
            "protocol.vertex",
            "provider.anthropic",
            "provider.google_ai_studio",
            "provider.google_antigravity",
            "provider.ollama",
            "provider.openai",
            "provider.xai",
            "runtime.standalone",
            "storage.mongodb",
            "storage.postgresql",
            "storage.sqlite",
        }
        self.assertTrue(expected.issubset(identifiers))

    def test_optional_capabilities_reflect_safe_configuration_without_secrets(self) -> None:
        environment = {
            "POSTGRESQL_URI": "postgresql://operator:database-secret@db/polaris",
            "OIDC_ENABLED": "true",
            "OIDC_CLIENT_SECRET": "oidc-secret",
            "PROMETHEUS_EXPORT_ENABLED": "true",
            "METRICS_TOKEN": "metrics-secret",
            "OTEL_EXPORT_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "https://telemetry.example/v1/metrics",
        }

        snapshot = get_capability_snapshot(environment)
        by_id = {capability.id: capability for capability in snapshot.capabilities}

        self.assertIs(by_id["storage.postgresql"].state, CapabilityState.ACTIVE)
        self.assertIs(by_id["storage.sqlite"].state, CapabilityState.AVAILABLE)
        self.assertIs(by_id["identity.oidc"].state, CapabilityState.ACTIVE)
        self.assertIs(by_id["telemetry.prometheus"].state, CapabilityState.ACTIVE)
        self.assertIs(by_id["telemetry.opentelemetry"].state, CapabilityState.ACTIVE)
        rendered = json.dumps(snapshot.model_dump(mode="json"), sort_keys=True)
        for secret in ("database-secret", "oidc-secret", "metrics-secret"):
            self.assertNotIn(secret, rendered)

    def test_retired_topology_is_not_reported_as_a_product_capability(self) -> None:
        identifiers = {item.id for item in get_capability_snapshot({}).capabilities}

        self.assertTrue(
            {
                "deployment.kubernetes",
                "runtime.coordinated",
                "runtime.multiple_replicas",
            }.isdisjoint(identifiers)
        )

    def test_conflicting_storage_selection_fails_closed(self) -> None:
        snapshot = get_capability_snapshot(
            {
                "POSTGRESQL_URI": "postgresql://db/polaris",
                "MONGODB_URI": "mongodb://db/polaris",
            }
        )
        by_id = {capability.id: capability for capability in snapshot.capabilities}

        self.assertEqual(
            {
                by_id["storage.sqlite"].state,
                by_id["storage.postgresql"].state,
                by_id["storage.mongodb"].state,
            },
            {CapabilityState.BLOCKED},
        )


if __name__ == "__main__":
    unittest.main()
