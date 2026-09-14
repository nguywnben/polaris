"""Behavior tests for token-aware conversation compression."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.token_compression import CompressionSettings, compress_gemini_request
from core.token_estimator import estimate_input_tokens


def text_content(role: str, text: str):
    return {"role": role, "parts": [{"text": text}]}


class TokenCompressionTests(unittest.TestCase):
    def test_settings_reject_values_outside_policy_bounds(self):
        invalid_settings = (
            {"threshold_tokens": 2_000_001},
            {"target_tokens": 2_000_000, "threshold_tokens": 2_000_001},
            {"min_recent_turns": 51},
        )
        for overrides in invalid_settings:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                CompressionSettings(**overrides)

    def test_request_below_threshold_is_preserved(self):
        payload = {
            "systemInstruction": {"parts": [{"text": "Keep this instruction."}]},
            "contents": [text_content("user", "short request")],
        }
        settings = CompressionSettings(
            enabled=True,
            threshold_tokens=1000,
            target_tokens=800,
            min_recent_turns=2,
        )

        result = compress_gemini_request(payload, settings)

        self.assertFalse(result.applied)
        self.assertEqual(result.request, payload)
        self.assertEqual(result.estimated_tokens_saved, 0)

    def test_oversized_history_keeps_system_instruction_and_recent_turns(self):
        contents = []
        for index in range(5):
            contents.append(text_content("user", f"user-{index}-" + "u" * 160))
            contents.append(text_content("model", f"model-{index}-" + "m" * 160))
        payload = {
            "systemInstruction": {"parts": [{"text": "Never remove this."}]},
            "contents": contents,
            "tools": [{"functionDeclarations": [{"name": "lookup"}]}],
        }
        settings = CompressionSettings(
            enabled=True,
            threshold_tokens=300,
            target_tokens=220,
            min_recent_turns=2,
            quality_profile="balanced",
            quality_policy_revision=9,
        )

        result = compress_gemini_request(payload, settings)

        self.assertTrue(result.applied)
        self.assertEqual(result.request["systemInstruction"], payload["systemInstruction"])
        self.assertEqual(result.request["tools"], payload["tools"])
        self.assertEqual(result.request["contents"], contents[-4:])
        self.assertEqual(result.removed_contents, 6)
        self.assertGreater(result.estimated_tokens_saved, 0)
        self.assertEqual(result.as_metrics()["quality_profile"], "balanced")
        self.assertEqual(result.as_metrics()["quality_policy_revision"], 9)
        self.assertEqual(result.as_metrics()["compression_reason"], result.reason)

    def test_compression_never_starts_with_an_orphaned_tool_result(self):
        contents = [
            text_content("user", "old request " + "x" * 300),
            {
                "role": "model",
                "parts": [{"functionCall": {"name": "lookup", "args": {}}}],
            },
            {
                "role": "user",
                "parts": [{"functionResponse": {"name": "lookup", "response": {}}}],
            },
            text_content("model", "tool response " + "y" * 200),
            text_content("user", "latest request " + "z" * 120),
            text_content("model", "latest response " + "q" * 120),
        ]
        payload = {"contents": contents}
        settings = CompressionSettings(
            enabled=True,
            threshold_tokens=180,
            target_tokens=120,
            min_recent_turns=1,
        )

        result = compress_gemini_request(payload, settings)

        first_part = result.request["contents"][0]["parts"][0]
        self.assertNotIn("functionResponse", first_part)
        self.assertEqual(result.request["contents"], contents[-2:])

    def test_compression_skips_an_unmatched_tool_result_history(self):
        payload = {
            "contents": [
                text_content("user", "old request " + "x" * 300),
                {
                    "role": "user",
                    "parts": [{"functionResponse": {"name": "lookup", "response": {"value": 1}}}],
                },
                text_content("model", "old answer " + "y" * 300),
                text_content("user", "new request " + "z" * 300),
                text_content("model", "new answer " + "q" * 300),
            ]
        }

        result = compress_gemini_request(
            payload,
            CompressionSettings(
                enabled=True,
                threshold_tokens=180,
                target_tokens=120,
                min_recent_turns=1,
            ),
        )

        self.assertFalse(result.applied)
        self.assertEqual(result.reason, "invalid_tool_history")
        self.assertIs(result.request, payload)

    def test_compression_skips_malformed_history_instead_of_guessing(self):
        payload = {
            "contents": [
                text_content("user", "old request " + "x" * 300),
                {"role": "model", "parts": "not-a-list"},
                text_content("user", "new request " + "z" * 300),
                text_content("model", "new answer " + "q" * 300),
            ]
        }

        result = compress_gemini_request(
            payload,
            CompressionSettings(
                enabled=True,
                threshold_tokens=180,
                target_tokens=120,
                min_recent_turns=1,
            ),
        )

        self.assertFalse(result.applied)
        self.assertEqual(result.reason, "invalid_history")
        self.assertIs(result.request, payload)

    def test_estimator_accounts_for_structured_payload_overhead(self):
        plain = {"contents": [text_content("user", "a" * 40)]}
        structured = {
            **plain,
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": "read_file",
                            "description": "Read a file from the workspace.",
                            "parameters": {"type": "object", "properties": {}},
                        }
                    ]
                }
            ],
        }

        self.assertGreater(estimate_input_tokens(structured), estimate_input_tokens(plain))

    def test_estimator_handles_deep_json_without_recursion_failure(self):
        nested: dict[str, object] = {"text": "leaf"}
        for _ in range(2_000):
            nested = {"nested": nested}

        self.assertGreater(estimate_input_tokens(nested), 2_000)

    def test_estimation_failure_preserves_the_original_request(self):
        payload: dict[str, object] = {"contents": []}
        payload["cycle"] = payload

        result = compress_gemini_request(
            payload,
            CompressionSettings(
                enabled=True,
                threshold_tokens=128,
                target_tokens=64,
                min_recent_turns=1,
            ),
        )

        self.assertFalse(result.applied)
        self.assertIs(result.request, payload)
        self.assertEqual(result.reason, "estimation_failed")
        self.assertEqual(result.original_estimated_tokens, 0)
        self.assertEqual(result.final_estimated_tokens, 0)

    def test_candidate_estimation_failure_falls_back_to_uncompressed_history(self):
        contents = [
            text_content("user", "old request " + "x" * 300),
            text_content("model", "old answer " + "y" * 300),
            text_content("user", "current request " + "z" * 300),
        ]
        payload = {
            "systemInstruction": {"parts": [{"text": "Never remove this."}]},
            "contents": contents,
            "tools": [{"functionDeclarations": [{"name": "lookup"}]}],
        }

        with patch(
            "core.token_compression.estimate_input_tokens",
            side_effect=[1_000, RuntimeError("synthetic estimator failure")],
        ):
            result = compress_gemini_request(
                payload,
                CompressionSettings(
                    enabled=True,
                    threshold_tokens=128,
                    target_tokens=64,
                    min_recent_turns=1,
                ),
            )

        self.assertFalse(result.applied)
        self.assertIs(result.request, payload)
        self.assertEqual(result.reason, "estimation_failed")
        self.assertEqual(result.original_estimated_tokens, 1_000)
        self.assertEqual(result.final_estimated_tokens, 1_000)

    def test_failed_post_compression_invariant_returns_the_original_request(self):
        payload = {
            "systemInstruction": {"parts": [{"text": "Never remove this."}]},
            "contents": [
                text_content("user", "old request " + "x" * 300),
                text_content("model", "old answer " + "y" * 300),
                text_content("user", "current request " + "z" * 300),
            ],
        }

        with patch("core.token_compression.copy.deepcopy", return_value={"contents": []}):
            result = compress_gemini_request(
                payload,
                CompressionSettings(
                    enabled=True,
                    threshold_tokens=128,
                    target_tokens=64,
                    min_recent_turns=1,
                ),
            )

        self.assertFalse(result.applied)
        self.assertIs(result.request, payload)
        self.assertEqual(result.reason, "invariant_failed")
        self.assertEqual(result.original_estimated_tokens, result.final_estimated_tokens)


if __name__ == "__main__":
    unittest.main()
