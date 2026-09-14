from __future__ import annotations

import copy
import json
import random
import sys
import unittest
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.token_compression import CompressionSettings, compress_gemini_request

CORPUS_PATH = Path(__file__).parent / "fixtures" / "ai-quality-compression-corpus-v1.json"


def _text(role: str, value: str) -> dict:
    return {"role": role, "parts": [{"text": value}]}


def _tool_names(contents: list[dict], field: str) -> Counter:
    names: Counter = Counter()
    for content in contents:
        for part in content.get("parts", []):
            value = part.get(field)
            if isinstance(value, dict) and isinstance(value.get("name"), str):
                names[value["name"]] += 1
    return names


class AIQualityCompressionCorpusTests(unittest.TestCase):
    def test_fixed_adversarial_corpus_preserves_quality_invariants(self):
        corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(corpus["version"], 1)

        for case in corpus["cases"]:
            with self.subTest(case=case["name"]):
                request = case["request"]
                original = copy.deepcopy(request)
                result = compress_gemini_request(request, CompressionSettings(**case["settings"]))

                self.assertEqual(request, original, "compression mutated its input")
                self.assertEqual(result.applied, case["expected"]["applied"])
                if expected_reason := case["expected"].get("reason"):
                    self.assertEqual(result.reason, expected_reason)
                self.assertIsInstance(result.original_estimated_tokens, int)
                self.assertIsInstance(result.final_estimated_tokens, int)
                self.assertGreaterEqual(result.original_estimated_tokens, 0)
                self.assertGreaterEqual(result.final_estimated_tokens, 0)
                self.assertLessEqual(
                    result.final_estimated_tokens, result.original_estimated_tokens
                )
                self.assertTrue(result.reason)

                serialized = json.dumps(result.request["contents"], ensure_ascii=False)
                self.assertIn(case["expected"]["current_request"], serialized)
                for field in case["expected"]["protected_fields"]:
                    self.assertEqual(result.request[field], original[field])

                if result.applied:
                    self.assertIsNot(result.request, request)
                    self.assertIn(
                        result.request["contents"],
                        [
                            original["contents"][index:]
                            for index in range(len(original["contents"]))
                        ],
                    )
                    retained = result.request["contents"]
                    self.assertEqual(
                        _tool_names(retained, "functionCall"),
                        _tool_names(retained, "functionResponse"),
                    )

    def test_property_matrix_never_rewrites_protected_fields_or_current_request(self):
        rng = random.Random(2_006)
        for sample in range(96):
            user_turns = rng.randint(2, 12)
            min_recent = rng.randint(1, min(4, user_turns - 1))
            contents = []
            for turn in range(user_turns):
                contents.extend(
                    (
                        _text("user", f"user-{sample}-{turn}-" + "u" * rng.randint(40, 240)),
                        _text("model", f"model-{sample}-{turn}-" + "m" * rng.randint(40, 240)),
                    )
                )
            marker = f"CURRENT-{sample}"
            contents.append(_text("user", marker + " z" * 80))
            request = {
                "systemInstruction": {"parts": [{"text": f"system-{sample}"}]},
                "tools": [{"functionDeclarations": [{"name": f"tool_{sample}"}]}],
                "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
                "generationConfig": {"temperature": rng.random()},
                "contents": contents,
            }
            original = copy.deepcopy(request)

            result = compress_gemini_request(
                request,
                CompressionSettings(
                    enabled=True,
                    threshold_tokens=128,
                    target_tokens=64,
                    min_recent_turns=min_recent,
                ),
            )

            self.assertEqual(request, original)
            self.assertIn(marker, json.dumps(result.request["contents"]))
            self.assertEqual(result.request["systemInstruction"], original["systemInstruction"])
            self.assertEqual(result.request["tools"], original["tools"])
            self.assertEqual(result.request["toolConfig"], original["toolConfig"])
            self.assertEqual(result.request["generationConfig"], original["generationConfig"])
            self.assertGreaterEqual(result.original_estimated_tokens, result.final_estimated_tokens)
            self.assertEqual(
                result.estimated_tokens_saved,
                result.original_estimated_tokens - result.final_estimated_tokens,
            )


if __name__ == "__main__":
    unittest.main()
