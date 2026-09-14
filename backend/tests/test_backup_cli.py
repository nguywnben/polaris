"""Offline encrypted backup entry-point contracts used by Compose rollback."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.storage.sqlite_manager import SQLiteManager

PASSPHRASE = "offline recovery passphrase"


def _frame(passphrase: str, archive: bytes = b"") -> bytes:
    encoded = passphrase.encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded + archive


class BackupCliTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        test_root = Path(os.environ["CREDENTIALS_DIR"]).parent
        self.directory = test_root / f"backup-cli-{uuid.uuid4().hex}"
        self.directory.mkdir(parents=True)
        with patch.dict(os.environ, {"CREDENTIALS_DIR": str(self.directory)}):
            manager = SQLiteManager()
            await manager.initialize()
            await manager.create_audit_repository(cursor_signing_key=b"a" * 32)
            await manager.create_identity_repository()
            await manager.create_request_trace_repository(cursor_signing_key=b"b" * 32)
            await manager.create_usage_ledger_repository()
            await manager.set_config("routing_strategy", "before-update")
            await manager.close()

    async def asyncTearDown(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)

    def _run(self, operation: str, content: bytes) -> subprocess.CompletedProcess[bytes]:
        environment = dict(os.environ)
        environment["CREDENTIALS_DIR"] = str(self.directory)
        return subprocess.run(
            [sys.executable, str(BACKEND / "backup_cli.py"), operation],
            cwd=ROOT,
            env=environment,
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    async def test_create_and_offline_restore_round_trip_the_sqlite_state(self) -> None:
        created = self._run("create", _frame(PASSPHRASE))
        self.assertEqual(created.returncode, 0, created.stderr.decode(errors="replace"))
        self.assertGreater(len(created.stdout), 100)

        database = self.directory / "credentials.db"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute(
                "UPDATE config SET value = ? WHERE key = ?",
                (json.dumps("after-update"), "routing_strategy"),
            )
            connection.commit()

        restored = self._run("restore", _frame(PASSPHRASE, created.stdout))
        self.assertEqual(restored.returncode, 0, restored.stderr.decode(errors="replace"))
        with closing(sqlite3.connect(database)) as connection:
            value = connection.execute(
                "SELECT value FROM config WHERE key = 'routing_strategy'"
            ).fetchone()[0]
        self.assertEqual(json.loads(value), "before-update")

    async def test_malformed_frame_fails_without_echoing_input(self) -> None:
        secret = "must-not-appear"
        result = self._run("restore", (100).to_bytes(4, "big") + secret.encode())

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(secret, result.stderr.decode("utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()
