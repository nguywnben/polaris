"""Atomic SQLite application-mutation fence used by durable migration evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

import aiosqlite
from core.durable_migration import DurableFamily
from core.durable_migration_runner import MigrationError
from core.storage.durable_family_sqlite import SQLITE_DURABLE_FAMILY_ADAPTERS
from core.storage.sqlite_runtime import open_sqlite

_PLAN_ID = re.compile(r"dmg_[0-9a-f]{32}")
_BARRIER_ID = re.compile(r"bar_[0-9a-f]{32}")
_INSTANCE_ID = re.compile(r"ins_[0-9a-f]{32}")
_BARRIER_KEY: Final = "_internal_durable_migration_barrier_v2"


class SourceMutationBarrierLost(MigrationError):
    """The declared SQLite source fence is absent, partial, or belongs to another plan."""


class SQLiteSourceMutationBarrier:
    """Fence every real application table with transactionally-installed SQLite triggers."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = str(database_path)

    async def activate(self, *, plan_id: str, barrier_id: str, source_instance_id: str) -> None:
        record = self._record(plan_id, barrier_id, source_instance_id)
        async with open_sqlite(self._database_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                row = await (
                    await db.execute("SELECT value FROM config WHERE key = ?", (_BARRIER_KEY,))
                ).fetchone()
                if row is not None and self._decode(row[0]) != record:
                    raise SourceMutationBarrierLost("SQLite source has another migration barrier.")
                await db.execute(
                    "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                    (_BARRIER_KEY, json.dumps(record, separators=(",", ":"), sort_keys=True)),
                )
                await self._install_triggers(db)
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def assert_active(
        self, *, plan_id: str, barrier_id: str, source_instance_id: str
    ) -> None:
        expected = self._record(plan_id, barrier_id, source_instance_id)
        try:
            async with open_sqlite(self._database_path) as db:
                row = await (
                    await db.execute("SELECT value FROM config WHERE key = ?", (_BARRIER_KEY,))
                ).fetchone()
                trigger_rows = await (
                    await db.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                        "AND name LIKE 'polaris_migration_fence_v2_%'"
                    )
                ).fetchall()
        except Exception as exc:
            raise SourceMutationBarrierLost(
                "SQLite source mutation barrier is unavailable."
            ) from exc
        if row is None or self._decode(row[0]) != expected:
            raise SourceMutationBarrierLost("SQLite source mutation barrier is not active.")
        if {item[0] for item in trigger_rows} != self._trigger_names():
            raise SourceMutationBarrierLost("SQLite source mutation barrier is incomplete.")

    async def deactivate(self, *, plan_id: str, barrier_id: str, source_instance_id: str) -> None:
        await self.assert_active(
            plan_id=plan_id,
            barrier_id=barrier_id,
            source_instance_id=source_instance_id,
        )
        async with open_sqlite(self._database_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                for name in self._trigger_names():
                    await db.execute(f"DROP TRIGGER {name}")
                await db.execute("DELETE FROM config WHERE key = ?", (_BARRIER_KEY,))
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    @classmethod
    async def _install_triggers(cls, db: aiosqlite.Connection) -> None:
        for table in cls._tables():
            for operation in ("INSERT", "UPDATE", "DELETE"):
                name = cls._trigger_name(table, operation)
                when = ""
                if table == "config":
                    subject = "OLD" if operation == "DELETE" else "NEW"
                    when = f" WHEN {subject}.key <> '{_BARRIER_KEY}'"
                await db.execute(
                    f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE {operation} ON {table}"
                    f"{when} BEGIN SELECT RAISE(ABORT, 'durable migration source fenced'); END"
                )

    @classmethod
    def _tables(cls) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    spec.table
                    for family, spec in SQLITE_DURABLE_FAMILY_ADAPTERS.items()
                    if family is not DurableFamily.MIGRATION_CHECKPOINT
                }
            )
        )

    @classmethod
    def _trigger_names(cls) -> set[str]:
        return {
            cls._trigger_name(table, operation)
            for table in cls._tables()
            for operation in ("INSERT", "UPDATE", "DELETE")
        }

    @staticmethod
    def _trigger_name(table: str, operation: str) -> str:
        return f"polaris_migration_fence_v2_{table}_{operation.lower()}"

    @staticmethod
    def _record(plan_id: str, barrier_id: str, source_instance_id: str) -> dict[str, object]:
        if (
            not isinstance(plan_id, str)
            or not _PLAN_ID.fullmatch(plan_id)
            or not isinstance(barrier_id, str)
            or not _BARRIER_ID.fullmatch(barrier_id)
            or not isinstance(source_instance_id, str)
            or not _INSTANCE_ID.fullmatch(source_instance_id)
        ):
            raise ValueError("SQLite source mutation barrier identity is invalid.")
        return {
            "schema_version": 2,
            "plan_id": plan_id,
            "barrier_id": barrier_id,
            "source_instance_id": source_instance_id,
        }

    @staticmethod
    def _decode(value: object) -> dict[str, object] | None:
        try:
            decoded = json.loads(value) if isinstance(value, str) else None
        except json.JSONDecodeError:
            return None
        if not isinstance(decoded, dict) or set(decoded) != {
            "schema_version",
            "plan_id",
            "barrier_id",
            "source_instance_id",
        }:
            return None
        return decoded
