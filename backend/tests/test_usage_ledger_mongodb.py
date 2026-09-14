"""Deterministic MongoDB driver-boundary tests for W4.14 usage storage."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.storage.mongodb_manager import MongoDBManager
from core.storage.usage_ledger_mongodb import MongoDBUsageLedgerRepository
from core.usage_ledger import (
    USAGE_LEDGER_SCHEMA_VERSION,
    UsageLedgerCorrupt,
    UsageLedgerEntry,
    UsageLedgerError,
)


def _entry() -> UsageLedgerEntry:
    return UsageLedgerEntry(
        schema_version=USAGE_LEDGER_SCHEMA_VERSION,
        event_id="use_" + ("a" * 32),
        occurred_at=1_777_777_777.0,
        credential_ref="account.json",
        request_id="request-1",
        model="gpt-5.6",
        provider="openai",
        status_code=200,
        success=True,
        input_tokens=10,
        output_tokens=2,
        total_tokens=12,
        cached_tokens=1,
        reasoning_tokens=0,
        estimated_input_tokens=10,
        estimated_tokens_saved=0,
        compressed_messages=0,
        quality_profile="balanced",
        quality_policy_revision=1,
        compression_reason="below_threshold",
        latency_ms=25,
        retry_count=0,
        cost_nanos=100,
        api_key_id="vk_enterprise",
    )


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


class _AsyncCursor:
    def __init__(self, documents):
        self._documents = documents

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for document in self._documents:
            yield document


class MongoDBUsageLedgerTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_creates_indexes_and_proves_transactions(self):
        ledger = Mock()
        ledger.create_indexes = AsyncMock()
        ledger.insert_one = AsyncMock()
        delete_result = Mock(deleted_count=1)
        ledger.delete_one = AsyncMock(return_value=delete_result)
        keys = Mock()
        keys.create_indexes = AsyncMock()
        session = Mock()

        async def with_transaction(callback):
            return await callback(session)

        session.with_transaction = AsyncMock(side_effect=with_transaction)
        client = Mock()
        client.start_session.return_value = _SessionContext(session)
        repository = MongoDBUsageLedgerRepository(client, ledger, keys)

        await repository.initialize()

        ledger.create_indexes.assert_awaited_once_with(unittest.mock.ANY)
        keys.create_indexes.assert_awaited_once_with(unittest.mock.ANY)
        session.with_transaction.assert_awaited_once()
        ledger.insert_one.assert_awaited_once()
        ledger.delete_one.assert_awaited_once()
        self.assertTrue(repository._initialized)

    async def test_initialize_rejects_non_transactional_deployment(self):
        ledger = Mock()
        ledger.create_indexes = AsyncMock()
        keys = Mock()
        keys.create_indexes = AsyncMock()
        session = Mock()
        session.with_transaction = AsyncMock(side_effect=RuntimeError("not a replica set"))
        client = Mock()
        client.start_session.return_value = _SessionContext(session)
        repository = MongoDBUsageLedgerRepository(client, ledger, keys)

        with self.assertRaisesRegex(UsageLedgerError, "transaction-capable"):
            await repository.initialize()
        self.assertFalse(repository._initialized)

    async def test_get_spend_awaits_async_aggregate_cursor(self):
        ledger = Mock()
        ledger.aggregate = AsyncMock(
            return_value=_AsyncCursor([{"cost": 250, "tokens": 12, "calls": 1}])
        )
        repository = MongoDBUsageLedgerRepository(Mock(), ledger, Mock())
        repository._initialized = True

        spend = await repository.get_spend(since=0, api_key_id="vk_enterprise")

        ledger.aggregate.assert_awaited_once()
        self.assertEqual((spend.cost_nanos, spend.total_tokens, spend.calls), (250, 12, 1))

    async def test_availability_probe_rejects_a_missing_collection(self):
        database = Mock()
        database.list_collection_names = AsyncMock(return_value=[])
        ledger = Mock(name="durable_usage_ledger")
        ledger.name = "durable_usage_ledger"
        ledger.database = database
        repository = MongoDBUsageLedgerRepository(Mock(), ledger, Mock())
        repository._initialized = True

        with self.assertRaises(UsageLedgerCorrupt):
            await repository.check_available()

    def test_strict_decode_checks_materialized_fields_against_payload(self):
        entry = _entry()
        repository = MongoDBUsageLedgerRepository(Mock(), Mock(), Mock())
        document = repository._usage_document(entry)
        self.assertEqual(repository._decode(document), entry)
        document["cost_nanos"] = 101
        with self.assertRaises(UsageLedgerCorrupt):
            repository._decode(document)

    async def test_manager_constructs_selected_repository(self):
        manager = MongoDBManager()
        manager._client = Mock()
        manager._db = MagicMock()
        manager._initialized = True
        repository = Mock()
        repository.initialize = AsyncMock()
        with (
            patch(
                "core.storage.usage_legacy_gate.require_external_usage_migration_ready",
                new=AsyncMock(),
            ),
            patch(
                "core.storage.usage_ledger_mongodb.MongoDBUsageLedgerRepository",
                return_value=repository,
            ) as repository_class,
        ):
            selected = await manager.create_usage_ledger_repository()

        repository_class.assert_called_once_with(
            manager._client,
            manager._db["durable_usage_ledger"],
            manager._db["durable_usage_budget_keys"],
        )
        repository.initialize.assert_awaited_once_with()
        self.assertIs(selected, repository)


if __name__ == "__main__":
    unittest.main()
