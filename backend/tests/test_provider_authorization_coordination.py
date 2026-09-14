"""Security contracts for shared one-time provider OAuth transactions."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.provider_authorization_coordination import (
    ProviderAuthorizationError,
    ProviderAuthorizationService,
    configure_provider_authorization_service,
    get_provider_authorization_service,
)
from core.state_store import InMemoryStateStore


class _RecordingStore(InMemoryStateStore):
    def __init__(self) -> None:
        super().__init__()
        self.last_payload = b""

    async def create_oidc_transaction(self, request):
        self.last_payload = request.payload
        return await super().create_oidc_transaction(request)


class ProviderAuthorizationServiceTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        configure_provider_authorization_service(None)

    def test_process_adapter_requires_explicit_lifecycle_injection(self) -> None:
        configure_provider_authorization_service(None)
        with self.assertRaises(ProviderAuthorizationError):
            get_provider_authorization_service()

        service = ProviderAuthorizationService(InMemoryStateStore(), key=b"z" * 32, fencing_epoch=1)
        configure_provider_authorization_service(service)
        self.assertIs(get_provider_authorization_service(), service)

    async def test_two_clients_share_encrypted_provider_bound_one_time_state(self) -> None:
        store = _RecordingStore()
        first = ProviderAuthorizationService(store, key=b"a" * 32, fencing_epoch=1)
        second = ProviderAuthorizationService(store, key=b"a" * 32, fencing_epoch=1)
        proof = b'{"client_id":"client","code_verifier":"secret-verifier"}'

        state = await first.create("claude", proof, ttl_seconds=900)
        consumed = await second.consume("claude", state)

        self.assertTrue(state.startswith("claude_"))
        self.assertEqual(consumed, proof)
        self.assertNotIn(b"secret-verifier", store.last_payload)
        with self.assertRaises(ProviderAuthorizationError):
            await first.consume("claude", state)

    async def test_cross_provider_substitution_and_corrupt_state_fail_closed(self) -> None:
        store = InMemoryStateStore()
        service = ProviderAuthorizationService(store, key=b"b" * 32, fencing_epoch=1)
        state = await service.create("xai", b"opaque", ttl_seconds=900)

        for provider, candidate in (
            ("claude", state),
            ("xai", "xai_invalid"),
            ("unknown", state),
        ):
            with self.subTest(provider=provider, state=candidate):
                with self.assertRaisesRegex(
                    ProviderAuthorizationError,
                    "Provider authorization transaction failed",
                ):
                    await service.consume(provider, candidate)

        self.assertEqual(await service.consume("xai", state), b"opaque")

    async def test_concurrent_consumers_have_exactly_one_winner(self) -> None:
        store = InMemoryStateStore()
        first = ProviderAuthorizationService(store, key=b"c" * 32, fencing_epoch=1)
        second = ProviderAuthorizationService(store, key=b"c" * 32, fencing_epoch=1)
        state = await first.create("claude", b"proof", ttl_seconds=900)

        results = await asyncio.gather(
            first.consume("claude", state),
            second.consume("claude", state),
            return_exceptions=True,
        )

        self.assertEqual(sum(result == b"proof" for result in results), 1)
        self.assertEqual(
            sum(isinstance(result, ProviderAuthorizationError) for result in results), 1
        )

    async def test_capacity_stale_epoch_and_dependency_loss_fail_closed(self) -> None:
        limited = InMemoryStateStore(_oidc_transaction_limit_for_testing=1)
        service = ProviderAuthorizationService(limited, key=b"d" * 32, fencing_epoch=1)
        await service.create("xai", b"first", ttl_seconds=900)
        with self.assertRaises(ProviderAuthorizationError):
            await service.create("xai", b"second", ttl_seconds=900)

        stale = ProviderAuthorizationService(limited, key=b"d" * 32, fencing_epoch=2)
        with self.assertRaises(ProviderAuthorizationError):
            await stale.create("claude", b"stale", ttl_seconds=900)

        await limited.close()
        with self.assertRaises(ProviderAuthorizationError):
            await service.consume("xai", "xai_" + "A" * 43)

    async def test_constructor_and_payload_bounds_are_closed(self) -> None:
        store = InMemoryStateStore()
        for key, epoch in ((b"short", 1), (b"e" * 32, 0)):
            with self.subTest(key_length=len(key), epoch=epoch):
                with self.assertRaises(ProviderAuthorizationError):
                    ProviderAuthorizationService(store, key=key, fencing_epoch=epoch)
        service = ProviderAuthorizationService(store, key=b"e" * 32, fencing_epoch=1)
        with self.assertRaises(ProviderAuthorizationError):
            await service.create("claude", b"x" * 8193, ttl_seconds=900)


if __name__ == "__main__":
    unittest.main()
