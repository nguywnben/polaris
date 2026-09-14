"""Static Access lifecycle and secret-lifetime contracts for W3.9."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


class AccessVirtualKeyFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fragment = (FRONTEND / "fragments/pages/access.html").read_text(encoding="utf-8")
        cls.feature = (FRONTEND / "js/features/virtual-keys.js").read_text(encoding="utf-8")
        cls.navigation = (FRONTEND / "js/core/navigation.js").read_text(encoding="utf-8")
        cls.locales = (FRONTEND / "js/core/page-locales.js").read_text(encoding="utf-8")
        cls.root = (ROOT / "backend/core/panel/root.py").read_text(encoding="utf-8")
        cls.styles = (FRONTEND / "css/access.css").read_text(encoding="utf-8")

    def _run_client_example_contract(self, assertions: str) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the Access client example contract.")
        harness = f"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync({json.dumps(str(FRONTEND / "js/features/virtual-keys.js"))}, 'utf8');
vm.runInThisContext(source + `\n;globalThis.__buildAccessClientExample = buildAccessClientExample; globalThis.__syncVirtualKeyScopeControl = syncVirtualKeyScopeControl;`);
const build = globalThis.__buildAccessClientExample;
const syncScopes = globalThis.__syncVirtualKeyScopeControl;
function assert(condition, message) {{ if (!condition) throw new Error(message); }}
{assertions}
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

    def test_access_page_exposes_complete_lifecycle_controls(self):
        for control_id in (
            "virtualKeySearch",
            "virtualKeyStatusFilter",
            "virtualKeyList",
            "virtualKeyEmptyState",
        ):
            self.assertIn(f'id="{control_id}"', self.fragment)
        for action in ("create", "refresh", "edit", "usage", "rotate", "revoke"):
            self.assertIn(f"virtual-key-{action}", self.fragment + self.feature)

    def test_empty_key_collection_hides_irrelevant_filters_and_has_a_primary_action(self):
        self.assertIn('id="virtualKeySection"', self.fragment)
        self.assertIn('data-ui-action="virtual-key-create"', self.fragment)
        self.assertIn("is-pristine-empty", self.feature)
        self.assertIn(".virtual-key-section.is-pristine-empty .virtual-key-filters", self.styles)

    def test_form_covers_policy_and_governance_inputs(self):
        for field in (
            "name",
            "enabled",
            "expires_at",
            "budget_daily_usd",
            "budget_monthly_usd",
            "rpm_limit",
            "tpm_limit",
            "allowed_models",
            "scopes",
            "unknown_pricing_policy",
            "fallback_price_usd_per_million",
        ):
            self.assertIn(field, self.feature)

    def test_virtual_key_header_uses_an_optically_compact_primary_action(self):
        self.assertIn(
            'class="btn btn-secondary" data-ui-action="virtual-key-refresh"',
            self.fragment,
        )
        self.assertIn(
            'class="btn btn-compact" data-ui-action="virtual-key-create"',
            self.fragment,
        )

    def test_management_write_scope_explains_and_enforces_read_dependency(self):
        self.assertIn("t('access.management_write_requires_read')", self.feature)
        self.assertEqual(
            self.locales.count("'access.management_write_requires_read'"),
            2,
        )
        self.assertIn("if (input === write && write.checked) read.checked = true;", self.feature)
        self.assertIn("if (input === read && !read.checked) write.checked = false;", self.feature)
        self._run_client_example_contract(
            """
const read = { checked: false };
const write = { checked: true };
const inference = { checked: true };
const form = {
    querySelector(selector) {
        return selector.includes('management:write') ? write : read;
    }
};
read.form = form;
write.form = form;
inference.form = form;
syncScopes(write);
assert(read.checked, 'Management write must select management read');
syncScopes(inference);
assert(write.checked && read.checked, 'Inference scopes must not alter management scopes');
read.checked = false;
syncScopes(read);
assert(!write.checked, 'Removing management read must remove management write');
"""
        )

    def test_virtual_key_form_actions_match_the_compact_header_action_rhythm(self):
        self.assertIn('class="message-modal-footer virtual-key-form-actions"', self.feature)
        self.assertIn(
            'type="submit" class="message-modal-btn message-modal-btn-primary btn-compact"',
            self.feature,
        )
        self.assertRegex(
            self.styles,
            r"(?s)\.virtual-key-form-actions\s*\{.*?gap:\s*8px",
        )

    def test_create_form_empty_fields_have_localized_placeholders(self):
        placeholders = {
            "name": "access.key_name_placeholder",
            "rpm_limit": "access.rpm_limit_placeholder",
            "tpm_limit": "access.tpm_limit_placeholder",
            "budget_daily_usd": "access.daily_budget_placeholder",
            "budget_monthly_usd": "access.monthly_budget_placeholder",
            "allowed_models": "access.allowed_models_placeholder",
            "fallback_price_usd_per_million": "access.fallback_price_placeholder",
        }

        for field, translation_key in placeholders.items():
            with self.subTest(field=field):
                self.assertIn(f'name="{field}"', self.feature)
                marker = f"placeholder=\"${{escapeAttribute(t('{translation_key}'))}}\""
                self.assertIn(marker, self.feature)
                self.assertEqual(self.locales.count(f"'{translation_key}'"), 2)

    def test_zero_budget_and_fallback_price_are_visible(self):
        self.assertIn("record.budget_daily_usd !== null", self.feature)
        self.assertIn("record.budget_monthly_usd !== null", self.feature)
        self.assertIn("formatVirtualKeyPricingPolicy(record)", self.feature)
        self.assertIn("record.fallback_price_usd_per_million", self.feature)

    def test_secret_is_ephemeral_and_never_uses_browser_storage(self):
        self.assertIn("clearVirtualKeySecret", self.feature)
        self.assertIn("showVirtualKeySecret", self.feature)
        self.assertIn("secretInput.value = ''", self.feature)
        self.assertNotIn("localStorage", self.feature)
        self.assertNotIn("sessionStorage", self.feature)

    def test_access_loader_fetches_root_and_virtual_keys_together(self):
        self.assertIn("access: () => loadAccessPage()", self.navigation)
        self.assertIn("js/features/virtual-keys.js", self.root)
        self.assertIn("Promise.all([updateEndpointUrls(), loadVirtualKeys()])", self.feature)

    def test_lifecycle_mutations_send_optimistic_revision(self):
        self.assertIn("expected_revision: record.revision", self.feature)
        self.assertIn("/${encodeURIComponent(record.id)}/rotate", self.feature)
        self.assertIn("/${encodeURIComponent(record.id)}/revoke", self.feature)
        self.assertIn("error.status === 409", self.feature)

    def test_client_quickstart_tracks_selected_protocol_without_root_secret(self):
        for control_id in (
            "accessProtocol",
            "accessClientFormat",
            "accessClientExample",
            "copyAccessClientExample",
        ):
            self.assertIn(f'id="{control_id}"', self.fragment)
        self.assertIn("renderAccessClientExample", self.feature)
        self.assertIn("<YOUR_POLARIS_VIRTUAL_KEY>", self.feature)
        self.assertIn('<option value="openai_chat"', self.fragment)
        self.assertIn('<option value="openai_responses"', self.fragment)
        self.assertIn("cURL (Bash)", self.fragment)
        self.assertIn('<option value="powershell">PowerShell</option>', self.fragment)
        for format_name in ("curl", "powershell", "python", "node"):
            self.assertIn(f"{format_name}:", self.feature)
        self.assertNotIn("document.getElementById('apiKey').value", self.feature)
        self.assertNotIn("client-route-card", self.fragment)

    def test_client_quickstart_covers_every_protocol_and_shell(self):
        self._run_client_example_contract(
            """
for (const format of ['curl', 'powershell', 'python', 'node']) {
    for (const protocol of ['openai_chat', 'openai_responses', 'anthropic', 'gemini']) {
        const text = build(protocol, 'http://127.0.0.1:4283', format);
        assert(text.includes('<YOUR_POLARIS_VIRTUAL_KEY>'), `${format}/${protocol} placeholder`);
    }
}
assert(build('openai_responses', 'http://localhost', 'curl').includes('/v1/responses'), 'Responses route');
const powershell = build('openai_chat', 'http://localhost', 'powershell');
assert(powershell.startsWith('curl.exe '), 'PowerShell must invoke curl.exe explicitly');
assert(powershell.includes(String.fromCharCode(96, 10)), 'PowerShell line continuation');
assert(!powershell.includes(String.fromCharCode(32, 92, 10)), 'PowerShell must not use Bash continuation');
assert(build('openai_chat', 'http://localhost', 'node').includes('client.mjs'), 'Node ESM guidance');
"""
        )

    def test_client_quickstart_uses_a_balanced_responsive_control_grid(self):
        self.assertIn(
            'class="btn btn-secondary btn-small" id="copyAccessClientExample"', self.fragment
        )
        self.assertRegex(
            self.styles,
            r"(?s)\.access-client-header\s*\{.*?display: grid.*?grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)",
        )
        self.assertRegex(
            self.styles,
            r"(?s)\.access-client-header\s*>\s*div\s*\{.*?grid-column: 1 / -1",
        )
        self.assertRegex(
            self.styles,
            r"(?s)@media \(max-width: 600px\).*?\.access-client-header.*?grid-template-columns: minmax\(0, 1fr\)",
        )

    def test_secret_cleanup_clears_value_and_removes_secret_node(self):
        self.assertIn("secretInput.value = ''", self.feature)
        self.assertIn("secretInput.removeAttribute('value')", self.feature)
        self.assertIn("modal.replaceChildren()", self.feature)
        self.assertIn("pagehide", self.feature)

    def test_destructive_lifecycle_actions_require_explicit_confirmation(self):
        self.assertIn("showConfirmModal(t('access.rotate_confirm'", self.feature)
        self.assertIn("showConfirmModal(t('access.revoke_confirm'", self.feature)
        self.assertIn("confirmLabel: t('access.rotate_key')", self.feature)
        self.assertIn("confirmLabel: t('access.revoke_key')", self.feature)


if __name__ == "__main__":
    unittest.main()
