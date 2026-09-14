"""The setup checklist must describe the server's actual password policy."""

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from core.panel.setup_security import _COMMON_OWNER_PASSWORDS, validate_owner_password
from fastapi import HTTPException


class PasswordChecklistTests(unittest.TestCase):
    def test_checklist_agrees_with_server_and_requires_confirmation(self):
        source = (ROOT / "frontend/js/features/authentication.js").read_text(encoding="utf-8")
        self.assertIn("function setupPasswordChecks(", source)
        function = (
            "function setupPasswordChecks("
            + source.split("function setupPasswordChecks(", 1)[1].split(
                "function renderSetupPasswordChecks", 1
            )[0]
        )
        candidates = [
            "",
            "short",
            "a" * 12,
            "abc" * 8,
            "abcd" * 3,
            "correct horse battery staple",
            "paſſword1234",
            "😀😃😄😁" * 3,
            "abcd" * 64,
            "abcd" * 65,
        ]
        candidates += list(_COMMON_OWNER_PASSWORDS) + [p.upper() for p in _COMMON_OWNER_PASSWORDS]
        expected = []
        for password in candidates:
            try:
                validate_owner_password(password)
                expected.append(True)
            except HTTPException:
                expected.append(False)
        script = (
            function
            + "\nconst values = "
            + json.dumps(candidates)
            + """;
        console.log(JSON.stringify(values.map(p => ({
            valid: Object.values(setupPasswordChecks(p, p)).every(Boolean),
            mismatch: setupPasswordChecks(p, p + 'different').match
        }))));"""
        )
        result = subprocess.run(
            [shutil.which("node")],
            input=script,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            timeout=15,
        )
        actual = json.loads(result.stdout)
        self.assertEqual([row["valid"] for row in actual], expected)
        self.assertFalse(any(row["mismatch"] for row in actual))


if __name__ == "__main__":
    unittest.main()
