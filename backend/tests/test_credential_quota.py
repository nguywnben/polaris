"""Tests for provider-specific credential quota responses."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.anthropic import AnthropicError
from core.codex import CodexError
from core.panel.credentials import get_credential_quota
from core.xai import XaiError


class CredentialQuotaRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_claude_code_oauth_returns_account_rate_limits(self):
        storage = AsyncMock()
        storage.get_credential.return_value = {
            "provider": "anthropic",
            "credential_type": "oauth",
            "access_token": "active-token",
            "refresh_token": "refresh-token",
        }
        usage = {
            "quota_type": "account_rate_limits",
            "plan": "max_20x",
            "windows": [
                {
                    "id": "session",
                    "label": "5-Hour Limit",
                    "used_percentage": 20,
                    "remaining_percentage": 80,
                    "reset_time": "2033-05-18T03:33:20+00:00",
                }
            ],
        }

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credentials.fetch_anthropic_oauth_usage",
                AsyncMock(return_value=usage),
            ) as fetch,
        ):
            response = await get_credential_quota(
                "claude-code-account.json",
                token="panel-token",
                mode="provider",
            )

        payload = json.loads(response.body)
        self.assertTrue(payload["supported"])
        self.assertEqual(payload["provider"], "anthropic")
        self.assertEqual(payload["provider_variant"], "claude_code")
        self.assertEqual(payload["windows"][0]["remaining_percentage"], 80)
        self.assertNotIn("access_token", payload)
        fetch.assert_awaited_once_with("active-token")

    async def test_expired_claude_code_token_is_refreshed_once_before_quota_retry(self):
        storage = AsyncMock()
        storage.get_credential.return_value = {
            "provider": "anthropic",
            "credential_type": "oauth",
            "access_token": "expired-token",
            "refresh_token": "refresh-token",
        }
        refreshed = {
            **storage.get_credential.return_value,
            "access_token": "fresh-token",
            "token": "fresh-token",
        }
        usage = AsyncMock(
            side_effect=[
                AnthropicError("Claude rejected this OAuth credential.", 401),
                {
                    "quota_type": "account_rate_limits",
                    "plan": "max",
                    "windows": [
                        {
                            "id": "weekly",
                            "label": "7-Day All Models",
                            "used_percentage": 40,
                            "remaining_percentage": 60,
                            "reset_time": None,
                        }
                    ],
                },
            ]
        )

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch("core.panel.credentials.fetch_anthropic_oauth_usage", usage),
            patch(
                "core.panel.credentials.refresh_claude_oauth_credential",
                AsyncMock(return_value=refreshed),
            ) as refresh,
        ):
            response = await get_credential_quota(
                "claude-code-account.json",
                token="panel-token",
                mode="provider",
            )

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(
            [call.args[0] for call in usage.await_args_list],
            ["expired-token", "fresh-token"],
        )
        refresh.assert_awaited_once()
        storage.store_credential.assert_awaited_once_with(
            "claude-code-account.json",
            refreshed,
            mode="primary",
        )

    async def test_codex_oauth_returns_account_rate_limits(self):
        storage = AsyncMock()
        storage.get_credential.return_value = {
            "provider": "openai",
            "credential_type": "oauth",
            "access_token": "active-token",
            "refresh_token": "refresh-token",
            "account_id": "account-123",
        }
        usage = {
            "quota_type": "account_rate_limits",
            "plan": "plus",
            "limit_reached": False,
            "review_limit_reached": False,
            "reset_credits": {"available_count": 1},
            "windows": [
                {
                    "id": "session",
                    "label": "5-Hour Limit",
                    "used_percentage": 20,
                    "remaining_percentage": 80,
                    "reset_time": "2033-05-18T03:33:20+00:00",
                }
            ],
        }

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credentials.fetch_codex_usage",
                AsyncMock(return_value=usage),
            ) as fetch,
        ):
            response = await get_credential_quota(
                "codex-account.json",
                token="panel-token",
                mode="provider",
            )

        payload = json.loads(response.body)
        self.assertTrue(payload["supported"])
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["quota_type"], "account_rate_limits")
        self.assertEqual(payload["windows"][0]["remaining_percentage"], 80)
        self.assertNotIn("access_token", payload)
        fetch.assert_awaited_once_with("active-token", "account-123")

    async def test_openai_platform_api_key_rejects_unsupported_quota_operation(self):
        storage = AsyncMock()
        storage.get_credential.return_value = {
            "provider": "openai",
            "credential_type": "api_key",
            "api_key": "sk-secret",
        }

        with patch(
            "core.panel.credentials.get_storage_adapter",
            AsyncMock(return_value=storage),
        ):
            response = await get_credential_quota(
                "openai-platform-key.json",
                token="panel-token",
                mode="provider",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(payload["error"]["code"], "credential_operation_unsupported")
        self.assertEqual(payload["error"]["operation"], "quota")
        self.assertNotIn("api_key", payload)

    async def test_expired_codex_token_is_refreshed_once_before_quota_retry(self):
        storage = AsyncMock()
        storage.get_credential.return_value = {
            "provider": "openai",
            "credential_type": "oauth",
            "access_token": "expired-token",
            "refresh_token": "refresh-token",
            "account_id": "account-old",
        }
        refreshed = {
            **storage.get_credential.return_value,
            "access_token": "fresh-token",
            "account_id": "account-new",
        }
        usage = AsyncMock(
            side_effect=[
                CodexError("Codex rejected this OAuth credential.", 401),
                {
                    "quota_type": "account_rate_limits",
                    "plan": "plus",
                    "limit_reached": False,
                    "review_limit_reached": False,
                    "reset_credits": {"available_count": 0},
                    "windows": [
                        {
                            "id": "session",
                            "label": "Session Limit",
                            "used_percentage": 10,
                            "remaining_percentage": 90,
                            "reset_time": None,
                        }
                    ],
                },
            ]
        )

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch("core.panel.credentials.fetch_codex_usage", usage),
            patch(
                "core.panel.credentials.refresh_codex_oauth_credential",
                AsyncMock(return_value=refreshed),
            ) as refresh,
        ):
            response = await get_credential_quota(
                "codex-account.json",
                token="panel-token",
                mode="provider",
            )

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(
            [call.args for call in usage.await_args_list],
            [("expired-token", "account-old"), ("fresh-token", "account-new")],
        )
        refresh.assert_awaited_once()
        storage.store_credential.assert_awaited_once_with(
            "codex-account.json",
            refreshed,
            mode="primary",
        )

    async def test_grok_build_oauth_returns_account_billing_quota(self):
        storage = AsyncMock()
        storage.get_credential.return_value = {
            "provider": "xai",
            "credential_type": "oauth",
            "access_token": "active-token",
            "refresh_token": "refresh-token",
        }
        billing = {
            "quota_type": "account_billing",
            "monthly": {
                "limit": 4000,
                "used": 1000,
                "remaining": 3000,
                "used_percentage": 25,
                "remaining_percentage": 75,
                "reset_time": "2026-08-01T00:00:00+00:00",
            },
            "weekly": None,
        }

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credentials.fetch_xai_billing_usage",
                AsyncMock(return_value=billing),
            ),
        ):
            response = await get_credential_quota(
                "grok-account.json",
                token="panel-token",
                mode="provider",
            )

        payload = json.loads(response.body)
        self.assertEqual(payload["provider"], "xai")
        self.assertEqual(payload["quota_type"], "account_billing")
        self.assertEqual(payload["monthly"]["remaining"], 3000)
        self.assertNotIn("access_token", payload)

    async def test_xai_console_api_key_rejects_unsupported_quota_operation(self):
        storage = AsyncMock()
        storage.get_credential.return_value = {
            "provider": "xai",
            "credential_type": "api_key",
            "api_key": "xai-secret",
        }

        with patch(
            "core.panel.credentials.get_storage_adapter",
            AsyncMock(return_value=storage),
        ):
            response = await get_credential_quota(
                "xai-console-key.json",
                token="panel-token",
                mode="provider",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(payload["error"]["code"], "credential_operation_unsupported")
        self.assertEqual(payload["error"]["operation"], "quota")
        self.assertNotIn("api_key", payload)

    async def test_expired_grok_build_token_is_refreshed_once_before_retry(self):
        storage = AsyncMock()
        storage.get_credential.return_value = {
            "provider": "xai",
            "credential_type": "oauth",
            "access_token": "expired-token",
            "refresh_token": "refresh-token",
        }
        refreshed = {
            **storage.get_credential.return_value,
            "access_token": "fresh-token",
            "token": "fresh-token",
        }
        billing = AsyncMock(
            side_effect=[
                XaiError("Grok Build rejected this OAuth credential.", 401),
                {
                    "quota_type": "account_billing",
                    "monthly": {
                        "limit": 4000,
                        "used": 1000,
                        "remaining": 3000,
                        "used_percentage": 25,
                        "remaining_percentage": 75,
                        "reset_time": "2026-08-01T00:00:00+00:00",
                    },
                    "weekly": None,
                },
            ]
        )
        refresh = AsyncMock(return_value=refreshed)

        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch("core.panel.credentials.fetch_xai_billing_usage", billing),
            patch("core.panel.credentials.refresh_xai_oauth_credential", refresh),
        ):
            response = await get_credential_quota(
                "grok-account.json",
                token="panel-token",
                mode="provider",
            )

        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(
            [call.args[0] for call in billing.await_args_list], ["expired-token", "fresh-token"]
        )
        refresh.assert_awaited_once()
        storage.store_credential.assert_awaited_once_with(
            "grok-account.json",
            refreshed,
            mode="primary",
        )


if __name__ == "__main__":
    unittest.main()
