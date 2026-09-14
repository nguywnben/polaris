"""Exercise the shipped translator, not English-filled source dictionaries."""

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


class LocaleCompletenessTests(unittest.TestCase):
    def test_shipped_catalogs_have_translations_and_matching_variables(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the locale contract")
        result = subprocess.run(
            [node, "tools/i18n-audit.mjs", "--strict"], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_backend_message_catalogs_cover_all_locales(self):
        from string import Formatter

        from backend.core.i18n import MESSAGES, SUPPORTED_LOCALES

        def fields(text):
            return {name for _, name, _, _ in Formatter().parse(text) if name}
        for key, translations in MESSAGES.items():
            with self.subTest(key=key):
                self.assertEqual(set(translations), set(SUPPORTED_LOCALES))
                expected = fields(translations["en"])
                for locale, text in translations.items():
                    self.assertTrue(text.strip(), locale)
                    self.assertEqual(fields(text), expected, locale)

    def test_completion_files_are_shipped_in_the_console_bundle(self):
        from backend.core.panel.root import CONSOLE_SCRIPT_ASSETS

        paths = {f"js/locales/{path.name}" for path in (ROOT / "frontend/js/locales").glob("*.js")}
        self.assertEqual(len(paths), 13)
        self.assertTrue(paths.issubset(set(CONSOLE_SCRIPT_ASSETS)))
        self.assertLess(CONSOLE_SCRIPT_ASSETS.index("js/core/identity-locales.js"),
                        min(CONSOLE_SCRIPT_ASSETS.index(path) for path in paths))
        self.assertGreater(CONSOLE_SCRIPT_ASSETS.index("js/core/locale-completion.js"),
                           max(CONSOLE_SCRIPT_ASSETS.index(path) for path in paths))
