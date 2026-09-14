"""Tests for Codex and OpenAI Platform provider contracts."""

from __future__ import annotations

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.codex import (
    build_codex_headers,
    codex_response_to_gemini,
    codex_stream_line_to_gemini,
    complete_codex_device_flow,
    create_codex_device_flow,
    fetch_codex_model_ids,
    gemini_request_to_codex,
    parse_codex_model_ids,
)
from core.device_authorization_coordination import (
    DeviceAuthorizationError,
    DeviceAuthorizationService,
    configure_device_authorization_service,
    get_device_authorization_service,
)
from core.openai_platform import (
    fetch_openai_model_ids,
    parse_openai_model_ids,
)
from core.panel.providers.openai import _parse_openai_json
from core.state_store import InMemoryStateStore


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def jwt_with_claims(claims: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


class OpenAIProviderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.store = InMemoryStateStore()
        self.authorization_key = b"o" * 32
        configure_device_authorization_service(
            DeviceAuthorizationService(
                self.store,
                key=self.authorization_key,
                fencing_epoch=1,
            )
        )

    async def asyncTearDown(self) -> None:
        configure_device_authorization_service(None)
        await self.store.close()

    def test_platform_model_parser_is_bounded_and_deduplicated(self):
        payload = {
            "data": [
                {"id": "gpt-5"},
                {"id": "gpt-5"},
                {"id": "invalid\u0000"},
                *({"id": f"model-{index}"} for index in range(600)),
            ]
        }

        models = parse_openai_model_ids(payload)

        self.assertEqual(models[0], "gpt-5")
        self.assertEqual(len(models), 500)
        self.assertNotIn("invalid\u0000", models)

    async def test_platform_model_discovery_uses_bearer_auth(self):
        request = AsyncMock(return_value=FakeResponse(200, {"data": [{"id": "gpt-5"}]}))
        with (
            patch("core.openai_platform.get_async", request),
            patch(
                "core.openai_platform.get_openai_api_url",
                AsyncMock(return_value="https://api.openai.com/v1"),
            ),
        ):
            models = await fetch_openai_model_ids("sk-example-key")

        self.assertEqual(models, ["gpt-5"])
        self.assertEqual(
            request.await_args.kwargs["headers"]["Authorization"],
            "Bearer sk-example-key",
        )
        self.assertEqual(request.await_args.args[0], "https://api.openai.com/v1/models")

    async def test_codex_device_flow_exchanges_tokens_and_extracts_identity(self):
        access_token = jwt_with_claims(
            {
                "email": "user@example.com",
                "exp": 2_000_000_000,
                "https://api.openai.com/auth": {"chatgpt_account_id": "account-123"},
            }
        )
        responses = [
            FakeResponse(
                200,
                {
                    "device_auth_id": "device-auth",
                    "user_code": "ABCD-EFGH",
                    "interval": 5,
                },
            ),
            FakeResponse(
                200,
                {
                    "authorization_code": "authorization-code",
                    "code_challenge": "challenge",
                    "code_verifier": "verifier",
                },
            ),
            FakeResponse(
                200,
                {
                    "access_token": access_token,
                    "refresh_token": "refresh-secret",
                    "id_token": access_token,
                },
            ),
        ]
        with (
            patch("core.codex.post_async", AsyncMock(side_effect=responses)),
            patch(
                "core.codex.get_codex_auth_base",
                AsyncMock(return_value="https://auth.openai.com"),
            ),
            patch(
                "core.codex.get_codex_client_id",
                AsyncMock(return_value="public-client-id"),
            ),
            patch(
                "core.codex.fetch_codex_model_ids",
                AsyncMock(return_value=["gpt-5-codex", "gpt-5.4"]),
            ),
        ):
            started = await create_codex_device_flow()
            configure_device_authorization_service(
                DeviceAuthorizationService(
                    self.store,
                    key=self.authorization_key,
                    fencing_epoch=1,
                )
            )
            completed = await complete_codex_device_flow(started["flow_id"])

        credential = completed["credential"]
        self.assertFalse(completed["pending"])
        self.assertEqual(credential["provider"], "openai")
        self.assertEqual(credential["credential_type"], "oauth")
        self.assertEqual(credential["user_email"], "user@example.com")
        self.assertEqual(credential["account_id"], "account-123")
        self.assertEqual(credential["model_ids"], ["gpt-5-codex", "gpt-5.4"])
        self.assertEqual(completed["model_count"], 2)
        with self.assertRaises(DeviceAuthorizationError):
            await get_device_authorization_service().claim(started["flow_id"], lease_seconds=30)

    def test_codex_model_parser_handles_supported_payload_shapes(self):
        models = parse_codex_model_ids(
            {
                "models": [
                    {"slug": "gpt-5-codex"},
                    {"id": "gpt-5-codex"},
                    {"model": "gpt-5.4"},
                    {"id": "invalid\u0000"},
                ]
            }
        )

        self.assertEqual(models, ["gpt-5-codex", "gpt-5.4"])

    async def test_codex_model_discovery_uses_account_headers(self):
        request = AsyncMock(return_value=FakeResponse(200, {"models": [{"slug": "gpt-5-codex"}]}))
        with (
            patch("core.codex.get_async", request),
            patch(
                "core.codex.get_codex_api_url",
                AsyncMock(return_value="https://chatgpt.com/backend-api/codex"),
            ),
            patch(
                "core.codex.get_codex_user_agent",
                AsyncMock(return_value="codex_cli_rs/test"),
            ),
        ):
            models = await fetch_codex_model_ids("access-secret", "account-123")

        self.assertEqual(models, ["gpt-5-codex"])
        self.assertEqual(
            request.await_args.args[0],
            "https://chatgpt.com/backend-api/codex/models?client_version=1.0.0",
        )
        self.assertEqual(
            request.await_args.kwargs["headers"]["ChatGPT-Account-Id"],
            "account-123",
        )

    def test_codex_import_normalizes_common_camel_case_fields(self):
        candidates = _parse_openai_json(
            json.dumps(
                {
                    "provider": "codex",
                    "accessToken": "access-secret",
                    "refreshToken": "refresh-secret",
                    "accountId": "account-123",
                    "email": "user@example.com",
                    "models": ["gpt-5-codex"],
                }
            ).encode(),
            "codex.json",
            "oauth",
        )

        payload = candidates[0]["payload"]
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["credential_type"], "oauth")
        self.assertEqual(payload["access_token"], "access-secret")
        self.assertEqual(payload["refresh_token"], "refresh-secret")
        self.assertEqual(payload["account_id"], "account-123")
        self.assertEqual(payload["user_email"], "user@example.com")
        self.assertEqual(payload["model_ids"], ["gpt-5-codex"])

    async def test_codex_device_flow_reports_pending_authorization(self):
        with (
            patch(
                "core.codex.post_async",
                AsyncMock(
                    side_effect=[
                        FakeResponse(
                            200,
                            {"device_auth_id": "device-auth", "user_code": "ABCD-EFGH"},
                        ),
                        FakeResponse(403, {"error": "authorization_pending"}),
                    ]
                ),
            ),
            patch(
                "core.codex.get_codex_auth_base",
                AsyncMock(return_value="https://auth.openai.com"),
            ),
            patch(
                "core.codex.get_codex_client_id",
                AsyncMock(return_value="public-client-id"),
            ),
        ):
            started = await create_codex_device_flow()
            result = await complete_codex_device_flow(started["flow_id"])

        self.assertTrue(result["pending"])
        retained = await get_device_authorization_service().claim(
            started["flow_id"], lease_seconds=30
        )
        await get_device_authorization_service().release(retained)

    def test_codex_request_uses_responses_tool_contract_and_forces_streaming(self):
        request = gemini_request_to_codex(
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
            },
            "gpt-5-codex",
            streaming=False,
        )

        self.assertTrue(request["stream"])
        self.assertFalse(request["store"])
        self.assertEqual(request["instructions"], "Be concise.")
        self.assertEqual(request["tools"][0]["name"], "run_tests")
        self.assertNotIn("function", request["tools"][0])
        self.assertEqual(request["input"][1]["type"], "function_call")

    def test_codex_headers_include_account_session_and_configured_user_agent(self):
        headers = build_codex_headers(
            "access-secret",
            "account-123",
            session_id="session-123",
            user_agent="codex_cli_rs/test",
        )

        self.assertEqual(headers["Authorization"], "Bearer access-secret")
        self.assertEqual(headers["ChatGPT-Account-Id"], "account-123")
        self.assertEqual(headers["session_id"], "session-123")
        self.assertEqual(headers["User-Agent"], "codex_cli_rs/test")

    def test_codex_response_and_stream_preserve_text_tools_and_usage(self):
        response = codex_response_to_gemini(
            {
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": "Done"}]},
                    {
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "run_tests",
                        "arguments": '{"scope":"unit"}',
                    },
                ],
                "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
            }
        )
        stream_chunk = codex_stream_line_to_gemini(
            'data: {"type":"response.output_text.delta","delta":"Done"}'
        )

        parts = response["candidates"][0]["content"]["parts"]
        self.assertEqual(parts[0], {"text": "Done"})
        self.assertEqual(parts[1]["functionCall"]["name"], "run_tests")
        self.assertEqual(response["usageMetadata"]["totalTokenCount"], 14)
        self.assertTrue(stream_chunk.startswith("data: "))

    def test_codex_stream_surfaces_model_not_found_as_route_failure(self):
        with self.assertRaisesRegex(Exception, "is unavailable") as context:
            codex_stream_line_to_gemini(
                'data: {"type":"response.failed","response":{"error":'
                '{"code":"model_not_found","message":"The selected model is unavailable."}}}'
            )

        self.assertEqual(context.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
