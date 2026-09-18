"""Provider onboarding no longer owns Antigravity credit management."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ProviderCreditSettingsFrontendTests(unittest.TestCase):
    def test_provider_workspace_has_no_credit_management_controls(self):
        html = (ROOT / "frontend/fragments/pages/providers.html").read_text(encoding="utf-8")
        self.assertNotIn('id="antigravityCreditSettings"', html)
        self.assertNotIn('id="antigravityCreditToggleBtn"', html)
        self.assertIn('id="getPrimaryAuthBtn"', html)
        self.assertIn('id="primaryUploadArea"', html)

    def test_unused_credit_ui_is_not_shipped_but_credential_status_is_preserved(self):
        root = (ROOT / "backend/core/panel/root.py").read_text(encoding="utf-8")
        self.assertNotIn('"js/features/provider-credit-settings.js"', root)
        self.assertFalse((ROOT / "frontend/js/features/provider-credit-settings.js").exists())
        cards = (ROOT / "frontend/js/ui/credential-cards.js").read_text(encoding="utf-8")
        self.assertIn("credInfo.enable_credit", cards)
        self.assertIn('class="status-badge credit-on credential-badge-hint"', cards)
        self.assertIn("const creditLabel = t('credit_enabled_title')", cards)
        self.assertIn('aria-label="${escapeAttribute(creditLabel)}"', cards)
        self.assertIn("${escapeHtml(creditLabel)}</span>", cards)

    def test_provider_website_labels_omit_trailing_slash_without_changing_targets(self):
        html = (ROOT / "frontend/fragments/pages/providers.html").read_text(encoding="utf-8")
        links = re.findall(r'class="provider-site-link" href="([^"]+)"[^>]*>([^<]+)</a>', html)
        self.assertGreaterEqual(len(links), 9)
        for target, label in links:
            with self.subTest(target=target):
                self.assertEqual(label, target.rstrip("/"))


if __name__ == "__main__":
    unittest.main()
