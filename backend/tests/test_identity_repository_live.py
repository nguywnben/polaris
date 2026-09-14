"""Opt-in live parity tests for shared durable identity backends.

Set ``POLARIS_TEST_POSTGRESQL_URI`` and/or ``POLARIS_TEST_MONGODB_URI`` to run these
tests. Each case creates a unique namespace and removes only that namespace.
"""

from __future__ import annotations

import os
import sys
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
from pymongo import AsyncMongoClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.storage.identity_mongodb import MongoDBIdentityRepository
from core.storage.identity_postgresql import PostgreSQLIdentityRepository
from tests.identity_repository_contract import IdentityRepositoryParityMixin

POSTGRESQL_URI = os.getenv("POLARIS_TEST_POSTGRESQL_URI", "").strip()
MONGODB_URI = os.getenv("POLARIS_TEST_MONGODB_URI", "").strip()
NOW = datetime(2026, 8, 27, 4, 0, tzinfo=timezone.utc)


@unittest.skipUnless(POSTGRESQL_URI, "POLARIS_TEST_POSTGRESQL_URI is not configured")
class LivePostgreSQLIdentityRepositoryTests(
    IdentityRepositoryParityMixin,
    unittest.IsolatedAsyncioTestCase,
):
    async def asyncSetUp(self):
        self.schema_name = f"polaris_identity_test_{uuid.uuid4().hex}"
        admin = await asyncpg.connect(POSTGRESQL_URI)
        try:
            await admin.execute(f'CREATE SCHEMA "{self.schema_name}"')
        finally:
            await admin.close()
        self.pool = await asyncpg.create_pool(
            POSTGRESQL_URI,
            min_size=1,
            max_size=4,
            server_settings={"search_path": self.schema_name},
        )
        self.repository = PostgreSQLIdentityRepository(self.pool, clock=lambda: NOW)
        await self.repository.initialize()

    async def asyncTearDown(self):
        await self.pool.close()
        admin = await asyncpg.connect(POSTGRESQL_URI)
        try:
            await admin.execute(f'DROP SCHEMA "{self.schema_name}" CASCADE')
        finally:
            await admin.close()

    async def restart_repository(self):
        restarted = PostgreSQLIdentityRepository(self.pool, clock=lambda: NOW)
        await restarted.initialize()
        return restarted


@unittest.skipUnless(MONGODB_URI, "POLARIS_TEST_MONGODB_URI is not configured")
class LiveMongoDBIdentityRepositoryTests(
    IdentityRepositoryParityMixin,
    unittest.IsolatedAsyncioTestCase,
):
    async def asyncSetUp(self):
        self.database_name = f"polaris_identity_test_{uuid.uuid4().hex}"
        self.client = AsyncMongoClient(MONGODB_URI)
        self.database = self.client[self.database_name]
        self.collection = self.database["management_identity_state"]
        self.repository = MongoDBIdentityRepository(self.collection, clock=lambda: NOW)
        await self.repository.initialize()

    async def asyncTearDown(self):
        await self.client.drop_database(self.database_name)
        await self.client.close()

    async def restart_repository(self):
        restarted = MongoDBIdentityRepository(self.collection, clock=lambda: NOW)
        await restarted.initialize()
        return restarted


if __name__ == "__main__":
    unittest.main()
