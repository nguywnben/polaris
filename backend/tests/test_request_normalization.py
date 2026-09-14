"""Regression tests for provider request normalization."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.api.primary import PrimarySessionState, prepare_provider_request, wrap_cli_request
from core.converter.anthropic_to_gemini import clean_json_schema
from core.converter.gemini_fix import normalize_gemini_request


def request_payload(generation_config):
    return {
        "model": "gemini-2.5-flash",
        "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
        "generationConfig": generation_config,
    }


class RequestNormalizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_nullable_anthropic_schema_preserves_nullability(self):
        normalized = clean_json_schema({"type": ["string", "null"]})

        self.assertEqual(normalized, {"type": "string", "nullable": True})

    async def test_client_output_limit_is_preserved(self):
        normalized = await normalize_gemini_request(
            request_payload({"maxOutputTokens": 256}), mode="primary"
        )

        self.assertEqual(normalized["generationConfig"]["maxOutputTokens"], 256)

    async def test_output_limit_is_not_invented_when_client_omits_it(self):
        normalized = await normalize_gemini_request(
            request_payload({"temperature": 0.2}), mode="primary"
        )

        self.assertNotIn("maxOutputTokens", normalized["generationConfig"])

    async def test_credit_capacity_is_only_enabled_for_opted_in_credentials(self):
        session = PrimarySessionState(
            conversation_id="conversation",
            trajectory_id="trajectory",
            session_id="session",
            step_index=1,
            created_at=1.0,
            last_used_at=1.0,
        )
        with (
            patch(
                "core.api.primary._get_session_state",
                AsyncMock(return_value=session),
            ),
            patch(
                "core.api.primary.get_token_compression_config",
                AsyncMock(
                    return_value={
                        "enabled": True,
                        "threshold_tokens": 32000,
                        "target_tokens": 24000,
                        "min_recent_turns": 4,
                    }
                ),
            ),
            patch(
                "core.api.primary.get_antigravity_payload_user_agent",
                AsyncMock(return_value="antigravity"),
            ),
        ):
            free_payload, _, _ = await wrap_cli_request(
                request_payload({}), "gemini-2.5-flash", "project", enable_credit=False
            )
            credit_payload, _, _ = await wrap_cli_request(
                request_payload({}), "gemini-2.5-flash", "project", enable_credit=True
            )

        self.assertNotIn("enabledCreditTypes", free_payload)
        self.assertEqual(credit_payload["enabledCreditTypes"], ["GOOGLE_ONE_AI"])

    async def test_ai_studio_request_uses_native_payload_and_api_key_header(self):
        credential = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "example-google-key-value",
        }
        body = {
            "model": "gemini-2.5-flash",
            "request": {
                "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
                "sessionId": "internal-session",
                "labels": {"internal": "value"},
            },
        }
        with (
            patch(
                "core.api.primary.get_google_ai_studio_api_url",
                AsyncMock(return_value="https://generativelanguage.googleapis.com"),
            ),
            patch(
                "core.api.primary.get_token_compression_config",
                AsyncMock(
                    return_value={
                        "enabled": True,
                        "threshold_tokens": 32000,
                        "target_tokens": 24000,
                        "min_recent_turns": 4,
                    }
                ),
            ),
        ):
            context = await prepare_provider_request(credential, body, streaming=False)

        self.assertEqual(context.provider_id, "google_ai_studio")
        self.assertEqual(
            context.target_url,
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent",
        )
        self.assertEqual(context.headers["x-goog-api-key"], "example-google-key-value")
        self.assertNotIn("Authorization", context.headers)
        self.assertNotIn("sessionId", context.payload)
        self.assertNotIn("labels", context.payload)
        self.assertEqual(context.payload["contents"], body["request"]["contents"])

    async def test_xai_request_uses_openai_transport_and_bearer_auth(self):
        credential = {
            "provider": "xai",
            "credential_type": "api_key",
            "api_key": "xai-example-key-value",
        }
        body = {
            "model": "grok-4",
            "request": {
                "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
                "generationConfig": {"maxOutputTokens": 256},
            },
        }
        with (
            patch(
                "core.api.primary.get_xai_api_url",
                AsyncMock(return_value="https://api.x.ai/v1"),
            ),
            patch(
                "core.api.primary.get_xai_user_agent",
                AsyncMock(return_value="grok-cli/polaris"),
            ),
            patch(
                "core.api.primary.get_token_compression_config",
                AsyncMock(
                    return_value={
                        "enabled": True,
                        "threshold_tokens": 32000,
                        "target_tokens": 24000,
                        "min_recent_turns": 4,
                    }
                ),
            ),
        ):
            context = await prepare_provider_request(credential, body, streaming=False)

        self.assertEqual(context.provider_id, "xai")
        self.assertEqual(context.target_url, "https://api.x.ai/v1/chat/completions")
        self.assertEqual(context.headers["Authorization"], "Bearer xai-example-key-value")
        self.assertEqual(context.headers["User-Agent"], "grok-cli/polaris")
        self.assertEqual(context.payload["model"], "grok-4")
        self.assertEqual(context.payload["messages"][0]["content"], "Hello")
        self.assertEqual(context.payload["max_tokens"], 256)

    async def test_openai_platform_request_uses_chat_completions_transport(self):
        credential = {
            "provider": "openai",
            "credential_type": "api_key",
            "api_key": "sk-example-key-value",
        }
        body = {
            "model": "gpt-5-mini",
            "request": {
                "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
            },
        }
        with (
            patch(
                "core.api.primary.get_openai_api_url",
                AsyncMock(return_value="https://api.openai.com/v1"),
            ),
            patch(
                "core.api.primary.get_token_compression_config",
                AsyncMock(
                    return_value={
                        "enabled": True,
                        "threshold_tokens": 32000,
                        "target_tokens": 24000,
                        "min_recent_turns": 4,
                    }
                ),
            ),
        ):
            context = await prepare_provider_request(credential, body, streaming=False)

        self.assertEqual(context.provider_id, "openai")
        self.assertEqual(context.target_url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(context.headers["Authorization"], "Bearer sk-example-key-value")
        self.assertEqual(context.payload["model"], "gpt-5-mini")
        self.assertFalse(context.payload["stream"])

    async def test_codex_request_uses_responses_transport_and_identity_headers(self):
        credential = {
            "provider": "openai",
            "credential_type": "oauth",
            "access_token": "codex-access-token",
            "account_id": "account-123",
        }
        body = {
            "model": "gpt-5-codex",
            "request": {
                "sessionId": "session-123",
                "contents": [{"role": "user", "parts": [{"text": "Hello"}]}],
            },
        }
        with (
            patch(
                "core.api.primary.get_codex_api_url",
                AsyncMock(return_value="https://chatgpt.com/backend-api/codex"),
            ),
            patch(
                "core.api.primary.get_codex_user_agent",
                AsyncMock(return_value="codex_cli_rs/test"),
            ),
            patch(
                "core.api.primary.get_token_compression_config",
                AsyncMock(
                    return_value={
                        "enabled": True,
                        "threshold_tokens": 32000,
                        "target_tokens": 24000,
                        "min_recent_turns": 4,
                    }
                ),
            ),
        ):
            context = await prepare_provider_request(credential, body, streaming=False)

        self.assertEqual(context.target_url, "https://chatgpt.com/backend-api/codex/responses")
        self.assertEqual(context.headers["ChatGPT-Account-Id"], "account-123")
        self.assertEqual(context.headers["session_id"], "session-123")
        self.assertEqual(context.headers["User-Agent"], "codex_cli_rs/test")
        self.assertTrue(context.payload["stream"])


if __name__ == "__main__":
    unittest.main()
