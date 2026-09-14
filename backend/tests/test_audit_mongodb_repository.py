"""MongoDB contract tests for durable append-only audit events."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pymongo.errors import DuplicateKeyError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.audit import (
    AuditEventAlreadyExistsError,
    AuditQuery,
    AuditRetentionPolicy,
    create_audit_event,
    decode_audit_cursor,
)
from core.storage.audit_mongodb import MongoAuditRepository

FINGERPRINT_KEY = b"mongodb-audit-fingerprint-key-32bytes"
CURSOR_KEY = b"mongodb-audit-cursor-signing-key-32b"


class _DeleteResult:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count


class _FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)
        self.sort_spec = None
        self.limit_count = None

    def sort(self, spec):
        self.sort_spec = spec
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def __aiter__(self):
        documents = self.documents[: self.limit_count] if self.limit_count else self.documents

        async def iterate():
            for document in documents:
                yield document

        return iterate()


class _FakeCollection:
    def __init__(self):
        self.indexes = []
        self.inserted = []
        self.insert_error = None
        self.find_documents = []
        self.find_calls = []
        self.last_cursor = None
        self.delete_calls = []
        self.delete_counts = []
        self.counts = []

    async def create_indexes(self, indexes):
        self.indexes.extend(indexes)

    async def insert_one(self, document):
        if self.insert_error is not None:
            raise self.insert_error
        self.inserted.append(document)

    def find(self, query, projection=None):
        self.find_calls.append((query, projection))
        self.last_cursor = _FakeCursor(self.find_documents)
        return self.last_cursor

    async def delete_many(self, query):
        self.delete_calls.append(query)
        return _DeleteResult(self.delete_counts.pop(0))

    async def count_documents(self, query):
        self.find_calls.append((query, None))
        return self.counts.pop(0)


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


class MongoAuditRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.collection = _FakeCollection()
        self.repository = MongoAuditRepository(
            self.collection,
            cursor_signing_key=CURSOR_KEY,
        )
        await self.repository.initialize()

    async def test_initialize_creates_unique_and_bounded_query_indexes_without_ttl(self):
        indexes = {index.document.get("name"): index.document for index in self.collection.indexes}

        self.assertTrue(indexes["idx_audit_event_id_unique"]["unique"])
        self.assertIn("idx_audit_events_order", indexes)
        self.assertIn("idx_audit_events_request", indexes)
        self.assertTrue(all("expireAfterSeconds" not in index for index in indexes.values()))

    async def test_append_stores_utc_redacted_record_and_normalizes_duplicates(self):
        event = _event()
        await self.repository.append(event)

        document = self.collection.inserted[-1]
        self.assertEqual(document["event_id"], event.event_id)
        self.assertEqual(document["occurred_at"].tzinfo, timezone.utc)
        self.assertNotIn("owner@example.com", repr(document))
        self.assertNotIn("configuration-1", repr(document))

        self.collection.insert_error = DuplicateKeyError("duplicate")
        with self.assertRaises(AuditEventAlreadyExistsError):
            await self.repository.append(event)

    async def test_query_uses_exact_filters_stable_order_projection_and_limit(self):
        event = _event()
        document = event.to_record()
        document["occurred_at"] = datetime.fromisoformat(document["occurred_at"])
        self.collection.find_documents = [document]

        page = await self.repository.query(
            AuditQuery(
                actions=("config.update",),
                target_fingerprints=(event.target_fingerprint,),
                outcomes=("succeeded",),
                page_size=10,
            )
        )

        query, projection = self.collection.find_calls[-1]
        self.assertEqual(query["action"], {"$in": ["config.update"]})
        self.assertEqual(query["target_fingerprint"], {"$in": [event.target_fingerprint]})
        self.assertEqual(query["outcome"], {"$in": ["succeeded"]})
        self.assertEqual(projection, {"_id": False})
        self.assertEqual(
            self.collection.last_cursor.sort_spec,
            [("occurred_at", -1), ("event_id", -1)],
        )
        self.assertEqual(self.collection.last_cursor.limit_count, 11)
        self.assertEqual(page.events, (event,))

    async def test_query_returns_signed_cursor_and_rejects_corrupted_documents(self):
        events = [_event(index) for index in range(1, 4)]
        self.collection.find_documents = [
            {
                **event.to_record(),
                "occurred_at": datetime.fromisoformat(event.occurred_at),
            }
            for event in events
        ]

        page = await self.repository.query(AuditQuery(page_size=2))

        self.assertEqual(page.events, tuple(events[:2]))
        self.assertIsNotNone(page.next_cursor)
        cursor_time, cursor_event_id = decode_audit_cursor(
            page.next_cursor,
            signing_key=CURSOR_KEY,
        )
        self.assertEqual(
            (cursor_time, cursor_event_id), (events[1].occurred_at, events[1].event_id)
        )

        corrupted = events[0].to_record()
        corrupted["unexpected"] = "field"
        self.collection.find_documents = [corrupted]
        with self.assertRaises(ValueError):
            await self.repository.query(AuditQuery())

    async def test_prune_uses_utc_cutoff_then_removes_only_oldest_surplus(self):
        self.collection.delete_counts = [100, 100]
        self.collection.counts = [1100]
        self.collection.find_documents = [{"event_id": f"event-{index}"} for index in range(100)]
        now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone(timedelta(hours=7)))

        removed = await self.repository.prune(
            AuditRetentionPolicy(retention_days=7, max_events=1000),
            now=now,
        )

        cutoff = self.collection.delete_calls[0]["occurred_at"]["$lt"]
        self.assertEqual(cutoff.tzinfo, timezone.utc)
        self.assertEqual(len(self.collection.delete_calls[1]["event_id"]["$in"]), 100)
        self.assertEqual(removed, 200)


if __name__ == "__main__":
    unittest.main()
