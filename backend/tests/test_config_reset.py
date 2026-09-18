"""Scoped Settings reset preserves routing ownership and legacy reset clients."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel import config_routes
from core.utils import verify_panel_token


class ResetStorage:
    def __init__(self):
        self.values = {
            "routing_strategy": "priority",
            "preferred_provider": "codex",
            "retry_429_enabled": False,
            "port": 9999,
            "panel_password": "fixture-password-hash",
            "api_key": "fixture-api-key",
        }

    async def delete_config(self, key):
        if key not in self.values:
            return False
        del self.values[key]
        return True


class ConfigResetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = ResetStorage()
        for target, replacement in (
            ("get_storage_adapter", AsyncMock(return_value=self.storage)),
            ("get_env_locked_keys", lambda: {"port"}),
            ("config.reload_config", AsyncMock()),
            (
                "config.get_log_config",
                AsyncMock(
                    return_value={
                        "level": "info",
                        "max_mb": 10,
                        "backup_count": 2,
                    }
                ),
            ),
            ("keep_alive_service.restart", AsyncMock()),
            ("configure_logging", lambda *_args: None),
        ):
            patcher = patch(f"core.panel.config_routes.{target}", replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        app = FastAPI()
        app.include_router(config_routes.router)
        app.dependency_overrides[verify_panel_token] = lambda: "fixture-session"
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )
        self.addAsyncCleanup(self.client.aclose)

    def assert_protected_values_preserved(self, payload):
        self.assertEqual(self.storage.values["port"], 9999)
        self.assertEqual(self.storage.values["panel_password"], "fixture-password-hash")
        self.assertEqual(self.storage.values["api_key"], "fixture-api-key")
        self.assertEqual(payload["env_locked"], ["port"])
        self.assertNotIn("fixture-password-hash", json.dumps(payload))
        self.assertNotIn("fixture-api-key", json.dumps(payload))

    async def test_system_reset_keeps_models_routing_and_resets_system_overrides(self):
        response = await self.client.post("/api/config/reset?scope=system")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.storage.values.get("routing_strategy"), "priority")
        self.assertEqual(self.storage.values.get("preferred_provider"), "codex")
        self.assertNotIn("retry_429_enabled", self.storage.values)
        self.assertEqual(response.json()["reset_config"], ["retry_429_enabled"])
        self.assert_protected_values_preserved(response.json())

    async def test_default_direct_reset_retains_legacy_routing_reset(self):
        response = await config_routes.reset_config(token="fixture-session")
        payload = json.loads(response.body)

        self.assertEqual(
            payload["reset_config"],
            [
                "preferred_provider",
                "retry_429_enabled",
                "routing_strategy",
            ],
        )
        self.assertNotIn("routing_strategy", self.storage.values)
        self.assertNotIn("preferred_provider", self.storage.values)
        self.assert_protected_values_preserved(payload)

    async def test_explicit_all_scope_retains_legacy_http_reset(self):
        response = await self.client.post("/api/config/reset?scope=all")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("routing_strategy", self.storage.values)
        self.assertNotIn("preferred_provider", self.storage.values)
        self.assert_protected_values_preserved(response.json())

    async def test_unknown_scope_is_rejected_before_any_reset(self):
        before = dict(self.storage.values)

        response = await self.client.post("/api/config/reset?scope=typo")

        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.storage.values, before)


if __name__ == "__main__":
    unittest.main()
