"""Regression guard for the console's single-owner provider settings contract."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ProviderSettingOwnershipTests(unittest.TestCase):
    def test_system_page_has_no_provider_specific_configuration(self):
        settings = (ROOT / "frontend/fragments/pages/settings.html").read_text(encoding="utf-8")
        self.assertNotIn("code_assist_", settings)
        self.assertIn('data-config-key="stream_to_nonstream"', settings)
        self.assertIn('data-config-key="switch_credential_enabled"', settings)

    def test_provider_workspaces_have_single_shared_editors(self):
        source = (ROOT / "frontend/fragments/pages/providers.html").read_text(encoding="utf-8")
        self.assertIn('id="grokApiUrl"', source)
        self.assertIn('id="googleSharedSettingsForm"', source)
        self.assertIn('id="googleCompatibilitySettingsForm"', source)
        self.assertNotIn('id="anthropicApiUrlCode"', source)
        self.assertEqual(source.count('id="anthropicApiUrlPlatform"'), 1)
        self.assertNotIn('id="antigravityStreamToNonstream"', source)

    def test_pool_does_not_edit_antigravity_credit_policy(self):
        source = (ROOT / "frontend/js/ui/credential-cards.js").read_text(encoding="utf-8")
        self.assertNotIn('data-credential-command="enable_credit"', source)
        self.assertNotIn('data-credential-command="disable_credit"', source)

    def test_settings_save_actions_do_not_overlay_provider_routing_controls(self):
        styles = (ROOT / "frontend/css/providers-and-models.css").read_text(encoding="utf-8")
        rules = re.search(r"\.settings-save-bar\s*\{([^}]+)\}", styles).group(1)
        self.assertNotRegex(rules, r"position:\s*(?:sticky|fixed)")


if __name__ == "__main__":
    unittest.main()
