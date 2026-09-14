"""Concrete durable-family migration adapter over Polaris PostgreSQL tables."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Final

import asyncpg
from core.durable_migration import (
    DurableBackend,
    DurableFamily,
    DurableFamilyAdapterSpec,
    DurableRecord,
    MigrationEndpointDescriptor,
    durable_logical_id,
    durable_ordering_key,
    durable_record_payload,
)
from core.durable_migration_runner import (
    MAX_BATCH_SIZE,
    MigrationDuplicateConflict,
    MigrationError,
    MigrationRecordPage,
)
from core.storage.durable_family_sqlite import SQLITE_DURABLE_FAMILY_ADAPTERS

# Both backends intentionally map the same manifest to equivalent application tables. Keeping a
# distinct immutable registry makes backend coverage explicit while sharing the closed schema.
POSTGRESQL_DURABLE_FAMILY_ADAPTERS: Final = MappingProxyType(dict(SQLITE_DURABLE_FAMILY_ADAPTERS))


def _normalized_row(spec: DurableFamilyAdapterSpec, row: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for column in spec.columns:
        value = row[column]
        if column in spec.json_columns and isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise MigrationError("Durable application row contains invalid JSON.") from exc
        if column in spec.boolean_columns and value is not None:
            value = bool(value)
        if column in spec.timestamp_columns and isinstance(value, datetime):
            value = value.astimezone(timezone.utc).isoformat()
        values[column] = value
    return values


class PostgreSQLDurableFamilyAdapter:
    """Bounded reader/writer using only the application's existing durable tables."""

    def __init__(self, pool: asyncpg.Pool, *, instance_id: str, revision: int = 1) -> None:
        if pool is None:
            raise ValueError("PostgreSQL migration pool is required.")
        self._pool = pool
        self.descriptor = MigrationEndpointDescriptor(
            DurableBackend.POSTGRESQL, instance_id, revision
        )

    async def read_page(
        self, *, family: DurableFamily, offset: int, limit: int
    ) -> MigrationRecordPage:
        spec = self._spec(family)
        self._page_bounds(offset, limit)
        where = f" WHERE {spec.predicate}" if spec.predicate else ""
        order = ", ".join(spec.key_columns)
        query = (
            f"SELECT {', '.join(spec.columns)} FROM {spec.table}{where} "
            f"ORDER BY {order} LIMIT $1 OFFSET $2"
        )
        try:
            async with self._pool.acquire() as connection:
                rows = await connection.fetch(query, limit + 1, offset)
        except Exception as exc:
            raise MigrationError("PostgreSQL durable family read failed.") from exc
        records = tuple(self._record(family, spec, row) for row in rows[:limit])
        return MigrationRecordPage(records, len(rows) <= limit)

    async def put_if_absent_or_equal(self, record: DurableRecord) -> None:
        if type(record) is not DurableRecord:
            raise ValueError("Migration durable record is invalid.")
        spec = self._spec(record.family)
        payload = durable_record_payload(record)
        if set(payload) != set(spec.columns):
            raise MigrationError("Migration durable record payload is incompatible.")
        if durable_logical_id(record.family, spec, payload) != record.logical_id:
            raise MigrationError("Migration durable record identity is inconsistent.")
        values = self._database_values(spec, payload)
        placeholders = ", ".join(
            f"${index}::jsonb" if column in spec.json_columns else f"${index}"
            for index, column in enumerate(spec.columns, start=1)
        )
        key_where = " AND ".join(
            f"{column} = ${index}" for index, column in enumerate(spec.key_columns, start=1)
        )
        keys = tuple(payload[column] for column in spec.key_columns)
        try:
            async with self._pool.acquire() as connection:
                async with connection.transaction():
                    await connection.execute(
                        f"INSERT INTO {spec.table} ({', '.join(spec.columns)}) "
                        f"VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                        *values,
                    )
                    row = await connection.fetchrow(
                        f"SELECT {', '.join(spec.columns)} FROM {spec.table} WHERE {key_where}",
                        *keys,
                    )
                    if row is None or self._record(record.family, spec, row) != record:
                        raise MigrationDuplicateConflict("Conflicting durable record.")
        except MigrationDuplicateConflict:
            raise
        except Exception as exc:
            raise MigrationError("PostgreSQL durable family write failed.") from exc

    @staticmethod
    def _record(
        family: DurableFamily, spec: DurableFamilyAdapterSpec, row: Mapping[str, Any]
    ) -> DurableRecord:
        payload = _normalized_row(spec, row)
        return DurableRecord(
            family=family,
            logical_id=durable_logical_id(family, spec, payload),
            schema_version=1,
            payload=payload,
            ordering_key=durable_ordering_key(spec, payload),
        )

    @staticmethod
    def _database_values(
        spec: DurableFamilyAdapterSpec, payload: Mapping[str, Any]
    ) -> tuple[Any, ...]:
        values: list[Any] = []
        for column in spec.columns:
            value = payload[column]
            if column in spec.json_columns:
                value = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            elif column in spec.timestamp_columns and isinstance(value, str):
                value = datetime.fromisoformat(value)
            values.append(value)
        return tuple(values)

    @staticmethod
    def _spec(family: DurableFamily) -> DurableFamilyAdapterSpec:
        if type(family) is not DurableFamily:
            raise ValueError("Migration durable family is invalid.")
        return POSTGRESQL_DURABLE_FAMILY_ADAPTERS[family]

    @staticmethod
    def _page_bounds(offset: int, limit: int) -> None:
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= MAX_BATCH_SIZE
        ):
            raise ValueError("Migration page bounds are invalid.")
