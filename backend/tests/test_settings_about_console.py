"""Production contracts for Settings, About, and optional team access."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.configuration_schema import CONFIGURATION_FIELDS

SETTINGS = ROOT / "frontend/fragments/pages/settings.html"
SYSTEM_SCRIPT = ROOT / "frontend/js/features/system-settings.js"
ABOUT = ROOT / "frontend/fragments/pages/about.html"
ABOUT_SCRIPT = ROOT / "frontend/js/features/about.js"
IDENTITY = ROOT / "frontend/fragments/pages/identity.html"
IDENTITY_SCRIPT = ROOT / "frontend/js/features/identity.js"


class SettingsConsoleContractTests(unittest.TestCase):
    def test_every_system_control_maps_to_the_authoritative_schema(self) -> None:
        fragment = SETTINGS.read_text(encoding="utf-8")
        rendered = set(re.findall(r'data-config-key="([a-z0-9_]+)"', fragment))
        authoritative = {
            field.config_key
            for field in CONFIGURATION_FIELDS
            if field.config_key and field.surface == "system"
        }
        self.assertEqual(rendered, authoritative)

    def test_metadata_and_secret_preservation_are_explicit(self) -> None:
        source = SYSTEM_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("normalizeSettingsMetadata", source)
        self.assertIn("renderSettingsMetadata", source)
        self.assertIn("collectSystemConfigForm", source)
        self.assertIn("code_assist_client_secret_configured", source)
        self.assertNotIn("c.code_assist_client_secret || ''", source)
        self.assertNotIn(".innerHTML", source)

    def test_settings_use_a_two_column_reading_flow_without_per_field_notes(self) -> None:
        source = SYSTEM_SCRIPT.read_text(encoding="utf-8")
        styles = (ROOT / "frontend/css/providers-and-models.css").read_text(encoding="utf-8")

        self.assertIn(".config-column", styles)
        self.assertIn("display: contents", styles)
        self.assertNotIn("settings-field-meta", source)

    def test_blank_secret_is_not_sent_back_as_a_destructive_clear(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the Settings UI contract.")
        source = SYSTEM_SCRIPT.read_text(encoding="utf-8")
        harness = f"""
const vm = require('vm');
const values = {{host: '127.0.0.1', port: '4283', codeAssistClientSecret: ''}};
globalThis.document = {{getElementById: (id) => ({{
  value: values[id] ?? '', checked: id === 'retry429Enabled'
}})}};
globalThis.window = {{addEventListener: () => {{}}}};
vm.runInThisContext({json.dumps(source)} + `\n;globalThis.contract = {{collectSystemConfigForm}};`);
const config = globalThis.contract.collectSystemConfigForm();
if (Object.hasOwn(config, 'code_assist_client_secret')) throw new Error('blank secret sent');
values.codeAssistClientSecret = 'replacement-secret';
const updated = globalThis.contract.collectSystemConfigForm();
if (updated.code_assist_client_secret !== 'replacement-secret') throw new Error('secret update lost');
"""
        result = subprocess.run(
            [node, "-e", harness],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


class AboutAndIdentityConsoleContractTests(unittest.TestCase):
    def test_about_exposes_build_support_and_maintenance_entry_points(self) -> None:
        fragment = ABOUT.read_text(encoding="utf-8")
        for element_id in (
            "aboutState",
            "aboutBuildFacts",
            "aboutSupportTiers",
            "checkUpdateBtn",
            "updateGuideLink",
            "backupGuideLink",
        ):
            self.assertIn(f'id="{element_id}"', fragment)
        self.assertNotRegex(fragment, r'id="(?:updateGuideLink|backupGuideLink)"[^>]*\bhidden\b')

    def test_about_runtime_validates_and_renders_untrusted_data_as_text(self) -> None:
        source = ABOUT_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("validateAboutVersion", source)
        self.assertIn("validateCapabilitySnapshot", source)
        self.assertIn("visibleAboutTiers", source)
        self.assertIn("loadAboutPage", source)
        self.assertIn("textContent", source)
        self.assertNotIn("innerHTML", source)

    def test_about_normalizes_unknown_build_version(self) -> None:
        source = ABOUT_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("normalizeAboutVersion", source)

    def test_about_hides_support_tiers_without_capabilities(self) -> None:
        source = ABOUT_SCRIPT.read_text(encoding="utf-8")
        self.assertRegex(
            source,
            r"ABOUT_TIERS\.filter\(\(tier\)\s*=>\s*capabilities\.some",
        )
        self.assertIn("visibleAboutTiers(capabilities).map", source)

    def test_optional_team_access_keeps_local_recovery_visible(self) -> None:
        fragment = IDENTITY.read_text(encoding="utf-8")
        source = IDENTITY_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('id="identityModeNotice"', fragment)
        self.assertIn('id="identityRecoverySummary"', fragment)
        self.assertIn("renderIdentityModeNotice", source)
        self.assertIn("identity.mode_disabled", source)
        self.assertIn("identity.mode_ready", source)
        self.assertIn("policy.readiness !== 'ready'", source)


if __name__ == "__main__":
    unittest.main()
