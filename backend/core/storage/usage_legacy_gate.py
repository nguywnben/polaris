"""Read-only legacy usage gate for external selected storage backends."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from core.usage_ledger import UsageLedgerCorrupt, UsageMigrationRequired

_REQUIRED_COLUMNS = frozenset({"id", "filename", "timestamp"})


async def require_external_usage_migration_ready(source_path: str) -> None:
    """Allow an external ledger only when the host has no legacy usage rows."""

    if not isinstance(source_path, str) or not source_path.strip():
        raise ValueError("Legacy usage source path is invalid.")
    await asyncio.to_thread(_inspect_legacy_source, Path(source_path))


def _inspect_legacy_source(source: Path) -> None:
    source = source.resolve()
    if not source.exists():
        return
    if not source.is_file():
        raise UsageLedgerCorrupt("Legacy usage source is invalid.")
    try:
        connection = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'usage_logs'"
            ).fetchone()
            if table is None:
                raise UsageLedgerCorrupt("Legacy usage source schema is missing.")
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(usage_logs)")}
            if not _REQUIRED_COLUMNS.issubset(columns):
                raise UsageLedgerCorrupt("Legacy usage source schema is invalid.")
            row = connection.execute("SELECT COUNT(*) FROM usage_logs").fetchone()
            if row is None or type(row[0]) is not int or row[0] < 0:
                raise UsageLedgerCorrupt("Legacy usage source count is invalid.")
            if row[0] > 0:
                raise UsageMigrationRequired("usage_migration_required")
        finally:
            connection.close()
    except (UsageLedgerCorrupt, UsageMigrationRequired):
        raise
    except sqlite3.Error as exc:
        raise UsageLedgerCorrupt("Legacy usage source cannot be verified.") from exc
