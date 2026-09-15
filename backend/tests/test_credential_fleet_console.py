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
POOL_HTML = ROOT / "frontend/fragments/pages/pool.html"
NUMBER_FORMAT_SOURCE = ROOT / "frontend/js/core/number-format.js"


class CredentialFleetConsoleTests(unittest.TestCase):
    def test_filtered_empty_results_do_not_hide_filter_controls(self) -> None:
        self._run_manager_contract("""
const tab = {classList: {toggle(name, value) {this[name] = value;}}};
const firstRun = {hidden: true};
elements.set('poolTab', tab);
elements.set('poolFirstRun', firstRun);
manager.hasLoaded = true;
manager.totalCount = 0;
manager.updateFirstRunState();
assert(firstRun.hidden === false, 'An unfiltered empty pool needs onboarding');
for (const definition of Object.values(manager.getFilterDefinitions())) {
    manager[definition.state] = 'filtered-value';
    manager.updateFirstRunState();
    assert(firstRun.hidden === true, 'Filtered zero results are not an empty pool');
    assert(tab.classList['is-pristine-empty'] === false, 'Filters must remain accessible');
    manager[definition.state] = 'all';
}
manager.hasLoaded = false;
manager.updateFirstRunState();
assert(firstRun.hidden === true, 'Loading is not an empty pool');
""")

    def test_load_errors_are_outside_the_data_only_region(self) -> None:
        html = POOL_HTML.read_text(encoding="utf-8")
        self.assertLess(html.index('id="primaryCredsState"'), html.index('id="poolFirstRun"'))

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
    location: {{href: 'http://localhost/pool', search: ''}},
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
        self.assertIn("const isCodexOAuth", source)

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
        self.assertIn('class="cred-actions-secondary"', source)
        self.assertIn("supportsQuotaPreview", source)
        primary_start = source.index("const primaryActionButtons")
        secondary_start = source.index("const secondaryActionButtons")
        test_action = source.index('data-credential-command="test"')
        quota_action = source.index('data-credential-command="quota"')
        self.assertLess(primary_start, secondary_start)
        self.assertGreater(test_action, primary_start)
        self.assertLess(test_action, secondary_start)
        self.assertGreater(quota_action, secondary_start)
        self.assertNotIn('data-credential-command="enable_credit"', source)
        self.assertNotIn('data-credential-command="disable_credit"', source)

    def test_cards_expose_safe_edit_and_oauth_reauthentication_actions(self) -> None:
        cards = CARD_SOURCE.read_text(encoding="utf-8")
        dialogs = (ROOT / "frontend/js/ui/credential-dialogs.js").read_text(encoding="utf-8")

        self.assertIn("const isManagedCredential", cards)
        self.assertIn("supportsEdit", cards)
        self.assertIn("supportsReauthenticate", cards)
        self.assertIn('data-credential-command="edit"', cards)
        self.assertIn('data-credential-command="reauthenticate"', cards)
        self.assertIn("credential_badge_environment", cards)
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
