"""Security contracts for control-panel configuration."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config
from core.configuration_schema import CONFIGURATION_FIELDS, ApplyMode
from core.models import AccessCredentialsUpdateRequest
from core.panel.config_routes import (
    ACCESS_SECRET_KEYS,
    ALLOWED_CONFIG_KEYS,
    POLICY_ONLY_CONFIG_KEYS,
    PROVIDER_SPECIFIC_CONFIG_KEYS,
    RESETTABLE_CONFIG_KEYS,
    RESTART_REQUIRED_CONFIG_KEYS,
    _classify_config_updates,
    _redact_access_secrets,
    update_access_credentials,
)
from core.passwords import is_password_hash, verify_password_value


class FakeStorageAdapter:
    def __init__(self):
        self.values = {}

    async def set_config(self, key, value):
        self.values[key] = value


def build_http_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/config/access",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("localhost", 4283),
        }
    )


class ConfigResponseSecurityTests(unittest.TestCase):
    def test_global_config_contract_excludes_access_and_provider_secrets(self):
        self.assertFalse(ALLOWED_CONFIG_KEYS & ACCESS_SECRET_KEYS)
        self.assertFalse(ALLOWED_CONFIG_KEYS & PROVIDER_SPECIFIC_CONFIG_KEYS)

    def test_settings_ownership_and_apply_modes_are_schema_derived(self):
        by_surface = {
            surface: {
                field.config_key
                for field in CONFIGURATION_FIELDS
                if field.config_key and field.surface == surface
            }
            for surface in ("system", "provider", "quality")
        }
        self.assertEqual(ALLOWED_CONFIG_KEYS, by_surface["system"])
        self.assertEqual(PROVIDER_SPECIFIC_CONFIG_KEYS, by_surface["provider"])
        self.assertEqual(POLICY_ONLY_CONFIG_KEYS, by_surface["quality"])
        self.assertEqual(RESETTABLE_CONFIG_KEYS, by_surface["system"])
        self.assertEqual(
            RESTART_REQUIRED_CONFIG_KEYS,
            {
                field.config_key
                for field in CONFIGURATION_FIELDS
                if field.config_key and field.apply is ApplyMode.RESTART
            },
        )

    def test_redacts_password_values_and_reports_configuration_state(self):
        config = {
            "host": "0.0.0.0",
            "api_password": "api-secret-value",
            "panel_password": "panel-secret-value",
            "password": "legacy-secret-value",
            "code_assist_client_secret": "code-assist-secret-value",
        }

        public_config = _redact_access_secrets(config)

        self.assertEqual(public_config["host"], "0.0.0.0")
        self.assertTrue(public_config["panel_password_configured"])
        self.assertTrue(public_config["code_assist_client_secret_configured"])
        self.assertNotIn("api_password", public_config)
        self.assertNotIn("panel_password", public_config)
        self.assertNotIn("password", public_config)
        self.assertNotIn("code_assist_client_secret", public_config)
        self.assertNotIn("api-secret-value", json.dumps(public_config))
        self.assertNotIn("panel-secret-value", json.dumps(public_config))
        self.assertNotIn("code-assist-secret-value", json.dumps(public_config))

    def test_classifies_listener_and_storage_changes_as_restart_required(self):
        classification = _classify_config_updates(
            {"host", "port", "credentials_dir", "proxy", "retry_429_enabled"}
        )

        self.assertEqual(
            classification["restart_required"],
            ["credentials_dir", "host", "port"],
        )
        self.assertEqual(
            classification["hot_updated"],
            ["proxy", "retry_429_enabled"],
        )


class RuntimePolicyConfigTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cache_patch = patch.object(config, "_config_cache", {})
        self.initialized_patch = patch.object(config, "_config_initialized", True)
        self.cache_patch.start()
        self.initialized_patch.start()
        self.addCleanup(self.initialized_patch.stop)
        self.addCleanup(self.cache_patch.stop)

    async def test_upstream_timeout_is_bounded(self):
        with patch.dict(os.environ, {"UPSTREAM_TIMEOUT_SECONDS": "1"}):
            self.assertEqual(await config.get_upstream_timeout_seconds(), 5.0)

        with patch.dict(os.environ, {"UPSTREAM_TIMEOUT_SECONDS": "120"}):
            self.assertEqual(await config.get_upstream_timeout_seconds(), 120.0)

    async def test_invalid_routing_strategy_falls_back_to_balanced(self):
        with patch.dict(os.environ, {"ROUTING_STRATEGY": "unknown"}):
            policy = await config.get_routing_policy()

        self.assertEqual(policy["strategy"], "balanced")

    async def test_log_retention_settings_are_bounded(self):
        with patch.dict(
            os.environ,
            {
                "LOG_LEVEL": "verbose",
                "LOG_MAX_MB": "0",
                "LOG_BACKUP_COUNT": "99",
            },
        ):
            log_config = await config.get_log_config()

        self.assertEqual(log_config["level"], "info")
        self.assertEqual(log_config["max_mb"], 1)
        self.assertEqual(log_config["backup_count"], 20)


class AccessCredentialUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_an_incorrect_current_password(self):
        request = AccessCredentialsUpdateRequest(
            current_password="incorrect-password",
            panel_password="new-panel-password",
            panel_password_confirm="new-panel-password",
        )

        with (
            patch.dict(os.environ, {"PANEL_PASSWORD": ""}),
            patch(
                "core.panel.config_routes.verify_password",
                new=AsyncMock(return_value=False),
            ),
        ):
            with self.assertRaises(HTTPException) as context:
                await update_access_credentials(
                    request,
                    build_http_request(),
                    token="session",
                )

        self.assertEqual(context.exception.status_code, 401)

    async def test_updates_passwords_without_returning_them(self):
        storage = FakeStorageAdapter()
        session_service = MagicMock()

        async def revoke_before_write():
            self.assertNotIn("panel_password", storage.values)
            return 2

        session_service.revoke_local_owner_sessions = AsyncMock(side_effect=revoke_before_write)
        request = AccessCredentialsUpdateRequest(
            current_password="current-password",
            panel_password="new-panel-password",
            panel_password_confirm="new-panel-password",
        )

        with (
            patch.dict(os.environ, {"PANEL_PASSWORD": ""}),
            patch(
                "core.panel.config_routes.verify_password",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "core.panel.config_routes.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.config_routes.config.reload_config",
                new=AsyncMock(),
            ),
            patch(
                "core.panel.config_routes.create_panel_session_token",
                new=AsyncMock(return_value="replacement-session"),
            ),
            patch(
                "core.panel.config_routes.get_session_service",
                return_value=session_service,
            ),
        ):
            response = await update_access_credentials(
                request,
                build_http_request(),
                token="session",
            )

        body = json.loads(response.body)
        self.assertTrue(is_password_hash(storage.values["panel_password"]))
        self.assertTrue(
            verify_password_value("new-panel-password", storage.values["panel_password"])
        )
        self.assertEqual(body["updated"], ["panel_password"])
        self.assertNotIn("new-panel-password", response.body.decode())
        self.assertIn("panel_session=replacement-session", response.headers["set-cookie"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        session_service.revoke_local_owner_sessions.assert_awaited_once_with()

    async def test_rejects_confirmation_mismatch(self):
        request = AccessCredentialsUpdateRequest(
            current_password="current-password",
            panel_password="new-panel-password",
            panel_password_confirm="different-password",
        )

        with (
            patch.dict(os.environ, {"PANEL_PASSWORD": ""}),
            patch(
                "core.panel.config_routes.verify_password",
                new=AsyncMock(return_value=True),
            ),
        ):
            with self.assertRaises(HTTPException) as context:
                await update_access_credentials(
                    request,
                    build_http_request(),
                    token="session",
                )

        self.assertEqual(context.exception.status_code, 400)

    async def test_concurrent_password_changes_cannot_reuse_one_current_password_proof(self):
        storage = FakeStorageAdapter()
        changed = False

        async def verify_current(_candidate):
            await asyncio.sleep(0.02)
            return not changed

        original_set_config = storage.set_config

        async def set_config(key, value):
            nonlocal changed
            await asyncio.sleep(0.02)
            result = await original_set_config(key, value)
            changed = True
            return result

        storage.set_config = set_config
        session_service = MagicMock()
        session_service.revoke_local_owner_sessions = AsyncMock(return_value=1)
        requests = (
            AccessCredentialsUpdateRequest(
                current_password="current-password",
                panel_password="new-panel-password-a",
                panel_password_confirm="new-panel-password-a",
            ),
            AccessCredentialsUpdateRequest(
                current_password="current-password",
                panel_password="new-panel-password-b",
                panel_password_confirm="new-panel-password-b",
            ),
        )

        with (
            patch.dict(os.environ, {"PANEL_PASSWORD": ""}),
            patch(
                "core.panel.config_routes.verify_password",
                new=AsyncMock(side_effect=verify_current),
            ),
            patch(
                "core.panel.config_routes.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.config_routes.config.reload_config",
                new=AsyncMock(),
            ),
            patch(
                "core.panel.config_routes.create_panel_session_token",
                new=AsyncMock(return_value="replacement-session"),
            ),
            patch(
                "core.panel.config_routes.hash_password",
                side_effect=lambda value: f"hashed:{value}",
            ),
            patch(
                "core.panel.config_routes.get_session_service",
                return_value=session_service,
            ),
        ):
            results = await asyncio.gather(
                *(
                    update_access_credentials(
                        payload,
                        build_http_request(),
                        token="session",
                    )
                    for payload in requests
                ),
                return_exceptions=True,
            )

        successes = [result for result in results if not isinstance(result, Exception)]
        denied = [
            result
            for result in results
            if isinstance(result, HTTPException) and result.status_code == 401
        ]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(denied), 1)
        session_service.revoke_local_owner_sessions.assert_awaited_once_with()
