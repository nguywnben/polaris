"""Lease and fail-closed contracts for shared device authorization flows."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.device_authorization_coordination import (
    DeviceAuthorizationBusyError,
    DeviceAuthorizationClaim,
    DeviceAuthorizationError,
    DeviceAuthorizationService,
    configure_device_authorization_service,
    get_device_authorization_service,
)
from core.state_store import InMemoryStateStore


class _RecordingStore(InMemoryStateStore):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.last_payload = b""

    async def compare_and_set(self, request):
        self.last_payload = request.payload
        return await super().compare_and_set(request)


class DeviceAuthorizationServiceTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        configure_device_authorization_service(None)

    def test_lifecycle_adapter_requires_explicit_injection(self) -> None:
        configure_device_authorization_service(None)
        with self.assertRaises(DeviceAuthorizationError):
            get_device_authorization_service()

        service = DeviceAuthorizationService(InMemoryStateStore(), key=b"z" * 32, fencing_epoch=1)
        configure_device_authorization_service(service)
        self.assertIs(get_device_authorization_service(), service)

    async def test_cross_client_release_consume_and_encryption(self) -> None:
        store = _RecordingStore()
        first = DeviceAuthorizationService(store, key=b"a" * 32, fencing_epoch=1)
        second = DeviceAuthorizationService(store, key=b"a" * 32, fencing_epoch=1)
        secret = b'{"device_auth_id":"device-secret","user_code":"CODE"}'

        flow_id = await first.create(secret, ttl_seconds=900)
        self.assertTrue(flow_id.startswith("codex_"))
        self.assertNotIn(b"device-secret", store.last_payload)

        claim = await second.claim(flow_id, lease_seconds=30)
        self.assertEqual(claim.payload, secret)
        with self.assertRaises(DeviceAuthorizationBusyError):
            await first.claim(flow_id, lease_seconds=30)

        await second.release(claim)
        final_claim = await first.claim(flow_id, lease_seconds=30)
        await first.consume(final_claim)
        with self.assertRaises(DeviceAuthorizationError):
            await second.claim(flow_id, lease_seconds=30)

    async def test_concurrent_claim_has_exactly_one_owner(self) -> None:
        store = InMemoryStateStore()
        first = DeviceAuthorizationService(store, key=b"b" * 32, fencing_epoch=1)
        second = DeviceAuthorizationService(store, key=b"b" * 32, fencing_epoch=1)
        flow_id = await first.create(b"proof", ttl_seconds=900)

        results = await asyncio.gather(
            first.claim(flow_id, lease_seconds=30),
            second.claim(flow_id, lease_seconds=30),
            return_exceptions=True,
        )

        self.assertEqual(sum(isinstance(item, DeviceAuthorizationClaim) for item in results), 1)
        self.assertEqual(sum(isinstance(item, DeviceAuthorizationBusyError) for item in results), 1)

    async def test_expiry_stale_epoch_and_dependency_loss_fail_closed(self) -> None:
        now = [1_000.0]
        store = InMemoryStateStore(clock=lambda: now[0])
        service = DeviceAuthorizationService(store, key=b"c" * 32, fencing_epoch=1)
        flow_id = await service.create(b"proof", ttl_seconds=60)
        now[0] += 61
        with self.assertRaises(DeviceAuthorizationError):
            await service.claim(flow_id, lease_seconds=30)

        stale = DeviceAuthorizationService(store, key=b"c" * 32, fencing_epoch=2)
        with self.assertRaises(DeviceAuthorizationError):
            await stale.create(b"proof", ttl_seconds=60)

        await store.close()
        with self.assertRaises(DeviceAuthorizationError):
            await service.create(b"proof", ttl_seconds=60)


if __name__ == "__main__":
    unittest.main()
