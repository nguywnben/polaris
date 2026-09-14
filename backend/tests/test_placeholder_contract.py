"""Placeholders supplement persistent labels on static and dynamic text fields."""

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
PLACEHOLDER_TYPES = {"text", "password", "search", "email", "url", "tel", "number"}


class PlaceholderParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.missing = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag != "textarea" and (tag != "input" or attributes.get("type", "text") not in PLACEHOLDER_TYPES):
            return
        if not (attributes.get("placeholder") or "").strip():
            self.missing.append(attributes.get("id") or attributes.get("name") or str(self.getpos()))


class PlaceholderContractTests(unittest.TestCase):
    def test_static_fields_have_nonblank_placeholders(self):
        missing = []
        for path in (FRONTEND / "fragments").rglob("*.html"):
            parser = PlaceholderParser()
            parser.feed(path.read_text(encoding="utf-8"))
            missing.extend(f"{path.name}: {field}" for field in parser.missing)
        self.assertEqual(missing, [])

    def test_dynamic_text_fields_have_placeholders(self):
        missing = []
        for folder in ("features", "ui"):
            for path in (FRONTEND / "js" / folder).glob("*.js"):
                for match in re.finditer(r"<(input|textarea)\b[^>]*>", path.read_text(encoding="utf-8")):
                    parser = PlaceholderParser()
                    parser.feed(match[0])
                    missing.extend(f"{path.name}: {field}" for field in parser.missing)
        self.assertEqual(missing, [])

    def test_placeholders_use_normal_font_weight(self):
        source = (FRONTEND / "css" / "forms-and-data.css").read_text(encoding="utf-8")
        self.assertRegex(source, r"input::placeholder,\s*textarea::placeholder\s*\{[^}]*font-weight:\s*400;")
