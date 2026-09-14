"""SQLite integration tests for smart-routing metadata."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from core.smart_routing import SmartCredentialRouter
from core.storage.sqlite_manager import SQLiteManager
from support import workspace_temp_directory


class SQLiteRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_hint_batch_preserves_the_exact_call_increment(self):
        with workspace_temp_directory() as temp_dir:
            with patch.dict(os.environ, {"CREDENTIALS_DIR": temp_dir}):
                storage = SQLiteManager()
                await storage.initialize()
                try:
                    await storage.store_credential(
                        "batched.json", {"token": "a", "project_id": "a"}, mode="primary"
                    )

                    await storage.record_success(
                        "batched.json",
                        mode="primary",
                        model_name="model-a",
                        call_increment=7,
                    )

                    state = await storage.get_credential_state("batched.json", mode="primary")
                    self.assertEqual(state["call_count"], 7)
                finally:
                    await storage.close()

    async def test_failed_attempt_updates_fairness_and_changes_selection(self):
        with workspace_temp_directory() as temp_dir:
            with patch.dict(os.environ, {"CREDENTIALS_DIR": temp_dir}):
                storage = SQLiteManager()
                await storage.initialize()
                try:
                    await storage.store_credential(
                        "a.json", {"token": "a", "project_id": "a"}, mode="primary"
                    )
                    await storage.store_credential(
                        "b.json", {"token": "b", "project_id": "b"}, mode="primary"
                    )
                    await storage.update_credential_state(
                        "a.json", {"last_success": 100.0}, mode="primary"
                    )
                    await storage.update_credential_state(
                        "b.json", {"last_success": 100.0}, mode="primary"
                    )
                    await storage.record_failure("a.json", mode="primary")

                    state = await storage.get_credential_state("a.json", mode="primary")
                    router = SmartCredentialRouter(clock=lambda: 100.0)
                    selected = await router.acquire(storage, mode="primary", model_name="model-a")

                    self.assertEqual(state["call_count"], 1)
                    self.assertEqual(selected[0], "b.json")
                finally:
                    await storage.close()


if __name__ == "__main__":
    unittest.main()
