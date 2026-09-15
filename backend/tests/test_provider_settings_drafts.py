"""Run real provider settings scripts against deterministic DOM/transport fixtures."""

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ProviderSettingsDraftTests(unittest.TestCase):
    def test_provider_family_settings_preserve_scope_and_loading_boundaries(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for core provider runtime contracts")
        for family in ("anthropic", "xai", "google"):
            with self.subTest(family=family):
                result = subprocess.run(
                    [
                        node,
                        str(ROOT / "backend/tests/provider_settings_drafts_contract.cjs"),
                        str(ROOT),
                        family,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
