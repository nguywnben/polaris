"""Deterministic PostgreSQL driver-boundary tests for W4.14 usage storage."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.storage.postgresql_manager import PostgreSQLManager
from core.storage.usage_ledger_postgresql import PostgreSQLUsageLedgerRepository
from core.usage_ledger import USAGE_LEDGER_SCHEMA_VERSION, UsageLedgerCorrupt, UsageLedgerEntry


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


_SCHEMA_TYPES = {
    "record_id": ("text", "NO"),
    "kind": ("text", "NO"),
    "state": ("text", "NO"),
    "revision": ("integer", "NO"),
    "key_id": ("text", "NO"),
    "created_at": ("double precision", "NO"),
    "expires_at": ("double precision", "YES"),
    "transitioned_at": ("double precision", "YES"),
    "estimated_cost_nanos": ("bigint", "YES"),
    "daily_budget_nanos": ("bigint", "YES"),
    "monthly_budget_nanos": ("bigint", "YES"),
    "event_id": ("text", "YES"),
    "occurred_at": ("double precision", "YES"),
    "credential_ref": ("text", "YES"),
    "provider": ("text", "YES"),
    "success": ("boolean", "YES"),
    "total_tokens": ("bigint", "YES"),
    "cost_nanos": ("bigint", "YES"),
    "api_key_id": ("text", "YES"),
    "payload": ("jsonb", "NO"),
}


def _schema_rows(**type_overrides):
    return [
        {
            "table_name": "durable_usage_budget_keys",
            "column_name": "key_id",
            "data_type": "text",
            "is_nullable": "NO",
        },
        *[
            {
                "table_name": "durable_usage_ledger",
                "column_name": name,
                "data_type": type_overrides.get(name, data_type),
                "is_nullable": nullable,
            }
            for name, (data_type, nullable) in _SCHEMA_TYPES.items()
        ],
    ]


def _constraint_rows():
    return [
        {
            "table_name": "durable_usage_budget_keys",
            "contype": "p",
            "definition": "PRIMARY KEY (key_id)",
        },
        {
            "table_name": "durable_usage_ledger",
            "contype": "p",
            "definition": "PRIMARY KEY (record_id)",
        },
        {
            "table_name": "durable_usage_ledger",
            "contype": "u",
            "definition": "UNIQUE (event_id)",
        },
        {
            "table_name": "durable_usage_ledger",
            "contype": "c",
            "definition": "CHECK ((kind = ANY (ARRAY['usage'::text, 'reservation'::text])))",
        },
    ]


def _index_rows():
    return [
        {
            "indexname": "idx_durable_usage_pg_spend",
            "indexdef": "CREATE INDEX idx_durable_usage_pg_spend ON durable_usage_ledger USING btree (api_key_id, occurred_at) WHERE (cost_nanos IS NOT NULL)",
        },
        {
            "indexname": "idx_durable_usage_pg_budget",
            "indexdef": "CREATE INDEX idx_durable_usage_pg_budget ON durable_usage_ledger USING btree (key_id, state, expires_at) WHERE (kind = 'reservation'::text)",
        },
        {
            "indexname": "idx_durable_usage_pg_credential",
            "indexdef": "CREATE INDEX idx_durable_usage_pg_credential ON durable_usage_ledger USING btree (credential_ref, occurred_at) WHERE (occurred_at IS NOT NULL)",
        },
    ]


class PostgreSQLUsageLedgerTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_creates_schema_and_indexes(self):
        connection = AsyncMock()
        fetch_results = iter([_schema_rows(), _constraint_rows(), _index_rows()])

        async def fetch_after_schema_creation(*_args):
            self.assertEqual(connection.execute.await_count, 5)
            return next(fetch_results)

        connection.fetch.side_effect = fetch_after_schema_creation
        acquire = AsyncMock()
        acquire.__aenter__.return_value = connection
        pool = Mock()
        pool.acquire.return_value = acquire
        repository = PostgreSQLUsageLedgerRepository(pool)

        await repository.initialize()

        self.assertTrue(repository._initialized)
        self.assertEqual(connection.execute.await_count, 5)
        statements = " ".join(call.args[0] for call in connection.execute.await_args_list)
        self.assertIn("durable_usage_budget_keys", statements)
        self.assertIn("durable_usage_ledger", statements)

    async def test_initialize_projects_catalog_constraint_type_as_text(self):
        connection = AsyncMock()
        connection.fetch.side_effect = [_schema_rows(), _constraint_rows(), _index_rows()]
        acquire = AsyncMock()
        acquire.__aenter__.return_value = connection
        pool = Mock()
        pool.acquire.return_value = acquire

        await PostgreSQLUsageLedgerRepository(pool).initialize()

        constraint_query = connection.fetch.await_args_list[1].args[0]
        self.assertIn("constraint_ref.contype::text AS contype", constraint_query)

    async def test_initialize_rejects_an_existing_incompatible_schema(self):
        connection = AsyncMock()
        connection.fetch.side_effect = [
            [{"column_name": "record_id"}],
            _constraint_rows(),
            _index_rows(),
        ]
        acquire = AsyncMock()
        acquire.__aenter__.return_value = connection
        pool = Mock()
        pool.acquire.return_value = acquire
        repository = PostgreSQLUsageLedgerRepository(pool)

        with self.assertRaises(UsageLedgerCorrupt):
            await repository.initialize()

    async def test_initialize_rejects_wrong_column_type(self):
        connection = AsyncMock()
        connection.fetch.side_effect = [
            _schema_rows(revision="text"),
            _constraint_rows(),
            _index_rows(),
        ]
        acquire = AsyncMock()
        acquire.__aenter__.return_value = connection
        pool = Mock()
        pool.acquire.return_value = acquire

        with self.assertRaises(UsageLedgerCorrupt):
            await PostgreSQLUsageLedgerRepository(pool).initialize()

    async def test_availability_probe_touches_the_ledger_relation(self):
        connection = AsyncMock()
        connection.fetchval.return_value = 0
        acquire = AsyncMock()
        acquire.__aenter__.return_value = connection
        pool = Mock()
        pool.acquire.return_value = acquire
        repository = PostgreSQLUsageLedgerRepository(pool)
        repository._initialized = True

        await repository.check_available()

        self.assertIn("durable_usage_ledger", connection.fetchval.await_args.args[0])

    def test_strict_decode_checks_materialized_columns_against_payload(self):
        entry = _entry()
        repository = PostgreSQLUsageLedgerRepository(Mock())
        row = {
            "record_id": entry.event_id,
            "kind": "usage",
            "state": "committed",
            "revision": 1,
            "key_id": entry.api_key_id,
            "created_at": entry.occurred_at,
            "expires_at": None,
            "transitioned_at": None,
            "estimated_cost_nanos": None,
            "daily_budget_nanos": None,
            "monthly_budget_nanos": None,
            "event_id": entry.event_id,
            "occurred_at": entry.occurred_at,
            "credential_ref": entry.credential_ref,
            "provider": entry.provider,
            "success": entry.success,
            "total_tokens": entry.total_tokens,
            "cost_nanos": entry.cost_nanos,
            "api_key_id": entry.api_key_id,
            "payload": entry.to_record(),
        }
        self.assertEqual(repository._decode(row), entry)
        row["cost_nanos"] = 101
        with self.assertRaises(UsageLedgerCorrupt):
            repository._decode(row)

    async def test_manager_constructs_selected_repository(self):
        manager = PostgreSQLManager()
        manager._pool = Mock()
        manager._initialized = True
        repository = Mock()
        repository.initialize = AsyncMock()
        with (
            patch(
                "core.storage.usage_legacy_gate.require_external_usage_migration_ready",
                new=AsyncMock(),
            ),
            patch(
                "core.storage.usage_ledger_postgresql.PostgreSQLUsageLedgerRepository",
                return_value=repository,
            ) as repository_class,
        ):
            selected = await manager.create_usage_ledger_repository()

        repository_class.assert_called_once_with(manager._pool)
        repository.initialize.assert_awaited_once_with()
        self.assertIs(selected, repository)


if __name__ == "__main__":
    unittest.main()
