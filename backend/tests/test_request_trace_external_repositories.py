"""Parameterized contract checks for PostgreSQL and MongoDB request trace repositories."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

import asyncpg
from pymongo.errors import DuplicateKeyError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.request_trace import RequestTraceAlreadyExistsError, RequestTraceQuery
from core.request_trace_service import RequestTraceCollector
from core.storage.request_trace_mongodb import MongoRequestTraceRepository
from core.storage.request_trace_postgresql import PostgreSQLRequestTraceRepository

CURSOR_KEY = b"request-trace-external-cursor-key-32"


def _trace():
    collector = RequestTraceCollector("request-123", "openai_chat")
    collector.record(
        category="routing",
        action="selected",
        result="succeeded",
        reason="healthy_candidate",
        provider="openai",
        model="gpt-5",
    )
    return collector.complete(status_code=200)


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


class _PostgresConnection:
    def __init__(self):
        self.executions = []
        self.rows = []
        self.error = None

    async def execute(self, sql, *args):
        if self.error:
            raise self.error
        self.executions.append((sql, args))

    async def fetch(self, sql, *args):
        self.executions.append((sql, args))
        return self.rows


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


class _Cursor:
    def __init__(self, documents):
        self.documents = documents
        self.sort_spec = None
        self.limit_count = None

    def sort(self, spec):
        self.sort_spec = spec
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def __aiter__(self):
        async def iterate():
            for document in self.documents[: self.limit_count]:
                yield document

        return iterate()


class _MongoCollection:
    def __init__(self):
        self.indexes = []
        self.documents = []
        self.error = None
        self.find_calls = []
        self.cursor = None

    async def create_indexes(self, indexes):
        self.indexes.extend(indexes)

    async def insert_one(self, document):
        if self.error:
            raise self.error
        self.documents.append(document)

    def find(self, query, projection=None):
        self.find_calls.append((query, projection))
        self.cursor = _Cursor(self.documents)
        return self.cursor


class ExternalRequestTraceRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_postgresql_uses_additive_schema_placeholders_and_strict_rows(self):
        connection = _PostgresConnection()
        repository = PostgreSQLRequestTraceRepository(
            _Pool(connection), cursor_signing_key=CURSOR_KEY
        )
        await repository.initialize()
        schema = "\n".join(sql for sql, _ in connection.executions)
        self.assertIn("CREATE TABLE IF NOT EXISTS request_traces", schema)
        self.assertNotIn("DROP ", schema.upper())

        trace = _trace()
        connection.executions.clear()
        await repository.append(trace)
        sql, args = connection.executions[-1]
        self.assertIn("VALUES ($1, $2", sql)
        self.assertNotIn("prompt", repr(args).lower())

        row = trace.to_record()
        row["started_at"] = datetime.fromisoformat(row["started_at"])
        row["completed_at"] = datetime.fromisoformat(row["completed_at"])
        connection.rows = [row]
        page = await repository.query(RequestTraceQuery(request_id="request-123"))
        self.assertEqual(page.traces, (trace,))

        connection.error = asyncpg.UniqueViolationError("duplicate")
        with self.assertRaises(RequestTraceAlreadyExistsError):
            await repository.append(trace)

    async def test_mongodb_indexes_append_query_and_duplicate_normalization(self):
        collection = _MongoCollection()
        repository = MongoRequestTraceRepository(collection, cursor_signing_key=CURSOR_KEY)
        await repository.initialize()
        names = {index.document["name"] for index in collection.indexes}
        self.assertIn("idx_request_trace_id_unique", names)
        self.assertTrue(
            all("expireAfterSeconds" not in index.document for index in collection.indexes)
        )

        trace = _trace()
        await repository.append(trace)
        page = await repository.query(
            RequestTraceQuery(protocols=("openai_chat",), outcomes=("succeeded",))
        )
        self.assertEqual(page.traces, (trace,))
        query, projection = collection.find_calls[-1]
        self.assertEqual(query["protocol"], {"$in": ["openai_chat"]})
        self.assertEqual(projection, {"_id": False})

        collection.error = DuplicateKeyError("duplicate")
        with self.assertRaises(RequestTraceAlreadyExistsError):
            await repository.append(trace)


if __name__ == "__main__":
    unittest.main()
