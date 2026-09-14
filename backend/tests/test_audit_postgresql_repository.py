"""PostgreSQL contract tests for durable append-only audit events."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.audit import (
    AuditEventAlreadyExistsError,
    AuditQuery,
    AuditRetentionPolicy,
    create_audit_event,
)
from core.storage.audit_postgresql import PostgreSQLAuditRepository

FINGERPRINT_KEY = b"postgres-audit-fingerprint-key-32bytes"
CURSOR_KEY = b"postgres-audit-cursor-signing-key-32b"


class _AcquireContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


class _TransactionContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _FakeConnection:
    def __init__(self):
        self.executions = []
        self.fetches = []
        self.rows = []
        self.counts = []
        self.execute_error = None

    async def execute(self, sql, *args):
        if self.execute_error is not None:
            raise self.execute_error
        self.executions.append((sql, args))
        return "OK"

    async def fetch(self, sql, *args):
        self.fetches.append((sql, args))
        return list(self.rows)

    async def fetchval(self, sql, *args):
        self.fetches.append((sql, args))
        return self.counts.pop(0)

    def transaction(self):
        return _TransactionContext()


class _FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _AcquireContext(self.connection)


def _event(index=1):
    return create_audit_event(
        request_id=f"request-{index}",
        actor_type="panel_session",
        actor_identifier="owner@example.com",
        action="config.update",
        target_type="configuration",
        target_identifier=f"configuration-{index}",
        outcome="succeeded",
        change_codes=("settings_changed",),
        fingerprint_key=FINGERPRINT_KEY,
        occurred_at=datetime(2026, 8, 24, 12, 0, index, tzinfo=timezone.utc),
    )


class PostgreSQLAuditRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = _FakeConnection()
        self.repository = PostgreSQLAuditRepository(
            _FakePool(self.connection), cursor_signing_key=CURSOR_KEY
        )
        await self.repository.initialize()

    async def test_initialize_is_additive_and_creates_bounded_query_indexes(self):
        schema = "\n".join(sql for sql, _args in self.connection.executions)

        self.assertIn("CREATE TABLE IF NOT EXISTS audit_events", schema)
        self.assertIn("idx_audit_events_order", schema)
        self.assertIn("idx_audit_events_request", schema)
        self.assertNotIn("DROP ", schema.upper())
        self.assertNotIn("TRUNCATE ", schema.upper())

    async def test_append_uses_placeholders_and_never_sends_raw_identifiers(self):
        event = _event()
        self.connection.executions.clear()

        await self.repository.append(event)

        sql, args = self.connection.executions[-1]
        self.assertIn("VALUES ($1, $2, $3", sql)
        self.assertEqual(args[1], event.event_id)
        self.assertNotIn("owner@example.com", repr(args))
        self.assertNotIn("configuration-1", repr(args))

    async def test_append_normalizes_unique_conflicts(self):
        self.connection.execute_error = asyncpg.UniqueViolationError("duplicate")

        with self.assertRaises(AuditEventAlreadyExistsError):
            await self.repository.append(_event())

    async def test_query_composes_parameterized_filters_and_revalidates_rows(self):
        event = _event()
        row = event.to_record()
        row["occurred_at"] = datetime.fromisoformat(row["occurred_at"])
        self.connection.rows = [row]

        page = await self.repository.query(
            AuditQuery(
                actions=("config.update",),
                target_fingerprints=(event.target_fingerprint,),
                outcomes=("succeeded",),
                page_size=10,
            )
        )

        sql, args = self.connection.fetches[-1]
        self.assertIn("action IN ($1)", sql)
        self.assertIn("target_fingerprint IN ($2)", sql)
        self.assertIn("outcome IN ($3)", sql)
        self.assertEqual(args[-1], 11)
        self.assertEqual(page.events, (event,))

    async def test_prune_uses_utc_cutoff_and_policy_bound_inside_a_transaction(self):
        self.connection.counts = [1200, 1100, 1000]
        now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone(timedelta(hours=7)))

        removed = await self.repository.prune(
            AuditRetentionPolicy(retention_days=7, max_events=1000),
            now=now,
        )

        delete_calls = [
            (sql, args)
            for sql, args in self.connection.executions
            if "DELETE FROM audit_events" in sql
        ]
        self.assertEqual(removed, 200)
        self.assertEqual(delete_calls[0][1][0].tzinfo, timezone.utc)
        self.assertEqual(delete_calls[1][1], (100,))


if __name__ == "__main__":
    unittest.main()
