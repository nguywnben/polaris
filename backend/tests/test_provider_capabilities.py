"""Provider capability contract tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.provider_registry import (
    ANTHROPIC,
    CLAUDE_CODE,
    CLAUDE_PLATFORM,
    CODEX,
    CREDENTIAL_OPERATIONS,
    GOOGLE_AI_STUDIO,
    GOOGLE_ANTIGRAVITY,
    GROK,
    INFERENCE_PROTOCOLS,
    MODEL_SUPPORT_DECLARED,
    MODEL_SUPPORT_INFERRED,
    MODEL_SUPPORT_UNSUPPORTED,
    OLLAMA,
    OPENAI,
    OPENAI_PLATFORM,
    XAI,
    XAI_CONSOLE,
    credential_model_support_level,
    credential_supports_model,
    credential_supports_operation,
    get_credential_provider_display_name,
    get_credential_provider_variant,
    get_credential_variant_capabilities,
    get_declared_credential_models,
    get_provider_capabilities,
    list_credential_variant_capabilities,
    list_provider_capabilities,
)


class ProviderCapabilityTests(unittest.TestCase):
    def test_kiro_reauthentication_only_applies_to_oauth(self):
        self.assertTrue(
            credential_supports_operation(
                {"provider": "kiro", "credential_type": "oauth"}, "reauthenticate"
            )
        )
        self.assertFalse(
            credential_supports_operation(
                {"provider": "kiro", "credential_type": "api_key", "api_key": "synthetic"},
                "reauthenticate",
            )
        )

    def test_every_advertised_variant_matches_the_production_capability_matrix(self):
        common = {
            "add",
            "verify",
            "test",
            "model_discovery",
            "disable",
            "edit",
            "export",
            "delete",
            "toggle",
        }
        oauth = common | {"refresh", "reauthenticate"}
        expected_operations = {
            **dict.fromkeys(
                (
                    "kimi",
                    "cloudflare",
                    "nvidia",
                    "poolside",
                    "kimchi",
                    "kilo",
                    "opencode",
                    "kiro",
                    "meta",
                    "groq",
                    "deepseek",
                    "mistral",
                    "cerebras",
                ),
                common,
            ),
            GOOGLE_ANTIGRAVITY: oauth | {"quota", "credit_mode"},
            "muse_code": oauth | {"quota"},
            "kiro": common | {"reauthenticate", "quota"},
            GOOGLE_AI_STUDIO: common,
            GROK: oauth | {"quota"},
            XAI_CONSOLE: common,
            CODEX: oauth | {"quota"},
            OPENAI_PLATFORM: common,
            CLAUDE_CODE: oauth | {"quota"},
            CLAUDE_PLATFORM: common,
            OLLAMA: common,
        }

        variants = list_credential_variant_capabilities()

        self.assertEqual(len(variants), len(expected_operations))
        for variant in variants:
            with self.subTest(variant=variant["variant_id"]):
                self.assertEqual(
                    set(variant["operations"]),
                    expected_operations[variant["variant_id"]],
                )
                self.assertEqual(set(variant["inference_protocols"]), INFERENCE_PROTOCOLS)

    def test_every_console_credential_variant_declares_operations(self):
        variants = list_credential_variant_capabilities()

        self.assertEqual(
            {variant["variant_id"] for variant in variants},
            {
                GOOGLE_ANTIGRAVITY,
                GOOGLE_AI_STUDIO,
                GROK,
                XAI_CONSOLE,
                CODEX,
                OPENAI_PLATFORM,
                CLAUDE_CODE,
                CLAUDE_PLATFORM,
                OLLAMA,
                "kimi",
                "cloudflare",
                "nvidia",
                "poolside",
                "kimchi",
                "kilo",
                "opencode",
                "kiro",
                "meta",
                "muse_code",
                "groq",
                "deepseek",
                "mistral",
                "cerebras",
            },
        )
        self.assertTrue(all(variant["operations"] for variant in variants))
        self.assertTrue(
            all(set(variant["operations"]) <= CREDENTIAL_OPERATIONS for variant in variants)
        )

    def test_common_operations_are_conservative_and_variant_specific(self):
        common = {
            "add",
            "verify",
            "test",
            "model_discovery",
            "disable",
            "edit",
            "toggle",
            "delete",
            "export",
        }
        oauth = common | {"refresh", "reauthenticate"}
        expected = {
            **dict.fromkeys(
                (
                    "kimi",
                    "cloudflare",
                    "nvidia",
                    "poolside",
                    "kimchi",
                    "kilo",
                    "opencode",
                    "kiro",
                    "meta",
                    "groq",
                    "deepseek",
                    "mistral",
                    "cerebras",
                ),
                common,
            ),
            GOOGLE_ANTIGRAVITY: oauth | {"quota", "credit_mode"},
            "muse_code": oauth | {"quota"},
            "kiro": common | {"reauthenticate", "quota"},
            GOOGLE_AI_STUDIO: common,
            GROK: oauth | {"quota"},
            XAI_CONSOLE: common,
            CODEX: oauth | {"quota"},
            OPENAI_PLATFORM: common,
            CLAUDE_CODE: oauth | {"quota"},
            CLAUDE_PLATFORM: common,
            OLLAMA: common,
        }

        self.assertEqual(
            {
                variant["variant_id"]: set(variant["operations"])
                for variant in list_credential_variant_capabilities()
            },
            expected,
        )

        self.assertTrue(
            credential_supports_operation(
                {"provider": GOOGLE_ANTIGRAVITY, "credential_type": "oauth"},
                "quota",
            )
        )
        self.assertTrue(
            credential_supports_operation({"provider": XAI, "credential_type": "oauth"}, "quota")
        )
        self.assertTrue(
            credential_supports_operation({"provider": OPENAI, "credential_type": "oauth"}, "quota")
        )
        self.assertFalse(
            credential_supports_operation(
                {"provider": GOOGLE_AI_STUDIO, "credential_type": "api_key"},
                "quota",
            )
        )
        self.assertTrue(
            credential_supports_operation(
                {"provider": GOOGLE_ANTIGRAVITY, "credential_type": "oauth"},
                "credit_mode",
            )
        )
        self.assertFalse(
            credential_supports_operation(
                {"provider": XAI, "credential_type": "oauth"}, "credit_mode"
            )
        )

    def test_unknown_variants_and_operations_fail_closed(self):
        self.assertIsNone(get_credential_variant_capabilities("unknown-provider"))
        self.assertFalse(
            credential_supports_operation(
                {"provider": "unknown-provider", "credential_type": "api_key"},
                "delete",
            )
        )
        self.assertFalse(
            credential_supports_operation(
                {"provider": OPENAI, "credential_type": "api_key"},
                "arbitrary-operation",
            )
        )

    def test_catalog_has_stable_unique_provider_ids(self):
        providers = list_provider_capabilities()

        self.assertEqual(
            {provider["provider_id"] for provider in providers},
            {
                ANTHROPIC,
                GOOGLE_ANTIGRAVITY,
                GOOGLE_AI_STUDIO,
                OLLAMA,
                OPENAI,
                XAI,
                "kimi",
                "cloudflare",
                "nvidia",
                "poolside",
                "kimchi",
                "kilo",
                "opencode",
                "kiro",
                "meta",
                "muse_code",
                "groq",
                "deepseek",
                "mistral",
                "cerebras",
            },
        )

    def test_anthropic_credentials_use_precise_user_facing_provider_names(self):
        oauth_credential = {"provider": ANTHROPIC, "credential_type": "oauth"}
        api_key_credential = {"provider": ANTHROPIC, "credential_type": "api_key"}

        self.assertEqual(get_credential_provider_variant(oauth_credential), CLAUDE_CODE)
        self.assertEqual(get_credential_provider_display_name(oauth_credential), "Claude Code")
        self.assertEqual(get_credential_provider_variant(api_key_credential), CLAUDE_PLATFORM)
        self.assertEqual(
            get_credential_provider_display_name(api_key_credential),
            "Claude Platform",
        )

    def test_ollama_accepts_discovered_models_without_brand_prefix_assumptions(self):
        capabilities = get_provider_capabilities(OLLAMA)

        self.assertEqual(capabilities.credential_types, ("connection",))
        self.assertTrue(capabilities.supports_model("qwen3.5"))
        self.assertTrue(capabilities.supports_model("custom-lab-model:latest"))

    def test_ai_studio_only_accepts_declared_model_families(self):
        capabilities = get_provider_capabilities(GOOGLE_AI_STUDIO)

        self.assertTrue(capabilities.supports_model("models/gemini-2.5-flash"))
        self.assertTrue(capabilities.supports_model("gemma-3-27b-it"))
        self.assertFalse(capabilities.supports_model("claude-sonnet-4-6"))

    def test_antigravity_declares_oauth_credentials(self):
        capabilities = get_provider_capabilities(GOOGLE_ANTIGRAVITY)

        self.assertEqual(capabilities.credential_types, ("oauth",))

    def test_xai_declares_dual_auth_and_grok_models(self):
        capabilities = get_provider_capabilities(XAI)

        self.assertEqual(capabilities.display_name, "Grok Build")
        self.assertEqual(capabilities.credential_types, ("oauth", "api_key"))
        self.assertTrue(capabilities.supports_model("grok-4"))
        self.assertFalse(capabilities.supports_model("gemini-2.5-flash"))

    def test_xai_credentials_use_precise_user_facing_provider_names(self):
        oauth_credential = {"provider": XAI, "credential_type": "oauth"}
        api_key_credential = {"provider": XAI, "credential_type": "api_key"}

        self.assertEqual(get_credential_provider_variant(oauth_credential), GROK)
        self.assertEqual(get_credential_provider_display_name(oauth_credential), "Grok Build")
        self.assertEqual(get_credential_provider_variant(api_key_credential), XAI_CONSOLE)
        self.assertEqual(
            get_credential_provider_display_name(api_key_credential),
            "SpaceXAI Console",
        )
        self.assertEqual(
            get_credential_provider_display_name({"provider": XAI, "api_key": "legacy-api-key"}),
            "SpaceXAI Console",
        )

    def test_openai_credentials_use_precise_user_facing_provider_names(self):
        oauth_credential = {"provider": OPENAI, "credential_type": "oauth"}
        api_key_credential = {"provider": OPENAI, "credential_type": "api_key"}

        self.assertEqual(get_credential_provider_variant(oauth_credential), CODEX)
        self.assertEqual(get_credential_provider_display_name(oauth_credential), "Codex")
        self.assertEqual(get_credential_provider_variant(api_key_credential), OPENAI_PLATFORM)
        self.assertEqual(
            get_credential_provider_display_name(api_key_credential),
            "OpenAI Platform",
        )

    def test_credential_model_catalog_restricts_individual_api_keys(self):
        credential = {
            "provider": GOOGLE_AI_STUDIO,
            "credential_type": "api_key",
            "api_key": "example-key",
            "model_ids": ["gemini-2.5-flash"],
        }

        self.assertTrue(credential_supports_model(credential, "gemini-2.5-flash"))
        self.assertFalse(credential_supports_model(credential, "gemini-2.5-pro"))

    def test_model_support_level_distinguishes_declared_inferred_and_unsupported(self):
        declared = {
            "provider": GOOGLE_AI_STUDIO,
            "credential_type": "api_key",
            "api_key": "example-key",
            "model_ids": ["gemini-2.5-flash"],
        }
        inferred = {
            "provider": GOOGLE_ANTIGRAVITY,
            "token": "example-token",
        }

        self.assertEqual(
            credential_model_support_level(declared, "gemini-2.5-flash"),
            MODEL_SUPPORT_DECLARED,
        )
        self.assertEqual(
            credential_model_support_level(inferred, "gemini-2.5-flash"),
            MODEL_SUPPORT_INFERRED,
        )
        self.assertEqual(
            credential_model_support_level(declared, "grok-4"),
            MODEL_SUPPORT_UNSUPPORTED,
        )

    def test_credential_model_catalog_preserves_non_google_namespaces(self):
        credential = {
            "provider": "google_ai_studio",
            "api_key": "test-key",
            "model_ids": ["models/gemini-2.5-flash"],
        }

        self.assertFalse(credential_supports_model(credential, "other/gemini-2.5-flash"))

    def test_declared_model_catalog_is_normalized_and_deduplicated(self):
        credential = {
            "model_ids": [
                " models/gemini-2.5-flash ",
                "gemini-2.5-flash",
                "gemini-2.5-pro",
                "",
                None,
            ]
        }

        self.assertEqual(
            get_declared_credential_models(credential),
            ["gemini-2.5-flash", "gemini-2.5-pro"],
        )


if __name__ == "__main__":
    unittest.main()
