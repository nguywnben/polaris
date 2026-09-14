from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.credential_manager import _CredentialManagerSingleton
from core.identity import configure_oidc_transaction_coordination
from core.panel.auth_support import reset_authentication_attempt_service
from core.response_cache import response_cache, response_cache_coordinator
from core.runtime_lifecycle import RuntimeLifecycle, RuntimeState, close_runtime, initialize_runtime
from core.runtime_policy import RuntimePolicy
from core.state_store import InMemoryStateStore
from core.virtual_keys import virtual_key_manager


class RuntimePolicyTests(unittest.TestCase):
    def test_default_runtime_is_single_process_and_selects_one_storage_backend(self) -> None:
        policy = RuntimePolicy.from_environment({})

        self.assertEqual(policy.mode, "standalone")
        self.assertEqual((policy.workers, policy.replicas), (1, 1))
        self.assertEqual(policy.durable_backend, "sqlite")

        with self.assertRaisesRegex(RuntimeError, "standalone"):
            RuntimePolicy.from_environment({"POLARIS_RUNTIME_MODE": "coordinated"})
        with self.assertRaisesRegex(RuntimeError, "WORKERS"):
            RuntimePolicy.from_environment({"WORKERS": "2"})
        with self.assertRaisesRegex(RuntimeError, "POLARIS_REPLICA_COUNT"):
            RuntimePolicy.from_environment({"POLARIS_REPLICA_COUNT": "2"})
        with self.assertRaisesRegex(RuntimeError, "only one external durable backend"):
            RuntimePolicy.from_environment(
                {"POSTGRESQL_URI": "postgresql://database", "MONGODB_URI": "mongodb://database"}
            )


class RuntimeLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        await close_runtime()

    async def test_runtime_injects_one_in_memory_service_into_process_consumers(self) -> None:
        singleton = _CredentialManagerSingleton()
        lifecycle = RuntimeLifecycle(
            policy=RuntimePolicy.from_environment({}),
            store_factory=InMemoryStateStore,
        )

        with (
            patch("core.runtime_lifecycle.credential_manager", singleton),
            patch("core.runtime_lifecycle.configure_governance_coordination") as governance,
            patch("core.runtime_lifecycle.configure_authentication_attempt_service") as attempts,
            patch("core.runtime_lifecycle.reset_authentication_attempt_service"),
            patch("core.runtime_lifecycle.configure_oidc_transaction_coordination") as oidc,
            patch("core.runtime_lifecycle.configure_device_authorization_service") as device_auth,
            patch(
                "core.runtime_lifecycle.configure_credential_batch_coordination_service"
            ) as batch,
            patch(
                "core.runtime_lifecycle.configure_provider_authorization_service"
            ) as provider_auth,
            patch("core.runtime_lifecycle.virtual_key_manager.configure_coordination") as quota,
            patch("core.runtime_lifecycle.virtual_key_manager.reset_coordination"),
            patch(
                "core.runtime_lifecycle.response_cache_coordinator.configure_coordination"
            ) as cache,
        ):
            await lifecycle.start()

        service = lifecycle.coordination_service
        self.assertIsNotNone(service)
        self.assertIs(lifecycle.state, RuntimeState.READY)
        self.assertIs(singleton._routing_coordination._store, service)
        governance.assert_called_once_with(singleton._routing_coordination)
        self.assertIs(attempts.call_args.args[0]._coordination, service)
        oidc.assert_called_once_with(service, fencing_epoch=1)
        self.assertIs(device_auth.call_args.args[0]._coordination, service)
        self.assertIs(batch.call_args.args[0]._coordination, service)
        self.assertIs(provider_auth.call_args.args[0]._coordination, service)
        quota.assert_called_once_with(service, fencing_epoch=1)
        cache.assert_called_once_with(singleton._routing_coordination)
        self.assertEqual(lifecycle.session_initialization_kwargs["fencing_epoch"], 1)
        self.assertIs(lifecycle.session_initialization_kwargs["coordination"], service)
        self.assertTrue(await lifecycle.check_ready())

        with (
            patch(
                "core.runtime_lifecycle.reset_authentication_attempt_service",
                wraps=reset_authentication_attempt_service,
            ) as close_attempts,
            patch(
                "core.runtime_lifecycle.configure_oidc_transaction_coordination",
                wraps=configure_oidc_transaction_coordination,
            ) as close_oidc,
            patch.object(
                virtual_key_manager,
                "reset_coordination",
                wraps=virtual_key_manager.reset_coordination,
            ) as close_quota,
        ):
            await lifecycle.close()
        self.assertIs(lifecycle.state, RuntimeState.CLOSED)
        self.assertIsNone(singleton._routing_coordination)
        close_attempts.assert_called_once_with()
        close_oidc.assert_called_once_with(None)
        close_quota.assert_called_once_with()

    async def test_failed_probe_is_visible_and_can_recover(self) -> None:
        lifecycle = RuntimeLifecycle(policy=RuntimePolicy.from_environment({}))
        with (
            patch(
                "core.runtime_lifecycle.credential_manager.configure_routing_coordination",
                new=AsyncMock(),
            ),
            patch("core.runtime_lifecycle.configure_governance_coordination"),
            patch("core.runtime_lifecycle.configure_authentication_attempt_service"),
            patch("core.runtime_lifecycle.reset_authentication_attempt_service"),
            patch("core.runtime_lifecycle.configure_oidc_transaction_coordination"),
            patch("core.runtime_lifecycle.configure_device_authorization_service"),
            patch("core.runtime_lifecycle.configure_credential_batch_coordination_service"),
            patch("core.runtime_lifecycle.configure_provider_authorization_service"),
            patch("core.runtime_lifecycle.virtual_key_manager.configure_coordination"),
            patch("core.runtime_lifecycle.virtual_key_manager.reset_coordination"),
            patch("core.runtime_lifecycle.response_cache_coordinator.configure_coordination"),
            patch("core.runtime_lifecycle.configure_primary_session_coordinator"),
        ):
            await lifecycle.start()
        service = lifecycle.coordination_service
        service.read_coordination_time = AsyncMock(side_effect=RuntimeError("private detail"))

        self.assertFalse(await lifecycle.check_ready())
        self.assertEqual(lifecycle.health_snapshot()["failure_code"], "dependency_unavailable")
        self.assertNotIn("private detail", repr(lifecycle.health_snapshot()))
        service.read_coordination_time = AsyncMock(return_value=object())
        self.assertTrue(await lifecycle.check_ready())

    async def test_close_restores_a_usable_process_local_response_cache(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            await initialize_runtime()

        await close_runtime()
        response_cache.clear()
        self.assertTrue(
            await response_cache_coordinator.set(
                "after-runtime-close",
                (b"{}", "application/json"),
                60,
            )
        )
        self.assertEqual(
            await response_cache_coordinator.get("after-runtime-close"),
            (b"{}", "application/json"),
        )


if __name__ == "__main__":
    unittest.main()
