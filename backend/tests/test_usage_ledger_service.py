"""Selected-backend lifecycle boundary for the W4.14 usage ledger."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.usage_ledger import SpendSnapshot, UsageLedgerError, UsageLiabilityPage
from core.usage_ledger_service import (
    UsageLedgerService,
    close_usage_ledger_service,
    get_usage_ledger_service,
    initialize_usage_ledger_service,
    render_usage_ledger_metrics,
)


class UsageLedgerServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await close_usage_ledger_service()

    async def asyncTearDown(self):
        await close_usage_ledger_service()

    async def test_initialization_owns_selected_repository_once(self):
        repository = Mock()
        storage = Mock()
        storage.create_usage_ledger_repository = AsyncMock(return_value=repository)

        first = await initialize_usage_ledger_service(storage)
        second = await initialize_usage_ledger_service(storage)

        self.assertIs(first, second)
        self.assertIs(get_usage_ledger_service(), first)
        storage.create_usage_ledger_repository.assert_awaited_once_with()

    async def test_uninitialized_access_fails_closed(self):
        with self.assertRaises(RuntimeError):
            get_usage_ledger_service()

    async def test_repository_failure_is_visible_and_recovery_is_observable(self):
        repository = Mock()
        repository.get_spend = AsyncMock(side_effect=UsageLedgerError("offline"))
        storage = Mock()
        storage.create_usage_ledger_repository = AsyncMock(return_value=repository)
        service = await initialize_usage_ledger_service(storage)

        with self.assertRaises(UsageLedgerError):
            await service.get_spend(since=0, api_key_id="vk_enterprise")
        unavailable = service.health_snapshot()
        self.assertFalse(unavailable["available"])
        self.assertEqual(unavailable["failure_count"], 1)
        self.assertEqual(unavailable["last_error_type"], "UsageLedgerError")
        self.assertNotIn("offline", str(unavailable))

        repository.get_spend = AsyncMock(
            return_value=SpendSnapshot(cost_nanos=1, total_tokens=2, calls=3, available=True)
        )
        recovered = await service.get_spend(since=0, api_key_id="vk_enterprise")
        self.assertEqual(recovered.calls, 3)
        self.assertTrue(service.health_snapshot()["available"])
        metrics = render_usage_ledger_metrics()
        self.assertIn(
            'backend="unknown",operation="spend",result="error"',
            metrics,
        )
        self.assertIn(
            'backend="unknown",operation="spend",result="success"',
            metrics,
        )

    async def test_availability_check_actively_probes_repository(self):
        repository = Mock()
        repository.check_available = AsyncMock()
        storage = Mock()
        storage.create_usage_ledger_repository = AsyncMock(return_value=repository)
        service = await initialize_usage_ledger_service(storage)

        await service.check_available()

        repository.check_available.assert_awaited_once_with()

    async def test_reconciliation_page_preserves_typed_liability_evidence(self):
        evidence = UsageLiabilityPage(0, True, None, "a" * 64, 0)
        repository = Mock()
        repository.reconciliation_page = AsyncMock(return_value=evidence)
        service = UsageLedgerService(repository)

        result = await service.reconciliation_page(after=None, limit=256)

        self.assertEqual(result, evidence)
        repository.reconciliation_page.assert_awaited_once_with(after=None, limit=256)


if __name__ == "__main__":
    unittest.main()
