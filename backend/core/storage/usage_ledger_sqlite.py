"""SQLite W4.14 durable usage ledger and hard-budget journal repository."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import sqlite3
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path

import aiosqlite
from core.quality_decision import normalize_quality_decision
from core.storage.sqlite_runtime import (
    SQLITE_BUSY_TIMEOUT_MS,
    SQLITE_BUSY_TIMEOUT_SECONDS,
    open_sqlite,
)
from core.usage_ledger import (
    DAILY_WINDOW_SECONDS,
    MAX_COST_NANOS,
    MAX_RECONCILE_BATCH,
    MAX_USAGE_REPORT_ROWS,
    MONTHLY_WINDOW_SECONDS,
    USAGE_LEDGER_SCHEMA_VERSION,
    BudgetCommitResult,
    BudgetReleaseResult,
    BudgetReservation,
    BudgetReservationDecision,
    BudgetReservationRequest,
    BudgetReservationState,
    CredentialUsageAggregate,
    ProviderUsageAggregate,
    SpendSnapshot,
    UsageAppendResult,
    UsageLedgerConflict,
    UsageLedgerCorrupt,
    UsageLedgerEntry,
    UsageLedgerStateConflict,
    UsageLiabilityPage,
    UsageTimeBucket,
    budget_reservation_from_record,
    usage_entry_from_record,
    usage_liability_page,
    usd_to_nanos,
    validate_usage_liability_cursor,
)

_LEGACY_OPTIONAL_DEFAULTS: dict[str, object] = {
    "request_id": "",
    "model": "",
    "provider": "",
    "status_code": 200,
    "success": 1,
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "cached_tokens": 0,
    "reasoning_tokens": 0,
    "estimated_input_tokens": 0,
    "estimated_tokens_saved": 0,
    "compressed_messages": 0,
    "quality_profile": "",
    "quality_policy_revision": 0,
    "compression_reason": "",
    "latency_ms": 0,
    "retry_count": 0,
    "cost_usd": 0,
    "api_key_id": "",
}

_COLUMNS = (
    "record_id",
    "kind",
    "state",
    "revision",
    "key_id",
    "created_at",
    "expires_at",
    "transitioned_at",
    "estimated_cost_nanos",
    "daily_budget_nanos",
    "monthly_budget_nanos",
    "event_id",
    "occurred_at",
    "credential_ref",
    "provider",
    "success",
    "total_tokens",
    "cost_nanos",
    "api_key_id",
    "payload",
)

_SQLITE_LEDGER_SCHEMA = {
    "record_id": ("TEXT", 0, 1),
    "kind": ("TEXT", 1, 0),
    "state": ("TEXT", 1, 0),
    "revision": ("INTEGER", 1, 0),
    "key_id": ("TEXT", 1, 0),
    "created_at": ("REAL", 1, 0),
    "expires_at": ("REAL", 0, 0),
    "transitioned_at": ("REAL", 0, 0),
    "estimated_cost_nanos": ("INTEGER", 0, 0),
    "daily_budget_nanos": ("INTEGER", 0, 0),
    "monthly_budget_nanos": ("INTEGER", 0, 0),
    "event_id": ("TEXT", 0, 0),
    "occurred_at": ("REAL", 0, 0),
    "credential_ref": ("TEXT", 0, 0),
    "provider": ("TEXT", 0, 0),
    "success": ("INTEGER", 0, 0),
    "total_tokens": ("INTEGER", 0, 0),
    "cost_nanos": ("INTEGER", 0, 0),
    "api_key_id": ("TEXT", 0, 0),
    "payload": ("TEXT", 1, 0),
}
_SQLITE_MIGRATION_SCHEMA = {
    "source_key": ("TEXT", 0, 1),
    "source_count": ("INTEGER", 1, 0),
    "source_checksum": ("TEXT", 1, 0),
    "completed_at": ("REAL", 1, 0),
}
_SQLITE_REQUIRED_INDEXES = {
    "idx_durable_usage_event": (1, 1, ("event_id",)),
    "idx_durable_usage_spend": (0, 1, ("api_key_id", "occurred_at")),
    "idx_durable_usage_active_budget": (0, 1, ("key_id", "state", "expires_at")),
    "idx_durable_usage_expiry": (0, 1, ("expires_at", "record_id")),
    "idx_durable_usage_credential": (0, 1, ("credential_ref", "occurred_at")),
}


@dataclass(frozen=True, slots=True)
class LegacyUsageImportResult:
    source_count: int
    imported_count: int
    source_checksum: str
    verified: bool


class SQLiteUsageLedgerRepository:
    """One-row-per-event/reservation repository with atomic per-database writes."""

    def __init__(self, database_path: str) -> None:
        if not isinstance(database_path, str) or not database_path.strip():
            raise ValueError("Usage ledger database path is invalid.")
        self._database_path = database_path
        self._initialized = False
        self._database: aiosqlite.Connection | None = None
        self._connection_lock = asyncio.Lock()

    async def initialize(self) -> None:
        Path(self._database_path).parent.mkdir(parents=True, exist_ok=True)
        async with self._connection(allow_initializing=True) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS durable_usage_ledger (
                    record_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL CHECK (kind IN ('usage', 'reservation')),
                    state TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    key_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    transitioned_at REAL,
                    estimated_cost_nanos INTEGER,
                    daily_budget_nanos INTEGER,
                    monthly_budget_nanos INTEGER,
                    event_id TEXT,
                    occurred_at REAL,
                    credential_ref TEXT,
                    provider TEXT,
                    success INTEGER,
                    total_tokens INTEGER,
                    cost_nanos INTEGER,
                    api_key_id TEXT,
                    payload TEXT NOT NULL
                )
                """
            )
            ledger_columns = {
                str(row[1])
                for row in await (
                    await db.execute("PRAGMA table_info(durable_usage_ledger)")
                ).fetchall()
            }
            if ledger_columns != set(_COLUMNS):
                raise UsageLedgerCorrupt("Usage ledger schema is incompatible.")
            await db.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_durable_usage_event
                ON durable_usage_ledger(event_id)
                WHERE event_id IS NOT NULL
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_durable_usage_spend
                ON durable_usage_ledger(api_key_id, occurred_at)
                WHERE cost_nanos IS NOT NULL
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_durable_usage_active_budget
                ON durable_usage_ledger(key_id, state, expires_at)
                WHERE kind = 'reservation'
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_durable_usage_expiry
                ON durable_usage_ledger(expires_at, record_id)
                WHERE kind = 'reservation' AND state = 'active'
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_durable_usage_credential
                ON durable_usage_ledger(credential_ref, occurred_at)
                WHERE occurred_at IS NOT NULL
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS durable_usage_migrations (
                    source_key TEXT PRIMARY KEY,
                    source_count INTEGER NOT NULL,
                    source_checksum TEXT NOT NULL,
                    completed_at REAL NOT NULL
                )
                """
            )
            migration_columns = {
                str(row[1])
                for row in await (
                    await db.execute("PRAGMA table_info(durable_usage_migrations)")
                ).fetchall()
            }
            if migration_columns != {
                "source_key",
                "source_count",
                "source_checksum",
                "completed_at",
            }:
                raise UsageLedgerCorrupt("Usage migration schema is incompatible.")
            await self._validate_schema_locked(db)
            await db.commit()
        database = await aiosqlite.connect(
            self._database_path,
            timeout=SQLITE_BUSY_TIMEOUT_SECONDS,
            isolation_level=None,
        )
        try:
            database.row_factory = aiosqlite.Row
            await database.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            await database.execute("PRAGMA foreign_keys=ON")
        except BaseException:
            await database.close()
            raise
        self._database = database
        self._initialized = True

    async def close(self) -> None:
        async with self._connection_lock:
            database = self._database
            self._database = None
            self._initialized = False
            if database is not None:
                await database.close()

    async def check_available(self) -> None:
        self._ensure_initialized()
        async with self._connection() as db:
            await (
                await db.execute("SELECT record_id FROM durable_usage_ledger LIMIT 1")
            ).fetchone()

    async def append_usage(self, entry: UsageLedgerEntry) -> UsageAppendResult:
        self._require_entry(entry)
        async with self._connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                existing = await self._get_locked(db, entry.event_id)
                if existing is not None:
                    decoded = self._decode_row(existing)
                    if decoded != entry:
                        raise UsageLedgerConflict("Usage event idempotency conflict.")
                    await db.rollback()
                    return UsageAppendResult(False, True)
                await self._insert_usage_locked(db, entry)
                await db.commit()
                return UsageAppendResult(True, False)
            except Exception:
                await db.rollback()
                raise

    async def reserve_budget(self, request: BudgetReservationRequest) -> BudgetReservationDecision:
        if type(request) is not BudgetReservationRequest:
            raise ValueError("Budget reservation request is invalid.")
        async with self._connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                await self._expire_locked(db, now=request.created_at, limit=MAX_RECONCILE_BATCH)
                existing = await self._get_locked(db, request.reservation_id)
                if existing is not None:
                    decoded = self._decode_reservation(existing)
                    if decoded.admits_delivery_replay(request):
                        await db.rollback()
                        return BudgetReservationDecision(
                            True,
                            request.reservation_id,
                            idempotent=True,
                            replayed=True,
                        )
                    if (
                        decoded.state is BudgetReservationState.COMMITTED
                        and decoded.matches_operation(request)
                    ):
                        raise UsageLedgerStateConflict("Budget reservation replay window expired.")
                    if self._request_from_reservation(decoded) != request:
                        raise UsageLedgerConflict("Budget reservation idempotency conflict.")
                    if decoded.state is not BudgetReservationState.ACTIVE:
                        raise UsageLedgerStateConflict("Budget reservation state conflict.")
                    await db.rollback()
                    return BudgetReservationDecision(
                        True,
                        request.reservation_id,
                        idempotent=True,
                    )

                active_cost = await self._active_cost_locked(
                    db,
                    key_id=request.key_id,
                    now=request.created_at,
                )
                if request.daily_budget_nanos is not None:
                    committed = await self._committed_cost_locked(
                        db,
                        key_id=request.key_id,
                        since=request.created_at - DAILY_WINDOW_SECONDS,
                    )
                    if (
                        committed + active_cost + request.estimated_cost_nanos
                        > request.daily_budget_nanos
                    ):
                        await db.rollback()
                        return BudgetReservationDecision(
                            False,
                            request.reservation_id,
                            reason="daily_budget",
                        )
                if request.monthly_budget_nanos is not None:
                    committed = await self._committed_cost_locked(
                        db,
                        key_id=request.key_id,
                        since=request.created_at - MONTHLY_WINDOW_SECONDS,
                    )
                    if (
                        committed + active_cost + request.estimated_cost_nanos
                        > request.monthly_budget_nanos
                    ):
                        await db.rollback()
                        return BudgetReservationDecision(
                            False,
                            request.reservation_id,
                            reason="monthly_budget",
                        )
                await self._insert_reservation_locked(db, BudgetReservation.active(request))
                await db.commit()
                return BudgetReservationDecision(True, request.reservation_id)
            except Exception:
                await db.rollback()
                raise

    async def commit_reservation(
        self,
        reservation_id: str,
        usage: UsageLedgerEntry,
        *,
        transitioned_at: float,
    ) -> BudgetCommitResult:
        self._require_entry(usage)
        async with self._connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                row = await self._get_locked(db, reservation_id)
                if row is None:
                    raise UsageLedgerStateConflict("Budget reservation state conflict.")
                reservation = self._decode_reservation(row)
                if reservation.state is BudgetReservationState.COMMITTED:
                    if reservation.usage != usage:
                        raise UsageLedgerConflict("Budget commit idempotency conflict.")
                    await db.rollback()
                    return BudgetCommitResult(False, idempotent=True)
                if reservation.state is not BudgetReservationState.ACTIVE:
                    raise UsageLedgerStateConflict("Budget reservation state conflict.")
                if usage.api_key_id != reservation.key_id:
                    raise UsageLedgerConflict("Budget commit attribution conflict.")
                if transitioned_at >= reservation.expires_at:
                    expired = replace(
                        reservation,
                        state=BudgetReservationState.EXPIRED,
                        revision=2,
                        transitioned_at=transitioned_at,
                    )
                    await self._update_reservation_locked(db, expired)
                    await db.commit()
                    raise UsageLedgerStateConflict("Budget reservation expired before commit.")
                event_row = await self._get_by_event_locked(db, usage.event_id)
                if event_row is not None:
                    raise UsageLedgerConflict("Usage event idempotency conflict.")

                other_active = await self._active_cost_locked(
                    db,
                    key_id=reservation.key_id,
                    now=transitioned_at,
                    exclude_record_id=reservation.reservation_id,
                )
                overspent = usage.cost_nanos > reservation.estimated_cost_nanos
                if reservation.daily_budget_nanos is not None:
                    daily = await self._committed_cost_locked(
                        db,
                        key_id=reservation.key_id,
                        since=transitioned_at - DAILY_WINDOW_SECONDS,
                    )
                    overspent = overspent or (
                        daily + other_active + usage.cost_nanos > reservation.daily_budget_nanos
                    )
                if reservation.monthly_budget_nanos is not None:
                    monthly = await self._committed_cost_locked(
                        db,
                        key_id=reservation.key_id,
                        since=transitioned_at - MONTHLY_WINDOW_SECONDS,
                    )
                    overspent = overspent or (
                        monthly + other_active + usage.cost_nanos > reservation.monthly_budget_nanos
                    )
                committed = replace(
                    reservation,
                    state=BudgetReservationState.COMMITTED,
                    revision=2,
                    transitioned_at=transitioned_at,
                    usage=usage,
                )
                await self._update_reservation_locked(db, committed)
                await db.commit()
                return BudgetCommitResult(True, overspent=overspent)
            except UsageLedgerStateConflict:
                if db.in_transaction:
                    await db.rollback()
                raise
            except Exception:
                await db.rollback()
                raise

    async def release_reservation(
        self,
        reservation_id: str,
        *,
        transitioned_at: float,
    ) -> BudgetReleaseResult:
        async with self._connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                row = await self._get_locked(db, reservation_id)
                if row is None:
                    raise UsageLedgerStateConflict("Budget reservation state conflict.")
                reservation = self._decode_reservation(row)
                if reservation.state is BudgetReservationState.RELEASED:
                    await db.rollback()
                    return BudgetReleaseResult(False, idempotent=True)
                if reservation.state is not BudgetReservationState.ACTIVE:
                    raise UsageLedgerStateConflict("Budget reservation state conflict.")
                if transitioned_at >= reservation.expires_at:
                    expired = replace(
                        reservation,
                        state=BudgetReservationState.EXPIRED,
                        revision=2,
                        transitioned_at=transitioned_at,
                    )
                    await self._update_reservation_locked(db, expired)
                    await db.commit()
                    raise UsageLedgerStateConflict("Budget reservation expired before release.")
                released = replace(
                    reservation,
                    state=BudgetReservationState.RELEASED,
                    revision=2,
                    transitioned_at=transitioned_at,
                )
                await self._update_reservation_locked(db, released)
                await db.commit()
                return BudgetReleaseResult(True)
            except Exception:
                await db.rollback()
                raise

    async def reconcile_expired(self, *, now: float, limit: int) -> int:
        if type(limit) is not int or not 1 <= limit <= MAX_RECONCILE_BATCH:
            raise ValueError("Usage reconciliation limit is invalid.")
        now = self._report_timestamp(now, "Usage reconciliation timestamp")
        async with self._connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                changed = await self._expire_locked(db, now=now, limit=limit)
                await db.commit()
                return changed
            except Exception:
                await db.rollback()
                raise

    async def reconciliation_page(self, *, after: str | None, limit: int) -> UsageLiabilityPage:
        self._ensure_initialized()
        after = validate_usage_liability_cursor(after)
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("Usage liability page size is invalid.")
        where = "WHERE kind = 'reservation' AND state = 'active'"
        if after is not None:
            where += " AND record_id > ?"
        parameters = (limit + 1,) if after is None else (after, limit + 1)
        async with self._connection() as db:
            rows = await (
                await db.execute(
                    f"SELECT {', '.join(_COLUMNS)} FROM durable_usage_ledger "
                    f"{where} ORDER BY record_id LIMIT ?",
                    parameters,
                )
            ).fetchall()
        records = tuple(self._decode_row(row) for row in rows[:limit])
        complete = len(rows) <= limit
        cursor = None
        if not complete:
            last = records[-1]
            if type(last) is not BudgetReservation:
                raise UsageLedgerCorrupt("Usage liability row is not an active reservation.")
            cursor = last.reservation_id
        return usage_liability_page(records, complete=complete, cursor=cursor)

    async def get_spend(self, *, since: float, api_key_id: str = "") -> SpendSnapshot:
        self._ensure_initialized()
        where = "occurred_at >= ? AND cost_nanos IS NOT NULL"
        parameters: list[object] = [self._report_timestamp(since, "Usage spend start")]
        if api_key_id:
            where += " AND api_key_id = ?"
            parameters.append(api_key_id)
        async with self._connection() as db:
            row = await (
                await db.execute(
                    f"""
                    SELECT COALESCE(SUM(cost_nanos), 0),
                           COALESCE(SUM(total_tokens), 0),
                           COUNT(*)
                    FROM durable_usage_ledger
                    WHERE {where}
                    """,
                    tuple(parameters),
                )
            ).fetchone()
        return SpendSnapshot(
            cost_nanos=int(row[0] or 0),
            total_tokens=int(row[1] or 0),
            calls=int(row[2] or 0),
            available=True,
        )

    async def import_legacy_usage(self, source_path: str) -> LegacyUsageImportResult:
        if not isinstance(source_path, str) or not source_path.strip():
            raise ValueError("Legacy usage source path is invalid.")
        source, exists, is_file = await asyncio.to_thread(self._legacy_source_details, source_path)
        if not exists:
            return LegacyUsageImportResult(0, 0, hashlib.sha256(b"").hexdigest(), True)
        target = await asyncio.to_thread(Path(self._database_path).resolve)
        if not is_file or source == target:
            raise ValueError("Legacy usage source path is invalid.")

        source_key = hashlib.sha256(str(source).casefold().encode("utf-8")).hexdigest()
        entries = await asyncio.to_thread(self._read_legacy_entries, source, source_key)
        checksum = self._migration_checksum(entries)
        imported = 0
        async with self._connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                marker = await (
                    await db.execute(
                        """
                        SELECT source_count, source_checksum
                        FROM durable_usage_migrations WHERE source_key = ?
                        """,
                        (source_key,),
                    )
                ).fetchone()
                if marker is not None:
                    previous_count = int(marker["source_count"])
                    previous_checksum = str(marker["source_checksum"])
                    current_prefix_checksum = self._migration_checksum(entries[:previous_count])
                    legacy_prefix_checksum = self._legacy_full_checksum(entries[:previous_count])
                    if len(entries) < previous_count or previous_checksum not in {
                        current_prefix_checksum,
                        legacy_prefix_checksum,
                        *self._pre_r2_migration_checksums(entries[:previous_count]),
                    }:
                        raise UsageLedgerConflict("Legacy usage source changed after verification.")

                target_hasher = hashlib.sha256()
                for entry in entries:
                    row = await self._get_by_event_locked(db, entry.event_id)
                    if row is None:
                        await self._insert_usage_locked(db, entry)
                        imported += 1
                        decoded = entry
                    else:
                        decoded = self._decode_row(row)
                    if type(decoded) is not UsageLedgerEntry or self._migration_record(
                        decoded
                    ) != self._migration_record(entry):
                        raise UsageLedgerConflict("Legacy usage target verification conflict.")
                    target_hasher.update(self._migration_payload(decoded))
                    target_hasher.update(b"\n")

                # Re-read before the atomic target commit to detect a moving source.
                verified_entries = await asyncio.to_thread(
                    self._read_legacy_entries, source, source_key
                )
                if (
                    len(verified_entries) != len(entries)
                    or self._migration_checksum(verified_entries) != checksum
                ):
                    raise UsageLedgerConflict("Legacy usage source changed during verification.")
                if target_hasher.hexdigest() != checksum:
                    raise UsageLedgerConflict("Legacy usage target checksum mismatch.")

                await db.execute(
                    """
                    INSERT INTO durable_usage_migrations (
                        source_key, source_count, source_checksum, completed_at
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(source_key) DO UPDATE SET
                        source_count = excluded.source_count,
                        source_checksum = excluded.source_checksum,
                        completed_at = excluded.completed_at
                    """,
                    (source_key, len(entries), checksum, time.time()),
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        return LegacyUsageImportResult(len(entries), imported, checksum, True)

    async def aggregate_credentials(
        self, *, since: float | None = None
    ) -> list[CredentialUsageAggregate]:
        where = "occurred_at IS NOT NULL"
        parameters: list[object] = []
        if since is not None:
            where += " AND occurred_at >= ?"
            parameters.append(self._report_timestamp(since, "Usage aggregate start"))

        detail_fields = (
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "cache_creation_tokens",
            "reasoning_tokens",
            "estimated_input_tokens",
            "estimated_tokens_saved",
            "compressed_messages",
            "latency_ms",
            "retry_count",
        )
        detail_columns = ",\n".join(
            f"SUM({self._usage_payload_integer(field)}) AS {field}" for field in detail_fields
        )
        async with self._connection() as db:
            rows = await (
                await db.execute(
                    f"""
                    WITH committed AS (
                        SELECT *, COUNT(*) OVER () AS source_rows
                        FROM durable_usage_ledger
                        WHERE {where}
                    )
                    SELECT credential_ref, MAX(provider) AS provider,
                           COUNT(*) AS calls,
                           SUM(success) AS successful_calls,
                           COUNT(*) - SUM(success) AS failed_calls,
                           {detail_columns},
                           SUM(total_tokens) AS total_tokens,
                           SUM(cost_nanos) AS cost_nanos,
                           SUM(CASE WHEN success = 1
                               THEN {self._usage_payload_integer("usage_reported")}
                               ELSE 0 END) AS reported_usage_calls,
                           MAX(source_rows) AS source_rows
                    FROM committed
                    GROUP BY credential_ref
                    ORDER BY credential_ref
                    """,
                    tuple(parameters),
                )
            ).fetchall()

        self._ensure_report_row_bound(rows)
        return [
            CredentialUsageAggregate(
                str(row["credential_ref"]),
                str(row["provider"] or ""),
                int(row["calls"]),
                int(row["successful_calls"]),
                int(row["failed_calls"]),
                int(row["input_tokens"]),
                int(row["output_tokens"]),
                int(row["total_tokens"]),
                int(row["cached_tokens"]),
                int(row["reasoning_tokens"]),
                int(row["estimated_input_tokens"]),
                int(row["estimated_tokens_saved"]),
                int(row["compressed_messages"]),
                int(row["latency_ms"]),
                int(row["retry_count"]),
                int(row["cost_nanos"]),
                int(row["cache_creation_tokens"]),
                int(row["reported_usage_calls"]),
            )
            for row in rows
        ]

    async def aggregate_providers(self) -> list[ProviderUsageAggregate]:
        entries = await self._committed_entries()
        grouped: dict[str, list[int]] = {}
        for entry in entries:
            provider = entry.provider or "unknown"
            totals = grouped.setdefault(provider, [0] * 6)
            values = (
                1,
                1 if entry.success else 0,
                0 if entry.success else 1,
                entry.total_tokens,
                entry.latency_ms,
                entry.cost_nanos,
            )
            for index, value in enumerate(values):
                totals[index] = self._checked_sum(totals[index], value)
        return [
            ProviderUsageAggregate(provider, *totals)
            for provider, totals in sorted(grouped.items())
        ]

    async def aggregate_time_series(
        self, *, since: float, until: float, points: int
    ) -> list[UsageTimeBucket]:
        since = self._report_timestamp(since, "Usage time-series start")
        until = self._report_timestamp(until, "Usage time-series end")
        if until <= since or type(points) is not int or not 1 <= points <= 1_000:
            raise ValueError("Usage time-series interval is invalid.")
        step = (until - since) / points
        totals = [[0] * 6 for _ in range(points)]
        async with self._connection() as db:
            rows = await (
                await db.execute(
                    f"""
                    WITH committed AS (
                        SELECT *, COUNT(*) OVER () AS source_rows
                        FROM durable_usage_ledger
                        WHERE occurred_at IS NOT NULL
                          AND occurred_at >= ? AND occurred_at < ?
                    )
                    SELECT MIN(CAST((occurred_at - ?) / ? AS INTEGER), ?) AS bucket_index,
                           COUNT(*) AS requests,
                           SUM(success) AS successful_requests,
                           COUNT(*) - SUM(success) AS failed_requests,
                           SUM(total_tokens) AS tokens,
                           SUM({self._usage_payload_integer("cached_tokens")}) AS cached_tokens,
                           SUM(cost_nanos) AS cost_nanos,
                           MAX(source_rows) AS source_rows
                    FROM committed
                    GROUP BY bucket_index
                    ORDER BY bucket_index
                    """,
                    (since, until, since, step, points - 1),
                )
            ).fetchall()
        self._ensure_report_row_bound(rows)
        for row in rows:
            totals[int(row["bucket_index"])] = [
                int(row["requests"]),
                int(row["successful_requests"]),
                int(row["failed_requests"]),
                int(row["tokens"]),
                int(row["cached_tokens"]),
                int(row["cost_nanos"]),
            ]
        return [
            UsageTimeBucket(
                since + (index * step),
                since + ((index + 1) * step),
                *values,
            )
            for index, values in enumerate(totals)
        ]

    @staticmethod
    def _usage_payload_integer(field: str) -> str:
        supported = {
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "cache_creation_tokens",
            "reasoning_tokens",
            "estimated_input_tokens",
            "estimated_tokens_saved",
            "compressed_messages",
            "latency_ms",
            "retry_count",
            "usage_reported",
        }
        if field not in supported:
            raise ValueError("Unsupported usage aggregate field.")
        return (
            "CAST(COALESCE(json_extract(payload, CASE kind "
            f"WHEN 'usage' THEN '$.{field}' ELSE '$.usage.{field}' END), 0) AS INTEGER)"
        )

    @staticmethod
    def _ensure_report_row_bound(rows: list[aiosqlite.Row]) -> None:
        if rows and int(rows[0]["source_rows"]) > MAX_USAGE_REPORT_ROWS:
            raise UsageLedgerCorrupt("Usage report exceeds the bounded row limit.")

    async def retire_credential(
        self,
        credential_ref: str,
        replacement_ref: str,
        *,
        provider: str,
        limit: int,
    ) -> int:
        self._validate_attribution(credential_ref, provider, limit)
        self._validate_attribution(replacement_ref, provider, limit)
        if credential_ref == replacement_ref:
            return 0
        async with self._connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                rows = await (
                    await db.execute(
                        f"""
                        SELECT {", ".join(_COLUMNS)}
                        FROM durable_usage_ledger
                        WHERE occurred_at IS NOT NULL AND credential_ref = ?
                        ORDER BY occurred_at, record_id
                        LIMIT ?
                        """,
                        (credential_ref, limit),
                    )
                ).fetchall()
                for row in rows:
                    decoded = self._decode_row(row)
                    if type(decoded) is UsageLedgerEntry:
                        rewritten: UsageLedgerEntry | BudgetReservation = replace(
                            decoded,
                            credential_ref=replacement_ref,
                            provider=provider,
                        )
                    else:
                        if decoded.usage is None:
                            raise UsageLedgerCorrupt(
                                "Committed reservation is missing usage attribution."
                            )
                        rewritten = replace(
                            decoded,
                            usage=replace(
                                decoded.usage,
                                credential_ref=replacement_ref,
                                provider=provider,
                            ),
                        )
                    await self._rewrite_attribution_locked(db, row, rewritten)
                await db.commit()
                return len(rows)
            except Exception:
                await db.rollback()
                raise

    async def _committed_entries(
        self, *, since: float | None = None, until: float | None = None
    ) -> list[UsageLedgerEntry]:
        where = "occurred_at IS NOT NULL"
        parameters: list[object] = []
        if since is not None:
            where += " AND occurred_at >= ?"
            parameters.append(self._report_timestamp(since, "Usage aggregate start"))
        if until is not None:
            where += " AND occurred_at < ?"
            parameters.append(self._report_timestamp(until, "Usage aggregate end"))
        async with self._connection() as db:
            rows = await (
                await db.execute(
                    f"""
                    SELECT {", ".join(_COLUMNS)} FROM durable_usage_ledger
                    WHERE {where} ORDER BY occurred_at, record_id
                    LIMIT ?
                    """,
                    tuple([*parameters, MAX_USAGE_REPORT_ROWS + 1]),
                )
            ).fetchall()
        if len(rows) > MAX_USAGE_REPORT_ROWS:
            raise UsageLedgerCorrupt("Usage report exceeds the bounded row limit.")
        entries: list[UsageLedgerEntry] = []
        for row in rows:
            decoded = self._decode_row(row)
            if type(decoded) is UsageLedgerEntry:
                entries.append(decoded)
            elif decoded.state is BudgetReservationState.COMMITTED and decoded.usage is not None:
                entries.append(decoded.usage)
            else:
                raise UsageLedgerCorrupt("Stored committed usage row is invalid.")
        return entries

    async def _rewrite_attribution_locked(
        self,
        db: aiosqlite.Connection,
        original: aiosqlite.Row,
        rewritten: UsageLedgerEntry | BudgetReservation,
    ) -> None:
        usage = rewritten if type(rewritten) is UsageLedgerEntry else rewritten.usage
        if usage is None:
            raise UsageLedgerCorrupt("Stored usage attribution is missing.")
        cursor = await db.execute(
            """
            UPDATE durable_usage_ledger
            SET credential_ref = ?, provider = ?, payload = ?
            WHERE record_id = ? AND revision = ? AND credential_ref = ?
            """,
            (
                usage.credential_ref,
                usage.provider,
                self._payload(rewritten),
                original["record_id"],
                original["revision"],
                original["credential_ref"],
            ),
        )
        if cursor.rowcount != 1:
            raise UsageLedgerStateConflict("Usage attribution revision conflict.")

    @staticmethod
    def _legacy_source_details(source_path: str) -> tuple[Path, bool, bool]:
        source = Path(source_path).resolve()
        return source, source.exists(), source.is_file()

    @staticmethod
    def _read_legacy_entries(source: Path, source_key: str) -> list[UsageLedgerEntry]:
        connection = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'usage_logs'"
            ).fetchone()
            if table is None:
                raise UsageLedgerCorrupt("Legacy usage source schema is missing.")
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(usage_logs)")}
            if not {"id", "filename", "timestamp"}.issubset(columns):
                raise UsageLedgerCorrupt("Legacy usage source schema is invalid.")
            selected = ["id", "filename", "timestamp"] + [
                name for name in _LEGACY_OPTIONAL_DEFAULTS if name in columns
            ]
            rows = connection.execute(
                f"SELECT {', '.join(selected)} FROM usage_logs ORDER BY id"
            ).fetchall()
        finally:
            connection.close()

        entries: list[UsageLedgerEntry] = []
        for row in rows:
            legacy_id = row["id"]
            if type(legacy_id) is not int or legacy_id <= 0:
                raise UsageLedgerCorrupt("Legacy usage source identity is invalid.")
            values = {
                name: (row[name] if name in row.keys() and row[name] is not None else default)
                for name, default in _LEGACY_OPTIONAL_DEFAULTS.items()
            }
            if type(values["success"]) is not int or values["success"] not in {0, 1}:
                raise UsageLedgerCorrupt("Legacy usage success flag is invalid.")
            quality = normalize_quality_decision(values)
            event_digest = hashlib.sha256(f"{source_key}:{legacy_id}".encode()).hexdigest()
            try:
                entries.append(
                    UsageLedgerEntry(
                        schema_version=USAGE_LEDGER_SCHEMA_VERSION,
                        event_id=f"use_{event_digest[:32]}",
                        occurred_at=row["timestamp"],
                        credential_ref=row["filename"],
                        request_id=values["request_id"],
                        model=values["model"],
                        provider=values["provider"],
                        status_code=values["status_code"],
                        success=bool(values["success"]),
                        input_tokens=values["input_tokens"],
                        output_tokens=values["output_tokens"],
                        total_tokens=values["total_tokens"],
                        cached_tokens=values["cached_tokens"],
                        reasoning_tokens=values["reasoning_tokens"],
                        estimated_input_tokens=values["estimated_input_tokens"],
                        estimated_tokens_saved=values["estimated_tokens_saved"],
                        compressed_messages=values["compressed_messages"],
                        quality_profile=quality["quality_profile"],
                        quality_policy_revision=quality["quality_policy_revision"],
                        compression_reason=quality["compression_reason"],
                        latency_ms=values["latency_ms"],
                        retry_count=values["retry_count"],
                        cost_nanos=usd_to_nanos(values["cost_usd"]),
                        api_key_id=values["api_key_id"],
                    )
                )
            except (TypeError, ValueError) as exc:
                raise UsageLedgerCorrupt("Legacy usage source record is invalid.") from exc
        return entries

    @staticmethod
    def _pre_r2_migration_checksums(entries: list[UsageLedgerEntry]) -> set[str]:
        """Reproduce both historical checkpoints before R2 added usage fields."""
        full = hashlib.sha256()
        unattributed = hashlib.sha256()
        for entry in entries:
            record = entry.to_record()
            record.pop("cache_creation_tokens")
            record.pop("usage_reported")
            for hasher in (full, unattributed):
                if hasher is unattributed:
                    record.pop("credential_ref")
                    record.pop("provider")
                hasher.update(
                    json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True).encode(
                        "utf-8"
                    )
                )
                hasher.update(b"\n")
        return {full.hexdigest(), unattributed.hexdigest()}

    @staticmethod
    def _migration_record(entry: UsageLedgerEntry) -> dict[str, object]:
        record = entry.to_record()
        record.pop("credential_ref")
        record.pop("provider")
        # Legacy usage has no reporting flag. R2 may infer it on decode and
        # persist that inference during credential retirement. Keep the original
        # migration representation; all historical usage and cost fields remain
        # verified, and the stored reporting flag is never rewritten here.
        record["usage_reported"] = False
        return record

    @classmethod
    def _migration_payload(cls, entry: UsageLedgerEntry) -> bytes:
        return json.dumps(
            cls._migration_record(entry),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
        ).encode("utf-8")

    @classmethod
    def _migration_checksum(cls, entries: list[UsageLedgerEntry]) -> str:
        hasher = hashlib.sha256()
        for entry in entries:
            hasher.update(cls._migration_payload(entry))
            hasher.update(b"\n")
        return hasher.hexdigest()

    @classmethod
    def _legacy_full_checksum(cls, entries: list[UsageLedgerEntry]) -> str:
        hasher = hashlib.sha256()
        for entry in entries:
            hasher.update(cls._payload(entry).encode("utf-8"))
            hasher.update(b"\n")
        return hasher.hexdigest()

    @staticmethod
    def _report_timestamp(value: float, label: str) -> float:
        if type(value) not in {int, float}:
            raise ValueError(f"{label} is invalid.")
        timestamp = float(value)
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError(f"{label} is invalid.")
        return timestamp

    @staticmethod
    def _checked_sum(current: int, value: int) -> int:
        total = current + value
        if total > MAX_COST_NANOS:
            raise UsageLedgerCorrupt("Usage aggregate exceeds the supported range.")
        return total

    @staticmethod
    def _validate_attribution(credential_ref: str, provider: str, limit: int) -> None:
        if (
            not isinstance(credential_ref, str)
            or not credential_ref
            or len(credential_ref) > 255
            or credential_ref in {".", ".."}
            or "/" in credential_ref
            or "\\" in credential_ref
            or any(ord(character) < 32 or ord(character) == 127 for character in credential_ref)
        ):
            raise ValueError("Usage credential reference is invalid.")
        if (
            not isinstance(provider, str)
            or len(provider) > 64
            or any(ord(character) < 32 or ord(character) == 127 for character in provider)
        ):
            raise ValueError("Usage provider is invalid.")
        if type(limit) is not int or not 1 <= limit <= MAX_RECONCILE_BATCH:
            raise ValueError("Usage retirement limit is invalid.")

    @asynccontextmanager
    async def _connection(self, *, allow_initializing: bool = False):
        self._ensure_initialized(allow_initializing=allow_initializing)
        if allow_initializing:
            async with open_sqlite(self._database_path, isolation_level=None) as connection:
                connection.row_factory = aiosqlite.Row
                yield connection
            return
        async with self._connection_lock:
            database = self._database
            if database is None:
                raise RuntimeError("Usage ledger repository is not initialized.")
            yield database

    def _ensure_initialized(self, *, allow_initializing: bool = False) -> None:
        if not self._initialized and not allow_initializing:
            raise RuntimeError("Usage ledger repository is not initialized.")

    @staticmethod
    async def _validate_schema_locked(db: aiosqlite.Connection) -> None:
        async def table_schema(table_name: str) -> dict[str, tuple[str, int, int]]:
            rows = await (await db.execute(f"PRAGMA table_info({table_name})")).fetchall()
            return {str(row[1]): (str(row[2]).upper(), int(row[3]), int(row[5])) for row in rows}

        if await table_schema("durable_usage_ledger") != _SQLITE_LEDGER_SCHEMA:
            raise UsageLedgerCorrupt("Usage ledger schema is incompatible.")
        if await table_schema("durable_usage_migrations") != _SQLITE_MIGRATION_SCHEMA:
            raise UsageLedgerCorrupt("Usage migration schema is incompatible.")

        index_rows = await (await db.execute("PRAGMA index_list(durable_usage_ledger)")).fetchall()
        indexes = {str(row[1]): (int(row[2]), int(row[4])) for row in index_rows}
        for index_name, (unique, partial, expected_columns) in _SQLITE_REQUIRED_INDEXES.items():
            if indexes.get(index_name) != (unique, partial):
                raise UsageLedgerCorrupt("Usage ledger index schema is incompatible.")
            column_rows = await (await db.execute(f"PRAGMA index_info({index_name})")).fetchall()
            if tuple(str(row[2]) for row in column_rows) != expected_columns:
                raise UsageLedgerCorrupt("Usage ledger index schema is incompatible.")

        row = await (
            await db.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' "
                "AND name = 'durable_usage_ledger'"
            )
        ).fetchone()
        schema_sql = " ".join(str(row[0] if row else "").lower().split())
        if "check (kind in ('usage', 'reservation'))" not in schema_sql:
            raise UsageLedgerCorrupt("Usage ledger constraints are incompatible.")

    @staticmethod
    def _require_entry(entry: UsageLedgerEntry) -> None:
        if type(entry) is not UsageLedgerEntry:
            raise ValueError("Usage ledger entry is invalid.")

    @staticmethod
    def _payload(value: UsageLedgerEntry | BudgetReservation) -> str:
        return json.dumps(
            value.to_record(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    async def _get_locked(self, db: aiosqlite.Connection, record_id: str):
        return await (
            await db.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM durable_usage_ledger WHERE record_id = ?",
                (record_id,),
            )
        ).fetchone()

    async def _get_by_event_locked(self, db: aiosqlite.Connection, event_id: str):
        return await (
            await db.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM durable_usage_ledger WHERE event_id = ?",
                (event_id,),
            )
        ).fetchone()

    @staticmethod
    def _request_from_reservation(
        reservation: BudgetReservation,
    ) -> BudgetReservationRequest:
        return BudgetReservationRequest(
            schema_version=reservation.schema_version,
            reservation_id=reservation.reservation_id,
            key_id=reservation.key_id,
            created_at=reservation.created_at,
            expires_at=reservation.expires_at,
            estimated_tokens=reservation.estimated_tokens,
            estimated_cost_nanos=reservation.estimated_cost_nanos,
            daily_budget_nanos=reservation.daily_budget_nanos,
            monthly_budget_nanos=reservation.monthly_budget_nanos,
        )

    async def _insert_usage_locked(self, db: aiosqlite.Connection, entry: UsageLedgerEntry) -> None:
        try:
            await db.execute(
                """
                INSERT INTO durable_usage_ledger (
                    record_id, kind, state, revision, key_id, created_at,
                    event_id, occurred_at, credential_ref, provider, success,
                    total_tokens, cost_nanos, api_key_id, payload
                ) VALUES (?, 'usage', 'committed', 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.event_id,
                    entry.api_key_id,
                    entry.occurred_at,
                    entry.event_id,
                    entry.occurred_at,
                    entry.credential_ref,
                    entry.provider,
                    1 if entry.success else 0,
                    entry.total_tokens,
                    entry.cost_nanos,
                    entry.api_key_id,
                    self._payload(entry),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise UsageLedgerConflict("Usage event idempotency conflict.") from exc

    async def _insert_reservation_locked(
        self, db: aiosqlite.Connection, reservation: BudgetReservation
    ) -> None:
        try:
            await db.execute(
                """
                INSERT INTO durable_usage_ledger (
                    record_id, kind, state, revision, key_id, created_at, expires_at,
                    estimated_cost_nanos, daily_budget_nanos, monthly_budget_nanos, payload
                ) VALUES (?, 'reservation', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reservation.reservation_id,
                    reservation.state.value,
                    reservation.revision,
                    reservation.key_id,
                    reservation.created_at,
                    reservation.expires_at,
                    reservation.estimated_cost_nanos,
                    reservation.daily_budget_nanos,
                    reservation.monthly_budget_nanos,
                    self._payload(reservation),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise UsageLedgerConflict("Budget reservation idempotency conflict.") from exc

    async def _update_reservation_locked(
        self, db: aiosqlite.Connection, reservation: BudgetReservation
    ) -> None:
        usage = reservation.usage
        try:
            cursor = await db.execute(
                """
                UPDATE durable_usage_ledger
                SET state = ?, revision = ?, transitioned_at = ?,
                    event_id = ?, occurred_at = ?, credential_ref = ?, provider = ?,
                    success = ?, total_tokens = ?, cost_nanos = ?, api_key_id = ?, payload = ?
                WHERE record_id = ? AND kind = 'reservation' AND revision = 1
                """,
                (
                    reservation.state.value,
                    reservation.revision,
                    reservation.transitioned_at,
                    None if usage is None else usage.event_id,
                    None if usage is None else usage.occurred_at,
                    None if usage is None else usage.credential_ref,
                    None if usage is None else usage.provider,
                    None if usage is None else (1 if usage.success else 0),
                    None if usage is None else usage.total_tokens,
                    None if usage is None else usage.cost_nanos,
                    None if usage is None else usage.api_key_id,
                    self._payload(reservation),
                    reservation.reservation_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise UsageLedgerConflict("Usage event idempotency conflict.") from exc
        if cursor.rowcount != 1:
            raise UsageLedgerStateConflict("Budget reservation revision conflict.")

    async def _expire_locked(self, db: aiosqlite.Connection, *, now: float, limit: int) -> int:
        rows = await (
            await db.execute(
                f"""
                SELECT {", ".join(_COLUMNS)}
                FROM durable_usage_ledger
                WHERE kind = 'reservation' AND state = 'active' AND expires_at <= ?
                ORDER BY expires_at, record_id
                LIMIT ?
                """,
                (float(now), limit),
            )
        ).fetchall()
        for row in rows:
            reservation = self._decode_reservation(row)
            expired = replace(
                reservation,
                state=BudgetReservationState.EXPIRED,
                revision=2,
                transitioned_at=max(float(now), reservation.expires_at),
            )
            await self._update_reservation_locked(db, expired)
        return len(rows)

    async def _active_cost_locked(
        self,
        db: aiosqlite.Connection,
        *,
        key_id: str,
        now: float,
        exclude_record_id: str = "",
    ) -> int:
        where = "kind = 'reservation' AND state = 'active' AND key_id = ? AND expires_at > ?"
        parameters: list[object] = [key_id, float(now)]
        if exclude_record_id:
            where += " AND record_id <> ?"
            parameters.append(exclude_record_id)
        row = await (
            await db.execute(
                f"""
                SELECT COALESCE(SUM(estimated_cost_nanos), 0)
                FROM durable_usage_ledger WHERE {where}
                """,
                tuple(parameters),
            )
        ).fetchone()
        return int(row[0] or 0)

    async def _committed_cost_locked(
        self, db: aiosqlite.Connection, *, key_id: str, since: float
    ) -> int:
        row = await (
            await db.execute(
                """
                SELECT COALESCE(SUM(
                    CASE
                        WHEN kind = 'reservation' THEN estimated_cost_nanos
                        ELSE cost_nanos
                    END
                ), 0)
                FROM durable_usage_ledger
                WHERE (
                    api_key_id = ? AND occurred_at >= ? AND cost_nanos IS NOT NULL
                ) OR (
                    kind = 'reservation' AND state = 'expired'
                    AND key_id = ? AND created_at >= ?
                    AND estimated_cost_nanos IS NOT NULL
                )
                """,
                (key_id, float(since), key_id, float(since)),
            )
        ).fetchone()
        return int(row[0] or 0)

    def _decode_row(self, row: aiosqlite.Row) -> UsageLedgerEntry | BudgetReservation:
        try:
            payload = json.loads(row["payload"])
            if row["kind"] == "usage":
                entry = usage_entry_from_record(payload)
                expected = (
                    entry.event_id,
                    "usage",
                    "committed",
                    1,
                    entry.api_key_id,
                    entry.occurred_at,
                    entry.event_id,
                    entry.occurred_at,
                    entry.credential_ref,
                    entry.provider,
                    1 if entry.success else 0,
                    entry.total_tokens,
                    entry.cost_nanos,
                    entry.api_key_id,
                )
                actual = (
                    row["record_id"],
                    row["kind"],
                    row["state"],
                    row["revision"],
                    row["key_id"],
                    row["created_at"],
                    row["event_id"],
                    row["occurred_at"],
                    row["credential_ref"],
                    row["provider"],
                    row["success"],
                    row["total_tokens"],
                    row["cost_nanos"],
                    row["api_key_id"],
                )
                if actual != expected:
                    raise ValueError
                return entry
            if row["kind"] == "reservation":
                reservation = budget_reservation_from_record(payload)
                usage = reservation.usage
                expected = (
                    reservation.reservation_id,
                    reservation.state.value,
                    reservation.revision,
                    reservation.key_id,
                    reservation.created_at,
                    reservation.expires_at,
                    reservation.transitioned_at,
                    reservation.estimated_cost_nanos,
                    reservation.daily_budget_nanos,
                    reservation.monthly_budget_nanos,
                    None if usage is None else usage.event_id,
                    None if usage is None else usage.occurred_at,
                    None if usage is None else usage.credential_ref,
                    None if usage is None else usage.provider,
                    None if usage is None else (1 if usage.success else 0),
                    None if usage is None else usage.total_tokens,
                    None if usage is None else usage.cost_nanos,
                    None if usage is None else usage.api_key_id,
                )
                actual = (
                    row["record_id"],
                    row["state"],
                    row["revision"],
                    row["key_id"],
                    row["created_at"],
                    row["expires_at"],
                    row["transitioned_at"],
                    row["estimated_cost_nanos"],
                    row["daily_budget_nanos"],
                    row["monthly_budget_nanos"],
                    row["event_id"],
                    row["occurred_at"],
                    row["credential_ref"],
                    row["provider"],
                    row["success"],
                    row["total_tokens"],
                    row["cost_nanos"],
                    row["api_key_id"],
                )
                if actual != expected:
                    raise ValueError
                return reservation
            raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UsageLedgerCorrupt("Stored usage ledger record is invalid.") from exc

    def _decode_reservation(self, row: aiosqlite.Row) -> BudgetReservation:
        decoded = self._decode_row(row)
        if type(decoded) is not BudgetReservation:
            raise UsageLedgerConflict("Usage ledger record kind conflict.")
        return decoded
