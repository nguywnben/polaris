"""Authenticated product-capability API contract tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity import ManagementPermission, ManagementRouteTransport, management_route_manifest
from core.panel.capabilities import get_product_capabilities, router
from core.utils import verify_panel_token


class ProductCapabilityRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_capability_summary_is_versioned_and_content_safe(self) -> None:
        response = await get_product_capabilities(token="session")
        body = json.loads(response.body)

        self.assertEqual(body["schema_version"], 1)
        self.assertEqual(body["profile"], "self_hosted")
        self.assertTrue(body["capabilities"])
        self.assertNotIn("environment", body)

    async def test_route_is_authenticated_typed_and_read_only(self) -> None:
        route = next(route for route in router.routes if route.path == "/api/capabilities")

        self.assertEqual(route.methods, {"GET"})
        self.assertTrue(
            any(
                dependency.call is verify_panel_token for dependency in route.dependant.dependencies
            )
        )
        self.assertIsNotNone(route.response_model)

        manifest_entry = next(
            entry
            for entry in management_route_manifest()
            if entry.transport is ManagementRouteTransport.HTTP
            and entry.method == "GET"
            and entry.path == "/api/capabilities"
        )
        self.assertIs(manifest_entry.permission, ManagementPermission.CONFIGURATION_READ)


if __name__ == "__main__":
    unittest.main()
