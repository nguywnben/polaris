"""SQLite contract tests for durable append-only audit events."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.audit import (
    AuditEventAlreadyExistsError,
    AuditQuery,
    AuditRetentionPolicy,
    create_audit_event,
)
from core.storage.audit_sqlite import SQLiteAuditRepository
from tests.support import workspace_temp_directory

FINGERPRINT_KEY = b"sqlite-audit-fingerprint-key-32bytes"
CURSOR_KEY = b"sqlite-audit-cursor-signing-key-32b"


def _event(
    *,
    event_index: int,
    occurred_at: datetime,
    action: str = "config.update",
    outcome: str = "succeeded",
):
    return create_audit_event(
        request_id=f"request-{event_index}",
        actor_type="panel_session",
        actor_identifier="owner@example.com",
        action=action,
        target_type="configuration",
        target_identifier=f"configuration-{event_index}",
        outcome=outcome,
        change_codes=("settings_changed",),
        fingerprint_key=FINGERPRINT_KEY,
        occurred_at=occurred_at,
    )


class SQLiteAuditRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = workspace_temp_directory()
        temp_path = self.temp_dir.__enter__()
        self.addCleanup(self.temp_dir.__exit__, None, None, None)
        self.db_path = Path(temp_path) / "credentials.db"
        self.repository = SQLiteAuditRepository(self.db_path, cursor_signing_key=CURSOR_KEY)
        await self.repository.initialize()

    async def test_initialize_is_additive_and_append_rejects_duplicate_event_ids(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("CREATE TABLE existing_config (value TEXT NOT NULL)")
            await db.execute("INSERT INTO existing_config(value) VALUES (?)", ("preserved",))
            await db.commit()

        await self.repository.initialize()
        event = _event(event_index=1, occurred_at=datetime.now(timezone.utc))
        await self.repository.append(event)

        with self.assertRaises(AuditEventAlreadyExistsError):
            await self.repository.append(event)
        async with aiosqlite.connect(self.db_path) as db:
            value = await (await db.execute("SELECT value FROM existing_config")).fetchone()
        self.assertEqual(value[0], "preserved")

    async def test_query_orders_newest_first_and_uses_a_stable_opaque_cursor(self):
        base = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
        events = [
            _event(event_index=index, occurred_at=base + timedelta(seconds=index))
            for index in range(3)
        ]
        for event in events:
            await self.repository.append(event)

        first = await self.repository.query(AuditQuery(page_size=2))
        second = await self.repository.query(AuditQuery(page_size=2, cursor=first.next_cursor))

        self.assertEqual(
            [item.event_id for item in first.events], [events[2].event_id, events[1].event_id]
        )
        self.assertIsNotNone(first.next_cursor)
        self.assertNotIn(events[1].occurred_at, first.next_cursor)
        self.assertEqual([item.event_id for item in second.events], [events[0].event_id])
        self.assertIsNone(second.next_cursor)

    async def test_query_composes_exact_filters_without_exposing_raw_identifiers(self):
        now = datetime.now(timezone.utc)
        succeeded = _event(event_index=1, occurred_at=now)
        failed = _event(
            event_index=2,
            occurred_at=now + timedelta(seconds=1),
            action="config.reset",
            outcome="failed",
        )
        await self.repository.append(succeeded)
        await self.repository.append(failed)

        page = await self.repository.query(
            AuditQuery(
                actor_fingerprints=(failed.actor_fingerprint,),
                actions=("config.reset",),
                target_fingerprints=(failed.target_fingerprint,),
                outcomes=("failed",),
                request_id="request-2",
                occurred_after=now,
                occurred_before=now + timedelta(seconds=2),
            )
        )

        self.assertEqual(page.events, (failed,))
        serialized = json.dumps([event.to_record() for event in page.events])
        self.assertNotIn("owner@example.com", serialized)
        self.assertNotIn("configuration-2", serialized)

    async def test_restart_preserves_events_and_policy_prune_is_the_only_removal_path(self):
        now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone(timedelta(hours=7)))
        utc_now = now.astimezone(timezone.utc)
        expired = _event(event_index=1, occurred_at=utc_now - timedelta(days=8))
        retained = _event(event_index=2, occurred_at=utc_now - timedelta(days=1))
        boundary = _event(
            event_index=3,
            occurred_at=utc_now - timedelta(days=7) + timedelta(minutes=1),
        )
        await self.repository.append(expired)
        await self.repository.append(retained)
        await self.repository.append(boundary)

        restarted = SQLiteAuditRepository(self.db_path, cursor_signing_key=CURSOR_KEY)
        await restarted.initialize()
        before = await restarted.query(AuditQuery())
        removed = await restarted.prune(
            AuditRetentionPolicy(retention_days=7, max_events=1000),
            now=now,
        )
        after = await restarted.query(AuditQuery())

        self.assertEqual(len(before.events), 3)
        self.assertEqual(removed, 1)
        self.assertEqual(after.events, (retained, boundary))

    async def test_corrupted_storage_record_fails_closed(self):
        event = _event(event_index=1, occurred_at=datetime.now(timezone.utc))
        await self.repository.append(event)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE audit_events SET target_fingerprint = ? WHERE event_id = ?",
                ("raw-secret-target", event.event_id),
            )
            await db.commit()

        with self.assertRaises(ValueError):
            await self.repository.query(AuditQuery())


if __name__ == "__main__":
    unittest.main()
