from __future__ import annotations

import asyncio
import sys
import time
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.coordination import CasRequest, CoordinationCorruptError, CoordinationUnavailableError
from core.routing_coordination import (
    CACHE_SCOPE_EXACT,
    CacheKind,
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


class _RecordingStore(InMemoryStateStore):
    def __init__(self, *, clock) -> None:
        super().__init__(clock=clock)
        self.keys: list[str] = []
        self.payloads: list[bytes] = []
        self.requests: list[CasRequest] = []

    async def read_cas(self, key: str, *, epoch: int):
        self.keys.append(key)
        return await super().read_cas(key, epoch=epoch)

    async def compare_and_set(self, request):
        self.keys.append(request.key)
        self.payloads.append(request.payload)
        self.requests.append(request)
        return await super().compare_and_set(request)


class _UnknownOutcomeStore(_RecordingStore):
    def __init__(self, *, clock) -> None:
        super().__init__(clock=clock)
        self.fail_next_cas = True
        self.fail_next_invalidation = True

    async def compare_and_set(self, request):
        result = await super().compare_and_set(request)
        if self.fail_next_cas:
            self.fail_next_cas = False
            raise CoordinationUnavailableError("unknown CAS outcome")
        return result

    async def invalidate(self, request):
        result = await super().invalidate(request)
        if self.fail_next_invalidation:
            self.fail_next_invalidation = False
            raise CoordinationUnavailableError("unknown invalidation outcome")
        return result


class _ContendedStore(_RecordingStore):
    """Expose same-process CAS contention that a local adapter can avoid."""

    def __init__(self, *, clock) -> None:
        super().__init__(clock=clock)
        self.active_writes = 0
        self.maximum_active_writes = 0

    async def compare_and_set(self, request):
        self.active_writes += 1
        self.maximum_active_writes = max(self.maximum_active_writes, self.active_writes)
        try:
            await asyncio.sleep(0)
            return await super().compare_and_set(request)
        finally:
            self.active_writes -= 1


class RoutingCoordinationAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.clock = _Clock()
        self.store = _RecordingStore(clock=self.clock)
        self.first = RoutingCoordinationAdapter(
            self.store,
            identifier_key=b"a" * 32,
            fencing_epoch=1,
        )
        self.second = RoutingCoordinationAdapter(
            self.store,
            identifier_key=b"a" * 32,
            fencing_epoch=1,
        )

    async def test_exclusive_lease_is_shared_released_and_expired(self) -> None:
        lease = await self.first.acquire_credential(
            "primary", "alice@example.json", ttl_seconds=10, max_concurrency=1
        )
        denied = await self.second.acquire_credential(
            "primary", "alice@example.json", ttl_seconds=10, max_concurrency=1
        )
        self.assertIsNotNone(lease)
        self.assertIsNone(denied)

        assert lease is not None
        self.assertTrue(await self.first.release_credential(lease))
        replacement = await self.second.acquire_credential(
            "primary", "alice@example.json", ttl_seconds=10, max_concurrency=1
        )
        self.assertIsNotNone(replacement)

        self.clock.advance(10.1)
        after_expiry = await self.first.acquire_credential(
            "primary", "alice@example.json", ttl_seconds=10, max_concurrency=1
        )
        self.assertIsNotNone(after_expiry)

    async def test_unknown_mutation_outcomes_retry_the_same_operation(self) -> None:
        store = _UnknownOutcomeStore(clock=self.clock)
        adapter = RoutingCoordinationAdapter(
            store,
            identifier_key=b"u" * 32,
            fencing_epoch=1,
        )

        lease = await adapter.acquire_credential(
            "primary", "unknown.json", ttl_seconds=10, max_concurrency=2
        )
        self.assertIsNotNone(lease)
        self.assertEqual((await adapter.read_credential("primary", "unknown.json")).in_flight, 1)

        generation = await adapter.invalidate(CACHE_SCOPE_EXACT)
        self.assertEqual(generation, 2)
        self.assertEqual(await adapter.current_generation(CACHE_SCOPE_EXACT), 2)

    async def test_high_churn_mutations_bound_replay_retention_independently(self) -> None:
        lease = await self.first.acquire_credential(
            "primary", "bounded-replay.json", ttl_seconds=300, max_concurrency=2
        )
        assert lease is not None
        await self.first.release_credential(lease)
        await self.first.record_route_outcome(
            "primary",
            "bounded-replay.json",
            "model",
            success=True,
            failure_kind="",
            retry_after_seconds=0,
            latency_ms=1,
        )
        generation = await self.first.current_generation(CACHE_SCOPE_EXACT)
        await self.first.publish_cache_metadata(
            CacheKind.EXACT,
            "bounded-replay-cache-key",
            content_digest="c" * 64,
            media_kind="json",
            generation=generation,
            ttl_seconds=300,
        )

        replay_ttls = [request.effective_replay_ttl_seconds for request in self.store.requests]
        self.assertEqual(replay_ttls[0], 300)
        self.assertTrue(all(ttl <= 60 for ttl in replay_ttls[1:]))
        self.assertTrue(all(request.ttl_seconds >= 300 for request in self.store.requests))

    async def test_missing_invalidation_authority_fails_closed(self) -> None:
        self.store._invalidation_generations.pop(CACHE_SCOPE_EXACT)

        with self.assertRaises(CoordinationCorruptError):
            await self.first.current_generation(CACHE_SCOPE_EXACT)

    async def test_store_receives_only_domain_separated_hmac_identifiers(self) -> None:
        lease = await self.first.acquire_credential(
            "primary", "secret-account.json", ttl_seconds=10, max_concurrency=2
        )
        self.assertIsNotNone(lease)
        serialized = b"\n".join(self.store.payloads)
        self.assertTrue(self.store.keys)
        self.assertTrue(all(key.startswith("routing-lease:") for key in self.store.keys))
        self.assertNotIn("secret-account", " ".join(self.store.keys))
        self.assertNotIn(b"secret-account", serialized)
        self.assertNotIn(b"primary", serialized)

    async def test_route_cooldown_and_latency_are_shared_and_bounded(self) -> None:
        await self.first.record_route_outcome(
            "primary",
            "alice.json",
            "model-secret",
            success=False,
            failure_kind="rate_limited",
            retry_after_seconds=30,
            latency_ms=None,
        )
        outcome = await self.second.read_route_outcome("primary", "alice.json", "model-secret")
        self.assertEqual(outcome.failure_count, 1)
        self.assertEqual(outcome.failure_kind, "rate_limited")
        self.assertAlmostEqual(outcome.retry_after_seconds, 30, delta=0.01)

        for latency in range(25):
            await self.first.record_route_outcome(
                "primary",
                "alice.json",
                "model-secret",
                success=True,
                failure_kind="",
                retry_after_seconds=0,
                latency_ms=float(latency + 1),
            )
        outcome = await self.second.read_route_outcome("primary", "alice.json", "model-secret")
        self.assertEqual(outcome.failure_count, 0)
        self.assertEqual(outcome.latency_samples_ms, tuple(float(value) for value in range(16, 26)))

    async def test_exact_cache_metadata_requires_current_generation_and_digest(self) -> None:
        generation = await self.first.current_generation(CACHE_SCOPE_EXACT)
        published = await self.first.publish_cache_metadata(
            CacheKind.EXACT,
            "raw-cache-key",
            content_digest="b" * 64,
            media_kind="json",
            generation=generation,
            ttl_seconds=30,
        )
        self.assertTrue(published)
        metadata = await self.second.resolve_cache_metadata(
            CacheKind.EXACT,
            "raw-cache-key",
            generation=generation,
        )
        self.assertEqual(metadata.content_digest, "b" * 64)
        self.assertEqual(metadata.media_kind, "json")

        invalidated = await self.second.invalidate(CACHE_SCOPE_EXACT)
        self.assertEqual(invalidated, 2)
        self.assertIsNone(
            await self.first.resolve_cache_metadata(
                CacheKind.EXACT,
                "raw-cache-key",
                generation=invalidated,
            )
        )
        self.assertNotIn("raw-cache-key", " ".join(self.store.keys))

    async def test_corrupt_payload_and_stale_epoch_fail_closed(self) -> None:
        key = self.first._lease_key("primary", "alice.json")
        await self.store.compare_and_set(CasRequest(key, 0, b"{}", 10, 1, "corrupt"))
        with self.assertRaises(CoordinationCorruptError):
            await self.first.read_credential("primary", "alice.json")

        advanced = await self.store.advance_epoch(1, "advance")
        self.assertEqual(advanced.epoch, 2)
        with self.assertRaises(CoordinationUnavailableError):
            await self.first.acquire_credential(
                "primary", "bob.json", ttl_seconds=10, max_concurrency=1
            )

    async def test_lease_capacity_payload_and_reference_latency_are_bounded(self) -> None:
        started = time.perf_counter()
        leases = []
        for _index in range(128):
            lease = await self.first.acquire_credential(
                "primary", "capacity.json", ttl_seconds=10, max_concurrency=128
            )
            self.assertIsNotNone(lease)
            leases.append(lease)
        self.assertIsNone(
            await self.second.acquire_credential(
                "primary", "capacity.json", ttl_seconds=10, max_concurrency=128
            )
        )
        snapshot = await self.store.read_cas(
            self.first._lease_key("primary", "capacity.json"), epoch=1
        )
        self.assertLess(len(snapshot.payload or b""), 16 * 1024)
        self.assertLess(time.perf_counter() - started, 2.0)

        for lease in leases:
            assert lease is not None
            self.assertTrue(await self.first.release_credential(lease))

    async def test_same_adapter_serializes_only_same_credential_lease_mutations(self) -> None:
        store = _ContendedStore(clock=self.clock)
        adapter = RoutingCoordinationAdapter(
            store,
            identifier_key=b"c" * 32,
            fencing_epoch=1,
        )

        leases = await asyncio.gather(
            *(
                adapter.acquire_credential(
                    "primary",
                    "contended.json",
                    ttl_seconds=10,
                    max_concurrency=16,
                )
                for _index in range(16)
            )
        )

        self.assertTrue(all(lease is not None for lease in leases))
        self.assertEqual(
            (await adapter.read_credential("primary", "contended.json")).in_flight,
            16,
        )
        self.assertEqual(store.maximum_active_writes, 1)

        store.maximum_active_writes = 0
        left, right = await asyncio.gather(
            adapter.acquire_credential("primary", "left.json", ttl_seconds=10, max_concurrency=1),
            adapter.acquire_credential("primary", "right.json", ttl_seconds=10, max_concurrency=1),
        )
        self.assertIsNotNone(left)
        self.assertIsNotNone(right)
        self.assertEqual(store.maximum_active_writes, 2)

    def test_invalid_keys_epochs_kinds_and_bounds_are_rejected(self) -> None:
        for invalid_key in (b"short", b"a" * 31, b"a" * 65):
            with self.subTest(invalid_key=len(invalid_key)):
                with self.assertRaises(ValueError):
                    RoutingCoordinationAdapter(
                        self.store,
                        identifier_key=invalid_key,
                        fencing_epoch=1,
                    )
        with self.assertRaises(ValueError):
            RoutingCoordinationAdapter(
                self.store,
                identifier_key=b"a" * 32,
                fencing_epoch=True,
            )


if __name__ == "__main__":
    unittest.main()
