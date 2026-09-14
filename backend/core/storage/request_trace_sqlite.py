"""SQLite repository for bounded request decision traces."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite
from core.request_trace import (
    RequestTrace,
    RequestTraceAlreadyExistsError,
    RequestTracePage,
    RequestTraceQuery,
    RequestTraceRetentionPolicy,
    decode_request_trace_cursor,
    encode_request_trace_cursor,
    request_trace_from_record,
)
from core.storage.sqlite_runtime import open_sqlite

_COLUMNS = (
    "schema_version",
    "trace_id",
    "request_id",
    "protocol",
    "started_at",
    "completed_at",
    "outcome",
    "status_code",
    "duration_ms",
    "requested_model",
    "selected_provider",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cost_usd",
    "decisions",
    "decisions_truncated",
)


class SQLiteRequestTraceRepository:
    def __init__(self, database_path: str | Path, *, cursor_signing_key: bytes) -> None:
        self._database_path = str(database_path)
        self._cursor_signing_key = cursor_signing_key
        self._initialized = False
        self._initialize_lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._initialize_lock:
            async with open_sqlite(self._database_path) as db:
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS request_traces (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        schema_version INTEGER NOT NULL,
                        trace_id TEXT NOT NULL UNIQUE,
                        request_id TEXT NOT NULL,
                        protocol TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        completed_at TEXT NOT NULL,
                        outcome TEXT NOT NULL,
                        status_code INTEGER NOT NULL,
                        duration_ms INTEGER NOT NULL,
                        requested_model TEXT NOT NULL,
                        selected_provider TEXT NOT NULL,
                        input_tokens INTEGER NOT NULL,
                        output_tokens INTEGER NOT NULL,
                        total_tokens INTEGER NOT NULL,
                        cost_usd REAL NOT NULL,
                        decisions TEXT NOT NULL,
                        decisions_truncated INTEGER NOT NULL
                    )
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_request_traces_order
                    ON request_traces(started_at DESC, trace_id DESC)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_request_traces_request
                    ON request_traces(request_id)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_request_traces_protocol_outcome
                    ON request_traces(protocol, outcome, started_at DESC)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_request_traces_route
                    ON request_traces(selected_provider, requested_model, started_at DESC)
                """)
                await db.commit()
            self._initialized = True

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("SQLite request trace repository is not initialized.")

    async def append(self, trace: RequestTrace) -> None:
        self._ensure_initialized()
        record = request_trace_from_record(trace.to_record()).to_record()
        values = [
            json.dumps(record[column], separators=(",", ":"))
            if column == "decisions"
            else int(record[column])
            if column == "decisions_truncated"
            else record[column]
            for column in _COLUMNS
        ]
        try:
            async with open_sqlite(self._database_path) as db:
                await db.execute(
                    f"INSERT INTO request_traces ({', '.join(_COLUMNS)}) "
                    f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
                    values,
                )
                await db.commit()
        except aiosqlite.IntegrityError as exc:
            raise RequestTraceAlreadyExistsError("Request trace already exists.") from exc

    async def query(self, query: RequestTraceQuery) -> RequestTracePage:
        self._ensure_initialized()
        clauses: list[str] = []
        parameters: list[Any] = []
        for column, values in (
            ("trace_id", query.trace_ids),
            ("protocol", query.protocols),
            ("outcome", query.outcomes),
            ("selected_provider", query.providers),
            ("requested_model", query.models),
        ):
            if values:
                clauses.append(f"{column} IN ({', '.join('?' for _ in values)})")
                parameters.extend(values)
        if query.request_id is not None:
            clauses.append("request_id = ?")
            parameters.append(query.request_id)
        if query.started_after is not None:
            clauses.append("started_at >= ?")
            parameters.append(query.started_after.isoformat())
        if query.started_before is not None:
            clauses.append("started_at <= ?")
            parameters.append(query.started_before.isoformat())
        if query.cursor is not None:
            cursor_time, cursor_id = decode_request_trace_cursor(
                query.cursor, signing_key=self._cursor_signing_key
            )
            clauses.append("(started_at < ? OR (started_at = ? AND trace_id < ?))")
            parameters.extend((cursor_time, cursor_time, cursor_id))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(query.page_size + 1)
        async with open_sqlite(self._database_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM request_traces{where} "
                "ORDER BY started_at DESC, trace_id DESC LIMIT ?",
                parameters,
            ) as cursor:
                rows = await cursor.fetchall()
        has_more = len(rows) > query.page_size
        traces = tuple(self._from_row(row) for row in rows[: query.page_size])
        next_cursor = None
        if has_more and traces:
            last = traces[-1]
            next_cursor = encode_request_trace_cursor(
                started_at=last.started_at,
                trace_id=last.trace_id,
                signing_key=self._cursor_signing_key,
            )
        return RequestTracePage(traces=traces, next_cursor=next_cursor)

    @staticmethod
    def _from_row(row: aiosqlite.Row) -> RequestTrace:
        record = {column: row[column] for column in _COLUMNS}
        try:
            record["decisions"] = json.loads(record["decisions"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid stored request trace decisions.") from exc
        record["decisions_truncated"] = bool(record["decisions_truncated"])
        return request_trace_from_record(record)

    async def prune(self, policy: RequestTraceRetentionPolicy, *, now: datetime) -> int:
        self._ensure_initialized()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("Request trace prune timestamp must be timezone-aware.")
        cutoff = (now.astimezone(timezone.utc) - timedelta(days=policy.retention_days)).isoformat()
        async with open_sqlite(self._database_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            before = await self._count(db)
            await db.execute("DELETE FROM request_traces WHERE started_at < ?", (cutoff,))
            remaining = await self._count(db)
            surplus = max(0, remaining - policy.max_traces)
            if surplus:
                await db.execute(
                    """
                    DELETE FROM request_traces WHERE trace_id IN (
                        SELECT trace_id FROM request_traces
                        ORDER BY started_at ASC, trace_id ASC LIMIT ?
                    )
                    """,
                    (surplus,),
                )
            after = await self._count(db)
            await db.commit()
        return before - after

    @staticmethod
    async def _count(db: aiosqlite.Connection) -> int:
        async with db.execute("SELECT COUNT(*) FROM request_traces") as cursor:
            row = await cursor.fetchone()
        return int(row[0])
