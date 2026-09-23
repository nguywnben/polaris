"""Regression tests for OpenAI tool history translated to Gemini turns."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.api.primary import _normalize_antigravity_tool_turns
from core.converter.openai_to_gemini import convert_openai_to_gemini_request


class OpenAIToGeminiToolTurnTests(unittest.IsolatedAsyncioTestCase):
    async def test_consecutive_assistant_turns_merge_before_function_call(self):
        translated = await convert_openai_to_gemini_request(
            {
                "model": "gemini-3.8-flash-tiered",
                "messages": [
                    {"role": "user", "content": "Inspect the repo."},
                    {"role": "assistant", "content": "I will inspect it."},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": '{"path":"README.md"}',
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call_1",
                        "content": '{"ok":true}',
                    },
                ],
            }
        )

        self.assertEqual([content["role"] for content in translated["contents"]], ["user", "model", "user"])
        model_parts = translated["contents"][1]["parts"]
        self.assertEqual(model_parts[0], {"text": "I will inspect it."})
        self.assertEqual(model_parts[1]["functionCall"]["name"], "read_file")
        self.assertEqual(translated["contents"][2]["parts"][0]["functionResponse"]["name"], "read_file")

    def test_antigravity_drops_narration_before_function_call(self):
        normalized = _normalize_antigravity_tool_turns(
            {
                "contents": [
                    {"role": "user", "parts": [{"text": "Inspect the repo."}]},
                    {
                        "role": "model",
                        "parts": [
                            {"text": "I will inspect it."},
                            {"functionCall": {"name": "read_file", "args": {}}},
                        ],
                    },
                ]
            }
        )

        self.assertEqual(
            normalized["contents"][1]["parts"],
            [{"functionCall": {"name": "read_file", "args": {}}}],
        )

    def test_antigravity_prepends_user_before_model_first_function_call(self):
        normalized = _normalize_antigravity_tool_turns(
            {
                "contents": [
                    {
                        "role": "model",
                        "parts": [{"functionCall": {"name": "read_file", "args": {}}}],
                    },
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": "read_file",
                                    "response": {"result": "ok"},
                                }
                            }
                        ],
                    },
                ]
            },
            "gemini-3.8-flash-tiered",
        )

        self.assertEqual(
            [content["role"] for content in normalized["contents"]],
            ["user", "model", "user"],
        )
        self.assertEqual(normalized["contents"][0]["parts"], [{"text": ""}])

    def test_antigravity_canonicalizes_function_response_role(self):
        normalized = _normalize_antigravity_tool_turns(
            {
                "contents": [
                    {
                        "role": "model",
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "read_file",
                                    "args": {},
                                }
                            }
                        ],
                    },
                    {
                        "role": "model",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": "read_file",
                                    "response": {"result": "ok"},
                                }
                            }
                        ],
                    },
                ]
            },
            "gemini-3.8-flash-tiered",
        )

        self.assertEqual(
            [content["role"] for content in normalized["contents"]],
            ["user", "model", "user"],
        )


if __name__ == "__main__":
    unittest.main()
