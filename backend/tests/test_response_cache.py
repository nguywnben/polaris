"""Tests for Response Caching Layer."""

from __future__ import annotations

import sys
import time
import unittest
from hashlib import sha256
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.response_cache import CoordinatedResponseCache, ResponseCache, generate_cache_key
from core.routing_coordination import (
    CACHE_SCOPE_EXACT,
    VALID_INVALIDATION_SCOPES,
    RoutingCoordinationAdapter,
)
from core.state_store import InMemoryStateStore


class ResponseCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cache = ResponseCache(default_ttl_seconds=2, max_entries=5)

    def test_cache_key_generation_deterministic(self) -> None:
        payload1 = {"messages": [{"role": "user", "content": "hello"}], "temperature": 0.7}
        payload2 = {"temperature": 0.7, "messages": [{"role": "user", "content": "hello"}]}

        key1 = generate_cache_key("gpt-4o", payload1)
        key2 = generate_cache_key("gpt-4o", payload2)
        key_stream = generate_cache_key("gpt-4o", payload1, stream=True)

        self.assertEqual(key1, key2)
        self.assertNotEqual(key1, key_stream)

    def test_cache_set_and_get(self) -> None:
        key = "test-hash-1"
        data = {"response": "world", "status_code": 200}
        self.cache.set(key, data)

        cached = self.cache.get(key)
        self.assertEqual(cached, data)

    def test_cache_expiration(self) -> None:
        key = "test-hash-exp"
        self.cache.set(key, {"value": 123}, ttl_seconds=1)
        self.assertEqual(self.cache.get(key), {"value": 123})

        time.sleep(1.1)
        self.assertIsNone(self.cache.get(key))

    def test_cache_lru_capacity(self) -> None:
        for i in range(5):
            self.cache.set(f"k{i}", f"v{i}")

        self.assertEqual(self.cache.size(), 5)
        # Adding 6th element should evict the oldest (k0)
        self.cache.set("k5", "v5")
        self.assertIsNone(self.cache.get("k0"))
        self.assertEqual(self.cache.get("k5"), "v5")


class CoordinatedResponseCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.now = 1_000.0
        store = InMemoryStateStore(clock=lambda: self.now)
        self.store = store
        self.first_local = ResponseCache(default_ttl_seconds=30, max_entries=5)
        self.second_local = ResponseCache(default_ttl_seconds=30, max_entries=5)
        first_adapter = RoutingCoordinationAdapter(store, identifier_key=b"c" * 32, fencing_epoch=1)
        second_adapter = RoutingCoordinationAdapter(
            store, identifier_key=b"c" * 32, fencing_epoch=1
        )
        self.first = CoordinatedResponseCache(self.first_local, first_adapter)
        self.second = CoordinatedResponseCache(self.second_local, second_adapter)

    async def test_small_body_is_encrypted_and_available_cross_replica(self) -> None:
        stored = await self.first.set("cache-key", (b'{"ok":true}', "application/json"), 30)
        self.assertTrue(stored)
        self.assertEqual(
            await self.first.get("cache-key"),
            (b'{"ok":true}', "application/json"),
        )
        self.assertEqual(
            await self.second.get("cache-key"),
            (b'{"ok":true}', "application/json"),
        )

    async def test_large_body_remains_local_only(self) -> None:
        content = b"x" * (16 * 1024)
        stored = await self.first.set("large-cache-key", (content, "text/plain"), 30)
        self.assertTrue(stored)
        self.assertEqual(await self.first.get("large-cache-key"), (content, "text/plain"))
        self.assertIsNone(await self.second.get("large-cache-key"))

    async def test_other_deployment_key_cannot_decrypt_shared_body(self) -> None:
        await self.first.set("cache-key", (b"trusted", "text/plain"), 30)
        foreign = CoordinatedResponseCache(
            ResponseCache(default_ttl_seconds=30, max_entries=5),
            RoutingCoordinationAdapter(
                self.store,
                identifier_key=b"d" * 32,
                fencing_epoch=1,
            ),
        )

        self.assertIsNone(await foreign.get("cache-key"))

    async def test_cross_replica_invalidation_prevents_stale_local_hit(self) -> None:
        await self.first.set("cache-key", (b"old", "text/plain"), 30)
        self.assertEqual(await self.first.get("cache-key"), (b"old", "text/plain"))

        generation = await self.second.invalidate()

        self.assertEqual(generation, 2)
        self.assertIsNone(await self.first.get("cache-key"))
        self.assertIsNone(self.first_local.get("cache-key"))

    async def test_digest_mismatch_evicts_local_body(self) -> None:
        await self.first.set("cache-key", (b"trusted", "text/plain"), 30)
        self.first_local.set("cache-key", (b"tampered", "text/plain"), 30)

        self.assertIsNone(await self.first.get("cache-key"))

    async def test_coordination_failure_is_a_miss_not_a_local_fallback(self) -> None:
        await self.first.set("cache-key", (b"trusted", "text/plain"), 30)
        await self.first._coordination._store.advance_epoch(1, "advance")

        self.assertIsNone(await self.first.get("cache-key"))

    async def test_epoch_advance_invalidates_every_cache_and_governance_scope(self) -> None:
        before = {
            scope: (await self.store.read_invalidation_generation(scope)).generation or 0
            for scope in VALID_INVALIDATION_SCOPES
        }

        await self.store.advance_epoch(1, "invalidate-all-on-advance")

        after = {
            scope: (await self.store.read_invalidation_generation(scope)).generation or 0
            for scope in VALID_INVALIDATION_SCOPES
        }
        self.assertEqual(after, {scope: value + 1 for scope, value in before.items()})

    def test_digest_binds_body_and_media_type(self) -> None:
        first = CoordinatedResponseCache.content_digest(b"value", "text/plain")
        second = CoordinatedResponseCache.content_digest(b"value", "application/json")
        self.assertEqual(len(first), sha256().digest_size * 2)
        self.assertNotEqual(first, second)

    async def test_invalidation_scope_is_fixed(self) -> None:
        self.assertEqual(self.first.scope, CACHE_SCOPE_EXACT)


if __name__ == "__main__":
    unittest.main()
