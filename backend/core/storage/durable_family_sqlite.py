"""Concrete durable-family migration adapter over Polaris SQLite tables."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import aiosqlite
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
from core.storage.sqlite_runtime import open_sqlite

_CREDENTIAL_COLUMNS = (
    "filename",
    "credential_data",
    "disabled",
    "error_codes",
    "error_messages",
    "last_success",
    "user_email",
    "model_cooldowns",
    "preview",
    "tier",
    "rotation_order",
    "call_count",
    "created_at",
    "updated_at",
)
_PRIMARY_CREDENTIAL_COLUMNS = tuple(
    column for column in _CREDENTIAL_COLUMNS if column != "preview"
) + ("enable_credit",)
_IDENTITY_COLUMNS = (
    "schema_version",
    "identity_id",
    "principal_type",
    "issuer",
    "subject",
    "enabled",
    "revision",
    "authorization_epoch",
    "created_at",
    "updated_at",
)
_ROLE_COLUMNS = (
    "schema_version",
    "binding_id",
    "identity_id",
    "role",
    "source",
    "revision",
    "created_at",
    "updated_at",
)
_AUDIT_COLUMNS = (
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
_TRACE_COLUMNS = (
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
_USAGE_COLUMNS = (
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

SQLITE_DURABLE_FAMILY_ADAPTERS: Final = MappingProxyType(
    {
        DurableFamily.CONFIGURATION: DurableFamilyAdapterSpec(
            "config",
            ("key", "value", "updated_at"),
            ("key",),
            "cfg",
            "key <> 'virtual_keys' AND key <> '_internal_durable_migration_barrier_v2'",
        ),
        DurableFamily.PROVIDER_CREDENTIAL: DurableFamilyAdapterSpec(
            "credentials", _CREDENTIAL_COLUMNS, ("filename",), "crd"
        ),
        DurableFamily.PRIMARY_CREDENTIAL: DurableFamilyAdapterSpec(
            "primary_credentials", _PRIMARY_CREDENTIAL_COLUMNS, ("filename",), "pri"
        ),
        DurableFamily.VIRTUAL_KEY: DurableFamilyAdapterSpec(
            "config", ("key", "value", "updated_at"), ("key",), "vky", "key = 'virtual_keys'"
        ),
        DurableFamily.IDENTITY: DurableFamilyAdapterSpec(
            "management_identities",
            _IDENTITY_COLUMNS,
            ("identity_id",),
            "idn",
            boolean_columns=("enabled",),
            timestamp_columns=("created_at", "updated_at"),
        ),
        DurableFamily.ROLE_BINDING: DurableFamilyAdapterSpec(
            "management_role_bindings",
            _ROLE_COLUMNS,
            ("binding_id",),
            "rol",
            timestamp_columns=("created_at", "updated_at"),
        ),
        DurableFamily.OIDC_POLICY_REVISION: DurableFamilyAdapterSpec(
            "oidc_policy_revision",
            ("singleton_id", "schema_version", "revision", "authorization_epoch", "updated_at"),
            ("singleton_id",),
            "oid",
            timestamp_columns=("updated_at",),
        ),
        DurableFamily.IDENTITY_SCHEMA_EVIDENCE: DurableFamilyAdapterSpec(
            "identity_migrations",
            ("migration_id", "schema_version", "applied_at"),
            ("migration_id",),
            "ism",
            timestamp_columns=("applied_at",),
        ),
        DurableFamily.AUDIT_EVENT: DurableFamilyAdapterSpec(
            "audit_events",
            _AUDIT_COLUMNS,
            ("event_id",),
            "aud",
            json_columns=("change_codes",),
            timestamp_columns=("occurred_at",),
        ),
        DurableFamily.REQUEST_TRACE: DurableFamilyAdapterSpec(
            "request_traces",
            _TRACE_COLUMNS,
            ("trace_id",),
            "trc",
            json_columns=("decisions",),
            boolean_columns=("decisions_truncated",),
            timestamp_columns=("started_at", "completed_at"),
        ),
        DurableFamily.USAGE_LEDGER: DurableFamilyAdapterSpec(
            "durable_usage_ledger",
            _USAGE_COLUMNS,
            ("record_id",),
            "usg",
            "kind = 'usage'",
            json_columns=("payload",),
            boolean_columns=("success",),
        ),
        DurableFamily.HARD_BUDGET_RESERVATION: DurableFamilyAdapterSpec(
            "durable_usage_ledger",
            _USAGE_COLUMNS,
            ("record_id",),
            "res",
            "kind = 'reservation'",
            json_columns=("payload",),
            boolean_columns=("success",),
        ),
        DurableFamily.MIGRATION_CHECKPOINT: DurableFamilyAdapterSpec(
            "durable_migration_checkpoints",
            ("plan_id", "revision", "record_json"),
            ("plan_id",),
            "mig",
        ),
    }
)


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
        values[column] = value
    return values


class SQLiteDurableFamilyAdapter:
    """Bounded reader/writer using only the application's existing durable tables."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        instance_id: str,
        revision: int = 1,
    ) -> None:
        self._database_path = str(database_path)
        self.descriptor = MigrationEndpointDescriptor(DurableBackend.SQLITE, instance_id, revision)

    async def read_page(
        self, *, family: DurableFamily, offset: int, limit: int
    ) -> MigrationRecordPage:
        spec = self._spec(family)
        self._page_bounds(offset, limit)
        where = f" WHERE {spec.predicate}" if spec.predicate else ""
        order = ", ".join(spec.key_columns)
        query = (
            f"SELECT {', '.join(spec.columns)} FROM {spec.table}{where} "
            f"ORDER BY {order} LIMIT ? OFFSET ?"
        )
        try:
            async with open_sqlite(self._database_path) as db:
                db.row_factory = aiosqlite.Row
                rows = await (await db.execute(query, (limit + 1, offset))).fetchall()
        except Exception as exc:
            raise MigrationError("SQLite durable family read failed.") from exc
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
        placeholders = ", ".join("?" for _ in spec.columns)
        key_where = " AND ".join(f"{column} = ?" for column in spec.key_columns)
        keys = tuple(payload[column] for column in spec.key_columns)
        try:
            async with open_sqlite(self._database_path) as db:
                db.row_factory = aiosqlite.Row
                await db.execute("BEGIN IMMEDIATE")
                await db.execute(
                    f"INSERT OR IGNORE INTO {spec.table} ({', '.join(spec.columns)}) "
                    f"VALUES ({placeholders})",
                    values,
                )
                row = await (
                    await db.execute(
                        f"SELECT {', '.join(spec.columns)} FROM {spec.table} WHERE {key_where}",
                        keys,
                    )
                ).fetchone()
                if row is None or self._record(record.family, spec, row) != record:
                    await db.rollback()
                    raise MigrationDuplicateConflict("Conflicting durable record.")
                await db.commit()
        except MigrationDuplicateConflict:
            raise
        except Exception as exc:
            raise MigrationError("SQLite durable family write failed.") from exc

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
            elif column in spec.boolean_columns and value is not None:
                value = int(bool(value))
            values.append(value)
        return tuple(values)

    @staticmethod
    def _spec(family: DurableFamily) -> DurableFamilyAdapterSpec:
        if type(family) is not DurableFamily:
            raise ValueError("Migration durable family is invalid.")
        return SQLITE_DURABLE_FAMILY_ADAPTERS[family]

    @staticmethod
    def _page_bounds(offset: int, limit: int) -> None:
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= MAX_BATCH_SIZE
        ):
            raise ValueError("Migration page bounds are invalid.")
