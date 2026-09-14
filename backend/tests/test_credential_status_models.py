"""Credential status contracts for public provider model metadata."""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.codex import CodexError
from core.model_pool import ModelCatalogEntry
from core.models import CredentialModelTestRequest
from core.panel.credential_operations import get_creds_status_common, verify_credential_common
from core.panel.credentials import get_credential_models, test_credential


class FakeCredentialBackend:
    async def get_credentials_summary(self, **_kwargs):
        return {
            "items": [
                {
                    "filename": "google-ai-studio-example.json",
                    "user_email": None,
                    "disabled": False,
                    "error_codes": [],
                    "last_success": None,
                    "model_cooldowns": {},
                    "tier": "pro",
                }
            ],
            "total": 1,
            "stats": {"total": 1, "normal": 1, "disabled": 0},
        }


class FakeCredentialStorage:
    def __init__(self):
        self._backend = FakeCredentialBackend()

    async def get_backend_info(self):
        return {"backend_type": "sqlite"}

    async def get_credential(self, _filename, mode="primary"):
        self.requested_mode = mode
        return {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "must-not-be-exposed",
            "model_ids": [
                "models/gemini-2.5-flash",
                "gemini-2.5-pro",
                "gemini-2.5-flash",
            ],
        }

    async def update_credential_state(self, filename, state, mode="primary"):
        self.updated_state = (filename, state, mode)


class FakeUpstreamResponse:
    status_code = 200
    text = '{"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}'


class FakeAntigravityStorage(FakeCredentialStorage):
    def __init__(self, *, expired: bool = False):
        super().__init__()
        self.expired = expired

    async def get_credential(self, _filename, mode="primary"):
        self.requested_mode = mode
        return {
            "provider": "google_antigravity",
            "credential_type": "oauth",
            "token": "example-access-token",
            "refresh_token": "example-refresh-token",
            "client_id": "example-client-id",
            "client_secret": "example-client-secret",
            "project_id": "example-project",
            "user_email": "developer@example.com",
            "expiry": "2000-01-01T00:00:00+00:00" if self.expired else "2099-01-01T00:00:00+00:00",
        }

    async def store_credential(self, filename, data, mode="primary"):
        self.stored_credential = (filename, dict(data), mode)


class FakeProviderStorage(FakeCredentialStorage):
    def __init__(self, credential_data):
        super().__init__()
        self.credential_data = credential_data

    async def get_credential(self, _filename, mode="primary"):
        self.requested_mode = mode
        return dict(self.credential_data)

    async def store_credential(self, filename, data, mode="primary"):
        self.stored_credential = (filename, dict(data), mode)


class CredentialStatusModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_exposes_model_count_without_repeating_the_catalog(self):
        storage = FakeCredentialStorage()

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.deduplicate_credentials_by_account_email",
                AsyncMock(return_value={"deleted_count": 0}),
            ),
        ):
            response = await get_creds_status_common(
                offset=0,
                limit=50,
                status_filter="all",
                mode="primary",
            )

        payload = json.loads(response.body)
        credential = payload["items"][0]
        self.assertEqual(credential["model_count"], 2)
        self.assertNotIn("model_ids", credential)
        self.assertNotIn("api_key", credential)

    async def test_model_endpoint_returns_normalized_catalog_without_secrets(self):
        storage = FakeCredentialStorage()

        with patch(
            "core.panel.credentials.get_storage_adapter",
            AsyncMock(return_value=storage),
        ):
            response = await get_credential_models(
                "google-ai-studio-example.json",
                token="test-session",
                mode="primary",
            )

        payload = json.loads(response.body)
        self.assertEqual(payload["model_count"], 2)
        self.assertEqual(
            payload["model_ids"],
            ["gemini-2.5-flash", "gemini-2.5-pro"],
        )
        self.assertNotIn("api_key", payload)

    async def test_credential_test_uses_the_explicitly_selected_model(self):
        storage = FakeCredentialStorage()

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credentials.get_google_ai_studio_api_url",
                AsyncMock(return_value="https://generativelanguage.googleapis.com"),
            ),
            patch(
                "core.httpx_client.post_async",
                AsyncMock(return_value=FakeUpstreamResponse()),
            ) as post_mock,
        ):
            response = await test_credential(
                "google-ai-studio-example.json",
                request=CredentialModelTestRequest(model="gemini-2.5-pro"),
                mode="primary",
                _token="test-session",
            )

        payload = json.loads(response.body)
        self.assertEqual(payload["model"], "gemini-2.5-pro")
        self.assertEqual(payload["provider"], "google_ai_studio")
        self.assertEqual(payload["credential_type"], "api_key")
        self.assertEqual(payload["message"], "Model test completed successfully.")
        self.assertIn("gemini-2.5-pro:generateContent", post_mock.await_args.kwargs["url"])

    async def test_codex_model_test_uses_the_openai_provider_transport(self):
        storage = FakeProviderStorage(
            {
                "provider": "openai",
                "credential_type": "oauth",
                "access_token": "codex-access-token",
                "refresh_token": "codex-refresh-token",
                "account_id": "account-123",
                "model_ids": ["gpt-5.4"],
            }
        )
        provider_context = SimpleNamespace(
            headers={"Authorization": "Bearer codex-access-token"},
            payload={"model": "gpt-5.4"},
            target_url="https://chatgpt.com/backend-api/codex/responses",
        )

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.api.primary.prepare_provider_request",
                AsyncMock(return_value=provider_context),
            ) as prepare_request,
            patch(
                "core.httpx_client.post_async",
                AsyncMock(return_value=FakeUpstreamResponse()),
            ) as post_request,
        ):
            response = await test_credential(
                "openai-codex-example.json",
                request=CredentialModelTestRequest(model="gpt-5.4"),
                mode="primary",
                _token="test-session",
            )

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["credential_type"], "oauth")
        self.assertEqual(payload["model"], "gpt-5.4")
        prepare_request.assert_awaited_once()
        self.assertEqual(post_request.await_args.kwargs["url"], provider_context.target_url)

    async def test_openai_platform_model_test_uses_the_openai_provider_transport(self):
        storage = FakeProviderStorage(
            {
                "provider": "openai",
                "credential_type": "api_key",
                "api_key": "sk-platform-example-key",
                "model_ids": ["gpt-4.1"],
            }
        )
        provider_context = SimpleNamespace(
            headers={"Authorization": "Bearer sk-platform-example-key"},
            payload={"model": "gpt-4.1"},
            target_url="https://api.openai.com/v1/chat/completions",
        )

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.api.primary.prepare_provider_request",
                AsyncMock(return_value=provider_context),
            ) as prepare_request,
            patch(
                "core.httpx_client.post_async",
                AsyncMock(return_value=FakeUpstreamResponse()),
            ) as post_request,
        ):
            response = await test_credential(
                "openai-platform-example.json",
                request=CredentialModelTestRequest(model="gpt-4.1"),
                mode="primary",
                _token="test-session",
            )

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["credential_type"], "api_key")
        self.assertEqual(payload["model"], "gpt-4.1")
        prepare_request.assert_awaited_once()
        self.assertEqual(post_request.await_args.kwargs["url"], provider_context.target_url)

    async def test_codex_model_test_refreshes_and_retries_once_after_unauthorized(self):
        storage = FakeProviderStorage(
            {
                "provider": "openai",
                "credential_type": "oauth",
                "access_token": "expired-access-token",
                "refresh_token": "codex-refresh-token",
                "account_id": "account-123",
                "model_ids": ["gpt-5.4"],
            }
        )
        refreshed_credential = {
            **storage.credential_data,
            "access_token": "refreshed-access-token",
        }
        stale_context = SimpleNamespace(
            headers={"Authorization": "Bearer expired-access-token"},
            payload={"model": "gpt-5.4"},
            target_url="https://chatgpt.com/backend-api/codex/responses",
        )
        refreshed_context = SimpleNamespace(
            headers={"Authorization": "Bearer refreshed-access-token"},
            payload={"model": "gpt-5.4"},
            target_url="https://chatgpt.com/backend-api/codex/responses",
        )
        unauthorized_response = SimpleNamespace(status_code=401, text='{"error":"expired"}')

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.api.primary.prepare_provider_request",
                AsyncMock(side_effect=[stale_context, refreshed_context]),
            ) as prepare_request,
            patch(
                "core.httpx_client.post_async",
                AsyncMock(side_effect=[unauthorized_response, FakeUpstreamResponse()]),
            ) as post_request,
            patch(
                "core.panel.credentials.refresh_codex_oauth_credential",
                AsyncMock(return_value=refreshed_credential),
            ) as refresh_credential,
        ):
            response = await test_credential(
                "openai-codex-example.json",
                request=CredentialModelTestRequest(model="gpt-5.4"),
                mode="primary",
                _token="test-session",
            )

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        refresh_credential.assert_awaited_once()
        self.assertEqual(prepare_request.await_count, 2)
        self.assertEqual(post_request.await_count, 2)
        self.assertEqual(storage.stored_credential[1]["access_token"], "refreshed-access-token")

    async def test_xai_console_model_test_does_not_enter_an_oauth_refresh_flow(self):
        storage = FakeProviderStorage(
            {
                "provider": "xai",
                "credential_type": "api_key",
                "api_key": "xai-platform-example-key",
                "model_ids": ["grok-4"],
            }
        )
        provider_context = SimpleNamespace(
            headers={"Authorization": "Bearer xai-platform-example-key"},
            payload={"model": "grok-4"},
            target_url="https://api.x.ai/v1/chat/completions",
        )

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.api.primary.prepare_provider_request",
                AsyncMock(return_value=provider_context),
            ),
            patch(
                "core.httpx_client.post_async",
                AsyncMock(return_value=FakeUpstreamResponse()),
            ),
            patch(
                "core.panel.credentials.refresh_xai_oauth_credential",
                new_callable=AsyncMock,
            ) as refresh_credential,
        ):
            response = await test_credential(
                "xai-console-example.json",
                request=CredentialModelTestRequest(model="grok-4"),
                mode="primary",
                _token="test-session",
            )

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["provider"], "xai")
        self.assertEqual(payload["credential_type"], "api_key")
        refresh_credential.assert_not_awaited()

    async def test_grok_build_model_test_refreshes_its_oauth_credential(self):
        storage = FakeProviderStorage(
            {
                "provider": "xai",
                "credential_type": "oauth",
                "access_token": "grok-access-token",
                "refresh_token": "grok-refresh-token",
                "model_ids": ["grok-4"],
            }
        )
        refreshed_credential = {
            **storage.credential_data,
            "access_token": "refreshed-grok-access-token",
        }
        provider_context = SimpleNamespace(
            headers={"Authorization": "Bearer refreshed-grok-access-token"},
            payload={"model": "grok-4"},
            target_url="https://api.x.ai/v1/chat/completions",
        )

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.api.primary.prepare_provider_request",
                AsyncMock(return_value=provider_context),
            ),
            patch(
                "core.httpx_client.post_async",
                AsyncMock(return_value=FakeUpstreamResponse()),
            ),
            patch(
                "core.panel.credentials.refresh_xai_oauth_credential",
                AsyncMock(return_value=refreshed_credential),
            ) as refresh_credential,
        ):
            response = await test_credential(
                "grok-build-example.json",
                request=CredentialModelTestRequest(model="grok-4"),
                mode="primary",
                _token="test-session",
            )

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["provider"], "xai")
        self.assertEqual(payload["credential_type"], "oauth")
        refresh_credential.assert_awaited_once()
        self.assertEqual(
            storage.stored_credential[1]["access_token"], "refreshed-grok-access-token"
        )

    async def test_model_endpoint_uses_provider_catalog_when_models_are_not_stored(self):
        storage = FakeAntigravityStorage()
        catalog = [
            ModelCatalogEntry("claude-sonnet-4-6", ("google_antigravity",)),
            ModelCatalogEntry("gemini-3-flash-preview", ("google_antigravity",)),
            ModelCatalogEntry("gemini-2.5-pro", ("google_ai_studio",)),
        ]

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credentials.model_catalog_service.get_catalog",
                AsyncMock(return_value=catalog),
            ),
        ):
            response = await get_credential_models(
                "google-antigravity-example.json",
                token="test-session",
                mode="primary",
            )

        payload = json.loads(response.body)
        self.assertEqual(
            payload["model_ids"],
            ["claude-sonnet-4-6", "gemini-3-flash-preview"],
        )

    async def test_credential_test_rejects_a_model_outside_its_catalog(self):
        storage = FakeCredentialStorage()

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch("core.httpx_client.post_async", new_callable=AsyncMock) as post_mock,
        ):
            response = await test_credential(
                "google-ai-studio-example.json",
                request=CredentialModelTestRequest(model="gemini-3-flash-preview"),
                mode="primary",
                _token="test-session",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["diagnostic"]["category"], "invalid_model")
        self.assertEqual(payload["diagnostic"]["code"], "provider_connection_invalid_model")
        post_mock.assert_not_awaited()

    async def test_provider_failure_retains_safe_status_without_upstream_body(self):
        storage = FakeCredentialStorage()
        secret = "sk-secret-that-must-not-leak"
        upstream = SimpleNamespace(
            status_code=403,
            text=json.dumps(
                {
                    "error": {
                        "code": "permission_error",
                        "message": f"Authorization: Bearer {secret}",
                    }
                }
            ),
        )

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credentials.get_google_ai_studio_api_url",
                AsyncMock(return_value="https://generativelanguage.googleapis.com"),
            ),
            patch("core.httpx_client.post_async", AsyncMock(return_value=upstream)),
        ):
            response = await test_credential(
                "google-ai-studio-example.json",
                request=CredentialModelTestRequest(model="gemini-2.5-pro"),
                mode="primary",
                _token="test-session",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["diagnostic"]["category"], "permission")
        self.assertEqual(payload["diagnostic"]["provider_status"], 403)
        self.assertEqual(payload["diagnostic"]["provider_code"], "permission_error")
        self.assertNotIn(secret, response.body.decode())
        self.assertEqual(
            storage.updated_state[1]["error_messages"]["403"],
            payload["diagnostic"]["message"],
        )

    async def test_rate_limit_is_a_successful_connection_with_typed_remediation(self):
        storage = FakeCredentialStorage()
        upstream = SimpleNamespace(
            status_code=429,
            text='{"error":{"code":"rate_limit_exceeded","message":"raw"}}',
        )

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credentials.get_google_ai_studio_api_url",
                AsyncMock(return_value="https://generativelanguage.googleapis.com"),
            ),
            patch("core.httpx_client.post_async", AsyncMock(return_value=upstream)),
        ):
            response = await test_credential(
                "google-ai-studio-example.json",
                request=CredentialModelTestRequest(model="gemini-2.5-pro"),
                mode="primary",
                _token="test-session",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["diagnostic"]["category"], "rate_limit")
        self.assertTrue(payload["diagnostic"]["retryable"])
        self.assertTrue(payload["diagnostic"]["remediation"])
        self.assertEqual(payload["message"], payload["diagnostic"]["message"])

    async def test_complete_connection_test_has_one_hard_timeout(self):
        storage = FakeCredentialStorage()

        async def blocked_request(*_args, **_kwargs):
            await asyncio.Event().wait()

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credentials.get_google_ai_studio_api_url",
                AsyncMock(return_value="https://generativelanguage.googleapis.com"),
            ),
            patch("core.httpx_client.post_async", blocked_request),
            patch("core.panel.credentials.CONNECTION_TEST_TIMEOUT_SECONDS", 0.001),
        ):
            response = await test_credential(
                "google-ai-studio-example.json",
                request=CredentialModelTestRequest(model="gemini-2.5-pro"),
                mode="primary",
                _token="test-session",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 504)
        self.assertEqual(payload["diagnostic"]["category"], "timeout")

    async def test_client_disconnect_cancels_the_complete_connection_test(self):
        cancelled = asyncio.Event()

        async def blocked_storage():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        http_request = SimpleNamespace(is_disconnected=AsyncMock(return_value=True))
        with patch("core.panel.credentials.get_storage_adapter", blocked_storage):
            response = await test_credential(
                "google-ai-studio-example.json",
                request=CredentialModelTestRequest(model="gemini-2.5-pro"),
                mode="primary",
                _token="test-session",
                http_request=http_request,
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 499)
        self.assertEqual(payload["diagnostic"]["category"], "cancelled")
        self.assertTrue(cancelled.is_set())

    async def test_antigravity_verification_persists_the_credential_model_catalog(self):
        storage = FakeAntigravityStorage()

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.get_antigravity_api_url",
                AsyncMock(return_value="https://provider.example"),
            ),
            patch(
                "core.panel.credential_operations.get_antigravity_user_agent",
                AsyncMock(return_value="test-agent"),
            ),
            patch(
                "core.panel.credential_operations.fetch_project_id_and_tier",
                AsyncMock(return_value=("example-project", "pro", None)),
            ),
            patch(
                "core.panel.credential_operations.fetch_antigravity_model_ids",
                AsyncMock(return_value=["claude-sonnet-4-6", "gemini-3-flash-preview"]),
            ),
        ):
            response = await verify_credential_common(
                "google-antigravity-example.json", mode="primary"
            )

        payload = json.loads(response.body)
        stored = storage.stored_credential[1]
        self.assertEqual(payload["model_count"], 2)
        self.assertEqual(
            stored["model_ids"],
            ["claude-sonnet-4-6", "gemini-3-flash-preview"],
        )
        self.assertEqual(stored["user_email"], "developer@example.com")

    async def test_antigravity_token_refresh_preserves_credential_metadata(self):
        storage = FakeAntigravityStorage(expired=True)

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.Credentials.refresh_if_needed",
                AsyncMock(return_value=True),
            ),
            patch(
                "core.panel.credential_operations.get_antigravity_api_url",
                AsyncMock(return_value="https://provider.example"),
            ),
            patch(
                "core.panel.credential_operations.get_antigravity_user_agent",
                AsyncMock(return_value="test-agent"),
            ),
            patch(
                "core.panel.credential_operations.fetch_project_id_and_tier",
                AsyncMock(return_value=("example-project", "pro", None)),
            ),
            patch(
                "core.panel.credential_operations.fetch_antigravity_model_ids",
                AsyncMock(return_value=["gemini-3-flash-preview"]),
            ),
        ):
            await verify_credential_common("google-antigravity-example.json", mode="primary")

        stored = storage.stored_credential[1]
        self.assertEqual(stored["provider"], "google_antigravity")
        self.assertEqual(stored["credential_type"], "oauth")
        self.assertEqual(stored["user_email"], "developer@example.com")

    async def test_google_ai_studio_verification_uses_api_key_validation(self):
        storage = FakeProviderStorage(
            {
                "provider": "google_ai_studio",
                "credential_type": "api_key",
                "api_key": "google-ai-studio-example-key",
            }
        )
        validation = SimpleNamespace(
            model_ids=["gemini-2.5-flash", "gemini-2.5-pro"],
            model_count=2,
        )

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.validate_api_key",
                AsyncMock(return_value=validation),
            ) as validate_credential,
        ):
            response = await verify_credential_common(
                "google-ai-studio-example.json", mode="primary"
            )

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["provider"], "google_ai_studio")
        self.assertEqual(payload["credential_type"], "api_key")
        validate_credential.assert_awaited_once_with("google-ai-studio-example-key")

    async def test_xai_console_verification_does_not_refresh_oauth(self):
        storage = FakeProviderStorage(
            {
                "provider": "xai",
                "credential_type": "api_key",
                "api_key": "xai-platform-example-key",
            }
        )

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.fetch_xai_model_ids",
                AsyncMock(return_value=["grok-4"]),
            ) as fetch_models,
            patch(
                "core.panel.credential_operations.refresh_xai_oauth_credential",
                new_callable=AsyncMock,
            ) as refresh_credential,
        ):
            response = await verify_credential_common("xai-console-example.json", mode="primary")

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["credential_type"], "api_key")
        fetch_models.assert_awaited_once_with("xai-platform-example-key")
        refresh_credential.assert_not_awaited()

    async def test_grok_build_verification_refreshes_oauth_before_model_discovery(self):
        storage = FakeProviderStorage(
            {
                "provider": "xai",
                "credential_type": "oauth",
                "access_token": "grok-access-token",
                "refresh_token": "grok-refresh-token",
            }
        )
        refreshed_credential = {
            **storage.credential_data,
            "access_token": "refreshed-grok-access-token",
        }

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.refresh_xai_oauth_credential",
                AsyncMock(return_value=refreshed_credential),
            ) as refresh_credential,
            patch(
                "core.panel.credential_operations.fetch_xai_oauth_model_ids",
                AsyncMock(return_value=["grok-4"]),
            ) as fetch_models,
        ):
            response = await verify_credential_common("grok-build-example.json", mode="primary")

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["credential_type"], "oauth")
        refresh_credential.assert_awaited_once()
        fetch_models.assert_awaited_once_with("refreshed-grok-access-token")

    async def test_codex_verification_uses_the_codex_model_catalog(self):
        storage = FakeProviderStorage(
            {
                "provider": "openai",
                "credential_type": "oauth",
                "access_token": "codex-access-token",
                "refresh_token": "codex-refresh-token",
                "account_id": "account-123",
                "user_email": "developer@example.com",
            }
        )

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.fetch_codex_model_ids",
                AsyncMock(return_value=["gpt-5.4", "gpt-5.3-codex"]),
            ) as fetch_models,
        ):
            response = await verify_credential_common("openai-codex-example.json", mode="primary")

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["credential_type"], "oauth")
        self.assertEqual(payload["model_count"], 2)
        self.assertIn("Codex", payload["message"])
        fetch_models.assert_awaited_once_with("codex-access-token", "account-123")
        self.assertEqual(
            storage.stored_credential[1]["model_ids"],
            ["gpt-5.4", "gpt-5.3-codex"],
        )
        self.assertEqual(
            storage.updated_state[1],
            {"error_codes": [], "error_messages": {}},
        )
        self.assertIn("enabled state was preserved", payload["message"].lower())

    async def test_codex_verification_refreshes_an_expired_access_token_once(self):
        storage = FakeProviderStorage(
            {
                "provider": "openai",
                "credential_type": "oauth",
                "access_token": "expired-access-token",
                "refresh_token": "codex-refresh-token",
                "account_id": "account-123",
            }
        )
        refreshed_credential = {
            **storage.credential_data,
            "access_token": "refreshed-access-token",
        }

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.fetch_codex_model_ids",
                AsyncMock(
                    side_effect=[
                        CodexError("Codex access token expired.", 401),
                        ["gpt-5.4"],
                    ]
                ),
            ) as fetch_models,
            patch(
                "core.panel.credential_operations.refresh_codex_oauth_credential",
                AsyncMock(return_value=refreshed_credential),
            ) as refresh_credential,
        ):
            response = await verify_credential_common("openai-codex-example.json", mode="primary")

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        refresh_credential.assert_awaited_once()
        self.assertEqual(fetch_models.await_count, 2)
        self.assertEqual(
            fetch_models.await_args_list[1].args,
            ("refreshed-access-token", "account-123"),
        )

    async def test_openai_platform_verification_uses_the_platform_model_catalog(self):
        storage = FakeProviderStorage(
            {
                "provider": "openai",
                "credential_type": "api_key",
                "api_key": "sk-platform-example-key",
            }
        )

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.fetch_openai_model_ids",
                AsyncMock(return_value=["gpt-4.1", "gpt-5"]),
            ) as fetch_models,
        ):
            response = await verify_credential_common(
                "openai-platform-example.json", mode="primary"
            )

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["credential_type"], "api_key")
        self.assertEqual(payload["model_count"], 2)
        self.assertIn("OpenAI Platform", payload["message"])
        fetch_models.assert_awaited_once_with("sk-platform-example-key")
        self.assertEqual(storage.stored_credential[1]["model_ids"], ["gpt-4.1", "gpt-5"])

    async def test_claude_code_verification_preserves_disabled_state(self):
        credential = {
            "provider": "anthropic",
            "credential_type": "oauth",
            "access_token": "claude-access-token",
            "refresh_token": "claude-refresh-token",
            "disabled": True,
        }
        storage = FakeProviderStorage(credential)

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.credential_manager.prepare_credential",
                AsyncMock(return_value=dict(credential)),
            ) as prepare,
            patch(
                "core.panel.credential_operations.fetch_anthropic_model_ids",
                AsyncMock(return_value=["claude-sonnet-4-6"]),
            ) as fetch_models,
        ):
            response = await verify_credential_common("claude-code-example.json", mode="primary")

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["credential_type"], "oauth")
        self.assertTrue(storage.stored_credential[1]["disabled"])
        self.assertNotIn("disabled", storage.updated_state[1])
        prepare.assert_awaited_once()
        fetch_models.assert_awaited_once()

    async def test_claude_platform_verification_preserves_disabled_state(self):
        credential = {
            "provider": "anthropic",
            "credential_type": "api_key",
            "api_key": "sk-ant-example-key",
            "disabled": True,
        }
        storage = FakeProviderStorage(credential)

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.fetch_anthropic_model_ids",
                AsyncMock(return_value=["claude-opus-4-1"]),
            ) as fetch_models,
        ):
            response = await verify_credential_common(
                "claude-platform-example.json", mode="primary"
            )

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["credential_type"], "api_key")
        self.assertTrue(storage.stored_credential[1]["disabled"])
        self.assertNotIn("disabled", storage.updated_state[1])
        fetch_models.assert_awaited_once()
        verified_credential = fetch_models.await_args.args[0]
        self.assertEqual(verified_credential["api_key"], "sk-ant-example-key")

    async def test_ollama_verification_preserves_disabled_state(self):
        storage = FakeProviderStorage(
            {
                "provider": "ollama",
                "credential_type": "connection",
                "base_url": "http://host.docker.internal:11434",
                "api_key": "optional-secret",
                "disabled": True,
            }
        )

        with (
            patch(
                "core.panel.credential_operations.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credential_operations.fetch_ollama_model_ids",
                AsyncMock(return_value=["qwen3.5"]),
            ) as fetch_models,
        ):
            response = await verify_credential_common("ollama-example.json", mode="primary")

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["credential_type"], "connection")
        self.assertTrue(storage.stored_credential[1]["disabled"])
        self.assertNotIn("disabled", storage.updated_state[1])
        fetch_models.assert_awaited_once_with(
            "http://host.docker.internal:11434", "optional-secret"
        )


if __name__ == "__main__":
    unittest.main()
