"""Static accessibility and secret-handling contracts for the setup console."""

from __future__ import annotations

import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel.root import _assemble_console_html


class ElementParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements: dict[str, tuple[str, dict[str, str | None]]] = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.elements[element_id] = (tag, attributes)


class SetupConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _assemble_console_html()
        parser = ElementParser()
        parser.feed(cls.html)
        cls.elements = parser.elements
        cls.client = (ROOT / "frontend" / "js" / "features" / "authentication.js").read_text(
            encoding="utf-8"
        )
        cls.bootstrap = (ROOT / "frontend" / "js" / "features" / "version.js").read_text(
            encoding="utf-8"
        )
        cls.styles = (ROOT / "frontend" / "css" / "shell.css").read_text(encoding="utf-8")
        cls.locales = (ROOT / "frontend" / "js" / "core" / "locales.js").read_text(encoding="utf-8")

    def test_preflight_summary_is_announced_and_checks_are_semantic(self):
        tag, attributes = self.elements["setupPreflightSummary"]
        self.assertEqual(tag, "section")
        self.assertEqual(attributes.get("role"), "status")
        self.assertEqual(attributes.get("aria-live"), "polite")
        self.assertEqual(self.elements["setupPreflightChecks"][0], "ul")
        for check_id in ("data", "address", "transport", "setupToken", "owner"):
            self.assertIn(f"setupCheck{check_id[0].upper()}{check_id[1:]}", self.elements)

    def test_owner_fields_are_disabled_until_preflight_and_have_bounded_inputs(self):
        fieldset_tag, fieldset = self.elements["setupOwnerFields"]
        self.assertEqual(fieldset_tag, "fieldset")
        self.assertIn("disabled", fieldset)
        for control_id in ("setupPassword", "setupPasswordConfirm"):
            tag, attributes = self.elements[control_id]
            self.assertEqual(tag, "input")
            self.assertEqual(attributes.get("minlength"), "12")
            self.assertEqual(attributes.get("maxlength"), "256")
            self.assertIn("required", attributes)
        self.assertEqual(self.elements["setupPreflightButton"][1].get("type"), "button")

    def test_setup_client_uses_post_bodies_text_content_and_clears_secrets(self):
        self.assertIn("fetch('./api/auth/setup/preflight'", self.client)
        self.assertIn("body: JSON.stringify", self.client)
        self.assertIn("element.textContent =", self.client)
        self.assertIn("passwordInput.value = ''", self.client)
        self.assertIn("confirmInput.value = ''", self.client)
        self.assertIn("setupTokenInput.value = ''", self.client)
        self.assertNotIn("application logs", self.locales)

    def test_setup_layout_has_a_bounded_responsive_card(self):
        self.assertIn(".setup-card", self.styles)
        self.assertIn("width: min(100%, 560px)", self.styles)
        self.assertIn("overflow-wrap: anywhere", self.styles)

    def test_setup_bootstrap_does_not_wait_for_external_assets(self):
        self.assertIn("async function initializeConsole()", self.bootstrap)
        self.assertIn(
            "document.addEventListener('DOMContentLoaded', initializeConsole",
            self.bootstrap,
        )
        self.assertIn("document.readyState === 'loading'", self.bootstrap)
        self.assertIn("void initializeConsole()", self.bootstrap)
        self.assertNotIn("window.onload", self.bootstrap)


if __name__ == "__main__":
    unittest.main()
