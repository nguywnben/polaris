"""PostgreSQL repository for bounded request decision traces."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
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


class PostgreSQLRequestTraceRepository:
    def __init__(self, pool: asyncpg.Pool, *, cursor_signing_key: bytes) -> None:
        self._pool = pool
        self._cursor_signing_key = cursor_signing_key
        self._initialized = False

    async def initialize(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS request_traces (
                sequence BIGSERIAL PRIMARY KEY, schema_version INTEGER NOT NULL,
                trace_id TEXT NOT NULL UNIQUE, request_id TEXT NOT NULL, protocol TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL, completed_at TIMESTAMPTZ NOT NULL,
                outcome TEXT NOT NULL, status_code INTEGER NOT NULL, duration_ms INTEGER NOT NULL,
                requested_model TEXT NOT NULL, selected_provider TEXT NOT NULL,
                input_tokens BIGINT NOT NULL, output_tokens BIGINT NOT NULL, total_tokens BIGINT NOT NULL,
                cost_usd DOUBLE PRECISION NOT NULL, decisions JSONB NOT NULL,
                decisions_truncated BOOLEAN NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_request_traces_order ON request_traces(started_at DESC, trace_id DESC)",
            "CREATE INDEX IF NOT EXISTS idx_request_traces_request ON request_traces(request_id)",
            "CREATE INDEX IF NOT EXISTS idx_request_traces_protocol_outcome ON request_traces(protocol, outcome, started_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_request_traces_route ON request_traces(selected_provider, requested_model, started_at DESC)",
        )
        async with self._pool.acquire() as connection:
            for statement in statements:
                await connection.execute(statement)
        self._initialized = True

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("PostgreSQL request trace repository is not initialized.")

    async def append(self, trace: RequestTrace) -> None:
        self._ensure_initialized()
        record = request_trace_from_record(trace.to_record()).to_record()
        values = tuple(
            datetime.fromisoformat(record[column])
            if column in {"started_at", "completed_at"}
            else json.dumps(record[column], separators=(",", ":"))
            if column == "decisions"
            else record[column]
            for column in _COLUMNS
        )
        placeholders = ", ".join(
            f"${index}::jsonb" if column == "decisions" else f"${index}"
            for index, column in enumerate(_COLUMNS, start=1)
        )
        try:
            async with self._pool.acquire() as connection:
                await connection.execute(
                    f"INSERT INTO request_traces ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                    *values,
                )
        except asyncpg.UniqueViolationError as exc:
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
                slots = ", ".join(
                    f"${index}"
                    for index in range(len(parameters) + 1, len(parameters) + len(values) + 1)
                )
                clauses.append(f"{column} IN ({slots})")
                parameters.extend(values)
        for column, value, operator in (
            ("request_id", query.request_id, "="),
            ("started_at", query.started_after, ">="),
            ("started_at", query.started_before, "<="),
        ):
            if value is not None:
                clauses.append(f"{column} {operator} ${len(parameters) + 1}")
                parameters.append(value)
        if query.cursor is not None:
            cursor_time, cursor_id = decode_request_trace_cursor(
                query.cursor, signing_key=self._cursor_signing_key
            )
            time_slot = len(parameters) + 1
            id_slot = len(parameters) + 2
            clauses.append(
                f"(started_at < ${time_slot} OR (started_at = ${time_slot} AND trace_id < ${id_slot}))"
            )
            parameters.extend((datetime.fromisoformat(cursor_time), cursor_id))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_slot = len(parameters) + 1
        parameters.append(query.page_size + 1)
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                f"SELECT {', '.join(_COLUMNS)} FROM request_traces{where} "
                f"ORDER BY started_at DESC, trace_id DESC LIMIT ${limit_slot}",
                *parameters,
            )
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
    def _from_row(row: Any) -> RequestTrace:
        record = {column: row[column] for column in _COLUMNS}
        for column in ("started_at", "completed_at"):
            if isinstance(record[column], datetime):
                record[column] = record[column].astimezone(timezone.utc).isoformat()
        if isinstance(record["decisions"], str):
            try:
                record["decisions"] = json.loads(record["decisions"])
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid stored request trace decisions.") from exc
        return request_trace_from_record(record)

    async def prune(self, policy: RequestTraceRetentionPolicy, *, now: datetime) -> int:
        self._ensure_initialized()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("Request trace prune timestamp must be timezone-aware.")
        cutoff = now.astimezone(timezone.utc) - timedelta(days=policy.retention_days)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                before = int(await connection.fetchval("SELECT COUNT(*) FROM request_traces"))
                await connection.execute("DELETE FROM request_traces WHERE started_at < $1", cutoff)
                remaining = int(await connection.fetchval("SELECT COUNT(*) FROM request_traces"))
                surplus = max(0, remaining - policy.max_traces)
                if surplus:
                    await connection.execute(
                        """DELETE FROM request_traces WHERE trace_id IN (
                            SELECT trace_id FROM request_traces
                            ORDER BY started_at ASC, trace_id ASC LIMIT $1
                        )""",
                        surplus,
                    )
                after = int(await connection.fetchval("SELECT COUNT(*) FROM request_traces"))
        return before - after
