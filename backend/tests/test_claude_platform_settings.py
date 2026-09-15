"""Claude Platform configuration must not borrow or mutate Claude Code settings."""

import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from core import anthropic
from core.api import primary
from core.models import ConfigSaveRequest
from core.panel.providers import anthropic as routes
from fastapi import HTTPException


class ClaudePlatformSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_reset_and_environment_lock_are_platform_only(self):
        values = {
            "claude_platform_api_url": "https://platform.example/v1",
            "claude_platform_user_agent": "polaris/platform-test",
        }
        storage = SimpleNamespace(set_config=AsyncMock(), delete_config=AsyncMock())
        with (
            patch.object(routes, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(routes, "get_env_locked_keys", return_value=set()),
            patch.object(routes, "_current_anthropic_config", AsyncMock(return_value=values)),
            patch.object(config, "reload_config", AsyncMock()),
        ):
            await routes.save_anthropic_config(ConfigSaveRequest(config=values), token="test")
            self.assertEqual(dict(call.args for call in storage.set_config.await_args_list), values)
            await routes.reset_anthropic_config(scope="platform", token="test")
            self.assertEqual(
                {call.args[0] for call in storage.delete_config.await_args_list}, set(values)
            )
            storage.set_config.reset_mock()
            storage.delete_config.reset_mock()
            with patch.object(routes, "get_env_locked_keys", return_value=set(values)):
                await routes.save_anthropic_config(ConfigSaveRequest(config=values), token="test")
                await routes.reset_anthropic_config(scope="platform", token="test")
            storage.set_config.assert_not_awaited()
            storage.delete_config.assert_not_awaited()

    async def test_platform_rejects_invalid_endpoint_and_header_before_writing(self):
        storage = SimpleNamespace(set_config=AsyncMock())
        with (
            patch.object(routes, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(routes, "get_env_locked_keys", return_value=set()),
        ):
            for key, value in (
                ("claude_platform_api_url", "javascript:alert(1)"),
                ("claude_platform_api_url", "https://user:password@example.com/v1"),
                ("claude_platform_user_agent", "agent\r\nInjected: value"),
                ("claude_platform_user_agent", ""),
            ):
                with self.subTest(key=key, value=value), self.assertRaises(HTTPException):
                    await routes.save_anthropic_config(
                        ConfigSaveRequest(config={key: value}), token="test"
                    )
            storage.set_config.assert_not_awaited()

    async def test_private_getters_do_not_read_legacy_keys(self):
        lookup = AsyncMock(side_effect=lambda key, default, env: default)
        with patch.object(config, "get_config_value", lookup):
            self.assertEqual(
                await config.get_claude_platform_api_url(), "https://api.anthropic.com/v1"
            )
            self.assertEqual(
                await config.get_claude_platform_user_agent(), "polaris/claude-platform"
            )
        self.assertEqual(
            [call.args[0] for call in lookup.await_args_list],
            ["claude_platform_api_url", "claude_platform_user_agent"],
        )
        self.assertEqual(config.ENV_MAPPINGS["CLAUDE_PLATFORM_API_URL"], "claude_platform_api_url")
        self.assertEqual(
            config.ENV_MAPPINGS["CLAUDE_PLATFORM_USER_AGENT"], "claude_platform_user_agent"
        )

    async def test_discovery_and_inference_select_the_same_private_connection(self):
        with ExitStack() as stack:
            for name, value in (
                ("get_anthropic_api_url", "https://code.example/v1"),
                ("get_claude_user_agent", "code-agent"),
                ("get_claude_platform_api_url", "https://platform.example/v1"),
                ("get_claude_platform_user_agent", "platform-agent"),
            ):
                stack.enter_context(patch.object(anthropic, name, AsyncMock(return_value=value)))
            stack.enter_context(
                patch.object(
                    primary,
                    "get_token_compression_config",
                    AsyncMock(return_value={"enabled": False}),
                )
            )
            for kind, host, agent in (
                ("oauth", "code", "code-agent"),
                ("api_key", "platform", "platform-agent"),
            ):
                credential = {
                    "provider": "anthropic",
                    "credential_type": kind,
                    "api_key": "fake-key",
                    "access_token": "fake-token",
                }
                request = AsyncMock(
                    return_value=httpx.Response(200, json={"data": [{"id": "claude-test"}]})
                )
                with patch.object(anthropic, "get_async", request):
                    self.assertEqual(
                        await anthropic.fetch_anthropic_model_ids(credential), ["claude-test"]
                    )
                self.assertEqual(request.call_args.args[0], f"https://{host}.example/v1/models")
                self.assertEqual(request.call_args.kwargs["headers"]["User-Agent"], agent)
                for streaming in (False, True):
                    result = await primary.prepare_provider_request(
                        credential,
                        {
                            "model": "claude-test",
                            "contents": [{"role": "user", "parts": [{"text": "test"}]}],
                        },
                        streaming=streaming,
                        extra_headers={"User-Agent": "must-not-override"},
                    )
                    self.assertEqual(result.target_url, f"https://{host}.example/v1/messages")
                    self.assertEqual(result.headers["User-Agent"], agent)
                    self.assertEqual("x-api-key" in result.headers, kind == "api_key")


if __name__ == "__main__":
    unittest.main()
