"""Atomic, fail-closed coordination for upstream conversation metadata."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.coordination import CoordinationUnavailableError
from core.coordination_service import CoordinationService
from core.primary_session_coordination import PrimarySessionCoordinator
from core.state_store import InMemoryStateStore


class _UnavailableStore(InMemoryStateStore):
    async def read_cas(self, key: str, *, epoch: int):
        raise CoordinationUnavailableError("unavailable")


class PrimarySessionCoordinationTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_steps_are_atomic_and_raw_identifiers_are_not_keys(self) -> None:
        store = InMemoryStateStore()
        coordinator = PrimarySessionCoordinator(
            CoordinationService(store), identifier_key=b"s" * 32, fencing_epoch=1
        )

        states = await asyncio.gather(
            *(coordinator.next_state("session:tenant-secret", "hello") for _ in range(12))
        )

        self.assertEqual(sorted(state.step_index for state in states), list(range(1, 13)))
        self.assertNotIn("tenant-secret", repr(store._cas))

    async def test_dependency_failure_never_falls_back_to_local_state(self) -> None:
        coordinator = PrimarySessionCoordinator(
            CoordinationService(_UnavailableStore()),
            identifier_key=b"s" * 32,
            fencing_epoch=1,
        )

        with self.assertRaises(CoordinationUnavailableError):
            await coordinator.next_state("session:one", "hello")

    async def test_corrupt_payload_fails_closed(self) -> None:
        store = InMemoryStateStore()
        coordinator = PrimarySessionCoordinator(
            CoordinationService(store), identifier_key=b"s" * 32, fencing_epoch=1
        )
        key = coordinator._coordination_key("session:one")
        await store.compare_and_set(
            coordinator._request(key, 0, b"{}", "primary-session-corrupt-test")
        )

        with self.assertRaisesRegex(ValueError, "corrupt"):
            await coordinator.next_state("session:one", "hello")


if __name__ == "__main__":
    unittest.main()
