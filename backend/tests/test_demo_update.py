"""Demo upgrades preserve login/configuration and roll back corpus replacement."""

import asyncio
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from tools.audit_demo_database import audit_database
from tools.seed_demo_database import seed_database
from tools.update_demo_database import update_database


class DemoUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory()
        root = Path(cls.scratch.name)
        cls.source = root / "source/credentials"
        cls.target = root / "target/credentials"
        asyncio.run(seed_database(cls.source, full=True))
        asyncio.run(seed_database(cls.target, full=True))
        with closing(sqlite3.connect(cls.target / "credentials.db")) as db:
            db.execute(
                "INSERT INTO config (key,value) VALUES (?,?)",
                ("test_operator_setting", json.dumps({"keep": "unchanged"})),
            )
            db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_failed_replacement_rolls_back_and_keeps_backup(self):
        database = self.target / "credentials.db"
        with closing(sqlite3.connect(database)) as db:
            before = list(db.iterdump())
        with patch("tools.update_demo_database.CONFIGS", ("missing_fixture_configuration",)):
            with self.assertRaisesRegex(ValueError, "incomplete"):
                update_database(database, self.source / "credentials.db")
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(list(db.iterdump()), before)
        self.assertTrue(list(self.target.glob("credentials.before-fidelity-*.db")))

    def test_upgrade_keeps_non_corpus_settings_and_produces_valid_database(self):
        result = update_database(self.target / "credentials.db", self.source / "credentials.db")
        self.assertTrue(Path(result["backup"]).is_file())
        self.assertTrue(result["login_preserved"])
        with closing(sqlite3.connect(self.target / "credentials.db")) as db:
            value = db.execute(
                "SELECT value FROM config WHERE key='test_operator_setting'"
            ).fetchone()[0]
        self.assertEqual(json.loads(value), {"keep": "unchanged"})
        self.assertEqual(audit_database(self.target)["credentials"], 89)

    def test_unmarked_target_is_refused_without_writes(self):
        with tempfile.TemporaryDirectory() as scratch:
            database = Path(scratch) / "credentials.db"
            with closing(sqlite3.connect(database)) as db:
                db.execute("CREATE TABLE config (key TEXT, value TEXT)")
            before = database.read_bytes()
            with self.assertRaises(ValueError):
                update_database(database, self.source / "credentials.db")
            self.assertEqual(database.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
