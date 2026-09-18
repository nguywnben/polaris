"""Tests for Claude Code and Claude Platform provider contracts."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.anthropic import (
    ANTHROPIC_REDIRECT_URI,
    AnthropicError,
    anthropic_response_to_gemini,
    anthropic_stream_line_to_gemini,
    build_anthropic_headers,
    complete_claude_oauth,
    create_claude_oauth_url,
    fetch_anthropic_model_ids,
    gemini_request_to_anthropic,
    parse_anthropic_model_ids,
)
from core.provider_authorization_coordination import (
    ProviderAuthorizationService,
    configure_provider_authorization_service,
)
from core.state_store import InMemoryStateStore


class AnthropicProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_follows_cursor_and_deduplicates_pages(self):
        pages = [
            httpx.Response(
                200, json={"data": [{"id": "claude-a"}], "has_more": True, "last_id": "claude-a"}
            ),
            httpx.Response(
                200, json={"data": [{"id": "claude-a"}, {"id": "claude-b"}], "has_more": False}
            ),
        ]
        with (
            patch(
                "core.anthropic.get_anthropic_connection",
                AsyncMock(return_value=("https://api.anthropic.com/v1", "")),
            ),
            patch("core.anthropic.get_async", AsyncMock(side_effect=pages)) as request,
        ):
            result = await fetch_anthropic_model_ids({"api_key": "synthetic"})
        self.assertEqual(result, ["claude-a", "claude-b"])
        self.assertEqual(
            parse_qs(urlparse(request.call_args.args[0]).query)["after_id"], ["claude-a"]
        )

    async def test_discovery_rejects_repeated_cursor(self):
        page = httpx.Response(
            200, json={"data": [{"id": "claude-a"}], "has_more": True, "last_id": "claude-a"}
        )
        with (
            patch(
                "core.anthropic.get_anthropic_connection",
                AsyncMock(return_value=("https://api.anthropic.com/v1", "")),
            ),
            patch("core.anthropic.get_async", AsyncMock(return_value=page)),
        ):
            with self.assertRaises(AnthropicError) as caught:
                await fetch_anthropic_model_ids({"api_key": "synthetic"})
        self.assertEqual(caught.exception.status_code, 502)

    def test_model_parser_does_not_invent_ids_for_non_string_values(self):
        self.assertEqual(
            parse_anthropic_model_ids(
                {"data": [{}, {"id": None}, {"id": 123}, {"id": "claude-a"}]}
            ),
            ["claude-a"],
        )

    async def asyncSetUp(self) -> None:
        self.store = InMemoryStateStore()
        self.authorization_key = b"a" * 32
        configure_provider_authorization_service(
            ProviderAuthorizationService(
                self.store,
                key=self.authorization_key,
                fencing_epoch=1,
            )
        )

    async def asyncTearDown(self) -> None:
        configure_provider_authorization_service(None)
        await self.store.close()

    def test_model_parser_is_bounded_and_deduplicated(self):
        payload = {
            "data": [
                {"id": "claude-sonnet-4-6"},
                {"id": "claude-sonnet-4-6"},
                {"id": "invalid\u0000"},
                *({"id": f"claude-test-{index}"} for index in range(600)),
            ]
        }
        models = parse_anthropic_model_ids(payload)
        self.assertEqual(models[0], "claude-sonnet-4-6")
        self.assertEqual(len(models), 500)
        self.assertNotIn("invalid\u0000", models)

    def test_headers_distinguish_oauth_and_api_key_credentials(self):
        oauth = build_anthropic_headers(
            {"credential_type": "oauth", "access_token": "oauth-secret"},
            user_agent="claude-cli/test",
        )
        platform = build_anthropic_headers(
            {"credential_type": "api_key", "api_key": "api-secret"},
            user_agent="polaris/test",
        )
        self.assertEqual(oauth["Authorization"], "Bearer oauth-secret")
        self.assertNotIn("x-api-key", oauth)
        self.assertEqual(platform["x-api-key"], "api-secret")
        self.assertNotIn("Authorization", platform)
        self.assertEqual(oauth["anthropic-version"], "2023-06-01")

    async def test_oauth_authorization_uses_pkce_and_loopback_callback(self):
        with patch(
            "core.anthropic.get_claude_client_id",
            AsyncMock(return_value="public-client-id"),
        ):
            result = await create_claude_oauth_url()
        query = parse_qs(urlparse(result["auth_url"]).query)
        self.assertEqual(result["redirect_uri"], ANTHROPIC_REDIRECT_URI)
        self.assertEqual(query["client_id"], ["public-client-id"])
        self.assertEqual(query["redirect_uri"], [ANTHROPIC_REDIRECT_URI])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["code"], ["true"])
        self.assertEqual(query["state"], [result["state"]])
        self.assertTrue(result["state"].startswith("claude_"))

    async def test_oauth_completion_can_move_to_another_replica(self):
        with patch(
            "core.anthropic.get_claude_client_id",
            AsyncMock(return_value="public-client-id"),
        ):
            authorization = await create_claude_oauth_url()

        configure_provider_authorization_service(
            ProviderAuthorizationService(
                self.store,
                key=self.authorization_key,
                fencing_epoch=1,
            )
        )
        exchange = AsyncMock(
            return_value={
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "expires_in": 3600,
            }
        )
        stored = AsyncMock(return_value={"action": "created", "filename": "claude-account.json"})
        with (
            patch("core.anthropic._exchange_claude_token", exchange),
            patch(
                "core.anthropic.get_claude_oauth_token_url",
                AsyncMock(return_value="https://console.anthropic.com/v1/oauth/token"),
            ),
            patch(
                "core.anthropic.fetch_anthropic_model_ids",
                AsyncMock(return_value=["claude-sonnet-4-6"]),
            ),
            patch("core.anthropic.credential_manager.add_primary_credential", stored),
        ):
            result = await complete_claude_oauth("authorization-code", authorization["state"])

        exchange_payload = exchange.await_args.args[0]
        self.assertEqual(exchange_payload["client_id"], "public-client-id")
        self.assertEqual(len(exchange_payload["code_verifier"]), 128)
        self.assertEqual(result["model_count"], 1)
        self.assertNotIn("access_token", result)

    def test_request_translation_preserves_system_tools_and_generation_options(self):
        payload = gemini_request_to_anthropic(
            {
                "systemInstruction": {"parts": [{"text": "Be concise."}]},
                "contents": [
                    {"role": "user", "parts": [{"text": "Check the build."}]},
                    {
                        "role": "model",
                        "parts": [
                            {
                                "functionCall": {
                                    "id": "call-1",
                                    "name": "run_tests",
                                    "args": {"scope": "unit"},
                                }
                            }
                        ],
                    },
                ],
                "tools": [
                    {
                        "functionDeclarations": [
                            {
                                "name": "run_tests",
                                "description": "Run tests.",
                                "parameters": {"type": "object"},
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "maxOutputTokens": 128,
                    "temperature": 0.2,
                    "stopSequences": ["STOP"],
                },
            },
            "claude-sonnet-4-6",
            streaming=True,
        )
        self.assertEqual(payload["model"], "claude-sonnet-4-6")
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["system"], "Be concise.")
        self.assertEqual(payload["max_tokens"], 128)
        self.assertEqual(payload["tools"][0]["name"], "run_tests")
        self.assertEqual(payload["messages"][1]["content"][0]["type"], "tool_use")

    def test_response_and_stream_translation_preserve_text_tools_and_usage(self):
        response = anthropic_response_to_gemini(
            {
                "model": "claude-sonnet-4-6",
                "content": [
                    {"type": "text", "text": "Done"},
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "run_tests",
                        "input": {"scope": "unit"},
                    },
                ],
                "stop_reason": "tool_use",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 4,
                    "cache_read_input_tokens": 5,
                    "cache_creation_input_tokens": 3,
                },
            }
        )
        stream = anthropic_stream_line_to_gemini(
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Done"}}'
        )
        parts = response["candidates"][0]["content"]["parts"]
        self.assertEqual(parts[0], {"text": "Done"})
        self.assertEqual(parts[1]["functionCall"]["name"], "run_tests")
        self.assertEqual(response["usageMetadata"]["promptTokenCount"], 18)
        self.assertEqual(response["usageMetadata"]["cachedContentTokenCount"], 5)
        self.assertEqual(response["usageMetadata"]["cacheCreationTokenCount"], 3)
        self.assertEqual(response["usageMetadata"]["totalTokenCount"], 22)
        self.assertTrue(stream.startswith("data: "))
        self.assertEqual(
            json.loads(stream.removeprefix("data: ").strip())["candidates"][0]["content"]["parts"][
                0
            ]["text"],
            "Done",
        )

    def test_stream_translation_preserves_split_input_output_and_cache_usage(self):
        message_start = anthropic_stream_line_to_gemini(
            'data: {"type":"message_start","message":{"usage":{'
            '"input_tokens":10,"output_tokens":0,"cache_read_input_tokens":5,'
            '"cache_creation_input_tokens":3}}}'
        )
        message_delta = anthropic_stream_line_to_gemini(
            'data: {"type":"message_delta","usage":{"input_tokens":0,"output_tokens":4}}'
        )

        start_usage = json.loads(message_start.removeprefix("data: ").strip())["usageMetadata"]
        delta_usage = json.loads(message_delta.removeprefix("data: ").strip())["usageMetadata"]
        self.assertEqual(
            start_usage,
            {
                "promptTokenCount": 18,
                "cachedContentTokenCount": 5,
                "cacheCreationTokenCount": 3,
                "totalTokenCount": 18,
            },
        )
        self.assertEqual(
            delta_usage,
            {"candidatesTokenCount": 4, "totalTokenCount": 4},
        )


if __name__ == "__main__":
    unittest.main()
