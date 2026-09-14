"""Production model-route lifecycle and validation contracts for P3.6."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.model_pool import (
    ModelCatalogEntry,
    assess_virtual_model_pool,
    decorate_virtual_model_pool,
)
from core.models import VirtualModelPoolUpdateRequest
from core.panel.model_pools import (
    create_default_model_pool,
    delete_default_model_pool,
    patch_default_model_route,
    validate_default_model_pool,
)


def response_body(response) -> dict:
    return json.loads(response.body)


class ModelRouteContractTests(unittest.TestCase):
    def test_revision_is_stable_and_changes_with_route_content(self) -> None:
        first = decorate_virtual_model_pool(
            {
                "alias": "polaris",
                "strategy": "priority_fallback",
                "selected_models": ["model-a"],
                "enabled": True,
            }
        )
        same = decorate_virtual_model_pool(dict(first))
        changed = decorate_virtual_model_pool(
            {
                "alias": "polaris",
                "strategy": "priority_fallback",
                "selected_models": ["model-b"],
                "enabled": True,
            }
        )

        self.assertEqual(first["revision"], same["revision"])
        self.assertNotEqual(first["revision"], changed["revision"])
        self.assertTrue(first["configured"])

    def test_validation_explains_degraded_and_unavailable_members(self) -> None:
        catalog = [
            {"model_id": "model-a", "available": True, "routable_providers": ["codex"]},
            {"model_id": "model-b", "available": False, "routable_providers": []},
        ]

        degraded = assess_virtual_model_pool(["model-a", "model-b"], catalog)
        unavailable = assess_virtual_model_pool(["model-b"], catalog)
        unknown = assess_virtual_model_pool(["model-missing"], catalog)

        self.assertTrue(degraded["valid"])
        self.assertEqual(degraded["status"], "degraded")
        self.assertEqual(degraded["issues"][0]["code"], "model_temporarily_unavailable")
        self.assertFalse(unavailable["valid"])
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertIn(
            "route_has_no_available_model", {item["code"] for item in unavailable["issues"]}
        )
        self.assertFalse(unknown["valid"])
        self.assertEqual(unknown["issues"][0]["code"], "model_not_discovered")


class ModelRouteApiLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.request = VirtualModelPoolUpdateRequest(
            selected_models=["model-a"],
            enabled=True,
        )
        self.entries = [ModelCatalogEntry("model-a", ("codex",))]

    async def test_validate_returns_a_versioned_safe_assessment(self) -> None:
        with (
            patch(
                "core.panel.model_pools.model_catalog_service.get_catalog",
                AsyncMock(return_value=self.entries),
            ),
            patch("core.panel.model_pools.get_model_blacklist", AsyncMock(return_value=[])),
            patch(
                "core.panel.model_pools.get_virtual_model_pool",
                AsyncMock(return_value={"selected_models": []}),
            ),
        ):
            response = await validate_default_model_pool(self.request, token="panel")

        payload = response_body(response)
        self.assertEqual(payload["schema_version"], "model-routing.v1")
        self.assertTrue(payload["validation"]["valid"])
        self.assertNotIn("credential_name", response.body.decode())

    async def test_saved_missing_fallback_can_be_retained_beside_a_healthy_model(self) -> None:
        with (
            patch(
                "core.panel.model_pools.model_catalog_service.get_catalog",
                AsyncMock(return_value=self.entries),
            ),
            patch("core.panel.model_pools.get_model_blacklist", AsyncMock(return_value=[])),
            patch(
                "core.panel.model_pools.get_virtual_model_pool",
                AsyncMock(return_value={"selected_models": ["missing-fallback"]}),
            ),
        ):
            response = await validate_default_model_pool(
                VirtualModelPoolUpdateRequest(selected_models=["model-a", "missing-fallback"]),
                token="panel",
            )
        validation = response_body(response)["validation"]
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["status"], "degraded")

    async def test_create_edit_delete_lifecycle_uses_only_discovered_models(self) -> None:
        class Storage:
            def __init__(self) -> None:
                self.values = {}

            async def get_config(self, key, default=None):
                return self.values.get(key, default)

            async def set_config(self, key, value):
                self.values[key] = value
                return True

        storage = Storage()
        entries = [
            ModelCatalogEntry("model-a", ("codex",)),
            ModelCatalogEntry("model-b", ("openai_platform",)),
        ]
        with (
            patch("core.model_pool.get_storage_adapter", AsyncMock(return_value=storage)),
            patch(
                "core.panel.model_pools.model_catalog_service.get_catalog",
                AsyncMock(return_value=entries),
            ),
            patch("core.panel.model_pools.get_model_blacklist", AsyncMock(return_value=[])),
        ):
            created = response_body(await create_default_model_pool(self.request, token="panel"))
            revision = created["pool"]["revision"]
            edited = response_body(
                await patch_default_model_route(
                    VirtualModelPoolUpdateRequest(
                        selected_models=["model-b", "model-a"],
                        enabled=True,
                    ),
                    token="panel",
                    if_match=revision,
                )
            )
            deleted = response_body(
                await delete_default_model_pool(
                    token="panel",
                    if_match=edited["pool"]["revision"],
                )
            )

        self.assertEqual(edited["pool"]["selected_models"], ["model-b", "model-a"])
        self.assertFalse(deleted["pool"]["configured"])
        self.assertEqual(storage.values["virtual_model_pool"]["selected_models"], [])

    async def test_create_rejects_an_existing_route_without_overwriting_it(self) -> None:
        existing = decorate_virtual_model_pool(
            {
                "alias": "polaris",
                "strategy": "priority_fallback",
                "selected_models": ["model-a"],
                "enabled": True,
            }
        )
        save = AsyncMock()
        with (
            patch(
                "core.panel.model_pools.get_virtual_model_pool", AsyncMock(return_value=existing)
            ),
            patch("core.panel.model_pools.save_virtual_model_pool", save),
        ):
            with self.assertRaises(HTTPException) as raised:
                await create_default_model_pool(self.request, token="panel")

        self.assertEqual(raised.exception.status_code, 409)
        save.assert_not_awaited()

    async def test_update_rejects_a_stale_revision(self) -> None:
        existing = decorate_virtual_model_pool(
            {
                "alias": "polaris",
                "strategy": "priority_fallback",
                "selected_models": ["model-a"],
                "enabled": True,
            }
        )
        save = AsyncMock()
        with (
            patch(
                "core.panel.model_pools.get_virtual_model_pool", AsyncMock(return_value=existing)
            ),
            patch("core.panel.model_pools.save_virtual_model_pool", save),
        ):
            with self.assertRaises(HTTPException) as raised:
                await patch_default_model_route(
                    self.request,
                    token="panel",
                    if_match='"stale-revision"',
                )

        self.assertEqual(raised.exception.status_code, 409)
        save.assert_not_awaited()

    async def test_update_requires_a_revision_precondition(self) -> None:
        existing = decorate_virtual_model_pool(
            {
                "alias": "polaris",
                "strategy": "priority_fallback",
                "selected_models": ["model-a"],
                "enabled": True,
            }
        )
        with patch(
            "core.panel.model_pools.get_virtual_model_pool",
            AsyncMock(return_value=existing),
        ):
            with self.assertRaises(HTTPException) as raised:
                await patch_default_model_route(self.request, token="panel", if_match=None)

        self.assertEqual(raised.exception.status_code, 428)

    async def test_delete_uses_the_same_revision_guard_and_disables_the_route(self) -> None:
        existing = decorate_virtual_model_pool(
            {
                "alias": "polaris",
                "strategy": "priority_fallback",
                "selected_models": ["model-a"],
                "enabled": True,
            }
        )
        deleted = decorate_virtual_model_pool(
            {
                "alias": "polaris",
                "strategy": "priority_fallback",
                "selected_models": [],
                "enabled": False,
            }
        )
        save = AsyncMock(return_value=deleted)
        with (
            patch(
                "core.panel.model_pools.get_virtual_model_pool", AsyncMock(return_value=existing)
            ),
            patch("core.panel.model_pools.save_virtual_model_pool", save),
        ):
            response = await delete_default_model_pool(
                token="panel",
                if_match=existing["revision"],
            )

        payload = response_body(response)
        self.assertFalse(payload["pool"]["configured"])
        save.assert_awaited_once_with([], enabled=False)


if __name__ == "__main__":
    unittest.main()
