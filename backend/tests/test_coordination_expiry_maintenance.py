"""Bounded maintenance must not change live coordination decisions."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.coordination import (
    CasRequest,
    CoordinationCorruptError,
    CoordinationReconciliationRequiredError,
    CoordinationUnavailableError,
    InvalidationRequest,
)
from core.coordination_service import CoordinationService
from core.state_store import InMemoryStateStore


class CoordinationExpiryMaintenanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 1000.0
        self.store = InMemoryStateStore(clock=lambda: self.now)
        self.addAsyncCleanup(self.store.close)

    async def seed(self, count=257):
        for index in range(count):
            await self.store.compare_and_set(
                CasRequest(
                    f"record-{index}", 0, b"live", 600, 1, f"op-{index}", replay_ttl_seconds=1
                )
            )
        self.now += 2

    async def test_batch_is_bounded_and_does_not_remove_live_records(self):
        await self.seed()
        count = await self.store.prune_expired_coordination_replays(
            epoch=1, operation="compare_and_set", limit=7
        )
        self.assertEqual(count, 7)
        self.assertEqual(len(self.store._cas_replays), 250)
        self.assertEqual(len(self.store._cas_replay_expiries), 250)
        self.assertEqual(len(self.store._cas), 257)
        snapshot = await self.store.read_cas("record-0", epoch=1)
        self.assertEqual(snapshot.payload, b"live")

    async def test_invalid_inputs_stale_epoch_and_closed_store_do_not_prune(self):
        await self.seed()
        before = copy.deepcopy(self.store._cas_replays)
        for limit in (0, -1, 257, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                await self.store.prune_expired_coordination_replays(
                    epoch=1, operation="compare_and_set", limit=limit
                )
        with self.assertRaises(ValueError):
            await self.store.prune_expired_coordination_replays(epoch=1, operation="sessions")
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.prune_expired_coordination_replays(
                epoch=2, operation="compare_and_set"
            )
        self.assertEqual(self.store._cas_replays, before)
        await self.store.close()
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.prune_expired_coordination_replays(
                epoch=1, operation="compare_and_set"
            )

    async def test_corrupt_expiry_batch_is_atomic(self):
        await self.seed(3)
        self.store._cas_replays.pop("op-1")
        before = copy.deepcopy((self.store._cas_replays, self.store._cas_replay_expiries))
        with self.assertRaises(CoordinationCorruptError):
            await self.store.prune_expired_coordination_replays(
                epoch=1, operation="compare_and_set"
            )
        self.assertEqual((self.store._cas_replays, self.store._cas_replay_expiries), before)

    async def test_duplicate_expiry_entry_does_not_partially_commit_batch(self):
        await self.seed(1)
        self.store._cas_replay_expiries.append(self.store._cas_replay_expiries[0])
        before = copy.deepcopy((self.store._cas_replays, self.store._cas_replay_expiries))
        with self.assertRaises(CoordinationCorruptError):
            await self.store.prune_expired_coordination_replays(
                epoch=1, operation="compare_and_set"
            )
        self.assertEqual((self.store._cas_replays, self.store._cas_replay_expiries), before)

    async def test_no_progress_remains_unavailable_in_service_health(self):
        self.store._coordination_replay_limit = 1
        service = CoordinationService(self.store)
        await service.compare_and_set(CasRequest("live", 0, b"live", 600, 1, "live-op"))
        with self.assertRaises(CoordinationReconciliationRequiredError):
            await service.compare_and_set(CasRequest("new", 0, b"new", 600, 1, "new-op"))
        self.assertFalse(service.health_snapshot()["available"])
        self.assertEqual(
            service.health_snapshot()["last_error_category"], "reconciliation_required"
        )

    async def test_invalidation_maintenance_leaves_cas_family_untouched(self):
        await self.seed(3)
        await self.store.invalidate(InvalidationRequest("scope", 1, "invalidate", 1))
        self.now += 2
        before = copy.deepcopy(self.store._cas_replays)
        self.assertEqual(
            await self.store.prune_expired_coordination_replays(epoch=1, operation="invalidate"), 1
        )
        self.assertEqual(self.store._cas_replays, before)
        self.assertEqual((await self.store.read_invalidation_generation("scope")).generation, 1)

    async def test_service_stops_at_batch_bound_and_reuses_original_request(self):
        service = CoordinationService(self.store)
        request = CasRequest("key", 0, b"value", 60, 1, "same-operation")
        mutation = AsyncMock(side_effect=CoordinationReconciliationRequiredError("backlog"))
        prune = AsyncMock(return_value=256)
        with (
            patch.object(self.store, "compare_and_set", mutation),
            patch.object(self.store, "prune_expired_coordination_replays", prune),
            patch("core.coordination_service._MAX_REPLAY_MAINTENANCE_BATCHES", 2),
            self.assertRaises(CoordinationReconciliationRequiredError),
        ):
            await service.compare_and_set(request)
        self.assertEqual(mutation.await_count, 3)
        self.assertEqual(prune.await_count, 2)
        self.assertTrue(all(call.args[0] is request for call in mutation.await_args_list))

    async def test_unavailable_store_without_maintenance_keeps_original_error(self):
        class StoreWithoutMaintenance:
            async def compare_and_set(self, request):
                raise CoordinationReconciliationRequiredError("backlog")

        with self.assertRaises(CoordinationReconciliationRequiredError):
            await CoordinationService(StoreWithoutMaintenance()).compare_and_set(
                CasRequest("key", 0, b"value", 60, 1, "operation")
            )


if __name__ == "__main__":
    unittest.main()
