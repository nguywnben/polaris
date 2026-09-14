"""SQLite implementation of the append-only audit repository contract."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite
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
from core.storage.sqlite_runtime import open_sqlite

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


class SQLiteAuditRepository:
    """Durable audit storage using additive SQLite tables and indexes."""

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
                    CREATE TABLE IF NOT EXISTS audit_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        schema_version INTEGER NOT NULL,
                        event_id TEXT NOT NULL UNIQUE,
                        occurred_at TEXT NOT NULL,
                        request_id TEXT NOT NULL,
                        actor_type TEXT NOT NULL,
                        actor_fingerprint TEXT NOT NULL,
                        action TEXT NOT NULL,
                        target_type TEXT NOT NULL,
                        target_fingerprint TEXT NOT NULL,
                        outcome TEXT NOT NULL,
                        change_codes TEXT NOT NULL
                    )
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_audit_events_order
                    ON audit_events(occurred_at DESC, event_id DESC)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_audit_events_request
                    ON audit_events(request_id)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_audit_events_action_outcome
                    ON audit_events(action, outcome, occurred_at DESC)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_audit_events_target
                    ON audit_events(target_type, target_fingerprint, occurred_at DESC)
                """)
                await db.commit()
            self._initialized = True

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("SQLite audit repository is not initialized.")

    async def append(self, event: AuditEvent) -> None:
        self._ensure_initialized()
        record = audit_event_from_record(event.to_record()).to_record()
        values = [
            json.dumps(record[column], separators=(",", ":"))
            if column == "change_codes"
            else record[column]
            for column in _EVENT_COLUMNS
        ]
        placeholders = ", ".join("?" for _ in _EVENT_COLUMNS)
        try:
            async with open_sqlite(self._database_path) as db:
                await db.execute(
                    f"INSERT INTO audit_events ({', '.join(_EVENT_COLUMNS)}) "
                    f"VALUES ({placeholders})",
                    values,
                )
                await db.commit()
        except aiosqlite.IntegrityError as exc:
            raise AuditEventAlreadyExistsError("Audit event already exists.") from exc

    async def query(self, query: AuditQuery) -> AuditPage:
        self._ensure_initialized()
        clauses: list[str] = []
        parameters: list[Any] = []
        self._add_exact_filters(query, clauses, parameters)
        if query.request_id is not None:
            clauses.append("request_id = ?")
            parameters.append(query.request_id)
        if query.occurred_after is not None:
            clauses.append("occurred_at >= ?")
            parameters.append(query.occurred_after.isoformat())
        if query.occurred_before is not None:
            clauses.append("occurred_at <= ?")
            parameters.append(query.occurred_before.isoformat())
        if query.cursor is not None:
            cursor_time, cursor_event_id = decode_audit_cursor(
                query.cursor,
                signing_key=self._cursor_signing_key,
            )
            clauses.append("(occurred_at < ? OR (occurred_at = ? AND event_id < ?))")
            parameters.extend((cursor_time, cursor_time, cursor_event_id))

        where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(query.page_size + 1)
        sql = (
            f"SELECT {', '.join(_EVENT_COLUMNS)} FROM audit_events"
            f"{where_clause} ORDER BY occurred_at DESC, event_id DESC LIMIT ?"
        )
        async with open_sqlite(self._database_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, parameters) as cursor:
                rows = await cursor.fetchall()

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
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{column} IN ({placeholders})")
            parameters.extend(values)

    @staticmethod
    def _event_from_row(row: aiosqlite.Row) -> AuditEvent:
        record = {column: row[column] for column in _EVENT_COLUMNS}
        try:
            record["change_codes"] = json.loads(record["change_codes"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid stored audit change summary.") from exc
        return audit_event_from_record(record)

    async def prune(self, policy: AuditRetentionPolicy, *, now: datetime) -> int:
        self._ensure_initialized()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("Audit prune timestamp must be timezone-aware.")
        cutoff = (now.astimezone(timezone.utc) - timedelta(days=policy.retention_days)).isoformat()
        async with open_sqlite(self._database_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            before = await self._count_events(db)
            await db.execute("DELETE FROM audit_events WHERE occurred_at < ?", (cutoff,))
            remaining = await self._count_events(db)
            surplus = max(0, remaining - policy.max_events)
            if surplus:
                await db.execute(
                    """
                    DELETE FROM audit_events
                    WHERE event_id IN (
                        SELECT event_id FROM audit_events
                        ORDER BY occurred_at ASC, event_id ASC
                        LIMIT ?
                    )
                    """,
                    (surplus,),
                )
            after = await self._count_events(db)
            await db.commit()
        return before - after

    @staticmethod
    async def _count_events(db: aiosqlite.Connection) -> int:
        async with db.execute("SELECT COUNT(*) FROM audit_events") as cursor:
            row = await cursor.fetchone()
        return int(row[0])
