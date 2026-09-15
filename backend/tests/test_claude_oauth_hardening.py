"""Offline regressions for Claude token failures and provider setting boundaries."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.anthropic import AnthropicError, _exchange_claude_token, normalize_claude_oauth_url
from core.credential_manager import CredentialManager
from core.models import ConfigSaveRequest
from core.panel.providers import anthropic as routes
from fastapi import FastAPI, HTTPException

TOKEN_URL = "https://api.anthropic.com/v1/oauth/token"
CURRENT_CONFIG = {
    "anthropic_api_url": "https://api.anthropic.com/v1",
    "claude_oauth_authorize_url": "https://claude.ai/oauth/authorize",
    "claude_oauth_token_url": TOKEN_URL,
    "claude_client_id": "public-client",
    "claude_user_agent": "claude-cli/test",
}


class ClaudeOAuthHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_exchange_preserves_transient_and_permanent_status_without_upstream_secrets(self):
        for status in (400, 401, 403, 429, 500, 502, 503, 504, 529):
            with (
                self.subTest(status=status),
                patch(
                    "core.anthropic.post_async",
                    AsyncMock(return_value=httpx.Response(status, text="upstream-secret")),
                ),
            ):
                with self.assertRaises(AnthropicError) as raised:
                    await _exchange_claude_token({"refresh_token": "test-refresh"}, TOKEN_URL)
                self.assertEqual(raised.exception.status_code, status)
                self.assertNotIn("upstream-secret", str(raised.exception))
                self.assertEqual(
                    CredentialManager()._is_permanent_refresh_failure(
                        str(raised.exception), raised.exception.status_code
                    ),
                    status in (400, 401, 403),
                )

    async def test_unexpected_http_status_is_transient_gateway_failure(self):
        for status in (302, 404, 408):
            with (
                self.subTest(status=status),
                patch("core.anthropic.post_async", AsyncMock(return_value=httpx.Response(status))),
            ):
                with self.assertRaises(AnthropicError) as raised:
                    await _exchange_claude_token({}, TOKEN_URL)
                self.assertEqual(raised.exception.status_code, 502)

    async def test_transient_refresh_does_not_disable_stored_account(self):
        manager = CredentialManager()
        manager._initialized = True
        manager._storage_adapter = SimpleNamespace(
            store_credential=AsyncMock(), _backend=SimpleNamespace(record_failure=AsyncMock())
        )
        manager.update_credential_state = AsyncMock()
        with patch("core.anthropic.post_async", AsyncMock(return_value=httpx.Response(503))):
            result = await manager._refresh_token(
                {
                    "provider": "anthropic",
                    "credential_type": "oauth",
                    "refresh_token": "test-refresh",
                    "token_uri": TOKEN_URL,
                    "client_id": "public-client",
                },
                "claude-test.json",
                mode="primary",
            )
        self.assertIsNone(result)
        manager.update_credential_state.assert_not_awaited()

    def test_runtime_accepts_only_reviewed_official_https_hosts(self):
        for host in (
            "claude.ai",
            "api.anthropic.com",
            "console.anthropic.com",
            "platform.claude.com",
        ):
            with self.subTest(host=host):
                url = f"https://{host}/v1/oauth/token"
                self.assertEqual(normalize_claude_oauth_url(url, "Token endpoint"), url)

    async def test_unsafe_endpoint_is_rejected_before_any_exchange(self):
        urls = (
            "https://attacker.anthropic.com/token",
            "https://claude.ai.attacker.test/token",
            "https://user:secret@api.anthropic.com/token",
            "https://api.anthropic.com:444/token",
            "https://api.anthropic.com/token?secret=value",
            "https://api.anthropic.com/token#secret",
            "http://api.anthropic.com/token",
            "https://api.anthropic.com/to\nken",
            "https://api.anthropic.com/token?",
            "https://api.anthropic.com/token#",
        )
        for url in urls:
            with (
                self.subTest(url=url),
                patch(
                    "core.anthropic.post_async",
                    AsyncMock(
                        return_value=httpx.Response(200, json={"access_token": "test-access"})
                    ),
                ) as post,
            ):
                with self.assertRaises(ValueError):
                    await _exchange_claude_token({}, url)
                post.assert_not_awaited()


class ClaudeSettingsHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = SimpleNamespace(set_config=AsyncMock(), delete_config=AsyncMock())
        for name, value in (
            ("_current_anthropic_config", AsyncMock(return_value=dict(CURRENT_CONFIG))),
            ("get_storage_adapter", AsyncMock(return_value=self.storage)),
            ("get_env_locked_keys", lambda: set()),
        ):
            patcher = patch.object(routes, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(routes.config, "reload_config", AsyncMock())
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_save_and_runtime_have_identical_url_policy(self):
        for key in ("claude_oauth_authorize_url", "claude_oauth_token_url"):
            for url in (
                "https://evil.test/token",
                "https://sub.claude.ai/token",
                "https://api.anthropic.com/token?secret=value",
            ):
                with self.subTest(key=key, url=url):
                    with self.assertRaises(HTTPException) as raised:
                        await routes.save_anthropic_config(
                            ConfigSaveRequest(config={key: url}), token="test"
                        )
                    self.assertEqual(raised.exception.status_code, 400)
        self.storage.set_config.assert_not_awaited()
        url = "https://platform.claude.com/v1/oauth/token"
        await routes.save_anthropic_config(
            ConfigSaveRequest(config={"claude_oauth_token_url": url}), token="test"
        )
        self.storage.set_config.assert_awaited_once_with("claude_oauth_token_url", url)

    async def test_shared_save_is_not_blocked_by_unrelated_invalid_oauth_config(self):
        with patch.object(
            routes,
            "_current_anthropic_config",
            AsyncMock(return_value={**CURRENT_CONFIG, "claude_oauth_token_url": "invalid"}),
        ):
            await routes.save_anthropic_config(
                ConfigSaveRequest(config={"claude_user_agent": "test/shared"}), token="test"
            )
        self.storage.set_config.assert_awaited_once_with("claude_user_agent", "test/shared")

    async def test_reset_scope_ownership_is_disjoint_and_locks_are_preserved(self):
        scopes = {
            "shared": {"anthropic_api_url", "claude_user_agent"},
            "code": {"claude_oauth_authorize_url", "claude_oauth_token_url", "claude_client_id"},
            "platform": set(),
        }
        for scope, keys in scopes.items():
            with self.subTest(scope=scope):
                self.storage.delete_config.reset_mock()
                await routes.reset_anthropic_config(scope=scope, token="test")
                self.assertEqual(
                    {call.args[0] for call in self.storage.delete_config.await_args_list}, keys
                )
        self.storage.delete_config.reset_mock()
        with patch.object(routes, "get_env_locked_keys", return_value={"anthropic_api_url"}):
            await routes.reset_anthropic_config(scope="shared", token="test")
        self.storage.delete_config.assert_awaited_once_with("claude_user_agent")

    async def test_locked_values_and_unknown_settings_never_write(self):
        with patch.object(routes, "get_env_locked_keys", return_value={"claude_oauth_token_url"}):
            await routes.save_anthropic_config(
                ConfigSaveRequest(config={"claude_oauth_token_url": "https://evil.test/token"}),
                token="test",
            )
        with self.assertRaises(HTTPException):
            await routes.save_anthropic_config(
                ConfigSaveRequest(config={"unrelated": "value"}), token="test"
            )
        self.storage.set_config.assert_not_awaited()

    async def test_settings_routes_retain_authorization_dependency(self):
        app = FastAPI()
        app.include_router(routes.router)

        async def deny():
            raise HTTPException(status_code=401, detail="Authentication required")

        app.dependency_overrides[routes.verify_panel_token] = deny
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for path in (
                "/api/providers/anthropic/config",
                "/api/providers/anthropic/config/reset",
            ):
                response = await client.post(path, json={"config": {"claude_user_agent": "test"}})
                self.assertEqual(response.status_code, 401)
        self.storage.set_config.assert_not_awaited()
        self.storage.delete_config.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
