"""Shared textarea bounds apply to static fields and dynamically created dialogs."""

import re
import unittest
from pathlib import Path


class TextareaLayoutTests(unittest.TestCase):
    def test_shared_textareas_cannot_resize_outside_their_column(self):
        source = (
            Path(__file__).resolve().parents[2] / "frontend/css/forms-and-data.css"
        ).read_text(encoding="utf-8")
        declarations = "\n".join(re.findall(r"^textarea\s*\{([^}]+)\}", source, re.MULTILINE))
        self.assertIn("resize: vertical;", declarations)
        self.assertIn("max-width: 100%;", declarations)
        self.assertIn("min-width: 0;", declarations)
