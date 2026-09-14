from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.governance_coordination import (
    GovernanceGenerationObserver,
    configure_governance_coordination,
    publish_governance_invalidation,
)
from core.routing_coordination import (
    GOVERNANCE_SCOPE_CONFIG,
    GOVERNANCE_SCOPE_CREDENTIALS,
    GOVERNANCE_SCOPE_MODEL_CATALOG,
    GOVERNANCE_SCOPE_VIRTUAL_KEYS,
    RoutingCoordinationAdapter,
)
from core.state_store import InMemoryStateStore
from core.storage_adapter import StorageAdapter


class _Backend:
    async def set_config(self, key, value):
        return True

    async def delete_config(self, key):
        return True

    async def store_credential(self, filename, credential_data, mode):
        return True

    async def update_credential_state(self, filename, state_updates, mode):
        return True

    async def delete_credential(self, filename, mode):
        return True


class GovernanceCoordinationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.store = InMemoryStateStore(clock=lambda: 1_000.0)
        self.adapter = RoutingCoordinationAdapter(
            self.store, identifier_key=b"g" * 32, fencing_epoch=1
        )
        configure_governance_coordination(self.adapter)

    async def asyncTearDown(self) -> None:
        configure_governance_coordination(None)

    async def test_each_owner_observes_initial_and_published_generation(self) -> None:
        first = GovernanceGenerationObserver(GOVERNANCE_SCOPE_CONFIG)
        second = GovernanceGenerationObserver(GOVERNANCE_SCOPE_CONFIG)
        first_reload = AsyncMock()
        second_reload = AsyncMock()

        self.assertTrue(await first.synchronize(first_reload))
        self.assertTrue(await second.synchronize(second_reload))
        self.assertFalse(await first.synchronize(first_reload))
        await publish_governance_invalidation(GOVERNANCE_SCOPE_CONFIG)
        self.assertTrue(await first.synchronize(first_reload))
        self.assertTrue(await second.synchronize(second_reload))

        self.assertEqual(first_reload.await_count, 2)
        self.assertEqual(second_reload.await_count, 2)

    async def test_storage_mutations_publish_only_after_success(self) -> None:
        adapter = StorageAdapter()
        adapter._backend = _Backend()
        adapter._initialized = True
        with patch(
            "core.governance_coordination.publish_governance_invalidation",
            new=AsyncMock(),
        ) as publish:
            self.assertTrue(await adapter.set_config("virtual_keys", []))
            self.assertTrue(await adapter.set_config("routing_strategy", "balanced"))
            self.assertTrue(await adapter.store_credential("a.json", {}, mode="primary"))
            self.assertTrue(
                await adapter.update_credential_state("a.json", {"disabled": True}, mode="primary")
            )
            self.assertTrue(await adapter.delete_credential("a.json", mode="primary"))

        scopes = [call.args[0] for call in publish.await_args_list]
        self.assertEqual(
            scopes,
            [
                GOVERNANCE_SCOPE_VIRTUAL_KEYS,
                GOVERNANCE_SCOPE_CONFIG,
                GOVERNANCE_SCOPE_CREDENTIALS,
                GOVERNANCE_SCOPE_MODEL_CATALOG,
                GOVERNANCE_SCOPE_CREDENTIALS,
                GOVERNANCE_SCOPE_MODEL_CATALOG,
                GOVERNANCE_SCOPE_CREDENTIALS,
                GOVERNANCE_SCOPE_MODEL_CATALOG,
            ],
        )

    async def test_storage_adapter_exposes_backend_config_cache_refresh(self) -> None:
        backend = AsyncMock()
        adapter = StorageAdapter()
        adapter._backend = backend
        adapter._initialized = True

        await adapter.reload_config_cache()

        backend.reload_config_cache.assert_awaited_once_with()

    async def test_unconfigured_observer_is_a_noop(self) -> None:
        configure_governance_coordination(None)
        callback = AsyncMock()
        observer = GovernanceGenerationObserver(GOVERNANCE_SCOPE_CONFIG)
        self.assertFalse(await observer.synchronize(callback))
        self.assertIsNone(await publish_governance_invalidation(GOVERNANCE_SCOPE_CONFIG))
        callback.assert_not_awaited()

    async def test_rebinding_same_generation_still_invalidates_each_owner(self) -> None:
        observer = GovernanceGenerationObserver(GOVERNANCE_SCOPE_CONFIG)
        callback = AsyncMock()
        self.assertTrue(await observer.synchronize(callback))
        replacement = RoutingCoordinationAdapter(
            InMemoryStateStore(clock=lambda: 1_000.0),
            identifier_key=b"h" * 32,
            fencing_epoch=1,
        )
        configure_governance_coordination(replacement)

        self.assertTrue(await observer.synchronize(callback))
        self.assertEqual(callback.await_count, 2)

    async def test_repeated_reads_share_one_bounded_generation_poll(self) -> None:
        coordination = AsyncMock()
        coordination.current_generation.return_value = 1
        configure_governance_coordination(coordination)
        observer = GovernanceGenerationObserver(GOVERNANCE_SCOPE_CONFIG)
        callback = AsyncMock()

        self.assertTrue(await observer.synchronize(callback))
        for _ in range(20):
            self.assertFalse(await observer.synchronize(callback))

        coordination.current_generation.assert_awaited_once_with(GOVERNANCE_SCOPE_CONFIG)
        callback.assert_awaited_once_with()

    async def test_forced_read_bypasses_poll_window_after_a_cache_miss(self) -> None:
        coordination = AsyncMock()
        coordination.current_generation.side_effect = (1, 2)
        configure_governance_coordination(coordination)
        observer = GovernanceGenerationObserver(GOVERNANCE_SCOPE_VIRTUAL_KEYS)
        callback = AsyncMock()

        self.assertTrue(await observer.synchronize(callback))
        self.assertFalse(await observer.synchronize(callback))
        self.assertTrue(await observer.synchronize(callback, force=True))

        self.assertEqual(coordination.current_generation.await_count, 2)
        self.assertEqual(callback.await_count, 2)

    async def test_forced_read_keeps_cache_when_generation_is_unchanged(self) -> None:
        coordination = AsyncMock()
        coordination.current_generation.return_value = 1
        configure_governance_coordination(coordination)
        observer = GovernanceGenerationObserver(GOVERNANCE_SCOPE_VIRTUAL_KEYS)
        callback = AsyncMock()

        self.assertTrue(await observer.synchronize(callback))
        self.assertFalse(await observer.synchronize(callback, force=True))

        self.assertEqual(coordination.current_generation.await_count, 2)
        callback.assert_awaited_once_with()
