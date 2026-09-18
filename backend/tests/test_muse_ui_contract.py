"""The Muse console uses manual OAuth, never API-key onboarding or timed polling."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class MuseUIContractTests(unittest.TestCase):
    def test_catalog_shows_only_connection_methods(self):
        source = (ROOT / "frontend/js/features/provider-onboarding.js").read_text(encoding="utf-8")
        renderer = source.split("function renderProviderCapabilityBadges()", 1)[1].split(
            "function setProviderCapabilityStatus", 1
        )[0]
        self.assertNotIn("providers.connection_test", renderer)
        self.assertNotIn("providers.model_discovery", renderer)
        catalog = (
            (ROOT / "frontend/fragments/pages/providers.html")
            .read_text(encoding="utf-8")
            .split('id="providerCatalogEmpty"', 1)[0]
        )
        self.assertNotIn("<span>JSON</span>", catalog)
        self.assertNotIn("<span>ZIP</span>", catalog)

    def test_advanced_settings_use_supported_credential_label(self):
        source = (ROOT / "frontend/js/features/muse-authentication.js").read_text(encoding="utf-8")
        self.assertIn("credential_label: credentialLabel.value.trim()", source)
        self.assertIn("'provider.muse.settings_help'", source)
        self.assertIn("'provider-device-code-inline'", source)
        self.assertNotIn("'provider-device-code-row'", source)

    def test_muse_follows_existing_oauth_link_layout(self):
        source = (ROOT / "frontend/js/features/muse-authentication.js").read_text(encoding="utf-8")
        self.assertIn("'endpoint-code-card auth-link-card'", source)
        self.assertIn("const link = extendedElement('a')", source)
        self.assertNotIn("museCancelLogin", source)
        self.assertNotIn("provider.ui.open_login", source)
        self.assertIn("museCompleteLogin", source)

    def test_muse_precedes_meta_without_extra_protocol_notice(self):
        source = (ROOT / "frontend/js/features/extended-providers.js").read_text(encoding="utf-8")
        self.assertLess(source.index("    muse_code:"), source.index("    meta:"))
        self.assertNotIn("'provider.muse.notice'", source)

    def test_manual_flow_is_bundled_without_polling_or_redirect(self):
        source = (ROOT / "frontend/js/features/muse-authentication.js").read_text(encoding="utf-8")
        for forbidden in (
            "setInterval(",
            "setTimeout(",
            "window.open(",
            "location.assign(",
            "access_token",
            "refresh_token",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("/api/providers/muse-code/oauth/", source)
        self.assertIn("createProviderCredentialSaveResult", source)
        self.assertIn("muse-authentication.js", (ROOT / "backend/core/panel/root.py").read_text())
