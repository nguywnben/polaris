"""Browser-side model routing workflow contracts for P3.6."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "frontend/js/features/model-pool.js"
FRAGMENT = ROOT / "frontend/fragments/pages/models.html"
STYLES = ROOT / "frontend/css/providers-and-models.css"


class ModelRoutingConsoleTests(unittest.TestCase):
    def test_global_policy_is_outside_the_catalog_only_workspace(self) -> None:
        fragment = FRAGMENT.read_text(encoding="utf-8")
        self.assertLess(
            fragment.index('id="modelRoutingPolicyPanel"'),
            fragment.index('id="modelPoolWorkspace"'),
        )
        self.assertIn('data-ui-action="save-model-routing-policy"', fragment)

    def test_global_policy_save_is_independent_and_preserves_failed_drafts(self) -> None:
        self._run_contract("""
(async () => {
    const strategy = {value: 'weighted', disabled: false};
    const preferred = {value: '', disabled: false};
    const panel = {inert: false};
    const button = {disabled: false};
    const elements = {modelRoutingStrategy: strategy, modelPreferredProvider: preferred,
        modelRoutingPolicyPanel: panel, saveModelRoutingPolicyBtn: button};
    global.document = {getElementById: id => elements[id] || null};
    global.AppState = {modelRoutingPolicy: {strategy: 'balanced', preferred_provider: ''}};
    global.getAuthHeaders = () => ({});
    global.t = key => key;
    const notices = [];
    global.showStatus = (message, type) => notices.push(type);
    updateModelPoolSummary = () => {};
    let finish;
    const writes = [];
    global.fetch = (url, options) => {
        writes.push({url, body: JSON.parse(options.body)});
        return new Promise(resolve => {finish = resolve;});
    };
    let saving = saveModelRoutingSettings();
    await saveModelRoutingSettings();
    assert(writes.length === 1, 'duplicate saves must not submit twice');
    assert(writes[0].url === './api/config/save', 'policy save must not write/validate a model route');
    assert(writes[0].body.config.routing_strategy === 'weighted', 'policy change missing');
    finish({ok: false, json: async () => ({detail: 'fixture failure'})});
    await saving;
    assert(strategy.value === 'weighted' && AppState.modelRoutingPolicy.strategy === 'balanced',
        'failure must retain the draft and old saved policy');
    assert(!panel.inert && !button.disabled && notices.at(-1) === 'error', 'failed save must unlock retry');
    saving = saveModelRoutingSettings();
    finish({ok: true, json: async () => ({})});
    await saving;
    assert(AppState.modelRoutingPolicy.strategy === 'weighted', 'successful save must update saved state');
    assert(button.disabled && notices.at(-1) === 'success', 'saved policy must no longer be dirty');
    await saveModelRoutingSettings();
    assert(writes.length === 2, 'unchanged policy must not be written');
    AppState.modelRoutingPolicy.strategy_locked = true;
    strategy.value = 'priority';
    await saveModelRoutingSettings();
    assert(writes.length === 2, 'environment locked policy must not be written');
})().catch(error => { console.error(error); process.exitCode = 1; });
""")

    def test_empty_catalog_keeps_existing_route_and_failure_workspaces(self) -> None:
        self._run_contract("""
const tab = {classList: {toggle(name, value) {this[name] = value;}}};
const firstRun = {hidden: true};
global.document = {getElementById: id => id === 'modelsTab' ? tab : firstRun};
global.AppState = {modelCatalogLoaded: true, modelCatalog: [], selectedModels: [],
    modelPoolConfigured: false, modelBlacklist: []};
updateModelFirstRunState();
assert(!firstRun.hidden, 'A fresh empty catalog needs onboarding');
for (const [key, value] of [['modelPoolConfigured', true], ['selectedModels', ['saved-model']],
    ['modelBlacklist', [{model_id: 'failed-model'}]]]) {
    const previous = AppState[key];
    AppState[key] = value;
    updateModelFirstRunState();
    assert(firstRun.hidden, 'Existing route or failure data must stay accessible: ' + key);
    assert(!tab.classList['is-pristine-empty'], 'Workspace must not be hidden');
    AppState[key] = previous;
}
AppState.modelCatalogLoaded = false;
updateModelFirstRunState();
assert(firstRun.hidden, 'Loading is not an empty catalog');
""")

    def _run_contract(self, assertions: str) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the model routing DOM contract.")
        harness = f"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync({json.dumps(str(SCRIPT))}, 'utf8');
vm.runInThisContext(source + `\n;globalThis.__modelRouteContract = {{deriveModelRouteState, buildModelPlaygroundHandoff}};`);
const {{deriveModelRouteState: derive, buildModelPlaygroundHandoff: handoff}} = globalThis.__modelRouteContract;
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

    def test_route_state_explains_ready_degraded_and_unavailable_drafts(self) -> None:
        self._run_contract(
            """
const catalog = [
    {model_id: 'healthy', available: true, routable_providers: ['codex', 'openai']},
    {model_id: 'cooling', available: false, routable_providers: []}
];
const ready = derive(['healthy'], catalog);
const degraded = derive(['healthy', 'cooling'], catalog);
const unavailable = derive(['cooling'], catalog);
const unknown = derive(['copied-by-hand'], catalog);
assert(ready.valid && ready.status === 'ready' && ready.summary.provider_routes === 2, 'ready route');
assert(degraded.valid && degraded.status === 'degraded', 'degraded route');
assert(!unavailable.valid && unavailable.status === 'unavailable', 'unavailable route');
assert(unknown.issues[0].code === 'model_not_discovered', 'unknown model explanation');
"""
        )

    def test_route_lifecycle_has_validation_conflict_and_delete_contracts(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        fragment = FRAGMENT.read_text(encoding="utf-8")

        for element_id in (
            "modelRoutingStrategy",
            "modelPreferredProvider",
            "validateModelRouteBtn",
            "testModelRouteBtn",
            "deleteModelRouteBtn",
            "saveModelPoolBtn",
        ):
            self.assertIn(f'id="{element_id}"', fragment)
        self.assertIn("method: creating ? 'POST' : 'PATCH'", source)
        self.assertIn("method: 'DELETE'", source)
        self.assertIn("headers['If-Match'] = AppState.modelPoolRevision", source)
        self.assertIn("model_route_conflict", source)
        self.assertIn("./api/model-routes/polaris/validate", source)

    def test_route_state_uses_compact_badge_without_redundant_validation_panel(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        fragment = FRAGMENT.read_text(encoding="utf-8")
        styles = STYLES.read_text(encoding="utf-8")

        self.assertIn('id="modelPoolStatus"', fragment)
        self.assertNotIn('id="modelRouteValidation"', fragment)
        self.assertNotIn("renderModelRouteValidation", source)
        self.assertNotIn(".model-route-validation", styles)

    def test_empty_catalog_uses_a_guided_first_run_state(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        fragment = FRAGMENT.read_text(encoding="utf-8")

        self.assertIn('id="modelFirstRun"', fragment)
        self.assertIn("updateModelFirstRunState()", source)
        self.assertIn("model-data-only", fragment)

    def test_virtual_model_description_stays_close_to_alias(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")

        self.assertRegex(
            styles,
            r"\.model-pool-heading\s+\.model-alias-title\s*\{[^}]*margin:\s*3px 0 0;",
        )

    def test_playground_handoff_is_bounded_and_contains_no_secret(self) -> None:
        self._run_contract(
            """
const result = handoff('polaris');
assert(JSON.stringify(result) === JSON.stringify({
    schema_version: 'playground-handoff.v1', source: 'models', model: 'polaris'
}), 'handoff contract changed');
assert(!('api_key' in result) && !('credential' in result) && !('prompt' in result), 'secret-capable field');
"""
        )

    def test_stale_validation_is_discarded_and_route_conflict_does_not_save_policy(self) -> None:
        self._run_contract(
            """
(async () => {
    global.AppState = {selectedModels: ['healthy'], savedModelSelection: ['healthy'],
        modelPoolConfigured: true, modelPoolRevision: 'revision', modelPoolEnabled: true};
    global.document = {getElementById: () => null};
    global.t = key => key;
    global.getAuthHeaders = () => ({});
    global.showStatus = () => {};
    let finish;
    global.fetch = () => new Promise(resolve => { finish = resolve; });
    const validating = validateModelRoute();
    AppState.selectedModels = ['changed'];
    finish({ok: true, json: async () => ({validation: {valid: true}})});
    assert(await validating === null, 'stale validation must be discarded');
    assert(!AppState.modelRouteValidation, 'stale result cannot replace current draft state');
    assert(modelRouteHasUnsavedChanges(), 'changed selection must be dirty');
    let policyWrites = 0;
    validateModelRoute = async () => ({valid: true});
    saveModelRoutingPolicy = async () => { policyWrites++; };
    loadModelCatalog = async () => {};
    global.fetch = async () => ({ok: false, json: async () => ({detail: {code: 'model_route_conflict'}})});
    await saveModelPool();
    assert(policyWrites === 0, 'a conflicting route must not mutate the global policy');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
        )

    def test_policy_draft_does_not_mark_the_independently_saved_route_dirty(self) -> None:
        self._run_contract(
            """
const strategy = {value: 'weighted'};
global.document = {getElementById: id => id === 'modelRoutingStrategy' ? strategy : null};
global.AppState = {selectedModels: ['healthy'], savedModelSelection: ['healthy'],
    modelRoutingPolicy: {strategy: 'balanced', preferred_provider: ''}};
assert(!modelRouteHasUnsavedChanges(), 'a global policy draft must not make the saved route dirty');
assert(Object.keys(modelRoutingPolicyChanges()).length === 1, 'policy draft still needs its own save');
AppState.modelRoutingPolicy.strategy = 'weighted';
assert(!modelRouteHasUnsavedChanges(), 'saved route and strategy must be testable');
AppState.modelRoutingPolicy.strategy_locked = true;
strategy.value = 'priority';
assert(!modelRouteHasUnsavedChanges(), 'environment-managed controls must not become writes');
"""
        )

    def test_responsive_route_controls_do_not_require_horizontal_scrolling(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")

        self.assertIn(".model-routing-policy-grid", styles)
        self.assertRegex(
            styles,
            r"(?s)@media \(max-width: 640px\).*?\.model-route-actions\s*\{.*?grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)",
        )


if __name__ == "__main__":
    unittest.main()
