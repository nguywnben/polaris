"""Tests for the shared Grok and SpaceXAI Console provider contract."""

from __future__ import annotations

import io
import json
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.models import ConfigSaveRequest, XaiCredentialRequest, XaiOAuthCodeRequest
from core.panel.providers.xai import (
    add_xai_api_key_credential,
    import_xai_credentials,
    reset_xai_config,
    save_xai_config,
    save_xai_oauth_credential,
)
from core.provider_authorization_coordination import (
    ProviderAuthorizationService,
    configure_provider_authorization_service,
    get_provider_authorization_service,
)
from core.state_store import InMemoryStateStore
from core.xai import (
    XAI_REDIRECT_URI,
    XaiError,
    XaiValidation,
    _stream_tool_calls,
    complete_xai_oauth,
    create_xai_oauth_url,
    fetch_xai_model_ids,
    fetch_xai_oauth_model_ids,
    gemini_request_to_xai,
    parse_xai_model_ids,
    refresh_xai_oauth_credential,
    xai_response_to_gemini,
    xai_stream_line_to_gemini,
)
from fastapi import UploadFile


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class XaiProviderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.store = InMemoryStateStore()
        self.authorization_key = b"x" * 32
        configure_provider_authorization_service(
            ProviderAuthorizationService(
                self.store,
                key=self.authorization_key,
                fencing_epoch=1,
            )
        )

    async def asyncTearDown(self) -> None:
        configure_provider_authorization_service(None)
        _stream_tool_calls.clear()
        await self.store.close()

    def test_model_parser_normalizes_unique_ids(self):
        self.assertEqual(
            parse_xai_model_ids({"data": [{"id": "grok-4"}, {"id": "grok-4"}, {"id": "grok-3"}]}),
            ["grok-4", "grok-3"],
        )

    def test_model_parser_bounds_and_sanitizes_the_provider_catalog(self):
        payload = {
            "data": [
                {"id": ""},
                {"id": "grok-valid"},
                {"id": "grok-invalid\u0000"},
                {"id": "x" * 257},
                *({"id": f"grok-{index}"} for index in range(600)),
            ]
        }

        model_ids = parse_xai_model_ids(payload)

        self.assertEqual(model_ids[0], "grok-valid")
        self.assertEqual(len(model_ids), 500)
        self.assertNotIn("grok-invalid\u0000", model_ids)

    async def test_model_discovery_uses_bearer_auth_and_user_agent(self):
        request = AsyncMock(return_value=FakeResponse(200, {"data": [{"id": "grok-4"}]}))
        with (
            patch("core.xai.get_async", request),
            patch(
                "core.xai.get_xai_api_url",
                AsyncMock(return_value="https://api.x.ai/v1"),
            ),
            patch(
                "core.xai.get_xai_user_agent",
                AsyncMock(return_value="grok-cli/polaris"),
            ),
        ):
            models = await fetch_xai_model_ids("xai-example-key")

        self.assertEqual(models, ["grok-4"])
        self.assertEqual(
            request.await_args.kwargs["headers"]["Authorization"],
            "Bearer xai-example-key",
        )
        self.assertEqual(
            request.await_args.kwargs["headers"]["User-Agent"],
            "grok-cli/polaris",
        )

    async def test_oauth_model_discovery_uses_grok_build_catalog_and_headers(self):
        request = AsyncMock(return_value=FakeResponse(200, {"models": [{"model": "grok-4"}]}))
        with (
            patch("core.xai.get_async", request),
            patch(
                "core.xai.get_xai_oauth_api_url",
                AsyncMock(return_value="https://cli-chat-proxy.grok.com/v1"),
            ),
            patch(
                "core.xai.get_xai_user_agent",
                AsyncMock(return_value="grok-cli/polaris"),
            ),
        ):
            models = await fetch_xai_oauth_model_ids("grok-oauth-token")

        self.assertEqual(models, ["grok-4"])
        self.assertEqual(
            request.await_args.args[0],
            "https://cli-chat-proxy.grok.com/v1/models-v2",
        )
        self.assertEqual(
            request.await_args.kwargs["headers"]["X-XAI-Token-Auth"],
            "xai-grok-cli",
        )
        self.assertEqual(
            request.await_args.kwargs["headers"]["x-grok-client-identifier"],
            "grok-shell",
        )

    async def test_oauth_authorization_uses_pkce_and_loopback_callback(self):
        with (
            patch(
                "core.xai.discover_xai_oauth_endpoints",
                AsyncMock(
                    return_value={
                        "authorization_endpoint": "https://auth.x.ai/oauth2/authorize",
                        "token_endpoint": "https://auth.x.ai/oauth2/token",
                    }
                ),
            ),
            patch(
                "core.xai.get_xai_client_id",
                AsyncMock(return_value="public-client-id"),
            ),
        ):
            result = await create_xai_oauth_url()

        query = parse_qs(urlparse(result["auth_url"]).query)
        self.assertEqual(result["redirect_uri"], XAI_REDIRECT_URI)
        self.assertEqual(query["client_id"], ["public-client-id"])
        self.assertEqual(query["redirect_uri"], [XAI_REDIRECT_URI])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["state"], [result["state"]])
        self.assertTrue(result["state"].startswith("xai_"))

    async def test_oauth_flow_storage_is_bounded(self):
        await self.store.close()
        self.store = InMemoryStateStore(_oidc_transaction_limit_for_testing=1)
        configure_provider_authorization_service(
            ProviderAuthorizationService(
                self.store,
                key=self.authorization_key,
                fencing_epoch=1,
            )
        )
        with (
            patch(
                "core.xai.discover_xai_oauth_endpoints",
                AsyncMock(
                    return_value={
                        "authorization_endpoint": "https://auth.x.ai/oauth2/authorize",
                        "token_endpoint": "https://auth.x.ai/oauth2/token",
                    }
                ),
            ),
            patch(
                "core.xai.get_xai_client_id",
                AsyncMock(return_value="public-client-id"),
            ),
        ):
            await create_xai_oauth_url()
            with self.assertRaisesRegex(XaiError, "could not be started"):
                await create_xai_oauth_url()

    async def test_refresh_updates_rotating_tokens_and_expiry(self):
        credential = {
            "provider": "xai",
            "credential_type": "oauth",
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "client_id": "public-client-id",
            "token_uri": "https://auth.x.ai/oauth2/token",
        }
        with patch(
            "core.xai._exchange_xai_token",
            AsyncMock(
                return_value={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 900,
                }
            ),
        ):
            refreshed = await refresh_xai_oauth_credential(credential)

        self.assertEqual(refreshed["access_token"], "new-access")
        self.assertEqual(refreshed["token"], "new-access")
        self.assertEqual(refreshed["refresh_token"], "new-refresh")
        self.assertTrue(refreshed["expiry"].endswith("+00:00"))

    async def test_token_exchange_rejects_non_xai_endpoint(self):
        credential = {
            "provider": "xai",
            "credential_type": "oauth",
            "refresh_token": "refresh-token",
            "client_id": "public-client-id",
            "token_uri": "https://example.com/oauth2/token",
        }

        with self.assertRaisesRegex(XaiError, "invalid token endpoint"):
            await refresh_xai_oauth_credential(credential)

    async def test_authorization_code_stores_tokens_but_returns_secret_free_metadata(self):
        verifier = "v" * 128
        state = await get_provider_authorization_service().create(
            "xai",
            json.dumps(
                {
                    "client_id": "public-client-id",
                    "code_verifier": verifier,
                    "schema_version": 1,
                    "token_endpoint": "https://auth.x.ai/oauth2/token",
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii"),
            ttl_seconds=900,
        )
        configure_provider_authorization_service(
            ProviderAuthorizationService(
                self.store,
                key=self.authorization_key,
                fencing_epoch=1,
            )
        )
        stored = AsyncMock(
            return_value={
                "action": "created",
                "filename": "xai-grok-account.json",
            }
        )
        exchange = AsyncMock(
            return_value={
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "id_token": "",
                "expires_in": 3600,
            }
        )
        with (
            patch(
                "core.xai._exchange_xai_token",
                exchange,
            ),
            patch(
                "core.xai.fetch_xai_oauth_model_ids",
                AsyncMock(return_value=["grok-4", "grok-3"]),
            ),
            patch("core.xai.credential_manager.add_primary_credential", stored),
        ):
            result = await complete_xai_oauth("authorization-code", state)

        saved_payload = stored.await_args.args[1]
        self.assertEqual(saved_payload["access_token"], "access-secret")
        self.assertEqual(saved_payload["refresh_token"], "refresh-secret")
        self.assertEqual(
            exchange.await_args.args[0],
            {
                "grant_type": "authorization_code",
                "client_id": "public-client-id",
                "code": "authorization-code",
                "redirect_uri": XAI_REDIRECT_URI,
                "code_verifier": verifier,
            },
        )
        self.assertEqual(result["model_count"], 2)
        self.assertNotIn("access_token", result)
        self.assertNotIn("refresh_token", result)

    async def test_authorization_code_rejects_an_expired_oauth_session(self):
        with self.assertRaisesRegex(XaiError, "not found or has expired"):
            await complete_xai_oauth("authorization-code", "xai_" + "A" * 43)

    async def test_authorization_code_rejects_a_callback_url(self):
        with self.assertRaisesRegex(XaiError, "not a callback URL"):
            await complete_xai_oauth(
                f"{XAI_REDIRECT_URI}?state=state-1&code=authorization-code",
                "state-1",
            )

    async def test_config_save_supports_partial_payload_with_environment_lock(self):
        storage = AsyncMock()
        current = {
            "xai_api_url": "https://api.x.ai/v1",
            "xai_oauth_issuer": "https://auth.x.ai",
            "xai_client_id": "locked-client-id",
            "xai_user_agent": "grok-cli/polaris",
        }
        with (
            patch(
                "core.panel.providers.xai.get_env_locked_keys",
                return_value={"xai_client_id"},
            ),
            patch(
                "core.panel.providers.xai._current_xai_config",
                AsyncMock(side_effect=[current, current]),
            ),
            patch(
                "core.panel.providers.xai.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.providers.xai.config.reload_config",
                AsyncMock(),
            ),
        ):
            response = await save_xai_config(
                ConfigSaveRequest(config={"xai_user_agent": "grok-cli/test"}),
                token="panel-token",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["env_locked"], ["xai_client_id"])
        storage.set_config.assert_awaited_once_with("xai_user_agent", "grok-cli/test")

    async def test_config_reset_is_scoped_to_the_selected_product(self):
        storage = AsyncMock()
        current = {
            "xai_api_url": "https://api.x.ai/v1",
            "xai_oauth_issuer": "https://auth.x.ai",
            "xai_client_id": "client-id",
            "xai_user_agent": "grok-cli/polaris",
        }
        with (
            patch(
                "core.panel.providers.xai.get_env_locked_keys",
                return_value=set(),
            ),
            patch(
                "core.panel.providers.xai._current_xai_config",
                AsyncMock(return_value=current),
            ),
            patch(
                "core.panel.providers.xai.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.providers.xai.config.reload_config",
                AsyncMock(),
            ),
        ):
            response = await reset_xai_config(scope="oauth", token="panel-token")

        payload = json.loads(response.body)
        self.assertEqual(payload["message"], "Grok Build settings reset to defaults.")
        deleted_keys = {call.args[0] for call in storage.delete_config.await_args_list}
        self.assertEqual(deleted_keys, {"xai_client_id", "xai_oauth_issuer"})

    async def test_api_key_route_returns_secret_free_frontend_contract(self):
        with (
            patch(
                "core.panel.providers.xai.validate_xai_api_key",
                AsyncMock(return_value=XaiValidation(model_ids=["grok-4"])),
            ),
            patch(
                "core.panel.providers.xai.store_xai_api_key_credential",
                AsyncMock(
                    return_value={
                        "action": "created",
                        "filename": "xai-grok-fingerprint.json",
                        "label": "API key ending 1234",
                    }
                ),
            ),
        ):
            response = await add_xai_api_key_credential(
                XaiCredentialRequest(api_key="xai-example-secret-1234"),
                token="panel-token",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(payload["provider"], "xai")
        self.assertEqual(payload["model_count"], 1)
        self.assertTrue(payload["credential_saved"])
        self.assertNotIn("api_key", payload)

    async def test_oauth_route_returns_secret_free_frontend_contract(self):
        with patch(
            "core.panel.providers.xai.complete_xai_oauth",
            AsyncMock(
                return_value={
                    "action": "created",
                    "filename": "xai-grok-account.json",
                    "label": "user@example.com",
                    "model_count": 2,
                }
            ),
        ):
            response = await save_xai_oauth_credential(
                XaiOAuthCodeRequest(code="code-1", state="state-1"),
                token="panel-token",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(payload["provider"], "xai")
        self.assertEqual(payload["model_count"], 2)
        self.assertNotIn("access_token", payload)
        self.assertNotIn("refresh_token", payload)

    async def test_import_accepts_xai_json_and_zip_without_returning_secrets(self):
        oauth_payload = {
            "provider": "xai",
            "credential_type": "oauth",
            "refresh_token": "refresh-secret",
            "credential_label": "OAuth account",
        }
        api_key_payload = {
            "provider": "xai",
            "credential_type": "api_key",
            "api_key": "xai-api-key-secret-value",
        }
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as archive:
            archive.writestr("nested/key.json", json.dumps(api_key_payload))

        files = [
            UploadFile(
                filename="oauth.json",
                file=io.BytesIO(json.dumps(oauth_payload).encode("utf-8")),
            ),
            UploadFile(filename="credentials.zip", file=io.BytesIO(archive_buffer.getvalue())),
        ]
        restore = AsyncMock(
            side_effect=[
                {
                    "status": "success",
                    "action": "created",
                    "filename": "xai-grok-oauth.json",
                    "message": "OAuth credential restored.",
                },
                {
                    "status": "success",
                    "action": "created",
                    "filename": "xai-grok-key.json",
                    "message": "API key restored.",
                },
            ]
        )

        with patch("core.panel.providers.xai.restore_xai_credential", restore):
            response = await import_xai_credentials(files=files, token="panel-token")

        payload = json.loads(response.body)
        serialized = json.dumps(payload)
        self.assertEqual(payload["uploaded_count"], 2)
        self.assertEqual(payload["error_count"], 0)
        self.assertEqual(len(payload["results"]), 2)
        self.assertNotIn("refresh-secret", serialized)
        self.assertNotIn("xai-api-key-secret-value", serialized)
        self.assertEqual(restore.await_count, 2)

    async def test_import_rejects_credentials_from_another_provider(self):
        google_payload = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "google-secret-value",
        }
        files = [
            UploadFile(
                filename="wrong-provider.json",
                file=io.BytesIO(json.dumps(google_payload).encode("utf-8")),
            )
        ]

        response = await import_xai_credentials(files=files, token="panel-token")

        payload = json.loads(response.body)
        serialized = json.dumps(payload)
        self.assertEqual(payload["uploaded_count"], 0)
        self.assertEqual(payload["error_count"], 1)
        self.assertIn(
            "does not contain a Grok Build or SpaceXAI Console credential",
            payload["results"][0]["message"],
        )
        self.assertNotIn("google-secret-value", serialized)

    async def test_import_scope_rejects_the_other_xai_credential_type(self):
        api_key_payload = {
            "provider": "xai",
            "credential_type": "api_key",
            "api_key": "xai-api-key-secret-value",
        }
        files = [
            UploadFile(
                filename="api-key.json",
                file=io.BytesIO(json.dumps(api_key_payload).encode("utf-8")),
            )
        ]
        restore = AsyncMock()

        with patch("core.panel.providers.xai.restore_xai_credential", restore):
            response = await import_xai_credentials(
                files=files,
                credential_type="oauth",
                token="panel-token",
            )

        payload = json.loads(response.body)
        serialized = json.dumps(payload)
        self.assertEqual(payload["uploaded_count"], 0)
        self.assertEqual(payload["error_count"], 1)
        self.assertIn("Grok Build OAuth credential", payload["results"][0]["message"])
        self.assertNotIn("xai-api-key-secret-value", serialized)
        restore.assert_not_awaited()

    def test_request_translation_preserves_images_tools_and_generation_config(self):
        payload = {
            "systemInstruction": {"parts": [{"text": "Follow the project rules."}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": "Inspect this image."},
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": "aW1hZ2U=",
                            }
                        },
                    ],
                },
                {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "id": "call-1",
                                "name": "lookup",
                                "args": {"query": "status"},
                            }
                        }
                    ],
                },
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "id": "call-1",
                                "name": "lookup",
                                "response": {"ok": True},
                            }
                        }
                    ],
                },
            ],
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": "lookup",
                            "description": "Look up status.",
                            "parametersJsonSchema": {
                                "type": "object",
                                "properties": {"query": {"type": "string"}},
                            },
                        }
                    ]
                }
            ],
            "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 512,
                "responseMimeType": "application/json",
            },
        }

        translated = gemini_request_to_xai(payload, "grok-4", streaming=True)

        self.assertEqual(translated["model"], "grok-4")
        self.assertTrue(translated["stream"])
        self.assertEqual(translated["messages"][0]["role"], "system")
        image_content = translated["messages"][1]["content"]
        self.assertEqual(
            image_content[1]["image_url"]["url"],
            "data:image/png;base64,aW1hZ2U=",
        )
        self.assertEqual(
            translated["messages"][2]["tool_calls"][0]["function"]["arguments"],
            '{"query": "status"}',
        )
        self.assertEqual(translated["messages"][3]["tool_call_id"], "call-1")
        self.assertEqual(translated["tools"][0]["function"]["name"], "lookup")
        self.assertEqual(translated["tool_choice"], "required")
        self.assertEqual(translated["max_tokens"], 512)
        self.assertEqual(translated["response_format"], {"type": "json_object"})

    def test_response_translation_preserves_reasoning_tools_and_usage(self):
        translated = xai_response_to_gemini(
            {
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": "Checking.",
                            "reasoning_content": "Need a tool.",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "lookup",
                                        "arguments": '{"query":"status"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                    "prompt_tokens_details": {"cached_tokens": 2},
                    "completion_tokens_details": {"reasoning_tokens": 1},
                },
            }
        )

        parts = translated["candidates"][0]["content"]["parts"]
        self.assertEqual(parts[0], {"text": "Need a tool.", "thought": True})
        self.assertEqual(parts[-1]["functionCall"]["id"], "call-1")
        self.assertEqual(translated["usageMetadata"]["cachedContentTokenCount"], 2)
        self.assertEqual(translated["usageMetadata"]["thoughtsTokenCount"], 1)

    def test_stream_translation_reassembles_fragmented_tool_arguments(self):
        first = xai_stream_line_to_gemini(
            'data: {"id":"response-1","choices":[{"index":0,"delta":'
            '{"tool_calls":[{"index":0,"id":"call-1","function":'
            '{"name":"lookup","arguments":"{\\"query\\":"}}]},'
            '"finish_reason":null}]}'
        )
        final = xai_stream_line_to_gemini(
            'data: {"id":"response-1","choices":[{"index":0,"delta":'
            '{"tool_calls":[{"index":0,"function":{"arguments":"\\"status\\"}"}}]},'
            '"finish_reason":"tool_calls"}]}'
        )

        self.assertIsNotNone(first)
        final_payload = json.loads(final.removeprefix("data: "))
        function_call = final_payload["candidates"][0]["content"]["parts"][0]["functionCall"]
        self.assertEqual(function_call["id"], "call-1")
        self.assertEqual(function_call["name"], "lookup")
        self.assertEqual(function_call["args"], {"query": "status"})


if __name__ == "__main__":
    unittest.main()
