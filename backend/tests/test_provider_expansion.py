"""Registration and isolation contracts for the September provider expansion."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.provider_registry import (
    credential_supports_model,
    get_credential_variant_capabilities,
    get_static_credential_identity,
)


class ProviderExpansionRegistryTests(unittest.TestCase):
    def test_provider_operations_preserve_key_support_and_kiro_oauth_default(self):
        for provider in (
            "kimi",
            "cloudflare",
            "nvidia",
            "poolside",
            "kimchi",
            "kilo",
            "opencode",
            "kiro",
        ):
            with self.subTest(provider=provider):
                contract = get_credential_variant_capabilities(provider)
                self.assertIsNotNone(contract)
                self.assertEqual(
                    contract.credential_type, "oauth" if provider == "kiro" else "api_key"
                )
                self.assertIn("test", contract.operations)
                self.assertNotIn("refresh", contract.operations)
                if provider == "kiro":
                    self.assertIn("quota", contract.operations)
                    self.assertIn("reauthenticate", contract.operations)
                else:
                    self.assertNotIn("quota", contract.operations)
                    self.assertNotIn("reauthenticate", contract.operations)

    def test_undiscovered_credentials_do_not_claim_arbitrary_models(self):
        self.assertFalse(credential_supports_model({"provider": "kilo"}, "unknown-model"))
        self.assertTrue(
            credential_supports_model(
                {"provider": "kilo", "model_ids": ["vendor/model"]}, "vendor/model"
            )
        )

    def test_only_relevant_connection_context_changes_identity(self):
        relevant = {
            "kimi": {"base_url"},
            "cloudflare": {"base_url", "account_id"},
            "nvidia": {"base_url"},
            "poolside": {"base_url"},
            "kimchi": {"base_url"},
            "kilo": {"base_url", "organization_id"},
            "opencode": {"base_url", "plan"},
            "kiro": {"region", "profile_arn"},
        }
        for provider, fields in relevant.items():
            for field in {
                "account_id",
                "organization_id",
                "base_url",
                "plan",
                "region",
                "profile_arn",
            }:
                with self.subTest(provider=provider, field=field):
                    base = {
                        "provider": provider,
                        "credential_type": "api_key",
                        "api_key": "test-key",
                    }
                    a = get_static_credential_identity({**base, field: "a"})
                    b = get_static_credential_identity({**base, field: "b"})
                    self.assertEqual(a != b, field in fields)

    def test_implicit_defaults_and_normalized_values_do_not_create_duplicates(self):
        from core.hosted_providers import HOSTED_PROVIDERS

        for provider, metadata in HOSTED_PROVIDERS.items():
            with self.subTest(provider=provider):
                base = {"provider": provider, "credential_type": "api_key", "api_key": "test-key"}
                identity = get_static_credential_identity(base)
                for endpoint in [
                    metadata["base_url"],
                    metadata["base_url"] + "/",
                    metadata["base_url"]
                    .replace(".com/", ".com:443/")
                    .replace(".ai/", ".ai:443/")
                    .replace(".dev/", ".dev:443/"),
                ]:
                    self.assertEqual(
                        identity, get_static_credential_identity({**base, "base_url": endpoint})
                    )
        for provider, extra in [
            ("kiro", {"region": "us-east-1"}),
            ("opencode", {"plan": "zen", "base_url": "https://opencode.ai/zen/v1"}),
        ]:
            base = {"provider": provider, "credential_type": "api_key", "api_key": "test-key"}
            self.assertEqual(
                get_static_credential_identity(base),
                get_static_credential_identity({**base, **extra}),
            )
        base = {
            "provider": "opencode",
            "credential_type": "api_key",
            "api_key": "test-key",
            "plan": "go",
        }
        self.assertEqual(
            get_static_credential_identity(base),
            get_static_credential_identity({**base, "base_url": "https://opencode.ai/zen/go/v1"}),
        )

    def test_nonconnection_metadata_and_account_case_do_not_change_identity(self):
        base = {
            "provider": "cloudflare",
            "credential_type": "api_key",
            "api_key": "test-key",
            "account_id": "a" * 32,
        }
        other = {
            **base,
            "account_id": "A" * 32,
            "credential_label": "Other",
            "model_ids": ["new"],
            "api_key": " test-key ",
        }
        self.assertEqual(
            get_static_credential_identity(base), get_static_credential_identity(other)
        )
