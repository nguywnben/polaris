"""Read-only fail-closed legacy usage gate contracts for external backends."""

from __future__ import annotations

import hashlib
import sqlite3
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.storage.usage_legacy_gate import require_external_usage_migration_ready
from core.usage_ledger import UsageLedgerCorrupt, UsageMigrationRequired

from backend.tests.support import workspace_temp_directory


class ExternalUsageMigrationGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = workspace_temp_directory()
        self.root = Path(self.temp_dir.__enter__())
        self.source = self.root / "usage_stats.db"

    def tearDown(self):
        self.temp_dir.__exit__(None, None, None)

    def _create(self, *, rows: int = 0, valid: bool = True) -> None:
        connection = sqlite3.connect(self.source)
        try:
            if valid:
                connection.execute(
                    "CREATE TABLE usage_logs (id INTEGER PRIMARY KEY, filename TEXT, timestamp REAL)"
                )
                for index in range(rows):
                    connection.execute(
                        "INSERT INTO usage_logs (filename, timestamp) VALUES (?, ?)",
                        (f"credential-{index}.json", 1_700_000_000.0 + index),
                    )
            else:
                connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
            connection.commit()
        finally:
            connection.close()

    async def test_absent_or_empty_legacy_source_allows_new_external_deployment(self):
        await require_external_usage_migration_ready(str(self.source))
        self._create()
        await require_external_usage_migration_ready(str(self.source))

    async def test_existing_rows_raise_stable_migration_required_without_writing(self):
        self._create(rows=2)
        before = self.source.read_bytes()
        before_hash = hashlib.sha256(before).hexdigest()
        before_mtime = self.source.stat().st_mtime_ns

        with self.assertRaisesRegex(UsageMigrationRequired, "^usage_migration_required$"):
            await require_external_usage_migration_ready(str(self.source))

        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), before_hash)
        self.assertEqual(self.source.stat().st_mtime_ns, before_mtime)

    async def test_malformed_existing_source_fails_closed(self):
        self._create(valid=False)
        with self.assertRaises(UsageLedgerCorrupt):
            await require_external_usage_migration_ready(str(self.source))


if __name__ == "__main__":
    unittest.main()
