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

from core.panel.providers.antigravity import get_antigravity_config, redact_antigravity_config


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


if __name__ == "__main__":
    unittest.main()
