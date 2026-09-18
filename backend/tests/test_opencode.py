"""OpenCode contract tests; no live accounts or upstream calls."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core import opencode


def credential(plan="zen", **extra):
    return {"api_key": "test-opencode-secret", "plan": plan, **extra}


def request_body():
    return {
        "systemInstruction": {"parts": [{"text": "Be concise."}]},
        "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
        "generationConfig": {"maxOutputTokens": 123, "temperature": 0.4},
    }


class OpenCodeContractTests(unittest.TestCase):
    def test_non_gemini_rejects_reasoning_history_before_conversion(self):
        parts = [
            {"text": "private reasoning", "thought": True},
            {"text": "signed content", "thoughtSignature": "opaque-signature"},
        ]
        for model in ("glm-5", "gpt-5.4", "claude-sonnet-4-6"):
            for part in parts:
                for location in ("contents", "systemInstruction"):
                    with self.subTest(model=model, part=part, location=location):
                        body = request_body()
                        if location == "contents":
                            body["contents"].insert(0, {"role": "model", "parts": [part]})
                        else:
                            body["systemInstruction"] = {"parts": [part]}
                        with (
                            patch("core.opencode.gemini_request_to_xai") as chat,
                            patch("core.opencode.gemini_request_to_codex") as responses,
                            patch("core.opencode.gemini_request_to_anthropic") as messages,
                        ):
                            with self.assertRaisesRegex(ValueError, "Reasoning history"):
                                opencode.prepare_request(credential(), body, model, True)
                            chat.assert_not_called()
                            responses.assert_not_called()
                            messages.assert_not_called()

    def test_native_gemini_preserves_reasoning_and_signature_without_mutation(self):
        body = request_body()
        body["contents"].insert(
            0,
            {
                "role": "model",
                "parts": [
                    {"text": "reasoning", "thought": True, "thoughtSignature": "opaque-signature"}
                ],
            },
        )
        before = copy.deepcopy(body)
        prepared = opencode.prepare_request(credential(), body, "gemini-3.1-pro", True)[2]
        self.assertEqual(prepared, before)
        self.assertEqual(body, before)

    def test_explicit_non_thought_text_remains_supported(self):
        body = request_body()
        body["contents"][0]["parts"][0]["thought"] = False
        for model in ("glm-5", "gpt-5.4", "claude-sonnet-4-6"):
            with self.subTest(model=model):
                prepared = opencode.prepare_request(credential(), body, model, False)[2]
                self.assertIn("Hello", json.dumps(prepared))

    def test_chat_stream_requests_usage_without_touching_other_protocols(self):
        for plan in ("zen", "go"):
            with self.subTest(plan=plan):
                streamed = opencode.prepare_request(
                    credential(plan), request_body(), "glm-5", True
                )[2]
                self.assertEqual(streamed["stream_options"], {"include_usage": True})
                plain = opencode.prepare_request(credential(plan), request_body(), "glm-5", False)[
                    2
                ]
                self.assertNotIn("stream_options", plain)
        for model in ("gpt-5.4", "claude-sonnet-4-6", "gemini-3.1-pro"):
            with self.subTest(model=model):
                body = opencode.prepare_request(credential(), request_body(), model, True)[2]
                self.assertNotIn("stream_options", body)

    def test_product_defaults_and_no_mutation(self):
        original = credential("go")
        saved = opencode.normalize_credential(original)
        self.assertEqual(saved["base_url"], "https://opencode.ai/zen/go/v1")
        self.assertEqual(saved["provider"], "opencode")
        self.assertEqual(saved["credential_type"], "api_key")
        self.assertNotIn("provider", original)
        self.assertEqual(opencode.normalize_credential(credential())["plan"], "zen")

    def test_rejects_invalid_credential(self):
        for data in (
            {},
            credential("unknown"),
            credential(api_key="public"),
            credential(api_key="x\r\ny"),
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                opencode.normalize_credential(data)

    def test_rejects_unsafe_urls(self):
        for url in (
            "http://opencode.ai/zen/v1",
            "https://u:p@opencode.ai/v1",
            "https://opencode.ai/v1?key=x",
            "https://opencode.ai/v1#x",
            "https://127.0.0.1/v1",
            "https://opencode.ai/../v1",
            "https://attacker.example/v1",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                opencode.normalize_credential(credential(base_url=url))

    def test_model_protocol_matrix(self):
        cases = [
            ("zen", "gpt-5.4", "responses"),
            ("zen", "grok-4.6", "responses"),
            ("zen", "claude-sonnet-4-6", "anthropic"),
            ("zen", "qwen3.7-plus", "anthropic"),
            ("zen", "minimax-m3", "openai"),
            ("go", "minimax-m3", "anthropic"),
            ("go", "kimi-k3", "openai"),
            ("zen", "gemini-3.1-pro", "gemini"),
        ]
        for plan, model, protocol in cases:
            with self.subTest(plan=plan, model=model):
                self.assertEqual(opencode.protocol_for_model(credential(plan), model), protocol)

    def test_unknown_protocol_and_path_injection_fail_closed(self):
        for model in ("future-unknown", "../gpt-5.4", "gpt-5.4?key=x", "opencode/gpt-5.4"):
            with self.subTest(model=model), self.assertRaises(ValueError):
                opencode.protocol_for_model(credential(), model)
        with self.assertRaises(ValueError):
            opencode.protocol_for_model(credential("go"), "gemini-3.1-pro")

    def test_chat_request_preserves_parameters(self):
        original = request_body()
        before = copy.deepcopy(original)
        url, headers, body = opencode.prepare_request(credential(), original, "kimi-k3", True)
        self.assertEqual(url, "https://opencode.ai/zen/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer test-opencode-secret")
        self.assertEqual(body["max_tokens"], 123)
        self.assertTrue(body["stream"])
        self.assertEqual(original, before)
        self.assertTrue(headers["User-Agent"].lower().startswith("polaris/"))

    def test_responses_does_not_force_codex_stream_or_encrypted_reasoning(self):
        url, _, body = opencode.prepare_request(credential(), request_body(), "gpt-5.4", False)
        self.assertTrue(url.endswith("/responses"))
        self.assertFalse(body["stream"])
        self.assertNotIn("include", body)
        self.assertEqual(body["max_output_tokens"], 123)
        self.assertEqual(body["temperature"], 0.4)
        self.assertEqual(body["instructions"], "Be concise.")

    def test_anthropic_uses_key_header_and_tool_choice(self):
        body = request_body()
        body["tools"] = [
            {"functionDeclarations": [{"name": "read_file", "parameters": {"type": "object"}}]}
        ]
        body["toolConfig"] = {
            "functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": ["read_file"]}
        }
        url, headers, prepared = opencode.prepare_request(
            credential("go"), body, "minimax-m3", False
        )
        self.assertTrue(url.endswith("/messages"))
        self.assertEqual(headers["x-api-key"], "test-opencode-secret")
        self.assertNotIn("Authorization", headers)
        self.assertEqual(prepared["tool_choice"], {"type": "tool", "name": "read_file"})

    def test_gemini_body_keeps_native_shape_but_no_internal_metadata(self):
        body = request_body()
        body["_polaris_session_id"] = "session-123"
        url, _, prepared = opencode.prepare_request(credential(), body, "gemini-3.1-pro", True)
        self.assertTrue(url.endswith("/models/gemini-3.1-pro:streamGenerateContent?alt=sse"))
        self.assertEqual(prepared["contents"], body["contents"])
        self.assertNotIn("_polaris_session_id", prepared)

    def test_session_is_stable_for_followups_and_key_scoped(self):
        first = request_body()
        followup = copy.deepcopy(first)
        followup["contents"].append({"role": "user", "parts": [{"text": "Continue"}]})

        def session(data, body):
            return opencode.prepare_request(data, body, "kimi-k3", True)[1]["x-opencode-session"]

        self.assertEqual(session(credential("go"), first), session(credential("go"), followup))
        self.assertNotEqual(
            session(credential("go"), first), session(credential("go", api_key="other-key"), first)
        )
        first["_polaris_session_id"] = "native-session"
        self.assertEqual(session(credential("go"), first), "native-session")

    def test_unsupported_semantics_are_not_silently_dropped(self):
        for field, value, model in (
            ("topK", 5, "kimi-k3"),
            ("stopSequences", ["STOP"], "gpt-5.4"),
            ("candidateCount", 2, "minimax-m3"),
        ):
            body = request_body()
            body["generationConfig"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                opencode.prepare_request(credential("go"), body, model, False)

    def test_tools_roundtrip_identifiers_survive_conversion(self):
        body = request_body()
        body["contents"].extend(
            [
                {
                    "role": "model",
                    "parts": [
                        {"functionCall": {"id": "call-1", "name": "read", "args": {"p": "a"}}}
                    ],
                },
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "id": "call-1",
                                "name": "read",
                                "response": {"text": "ok"},
                            }
                        }
                    ],
                },
            ]
        )
        for model in ("kimi-k3", "gpt-5.4", "claude-sonnet-4-6"):
            with self.subTest(model=model):
                prepared = opencode.prepare_request(credential(), body, model, True)[2]
                self.assertEqual(json.dumps(prepared).count("call-1"), 2)

    def test_tool_subset_and_unknown_content_are_rejected(self):
        for model in ("kimi-k3", "gpt-5.4", "claude-sonnet-4-6"):
            body = request_body()
            body["toolConfig"] = {
                "functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": ["one", "two"]}
            }
            with self.subTest(model=model), self.assertRaises(ValueError):
                opencode.prepare_request(credential(), body, model, True)
            body = request_body()
            body["contents"][0]["parts"] = [{"executableCode": {"code": "print(1)"}}]
            with self.subTest(model=model), self.assertRaises(ValueError):
                opencode.prepare_request(credential(), body, model, True)

    def test_invalid_session_header_is_rejected(self):
        body = request_body()
        body["_polaris_session_id"] = "session\r\nAuthorization: secret"
        with self.assertRaises(ValueError):
            opencode.prepare_request(credential("go"), body, "kimi-k3", True)

    def test_missing_tool_ids_are_linked(self):
        body = request_body()
        body["contents"].extend(
            [
                {"role": "model", "parts": [{"functionCall": {"name": "read", "args": {}}}]},
                {
                    "role": "user",
                    "parts": [{"functionResponse": {"name": "read", "response": {"text": "ok"}}}],
                },
            ]
        )
        prepared = opencode.prepare_request(credential(), body, "claude-sonnet-4-6", False)[2]
        self.assertEqual(
            prepared["messages"][1]["content"][0]["id"],
            prepared["messages"][2]["content"][0]["tool_use_id"],
        )


class OpenCodeCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def discover(self, response, plan="zen"):
        requests = []

        def handler(request):
            requests.append(request)
            return response

        @asynccontextmanager
        async def client(**kwargs):
            self.assertFalse(kwargs["follow_redirects"])
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
                yield session

        with patch.object(opencode.http_client, "get_client", client):
            result = await opencode.discover_models(credential(plan))
        return result, requests

    async def test_catalog_deduplicates_and_filters_unknown_protocols(self):
        models, requests = await self.discover(
            httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "kimi-k3"},
                        {"id": "kimi-k3"},
                        {"id": "unknown-future"},
                        {"id": "minimax-m3"},
                    ]
                },
            ),
            "go",
        )
        self.assertEqual(models, ["kimi-k3", "minimax-m3"])
        self.assertEqual(str(requests[0].url), "https://opencode.ai/zen/go/v1/models")
        self.assertNotIn("authorization", requests[0].headers)

    async def test_rejects_redirect_and_sanitizes_remote_errors(self):
        for status in (302, 401, 403, 429, 500):
            with self.subTest(status=status), self.assertRaises(opencode.OpenCodeError) as raised:
                await self.discover(httpx.Response(status, text="test-opencode-secret"))
            self.assertNotIn("test-opencode-secret", str(raised.exception))

    async def test_rejects_malformed_oversized_and_empty_catalog(self):
        for response in (
            httpx.Response(200, text="not JSON"),
            httpx.Response(200, content=b"x" * (opencode.MAX_CATALOG_BYTES + 1)),
            httpx.Response(200, json={"data": []}),
            httpx.Response(200, json={"data": [{"id": "../bad"}]}),
        ):
            with self.subTest(), self.assertRaises(opencode.OpenCodeError):
                await self.discover(response)
