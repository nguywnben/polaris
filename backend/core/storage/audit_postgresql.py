"""PostgreSQL implementation of the append-only audit repository contract."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
from core.audit import (
    AuditEvent,
    AuditEventAlreadyExistsError,
    AuditPage,
    AuditQuery,
    AuditRetentionPolicy,
    audit_event_from_record,
    decode_audit_cursor,
    encode_audit_cursor,
)

_EVENT_COLUMNS = (
    "schema_version",
    "event_id",
    "occurred_at",
    "request_id",
    "actor_type",
    "actor_fingerprint",
    "action",
    "target_type",
    "target_fingerprint",
    "outcome",
    "change_codes",
)


class PostgreSQLAuditRepository:
    """Durable audit storage over an existing asyncpg connection pool."""

    def __init__(self, pool: asyncpg.Pool, *, cursor_signing_key: bytes) -> None:
        self._pool = pool
        self._cursor_signing_key = cursor_signing_key
        self._initialized = False

    async def initialize(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                sequence BIGSERIAL PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                event_id TEXT NOT NULL UNIQUE,
                occurred_at TIMESTAMPTZ NOT NULL,
                request_id TEXT NOT NULL,
                actor_type TEXT NOT NULL,
                actor_fingerprint TEXT NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_fingerprint TEXT NOT NULL,
                outcome TEXT NOT NULL,
                change_codes JSONB NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_order
            ON audit_events(occurred_at DESC, event_id DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_request
            ON audit_events(request_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_action_outcome
            ON audit_events(action, outcome, occurred_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_target
            ON audit_events(target_type, target_fingerprint, occurred_at DESC)
            """,
        )
        async with self._pool.acquire() as connection:
            for statement in statements:
                await connection.execute(statement)
        self._initialized = True

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("PostgreSQL audit repository is not initialized.")

    async def append(self, event: AuditEvent) -> None:
        self._ensure_initialized()
        record = audit_event_from_record(event.to_record()).to_record()
        values = tuple(
            datetime.fromisoformat(record[column])
            if column == "occurred_at"
            else json.dumps(record[column], separators=(",", ":"))
            if column == "change_codes"
            else record[column]
            for column in _EVENT_COLUMNS
        )
        placeholders = ", ".join(
            f"${index}::jsonb" if column == "change_codes" else f"${index}"
            for index, column in enumerate(_EVENT_COLUMNS, start=1)
        )
        try:
            async with self._pool.acquire() as connection:
                await connection.execute(
                    f"INSERT INTO audit_events ({', '.join(_EVENT_COLUMNS)}) "
                    f"VALUES ({placeholders})",
                    *values,
                )
        except asyncpg.UniqueViolationError as exc:
            raise AuditEventAlreadyExistsError("Audit event already exists.") from exc

    async def query(self, query: AuditQuery) -> AuditPage:
        self._ensure_initialized()
        clauses: list[str] = []
        parameters: list[Any] = []
        self._add_exact_filters(query, clauses, parameters)
        if query.request_id is not None:
            clauses.append(f"request_id = ${len(parameters) + 1}")
            parameters.append(query.request_id)
        if query.occurred_after is not None:
            clauses.append(f"occurred_at >= ${len(parameters) + 1}")
            parameters.append(query.occurred_after)
        if query.occurred_before is not None:
            clauses.append(f"occurred_at <= ${len(parameters) + 1}")
            parameters.append(query.occurred_before)
        if query.cursor is not None:
            cursor_time, cursor_event_id = decode_audit_cursor(
                query.cursor,
                signing_key=self._cursor_signing_key,
            )
            time_parameter = len(parameters) + 1
            event_parameter = len(parameters) + 2
            clauses.append(
                f"(occurred_at < ${time_parameter} OR "
                f"(occurred_at = ${time_parameter} AND event_id < ${event_parameter}))"
            )
            parameters.extend((datetime.fromisoformat(cursor_time), cursor_event_id))

        where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_parameter = len(parameters) + 1
        parameters.append(query.page_size + 1)
        sql = (
            f"SELECT {', '.join(_EVENT_COLUMNS)} FROM audit_events"
            f"{where_clause} ORDER BY occurred_at DESC, event_id DESC LIMIT ${limit_parameter}"
        )
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(sql, *parameters)

        has_more = len(rows) > query.page_size
        events = tuple(self._event_from_row(row) for row in rows[: query.page_size])
        next_cursor = None
        if has_more and events:
            last_event = events[-1]
            next_cursor = encode_audit_cursor(
                occurred_at=last_event.occurred_at,
                event_id=last_event.event_id,
                signing_key=self._cursor_signing_key,
            )
        return AuditPage(events=events, next_cursor=next_cursor)

    @staticmethod
    def _add_exact_filters(
        query: AuditQuery,
        clauses: list[str],
        parameters: list[Any],
    ) -> None:
        filters = (
            ("actor_type", query.actor_types),
            ("actor_fingerprint", query.actor_fingerprints),
            ("action", query.actions),
            ("target_type", query.target_types),
            ("target_fingerprint", query.target_fingerprints),
            ("outcome", query.outcomes),
        )
        for column, values in filters:
            if not values:
                continue
            placeholders = ", ".join(
                f"${index}"
                for index in range(len(parameters) + 1, len(parameters) + len(values) + 1)
            )
            clauses.append(f"{column} IN ({placeholders})")
            parameters.extend(values)

    @staticmethod
    def _event_from_row(row: Any) -> AuditEvent:
        record = {column: row[column] for column in _EVENT_COLUMNS}
        occurred_at = record["occurred_at"]
        if isinstance(occurred_at, datetime):
            record["occurred_at"] = occurred_at.astimezone(timezone.utc).isoformat()
        change_codes = record["change_codes"]
        if isinstance(change_codes, str):
            try:
                record["change_codes"] = json.loads(change_codes)
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid stored audit change summary.") from exc
        return audit_event_from_record(record)

    async def prune(self, policy: AuditRetentionPolicy, *, now: datetime) -> int:
        self._ensure_initialized()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("Audit prune timestamp must be timezone-aware.")
        cutoff = now.astimezone(timezone.utc) - timedelta(days=policy.retention_days)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                before = int(await connection.fetchval("SELECT COUNT(*) FROM audit_events"))
                await connection.execute(
                    "DELETE FROM audit_events WHERE occurred_at < $1",
                    cutoff,
                )
                remaining = int(await connection.fetchval("SELECT COUNT(*) FROM audit_events"))
                surplus = max(0, remaining - policy.max_events)
                if surplus:
                    await connection.execute(
                        """
                        DELETE FROM audit_events
                        WHERE event_id IN (
                            SELECT event_id FROM audit_events
                            ORDER BY occurred_at ASC, event_id ASC
                            LIMIT $1
                        )
                        """,
                        surplus,
                    )
                after = int(await connection.fetchval("SELECT COUNT(*) FROM audit_events"))
        return before - after
