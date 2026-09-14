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

    def test_unsaved_global_strategy_blocks_handoff_until_it_is_saved(self) -> None:
        self._run_contract(
            """
const strategy = {value: 'weighted'};
global.document = {getElementById: id => id === 'modelRoutingStrategy' ? strategy : null};
global.AppState = {selectedModels: ['healthy'], savedModelSelection: ['healthy'],
    modelRoutingPolicy: {strategy: 'balanced', preferred_provider: ''}};
assert(modelRouteHasUnsavedChanges(), 'strategy-only edits must block a saved-route handoff');
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
