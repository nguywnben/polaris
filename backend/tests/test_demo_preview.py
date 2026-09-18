"""Safety boundaries of the opt-in, offline developer preview."""

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from tools.demo_preview import configure_environment, deny_outbound, validate_demo_database
from tools.seed_demo_database import MARKER


class DemoPreviewSafetyTests(unittest.TestCase):
    def test_installed_guard_rejects_a_real_socket_connection(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import socket, sys; from tools.demo_preview import deny_outbound; sys.addaudithook(deny_outbound); socket.create_connection(('127.0.0.1', 9))",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PermissionError: DEMO:", result.stderr)

    def test_environment_discards_operator_configuration(self):
        with patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "operator-secret",
                "PANEL_PASSWORD": "operator-password",
                "POSTGRESQL_URI": "operator-database",
            },
        ):
            configure_environment(ROOT / "temp/round2-demo/credentials", 4285)
            import os

            self.assertNotIn("OPENAI_API_KEY", os.environ)
            self.assertNotIn("PANEL_PASSWORD", os.environ)
            self.assertEqual(os.environ["POSTGRESQL_URI"], "")
            self.assertEqual(os.environ["PYTHON_DOTENV_DISABLED"], "1")
            self.assertEqual(os.environ["HOST"], "127.0.0.1")

    def test_denies_connect_dns_datagrams_and_subprocesses(self):
        for event, arguments in (
            ("socket.connect", (None, ("127.0.0.1", 11434))),
            ("socket.connect", (None, ("api.meta.ai", 443))),
            ("socket.getaddrinfo", ("api.meta.ai", 443)),
            ("socket.sendto", (None, "address")),
            ("subprocess.Popen", ("curl",)),
            ("os.system", ("curl",)),
        ):
            with self.subTest(event=event), self.assertRaises(PermissionError):
                deny_outbound(event, arguments)
        deny_outbound("socket.getaddrinfo", ("127.0.0.1", 4285))
        deny_outbound("socket.bind", (None, ("127.0.0.1", 4285)))

    def test_refuses_unmarked_or_non_synthetic_database(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch)
            with closing(sqlite3.connect(target / "credentials.db")) as db:
                db.execute("CREATE TABLE config (key TEXT, value TEXT)")
                db.execute("CREATE TABLE primary_credentials (credential_data TEXT)")
                db.execute("CREATE TABLE credentials (credential_data TEXT)")
                db.commit()
                with self.assertRaises(ValueError):
                    validate_demo_database(target)
                db.execute(
                    "INSERT INTO config VALUES (?, ?)",
                    ("demo_dataset_v1", json.dumps({"marker": MARKER})),
                )
                db.execute(
                    "INSERT INTO primary_credentials VALUES (?)",
                    (json.dumps({"synthetic": True, "api_key": "real-looking-key"}),),
                )
                db.commit()
                with self.assertRaises(ValueError):
                    validate_demo_database(target)

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch)
            with self.assertRaises((ValueError, sqlite3.Error)):
                validate_demo_database(target)
            self.assertEqual(list(target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
