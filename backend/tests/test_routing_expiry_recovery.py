"""Regression coverage for credential routing after a burst of replay expiry."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.coordination import CoordinationReconciliationRequiredError
from core.coordination_service import CoordinationService
from core.routing_coordination import (
    CACHE_SCOPE_EXACT,
    ROUTING_MUTATION_REPLAY_TTL_SECONDS,
    RoutingCoordinationAdapter,
)
from core.state_store import InMemoryStateStore


class _Clock:
    def __init__(self) -> None:
        self.value = 1_000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class RoutingExpiryRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.clock = _Clock()
        self.service = CoordinationService(InMemoryStateStore(clock=self.clock))
        self.adapter = RoutingCoordinationAdapter(
            self.service, identifier_key=b"a" * 32, fencing_epoch=1
        )

    async def asyncTearDown(self) -> None:
        await self.service.close()

    async def _create_short_leases(self, count: int) -> None:
        for index in range(count):
            lease = await self.adapter.acquire_credential(
                "primary", f"expired-{index}.json", ttl_seconds=10, max_concurrency=1
            )
            self.assertIsNotNone(lease)

    async def test_routing_recovers_after_more_than_one_batch_expires_during_idle(self) -> None:
        await self._create_short_leases(257)
        self.clock.advance(ROUTING_MUTATION_REPLAY_TTL_SECONDS + 1)

        replacement = await self.adapter.acquire_credential(
            "primary", "expired-0.json", ttl_seconds=10, max_concurrency=1
        )

        self.assertIsNotNone(replacement)
        snapshot = await self.adapter.read_credential("primary", "expired-0.json")
        self.assertEqual(snapshot.in_flight, 1)
        self.assertTrue(self.service.health_snapshot()["available"])

    async def test_cleanup_preserves_live_lease_and_its_idempotent_admission(self) -> None:
        await self._create_short_leases(257)
        live = await self.adapter.acquire_credential(
            "primary", "still-running.json", ttl_seconds=300, max_concurrency=1
        )
        assert live is not None and live.admission is not None
        before = await self.service.read_cas(live.record_key, epoch=1)
        self.clock.advance(ROUTING_MUTATION_REPLAY_TTL_SECONDS + 1)

        recovered = await self.adapter.acquire_credential(
            "primary", "next-request.json", ttl_seconds=10, max_concurrency=1
        )

        self.assertIsNotNone(recovered)
        self.assertEqual(await self.service.read_cas(live.record_key, epoch=1), before)
        replay = await self.service.compare_and_set(live.admission)
        self.assertTrue(replay.applied)
        self.assertTrue(replay.idempotent)
        self.assertEqual(replay.revision, before.revision)
        self.assertIsNone(
            await self.adapter.acquire_credential(
                "primary", "still-running.json", ttl_seconds=10, max_concurrency=1
            )
        )
        self.assertTrue(await self.adapter.release_credential(live))

    async def test_large_expiry_backlog_recovers_without_starving_other_coroutines(self) -> None:
        await self._create_short_leases(1_025)
        self.clock.advance(ROUTING_MUTATION_REPLAY_TTL_SECONDS + 1)
        other_task_ran = asyncio.Event()

        async def other_request() -> None:
            other_task_ran.set()

        other_task = asyncio.create_task(other_request())
        try:
            recovered = await self.adapter.acquire_credential(
                "primary", "after-idle.json", ttl_seconds=10, max_concurrency=1
            )
            self.assertIsNotNone(recovered)
            self.assertTrue(
                other_task_ran.is_set(), "Expiry maintenance must yield between batches"
            )
        finally:
            await other_task

    async def test_cache_invalidation_recovers_after_replay_expiry_without_resetting_generation(
        self,
    ) -> None:
        generation = await self.adapter.current_generation(CACHE_SCOPE_EXACT)
        for _index in range(257):
            generation = await self.adapter.invalidate(CACHE_SCOPE_EXACT)
        # Cache invalidation admissions retain their replay proof for five minutes.
        self.clock.advance(301)

        next_generation = await self.adapter.invalidate(CACHE_SCOPE_EXACT)

        self.assertEqual(next_generation, generation + 1)
        self.assertEqual(await self.adapter.current_generation(CACHE_SCOPE_EXACT), next_generation)

    async def test_live_replay_capacity_is_not_recovered_by_discarding_live_records(self) -> None:
        limited_service = CoordinationService(
            InMemoryStateStore(clock=self.clock, _coordination_replay_limit_for_testing=2)
        )
        limited_adapter = RoutingCoordinationAdapter(
            limited_service, identifier_key=b"b" * 32, fencing_epoch=1
        )
        try:
            leases = []
            for index in range(2):
                lease = await limited_adapter.acquire_credential(
                    "primary", f"live-{index}.json", ttl_seconds=300, max_concurrency=1
                )
                assert lease is not None and lease.admission is not None
                leases.append(lease)

            with self.assertRaises(CoordinationReconciliationRequiredError):
                await limited_adapter.acquire_credential(
                    "primary", "over-capacity.json", ttl_seconds=10, max_concurrency=1
                )

            for index, lease in enumerate(leases):
                snapshot = await limited_adapter.read_credential("primary", f"live-{index}.json")
                self.assertEqual(snapshot.in_flight, 1)
                assert lease.admission is not None
                replay = await limited_service.compare_and_set(lease.admission)
                self.assertTrue(replay.applied)
                self.assertTrue(replay.idempotent)
        finally:
            await limited_service.close()


if __name__ == "__main__":
    unittest.main()
