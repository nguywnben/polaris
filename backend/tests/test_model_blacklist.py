"""Persistent provider-model blacklist behavior for virtual routing."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.model_blacklist import (
    clear_model_blacklist,
    get_credential_model_blacklist_pairs,
    get_model_blacklist,
    get_model_blacklist_pairs,
    record_model_not_found,
    remove_model_blacklist_entry,
)
from core.model_pool import ModelCatalogEntry
from core.panel.model_pools import (
    delete_model_blacklist,
    delete_model_blacklist_entry,
    get_model_catalog,
)


class FakeConfigStorage:
    def __init__(self):
        self.values = {}

    async def get_config(self, key, default=None):
        return self.values.get(key, default)

    async def set_config(self, key, value):
        self.values[key] = value
        return True


class ModelBlacklistTests(unittest.IsolatedAsyncioTestCase):
    async def test_not_found_routes_are_scoped_to_individual_credentials(self):
        storage = FakeConfigStorage()

        await record_model_not_found(
            "google_ai_studio",
            "gemini-account-limited",
            credential_name="first.json",
            storage_adapter=storage,
            now=100.0,
        )
        await record_model_not_found(
            "google_ai_studio",
            "gemini-account-limited",
            credential_name="second.json",
            storage_adapter=storage,
            now=110.0,
        )

        entries = await get_model_blacklist(storage_adapter=storage)
        self.assertEqual(
            [(entry["credential_name"], entry["failure_count"]) for entry in entries],
            [("second.json", 1), ("first.json", 1)],
        )
        self.assertEqual(
            await get_credential_model_blacklist_pairs(storage_adapter=storage),
            {
                ("first.json", "gemini-account-limited"),
                ("second.json", "gemini-account-limited"),
            },
        )
        self.assertEqual(await get_model_blacklist_pairs(storage_adapter=storage), set())

    async def test_legacy_provider_routes_remain_provider_scoped(self):
        storage = FakeConfigStorage()
        storage.values["model_route_blacklist"] = {
            "entries": [
                {
                    "provider_id": "google_ai_studio",
                    "model_id": "gemini-retired",
                    "failure_count": 1,
                    "first_seen_at": 100.0,
                    "last_seen_at": 100.0,
                }
            ]
        }

        self.assertEqual(
            await get_model_blacklist_pairs(storage_adapter=storage),
            {("google_ai_studio", "gemini-retired")},
        )
        self.assertEqual(
            await get_credential_model_blacklist_pairs(storage_adapter=storage),
            set(),
        )

    async def test_repeated_not_found_updates_one_provider_model_entry(self):
        storage = FakeConfigStorage()

        await record_model_not_found(
            "google_ai_studio",
            "models/gemini-retired",
            storage_adapter=storage,
            now=100.0,
        )
        await record_model_not_found(
            "google_ai_studio",
            "gemini-retired",
            storage_adapter=storage,
            now=125.0,
        )

        entries = await get_model_blacklist(storage_adapter=storage)
        self.assertEqual(
            entries,
            [
                {
                    "provider_id": "google_ai_studio",
                    "model_id": "gemini-retired",
                    "status_code": 404,
                    "failure_count": 2,
                    "first_seen_at": 100.0,
                    "last_seen_at": 125.0,
                }
            ],
        )
        self.assertEqual(
            await get_model_blacklist_pairs(storage_adapter=storage),
            {("google_ai_studio", "gemini-retired")},
        )

    async def test_entries_can_be_removed_individually_or_cleared(self):
        storage = FakeConfigStorage()
        await record_model_not_found(
            "google_ai_studio",
            "gemini-retired",
            storage_adapter=storage,
            now=100.0,
        )
        await record_model_not_found(
            "google_antigravity",
            "claude-retired",
            storage_adapter=storage,
            now=110.0,
        )

        removed = await remove_model_blacklist_entry(
            "google_ai_studio",
            "gemini-retired",
            storage_adapter=storage,
        )

        self.assertTrue(removed)
        self.assertEqual(
            await get_model_blacklist_pairs(storage_adapter=storage),
            {("google_antigravity", "claude-retired")},
        )
        self.assertEqual(await clear_model_blacklist(storage_adapter=storage), 1)
        self.assertEqual(await get_model_blacklist(storage_adapter=storage), [])

    async def test_catalog_distinguishes_blacklisted_and_routable_providers(self):
        catalog = [
            ModelCatalogEntry(
                "gemini-shared",
                ("google_ai_studio", "google_antigravity"),
            ),
            ModelCatalogEntry("gemini-blocked", ("google_ai_studio",)),
        ]
        blacklist = [
            {
                "provider_id": "google_ai_studio",
                "model_id": "gemini-shared",
                "status_code": 404,
                "failure_count": 1,
                "first_seen_at": 100.0,
                "last_seen_at": 100.0,
            },
            {
                "provider_id": "google_ai_studio",
                "model_id": "gemini-blocked",
                "status_code": 404,
                "failure_count": 2,
                "first_seen_at": 100.0,
                "last_seen_at": 120.0,
            },
        ]

        with (
            patch(
                "core.panel.model_pools.model_catalog_service.get_catalog",
                AsyncMock(return_value=catalog),
            ),
            patch(
                "core.panel.model_pools.get_virtual_model_pool",
                AsyncMock(
                    return_value={
                        "alias": "polaris",
                        "strategy": "priority_fallback",
                        "selected_models": ["gemini-shared", "gemini-blocked"],
                        "enabled": True,
                    }
                ),
            ),
            patch(
                "core.panel.model_pools.get_model_blacklist",
                AsyncMock(return_value=blacklist),
            ),
        ):
            response = await get_model_catalog(refresh=False, token="test-session")

        payload = json.loads(response.body)
        shared = next(item for item in payload["catalog"] if item["model_id"] == "gemini-shared")
        blocked = next(item for item in payload["catalog"] if item["model_id"] == "gemini-blocked")
        self.assertEqual(shared["routable_providers"], ["google_antigravity"])
        self.assertEqual(shared["blacklisted_providers"], ["google_ai_studio"])
        self.assertTrue(shared["available"])
        self.assertEqual(blocked["routable_providers"], [])
        self.assertFalse(blocked["available"])
        self.assertEqual(payload["blacklist"], blacklist)
        self.assertEqual(payload["summary"]["blacklisted_routes"], 2)

    async def test_management_api_removes_one_entry_or_the_entire_blacklist(self):
        with patch(
            "core.panel.model_pools.remove_model_blacklist_entry",
            AsyncMock(return_value=True),
        ) as remove_mock:
            response = await delete_model_blacklist_entry(
                "google_ai_studio",
                "gemini-retired",
                credential_name="first.json",
                token="test-session",
            )
        remove_mock.assert_awaited_once_with(
            "google_ai_studio",
            "gemini-retired",
            credential_name="first.json",
        )
        self.assertEqual(
            json.loads(response.body)["message"], "Model route removed from blacklist."
        )

        with patch(
            "core.panel.model_pools.clear_model_blacklist",
            AsyncMock(return_value=3),
        ):
            response = await delete_model_blacklist(token="test-session")
        self.assertEqual(json.loads(response.body)["removed_count"], 3)


if __name__ == "__main__":
    unittest.main()
