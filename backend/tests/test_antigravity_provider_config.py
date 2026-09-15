"""Security and response-contract tests for Antigravity provider settings."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import ManagementPermission, management_route_manifest
from core.models import ConfigSaveRequest
from core.panel.providers.antigravity import (
    ANTIGRAVITY_CONFIG_KEYS,
    GOOGLE_COMPATIBILITY_CONFIG_KEYS,
    GOOGLE_CONFIG_KEYS,
    GOOGLE_SHARED_CONFIG_KEYS,
    get_antigravity_config,
    redact_antigravity_config,
    redact_google_config,
    reset_google_config,
    save_antigravity_config,
    save_google_config,
)
from fastapi import HTTPException


class AntigravityProviderConfigTests(unittest.TestCase):
    def test_secret_is_replaced_by_configured_state(self):
        payload = redact_antigravity_config(
            {
                "antigravity_client_id": "public-client",
                "antigravity_client_secret": "never-return-this-secret",
                "antigravity_api_url": "https://example.test",
            }
        )

        self.assertEqual(payload["config"]["antigravity_client_secret"], "")
        self.assertEqual(payload["configured_secrets"], ["antigravity_client_secret"])
        self.assertNotIn("never-return-this-secret", repr(payload))

    def test_empty_secret_does_not_claim_to_be_configured(self):
        payload = redact_antigravity_config({"antigravity_client_secret": ""})

        self.assertEqual(payload["configured_secrets"], [])


class AntigravityProviderConfigRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_route_never_reflects_the_stored_secret(self):
        with (
            patch(
                "core.panel.providers.antigravity._current_antigravity_config",
                new=AsyncMock(
                    return_value={
                        "antigravity_client_id": "public-client",
                        "antigravity_client_secret": "route-secret",
                    }
                ),
            ),
            patch(
                "core.panel.providers.antigravity.get_env_locked_keys",
                return_value={"antigravity_client_secret"},
            ),
        ):
            response = await get_antigravity_config(token="session")

        payload = json.loads(response.body)
        self.assertEqual(payload["config"]["antigravity_client_secret"], "")
        self.assertEqual(payload["configured_secrets"], ["antigravity_client_secret"])
        self.assertEqual(payload["env_locked"], ["antigravity_client_secret"])
        self.assertNotIn("route-secret", response.body.decode("utf-8"))

    async def test_antigravity_route_rejects_shared_and_global_settings(self):
        self.assertEqual(
            ANTIGRAVITY_CONFIG_KEYS,
            {
                "antigravity_client_id",
                "antigravity_client_secret",
                "antigravity_api_url",
                "antigravity_user_agent",
                "antigravity_payload_user_agent",
            },
        )
        storage = AsyncMock()
        with patch(
            "core.panel.providers.antigravity.get_storage_adapter",
            new=AsyncMock(return_value=storage),
        ):
            with self.assertRaisesRegex(Exception, "Unsupported Google Antigravity setting"):
                await save_antigravity_config(
                    ConfigSaveRequest(config={"stream_to_nonstream": True}), token="session"
                )
        storage.set_config.assert_not_awaited()

    async def test_antigravity_validates_all_fields_before_any_write(self):
        storage = AsyncMock()
        with (
            patch(
                "core.panel.providers.antigravity.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch("core.panel.providers.antigravity.get_env_locked_keys", return_value=set()),
        ):
            with self.assertRaisesRegex(Exception, "must use HTTP or HTTPS"):
                await save_antigravity_config(
                    ConfigSaveRequest(
                        config={
                            "antigravity_client_id": "valid-client",
                            "antigravity_api_url": "file:///etc/passwd",
                        }
                    ),
                    token="session",
                )
        storage.set_config.assert_not_awaited()

    async def test_blank_antigravity_secret_preserves_stored_value(self):
        storage = AsyncMock()
        with (
            patch(
                "core.panel.providers.antigravity.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch("core.panel.providers.antigravity.get_env_locked_keys", return_value=set()),
            patch("core.panel.providers.antigravity.config.reload_config", new=AsyncMock()),
        ):
            await save_antigravity_config(
                ConfigSaveRequest(
                    config={
                        "antigravity_client_id": "client",
                        "antigravity_client_secret": "   ",
                    }
                ),
                token="session",
            )

        storage.set_config.assert_awaited_once_with("antigravity_client_id", "client")


class GoogleProviderConfigRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_google_config_routes_have_explicit_management_permissions(self):
        permissions = {
            (entry.method, entry.path): entry.permission for entry in management_route_manifest()
        }
        self.assertIs(
            permissions[("GET", "/api/providers/google/config")],
            ManagementPermission.PROVIDERS_READ,
        )
        self.assertIs(
            permissions[("POST", "/api/providers/google/config")],
            ManagementPermission.PROVIDERS_MANAGE,
        )
        self.assertIs(
            permissions[("POST", "/api/providers/google/config/reset")],
            ManagementPermission.PROVIDERS_MANAGE,
        )

    def test_google_route_has_shared_and_legacy_compatibility_keys_only(self):
        self.assertEqual(
            GOOGLE_CONFIG_KEYS,
            {
                "oauth_url",
                "google_apis_url",
                "resource_manager_url",
                "service_usage_url",
                "code_assist_client_id",
                "code_assist_client_secret",
                "code_assist_endpoint",
            },
        )

    def test_google_secret_is_redacted(self):
        payload = redact_google_config(
            {
                "code_assist_client_id": "public-client",
                "code_assist_client_secret": "never-return-this-secret",
            }
        )

        self.assertEqual(payload["config"]["code_assist_client_secret"], "")
        self.assertEqual(payload["configured_secrets"], ["code_assist_client_secret"])
        self.assertNotIn("never-return-this-secret", repr(payload))

    async def test_google_route_validates_every_endpoint_before_any_write(self):
        storage = AsyncMock()
        with (
            patch(
                "core.panel.providers.antigravity.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch("core.panel.providers.antigravity.get_env_locked_keys", return_value=set()),
        ):
            with self.assertRaisesRegex(Exception, "trusted Google HTTPS origin"):
                await save_google_config(
                    ConfigSaveRequest(
                        config={
                            "code_assist_client_id": "valid-client",
                            "oauth_url": "https://oauth2.googleapis.com.attacker.test",
                        }
                    ),
                    token="session",
                )
        storage.set_config.assert_not_awaited()

    async def test_blank_google_secret_preserves_stored_value(self):
        storage = AsyncMock()
        with (
            patch(
                "core.panel.providers.antigravity.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch("core.panel.providers.antigravity.get_env_locked_keys", return_value=set()),
            patch("core.panel.providers.antigravity.config.reload_config", new=AsyncMock()),
        ):
            await save_google_config(
                ConfigSaveRequest(
                    config={
                        "code_assist_client_id": "client",
                        "code_assist_client_secret": "",
                    }
                ),
                token="session",
            )

        storage.set_config.assert_awaited_once_with("code_assist_client_id", "client")

    async def test_google_save_and_reset_respect_environment_locks(self):
        storage = AsyncMock()
        storage.delete_config.return_value = True
        effective = {
            "oauth_url": "https://oauth2.googleapis.com",
            "google_apis_url": "https://www.googleapis.com",
            "resource_manager_url": "https://cloudresourcemanager.googleapis.com",
            "service_usage_url": "https://serviceusage.googleapis.com",
            "code_assist_client_id": "environment-client",
            "code_assist_client_secret": "environment-secret",
            "code_assist_endpoint": "https://cloudcode-pa.googleapis.com",
        }
        with (
            patch(
                "core.panel.providers.antigravity.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.providers.antigravity.get_env_locked_keys",
                return_value={"code_assist_client_id"},
            ),
            patch("core.panel.providers.antigravity.config.reload_config", new=AsyncMock()),
            patch(
                "core.panel.providers.antigravity._current_google_config",
                new=AsyncMock(return_value=effective),
            ),
        ):
            response = await save_google_config(
                ConfigSaveRequest(
                    config={
                        "code_assist_client_id": "attempted-override",
                        "code_assist_endpoint": "https://proxy.test/google",
                    }
                ),
                token="session",
            )
            reset_response = await reset_google_config(scope="compatibility", token="session")

        storage.set_config.assert_awaited_once_with(
            "code_assist_endpoint", "https://proxy.test/google"
        )
        deleted = {call.args[0] for call in storage.delete_config.await_args_list}
        self.assertEqual(deleted, GOOGLE_COMPATIBILITY_CONFIG_KEYS - {"code_assist_client_id"})
        self.assertEqual(json.loads(response.body)["env_locked"], ["code_assist_client_id"])
        reset_payload = json.loads(reset_response.body)
        self.assertEqual(reset_payload["env_locked"], ["code_assist_client_id"])
        self.assertNotIn("environment-secret", reset_response.body.decode("utf-8"))

    async def test_shared_reset_does_not_delete_compatibility_settings(self):
        storage = AsyncMock()
        storage.delete_config.return_value = True
        with (
            patch(
                "core.panel.providers.antigravity.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch("core.panel.providers.antigravity.get_env_locked_keys", return_value=set()),
            patch("core.panel.providers.antigravity.config.reload_config", new=AsyncMock()),
            patch(
                "core.panel.providers.antigravity._current_google_config",
                new=AsyncMock(return_value={}),
            ),
        ):
            await reset_google_config(scope="shared", token="session")

        deleted = {call.args[0] for call in storage.delete_config.await_args_list}
        self.assertEqual(deleted, GOOGLE_SHARED_CONFIG_KEYS)
        self.assertTrue(deleted.isdisjoint(GOOGLE_COMPATIBILITY_CONFIG_KEYS))

    async def test_google_reset_rejects_unknown_scope_before_storage_access(self):
        get_storage = AsyncMock()
        with patch(
            "core.panel.providers.antigravity.get_storage_adapter", new=get_storage
        ):
            with self.assertRaises(HTTPException) as raised:
                await reset_google_config(scope="all", token="session")

        self.assertEqual(raised.exception.status_code, 400)
        get_storage.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
