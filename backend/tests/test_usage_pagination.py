"""Dashboard usage pages retain every credential and complete provider totals."""

from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel import usage_routes
from core.usage_stats import UNASSIGNED_USAGE_FILENAME
from core.utils import verify_panel_token


class UsagePaginationFrontendTests(unittest.TestCase):
    def test_server_page_navigation_behavior(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the usage pagination contract.")
        result = subprocess.run(
            [node, str(Path(__file__).with_name("usage_pagination_contract.cjs"))],
            cwd=BACKEND_DIR.parent,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


class UsagePaginationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app = FastAPI()
        app.include_router(usage_routes.router)
        app.dependency_overrides[verify_panel_token] = lambda: "test-panel-session"
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )
        self.stats = {}
        self.stats_patch = patch.object(
            usage_routes,
            "get_stats_for_period",
            AsyncMock(side_effect=lambda *_args: self.stats),
        )
        self.stats_patch.start()

    async def asyncTearDown(self):
        self.stats_patch.stop()
        await self.client.aclose()

    async def page(self, **params):
        response = await self.client.get("/api/usage/stats/page", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_name_order_reaches_every_row_after_counters_change_between_pages(self):
        names = [f"credential-{index:03}.json" for index in range(205)]
        self.stats = {name: {"calls": 1} for name in reversed(names)}

        first = await self.page(page_size=100, offset=0, order="name")
        self.stats[names[150]]["calls"] = 9999
        second = await self.page(page_size=100, offset=100, order="name")
        third = await self.page(page_size=100, offset=200, order="name")

        observed = list(first["data"]) + list(second["data"]) + list(third["data"])
        self.assertEqual(observed, names)
        self.assertEqual(len(set(observed)), 205)
        for result, offset, has_more in (
            (first, 0, True),
            (second, 100, True),
            (third, 200, False),
        ):
            self.assertEqual(result["total_items"], 205)
            self.assertEqual(result["offset"], offset)
            self.assertEqual(result["has_more"], has_more)

    async def test_default_all_group_preserves_call_ranking_and_zero_rows_with_offset(self):
        self.stats = {
            "z.json": {"calls": 0},
            "b.json": {"calls": 10},
            "a.json": {"calls": 10},
            "c.json": {"calls": 5},
        }

        result = await self.page(page_size=2, offset=2)

        self.assertEqual(list(result["data"]), ["c.json", "z.json"])
        self.assertEqual(result["total_items"], 4)
        self.assertEqual(result["group"], "all")
        self.assertFalse(result["has_more"])

    async def test_group_filter_precedes_pagination_and_counts_only_matching_traffic(self):
        self.stats = {
            "a-deleted.json": {"calls": 10, "is_deleted": True},
            "b-historical.json": {"calls": 9, "is_historical": True},
            "c-current.json": {"calls": 8},
            "d-current.json": {"calls": 7},
            "e-idle.json": {"calls": 0},
            "f-idle-historical.json": {"calls": 0, "is_historical": True},
            UNASSIGNED_USAGE_FILENAME: {"calls": 1, "is_historical": True},
        }

        current = await self.page(group="current", order="name", page_size=1, offset=1)
        historical = await self.page(group="historical", order="name", page_size=1, offset=1)

        self.assertEqual(list(current["data"]), ["c-current.json"])
        self.assertEqual(current["total_items"], 3)
        self.assertEqual(current["group"], "current")
        self.assertTrue(current["has_more"])
        self.assertEqual(list(historical["data"]), ["b-historical.json"])
        self.assertEqual(historical["total_items"], 2)
        self.assertEqual(historical["group"], "historical")
        self.assertFalse(historical["has_more"])

    async def test_offset_past_last_row_returns_empty_page_with_total(self):
        self.stats = {"only.json": {"calls": 2}}

        result = await self.page(offset=100)

        self.assertEqual(result["data"], {})
        self.assertEqual(result["total_items"], 1)
        self.assertEqual(result["offset"], 100)
        self.assertFalse(result["has_more"])

    async def test_provider_totals_include_all_current_traffic_on_every_group_page(self):
        common = {"provider": "openai", "credential_type": "api_key"}
        self.stats = {
            "a.json": {
                **common,
                "calls": 4,
                "successful_calls": 3,
                "failed_calls": 1,
                "total_tokens": 40,
                "in_cooldown": False,
            },
            "b.json": {
                "provider_name": "openai",
                "credential_type": "api_key",
                "calls": 6,
                "successful_calls": 4,
                "failed_calls": 2,
                "total_tokens": 60,
                "in_cooldown": True,
            },
            "deleted.json": {**common, "calls": 100, "is_deleted": True},
            "historical.json": {**common, "calls": 100, "is_historical": True},
            "idle.json": {**common, "calls": 0},
            UNASSIGNED_USAGE_FILENAME: {**common, "calls": 100},
        }
        expected = [
            {
                **common,
                "credentials": 2,
                "calls": 10,
                "successful_calls": 7,
                "failed_calls": 3,
                "total_tokens": 100,
                "in_cooldown": True,
            }
        ]

        for group, offset in (("current", 0), ("current", 1), ("historical", 1)):
            with self.subTest(group=group, offset=offset):
                result = await self.page(group=group, order="name", offset=offset, page_size=1)
                self.assertEqual(result.get("provider_totals"), expected)

    async def test_invalid_page_selectors_are_rejected(self):
        for params in ({"offset": -1}, {"group": "unknown"}, {"order": "unknown"}):
            with self.subTest(params=params):
                response = await self.client.get("/api/usage/stats/page", params=params)
                self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
