"""Hosted provider boundaries use synthetic catalogs; no real credentials or network."""

from __future__ import annotations

import asyncio
import copy
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.hosted_providers import (
    HOSTED_PROVIDERS,
    MAX_CATALOG_BYTES,
    HostedProviderError,
    discover_models,
    normalize_credential,
    prepare_request,
)


def credential(provider="kimi", **extra):
    return {"provider": provider, "api_key": "synthetic-key-not-a-secret", **extra}


class HostedProviderTests(unittest.IsolatedAsyncioTestCase):
    @asynccontextmanager
    async def transport(self, handler):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:

            @asynccontextmanager
            async def get_client(**kwargs):
                self.assertFalse(kwargs["follow_redirects"])
                yield client

            with patch("core.hosted_providers.http_client.get_client", get_client):
                yield

    def test_hosted_defaults_are_specific_and_normalized_without_mutation(self):
        expected = {
            "groq": "https://api.groq.com/openai/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "mistral": "https://api.mistral.ai/v1",
            "cerebras": "https://api.cerebras.ai/v1",
            "kimi": "https://api.moonshot.ai/v1",
            "cloudflare": "https://api.cloudflare.com/client/v4",
            "nvidia": "https://integrate.api.nvidia.com/v1",
            "poolside": "https://inference.poolside.ai/v1",
            "kimchi": "https://llm.kimchi.dev/openai/v1",
            "kilo": "https://api.kilo.ai/api/gateway",
        }
        self.assertEqual(set(expected), set(HOSTED_PROVIDERS))
        for provider, base in expected.items():
            source = credential(provider, account_id="a" * 32)
            result = normalize_credential(source)
            self.assertEqual(base, result["base_url"])
            self.assertEqual("api_key", result["credential_type"])
            self.assertNotIn("base_url", source)

    def test_rejects_unsafe_urls_without_echoing_secrets(self):
        for url in (
            "http://api.moonshot.ai/v1",
            "https://localhost/v1",
            "https://127.0.0.1/v1",
            "https://api.moonshot.ai.evil.test/v1",
            "https://secret@api.moonshot.ai/v1",
            "https://api.moonshot.ai/v1?key=secret",
            "https://api.moonshot.ai/v1#secret",
            "https://api.moonshot.ai:444/v1",
            "https://api.moonshot.ai/../v1",
            "https://api.moonshot.ai/%2e%2e/v1",
            "https://api.moonshot.ai\\evil.test/v1",
        ):
            with self.subTest(url=url), self.assertRaises(HostedProviderError) as caught:
                normalize_credential(credential(base_url=url))
            self.assertNotIn("secret", str(caught.exception))

    def test_rejects_missing_key_and_header_injection(self):
        for key in ("", "a\r\nb: c", "has space", "\x00", "é", "a" * 8193):
            with self.subTest(key_length=len(key)), self.assertRaises(HostedProviderError):
                normalize_credential(credential(api_key=key))

    def test_rejects_unsupported_provider_and_invalid_context(self):
        for data in (
            credential("unknown"),
            credential("cloudflare"),
            credential("cloudflare", account_id="../account"),
            credential("kilo", organization_id="org\r\nInjected: yes"),
        ):
            with self.assertRaises(HostedProviderError):
                normalize_credential(data)

    def test_malformed_provider_type_fails_with_safe_error(self):
        with self.assertRaises(HostedProviderError):
            normalize_credential(credential(provider=["kimi"]))

    def test_kimi_china_endpoint_can_be_selected_explicitly(self):
        result = normalize_credential(credential(base_url="https://api.moonshot.cn/v1/"))
        self.assertEqual("https://api.moonshot.cn/v1", result["base_url"])

    def test_normalization_strips_other_provider_connection_context(self):
        data = credential(
            "kimi",
            plan="go",
            account_id="account",
            organization_id="org",
            region="us-east-1",
            profile_arn="profile",
            credential_label="Keep",
            model_ids=["model"],
        )
        normalized = normalize_credential(data)
        for field in ("plan", "account_id", "organization_id", "region", "profile_arn"):
            self.assertNotIn(field, normalized)
        self.assertEqual(normalized["credential_label"], "Keep")
        self.assertEqual(normalized["model_ids"], ["model"])

    def test_prepare_request_preserves_tools_reasoning_and_input(self):
        source = {
            "contents": [
                {"role": "user", "parts": [{"text": "weather?"}]},
                {
                    "role": "model",
                    "parts": [
                        {"text": "Need a tool", "thought": True},
                        {
                            "functionCall": {
                                "id": "call-1",
                                "name": "weather",
                                "args": {"city": "Hanoi"},
                            }
                        },
                    ],
                },
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "id": "call-1",
                                "name": "weather",
                                "response": {"temp": 20},
                            }
                        }
                    ],
                },
            ],
            "tools": [
                {"functionDeclarations": [{"name": "weather", "parameters": {"type": "object"}}]}
            ],
            "generationConfig": {"maxOutputTokens": 50},
        }
        before = copy.deepcopy(source)
        for provider in HOSTED_PROVIDERS:
            url, headers, payload = prepare_request(
                credential(provider, account_id="a" * 32), source, "test-model", True
            )
            self.assertTrue(url.endswith("/chat/completions"))
            self.assertEqual("text/event-stream", headers["Accept"])
            self.assertTrue(payload["stream"])
            expected_id = "p00000001" if provider == "mistral" else "call-1"
            self.assertEqual(expected_id, payload["messages"][1]["tool_calls"][0]["id"])
            if provider == "mistral":
                self.assertEqual(
                    "Need a tool", payload["messages"][1]["content"][0]["thinking"][0]["text"]
                )
            else:
                self.assertEqual("Need a tool", payload["messages"][1]["reasoning_content"])
            self.assertEqual(expected_id, payload["messages"][2]["tool_call_id"])
            self.assertEqual(50, payload["max_tokens"])
        self.assertEqual(source, before)

    def test_cloudflare_url_and_kilo_org_header(self):
        url, _, _ = prepare_request(
            credential("cloudflare", account_id="b" * 32), {}, "@cf/model", False
        )
        self.assertEqual(
            "https://api.cloudflare.com/client/v4/accounts/" + "b" * 32 + "/ai/v1/chat/completions",
            url,
        )
        _, headers, _ = prepare_request(
            credential("kilo", organization_id="org_123"), {}, "a/model", False
        )
        self.assertEqual("org_123", headers["X-KiloCode-OrganizationId"])
        self.assertFalse(any("Version" in key for key in headers))

    def test_streaming_requests_ask_supported_endpoints_for_authoritative_usage(self):
        for provider in ("kimi", "cloudflare", "nvidia", "poolside", "kilo"):
            with self.subTest(provider=provider):
                data = credential(provider, account_id="a" * 32)
                _, _, streamed = prepare_request(data, {}, "model", True)
                self.assertEqual(streamed["stream_options"], {"include_usage": True})
                _, _, ordinary = prepare_request(data, {}, "model", False)
                self.assertNotIn("stream_options", ordinary)

    def test_kimchi_does_not_receive_an_unverified_optional_wire_parameter(self):
        _, _, payload = prepare_request(credential("kimchi"), {}, "model", True)
        self.assertNotIn("stream_options", payload)

    def test_missing_tool_ids_are_linked_across_content_part_indices(self):
        source = {
            "contents": [
                {
                    "role": "model",
                    "parts": [{"text": "Lookup"}, {"functionCall": {"name": "lookup", "args": {}}}],
                },
                {
                    "role": "user",
                    "parts": [{"functionResponse": {"name": "lookup", "response": {"ok": True}}}],
                },
            ]
        }
        before = copy.deepcopy(source)
        _, _, payload = prepare_request(credential(), source, "model", False)
        self.assertEqual(
            payload["messages"][0]["tool_calls"][0]["id"], payload["messages"][1]["tool_call_id"]
        )
        self.assertEqual(before, source)

    def test_ambiguous_or_orphaned_tool_result_fails_closed(self):
        for calls in [[], [{"functionCall": {"name": "lookup", "args": {}}}] * 2]:
            source = {
                "contents": [
                    {"role": "model", "parts": calls},
                    {
                        "role": "user",
                        "parts": [{"functionResponse": {"name": "lookup", "response": {}}}],
                    },
                ]
            }
            with self.assertRaises(HostedProviderError):
                prepare_request(credential(), source, "model", False)

    def test_parallel_same_name_tool_calls_with_explicit_ids_are_supported(self):
        source = {
            "contents": [
                {
                    "role": "model",
                    "parts": [
                        {"functionCall": {"name": "lookup", "id": "a", "args": {}}},
                        {"functionCall": {"name": "lookup", "id": "b", "args": {}}},
                    ],
                },
                {
                    "role": "user",
                    "parts": [
                        {"functionResponse": {"name": "lookup", "id": "b", "response": {}}},
                        {"functionResponse": {"name": "lookup", "id": "a", "response": {}}},
                    ],
                },
            ]
        }
        _, _, payload = prepare_request(credential(), source, "model", False)
        self.assertEqual(
            [message["tool_call_id"] for message in payload["messages"][1:]], ["b", "a"]
        )

    def test_tool_selection_never_relaxes_multiple_allowed_names(self):
        source = {
            "tools": [
                {"functionDeclarations": [{"name": name} for name in ("one", "two", "forbidden")]}
            ],
            "toolConfig": {
                "functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": ["one", "two"]}
            },
        }
        _, _, payload = prepare_request(credential(), source, "model", False)
        self.assertEqual({tool["function"]["name"] for tool in payload["tools"]}, {"one", "two"})
        self.assertEqual(payload["tool_choice"], "required")

    def test_unsupported_tools_and_unknown_allowed_names_fail_closed(self):
        for source in [
            {"tools": [{"googleSearch": {}}]},
            {
                "tools": [{"functionDeclarations": [{"name": "one"}]}],
                "toolConfig": {
                    "functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": ["two"]}
                },
            },
        ]:
            with self.assertRaises(HostedProviderError):
                prepare_request(credential(), source, "model", False)

    async def test_regular_catalogs_and_public_catalog_do_not_validate_inference(self):
        for provider in ("kimi", "nvidia", "poolside", "kilo"):

            def handler(request):
                self.assertEqual("GET", request.method)
                self.assertTrue(request.url.path.endswith("/models"))
                return httpx.Response(
                    200, json={"data": [{"id": "a/model"}, {"id": "a/model"}, {"id": "b"}]}
                )

            async with self.transport(handler):
                self.assertEqual(["a/model", "b"], await discover_models(credential(provider)))

    async def test_kimchi_metadata_uses_slug_and_own_user_agent(self):
        def handler(request):
            self.assertEqual("/v1/models/metadata", request.url.path)
            self.assertEqual("true", request.url.params["include_in_cli"])
            self.assertNotIn("kimchi/", request.headers.get("user-agent", ""))
            return httpx.Response(200, json={"models": [{"id": "internal", "slug": "kimi-k3"}]})

        async with self.transport(handler):
            self.assertEqual(["kimi-k3"], await discover_models(credential("kimchi")))

    async def test_cloudflare_discovery_paginated_uses_slug_not_uuid(self):
        pages = []

        def handler(request):
            page = int(request.url.params["page"])
            pages.append(page)
            self.assertEqual("Text Generation", request.url.params["task"])
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": [{"id": "uuid", "name": f"@cf/model-{page}"}],
                    "result_info": {"page": page, "total_pages": 2},
                },
            )

        async with self.transport(handler):
            result = await discover_models(credential("cloudflare", account_id="a" * 32))
        self.assertEqual(["@cf/model-1", "@cf/model-2"], result)
        self.assertEqual([1, 2], pages)

    async def test_cloudflare_repeated_page_fails_instead_of_truncating(self):
        async with self.transport(
            lambda _: httpx.Response(
                200,
                json={
                    "success": True,
                    "result": [{"name": "@cf/a"}],
                    "result_info": {"total_pages": 3},
                },
            )
        ):
            with self.assertRaises(HostedProviderError):
                await discover_models(credential("cloudflare", account_id="a" * 32))

    async def test_cloudflare_full_duplicate_page_does_not_silently_end_pagination(self):
        async with self.transport(
            lambda _: httpx.Response(
                200, json={"success": True, "result": [{"name": "@cf/a"}] * 50}
            )
        ):
            with self.assertRaises(HostedProviderError):
                await discover_models(credential("cloudflare", account_id="a" * 32))

    async def test_cloudflare_malformed_pagination_fails_closed(self):
        for info in ([], "wrong", {"total_pages": True}, {"total_pages": 99}):
            async with self.transport(
                lambda _, info=info: httpx.Response(
                    200, json={"success": True, "result": [{"name": "@cf/a"}], "result_info": info}
                )
            ):
                with self.assertRaises(HostedProviderError):
                    await discover_models(credential("cloudflare", account_id="a" * 32))

    async def test_catalog_errors_are_safe_and_preserve_status(self):
        for status in (301, 401, 403, 429, 500):
            async with self.transport(
                lambda _, status=status: httpx.Response(
                    status,
                    text="synthetic-key-not-a-secret",
                    headers={"location": "https://evil.test/"},
                )
            ):
                with self.assertRaises(HostedProviderError) as caught:
                    await discover_models(credential())
                self.assertNotIn("synthetic-key", str(caught.exception))
                self.assertEqual(
                    status if status in {401, 403, 429} else 502, caught.exception.status_code
                )

    async def test_invalid_and_excessive_catalogs_fail_closed(self):
        for body in (
            [],
            {"data": "wrong"},
            {"data": [{"id": "bad\nmodel"}]},
            {"data": [{"id": str(i)} for i in range(501)]},
            {"data": []},
        ):
            async with self.transport(lambda _, body=body: httpx.Response(200, json=body)):
                with self.assertRaises(HostedProviderError):
                    await discover_models(credential())
        async with self.transport(
            lambda _: httpx.Response(200, content=b"x" * (MAX_CATALOG_BYTES + 1))
        ):
            with self.assertRaises(HostedProviderError):
                await discover_models(credential())

    async def test_network_errors_are_sanitized_and_cancellation_propagates(self):
        for error in (httpx.ConnectError("secret"), asyncio.CancelledError()):

            def handler(_):
                raise error

            async with self.transport(handler):
                with self.assertRaises(
                    asyncio.CancelledError
                    if isinstance(error, asyncio.CancelledError)
                    else HostedProviderError
                ) as caught:
                    await discover_models(credential())
                self.assertNotIn("secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
