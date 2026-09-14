"""Application startup, shutdown, and singleton lifecycle contracts."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.credential_manager import _CredentialManagerSingleton
from main import app, lifespan


class CredentialManagerSingletonTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_initialization_creates_one_manager(self) -> None:
        singleton = _CredentialManagerSingleton()
        manager = MagicMock()

        async def initialize() -> None:
            await asyncio.sleep(0)

        manager.initialize = AsyncMock(side_effect=initialize)
        manager.close = AsyncMock()

        with patch("core.credential_manager.CredentialManager", return_value=manager) as factory:
            instances = await asyncio.gather(
                singleton._get_or_create(),
                singleton._get_or_create(),
                singleton._get_or_create(),
            )

        self.assertTrue(all(instance is manager for instance in instances))
        factory.assert_called_once_with()
        manager.initialize.assert_awaited_once_with()

        await singleton.close()
        manager.close.assert_awaited_once_with()
        self.assertIsNone(singleton._instance)


class ApplicationLifecycleTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _configured_module() -> MagicMock:
        config_module = MagicMock()
        config_module.init_config = AsyncMock()
        config_module.get_log_config = AsyncMock(
            return_value={"level": "info", "max_mb": 10, "backup_count": 3}
        )
        config_module.has_password_configured = AsyncMock(return_value=True)
        return config_module

    async def test_shutdown_closes_runtime_manager_and_storage(self) -> None:
        config_module = self._configured_module()
        runtime_log_patcher = patch("main.log")
        runtime_log = runtime_log_patcher.start()
        self.addCleanup(runtime_log_patcher.stop)

        with (
            patch.dict(sys.modules, {"config": config_module}),
            patch("main.initialize_runtime", new=AsyncMock()),
            patch("main.close_runtime", new=AsyncMock()) as close_runtime,
            patch("main.get_runtime_session_kwargs", return_value={}),
            patch("main.credential_manager._get_or_create", new=AsyncMock()),
            patch("main.initialize_audit_service", new=AsyncMock()),
            patch("main.initialize_session_service", new=AsyncMock()),
            patch("main.close_session_service", new=AsyncMock()) as close_session,
            patch("main.close_oidc_login_service", new=AsyncMock()) as close_oidc,
            patch("main.initialize_request_trace_service", new=AsyncMock()),
            patch("main.close_request_trace_service", new=AsyncMock()),
            patch("main.initialize_usage_ledger_service", new=AsyncMock()),
            patch("main.close_usage_ledger_service", new=AsyncMock()) as close_usage,
            patch("main.close_audit_service", new=AsyncMock()) as close_audit,
            patch("main.credential_manager.close", new=AsyncMock()) as close_manager,
            patch("main.close_storage_adapter", new=AsyncMock()) as close_storage,
            patch("main.keep_alive_service.start", new=AsyncMock()),
            patch("main.keep_alive_service.stop", new=AsyncMock()) as stop_keep_alive,
            patch("main.shutdown_all_tasks", new=AsyncMock()) as shutdown_tasks,
        ):
            close_usage.side_effect = RuntimeError("shutdown-secret")
            async with lifespan(app):
                pass

        stop_keep_alive.assert_awaited_once_with()
        shutdown_tasks.assert_awaited_once_with(timeout=10.0)
        close_usage.assert_awaited_once_with()
        close_audit.assert_awaited_once_with()
        close_session.assert_awaited_once_with()
        close_oidc.assert_awaited_once_with()
        close_manager.assert_awaited_once_with()
        close_runtime.assert_awaited_once_with()
        close_storage.assert_awaited_once_with()
        rendered_logs = " ".join(str(call) for call in runtime_log.mock_calls)
        self.assertNotIn("shutdown-secret", rendered_logs)
        self.assertIn("RuntimeError", rendered_logs)

    async def test_configuration_failure_aborts_startup(self) -> None:
        config_module = MagicMock()
        config_module.init_config = AsyncMock(side_effect=RuntimeError("database secret"))
        runtime_log_patcher = patch("main.log")
        runtime_log = runtime_log_patcher.start()
        self.addCleanup(runtime_log_patcher.stop)

        with (
            patch.dict(sys.modules, {"config": config_module}),
            patch("main.initialize_runtime", new=AsyncMock()) as initialize_runtime,
            patch("main.credential_manager._get_or_create", new=AsyncMock()) as initialize_manager,
        ):
            with self.assertRaisesRegex(RuntimeError, "Configuration initialization failed"):
                async with lifespan(app):
                    pass

        initialize_runtime.assert_not_awaited()
        initialize_manager.assert_not_awaited()
        rendered_logs = " ".join(str(call) for call in runtime_log.mock_calls)
        self.assertNotIn("database secret", rendered_logs)
        self.assertIn("RuntimeError", rendered_logs)

    async def test_audit_failure_closes_runtime_before_aborting(self) -> None:
        config_module = self._configured_module()

        with (
            patch.dict(sys.modules, {"config": config_module}),
            patch("main.initialize_runtime", new=AsyncMock()),
            patch("main.close_runtime", new=AsyncMock()) as close_runtime,
            patch("main.get_runtime_session_kwargs", return_value={}),
            patch("main.credential_manager._get_or_create", new=AsyncMock()),
            patch(
                "main.initialize_audit_service",
                new=AsyncMock(side_effect=RuntimeError("secret storage detail")),
            ),
            patch("main.credential_manager.close", new=AsyncMock()) as close_manager,
            patch("main.close_storage_adapter", new=AsyncMock()) as close_storage,
            patch("main.keep_alive_service.start", new=AsyncMock()) as start_keep_alive,
        ):
            with self.assertRaisesRegex(RuntimeError, "Audit service initialization failed"):
                async with lifespan(app):
                    pass

        close_manager.assert_awaited_once_with()
        close_runtime.assert_awaited_once_with()
        close_storage.assert_awaited_once_with()
        start_keep_alive.assert_not_awaited()

    async def test_session_failure_closes_runtime_before_aborting(self) -> None:
        config_module = self._configured_module()

        with (
            patch.dict(sys.modules, {"config": config_module}),
            patch("main.initialize_runtime", new=AsyncMock()),
            patch("main.close_runtime", new=AsyncMock()) as close_runtime,
            patch("main.get_runtime_session_kwargs", return_value={}),
            patch("main.credential_manager._get_or_create", new=AsyncMock()),
            patch("main.initialize_audit_service", new=AsyncMock()),
            patch(
                "main.initialize_session_service",
                new=AsyncMock(side_effect=RuntimeError("session master secret")),
            ),
            patch("main.close_audit_service", new=AsyncMock()) as close_audit,
            patch("main.credential_manager.close", new=AsyncMock()) as close_manager,
            patch("main.close_storage_adapter", new=AsyncMock()) as close_storage,
            patch("main.initialize_request_trace_service", new=AsyncMock()) as initialize_traces,
            patch("main.keep_alive_service.start", new=AsyncMock()) as start_keep_alive,
        ):
            with self.assertRaisesRegex(RuntimeError, "Session service initialization failed"):
                async with lifespan(app):
                    pass

        close_audit.assert_awaited_once_with()
        close_manager.assert_awaited_once_with()
        close_runtime.assert_awaited_once_with()
        close_storage.assert_awaited_once_with()
        initialize_traces.assert_not_awaited()
        start_keep_alive.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
