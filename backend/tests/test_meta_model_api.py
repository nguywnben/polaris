"""Meta Model API transport contract, using isolated upstream HTTP fixtures."""

from __future__ import annotations

import copy
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core import meta_model_api as meta
from core.meta_native_boundary import seal_native_request


def credential(**extra):
    return {"api_key": "fixture-meta-api-key", **extra}


def request_body():
    return {"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]}


class MetaCredentialTests(unittest.TestCase):
    def test_defaults_do_not_choose_a_model_or_change_source(self):
        source = credential()
        normalized = meta.normalize_credential(source)
        self.assertEqual(normalized["provider"], "meta")
        self.assertEqual(normalized["credential_type"], "api_key")
        self.assertEqual(normalized["base_url"], "https://api.meta.ai/v1")
        self.assertEqual(normalized["model_ids"], [])
        self.assertEqual(source, credential())

    def test_credential_keys_reject_control_characters_and_wrong_types(self):
        for key in (None, "", " ", "secret\r\nheader", "secret\x00", 123, "a" * 8193):
            with self.subTest(key_type=type(key)), self.assertRaises(meta.MetaModelAPIError):
                meta.normalize_credential(credential(api_key=key))

    def test_origin_path_and_protocol_are_fixed(self):
        for base in (
            "http://api.meta.ai/v1",
            "https://evil.example/v1",
            "https://api.meta.ai/v2",
            "https://api.meta.ai/v1?key=x",
            "https://user@api.meta.ai/v1",
            "https://api.meta.ai:444/v1",
            "https://api.meta.ai/v1#fragment",
            "https://api.meta.ai/../v1",
            "https://api.meta.ai/v1/responses",
            5,
        ):
            with self.subTest(base=base), self.assertRaises(meta.MetaModelAPIError):
                meta.normalize_credential(credential(base_url=base))

    def test_explicit_contributor_is_preserved_without_substitution(self):
        normalized = meta.normalize_credential(
            credential(
                model_ids=[
                    "muse-spark-1.3",
                    "muse-spark-1.3-contributor",
                    "muse-spark-1.3",
                ]
            )
        )
        self.assertEqual(normalized["model_ids"], ["muse-spark-1.3", "muse-spark-1.3-contributor"])
        self.assertEqual(meta.protocol_for_model(normalized, "muse-spark-1.3"), "responses")

    def test_non_coding_models_and_malformed_identifiers_are_rejected(self):
        for model in (
            "muse-image-1",
            "muse-audio-1",
            "gpt-5",
            "muse-spark-../../x",
            "muse-spark-",
            None,
        ):
            with self.subTest(model=model), self.assertRaises(meta.MetaModelAPIError):
                meta.normalize_credential(credential(model_ids=[model]))


class MetaCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def discover(self, response):
        requests = []

        def handler(request):
            requests.append(request)
            return response

        @asynccontextmanager
        async def client(**kwargs):
            self.assertFalse(kwargs["follow_redirects"])
            self.assertEqual(kwargs["destination_url"], "https://api.meta.ai/v1/models")
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
                yield session

        with patch.object(meta.http_client, "get_client", client):
            result = await meta.discover_models(credential())
        return result, requests

    async def test_authenticated_catalog_filters_image_audio_and_deduplicates(self):
        result, requests = await self.discover(
            httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "muse-spark-1.3"},
                        {"id": "muse-image-1"},
                        {"id": "muse-audio-1"},
                        {"id": "muse-spark-1.3-contributor"},
                        {"id": "muse-spark-1.3"},
                    ]
                },
            )
        )
        self.assertEqual(result, ["muse-spark-1.3", "muse-spark-1.3-contributor"])
        self.assertEqual(requests[0].headers["authorization"], "Bearer fixture-meta-api-key")

    async def test_remote_failure_is_sanitized_and_redirect_not_followed(self):
        for status in (302, 401, 403, 429, 500):
            with self.subTest(status=status), self.assertRaises(meta.MetaModelAPIError) as raised:
                await self.discover(httpx.Response(status, text="fixture-meta-api-key"))
            self.assertNotIn("fixture-meta-api-key", str(raised.exception))
            self.assertEqual(raised.exception.status_code, status if status >= 400 else 502)

    async def test_catalog_limits_and_malformed_payload_fail_closed(self):
        for response in (
            httpx.Response(200, text="not-json"),
            httpx.Response(200, json={"data": []}),
            httpx.Response(200, json={"data": [{"id": "../../x"}]}),
            httpx.Response(200, json={"data": [{"id": "muse-image-1"}]}),
            httpx.Response(200, content=b"x" * (meta.MAX_CATALOG_BYTES + 1)),
            httpx.Response(
                200, json={"data": [{"id": "muse-spark-1.3"}] * (meta.MAX_DECLARED_MODELS + 1)}
            ),
        ):
            with self.subTest(), self.assertRaises(meta.MetaModelAPIError):
                await self.discover(response)


class MetaToolOptionTests(unittest.TestCase):
    def test_forced_function_selection_keeps_declared_tool(self):
        source = {
            **request_body(),
            "tools": [
                {"functionDeclarations": [{"name": "read", "parameters": {"type": "object"}}]}
            ],
            "toolConfig": {
                "functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": ["read"]}
            },
        }
        body = meta.prepare_request(credential(), source, "muse-spark-1.3", False)[2]
        self.assertEqual(body["tool_choice"], {"type": "function", "name": "read"})
        self.assertEqual(body["tools"][0]["parameters"], {"type": "object"})

    def test_unimplemented_tool_options_are_not_silently_dropped(self):
        for extra in ({"disableParallelFunctionCalling": True}, {"allowedFunctionNames": ["read"]}):
            source = {
                **request_body(),
                "tools": [{"functionDeclarations": [{"name": "read"}]}],
                "toolConfig": {"functionCallingConfig": {"mode": "AUTO", **extra}},
            }
            with self.subTest(extra=extra), self.assertRaises(meta.MetaModelAPIError):
                meta.prepare_request(credential(), source, "muse-spark-1.3", False)


class MetaAnthropicCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_messages_converter_basic_text_and_tool_history(self):
        payload = {
            "model": "muse-spark-1.3",
            "max_tokens": 128,
            "messages": [
                {"role": "user", "content": "Read the file"},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Checking"},
                        {
                            "type": "tool_use",
                            "id": "tool_read",
                            "name": "read",
                            "input": {"path": "x"},
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "tool_read", "content": "done"}
                    ],
                },
            ],
            "tools": [
                {
                    "name": "read",
                    "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
                }
            ],
        }
        with patch("config.get_compatibility_mode_enabled", AsyncMock(return_value=False)):
            canonical = await meta.anthropic_request_to_meta_canonical(payload)
        body = meta.prepare_request(credential(), canonical, "muse-spark-1.3", False)[2]
        self.assertEqual(body["max_output_tokens"], 128)
        self.assertEqual(
            [item["call_id"] for item in body["input"] if "call_id" in item],
            ["tool_read", "tool_read"],
        )
        self.assertNotIn("stop", body)

    async def test_explicit_unsupported_stops_and_thinking_are_not_hidden(self):
        for extra in (
            {"stop_sequences": ["stop"]},
            {"top_k": 4},
            {"thinking": {"type": "enabled", "budget_tokens": 100}},
        ):
            payload = {
                "model": "muse-spark-1.3",
                "max_tokens": 128,
                "messages": [{"role": "user", "content": "Hello"}],
                **extra,
            }
            with patch("config.get_compatibility_mode_enabled", AsyncMock(return_value=False)):
                with self.subTest(extra=extra), self.assertRaises(meta.MetaModelAPIError):
                    canonical = await meta.anthropic_request_to_meta_canonical(payload)
                    meta.prepare_request(credential(), canonical, "muse-spark-1.3", False)


class MetaRequestTests(unittest.TestCase):
    def test_unsealed_native_replay_is_rejected_at_transport(self):
        with self.assertRaises(ValueError):
            meta.prepare_request(
                credential(),
                {"_polaris_meta_responses": {"input": "hidden"}},
                "muse-spark-1.3",
                False,
            )

    def test_native_replay_preserves_reasoning_phase_and_requested_include(self):
        native = {
            "model": "muse-spark-1.3",
            "stream": False,
            "store": False,
            "input": [
                {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "opaque"},
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": "Checking"}],
                },
            ],
            "include": ["reasoning.encrypted_content"],
            "metadata": {"project": "fixture"},
        }
        source = seal_native_request(request_body(), native)
        before = copy.deepcopy(source)
        body = meta.prepare_request(credential(), source, "muse-spark-1.3", True)[2]
        self.assertEqual(body["input"], native["input"])
        self.assertEqual(body["metadata"], native["metadata"])
        self.assertEqual(body["include"], native["include"])
        self.assertIs(body["stream"], True)
        self.assertEqual(source, before)

    def test_no_encrypted_reasoning_is_requested_implicitly(self):
        for source in (request_body(), seal_native_request(request_body(), {"input": "Hello"})):
            body = meta.prepare_request(credential(), source, "muse-spark-1.3", False)[2]
            self.assertNotIn("include", body)

    def test_native_unsupported_options_are_rejected(self):
        for field in ("previous_response_id", "truncation", "background", "service_tier"):
            with self.subTest(field=field), self.assertRaises(meta.MetaModelAPIError):
                meta.prepare_request(
                    credential(),
                    seal_native_request(request_body(), {"input": "hello", field: "x"}),
                    "muse-spark-1.3",
                    False,
                )

    def test_native_typed_fields_cannot_bypass_validation(self):
        for extra in (
            {"reasoning": {"effort": "none"}},
            {"reasoning": {"effort": "max"}},
            {"input": [{"role": "user", "phase": "commentary", "content": "hello"}]},
            {"store": True},
            {"include": ["unknown"]},
        ):
            with self.subTest(extra=extra), self.assertRaises(meta.MetaModelAPIError):
                meta.prepare_request(
                    credential(),
                    seal_native_request(request_body(), {"input": "hello", **extra}),
                    "muse-spark-1.3-contributor",
                    False,
                )

    def test_max_reasoning_is_supported_only_by_standard_spark_13(self):
        source = seal_native_request(
            request_body(), {"input": "hello", "reasoning": {"effort": "max"}}
        )
        prepared = meta.prepare_request(credential(), source, "muse-spark-1.3", False)[2]
        self.assertEqual(prepared["reasoning"], {"effort": "max"})
        with self.assertRaises(meta.MetaModelAPIError):
            meta.prepare_request(credential(), source, "muse-spark-1.2", False)

    def test_generation_options_and_json_schema_are_mapped(self):
        source = request_body()
        source["generationConfig"] = {
            "maxOutputTokens": 32,
            "temperature": 0.3,
            "topP": 0.8,
            "responseMimeType": "application/json",
            "responseSchema": {"type": "object", "properties": {}},
        }
        body = meta.prepare_request(credential(), source, "muse-spark-1.3", False)[2]
        self.assertEqual(body["max_output_tokens"], 32)
        self.assertEqual(body["temperature"], 0.3)
        self.assertEqual(body["top_p"], 0.8)
        self.assertEqual(
            body["text"]["format"]["schema"], source["generationConfig"]["responseSchema"]
        )

    def test_invalid_numeric_ranges_fail_closed(self):
        for field, value in (
            ("maxOutputTokens", 15),
            ("maxOutputTokens", True),
            ("temperature", float("nan")),
            ("topP", 1.5),
        ):
            with self.subTest(field=field), self.assertRaises(meta.MetaModelAPIError):
                meta.prepare_request(
                    credential(),
                    {**request_body(), "generationConfig": {field: value}},
                    "muse-spark-1.3",
                    False,
                )

    def test_ambiguous_and_duplicate_tool_calls_fail_closed(self):
        for calls, result in (
            (
                [{"name": "read", "args": {}}, {"name": "read", "args": {}}],
                {"name": "read", "response": {}},
            ),
            (
                [
                    {"name": "read", "id": "same", "args": {}},
                    {"name": "read", "id": "same", "args": {}},
                ],
                {"name": "read", "id": "same", "response": {}},
            ),
        ):
            source = {
                "contents": [
                    {"role": "model", "parts": [{"functionCall": call} for call in calls]},
                    {"role": "user", "parts": [{"functionResponse": result}]},
                ]
            }
            with self.subTest(), self.assertRaises(meta.MetaModelAPIError):
                meta.prepare_request(credential(), source, "muse-spark-1.3", False)

    def test_stateless_responses_and_secret_header(self):
        source = request_body()
        before = copy.deepcopy(source)
        for streaming in (True, False):
            url, headers, body = meta.prepare_request(
                credential(), source, "muse-spark-1.3", streaming
            )
            self.assertEqual(url, "https://api.meta.ai/v1/responses")
            self.assertEqual(headers["Authorization"], "Bearer fixture-meta-api-key")
            self.assertEqual(body["model"], "muse-spark-1.3")
            self.assertEqual(body["stream"], streaming)
            self.assertIs(body["store"], False)
            self.assertEqual(body["input"][0]["content"][0]["text"], "Hello")
        self.assertEqual(source, before)

    def test_tool_calls_and_results_keep_ids_and_order(self):
        source = {
            "contents": [
                {
                    "role": "model",
                    "parts": [
                        {"text": "Checking"},
                        {"functionCall": {"name": "read", "args": {"path": "x"}}},
                    ],
                },
                {
                    "role": "user",
                    "parts": [
                        {"functionResponse": {"name": "read", "response": {"result": "yes"}}},
                        {"text": "Continue"},
                    ],
                },
            ]
        }
        body = meta.prepare_request(credential(), source, "muse-spark-1.3", False)[2]
        items = body["input"]
        self.assertEqual(
            [item["type"] for item in items],
            ["message", "function_call", "function_call_output", "message"],
        )
        self.assertEqual(items[1]["call_id"], items[2]["call_id"])
        self.assertEqual(items[0]["phase"], "commentary")
        self.assertNotIn("id", source["contents"][0]["parts"][1]["functionCall"])

    def test_tool_call_identifiers_obey_meta_64_character_limit(self):
        source = {
            "contents": [
                {
                    "role": "model",
                    "parts": [{"functionCall": {"name": "read", "id": "x" * 65, "args": {}}}],
                }
            ]
        }
        with self.assertRaises(meta.MetaModelAPIError):
            meta.prepare_request(credential(), source, "muse-spark-1.3", False)

    def test_final_assistant_text_is_not_mislabelled_commentary(self):
        source = {"contents": [{"role": "model", "parts": [{"text": "Done"}]}]}
        body = meta.prepare_request(credential(), source, "muse-spark-1.3", False)[2]
        self.assertNotIn("phase", body["input"][0])

    def test_unmatched_tool_result_is_rejected(self):
        source = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"functionResponse": {"id": "missing", "name": "read", "response": {}}}
                    ],
                }
            ]
        }
        with self.assertRaises(meta.MetaModelAPIError):
            meta.prepare_request(credential(), source, "muse-spark-1.3", False)

    def test_unsupported_generation_options_are_not_silently_lost(self):
        for field, value in (
            ("topK", 4),
            ("candidateCount", 2),
            ("stopSequences", ["stop"]),
            ("seed", 1),
        ):
            source = request_body()
            source["generationConfig"] = {field: value}
            with self.subTest(field=field), self.assertRaises(meta.MetaModelAPIError):
                meta.prepare_request(credential(), source, "muse-spark-1.3", False)
