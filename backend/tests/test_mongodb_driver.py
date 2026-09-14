"""Contracts for the asynchronous MongoDB storage driver."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.credential_pool_mutation import CredentialPoolMutation
from core.storage.mongodb_manager import AsyncMongoClient, MongoDBManager


class MongoDBDriverTests(unittest.IsolatedAsyncioTestCase):
    def test_uses_pymongo_async_client(self):
        self.assertEqual(AsyncMongoClient.__module__, "pymongo.asynchronous.mongo_client")

    async def test_close_awaits_async_client_shutdown(self):
        manager = MongoDBManager()
        client = AsyncMock()
        manager._client = client
        manager._db = object()
        manager._initialized = True

        await manager.close()

        client.close.assert_awaited_once_with()
        self.assertIsNone(manager._client)
        self.assertIsNone(manager._db)
        self.assertFalse(manager._initialized)

    def test_driver_has_no_redis_acceleration_surface(self):
        manager = MongoDBManager()
        self.assertFalse(hasattr(manager, "_redis"))
        self.assertFalse(hasattr(manager, "_redis_enabled"))
        self.assertFalse(hasattr(manager, "_init_redis"))

    async def test_pool_mutation_uses_process_local_lock(self):
        manager = MongoDBManager()
        manager._initialized = True
        mutation = CredentialPoolMutation((), (), {"action": "none"})
        manager._mutate_credential_pool_in_session = AsyncMock(return_value=mutation)

        def planner(records):
            return CredentialPoolMutation((), (), {"action": "none"})

        result = await manager.mutate_credential_pool("primary", planner)

        self.assertIs(result, mutation)
        manager._mutate_credential_pool_in_session.assert_awaited_once_with("primary", planner)


if __name__ == "__main__":
    unittest.main()
