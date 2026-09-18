"""Four API platforms: deterministic boundary contracts, no vendor credentials."""

import copy
import io
import json
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import UploadFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import hosted_providers as hosted
from core.api.utils import collect_streaming_response
from core.extended_provider_runtime import (
    ProviderStreamError,
    _platform_stream_event,
    _StreamDecoder,
    stream_extended_request,
)
from core.panel.providers import extended
from core.provider_registry import EXTENDED_PROVIDER_DEFAULT_BASE_URLS, EXTENDED_PROVIDERS

PLATFORMS = {
    "groq": "https://api.groq.com/openai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
}


class ApiPlatformTests(unittest.TestCase):
    def test_unrepresentable_generation_options_are_not_silently_dropped(self):
        for provider in PLATFORMS:
            for config in (
                {"topK": 3},
                {"thinkingConfig": {"thinkingBudget": 100}},
                {"responseMimeType": "image/png"},
                {"responseSchema": {"type": "object"}},
            ):
                with (
                    self.subTest(provider=provider, config=config),
                    self.assertRaises(hosted.HostedProviderError),
                ):
                    hosted.prepare_request(
                        {"provider": provider, "api_key": "fixture-key"},
                        {"generationConfig": config},
                        "chat-model",
                        True,
                    )
        _, _, payload = hosted.prepare_request(
            {"provider": "mistral", "api_key": "fixture-key"},
            {"generationConfig": {"seed": 123}},
            "chat-model",
            True,
        )
        self.assertEqual(payload["random_seed"], 123)
        self.assertNotIn("seed", payload)

    def test_vendor_stream_content_usage_and_errors(self):
        event = {
            "choices": [
                {
                    "delta": {
                        "content": [
                            {"type": "thinking", "thinking": [{"type": "text", "text": "Think"}]},
                            {"type": "text", "text": "Answer"},
                        ]
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3},
        }
        before = copy.deepcopy(event)
        decoder = _StreamDecoder("openai")
        result = decoder.decode(_platform_stream_event("mistral", event))
        self.assertIn('"thought": true', result)
        self.assertIn("Answer", result)
        self.assertIn('"totalTokenCount": 5', decoder.complete())
        self.assertEqual(before, event)
        decoder = _StreamDecoder("openai")
        decoder.decode({"choices": [{"delta": {}, "finish_reason": "stop"}]})
        decoder.decode(
            _platform_stream_event(
                "groq",
                {"choices": [], "x_groq": {"usage": {"prompt_tokens": 4, "completion_tokens": 2}}},
            )
        )
        self.assertIn('"totalTokenCount": 6', decoder.complete())
        with self.assertRaises(ProviderStreamError):
            _platform_stream_event("groq", {"x_groq": {"error": "secret upstream text"}})

    def test_registration_and_isolated_connection_defaults(self):
        for provider, base in PLATFORMS.items():
            with self.subTest(provider=provider):
                self.assertIn(provider, EXTENDED_PROVIDERS)
                source = {"provider": provider, "api_key": "fixture-key", "account_id": "other"}
                normalized = hosted.normalize_credential(source)
                self.assertEqual(normalized["base_url"], base)
                self.assertEqual(EXTENDED_PROVIDER_DEFAULT_BASE_URLS[provider], base)
                self.assertNotIn("account_id", normalized)
                self.assertNotIn("base_url", source)
                with self.assertRaises(hosted.HostedProviderError):
                    hosted.normalize_credential({**source, "base_url": "https://evil.test/v1"})

    def test_chat_and_stream_usage_contract(self):
        request = {"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]}
        for provider, base in PLATFORMS.items():
            with self.subTest(provider=provider):
                url, headers, body = hosted.prepare_request(
                    {"provider": provider, "api_key": "fixture-key"}, request, "chat-model", True
                )
                self.assertEqual(url, base + "/chat/completions")
                self.assertEqual(headers["Authorization"], "Bearer fixture-key")
                self.assertTrue(body["stream"])
                self.assertEqual("stream_options" in body, provider in {"groq", "deepseek"})
                if provider == "deepseek":
                    self.assertEqual(body["thinking"], {"type": "disabled"})
                if provider == "mistral":
                    self.assertEqual(body["reasoning_effort"], "none")

    def test_chat_catalog_filtering(self):
        self.assertEqual(
            hosted._catalog_ids(
                {
                    "data": [
                        {"id": "whisper-large-v3"},
                        {"id": "canopylabs/orpheus-v1-english"},
                        {"id": "groq/compound"},
                        {"id": "chat-model", "active": True},
                        {"id": "retired", "active": False},
                    ]
                },
                "groq",
            ),
            ["chat-model"],
        )
        self.assertEqual(
            hosted._catalog_ids(
                {
                    "data": [
                        {"id": "embed", "capabilities": {"completion_chat": False}},
                        {"id": "chat", "capabilities": {"completion_chat": True}},
                        {"id": "old", "archived": True, "capabilities": {"completion_chat": True}},
                    ]
                },
                "mistral",
            ),
            ["chat"],
        )

    def test_reasoning_and_tool_history_are_not_mutated(self):
        source = {
            "contents": [
                {
                    "role": "model",
                    "parts": [
                        {"text": "Think", "thought": True},
                        {"functionCall": {"id": "call-long-id", "name": "lookup", "args": {}}},
                    ],
                },
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "id": "call-long-id",
                                "name": "lookup",
                                "response": {"ok": True},
                            }
                        }
                    ],
                },
            ]
        }
        before = copy.deepcopy(source)
        for provider in ("deepseek", "mistral"):
            _, _, body = hosted.prepare_request(
                {"provider": provider, "api_key": "fixture-key"}, source, "chat-model", True
            )
            assistant, result = body["messages"]
            call_id = assistant["tool_calls"][0]["id"]
            self.assertEqual(call_id, result["tool_call_id"])
            if provider == "mistral":
                self.assertRegex(call_id, r"^[a-zA-Z0-9]{9}$")
                self.assertEqual(assistant["content"][0]["thinking"][0]["text"], "Think")
                self.assertNotIn("reasoning_content", assistant)
            else:
                self.assertEqual(assistant["reasoning_content"], "Think")
        self.assertEqual(source, before)


class ApiPlatformIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_management_add_discovers_catalog_without_inference_or_key_echo(self):
        for provider, base in PLATFORMS.items():
            with (
                self.subTest(provider=provider),
                patch.object(
                    extended, "discover_extended_models", AsyncMock(return_value=["chat-model"])
                ) as discover,
                patch.object(
                    extended,
                    "store_extended_credential",
                    AsyncMock(return_value={"action": "created", "filename": "fixture.json"}),
                ) as store,
            ):
                response = await extended.add_extended_credential(
                    provider,
                    extended.ExtendedCredentialRequest(api_key="fixture-private-key"),
                    "fixture-session",
                )
                self.assertEqual(response.status_code, 201)
                self.assertNotIn(b"fixture-private-key", response.body)
                self.assertTrue(json.loads(response.body)["connection_test_required"])
                self.assertEqual(discover.await_args.args[0]["base_url"], base)
                self.assertEqual(store.await_args.args[1], ["chat-model"])

    async def test_discovery_uses_real_bounded_http_adapter_for_each_platform(self):
        for provider, base in PLATFORMS.items():

            def handler(request):
                self.assertEqual(str(request.url), base + "/models")
                self.assertEqual(request.headers["authorization"], "Bearer fixture-key")
                return httpx.Response(
                    200,
                    json={
                        "data": [{"id": "chat-model", "capabilities": {"completion_chat": True}}]
                    },
                )

            @asynccontextmanager
            async def client(**kwargs):
                self.assertFalse(kwargs["follow_redirects"])
                async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as value:
                    yield value

            with (
                self.subTest(provider=provider),
                patch.object(hosted.http_client, "get_client", client),
            ):
                self.assertEqual(
                    await hosted.discover_models({"provider": provider, "api_key": "fixture-key"}),
                    ["chat-model"],
                )

    async def test_selected_provider_rejects_another_platform_import(self):
        for provider in PLATFORMS:
            payload = {"provider": "kimi", "api_key": "fixture-key"}
            file = UploadFile(filename="wrong.json", file=io.BytesIO(json.dumps(payload).encode()))
            response = await extended.import_extended_credentials(provider, [file], "fixture")
            report = json.loads(response.body)
            self.assertEqual(report["uploaded_count"], 0)
            self.assertNotIn("fixture-key", response.body.decode())

    async def test_fragmented_stream_and_nonstream_collection_for_all_platforms(self):
        for provider in PLATFORMS:
            content = (
                [
                    {"type": "thinking", "thinking": [{"type": "text", "text": "Think"}]},
                    {"type": "text", "text": "Xin chào"},
                ]
                if provider == "mistral"
                else "Xin chào"
            )
            events = [
                {"choices": [{"delta": {"content": content}}]},
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call12345",
                                        "function": {"name": "lookup", "arguments": '{"city":'},
                                    }
                                ]
                            }
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [{"index": 0, "function": {"arguments": '"Hanoi"}'}}]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                },
                {"choices": [], "usage": {"prompt_tokens": 8, "completion_tokens": 3}},
            ]
            if provider == "groq":
                events[-1] = {"choices": [], "x_groq": {"usage": events[-1]["usage"]}}
            wire = (
                "".join(
                    "data: " + json.dumps(event, ensure_ascii=False) + "\n\n" for event in events
                )
                + "data: [DONE]\n\n"
            ).encode()

            class Body(httpx.AsyncByteStream):
                async def __aiter__(self):
                    for index in range(0, len(wire), 7):
                        yield wire[index : index + 7]

            @asynccontextmanager
            async def client(**kwargs):
                self.assertFalse(kwargs["follow_redirects"])
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Body()))
                ) as value:
                    yield value

            with (
                self.subTest(provider=provider),
                patch("core.extended_provider_runtime.http_client.get_streaming_client", client),
            ):
                stream = stream_extended_request(
                    {"provider": provider, "api_key": "fixture-key"},
                    "chat-model",
                    url=PLATFORMS[provider] + "/chat/completions",
                    body={},
                    headers={},
                    timeout=30,
                )
                response = await collect_streaming_response(stream)
                self.assertEqual(response.status_code, 200)
                payload = json.loads(response.body)
                self.assertEqual(payload["usageMetadata"]["totalTokenCount"], 11)
                parts = payload["candidates"][0]["content"]["parts"]
                self.assertTrue(any(p.get("text") == "Xin chào" for p in parts))
                self.assertTrue(
                    any(p.get("functionCall", {}).get("args") == {"city": "Hanoi"} for p in parts)
                )
                if provider == "mistral":
                    self.assertEqual(parts[0], {"text": "Think", "thought": True})


if __name__ == "__main__":
    unittest.main()
