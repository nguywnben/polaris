"""The credentials page replaces the retired pool URL without an alias."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


class CredentialsPageRouteTests(unittest.TestCase):
    def test_server_only_registers_credentials_page(self):
        from core.panel.root import router, serve_control_panel

        paths = {
            route.path
            for route in router.routes
            if getattr(route, "endpoint", None) is serve_control_panel
        }
        self.assertIn("/credentials", paths)
        self.assertNotIn("/pool", paths)

    def test_frontend_uses_credentials_page_and_navigation(self):
        from core.panel.root import _assemble_console_html

        html = _assemble_console_html()
        navigation = (ROOT / "frontend/js/core/navigation.js").read_text(encoding="utf-8")
        self.assertIn('id="credentialsTab"', html)
        self.assertIn('data-tab="credentials"', html)
        self.assertNotIn('data-tab="pool"', html)
        self.assertNotIn('id="poolTab"', html)
        self.assertIn("'/credentials': 'credentials'", navigation)
        self.assertNotIn("'/pool'", navigation)
