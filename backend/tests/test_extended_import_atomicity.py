"""Offline imports must never overwrite an existing credential identity."""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.credential_manager import CredentialManager
from core.provider_store import store_extended_credential
from core.storage.sqlite_manager import SQLiteManager
from support import workspace_temp_directory


class Adapter:
    def __init__(self, backend):
        self.backend = backend

    async def mutate_credential_pool(self, mode, planner):
        mutation = await self.backend.mutate_credential_pool(mode, planner)
        return dict(mutation.result)


class ExtendedImportAtomicityTests(unittest.IsolatedAsyncioTestCase):
    async def test_reimport_preserves_existing_catalog_label_and_verification(self):
        with (
            workspace_temp_directory() as directory,
            patch.dict(os.environ, {"CREDENTIALS_DIR": directory}),
        ):
            backend = SQLiteManager()
            await backend.initialize()
            try:
                with (
                    patch("core.provider_store.credential_manager", CredentialManager()),
                    patch(
                        "core.credential_manager.CredentialManager._ensure_initialized", AsyncMock()
                    ),
                    patch(
                        "core.credential_pool.get_storage_adapter",
                        AsyncMock(return_value=Adapter(backend)),
                    ),
                ):
                    existing = await store_extended_credential(
                        {
                            "provider": "kimi",
                            "api_key": "synthetic-atomic-key",
                            "credential_label": "Existing",
                        },
                        ["discovered-model"],
                    )
                    await backend.update_credential_state(
                        existing["filename"], {"disabled": True, "last_success": 1234.0}, "primary"
                    )
                    before = await backend.get_credential(existing["filename"], "primary")
                    state_before = await backend.get_credential_state(
                        existing["filename"], "primary"
                    )
                    imported = await store_extended_credential(
                        {
                            "provider": "kimi",
                            "api_key": "synthetic-atomic-key",
                            "credential_label": "Overwrite",
                        },
                        [],
                        file_import=True,
                    )
                    after = await backend.get_credential(existing["filename"], "primary")
                    state_after = await backend.get_credential_state(
                        existing["filename"], "primary"
                    )
                    updated = await store_extended_credential(
                        {
                            "provider": "kimi",
                            "api_key": "synthetic-atomic-key",
                            "credential_label": "Explicit update",
                        },
                        ["new-model"],
                    )
                self.assertEqual(imported["action"], "skipped")
                self.assertEqual(imported["filename"], existing["filename"])
                self.assertEqual(before, after)
                self.assertEqual(state_before, state_after)
                self.assertNotIn("validation_status", after)
                self.assertEqual(updated["action"], "updated")
                self.assertEqual(
                    (await backend.get_credential(existing["filename"], "primary"))["model_ids"],
                    ["new-model"],
                )
            finally:
                await backend.close()

    async def test_concurrent_file_imports_create_once_without_overwriting_winner(self):
        with (
            workspace_temp_directory() as directory,
            patch.dict(os.environ, {"CREDENTIALS_DIR": directory}),
        ):
            first, second = SQLiteManager(), SQLiteManager()
            await first.initialize()
            await second.initialize()
            try:
                with (
                    patch("core.provider_store.credential_manager", CredentialManager()),
                    patch(
                        "core.credential_manager.CredentialManager._ensure_initialized", AsyncMock()
                    ),
                    patch(
                        "core.credential_pool.get_storage_adapter",
                        AsyncMock(side_effect=[Adapter(first), Adapter(second)]),
                    ),
                ):
                    results = await asyncio.gather(
                        *[
                            store_extended_credential(
                                {
                                    "provider": "kimi",
                                    "api_key": "synthetic-atomic-key",
                                    "credential_label": label,
                                },
                                [],
                                file_import=True,
                            )
                            for label in ("First", "Second")
                        ]
                    )
                self.assertEqual(
                    sorted(result["action"] for result in results), ["created", "skipped"]
                )
                winner = next(
                    i for i, result in enumerate(results) if result["action"] == "created"
                )
                filename = results[winner]["filename"]
                self.assertEqual(await first.list_credentials("primary"), [filename])
                payload = await first.get_credential(filename, "primary")
                self.assertEqual(payload["credential_label"], ("First", "Second")[winner])
                self.assertEqual(payload["validation_status"], "unverified")
            finally:
                await first.close()
                await second.close()
