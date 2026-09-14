from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.quality_policy import (
    QualityPolicyError,
    assess_policy_warnings,
    build_policy_document,
    get_profile_defaults,
    load_policy_document,
    preview_policy,
    project_legacy_policy,
)


def balanced_legacy() -> dict:
    return {
        "compatibility_mode_enabled": False,
        "return_thoughts_to_frontend": True,
        "anti_truncation_max_attempts": 3,
        "token_compression_enabled": True,
        "token_compression_threshold": 32_000,
        "token_compression_target": 24_000,
        "token_compression_min_recent_turns": 4,
        "guardrails_enabled": False,
        "guardrails_pii_masking_enabled": True,
        "guardrails_injection_detection_enabled": True,
        "guardrails_blocked_keywords": [],
        "response_cache_enabled": False,
        "response_cache_ttl_seconds": 300,
        "response_cache_max_entries": 1_000,
    }


class QualityPolicyDomainTests(unittest.TestCase):
    def test_safe_presets_have_bounded_compression_and_anti_truncation(self):
        presets = get_profile_defaults()

        self.assertEqual(
            {
                profile: settings["anti_truncation_max_attempts"]
                for profile, settings in presets.items()
            },
            {"quality": 5, "balanced": 3, "capacity": 2},
        )
        self.assertFalse(presets["quality"]["compression"]["enabled"])
        for profile, settings in presets.items():
            with self.subTest(profile=profile):
                compression = settings["compression"]
                self.assertEqual(compression["mode"], "structural")
                self.assertLess(compression["target_tokens"], compression["threshold_tokens"])
                self.assertGreaterEqual(compression["min_recent_turns"], 3)

    def test_default_legacy_settings_project_to_balanced_without_persistence(self):
        policy = project_legacy_policy(balanced_legacy())

        self.assertEqual(policy["schema_version"], 1)
        self.assertEqual(policy["revision"], 0)
        self.assertEqual(policy["profile"], "balanced")
        self.assertEqual(policy["source"], "legacy_projection")
        self.assertEqual(policy["settings"]["compression"]["target_tokens"], 24_000)

    def test_nonstandard_legacy_settings_project_to_custom_without_changing_values(self):
        legacy = balanced_legacy()
        legacy["token_compression_enabled"] = False
        legacy["return_thoughts_to_frontend"] = False

        policy = project_legacy_policy(legacy)

        self.assertEqual(policy["profile"], "custom")
        self.assertFalse(policy["settings"]["compression"]["enabled"])
        self.assertFalse(policy["settings"]["return_reasoning"])

    def test_quality_preset_disables_compression_and_exact_response_cache(self):
        policy = build_policy_document(profile="quality", revision=1)

        self.assertFalse(policy["settings"]["compression"]["enabled"])
        self.assertFalse(policy["settings"]["response_cache"]["enabled"])
        self.assertTrue(policy["settings"]["return_reasoning"])

    def test_custom_policy_rejects_a_target_that_is_not_below_the_threshold(self):
        settings = project_legacy_policy(balanced_legacy())["settings"]
        settings["compression"]["target_tokens"] = settings["compression"]["threshold_tokens"]

        with self.assertRaises(QualityPolicyError) as context:
            build_policy_document(profile="custom", revision=1, settings=settings)

        self.assertEqual(context.exception.code, "quality_policy_invalid")

    def test_stored_preset_cannot_smuggle_settings_that_differ_from_its_profile(self):
        stored = build_policy_document(profile="balanced", revision=4)
        stored["settings"]["compression"]["enabled"] = False

        with self.assertRaises(QualityPolicyError):
            load_policy_document(stored, balanced_legacy())

    def test_preview_is_bounded_redacted_and_does_not_claim_a_provider_call(self):
        policy = build_policy_document(profile="balanced", revision=2)

        result = preview_policy(
            policy,
            {
                "estimated_input_tokens": 50_000,
                "message_count": 40,
                "tool_count": 3,
                "has_system_instruction": True,
                "has_tool_pairs": True,
            },
        )

        self.assertEqual(result["decision"]["reason"], "structural_compression_candidate")
        self.assertEqual(result["decision"]["estimated_tokens_after"], 24_000)
        self.assertFalse(result["provider_call"])
        self.assertFalse(result["persisted"])
        self.assertNotIn("prompt", str(result).lower())

    def test_preview_and_runtime_agree_that_threshold_is_not_exceeded_at_equality(self):
        policy = build_policy_document(profile="balanced", revision=2)

        result = preview_policy(
            policy,
            {
                "estimated_input_tokens": 32_000,
                "message_count": 40,
                "tool_count": 0,
                "has_system_instruction": False,
                "has_tool_pairs": False,
            },
        )

        self.assertEqual(result["decision"]["reason"], "below_compression_threshold")
        self.assertEqual(result["decision"]["estimated_tokens_before"], 32_000)
        self.assertEqual(result["decision"]["estimated_tokens_after"], 32_000)

    def test_policy_warnings_name_risky_combinations_without_flagging_balanced(self):
        balanced = build_policy_document(profile="balanced", revision=1)["settings"]
        self.assertEqual(assess_policy_warnings(balanced), [])

        risky = build_policy_document(profile="balanced", revision=1)["settings"]
        risky["compatibility_mode"] = True
        risky["anti_truncation_max_attempts"] = 7
        risky["compression"]["min_recent_turns"] = 1
        risky["guardrails"].update(
            enabled=True,
            pii_masking_enabled=False,
            injection_detection_enabled=False,
        )
        risky["response_cache"]["enabled"] = True

        self.assertEqual(
            assess_policy_warnings(risky),
            [
                "compatibility_changes_instruction_shape",
                "low_recent_turn_retention",
                "guardrails_without_checks",
                "cache_with_reasoning",
                "high_recovery_attempts",
            ],
        )

    def test_preview_reports_transform_scope_and_estimated_removed_messages(self):
        policy = build_policy_document(profile="balanced", revision=2)

        result = preview_policy(
            policy,
            {
                "estimated_input_tokens": 48_000,
                "message_count": 24,
                "tool_count": 2,
                "has_system_instruction": True,
                "has_tool_pairs": True,
            },
        )

        self.assertTrue(result["transformation"]["will_transform"])
        self.assertEqual(result["transformation"]["scope"], "history_prefix_only")
        self.assertEqual(result["transformation"]["failure_behavior"], "forward_unchanged")
        self.assertEqual(result["transformation"]["estimated_removed_messages"], 12)
        self.assertFalse(result["provider_call"])


if __name__ == "__main__":
    unittest.main()
