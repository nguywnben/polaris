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
    def test_settings_reset_uses_system_scope(self) -> None:
        source = SYSTEM_SCRIPT.read_text(encoding="utf-8")
        harness = f"""
const vm = require('vm');
const calls = [];
globalThis.showConfirmModal = async () => true;
globalThis.t = key => key;
globalThis.getAuthHeaders = () => ({{}});
globalThis.showStatus = () => {{}};
globalThis.setTimeout = () => {{}};
globalThis.fetch = async (url, options) => {{
    calls.push({{url, method: options.method}});
    return {{ok: true, json: async () => ({{}})}};
}};
vm.runInThisContext({json.dumps(source)});
(async () => {{
    await resetConfig();
    if (calls.length !== 1 || calls[0].url !== './api/config/reset?scope=system'
        || calls[0].method !== 'POST') throw Error('Settings reset must preserve Models routing');
}})().catch(error => {{console.error(error); process.exitCode = 1;}});
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", harness],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_routing_is_read_only_in_settings_and_not_submitted(self) -> None:
        fragment = SETTINGS.read_text(encoding="utf-8")
        self.assertNotRegex(fragment, r'<select[^>]+id="(?:routingStrategy|preferredProvider)"')
        self.assertIn('href="/models"', fragment)
        source = SYSTEM_SCRIPT.read_text(encoding="utf-8")
        harness = f"""
const vm = require('vm');
globalThis.document = {{getElementById: () => ({{value: '', checked: false}})}};
vm.runInThisContext({json.dumps(source)});
const payload = collectSystemConfigForm();
if ('routing_strategy' in payload || 'preferred_provider' in payload) throw Error('Settings overwrites routing');
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", harness], capture_output=True, text=True, timeout=15
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_settings_are_not_submitted(self) -> None:
        source = SYSTEM_SCRIPT.read_text(encoding="utf-8")
        harness = f"""
const vm = require('vm');
globalThis.document = {{querySelectorAll: () => [{{disabled: false, reportValidity: () => false}}]}};
globalThis.fetch = () => {{throw new Error('Invalid form reached the network');}};
globalThis.showStatus = () => {{throw new Error('Save must stop before collection/network');}};
globalThis.t = value => value;
vm.runInThisContext({json.dumps(source)});
saveConfig();
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", harness], capture_output=True, text=True, timeout=15
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_save_validates_form_controls_and_ignores_read_only_routing_summaries(self) -> None:
        source = SYSTEM_SCRIPT.read_text(encoding="utf-8")
        harness = f"""
const vm = require('vm');
const calls = [], validated = [];
const control = (tagName, id, value, disabled = false) => ({{tagName, id, value, disabled,
    reportValidity() {{validated.push(id); return true;}}}});
const fields = [control('INPUT', 'host', '127.0.0.1'), control('SELECT', 'runtimeLogLevel', 'info'),
    control('TEXTAREA', 'autoBanErrorCodes', '401'), control('INPUT', 'port', '4283', true),
    {{tagName: 'P', id: 'routingStrategy', textContent: 'Balanced'}},
    {{tagName: 'P', id: 'preferredProvider', textContent: 'Automatic'}}];
globalThis.document = {{
    getElementById: id => fields.find(field => field.id === id) || {{value: '', checked: false}},
    querySelectorAll: selector => fields.filter(field => selector.split(',').some(part => {{
        const tag = part.trim().split(/\\s+/).at(-1).split('[')[0];
        return !tag || tag.toUpperCase() === field.tagName;
    }})),
}};
globalThis.fetch = async (url, options) => {{calls.push({{url, payload: JSON.parse(options.body)}});
    return {{ok: true, json: async () => ({{}})}};}};
globalThis.getAuthHeaders = () => ({{}});
globalThis.showStatus = () => {{}};
globalThis.setTimeout = () => {{}};
globalThis.t = key => key;
vm.runInThisContext({json.dumps(source)});
(async () => {{
    await saveConfig();
    if (calls.length !== 1 || calls[0].url !== './api/config/save') throw Error('Valid settings were not saved');
    if (validated.join() !== 'host,runtimeLogLevel,autoBanErrorCodes') throw Error('Form validation was skipped');
    if ('routing_strategy' in calls[0].payload.config || 'preferred_provider' in calls[0].payload.config)
        throw Error('Read-only routing was submitted');
}})().catch(error => {{console.error(error); process.exitCode = 1;}});
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", harness],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

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

    def test_settings_use_independent_columns_without_per_field_notes(self) -> None:
        fragment = SETTINGS.read_text(encoding="utf-8")
        source = SYSTEM_SCRIPT.read_text(encoding="utf-8")
        styles = (ROOT / "frontend/css/providers-and-models.css").read_text(encoding="utf-8")

        self.assertEqual(fragment.count('class="config-column"'), 2)
        self.assertRegex(styles, r"\.config-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2")
        self.assertRegex(styles, r"\.config-column\s*\{[^}]*align-content:\s*start")
        self.assertNotIn("column-count", styles)
        self.assertNotIn("settings-field-meta", source)

    def test_page_header_allows_copy_to_shrink_before_actions_wrap(self) -> None:
        styles = (ROOT / "frontend/css/shell.css").read_text(encoding="utf-8")

        self.assertRegex(styles, r"\.page-header\s*>\s*:first-child\s*\{[^}]*min-width:\s*0")
        self.assertRegex(
            styles, r"\.page-header\s*>\s*\.page-actions\s*\{[^}]*flex:\s*0\s+0\s+auto"
        )

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
vm.runInThisContext('const AppState = {{envLockedFields: new Set(["host", "code_assist_client_secret"])}};');
const locked = globalThis.contract.collectSystemConfigForm();
if ('host' in locked || 'code_assist_client_secret' in locked) throw new Error('environment-managed fields submitted');
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
    def test_support_counts_are_labelled_and_empty_snapshot_is_explicit(self) -> None:
        source = ABOUT_SCRIPT.read_text(encoding="utf-8")
        harness = f"""
const vm = require('vm');
const host = {{replaceChildren(...nodes) {{this.children = nodes;}}, setAttribute() {{}}}};
globalThis.document = {{getElementById: () => host, addEventListener() {{}},
  createElement: tag => ({{tag, children: [], append(...nodes) {{this.children.push(...nodes);}}, setAttribute() {{}}}})}};
globalThis.t = key => key;
globalThis.formatConsoleNumber = String;
vm.runInThisContext({json.dumps(source)});
renderAboutCapabilities([{{tier:'core',state:'active'}},{{tier:'core',state:'blocked'}}]);
const stats = host.children[0].children[1];
if (stats.tag !== 'dl' || stats.children.length !== 4) throw new Error('Missing labelled state counts');
if (stats.children.map(row => row.children[1].textContent).join() !== '1,0,0,1') throw new Error('Wrong counts');
renderAboutCapabilities([]);
if (host.children[0]?.textContent !== 'about.no_capabilities') throw new Error('Empty snapshot has no explanation');
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", harness], capture_output=True, text=True, timeout=15
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_about_exposes_build_support_and_maintenance_entry_points(self) -> None:
        fragment = ABOUT.read_text(encoding="utf-8")
        for element_id in (
            "aboutState",
            "aboutBuildFacts",
            "aboutSupportTiers",
            "checkUpdateBtn",
            "updateGuideLink",
            "backupGuideLink",
            "sponsorLink",
        ):
            self.assertIn(f'id="{element_id}"', fragment)
        self.assertNotRegex(fragment, r'id="(?:updateGuideLink|backupGuideLink)"[^>]*\bhidden\b')
        self.assertRegex(
            fragment,
            r'id="sponsorLink"[^>]*href="https://github\.com/sponsors/nguywnben"[^>]*target="_blank"[^>]*rel="noopener noreferrer"',
        )

    def test_about_cards_flow_in_independent_columns(self) -> None:
        fragment = ABOUT.read_text(encoding="utf-8")
        styles = (ROOT / "frontend/css/providers-and-models.css").read_text(encoding="utf-8")

        self.assertEqual(fragment.count('class="about-column"'), 2)
        self.assertRegex(
            styles,
            r"\.about-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*7fr\)\s+minmax\(0,\s*5fr\)",
        )
        self.assertRegex(styles, r"\.about-column\s*\{[^}]*align-content:\s*start")

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

    def test_about_does_not_prefix_unknown_version_with_v(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the About UI contract.")
        source = ABOUT_SCRIPT.read_text(encoding="utf-8")
        harness = f"""
const vm = require('vm');
let renderedValue = '';
globalThis.t = (key) => key === 'unknown_version' ? 'Unknown version' : key;
globalThis.document = {{
  getElementById: () => ({{replaceChildren: (...nodes) => {{ renderedValue = nodes[0].children[1].textContent; }}, setAttribute: () => {{}}}}),
  createElement: () => ({{children: [], append(...nodes) {{ this.children.push(...nodes); }}, textContent: '', className: ''}}),
  addEventListener: () => {{}}
}};
globalThis.AppState = {{}};
vm.runInThisContext({json.dumps(source)} + `\n;globalThis.contract = {{validateAboutVersion, renderAboutVersion}};`);
const version = globalThis.contract.validateAboutVersion({{success: true, version: 'unknown', source: 'container'}});
globalThis.contract.renderAboutVersion(version);
if (renderedValue !== 'Unknown version') throw new Error(`unexpected version: ${{renderedValue}}`);
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
