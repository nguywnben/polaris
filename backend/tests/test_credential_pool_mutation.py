"""Atomic credential-pool mutation contracts."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from core.credential_pool import upsert_credential_by_email
from core.credential_pool_mutation import (
    CredentialPoolMutation,
    CredentialPoolMutationError,
    CredentialPoolWrite,
    normalize_pool_mode,
)
from core.storage.postgresql_manager import PostgreSQLManager
from core.storage.sqlite_manager import SQLiteManager
from support import workspace_temp_directory


class SQLiteCredentialPoolMutationTests(unittest.IsolatedAsyncioTestCase):
    def test_invalid_pool_mode_fails_closed(self) -> None:
        with self.assertRaises(CredentialPoolMutationError):
            normalize_pool_mode("unexpected")

    async def test_mutation_commits_one_validated_plan_atomically(self):
        with workspace_temp_directory() as temp_dir:
            with patch.dict(os.environ, {"CREDENTIALS_DIR": temp_dir}):
                storage = SQLiteManager()
                await storage.initialize()
                try:
                    result = await storage.mutate_credential_pool(
                        "primary",
                        lambda records: CredentialPoolMutation(
                            writes=(
                                CredentialPoolWrite(
                                    filename="one.json",
                                    credential_data={"provider": "openai", "api_key": "secret"},
                                    user_email="owner@example.com",
                                ),
                            ),
                            deletes=(),
                            result={"action": "created"},
                        ),
                    )

                    self.assertEqual(result.result, {"action": "created"})
                    self.assertEqual(await storage.list_credentials("primary"), ["one.json"])
                    self.assertEqual(
                        (await storage.get_credential_state("one.json", "primary"))["user_email"],
                        "owner@example.com",
                    )
                finally:
                    await storage.close()

    async def test_invalid_plan_rolls_back_without_partial_write(self):
        with workspace_temp_directory() as temp_dir:
            with patch.dict(os.environ, {"CREDENTIALS_DIR": temp_dir}):
                storage = SQLiteManager()
                await storage.initialize()
                try:
                    with self.assertRaises(CredentialPoolMutationError):
                        await storage.mutate_credential_pool(
                            "primary",
                            lambda records: CredentialPoolMutation(
                                writes=(
                                    CredentialPoolWrite(
                                        filename="overlap.json",
                                        credential_data={"provider": "openai", "api_key": "secret"},
                                        user_email=None,
                                    ),
                                ),
                                deletes=("overlap.json",),
                                result={"action": "invalid"},
                            ),
                        )

                    self.assertEqual(await storage.list_credentials("primary"), [])
                finally:
                    await storage.close()

    async def test_two_clients_cannot_admit_duplicate_identity(self):
        class Adapter:
            def __init__(self, backend):
                self.backend = backend

            async def mutate_credential_pool(self, mode, planner):
                mutation = await self.backend.mutate_credential_pool(mode, planner)
                return dict(mutation.result)

            def __getattr__(self, name):
                return getattr(self.backend, name)

        with workspace_temp_directory() as temp_dir:
            with patch.dict(os.environ, {"CREDENTIALS_DIR": temp_dir}):
                first_storage = SQLiteManager()
                second_storage = SQLiteManager()
                await first_storage.initialize()
                await second_storage.initialize()
                incoming = {
                    "provider": "openai",
                    "credential_type": "oauth",
                    "user_email": "owner@example.com",
                    "refresh_token": "refresh",
                    "expiry": "2030-01-01T00:00:00+00:00",
                }
                try:
                    with patch(
                        "core.credential_pool.get_storage_adapter",
                        new=AsyncMock(
                            side_effect=[Adapter(first_storage), Adapter(second_storage)]
                        ),
                    ):
                        first, second = await asyncio.gather(
                            upsert_credential_by_email(
                                "first.json", dict(incoming), mode="primary"
                            ),
                            upsert_credential_by_email(
                                "second.json", dict(incoming), mode="primary"
                            ),
                        )

                    self.assertEqual({first["action"], second["action"]}, {"created", "skipped"})
                    created = next(
                        result for result in (first, second) if result["action"] == "created"
                    )
                    skipped = next(
                        result for result in (first, second) if result["action"] == "skipped"
                    )
                    self.assertEqual(skipped["filename"], created["filename"])
                    self.assertEqual(
                        await first_storage.list_credentials("primary"), [created["filename"]]
                    )
                    self.assertEqual(
                        await second_storage.list_credentials("primary"), [created["filename"]]
                    )
                finally:
                    await first_storage.close()
                    await second_storage.close()


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class PostgreSQLCredentialPoolMutationTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_backend_holds_table_gate_for_snapshot_and_writes(self):
        connection = AsyncMock()
        connection.transaction = MagicMock(return_value=_AsyncContext(None))
        connection.fetch.return_value = []
        connection.fetchrow.return_value = {"next_order": 0}
        pool = MagicMock()
        pool.acquire.return_value = _AsyncContext(connection)
        storage = PostgreSQLManager()
        storage._initialized = True
        storage._pool = pool

        mutation = await storage.mutate_credential_pool(
            "primary",
            lambda records: CredentialPoolMutation(
                writes=(CredentialPoolWrite("one.json", {"provider": "openai"}, None),),
                deletes=(),
                result={"action": "created"},
            ),
        )

        self.assertEqual(mutation.result, {"action": "created"})
        statements = [call.args[0] for call in connection.execute.await_args_list]
        self.assertTrue(any("LOCK TABLE primary_credentials" in sql for sql in statements))
        self.assertTrue(any("INSERT INTO primary_credentials" in sql for sql in statements))


if __name__ == "__main__":
    unittest.main()
