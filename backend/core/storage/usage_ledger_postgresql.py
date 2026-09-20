"""PostgreSQL durable usage ledger with serialized per-key hard budgets."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from typing import Any

import asyncpg
from core.usage_ledger import (
    DAILY_WINDOW_SECONDS,
    MAX_COST_NANOS,
    MAX_RECONCILE_BATCH,
    MAX_USAGE_REPORT_ROWS,
    MONTHLY_WINDOW_SECONDS,
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
    validate_usage_liability_cursor,
)

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

_POSTGRES_LEDGER_SCHEMA = {
    "record_id": ("text", "NO"),
    "kind": ("text", "NO"),
    "state": ("text", "NO"),
    "revision": ("integer", "NO"),
    "key_id": ("text", "NO"),
    "created_at": ("double precision", "NO"),
    "expires_at": ("double precision", "YES"),
    "transitioned_at": ("double precision", "YES"),
    "estimated_cost_nanos": ("bigint", "YES"),
    "daily_budget_nanos": ("bigint", "YES"),
    "monthly_budget_nanos": ("bigint", "YES"),
    "event_id": ("text", "YES"),
    "occurred_at": ("double precision", "YES"),
    "credential_ref": ("text", "YES"),
    "provider": ("text", "YES"),
    "success": ("boolean", "YES"),
    "total_tokens": ("bigint", "YES"),
    "cost_nanos": ("bigint", "YES"),
    "api_key_id": ("text", "YES"),
    "payload": ("jsonb", "NO"),
}
_POSTGRES_SCHEMAS = {
    "durable_usage_budget_keys": {"key_id": ("text", "NO")},
    "durable_usage_ledger": _POSTGRES_LEDGER_SCHEMA,
}
_POSTGRES_REQUIRED_INDEXES = {
    "idx_durable_usage_pg_spend": ("(api_key_id, occurred_at)", "cost_nanos is not null"),
    "idx_durable_usage_pg_budget": ("(key_id, state, expires_at)", "kind = 'reservation'"),
    "idx_durable_usage_pg_credential": (
        "(credential_ref, occurred_at)",
        "occurred_at is not null",
    ),
}


class PostgreSQLUsageLedgerRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._initialized = False

    async def initialize(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS durable_usage_budget_keys (
                key_id TEXT PRIMARY KEY
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS durable_usage_ledger (
                record_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK (kind IN ('usage', 'reservation')),
                state TEXT NOT NULL,
                revision INTEGER NOT NULL,
                key_id TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL,
                expires_at DOUBLE PRECISION,
                transitioned_at DOUBLE PRECISION,
                estimated_cost_nanos BIGINT,
                daily_budget_nanos BIGINT,
                monthly_budget_nanos BIGINT,
                event_id TEXT UNIQUE,
                occurred_at DOUBLE PRECISION,
                credential_ref TEXT,
                provider TEXT,
                success BOOLEAN,
                total_tokens BIGINT,
                cost_nanos BIGINT,
                api_key_id TEXT,
                payload JSONB NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_durable_usage_pg_spend
            ON durable_usage_ledger(api_key_id, occurred_at)
            WHERE cost_nanos IS NOT NULL
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_durable_usage_pg_budget
            ON durable_usage_ledger(key_id, state, expires_at)
            WHERE kind = 'reservation'
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_durable_usage_pg_credential
            ON durable_usage_ledger(credential_ref, occurred_at)
            WHERE occurred_at IS NOT NULL
            """,
        )
        async with self._pool.acquire() as connection:
            for index, statement in enumerate(statements):
                await connection.execute(statement)
                if index == len(statements) - 1:
                    rows = await connection.fetch(
                        """
                        SELECT table_name, column_name, data_type, is_nullable
                        FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name IN (
                              'durable_usage_budget_keys', 'durable_usage_ledger'
                          )
                        """
                    )
                    try:
                        actual_schemas: dict[str, dict[str, tuple[str, str]]] = {}
                        for row in rows:
                            actual_schemas.setdefault(str(row["table_name"]), {})[
                                str(row["column_name"])
                            ] = (str(row["data_type"]), str(row["is_nullable"]))
                    except (KeyError, TypeError) as exc:
                        raise UsageLedgerCorrupt("Usage ledger schema is incompatible.") from exc
                    if actual_schemas != _POSTGRES_SCHEMAS:
                        raise UsageLedgerCorrupt("Usage ledger schema is incompatible.")
                    constraint_rows = await connection.fetch(
                        """
                        SELECT table_ref.relname AS table_name, constraint_ref.contype::text AS contype,
                               pg_get_constraintdef(constraint_ref.oid) AS definition
                        FROM pg_constraint AS constraint_ref
                        JOIN pg_class AS table_ref
                          ON table_ref.oid = constraint_ref.conrelid
                        JOIN pg_namespace AS namespace_ref
                          ON namespace_ref.oid = table_ref.relnamespace
                        WHERE namespace_ref.nspname = current_schema()
                          AND table_ref.relname IN (
                              'durable_usage_budget_keys', 'durable_usage_ledger'
                          )
                        """
                    )
                    constraints = {
                        (
                            str(row["table_name"]),
                            str(row["contype"]),
                            " ".join(str(row["definition"]).lower().split()),
                        )
                        for row in constraint_rows
                    }
                    required_constraints = {
                        ("durable_usage_budget_keys", "p", "primary key (key_id)"),
                        ("durable_usage_ledger", "p", "primary key (record_id)"),
                        ("durable_usage_ledger", "u", "unique (event_id)"),
                    }
                    kind_checks = [
                        definition
                        for table_name, constraint_type, definition in constraints
                        if table_name == "durable_usage_ledger" and constraint_type == "c"
                    ]
                    if not required_constraints.issubset(constraints) or not any(
                        all(fragment in definition for fragment in ("kind", "usage", "reservation"))
                        for definition in kind_checks
                    ):
                        raise UsageLedgerCorrupt("Usage ledger constraints are incompatible.")
                    index_rows = await connection.fetch(
                        """
                        SELECT indexname, indexdef FROM pg_indexes
                        WHERE schemaname = current_schema()
                          AND tablename = 'durable_usage_ledger'
                        """
                    )
                    indexes = {
                        str(row["indexname"]): " ".join(str(row["indexdef"]).lower().split())
                        for row in index_rows
                    }
                    for index_name, fragments in _POSTGRES_REQUIRED_INDEXES.items():
                        definition = indexes.get(index_name, "")
                        if any(fragment not in definition for fragment in fragments):
                            raise UsageLedgerCorrupt("Usage ledger index schema is incompatible.")
        self._initialized = True

    async def check_available(self) -> None:
        self._ensure_initialized()
        async with self._pool.acquire() as connection:
            result = await connection.fetchval(
                "SELECT COUNT(*) FROM durable_usage_ledger WHERE FALSE"
            )
        if result != 0:
            raise UsageLedgerCorrupt("Usage ledger availability probe failed.")

    async def append_usage(self, entry: UsageLedgerEntry) -> UsageAppendResult:
        self._ensure_initialized()
        if type(entry) is not UsageLedgerEntry:
            raise ValueError("Usage ledger entry is invalid.")
        try:
            async with self._pool.acquire() as connection:
                await self._insert_usage(connection, entry)
            return UsageAppendResult(True, False)
        except asyncpg.UniqueViolationError:
            async with self._pool.acquire() as connection:
                row = await self._get_by_event(connection, entry.event_id)
            if row is not None and self._decode(row) == entry:
                return UsageAppendResult(False, True)
            raise UsageLedgerConflict("Usage event idempotency conflict.") from None

    async def reserve_budget(self, request: BudgetReservationRequest) -> BudgetReservationDecision:
        self._ensure_initialized()
        if type(request) is not BudgetReservationRequest:
            raise ValueError("Budget reservation request is invalid.")
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await self._lock_key(connection, request.key_id)
                await connection.execute(
                    """
                    UPDATE durable_usage_ledger
                    SET state = 'expired', revision = 2, transitioned_at = expires_at,
                        payload = jsonb_set(
                            jsonb_set(payload, '{state}', '"expired"'::jsonb),
                            '{revision}', '2'::jsonb
                        ) || jsonb_build_object('transitioned_at', expires_at)
                    WHERE kind = 'reservation' AND state = 'active'
                      AND key_id = $1 AND expires_at <= $2
                    """,
                    request.key_id,
                    request.created_at,
                )
                existing = await self._get(connection, request.reservation_id, for_update=True)
                if existing is not None:
                    reservation = self._decode_reservation(existing)
                    if reservation.admits_delivery_replay(request):
                        return BudgetReservationDecision(
                            True,
                            request.reservation_id,
                            idempotent=True,
                            replayed=True,
                        )
                    if (
                        reservation.state is BudgetReservationState.COMMITTED
                        and reservation.matches_operation(request)
                    ):
                        raise UsageLedgerStateConflict("Budget reservation replay window expired.")
                    if self._request(reservation) != request:
                        raise UsageLedgerConflict("Budget reservation idempotency conflict.")
                    if reservation.state is not BudgetReservationState.ACTIVE:
                        raise UsageLedgerStateConflict("Budget reservation state conflict.")
                    return BudgetReservationDecision(True, request.reservation_id, idempotent=True)
                active = await connection.fetchval(
                    """
                    SELECT COALESCE(SUM(estimated_cost_nanos), 0)
                    FROM durable_usage_ledger
                    WHERE kind = 'reservation' AND state = 'active'
                      AND key_id = $1 AND expires_at > $2
                    """,
                    request.key_id,
                    request.created_at,
                )
                if request.daily_budget_nanos is not None:
                    committed = await self._committed_cost(
                        connection,
                        request.key_id,
                        request.created_at - DAILY_WINDOW_SECONDS,
                    )
                    if (
                        committed + int(active or 0) + request.estimated_cost_nanos
                        > request.daily_budget_nanos
                    ):
                        return BudgetReservationDecision(
                            False, request.reservation_id, reason="daily_budget"
                        )
                if request.monthly_budget_nanos is not None:
                    committed = await self._committed_cost(
                        connection,
                        request.key_id,
                        request.created_at - MONTHLY_WINDOW_SECONDS,
                    )
                    if (
                        committed + int(active or 0) + request.estimated_cost_nanos
                        > request.monthly_budget_nanos
                    ):
                        return BudgetReservationDecision(
                            False, request.reservation_id, reason="monthly_budget"
                        )
                await self._insert_reservation(connection, BudgetReservation.active(request))
                return BudgetReservationDecision(True, request.reservation_id)

    async def commit_reservation(
        self,
        reservation_id: str,
        usage: UsageLedgerEntry,
        *,
        transitioned_at: float,
    ) -> BudgetCommitResult:
        self._ensure_initialized()
        if type(usage) is not UsageLedgerEntry:
            raise ValueError("Usage ledger entry is invalid.")
        expired = False
        result: BudgetCommitResult | None = None
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await self._get(connection, reservation_id)
                if row is None:
                    raise UsageLedgerStateConflict("Budget reservation state conflict.")
                initial = self._decode_reservation(row)
                await self._lock_key(connection, initial.key_id)
                row = await self._get(connection, reservation_id, for_update=True)
                reservation = self._decode_reservation(row)
                if reservation.state is BudgetReservationState.COMMITTED:
                    if reservation.usage != usage:
                        raise UsageLedgerConflict("Budget commit idempotency conflict.")
                    return BudgetCommitResult(False, idempotent=True)
                if reservation.state is not BudgetReservationState.ACTIVE:
                    raise UsageLedgerStateConflict("Budget reservation state conflict.")
                if usage.api_key_id != reservation.key_id:
                    raise UsageLedgerConflict("Budget commit attribution conflict.")
                if transitioned_at >= reservation.expires_at:
                    await self._update_reservation(
                        connection,
                        replace(
                            reservation,
                            state=BudgetReservationState.EXPIRED,
                            revision=2,
                            transitioned_at=transitioned_at,
                        ),
                    )
                    expired = True
                else:
                    result = await self._commit_active(
                        connection,
                        reservation,
                        usage,
                        transitioned_at,
                    )
        if expired:
            raise UsageLedgerStateConflict("Budget reservation expired before commit.")
        if result is None:
            raise UsageLedgerStateConflict("Budget reservation state conflict.")
        return result

    async def release_reservation(
        self, reservation_id: str, *, transitioned_at: float
    ) -> BudgetReleaseResult:
        self._ensure_initialized()
        expired = False
        result: BudgetReleaseResult | None = None
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await self._get(connection, reservation_id)
                if row is None:
                    raise UsageLedgerStateConflict("Budget reservation state conflict.")
                initial = self._decode_reservation(row)
                await self._lock_key(connection, initial.key_id)
                reservation = self._decode_reservation(
                    await self._get(connection, reservation_id, for_update=True)
                )
                if reservation.state is BudgetReservationState.RELEASED:
                    return BudgetReleaseResult(False, idempotent=True)
                if reservation.state is not BudgetReservationState.ACTIVE:
                    raise UsageLedgerStateConflict("Budget reservation state conflict.")
                state = (
                    BudgetReservationState.EXPIRED
                    if transitioned_at >= reservation.expires_at
                    else BudgetReservationState.RELEASED
                )
                await self._update_reservation(
                    connection,
                    replace(
                        reservation,
                        state=state,
                        revision=2,
                        transitioned_at=transitioned_at,
                    ),
                )
                if state is BudgetReservationState.EXPIRED:
                    expired = True
                else:
                    result = BudgetReleaseResult(True)
        if expired:
            raise UsageLedgerStateConflict("Budget reservation expired before release.")
        if result is None:
            raise UsageLedgerStateConflict("Budget reservation state conflict.")
        return result

    async def reconcile_expired(self, *, now: float, limit: int) -> int:
        self._ensure_initialized()
        self._limit(limit)
        async with self._pool.acquire() as connection:
            result = await connection.fetch(
                """
                WITH candidates AS (
                    SELECT record_id FROM durable_usage_ledger
                    WHERE kind = 'reservation' AND state = 'active' AND expires_at <= $1
                    ORDER BY expires_at, record_id LIMIT $2 FOR UPDATE SKIP LOCKED
                )
                UPDATE durable_usage_ledger AS ledger
                SET state = 'expired', revision = 2, transitioned_at = ledger.expires_at,
                    payload = jsonb_set(
                        jsonb_set(ledger.payload, '{state}', '"expired"'::jsonb),
                        '{revision}', '2'::jsonb
                    ) || jsonb_build_object('transitioned_at', ledger.expires_at)
                FROM candidates WHERE ledger.record_id = candidates.record_id
                RETURNING ledger.record_id
                """,
                self._timestamp(now),
                limit,
            )
        return len(result)

    async def reconciliation_page(self, *, after: str | None, limit: int) -> UsageLiabilityPage:
        self._ensure_initialized()
        after = validate_usage_liability_cursor(after)
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("Usage liability page size is invalid.")
        where = "WHERE kind = 'reservation' AND state = 'active'"
        if after is not None:
            where += " AND record_id > $2"
        arguments = (limit + 1,) if after is None else (limit + 1, after)
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                f"SELECT {', '.join(_COLUMNS)} FROM durable_usage_ledger "
                f"{where} ORDER BY record_id LIMIT $1",
                *arguments,
            )
        records = tuple(self._decode(row) for row in rows[:limit])
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
        parameters: list[Any] = [self._timestamp(since)]
        where = "occurred_at >= $1 AND cost_nanos IS NOT NULL"
        if api_key_id:
            parameters.append(api_key_id)
            where += " AND api_key_id = $2"
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT COALESCE(SUM(cost_nanos), 0) AS cost,
                       COALESCE(SUM(total_tokens), 0) AS tokens, COUNT(*) AS calls
                FROM durable_usage_ledger WHERE {where}
                """,
                *parameters,
            )
        return SpendSnapshot(int(row["cost"]), int(row["tokens"]), int(row["calls"]), True)

    async def aggregate_credentials(
        self, *, since: float | None = None
    ) -> list[CredentialUsageAggregate]:
        return self._aggregate_credentials(await self._entries(since=since))

    async def aggregate_providers(self) -> list[ProviderUsageAggregate]:
        return self._aggregate_providers(await self._entries())

    async def aggregate_time_series(
        self, *, since: float, until: float, points: int
    ) -> list[UsageTimeBucket]:
        since = self._timestamp(since)
        until = self._timestamp(until)
        if until <= since or type(points) is not int or not 1 <= points <= 1_000:
            raise ValueError("Usage time-series interval is invalid.")
        return self._aggregate_time(
            await self._entries(since=since, until=until), since, until, points
        )

    async def retire_credential(
        self,
        credential_ref: str,
        replacement_ref: str,
        *,
        provider: str,
        limit: int,
    ) -> int:
        self._attribution(credential_ref, provider, limit)
        self._attribution(replacement_ref, provider, limit)
        if credential_ref == replacement_ref:
            return 0
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                rows = await connection.fetch(
                    f"""
                    SELECT {", ".join(_COLUMNS)} FROM durable_usage_ledger
                    WHERE occurred_at IS NOT NULL AND credential_ref = $1
                    ORDER BY occurred_at, record_id LIMIT $2 FOR UPDATE
                    """,
                    credential_ref,
                    limit,
                )
                for row in rows:
                    decoded = self._decode(row)
                    if type(decoded) is UsageLedgerEntry:
                        rewritten: UsageLedgerEntry | BudgetReservation = replace(
                            decoded, credential_ref=replacement_ref, provider=provider
                        )
                        usage = rewritten
                    else:
                        if decoded.usage is None:
                            raise UsageLedgerCorrupt("Committed reservation usage is missing.")
                        usage = replace(
                            decoded.usage,
                            credential_ref=replacement_ref,
                            provider=provider,
                        )
                        rewritten = replace(decoded, usage=usage)
                    updated = await connection.execute(
                        """
                        UPDATE durable_usage_ledger
                        SET credential_ref = $1, provider = $2, payload = $3::jsonb
                        WHERE record_id = $4 AND revision = $5 AND credential_ref = $6
                        """,
                        usage.credential_ref,
                        usage.provider,
                        self._payload(rewritten),
                        row["record_id"],
                        row["revision"],
                        row["credential_ref"],
                    )
                    if updated != "UPDATE 1":
                        raise UsageLedgerStateConflict("Usage attribution revision conflict.")
                return len(rows)

    async def _entries(
        self, *, since: float | None = None, until: float | None = None
    ) -> list[UsageLedgerEntry]:
        clauses = ["occurred_at IS NOT NULL"]
        parameters: list[Any] = []
        if since is not None:
            parameters.append(self._timestamp(since))
            clauses.append(f"occurred_at >= ${len(parameters)}")
        if until is not None:
            parameters.append(self._timestamp(until))
            clauses.append(f"occurred_at < ${len(parameters)}")
        parameters.append(MAX_USAGE_REPORT_ROWS + 1)
        limit_parameter = len(parameters)
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                f"SELECT {', '.join(_COLUMNS)} FROM durable_usage_ledger "
                f"WHERE {' AND '.join(clauses)} ORDER BY occurred_at, record_id "
                f"LIMIT ${limit_parameter}",
                *parameters,
            )
        if len(rows) > MAX_USAGE_REPORT_ROWS:
            raise UsageLedgerCorrupt("Usage report exceeds the bounded row limit.")
        entries = []
        for row in rows:
            decoded = self._decode(row)
            if type(decoded) is UsageLedgerEntry:
                entries.append(decoded)
            elif decoded.state is BudgetReservationState.COMMITTED and decoded.usage is not None:
                entries.append(decoded.usage)
            else:
                raise UsageLedgerCorrupt("Stored committed usage row is invalid.")
        return entries

    async def _lock_key(self, connection: Any, key_id: str) -> None:
        await connection.execute(
            "INSERT INTO durable_usage_budget_keys (key_id) VALUES ($1) ON CONFLICT DO NOTHING",
            key_id,
        )
        await connection.fetchval(
            "SELECT key_id FROM durable_usage_budget_keys WHERE key_id = $1 FOR UPDATE",
            key_id,
        )

    async def _commit_active(
        self,
        connection: Any,
        reservation: BudgetReservation,
        usage: UsageLedgerEntry,
        transitioned_at: float,
    ) -> BudgetCommitResult:
        if await self._get_by_event(connection, usage.event_id) is not None:
            raise UsageLedgerConflict("Usage event idempotency conflict.")
        active = await connection.fetchval(
            """
            SELECT COALESCE(SUM(estimated_cost_nanos), 0)
            FROM durable_usage_ledger
            WHERE kind = 'reservation' AND state = 'active' AND key_id = $1
              AND expires_at > $2 AND record_id <> $3
            """,
            reservation.key_id,
            transitioned_at,
            reservation.reservation_id,
        )
        overspent = usage.cost_nanos > reservation.estimated_cost_nanos
        if reservation.daily_budget_nanos is not None:
            daily = await self._committed_cost(
                connection,
                reservation.key_id,
                transitioned_at - DAILY_WINDOW_SECONDS,
            )
            overspent = (
                overspent
                or daily + int(active or 0) + usage.cost_nanos > reservation.daily_budget_nanos
            )
        if reservation.monthly_budget_nanos is not None:
            monthly = await self._committed_cost(
                connection,
                reservation.key_id,
                transitioned_at - MONTHLY_WINDOW_SECONDS,
            )
            overspent = (
                overspent
                or monthly + int(active or 0) + usage.cost_nanos > reservation.monthly_budget_nanos
            )
        await self._update_reservation(
            connection,
            replace(
                reservation,
                state=BudgetReservationState.COMMITTED,
                revision=2,
                transitioned_at=transitioned_at,
                usage=usage,
            ),
        )
        return BudgetCommitResult(True, overspent=overspent)

    async def _committed_cost(self, connection: Any, key_id: str, since: float) -> int:
        return int(
            await connection.fetchval(
                """
                SELECT COALESCE(SUM(
                    CASE
                        WHEN kind = 'reservation' THEN estimated_cost_nanos
                        ELSE cost_nanos
                    END
                ), 0) FROM durable_usage_ledger
                WHERE (
                    api_key_id = $1 AND occurred_at >= $2 AND cost_nanos IS NOT NULL
                ) OR (
                    kind = 'reservation' AND state = 'expired'
                    AND key_id = $1 AND created_at >= $2
                    AND estimated_cost_nanos IS NOT NULL
                )
                """,
                key_id,
                since,
            )
            or 0
        )

    async def _get(self, connection: Any, record_id: str, *, for_update: bool = False):
        suffix = " FOR UPDATE" if for_update else ""
        return await connection.fetchrow(
            f"SELECT {', '.join(_COLUMNS)} FROM durable_usage_ledger WHERE record_id = $1{suffix}",
            record_id,
        )

    async def _get_by_event(self, connection: Any, event_id: str):
        return await connection.fetchrow(
            f"SELECT {', '.join(_COLUMNS)} FROM durable_usage_ledger WHERE event_id = $1",
            event_id,
        )

    async def _insert_usage(self, connection: Any, entry: UsageLedgerEntry) -> None:
        await connection.execute(
            """
            INSERT INTO durable_usage_ledger (
                record_id, kind, state, revision, key_id, created_at, event_id,
                occurred_at, credential_ref, provider, success, total_tokens,
                cost_nanos, api_key_id, payload
            ) VALUES ($1, 'usage', 'committed', 1, $2, $3, $1, $3, $4, $5, $6,
                      $7, $8, $2, $9::jsonb)
            """,
            entry.event_id,
            entry.api_key_id,
            entry.occurred_at,
            entry.credential_ref,
            entry.provider,
            entry.success,
            entry.total_tokens,
            entry.cost_nanos,
            self._payload(entry),
        )

    async def _insert_reservation(self, connection: Any, value: BudgetReservation) -> None:
        await connection.execute(
            """
            INSERT INTO durable_usage_ledger (
                record_id, kind, state, revision, key_id, created_at, expires_at,
                estimated_cost_nanos, daily_budget_nanos, monthly_budget_nanos, payload
            ) VALUES ($1, 'reservation', $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
            """,
            value.reservation_id,
            value.state.value,
            value.revision,
            value.key_id,
            value.created_at,
            value.expires_at,
            value.estimated_cost_nanos,
            value.daily_budget_nanos,
            value.monthly_budget_nanos,
            self._payload(value),
        )

    async def _update_reservation(self, connection: Any, value: BudgetReservation) -> None:
        usage = value.usage
        try:
            status = await connection.execute(
                """
                UPDATE durable_usage_ledger SET
                    state = $1, revision = $2, transitioned_at = $3, event_id = $4,
                    occurred_at = $5, credential_ref = $6, provider = $7, success = $8,
                    total_tokens = $9, cost_nanos = $10, api_key_id = $11, payload = $12::jsonb
                WHERE record_id = $13 AND kind = 'reservation' AND revision = 1
                """,
                value.state.value,
                value.revision,
                value.transitioned_at,
                None if usage is None else usage.event_id,
                None if usage is None else usage.occurred_at,
                None if usage is None else usage.credential_ref,
                None if usage is None else usage.provider,
                None if usage is None else usage.success,
                None if usage is None else usage.total_tokens,
                None if usage is None else usage.cost_nanos,
                None if usage is None else usage.api_key_id,
                self._payload(value),
                value.reservation_id,
            )
        except asyncpg.UniqueViolationError as exc:
            raise UsageLedgerConflict("Usage event idempotency conflict.") from exc
        if status != "UPDATE 1":
            raise UsageLedgerStateConflict("Budget reservation revision conflict.")

    def _decode(self, row: Any) -> UsageLedgerEntry | BudgetReservation:
        try:
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            if row["kind"] == "usage":
                value: UsageLedgerEntry | BudgetReservation = usage_entry_from_record(payload)
            elif row["kind"] == "reservation":
                value = budget_reservation_from_record(payload)
            else:
                raise ValueError
            usage = value if type(value) is UsageLedgerEntry else value.usage
            expected = {
                "record_id": value.event_id
                if type(value) is UsageLedgerEntry
                else value.reservation_id,
                "kind": "usage" if type(value) is UsageLedgerEntry else "reservation",
                "state": "committed" if type(value) is UsageLedgerEntry else value.state.value,
                "revision": 1 if type(value) is UsageLedgerEntry else value.revision,
                "key_id": value.api_key_id if type(value) is UsageLedgerEntry else value.key_id,
                "created_at": value.occurred_at
                if type(value) is UsageLedgerEntry
                else value.created_at,
                "expires_at": None if type(value) is UsageLedgerEntry else value.expires_at,
                "transitioned_at": None
                if type(value) is UsageLedgerEntry
                else value.transitioned_at,
                "estimated_cost_nanos": None
                if type(value) is UsageLedgerEntry
                else value.estimated_cost_nanos,
                "daily_budget_nanos": None
                if type(value) is UsageLedgerEntry
                else value.daily_budget_nanos,
                "monthly_budget_nanos": None
                if type(value) is UsageLedgerEntry
                else value.monthly_budget_nanos,
                "event_id": None if usage is None else usage.event_id,
                "occurred_at": None if usage is None else usage.occurred_at,
                "credential_ref": None if usage is None else usage.credential_ref,
                "provider": None if usage is None else usage.provider,
                "success": None if usage is None else usage.success,
                "total_tokens": None if usage is None else usage.total_tokens,
                "cost_nanos": None if usage is None else usage.cost_nanos,
                "api_key_id": None if usage is None else usage.api_key_id,
            }
            if any(row[name] != expected[name] for name in expected):
                raise ValueError
            return value
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise UsageLedgerCorrupt("Stored usage ledger record is invalid.") from exc

    def _decode_reservation(self, row: Any) -> BudgetReservation:
        value = self._decode(row)
        if type(value) is not BudgetReservation:
            raise UsageLedgerConflict("Usage ledger record kind conflict.")
        return value

    @staticmethod
    def _request(value: BudgetReservation) -> BudgetReservationRequest:
        return BudgetReservationRequest(
            **{name: getattr(value, name) for name in BudgetReservationRequest.__dataclass_fields__}
        )

    @staticmethod
    def _payload(value: UsageLedgerEntry | BudgetReservation) -> str:
        return json.dumps(value.to_record(), sort_keys=True, separators=(",", ":"), allow_nan=False)

    @staticmethod
    def _timestamp(value: float) -> float:
        if type(value) not in {int, float} or not math.isfinite(float(value)) or value < 0:
            raise ValueError("Usage timestamp is invalid.")
        return float(value)

    @staticmethod
    def _limit(limit: int) -> None:
        if type(limit) is not int or not 1 <= limit <= MAX_RECONCILE_BATCH:
            raise ValueError("Usage batch limit is invalid.")

    @classmethod
    def _attribution(cls, credential_ref: str, provider: str, limit: int) -> None:
        cls._limit(limit)
        if (
            not credential_ref
            or len(credential_ref) > 255
            or credential_ref in {".", ".."}
            or "/" in credential_ref
            or "\\" in credential_ref
        ):
            raise ValueError("Usage credential reference is invalid.")
        if not isinstance(provider, str) or len(provider) > 64:
            raise ValueError("Usage provider is invalid.")

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("PostgreSQL usage ledger repository is not initialized.")

    @staticmethod
    def _checked(current: int, value: int) -> int:
        total = current + value
        if total > MAX_COST_NANOS:
            raise UsageLedgerCorrupt("Usage aggregate exceeds the supported range.")
        return total

    @classmethod
    def _aggregate_credentials(
        cls, entries: list[UsageLedgerEntry]
    ) -> list[CredentialUsageAggregate]:
        grouped: dict[str, list[int]] = {}
        providers: dict[str, str] = {}
        for entry in entries:
            totals = grouped.setdefault(entry.credential_ref, [0] * 17)
            providers[entry.credential_ref] = max(
                providers.get(entry.credential_ref, ""), entry.provider
            )
            values = (
                1,
                int(entry.success),
                int(not entry.success),
                entry.input_tokens,
                entry.output_tokens,
                entry.total_tokens,
                entry.cached_tokens,
                entry.reasoning_tokens,
                entry.estimated_input_tokens,
                entry.estimated_tokens_saved,
                entry.compressed_messages,
                entry.latency_ms,
                entry.retry_count,
                entry.cost_nanos,
                entry.cache_creation_tokens,
                int(entry.success and entry.usage_reported),
                int(entry.success and entry.cost_status in {"estimated", "reported", "free"}),
            )
            for index, value in enumerate(values):
                totals[index] = cls._checked(totals[index], value)
        return [
            CredentialUsageAggregate(ref, providers[ref], *values)
            for ref, values in sorted(grouped.items())
        ]

    @classmethod
    def _aggregate_providers(cls, entries: list[UsageLedgerEntry]) -> list[ProviderUsageAggregate]:
        grouped: dict[str, list[int]] = {}
        for entry in entries:
            provider = entry.provider or "unknown"
            totals = grouped.setdefault(provider, [0] * 6)
            values = (
                1,
                int(entry.success),
                int(not entry.success),
                entry.total_tokens,
                entry.latency_ms,
                entry.cost_nanos,
            )
            for index, value in enumerate(values):
                totals[index] = cls._checked(totals[index], value)
        return [
            ProviderUsageAggregate(provider, *values)
            for provider, values in sorted(grouped.items())
        ]

    @classmethod
    def _aggregate_time(
        cls, entries: list[UsageLedgerEntry], since: float, until: float, points: int
    ) -> list[UsageTimeBucket]:
        step = (until - since) / points
        grouped = [[0] * 6 for _ in range(points)]
        for entry in entries:
            index = min(int((entry.occurred_at - since) / step), points - 1)
            values = (
                1,
                int(entry.success),
                int(not entry.success),
                entry.total_tokens,
                entry.cached_tokens,
                entry.cost_nanos,
            )
            for position, value in enumerate(values):
                grouped[index][position] = cls._checked(grouped[index][position], value)
        return [
            UsageTimeBucket(since + index * step, since + (index + 1) * step, *values)
            for index, values in enumerate(grouped)
        ]
