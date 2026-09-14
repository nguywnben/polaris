"""SQLite persistence, filtering, restart, and retention tests for request traces."""

from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.request_trace import (
    RequestTraceAlreadyExistsError,
    RequestTraceQuery,
    RequestTraceRetentionPolicy,
)
from core.request_trace_service import RequestTraceCollector
from core.storage.request_trace_sqlite import SQLiteRequestTraceRepository
from tests.support import workspace_temp_directory

CURSOR_KEY = b"request-trace-sqlite-cursor-key-32"


def _trace(index: int, started_at: datetime, *, protocol="openai_chat", status=200):
    collector = RequestTraceCollector(f"request-{index}", protocol)
    collector.record(
        category="routing",
        action="selected",
        result="succeeded",
        reason="healthy_candidate",
        provider="openai",
        model=f"model-{index}",
    )
    trace = collector.complete(status_code=status)
    return replace(
        trace,
        started_at=started_at.isoformat(),
        completed_at=(started_at + timedelta(milliseconds=trace.duration_ms)).isoformat(),
    )


class SQLiteRequestTraceRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = workspace_temp_directory()
        temp_path = self.temp_dir.__enter__()
        self.addCleanup(self.temp_dir.__exit__, None, None, None)
        self.db_path = Path(temp_path) / "credentials.db"
        self.repository = SQLiteRequestTraceRepository(self.db_path, cursor_signing_key=CURSOR_KEY)
        await self.repository.initialize()

    async def test_append_query_cursor_and_duplicate_protection(self):
        base = datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc)
        traces = [_trace(index, base + timedelta(seconds=index)) for index in range(3)]
        for trace in traces:
            await self.repository.append(trace)
        with self.assertRaises(RequestTraceAlreadyExistsError):
            await self.repository.append(traces[0])

        first = await self.repository.query(RequestTraceQuery(page_size=2))
        second = await self.repository.query(
            RequestTraceQuery(page_size=2, cursor=first.next_cursor)
        )
        self.assertEqual([item.request_id for item in first.traces], ["request-2", "request-1"])
        self.assertEqual([item.request_id for item in second.traces], ["request-0"])

    async def test_exact_filters_and_corrupted_json_fail_closed(self):
        now = datetime.now(timezone.utc)
        succeeded = _trace(1, now)
        failed = _trace(2, now + timedelta(seconds=1), protocol="gemini_generate", status=502)
        await self.repository.append(succeeded)
        await self.repository.append(failed)

        page = await self.repository.query(
            RequestTraceQuery(
                protocols=("gemini_generate",),
                outcomes=("upstream_error",),
                providers=("openai",),
                models=("model-2",),
                request_id="request-2",
            )
        )
        self.assertEqual(page.traces, (failed,))

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE request_traces SET decisions = ? WHERE trace_id = ?",
                ('[{"prompt":"private"}]', failed.trace_id),
            )
            await db.commit()
        with self.assertRaises(ValueError):
            await self.repository.query(RequestTraceQuery(request_id="request-2"))

    async def test_restart_and_age_then_count_retention(self):
        now = datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc)
        traces = [
            _trace(1, now - timedelta(days=8)),
            _trace(2, now - timedelta(days=2)),
            _trace(3, now - timedelta(days=1)),
        ]
        for trace in traces:
            await self.repository.append(trace)

        restarted = SQLiteRequestTraceRepository(self.db_path, cursor_signing_key=CURSOR_KEY)
        await restarted.initialize()
        removed = await restarted.prune(
            RequestTraceRetentionPolicy(retention_days=7, max_traces=1_000), now=now
        )
        self.assertEqual(removed, 1)
        remaining = await restarted.query(RequestTraceQuery())
        self.assertEqual(
            [trace.request_id for trace in remaining.traces], ["request-3", "request-2"]
        )


if __name__ == "__main__":
    unittest.main()
