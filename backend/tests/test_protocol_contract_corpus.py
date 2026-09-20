"""Golden contract coverage shared by every advertised inference protocol."""

from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main
from core.models import (
    ClaudeRequest,
    GeminiRequest,
    OpenAIChatCompletionRequest,
    OpenAIChatCompletionResponse,
    OpenAIResponsesRequest,
    model_to_dict,
)
from core.protocol_contract import ProtocolTranslationError, list_protocol_conversions
from core.provider_registry import INFERENCE_PROTOCOLS
from core.router.primary.responses import responses_to_chat_request
from core.router.protocol_errors import protocol_error_payload

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "protocol-contract-corpus-v1.json"
REQUEST_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "protocol-request-golden-v1.json"
RESPONSE_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "protocol-response-golden-v1.json"
REASONING_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "protocol-reasoning-extension-v1.json"


class ProtocolContractMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_corpus_covers_every_advertised_family_and_feature(self):
        self.assertEqual(self.fixture["schema_version"], 1)
        self.assertEqual(set(self.fixture["advertised_families"]), set(INFERENCE_PROTOCOLS))

        vocabulary = set(self.fixture["feature_vocabulary"])
        covered_families = set()
        for conversion in self.fixture["conversions"].values():
            covered_families.add(conversion["family"])
            self.assertEqual(set(conversion["features"]), vocabulary)
            self.assertTrue(
                set(conversion["features"].values()) <= {"supported", "translated", "rejected"}
            )
        self.assertEqual(covered_families, set(INFERENCE_PROTOCOLS))

    def test_runtime_contract_matches_the_versioned_corpus(self):
        expected = deepcopy(self.fixture["conversions"])
        extension = json.loads(REASONING_FIXTURE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(extension["schema_version"], 1)
        for conversion, features in extension["feature_overrides"].items():
            expected[conversion]["features"].update(features)
        self.assertEqual(list_protocol_conversions(), expected)

    def test_reasoning_extension_preserves_the_golden_native_control(self):
        from core.reasoning_control import REASONING_EFFORT_KEY, prepare_reasoning_request

        extension = json.loads(REASONING_FIXTURE_PATH.read_text(encoding="utf-8"))
        request = OpenAIChatCompletionRequest.model_validate(extension["request"])
        result, _ = prepare_reasoning_request(
            {REASONING_EFFORT_KEY: request.reasoning_effort},
            request.model,
            "google_antigravity",
            "",
        )
        self.assertEqual(result["generationConfig"]["thinkingConfig"], extension["thinking_config"])

    def test_unknown_top_level_fields_fail_closed_for_every_request_family(self):
        cases = (
            (
                OpenAIChatCompletionRequest,
                {
                    "model": "fixture-model",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "silent_semantic_change": True,
                },
            ),
            (
                OpenAIResponsesRequest,
                {
                    "model": "fixture-model",
                    "input": "Hello",
                    "silent_semantic_change": True,
                },
            ),
            (
                ClaudeRequest,
                {
                    "model": "fixture-model",
                    "max_tokens": 32,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "silent_semantic_change": True,
                },
            ),
            (
                GeminiRequest,
                {
                    "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
                    "silentSemanticChange": True,
                },
            ),
        )

        for model, payload in cases:
            with self.subTest(model=model.__name__), self.assertRaises(ValidationError):
                model.model_validate(payload)

    def test_unknown_nested_gemini_config_field_fails_closed(self):
        with self.assertRaises(ValidationError):
            GeminiRequest.model_validate(
                {
                    "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
                    "generationConfig": {"silentSemanticChange": True},
                }
            )

    def test_reasoning_content_is_output_only_for_chat_completions(self):
        with self.assertRaises(ValidationError):
            OpenAIChatCompletionRequest.model_validate(
                {
                    "model": "fixture-model",
                    "messages": [
                        {
                            "role": "assistant",
                            "content": "Previous answer",
                            "reasoning_content": "private reasoning",
                        }
                    ],
                }
            )

        response = OpenAIChatCompletionResponse.model_validate(
            {
                "id": "chatcmpl-fixture",
                "created": 1,
                "model": "fixture-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Answer",
                            "reasoning_content": "preserved reasoning",
                        },
                        "finish_reason": "stop",
                    }
                ],
            }
        )
        self.assertEqual(
            response.choices[0].message.reasoning_content,
            "preserved reasoning",
        )


class ProtocolContractBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_unknown_fields_return_native_http_400_for_every_public_family(self):
        cases = (
            (
                "/v1/chat/completions",
                {"Authorization": "Bearer sk-polaris-test-key"},
                {
                    "model": "fixture-model",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "silent_semantic_change": True,
                },
                "invalid_request_error",
            ),
            (
                "/v1/responses",
                {"Authorization": "Bearer sk-polaris-test-key"},
                {
                    "model": "fixture-model",
                    "input": "Hello",
                    "silent_semantic_change": True,
                },
                "invalid_request_error",
            ),
            (
                "/v1/messages",
                {"x-api-key": "sk-polaris-test-key"},
                {
                    "model": "fixture-model",
                    "max_tokens": 32,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "silent_semantic_change": True,
                },
                "invalid_request_error",
            ),
            (
                "/v1beta/models/fixture-model:generateContent",
                {"x-goog-api-key": "sk-polaris-test-key"},
                {
                    "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
                    "silentSemanticChange": True,
                },
                "INVALID_ARGUMENT",
            ),
            (
                "/vertex/v1beta/models/fixture-model:generateContent",
                {"x-goog-api-key": "sk-polaris-test-key"},
                {
                    "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
                    "silentSemanticChange": True,
                },
                "INVALID_ARGUMENT",
            ),
        )

        with patch("config.get_api_key", new=AsyncMock(return_value="sk-polaris-test-key")):
            for path, headers, body, expected_error in cases:
                with self.subTest(path=path):
                    response = await self.client.post(path, headers=headers, json=body)
                    payload = response.json()["error"]

                    self.assertEqual(response.status_code, 400)
                    self.assertIn(expected_error, payload.values())
                    self.assertIn("silent", payload["message"].lower())

    async def test_translation_failures_use_the_endpoint_native_502_envelope(self):
        from starlette.requests import Request

        cases = (
            ("/v1/chat/completions", "server_error"),
            ("/v1/messages", "overloaded_error"),
            ("/v1beta/models/fixture:generateContent", "UNAVAILABLE"),
        )
        for path, expected in cases:
            with self.subTest(path=path):
                request = Request(
                    {
                        "type": "http",
                        "method": "POST",
                        "path": path,
                        "headers": [],
                        "query_string": b"",
                        "scheme": "http",
                        "server": ("test", 80),
                    }
                )
                response = await main.handle_protocol_translation_exception(
                    request, ProtocolTranslationError("Unsupported upstream response part.")
                )
                self.assertEqual(response.status_code, 502)
                self.assertIn(expected, response.body.decode())


class ProtocolRequestGoldenTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(REQUEST_FIXTURE_PATH.read_text(encoding="utf-8"))

    async def test_openai_chat_and_vertex_openai_translate_the_golden_request(self):
        from core.converter.openai_to_gemini import convert_openai_to_gemini_request

        case = self.fixture["openai_chat"]
        request = OpenAIChatCompletionRequest.model_validate(case["request"])
        with patch("config.get_compatibility_mode_enabled", new=AsyncMock(return_value=False)):
            translated = await convert_openai_to_gemini_request(model_to_dict(request))

        expected = case["expected"]
        self.assertEqual(
            translated["systemInstruction"]["parts"][0]["text"], expected["system_text"]
        )
        self.assertEqual(translated["contents"][0]["parts"][0]["text"], expected["user_text"])
        inline_data = translated["contents"][0]["parts"][1]["inlineData"]
        self.assertEqual(inline_data["mimeType"], expected["image_mime_type"])
        self.assertEqual(inline_data["data"], expected["image_data"])
        self.assertEqual(
            translated["generationConfig"]["maxOutputTokens"], expected["max_output_tokens"]
        )
        self.assertEqual(
            translated["generationConfig"]["responseMimeType"],
            expected["response_mime_type"],
        )
        self.assertEqual(
            translated["tools"][0]["functionDeclarations"][0]["name"],
            expected["tool_name"],
        )

    def test_openai_responses_translates_the_golden_request_without_loss(self):
        case = self.fixture["openai_responses"]
        request = OpenAIResponsesRequest.model_validate(case["request"])
        translated = model_to_dict(responses_to_chat_request(request))
        expected = case["expected"]

        self.assertEqual(
            [item["role"] for item in translated["messages"]], expected["message_roles"]
        )
        self.assertEqual(translated["tools"][0]["function"]["name"], expected["tool_name"])
        self.assertEqual(translated["response_format"]["type"], expected["response_format_type"])
        self.assertEqual(
            translated["response_format"]["json_schema"]["name"],
            expected["response_format_name"],
        )

    async def test_anthropic_translates_the_golden_request_without_loss(self):
        from core.converter.anthropic_to_gemini import anthropic_to_gemini_request

        case = self.fixture["anthropic"]
        request = ClaudeRequest.model_validate(case["request"])
        with patch("config.get_compatibility_mode_enabled", new=AsyncMock(return_value=False)):
            translated = await anthropic_to_gemini_request(model_to_dict(request))

        expected = case["expected"]
        self.assertEqual(
            translated["systemInstruction"]["parts"][0]["text"], expected["system_text"]
        )
        thinking_part = next(
            part
            for content in translated["contents"]
            for part in content["parts"]
            if part.get("thought") is True
        )
        self.assertEqual(thinking_part["text"], expected["thinking_text"])
        self.assertEqual(thinking_part["thoughtSignature"], expected["thinking_signature"])
        self.assertEqual(
            translated["generationConfig"]["thinkingConfig"]["thinkingBudget"],
            expected["thinking_budget"],
        )
        self.assertEqual(
            translated["generationConfig"]["responseMimeType"],
            expected["response_mime_type"],
        )
        self.assertEqual(
            translated["tools"][0]["functionDeclarations"][0]["name"],
            expected["tool_name"],
        )

    def test_gemini_and_vertex_gemini_preserve_the_native_golden_request(self):
        from core.anthropic import gemini_request_to_anthropic

        request = self.fixture["gemini"]["request"]
        self.assertEqual(model_to_dict(GeminiRequest.model_validate(request)), request)
        translated = gemini_request_to_anthropic(request, "fixture-model", False)
        self.assertEqual(
            translated["output_config"]["format"],
            {
                "type": "json_schema",
                "schema": request["generationConfig"]["responseSchema"],
            },
        )

    def test_unsupported_or_unknown_semantics_fail_closed(self):
        cases = (
            (
                OpenAIChatCompletionRequest,
                {
                    "model": "fixture-model",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "reasoning_effort": "unknown",
                },
            ),
            (
                OpenAIChatCompletionRequest,
                {
                    "model": "fixture-model",
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"type": "unknown_part", "value": "lost"}],
                        }
                    ],
                },
            ),
            (
                OpenAIChatCompletionRequest,
                {
                    "model": "fixture-model",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": "https://example.invalid/image.png"},
                                }
                            ],
                        }
                    ],
                },
            ),
            (
                OpenAIChatCompletionRequest,
                {
                    "model": "fixture-model",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "response_format": {"type": "future_format"},
                },
            ),
            (
                OpenAIResponsesRequest,
                {"model": "fixture-model", "input": "Hello", "reasoning": {"effort": "high"}},
            ),
            (
                OpenAIResponsesRequest,
                {
                    "model": "fixture-model",
                    "input": [{"type": "unknown_item", "value": "lost"}],
                },
            ),
            (
                OpenAIResponsesRequest,
                {
                    "model": "fixture-model",
                    "input": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": "Hello",
                            "future_semantic": "lost",
                        }
                    ],
                },
            ),
            (
                ClaudeRequest,
                {
                    "model": "fixture-model",
                    "max_tokens": 32,
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"type": "unknown_block", "value": "lost"}],
                        }
                    ],
                },
            ),
            (
                ClaudeRequest,
                {
                    "model": "fixture-model",
                    "max_tokens": 32,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "output_config": {
                        "format": {"type": "json_schema", "schema": {}},
                        "future_semantic": "lost",
                    },
                },
            ),
        )

        for model, payload in cases:
            with self.subTest(model=model.__name__), self.assertRaises(ValidationError):
                model.model_validate(payload)


class ProtocolResponseGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(RESPONSE_FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_gemini_response_translates_to_openai_chat_without_usage_loss(self):
        from core.converter.openai_to_gemini import convert_gemini_to_openai_response

        translated = convert_gemini_to_openai_response(
            self.fixture["gemini_response"], "fixture-model"
        )
        expected = self.fixture["expected_openai_chat"]
        choice = translated["choices"][0]
        usage = translated["usage"]

        self.assertEqual(choice["message"]["reasoning_content"], expected["reasoning_content"])
        self.assertEqual(choice["message"]["content"], expected["content"])
        self.assertEqual(
            choice["message"]["tool_calls"][0]["function"]["name"], expected["tool_name"]
        )
        self.assertEqual(choice["finish_reason"], expected["finish_reason"])
        self.assertEqual(usage["prompt_tokens"], expected["prompt_tokens"])
        self.assertEqual(usage["prompt_tokens_details"]["cached_tokens"], expected["cached_tokens"])
        self.assertEqual(usage["completion_tokens"], expected["completion_tokens"])
        self.assertEqual(
            usage["completion_tokens_details"]["reasoning_tokens"],
            expected["reasoning_tokens"],
        )
        self.assertEqual(usage["total_tokens"], expected["total_tokens"])

    def test_openai_chat_response_translates_to_responses_with_reasoning(self):
        from core.converter.openai_to_gemini import convert_gemini_to_openai_response
        from core.router.primary.responses import chat_to_responses_response

        chat = convert_gemini_to_openai_response(self.fixture["gemini_response"], "fixture-model")
        request = OpenAIResponsesRequest(model="fixture-model", input="Hello")
        translated = chat_to_responses_response(chat, request)
        expected = self.fixture["expected_openai_responses"]

        self.assertEqual([item["type"] for item in translated["output"]], expected["output_types"])
        self.assertEqual(translated["output"][0]["summary"][0]["text"], expected["reasoning_text"])
        self.assertEqual(translated["output"][1]["content"][0]["text"], expected["output_text"])
        self.assertEqual(translated["usage"]["input_tokens"], expected["input_tokens"])
        self.assertEqual(translated["usage"]["output_tokens"], expected["output_tokens"])
        self.assertEqual(translated["usage"]["total_tokens"], expected["total_tokens"])

    def test_gemini_response_translates_to_official_anthropic_shape(self):
        from core.converter.anthropic_to_gemini import gemini_to_anthropic_response

        translated = gemini_to_anthropic_response(self.fixture["gemini_response"], "fixture-model")
        expected = self.fixture["expected_anthropic"]
        thinking, text_block, tool = translated["content"]

        self.assertEqual(thinking["thinking"], expected["thinking"])
        self.assertEqual(thinking["signature"], expected["signature"])
        self.assertNotIn("thoughtSignature", thinking)
        self.assertEqual(text_block["text"], expected["text"])
        self.assertEqual(tool["name"], expected["tool_name"])
        self.assertEqual(translated["stop_reason"], expected["stop_reason"])
        self.assertEqual(translated["usage"]["input_tokens"], expected["input_tokens"])
        self.assertEqual(
            translated["usage"]["cache_read_input_tokens"], expected["cache_read_input_tokens"]
        )
        self.assertEqual(translated["usage"]["output_tokens"], expected["output_tokens"])

    def test_normalized_error_envelopes_match_the_golden_corpus(self):
        for case in self.fixture["errors"]:
            with self.subTest(protocol=case["protocol"], status=case["status_code"]):
                self.assertEqual(
                    protocol_error_payload(
                        case["protocol"], case["status_code"], "Invalid fixture input."
                    ),
                    case["expected"],
                )

    def test_finish_reasons_translate_without_claiming_normal_completion(self):
        from core.converter.anthropic_to_gemini import gemini_to_anthropic_response
        from core.converter.openai_to_gemini import convert_gemini_to_openai_response
        from core.router.primary.responses import chat_to_responses_response

        request = OpenAIResponsesRequest(model="fixture-model", input="Hello")
        for case in self.fixture["finish_reasons"]:
            with self.subTest(reason=case["gemini"]):
                payload = {
                    "candidates": [
                        {
                            "content": {"role": "model", "parts": [{"text": "Done"}]},
                            "finishReason": case["gemini"],
                        }
                    ]
                }
                chat = convert_gemini_to_openai_response(payload, "fixture-model")
                anthropic = gemini_to_anthropic_response(payload, "fixture-model")
                responses = chat_to_responses_response(chat, request)

                self.assertEqual(chat["choices"][0]["finish_reason"], case["openai"])
                self.assertEqual(anthropic["stop_reason"], case["anthropic"])
                if case["openai"] == "length":
                    self.assertEqual(responses["status"], "incomplete")
                    self.assertEqual(responses["incomplete_details"]["reason"], "max_output_tokens")
                elif case["openai"] == "content_filter":
                    self.assertEqual(responses["status"], "incomplete")
                    self.assertEqual(responses["incomplete_details"]["reason"], "content_filter")
                else:
                    self.assertEqual(responses["status"], "completed")
                    self.assertIsNone(responses["incomplete_details"])

    def test_unknown_response_parts_fail_instead_of_disappearing(self):
        from core.converter.anthropic_to_gemini import gemini_to_anthropic_response
        from core.converter.openai_to_gemini import convert_gemini_to_openai_response

        payload = {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"futurePart": {"value": 1}}]},
                    "finishReason": "STOP",
                }
            ]
        }
        for converter in (
            lambda: convert_gemini_to_openai_response(payload, "fixture-model"),
            lambda: gemini_to_anthropic_response(payload, "fixture-model"),
        ):
            with self.subTest(converter=converter), self.assertRaises(ValueError):
                converter()

    def test_openai_usage_round_trips_through_provider_canonical_responses(self):
        from core.codex import codex_response_to_gemini
        from core.converter.openai_to_gemini import convert_gemini_to_openai_response
        from core.xai import xai_response_to_gemini

        usage = {
            "prompt_tokens": 12,
            "completion_tokens": 7,
            "total_tokens": 19,
            "prompt_tokens_details": {"cached_tokens": 3},
            "completion_tokens_details": {"reasoning_tokens": 2},
        }
        responses_usage = {
            "input_tokens": 12,
            "output_tokens": 7,
            "total_tokens": 19,
            "input_tokens_details": {"cached_tokens": 3},
            "output_tokens_details": {"reasoning_tokens": 2},
        }
        canonical_responses = (
            xai_response_to_gemini(
                {
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"content": "Done"},
                        }
                    ],
                    "usage": usage,
                }
            ),
            codex_response_to_gemini(
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "Done"}],
                        }
                    ],
                    "usage": responses_usage,
                }
            ),
        )

        for canonical in canonical_responses:
            with self.subTest(canonical=canonical):
                translated = convert_gemini_to_openai_response(canonical, "fixture-model")
                self.assertEqual(translated["usage"], usage)


if __name__ == "__main__":
    unittest.main()
