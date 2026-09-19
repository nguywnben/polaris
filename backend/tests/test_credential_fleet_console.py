"""Browser-side credential fleet workflow contracts for P3.5."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANAGER_SOURCE = ROOT / "frontend/js/core/credential-manager.js"
CARD_SOURCE = ROOT / "frontend/js/ui/credential-cards.js"
CARD_STYLES = ROOT / "frontend/css/components.css"
POOL_HTML = ROOT / "frontend/fragments/pages/credentials.html"
NUMBER_FORMAT_SOURCE = ROOT / "frontend/js/core/number-format.js"


class CredentialFleetConsoleTests(unittest.TestCase):
    def test_badge_hints_dismiss_without_moving_focus_and_reopen_on_reentry(self) -> None:
        self._run_manager_contract(f"""
vm.runInThisContext(fs.readFileSync({json.dumps(str(CARD_SOURCE))}, 'utf8'));
const listeners = {{}};
const badge = {{dataset: {{}}, contains: node => node === badge}};
document.addEventListener = (name, handler) => {{ listeners[name] = handler; }};
document.querySelectorAll = () => [badge];
initCredentialBadgeHints();
let consumed = 0;
listeners.keydown({{key: 'Escape', preventDefault() {{ consumed++; }}, stopPropagation() {{}}}});
assert(badge.dataset.hintDismissed === 'true' && consumed === 1, 'Escape dismisses the hint');
const target = {{closest: () => badge}};
listeners.pointerover({{target, relatedTarget: badge}});
assert(badge.dataset.hintDismissed === 'true', 'Moving within a dismissed hint must not reopen it');
listeners.pointerover({{target, relatedTarget: null}});
assert(!badge.dataset.hintDismissed, 'Pointer reentry reopens the hint');
badge.dataset.hintDismissed = 'true';
listeners.focusin({{target}});
assert(!badge.dataset.hintDismissed, 'Keyboard focus reentry reopens the hint');
document.querySelectorAll = () => [];
listeners.keydown({{key: 'Escape', preventDefault() {{ throw new Error('Unrelated Escape intercepted'); }}}});
""")

    def test_identity_subtitle_uses_only_masked_key_or_oauth_email(self) -> None:
        self._run_manager_contract(f"""
vm.runInThisContext(fs.readFileSync({json.dumps(str(CARD_SOURCE))}, 'utf8'));
global.escapeHtml = global.escapeAttribute = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
const provider = {{id: 'openai_platform'}};
const key = {{credential_type: 'api_key', api_key_hint: 'sample…last', api_key: 'never-render-this'}};
assert(renderCredentialIdentitySubtitle(provider, key, 'Work').includes('sample…last'), 'Show masked key beneath the name');
assert(!renderCredentialIdentitySubtitle(provider, key, 'Work').includes('never-render'), 'Never derive preview from a full client-side key');
assert(renderCredentialIdentitySubtitle(provider, {{api_key: 'secret'}}, 'Work') === '', 'Missing hint must not fall back to the full key');
assert(!renderCredentialIdentitySubtitle(provider, {{...key, api_key_hint: '<img src=x>'}}, 'Work').includes('<img'), 'Escape the hint');
const oauth = {{credential_type: 'oauth', credential_label: 'Work', user_email: 'user@example.test', api_key_hint: 'not-for-oauth'}};
assert(renderCredentialIdentitySubtitle({{id: 'muse_code'}}, oauth, 'Work').includes('user@example.test'), 'Keep OAuth email under a label');
assert(!renderCredentialIdentitySubtitle({{id: 'muse_code'}}, oauth, 'Work').includes('not-for-oauth'), 'OAuth must not show key hints');
assert(renderCredentialIdentitySubtitle({{id: 'muse_code'}}, oauth, 'user@example.test') === '', 'Do not repeat the email when it is the main title');
""")

    def test_compact_badges_keep_full_plan_and_oauth_in_management(self) -> None:
        self._run_manager_contract(f"""
vm.runInThisContext(fs.readFileSync({json.dumps(str(CARD_SOURCE))}, 'utf8'));
global.escapeHtml = global.escapeAttribute = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
const plan = 'Muse Code Power Usage';
const badge = renderCredentialSubscriptionBadge('test', plan, 'provider_plan');
assert(badge.includes(`class="credential-badge-label">${{plan}}</span>`), 'Card should show the plan without the Gói prefix');
assert(!badge.includes('tabindex=') && !badge.includes('credential-badge-tooltip') && !badge.includes(' title='), 'Plan is plain text without a hover or focus tooltip');
assert(badge.includes(plan) && !badge.includes('Power…'), 'Truncation must be visual, not data loss');
assert(renderCredentialSubscriptionBadge('test', '', 'provider_plan').includes('hidden'), 'Unknown plans stay hidden');
const unsafe = renderCredentialSubscriptionBadge('test', '<img src=x>', 'provider_plan');
assert(!unsafe.includes('<img'), 'Provider plan text must be escaped');
const oauth = {{id: 'muse_code'}};
const info = {{credential_type: 'oauth'}};
assert(renderCredentialAuthenticationBadge(oauth, info, {{compact: true}}) === '', 'Do not repeat OAuth in compact cards');
assert(renderCredentialAuthenticationBadge(oauth, info).includes('OAuth'), 'Management still shows OAuth');
assert(renderCredentialAuthenticationBadge({{id: 'openai_platform'}}, {{}}, {{compact: true}}).includes('credentials.workspace.api_key'), 'Keep API key badges');
""")

    def test_quota_refresh_preserves_plan_badge_until_a_new_plan_arrives(self) -> None:
        dialogs = ROOT / "frontend/js/ui/credential-dialogs.js"
        self._run_manager_contract(f"""
vm.runInThisContext(fs.readFileSync({json.dumps(str(CARD_SOURCE))}, 'utf8'));
vm.runInThisContext(fs.readFileSync({json.dumps(str(dialogs))}, 'utf8'));
global.escapeHtml = global.escapeAttribute = String;
let replacements = 0;
const badge = {{
    querySelector: () => ({{textContent: 'G1 Pro Tier'}}),
    classList: {{contains: name => name === 'tier-pro'}},
    set outerHTML(value) {{ replacements++; this.markup = value; }},
}};
elements.set('subscription-plan-card', badge);
global.AppState = {{credentialCardIndex: {{card: {{providerVariant: 'google_antigravity', subscriptionPlan: 'pro'}}}}, quotaPreviewCache: {{}}}};
for (const cached of [{{loading: true}}, {{error: 'Quota unavailable'}}, {{data: {{}}}}, {{data: {{plan: 'g1-pro-tier'}}}}]) {{
    AppState.quotaPreviewCache.file = cached;
    updateCredentialSubscriptionBadge('card', 'file');
    assert(replacements === 0, 'Loading, error, absent or unchanged plan must preserve the existing badge node');
}}
AppState.quotaPreviewCache.file = {{data: {{plan: 'ultra'}}}};
updateCredentialSubscriptionBadge('card', 'file');
assert(replacements === 1 && badge.markup.includes('Ultra'), 'A confirmed plan change must still update');
""")

    def test_card_summary_only_shows_enabled_state_and_plan(self) -> None:
        self._run_manager_contract(f"""
vm.runInThisContext(fs.readFileSync({json.dumps(str(CARD_SOURCE))}, 'utf8'));
global.escapeHtml = global.escapeAttribute = String;
global.AppState = {{quotaPreviewCache: {{file: {{data: {{plan: 'g1-pro-tier'}}}}}}, credentialCardIndex: {{}}}};
global.getCredentialProviderMeta = () => ({{id: 'google_antigravity', name: 'Antigravity'}});
global.renderCredentialQuotaPreview = () => '';
global.formatCooldownTime = () => '60s';
document.createElement = () => ({{querySelector: () => null, querySelectorAll: () => []}});
manager.credentialSupportsOperation = () => false;
const card = createCredCard({{filename: 'file', status: {{disabled: true, error_codes: [403]}},
    credential_type: 'oauth', tier: 'g1-pro-tier', enable_credit: true,
    model_cooldowns: {{'gemini-pro': Date.now() / 1000 + 60}}}}, manager);
const summary = card.innerHTML.split('<div class="cred-status cred-summary">')[1].split('</div>')[0];
assert((summary.match(/class="status-badge /g) || []).length === 2, 'Only enabled state and plan belong in the summary');
assert(!card.innerHTML.includes('cooldown-badge') && !summary.includes('error-codes') && !summary.includes('credit-on'), 'Diagnostics must not add card badges');
""")

    def test_provider_sections_are_ordered_by_matching_credential_count(self) -> None:
        self._run_manager_contract("""
const list = new TestElement();
list.innerHTML = '';
list.classList = {remove() {}};
list.appendChild = () => {};
const pagination = new TestElement();
pagination.style = {};
elements.set('primaryCredsList', list);
elements.set('primaryPaginationContainer', pagination);
const order = [];
global.getCredentialProviderMeta = cred => ({id: cred.provider, name: cred.provider});
global.createCredentialProviderGroup = (meta, credentials) => {
    order.push([meta.name, credentials.length]);
    return {};
};
manager.filteredData = {
    a: {filename: 'a', provider: 'few'},
    b: {filename: 'b', provider: 'many'},
    c: {filename: 'c', provider: 'many'},
    d: {filename: 'd', provider: 'many'},
    e: {filename: 'e', provider: 'medium'},
    f: {filename: 'f', provider: 'medium'},
};
manager.data = manager.filteredData;
manager.totalCount = 6;
manager.hasLoaded = true;
manager.facets = {provider_variant: {few: 8, many: 4, medium: 2}};
manager.renderList();
assert(JSON.stringify(order) === JSON.stringify([
    ['few', 1], ['many', 3], ['medium', 2]
]), `Unexpected provider section order: ${JSON.stringify(order)}`);
""")

    def test_every_displayed_provider_filter_is_applied_and_restored(self) -> None:
        from backend.core.provider_registry import list_credential_variant_capabilities

        variants = [item["variant_id"] for item in list_credential_variant_capabilities()]
        self._run_manager_contract(f"""
const variants = {json.dumps(variants)};
const providerFilter = new TestElement();
providerFilter.options = ['all', ...variants].map(value => ({{value}}));
elements.set('primaryProviderFilter', providerFilter);
manager.refresh = () => {{}};
for (const variant of variants) {{
    providerFilter.value = variant;
    manager.applyStatusFilter();
    assert(manager.currentProviderFilter === variant, `Provider filter ignored: ${{variant}}`);
    manager.filtersRestored = false;
    manager.currentProviderFilter = 'all';
    window.location.search = '?pool_provider=' + variant;
    manager.restoreFilterState();
    assert(manager.currentProviderFilter === variant, `Provider deep link not restored: ${{variant}}`);
}}
providerFilter.value = 'unregistered';
manager.applyStatusFilter();
assert(manager.currentProviderFilter !== 'unregistered', 'Do not accept unregistered filter values');
""")

    def test_identity_uses_labels_or_oauth_email_not_missing_email_errors(self) -> None:
        self._run_manager_contract(f"""
vm.runInThisContext(fs.readFileSync({json.dumps(str(CARD_SOURCE))}, 'utf8'));
const oauth = {{credential_type: 'oauth', filename: 'muse-code-ab12.json'}};
const key = {{credential_type: 'api_key', filename: 'deepseek-cd34.json'}};
assert(getCredentialAccountLabel(oauth) === 'muse-code-ab12', 'OAuth without email needs an identifier');
assert(getCredentialAccountLabel(key) === 'deepseek-cd34', 'Keys do not need email');
assert(getCredentialAccountLabel({{...oauth, user_email: 'person@example.test'}}) === 'person@example.test', 'Keep known OAuth email');
assert(getCredentialAccountLabel({{...key, user_email: 'not-an-account'}}) === 'deepseek-cd34', 'API keys must not use email fallback');
assert(getCredentialAccountLabel({{...oauth, credential_label: 'Work'}}) === 'Work', 'Explicit labels take precedence');
assert(!getCredentialAccountLabel({{...key, api_key: 'secret-key'}}).includes('secret'), 'Never derive identity from a secret');
""")

    def test_provider_batch_snapshots_scope_and_preserves_unrelated_selection(self) -> None:
        self._run_manager_contract("""
(async () => {
    manager.selectedFiles = new Set(['other.json']);
    const targets = ['provider-a.json', 'provider-b.json'];
    const requests = [];
    global.AppState = {quotaPreviewCache: {}, credentialCardIndex: {}};
    global.showStatus = () => {};
    global.showMessageModal = () => {};
    global.showConfirmModal = async (message) => {
        assert(message.includes('Provider A'), 'Confirmation must name the provider scope');
        targets.push('unrelated.json');
        manager.selectedFiles.add('another.json');
        return true;
    };
    global.fetch = async (url, options) => {
        requests.push(JSON.parse(options.body));
        return {ok: true, json: async () => ({total_count: 2, success_count: 2,
            outcome_counts: {eligible: 2}, preview_token: 'snapshot', results: []})};
    };
    manager.refresh = async () => {};
    await manager.batchAction('disable', {filenames: targets, description: 'Provider A — visible credentials'});
    assert(requests.length === 2, 'Batch needs preview and commit');
    assert(requests.every(body => JSON.stringify(body.filenames) === JSON.stringify(['provider-a.json', 'provider-b.json'])), 'Scope must stay fixed across confirmation');
    assert(requests[1].preview_token === 'snapshot', 'Server preview token must be retained');
    assert(manager.selectedFiles.has('other.json') && manager.selectedFiles.has('another.json'), 'Provider action must preserve global selection');
})().catch(error => {console.error(error); process.exitCode = 1;});
""")

    def test_filtered_empty_results_do_not_hide_filter_controls(self) -> None:
        self._run_manager_contract("""
const tab = {classList: {toggle(name, value) {this[name] = value;}}};
const firstRun = {hidden: true};
elements.set('credentialsTab', tab);
elements.set('credentialsFirstRun', firstRun);
manager.hasLoaded = true;
manager.totalCount = 0;
manager.updateFirstRunState();
assert(firstRun.hidden === false, 'An unfiltered empty pool needs onboarding');
for (const definition of Object.values(manager.getFilterDefinitions())) {
    manager[definition.state] = 'filtered-value';
    manager.updateFirstRunState();
    assert(firstRun.hidden === true, 'Filtered zero results are not an empty credential store');
    assert(tab.classList['is-pristine-empty'] === false, 'Filters must remain accessible');
    manager[definition.state] = 'all';
}
manager.hasLoaded = false;
manager.updateFirstRunState();
assert(firstRun.hidden === true, 'Loading is not an empty credential store');
""")

    def test_load_errors_are_outside_the_data_only_region(self) -> None:
        html = POOL_HTML.read_text(encoding="utf-8")
        self.assertLess(
            html.index('id="primaryCredsState"'), html.index('id="credentialsFirstRun"')
        )

    def _run_manager_contract(self, assertions: str) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the credential fleet DOM contract.")
        harness = f"""
const fs = require('fs');
const vm = require('vm');
class TestElement {{
    constructor() {{
        this.disabled = false;
        this.hidden = false;
        this.title = '';
        this.textContent = '';
        this.checked = false;
        this.indeterminate = false;
        this.value = 'all';
        this.selectedOptions = [{{textContent: 'All'}}];
    }}
}}
const elements = new Map();
for (const suffix of [
    'SelectedCount', 'BatchEnableBtn', 'BatchDisableBtn', 'BatchDeleteBtn',
    'BatchVerifyBtn',
    'SelectAllCheckbox', 'SelectAllMatchingBtn', 'ClearSelectionBtn'
]) elements.set(`primary${{suffix}}`, new TestElement());
global.document = {{
    getElementById(id) {{ return elements.get(id) || null; }},
    querySelectorAll() {{ return []; }},
    querySelector(selector) {{
        return selector.startsWith('label[for=') ? {{textContent: 'Filter'}} : null;
    }}
}};
global.window = {{
    location: {{href: 'http://localhost/credentials', search: ''}},
    history: {{state: null, replaceState() {{}}}}
}};
global.sessionStorage = {{getItem() {{ return null; }}, setItem() {{}}}};
global.t = (key, values = {{}}) => `${{key}}:${{JSON.stringify(values)}}`;
global.getActiveLocale = () => 'en-US';
global.getAuthHeaders = () => ({{}});
const numberSource = fs.readFileSync({json.dumps(str(NUMBER_FORMAT_SOURCE))}, 'utf8');
const source = fs.readFileSync({json.dumps(str(MANAGER_SOURCE))}, 'utf8');
vm.runInThisContext(numberSource);
vm.runInThisContext(source + '\\n;globalThis.__createCredsManager = createCredsManager;');
const manager = globalThis.__createCredsManager('primary');
manager.permissions = new Set(['credentials.read', 'credentials.operate', 'credentials.manage', 'credentials.export']);
manager.capabilityByVariant = {{
    common: {{operations: ['toggle', 'delete', 'verify']}},
    credit: {{operations: ['toggle', 'delete', 'verify', 'credit_mode']}}
}};
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

    def test_card_renderer_has_no_removed_provider_flag_reference(self) -> None:
        source = CARD_SOURCE.read_text(encoding="utf-8")

        self.assertNotIn("isStaticProvider", source)
        self.assertNotIn("isCodexOAuth", source)
        self.assertIn("const supportsQuotaPreview", source)
        self.assertIn("} else if (supportsQuotaPreview)", source)
        self.assertIn("manager.credentialSupportsOperation(credInfo, 'quota')", source)

    def test_credential_page_navigation_is_single_flight_and_preserves_content(self) -> None:
        source = MANAGER_SOURCE.read_text(encoding="utf-8")

        self.assertIn("pageChangePromise: null", source)
        self.assertIn("preserveContent: true", source)
        self.assertIn("this.pageChangePromise", source)

    def test_select_page_checkbox_uses_the_manager_id_contract(self) -> None:
        html = POOL_HTML.read_text(encoding="utf-8")

        self.assertIn('id="primarySelectAllCheckbox"', html)
        self.assertIn('for="primarySelectAllCheckbox"', html)
        self.assertNotIn('id="selectAllPrimaryCheckbox"', html)

    def test_mixed_selection_hides_provider_specific_actions(self) -> None:
        html = POOL_HTML.read_text(encoding="utf-8")

        self.assertNotIn('data-batch-action="enable_credit"', html)
        self.assertNotIn('data-batch-action="disable_credit"', html)
        self.assertNotIn('id="primaryBatchEnableCreditBtn"', html)
        self.assertNotIn('id="primaryBatchDisableCreditBtn"', html)
        self._run_manager_contract(
            """
manager.data = {a: {provider_variant: 'common'}, b: {provider_variant: 'credit'}};
manager.selectedFiles = new Set(['a', 'b']);
manager.updateBatchControls();
assert(elements.get('primaryBatchEnableBtn').disabled === false, 'common enable disabled');
assert(elements.get('primaryBatchDeleteBtn').disabled === false, 'common delete disabled');
assert(elements.get('primaryBatchVerifyBtn').hidden === false, 'common verify hidden');
"""
        )

    def test_card_actions_separate_standard_and_provider_specific_operations(self) -> None:
        source = CARD_SOURCE.read_text(encoding="utf-8")

        self.assertIn('class="cred-actions-primary"', source)
        self.assertIn('data-credential-command="manage"', source)
        self.assertIn('class="cred-btn icon-btn view"', source)
        self.assertIn('class="cred-btn icon-btn disable"', source)
        self.assertIn('class="cred-btn icon-btn" data-credential-command="test"', source)
        self.assertIn('class="visually-hidden"', source)
        self.assertIn("showCredentialManagement(pathId, manager, credInfo", source)
        self.assertIn("supportsQuotaPreview", source)
        primary_start = source.index("const primaryActionButtons")
        test_action = source.index('data-credential-command="test"')
        self.assertGreater(test_action, primary_start)
        self.assertNotIn("const secondaryActionButtons", source)
        workspace = (ROOT / "frontend/js/ui/credential-management.js").read_text(encoding="utf-8")
        self.assertIn("capabilities.quota ? credentialManagementSection", workspace)
        self.assertIn("capabilities.models || capabilities.test", workspace)
        self.assertIn("data-management-result", workspace)
        self.assertNotIn("showMessageModal(", workspace)
        self.assertNotIn('data-credential-command="enable_credit"', source)
        self.assertNotIn('data-credential-command="disable_credit"', source)

    def test_primary_card_actions_fit_on_one_row(self) -> None:
        styles = CARD_STYLES.read_text(encoding="utf-8")

        self.assertRegex(
            styles,
            r"\.cred-actions-primary\s*\{\s*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\);",
        )
        self.assertNotIn(
            '.cred-actions-primary [data-credential-command="manage"]',
            styles,
        )

    def test_cards_expose_safe_edit_and_oauth_reauthentication_actions(self) -> None:
        cards = CARD_SOURCE.read_text(encoding="utf-8")
        dialogs = (ROOT / "frontend/js/ui/credential-dialogs.js").read_text(encoding="utf-8")

        self.assertIn("const isManagedCredential", cards)
        self.assertIn("supportsEdit", cards)
        self.assertIn("supportsReauthenticate", cards)
        self.assertIn("edit: supportsEdit", cards)
        self.assertIn("reauthenticate: supportsReauthenticate", cards)
        self.assertIn(
            "settings.managed_environment",
            (ROOT / "frontend/js/ui/credential-management.js").read_text(encoding="utf-8"),
        )
        self.assertIn("showCredentialEditModal(pathId)", cards)
        self.assertIn("reauthenticateCredential(pathId)", cards)
        self.assertIn("/configuration/", dialogs)
        self.assertIn("method: 'PATCH'", dialogs)
        self.assertIn("data-credential-edit-form", dialogs)

    def test_explicit_and_all_matching_batches_share_the_100_item_bound(self) -> None:
        self._run_manager_contract(
            """
manager.data = Object.fromEntries(Array.from({length: 101}, (_, index) => [
    `cred-${index}`, {provider_variant: 'common'}
]));
manager.selectedFiles = new Set(Object.keys(manager.data));
manager.updateBatchControls();
assert(elements.get('primaryBatchDeleteBtn').disabled === true, '101 explicit targets enabled');
assert(elements.get('primaryBatchDeleteBtn').title.includes('pool.operation.limit'), 'limit reason missing');
manager.selectionScope = 'all_matching';
manager.allMatchingSelection = {matching_count: 101, token: 'selection-token'};
manager.facets = {provider_variant: {common: 101}};
manager.updateBatchControls();
assert(elements.get('primaryBatchDeleteBtn').disabled === true, '101 matching targets enabled');
"""
        )

    def test_filters_are_progressively_disclosed_and_resettable(self) -> None:
        html = POOL_HTML.read_text(encoding="utf-8")

        self.assertIn('data-credential-filter-tier="primary"', html)
        self.assertIn('data-credential-filter-tier="advanced"', html)
        self.assertIn('data-ui-action="reset-primary-filters"', html)
        self._run_manager_contract(
            """
for (const definition of Object.values(manager.getFilterDefinitions())) {
    elements.set(`primary${definition.suffix}`, new TestElement());
}
elements.set('primaryActiveFilterCount', new TestElement());
elements.set('primaryAdvancedFilters', new TestElement());
manager.refresh = () => {};
manager.currentProviderFilter = 'codex';
manager.updateActiveFilterSummary();
assert(elements.get('primaryActiveFilterCount').textContent.includes('pool.filters.active'), 'active filter count missing');
manager.currentSourceFilter = 'environment';
manager.updateActiveFilterSummary();
assert(elements.get('primaryAdvancedFilters').open === true, 'advanced filter not disclosed');
manager.resetFilters();
assert(manager.currentProviderFilter === 'all', 'primary filter not reset');
assert(manager.currentSourceFilter === 'all', 'advanced filter not reset');
assert(elements.get('primaryAdvancedFilters').open === false, 'advanced filters left open after reset');
"""
        )

    def test_all_matching_preview_names_the_exact_query_and_impact(self) -> None:
        source = MANAGER_SOURCE.read_text(encoding="utf-8")

        self._run_manager_contract(
            """
const providerFilter = new TestElement();
providerFilter.value = 'codex';
providerFilter.selectedOptions = [{textContent: 'Codex'}];
elements.set('primaryProviderFilter', providerFilter);
manager.currentProviderFilter = 'codex';
manager.selectionScope = 'all_matching';
manager.allMatchingSelection = {matching_count: 2, token: 'selection-token', query_fingerprint: 'query-123'};
const description = manager.describeSelectionQuery();
assert(description.includes('Codex'), 'exact filter value missing');
assert(description.includes('query-123'), 'query fingerprint missing');
"""
        )
        query_index = source.index("this.describeSelectionQuery()")
        confirmation_index = source.index("await showConfirmModal(confirmMsg, confirmOptions)")
        self.assertLess(query_index, confirmation_index)

    def test_refresh_retains_valid_selection_and_persists_the_page(self) -> None:
        source = MANAGER_SOURCE.read_text(encoding="utf-8")

        self.assertIn("pool_page", source)
        self.assertIn("retainVisibleSelection()", source)
        self.assertIn("this.currentPage > totalPages", source)


if __name__ == "__main__":
    unittest.main()
