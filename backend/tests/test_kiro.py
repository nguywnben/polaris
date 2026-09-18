"""Kiro API-key transport contracts; fixtures never contact an upstream account."""

from __future__ import annotations

import asyncio
import json
import struct
import sys
import unittest
import zlib
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.kiro import KiroError, normalize_credential, prepare_request, stream_to_gemini


def frame(event: str, payload: dict, message_type: str = "event") -> bytes:
    headers = b""
    for key, value in {":message-type": message_type, ":event-type": event}.items():
        name, text = key.encode(), value.encode()
        headers += bytes([len(name)]) + name + b"\x07" + struct.pack(">H", len(text)) + text
    data = json.dumps(payload).encode()
    prelude = struct.pack(">II", 16 + len(headers) + len(data), len(headers))
    message = prelude + struct.pack(">I", zlib.crc32(prelude)) + headers + data
    return message + struct.pack(">I", zlib.crc32(message))


async def chunks(data: bytes, size: int = 7):
    for offset in range(0, len(data), size):
        yield data[offset : offset + size]


async def events(data: bytes, size: int = 7) -> list[dict]:
    return [
        json.loads(item.removeprefix("data: ").strip())
        async for item in stream_to_gemini(chunks(data, size))
    ]


class KiroCredentialTests(unittest.TestCase):
    def test_api_key_and_region_normalization(self):
        result = normalize_credential({"api_key": " test-key-not-real ", "region": "eu-central-1"})
        self.assertEqual(
            result,
            {
                "provider": "kiro",
                "credential_type": "api_key",
                "api_key": "test-key-not-real",
                "region": "eu-central-1",
            },
        )

    def test_credentials_reject_injection_and_invalid_region(self):
        for update in (
            {"api_key": "bad\r\nHeader: x"},
            {"region": "us-east-1.evil.example"},
            {"profile_arn": "arn:aws:codewhisperer:eu-central-1:123456789012:profile/test"},
        ):
            with self.subTest(update=update), self.assertRaises(KiroError):
                normalize_credential({"api_key": "test-key-not-real", **update})

    def test_request_preserves_system_history_and_config(self):
        request = {
            "systemInstruction": {"parts": [{"text": "Be concise"}]},
            "contents": [
                {"role": "user", "parts": [{"text": "Hello"}]},
                {"role": "model", "parts": [{"text": "Hi"}]},
                {"role": "user", "parts": [{"text": "Again"}]},
            ],
            "generationConfig": {"maxOutputTokens": 90, "temperature": 0},
        }
        url, headers, payload = prepare_request(
            {"api_key": "test-key-not-real"}, request, "actual-model", False
        )
        self.assertTrue(url.endswith("/generateAssistantResponse"))
        self.assertEqual(headers["tokentype"], "API_KEY")
        self.assertNotIn("stream", payload)
        self.assertEqual(payload["inferenceConfig"], {"maxTokens": 90, "temperature": 0})
        self.assertIn(
            "Be concise", payload["conversationState"]["history"][0]["userInputMessage"]["content"]
        )
        self.assertEqual(
            payload["conversationState"]["currentMessage"]["userInputMessage"]["content"], "Again"
        )

    def test_unsupported_semantics_are_not_silently_removed(self):
        for addition in (
            {"generationConfig": {"responseMimeType": "application/json"}},
            {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"fileData": {"fileUri": "https://example.com/audio"}}],
                    }
                ]
            },
            {"toolConfig": {"functionCallingConfig": {"mode": "ANY"}}},
        ):
            with self.subTest(addition=addition), self.assertRaises(KiroError):
                prepare_request(
                    {"api_key": "test-key-not-real"},
                    {"contents": [{"role": "user", "parts": [{"text": "hello"}]}], **addition},
                    "model",
                    True,
                )

    def test_reasoning_history_is_not_flattened_into_visible_text(self):
        for metadata in ({"thought": True}, {"thoughtSignature": "opaque-signature"}):
            with self.subTest(metadata=metadata), self.assertRaises(KiroError):
                prepare_request(
                    {"api_key": "test-key-not-real"},
                    {
                        "contents": [
                            {"role": "model", "parts": [{"text": "reasoning", **metadata}]},
                            {"role": "user", "parts": [{"text": "continue"}]},
                        ]
                    },
                    "model",
                    True,
                )

    def test_tool_result_ids_match_and_current_turn_has_schema(self):
        request = {
            "tools": [
                {"functionDeclarations": [{"name": "search", "parameters": {"type": "object"}}]}
            ],
            "contents": [
                {"role": "user", "parts": [{"text": "Find it"}]},
                {
                    "role": "model",
                    "parts": [
                        {"functionCall": {"name": "search", "id": "call1", "args": {"q": "abc"}}}
                    ],
                },
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": "search",
                                "id": "call1",
                                "response": {"found": True},
                            }
                        }
                    ],
                },
            ],
        }
        _, _, payload = prepare_request({"api_key": "test-key-not-real"}, request, "model", True)
        context = payload["conversationState"]["currentMessage"]["userInputMessage"][
            "userInputMessageContext"
        ]
        self.assertEqual(context["toolResults"][0]["toolUseId"], "call1")
        self.assertEqual(context["tools"][0]["toolSpecification"]["name"], "search")

    def test_unmatched_tool_result_is_rejected(self):
        with self.assertRaises(KiroError):
            prepare_request(
                {"api_key": "test-key-not-real"},
                {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"functionResponse": {"name": "search", "response": {}}}],
                        }
                    ]
                },
                "model",
                True,
            )

    def test_schema_type_and_json_schema_are_preserved(self):
        request = {
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": "search",
                            "parametersJsonSchema": {
                                "type": "OBJECT",
                                "properties": {"q": {"type": "STRING"}},
                            },
                        }
                    ]
                }
            ],
            "contents": [{"role": "user", "parts": [{"text": "hello"}]}],
        }
        _, _, result = prepare_request({"api_key": "test-key-not-real"}, request, "model", True)
        schema = result["conversationState"]["currentMessage"]["userInputMessage"][
            "userInputMessageContext"
        ]["tools"][0]["toolSpecification"]["inputSchema"]["json"]
        self.assertEqual(schema, {"type": "object", "properties": {"q": {"type": "string"}}})

    def test_malformed_request_shapes_fail_with_safe_errors(self):
        for request in (
            {"contents": [None]},
            {"contents": [{"role": "user", "parts": [None]}]},
            {
                "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
                "generationConfig": {"temperature": float("nan")},
            },
        ):
            with self.subTest(request=request), self.assertRaises(KiroError):
                prepare_request({"api_key": "test-key-not-real"}, request, "model", True)


class KiroStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_split_binary_text_and_cumulative_usage(self):
        wire = (
            frame("assistantResponseEvent", {"content": "Xin chào"})
            + frame("metricsEvent", {"inputTokens": 10, "outputTokens": 2})
            + frame("metricsEvent", {"inputTokens": 10, "outputTokens": 3})
            + frame("messageStopEvent", {})
        )
        result = await events(wire, 1)
        self.assertEqual(result[0]["candidates"][0]["content"]["parts"], [{"text": "Xin chào"}])
        self.assertEqual(result[-1]["candidates"][0]["finishReason"], "STOP")
        self.assertEqual(result[-1]["usageMetadata"]["totalTokenCount"], 13)

    async def test_missing_stop_and_corrupt_or_truncated_frame_fail_closed(self):
        valid = frame("assistantResponseEvent", {"content": "partial"})
        corrupt = bytearray(valid)
        corrupt[-1] ^= 1
        for wire in (b"", valid, valid[:-1], bytes(corrupt), struct.pack(">III", 99_000_000, 0, 0)):
            with self.subTest(wire=wire[:10]), self.assertRaises(KiroError):
                await events(wire)

    async def test_upstream_exception_is_sanitized(self):
        with self.assertRaises(KiroError) as caught:
            await events(
                frame("validationException", {"message": "private key and prompt"}, "exception")
            )
        self.assertNotIn("private", str(caught.exception))

    async def test_cancellation_is_not_converted_to_success(self):
        async def cancelled():
            yield frame("assistantResponseEvent", {"content": "partial"})
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            _ = [item async for item in stream_to_gemini(cancelled())]

    async def test_tool_partial_objects_emit_one_complete_call(self):
        wire = (
            frame("toolUseEvent", {"toolUseId": "call1", "name": "search", "input": {"q": "a"}})
            + frame("toolUseEvent", {"toolUseId": "call1", "input": {"q": "ab"}, "stop": True})
            + frame("messageStopEvent", {})
        )
        result = await events(wire)
        calls = [
            part["functionCall"]
            for item in result
            for candidate in item.get("candidates", [])
            for part in candidate.get("content", {}).get("parts", [])
            if "functionCall" in part
        ]
        self.assertEqual(calls, [{"id": "call1", "name": "search", "args": {"q": "ab"}}])

    async def test_string_tool_arguments_and_max_tokens(self):
        result = await events(
            frame("toolUseEvent", {"toolUseId": "c", "name": "search", "input": '{"q":'})
            + frame("toolUseEvent", {"toolUseId": "c", "input": '"ok"}'})
            + frame("messageStopEvent", {"stopReason": "max_tokens"})
        )
        self.assertEqual(result[-1]["candidates"][0]["finishReason"], "MAX_TOKENS")
        self.assertEqual(
            result[-1]["candidates"][0]["content"]["parts"][0]["functionCall"]["args"], {"q": "ok"}
        )

    async def test_terminal_event_does_not_hide_later_corruption(self):
        with self.assertRaises(KiroError):
            await events(frame("messageStopEvent", {}) + b"broken")

    async def test_missing_usage_is_not_estimated(self):
        result = await events(
            frame("assistantResponseEvent", {"content": "hello"}) + frame("messageStopEvent", {})
        )
        self.assertNotIn("usageMetadata", result[-1])


class KiroDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def discover_with(self, handler):
        from core.kiro import discover_models

        @asynccontextmanager
        async def client(**kwargs):
            self.assertFalse(kwargs["follow_redirects"])
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as value:
                yield value

        with patch("core.kiro.http_client.get_client", client):
            return await discover_models({"api_key": "test-key-not-real"})

    async def test_live_models_are_bounded_deduplicated_and_paginated(self):
        def handle(request):
            self.assertEqual(request.headers["tokentype"], "API_KEY")
            self.assertEqual(request.url.host, "q.us-east-1.amazonaws.com")
            if "nextToken" in request.url.params:
                return httpx.Response(200, json={"models": [{"modelId": "m1"}, {"modelId": "m2"}]})
            return httpx.Response(200, json={"models": [{"modelId": "m1"}], "nextToken": "page2"})

        self.assertEqual(await self.discover_with(handle), ["m1", "m2"])

    async def test_status_errors_are_safe_and_not_fabricated_catalogs(self):
        for status in (401, 403, 429, 500, 302):
            with self.subTest(status=status), self.assertRaises(KiroError) as caught:
                await self.discover_with(
                    lambda _: httpx.Response(
                        status,
                        text="private-key-response",
                        headers={"location": "https://evil.example"},
                    )
                )
            self.assertNotIn("private-key", str(caught.exception))

    async def test_malformed_catalog_and_pagination_cycle_rejected(self):
        for payload in (
            {"models": "no"},
            {"models": [{"modelId": "bad\nmodel"}]},
            {"models": [], "nextToken": "again"},
        ):
            with self.subTest(payload=payload), self.assertRaises(KiroError):
                await self.discover_with(lambda _: httpx.Response(200, json=payload))


if __name__ == "__main__":
    unittest.main()
