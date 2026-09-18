"""Isolated browser behavior contracts: no production archive or restore is used."""

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class BackupConsoleTests(unittest.TestCase):
    def test_reauthentication_explicitly_clears_existing_session(self):
        from html.parser import HTMLParser

        class ReauthenticationControl(HTMLParser):
            control = None

            def handle_starttag(self, tag, attrs):
                attributes = dict(attrs)
                if attributes.get("id") == "backupReauthenticate":
                    self.control = (tag, attributes)

        parser = ReauthenticationControl()
        parser.feed((ROOT / "frontend/fragments/pages/settings.html").read_text(encoding="utf-8"))
        tag, attributes = parser.control
        self.assertEqual(tag, "button")
        self.assertEqual(attributes.get("type"), "button")
        self.assertEqual(attributes.get("data-ui-action"), "logout")

    def test_backup_workflow_dom_contract(self):
        result = subprocess.run(
            [shutil.which("node"), str(ROOT / "backend/tests/backup_console_contract.cjs")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_upload_limit_matches_backend(self):
        import re

        frontend = (ROOT / "frontend/js/features/backups.js").read_text(encoding="utf-8")
        backend = (ROOT / "backend/core/portable_backup.py").read_text(encoding="utf-8")
        pattern = r"MAX_BACKUP_UPLOAD_BYTES = (64 \* 1024 \* 1024)"
        self.assertIsNotNone(re.search(pattern, frontend))
        self.assertIsNotNone(re.search(pattern, backend))
