"""Tests for production health probes."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.health import health, ready


class HealthProbeTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _ready_lifecycle():
        lifecycle = Mock()
        lifecycle.check_ready = AsyncMock(return_value=True)
        return lifecycle

    async def test_liveness_is_dependency_free(self):
        response = await health()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body), {"status": "ok"})

    async def test_readiness_reports_available_storage(self):
        storage = AsyncMock()
        storage.get_all_config.return_value = {}
        ledger = Mock()
        ledger.check_available = AsyncMock()
        ledger.health_snapshot.return_value = {"available": True}
        with (
            patch(
                "core.health.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch("core.health.get_usage_ledger_service", return_value=ledger),
            patch("core.health.get_runtime_lifecycle", return_value=self._ready_lifecycle()),
        ):
            response = await ready()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["storage"], "available")
        ledger.check_available.assert_awaited_once_with()

    async def test_readiness_returns_503_without_exposing_exception(self):
        with (
            patch(
                "core.health.get_storage_adapter",
                new=AsyncMock(side_effect=RuntimeError("database password leaked")),
            ),
            patch("core.health.get_runtime_lifecycle", return_value=self._ready_lifecycle()),
        ):
            response = await ready()

        self.assertEqual(response.status_code, 503)
        body = response.body.decode()
        self.assertNotIn("database password leaked", body)
        self.assertEqual(json.loads(body)["storage"], "unavailable")

    async def test_readiness_fails_when_usage_ledger_is_unavailable(self):
        storage = AsyncMock()
        storage.get_all_config.return_value = {}
        ledger = Mock()
        ledger.check_available = AsyncMock(side_effect=RuntimeError("offline"))
        ledger.health_snapshot.return_value = {"available": False}
        with (
            patch(
                "core.health.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch("core.health.get_usage_ledger_service", return_value=ledger),
            patch("core.health.get_runtime_lifecycle", return_value=self._ready_lifecycle()),
        ):
            response = await ready()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.body)["storage"], "available")
        self.assertEqual(json.loads(response.body)["usage_ledger"], "unavailable")

    async def test_readiness_fails_during_runtime_startup_without_dependency_reads(self):
        storage = AsyncMock()
        with (
            patch("core.health.get_runtime_lifecycle", return_value=None),
            patch("core.health.get_storage_adapter", new=storage),
        ):
            response = await ready()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.body)["coordination"], "unavailable")
        storage.assert_not_awaited()

    async def test_coordination_outage_does_not_misreport_healthy_durable_dependencies(self):
        lifecycle = Mock()
        lifecycle.check_ready = AsyncMock(return_value=False)
        storage = AsyncMock()
        storage.get_all_config.return_value = {}
        ledger = Mock()
        ledger.check_available = AsyncMock()
        ledger.health_snapshot.return_value = {"available": True}
        with (
            patch("core.health.get_runtime_lifecycle", return_value=lifecycle),
            patch("core.health.get_storage_adapter", new=AsyncMock(return_value=storage)),
            patch("core.health.get_usage_ledger_service", return_value=ledger),
        ):
            response = await ready()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            json.loads(response.body),
            {
                "status": "unavailable",
                "storage": "available",
                "usage_ledger": "available",
                "coordination": "unavailable",
            },
        )
