"""Unified Activity workflow contracts for the production console."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel.root import serve_control_panel

ROOT = BACKEND_DIR.parent
FRONTEND = ROOT / "frontend"
ACTIVITY_SCRIPT = FRONTEND / "js/features/activity.js"
ACTIVITY_STYLE = FRONTEND / "css/observability.css"


class ActivityConsoleContractTests(unittest.TestCase):
    def _run_empty_state_contract(self, feature: str, assertions: str) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the Activity empty-state contract")
        source = (FRONTEND / "js/features" / feature).read_text(encoding="utf-8")
        harness = f"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const elements = new Map();
function element(id) {{
    if (!elements.has(id)) elements.set(id, {{
        value: '', textContent: '', children: [], dataset: {{}},
        replaceChildren() {{ this.children = []; }},
        append(...nodes) {{ this.children.push(...nodes); }},
        setAttribute() {{}}, closest() {{ return null; }}
    }});
    return elements.get(id);
}}
global.document = {{addEventListener() {{}}, getElementById: element,
    createElement() {{ return {{textContent: '', dataset: {{}}}}; }} }};
global.window = {{location: {{href: 'http://localhost/activity'}}}};
global.WebSocket = class {{ static OPEN = 1; constructor(url) {{ this.url = url; this.readyState = 0; }} }};
global.AppState = {{allLogs: [], filteredLogs: [], currentLogFilter: 'all', logWebSocket: null}};
global.t = key => key;
global.getAuthHeaders = () => ({{}});
global.showStatus = () => {{}};
global.showConfirmModal = async () => true;
global.fetch = async () => {{ throw new Error('Unexpected network request'); }};
vm.runInThisContext({json.dumps(source)});
(async () => {{
{assertions}
}})().catch(error => {{console.error(error); process.exitCode = 1;}});
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

    def test_trace_first_empty_state_uses_applied_filters_not_unsubmitted_fields(self):
        self._run_empty_state_contract(
            "traces.js",
            """
TraceConsoleState.loaded = true;
TraceConsoleState.filters = {
    protocols: [], outcomes: [], providers: [], models: [], request_id: '',
    started_after: '', started_before: '', page_size: 200
};
element('traceProtocol').value = 'openai_chat';
element('traceModel').value = 'draft-model';
element('activityRequestId').value = 'draft-request';
element('activityProvider').value = 'draft-provider';
renderTraces();
assert.equal(element('traceList').children.length, 1);
assert.equal(element('traceList').children[0].textContent, 'dashboard.recent_empty',
    'first empty response needs a no-requests message even when unapplied fields contain drafts');
TraceConsoleState.filters = {};
renderTraces();
assert.equal(element('traceList').children[0].textContent, 'dashboard.recent_empty');
""",
        )

    def test_trace_filtered_or_later_page_empty_state_retains_filter_message(self):
        self._run_empty_state_contract(
            "traces.js",
            """
TraceConsoleState.loaded = true;
for (const filters of [
    {protocols: ['openai_chat']}, {outcomes: ['succeeded']}, {providers: ['openai']},
    {models: ['test-model']}, {request_id: 'req-missing'},
    {started_after: '2026-09-15T00:00:00Z'}, {started_before: '2026-09-16T00:00:00Z'}
]) {
    TraceConsoleState.filters = filters;
    renderTraces();
    assert.equal(element('traceList').children[0]?.textContent, 'trace.empty',
        `applied ${Object.keys(filters)[0]} filter must explain no matching results`);
}
TraceConsoleState.filters = {};
for (const [cursor, stack] of [['opaque-cursor', []], [null, [null]]]) {
    TraceConsoleState.cursor = cursor;
    TraceConsoleState.cursorStack = stack;
    renderTraces();
    assert.equal(element('traceList').children[0]?.textContent, 'trace.empty',
        'an empty later page must not claim no requests have ever been recorded');
}
""",
        )

    def test_trace_loading_and_errors_suppress_both_empty_messages(self):
        self._run_empty_state_contract(
            "traces.js",
            """
for (const filters of [{}, {request_id: 'req-missing'}]) {
    TraceConsoleState.filters = filters;
    for (const [loaded, loading, error] of [[false, false, false], [true, true, false], [true, false, true]]) {
        TraceConsoleState.loaded = loaded;
        TraceConsoleState.loading = loading;
        TraceConsoleState.loadError = error;
        renderTraces();
        assert.equal(element('traceList').children.length, 0, 'only successful completed loads may announce empty results');
    }
}
""",
        )

    def test_log_connection_and_default_reset_do_not_claim_logs_were_cleared(self):
        self._run_empty_state_contract(
            "logs.js",
            """
AppState.allLogs = ['previous display line'];
AppState.filteredLogs = ['previous display line'];
connectWebSocket();
assert.equal(typeof AppState.logWebSocket.onopen, 'function');
AppState.logWebSocket.onopen();
assert.equal(element('logContent').textContent, 'no_logs_yet',
    'opening the stream must not announce a user clear operation');
assert.equal(AppState.allLogs.length, 0);
assert.equal(AppState.filteredLogs.length, 0);
element('logContent').textContent = 'stale display';
clearLogsDisplay();
assert.equal(element('logContent').textContent, 'no_logs_yet', 'the default display reset must be neutral');
""",
        )

    def test_only_successful_confirmed_log_clear_announces_cleared_state(self):
        self._run_empty_state_contract(
            "logs.js",
            """
let requests = 0;
global.fetch = async () => { requests++; return {ok: false, json: async () => ({})}; };
element('logContent').textContent = 'retained display';
AppState.allLogs = ['retained display'];
global.showConfirmModal = async () => false;
await clearLogs();
assert.equal(requests, 0);
assert.equal(element('logContent').textContent, 'retained display');
global.showConfirmModal = async () => true;
await clearLogs();
assert.equal(requests, 1);
assert.equal(element('logContent').textContent, 'retained display', 'failed server clear must preserve displayed logs');
global.fetch = async (url, options) => {
    assert.equal(url, './api/logs/clear');
    assert.equal(options.method, 'POST');
    return {ok: true, json: async () => ({message: 'done'})};
};
await clearLogs();
assert.equal(element('logContent').textContent, 'logs_cleared_waiting_for_new_logs');
assert.equal(AppState.allLogs.length, 0);
""",
        )

    def _run_javascript_contract(self, assertions: str) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the Activity behavior contract.")
        source = ACTIVITY_SCRIPT.read_text(encoding="utf-8")
        harness = f"""
const vm = require('vm');
global.document = {{ addEventListener() {{}}, getElementById() {{ return null; }} }};
global.window = {{ location: {{pathname: '/activity', search: ''}} }};
global.history = {{ pushState() {{}} }};
global.AppState = {{activeActivityView: 'traces'}};
global.triggerTabDataLoad = async () => undefined;
global.t = (key) => key;
vm.runInThisContext({json.dumps(source)});
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

    def test_shared_filters_have_one_semantic_owner(self) -> None:
        body = serve_control_panel().body.decode("utf-8")
        activity = (FRONTEND / "fragments/pages/activity.html").read_text(encoding="utf-8")
        traces = (FRONTEND / "fragments/pages/logs.html").read_text(encoding="utf-8")
        audit = (FRONTEND / "fragments/pages/audit.html").read_text(encoding="utf-8")

        for element_id in (
            "activityFilterForm",
            "activityStartedAfter",
            "activityStartedBefore",
            "activityOutcome",
            "activityProvider",
            "activityActorType",
            "activityRequestId",
            "activityFilterStatus",
        ):
            self.assertIn(f'id="{element_id}"', activity)
            self.assertEqual(body.count(f'id="{element_id}"'), 1)

        for obsolete_id in (
            "traceOutcome",
            "traceProvider",
            "traceRequestId",
            "traceStartedAfter",
            "traceStartedBefore",
        ):
            self.assertNotIn(f'id="{obsolete_id}"', traces)
        for obsolete_id in (
            "auditOutcome",
            "auditActorType",
            "auditRequestId",
            "auditOccurredAfter",
            "auditOccurredBefore",
        ):
            self.assertNotIn(f'id="{obsolete_id}"', audit)
        self.assertIn('pattern="[A-Za-z0-9._:\\-]{1,128}"', activity)

    def test_common_outcomes_map_to_each_bounded_backend_contract(self) -> None:
        self._run_javascript_contract(
            """
const failed = normalizeActivityFilters({
    started_after: '', started_before: '', outcome: 'failed', provider: 'openai',
    actor_type: 'local_owner', request_id: 'req-correlated'
});
assert(failed !== null, 'valid common filters rejected');
const trace = mergeActivityTraceFilters({protocols: [], outcomes: [], providers: [], models: []}, failed);
assert(trace.request_id === 'req-correlated', 'trace request ID missing');
assert(trace.providers[0] === 'openai', 'trace provider missing');
assert(trace.outcomes.includes('upstream_error') && trace.outcomes.includes('internal_error'), 'trace failure mapping incomplete');
const audit = mergeActivityAuditFilters({actions: [], outcomes: [], actor_types: [], target_types: []}, failed);
assert(audit.request_id === 'req-correlated', 'audit request ID missing');
assert(audit.actor_types[0] === 'local_owner', 'audit actor missing');
assert(audit.outcomes.includes('failed') && audit.outcomes.includes('timed_out'), 'audit failure mapping incomplete');
assert(activityViewFromLocation('/logs', '') === 'runtime', 'logs alias must select runtime logs');
assert(normalizeActivityFilters({...failed, request_id: 'bad request'}) === null, 'unsafe request ID accepted');
assert(investigateActivityRequest('req-p4.5-correlated', 'audit') === true, 'request pivot rejected');
assert(ActivityFilterState.filters.request_id === 'req-p4.5-correlated', 'request pivot lost correlation ID');
assert(AppState.activeActivityView === 'audit', 'request pivot did not select target view');
"""
        )

    def test_request_pivots_cross_views_and_dashboard_opens_the_trace(self) -> None:
        activity = ACTIVITY_SCRIPT.read_text(encoding="utf-8")
        traces = (FRONTEND / "js/features/traces.js").read_text(encoding="utf-8")
        audit = (FRONTEND / "js/features/audit.js").read_text(encoding="utf-8")
        dashboard = (FRONTEND / "js/features/dashboard.js").read_text(encoding="utf-8")
        bindings = (FRONTEND / "js/features/navigation.js").read_text(encoding="utf-8")

        self.assertIn("function investigateActivityRequest", activity)
        self.assertIn("investigateActivityRequest(trace.request_id, 'audit')", traces)
        self.assertIn("investigateActivityRequest(event.request_id, 'traces')", audit)
        self.assertIn('data-ui-action="investigate-activity-request"', dashboard)
        self.assertIn("'investigate-activity-request'", bindings)
        self.assertIn("'related-audit-request'", bindings)
        self.assertIn("'related-trace-request'", bindings)

    def test_runtime_log_filter_uses_the_shared_correlation_contract(self) -> None:
        activity = ACTIVITY_SCRIPT.read_text(encoding="utf-8")
        logs = (FRONTEND / "js/features/logs.js").read_text(encoding="utf-8")

        self.assertIn("function activityLogLineMatches", activity)
        self.assertIn("activityLogLineMatches(log)", logs)
        self.assertIn("MAX_ACTIVITY_LOG_FILTER_LENGTH", activity)

    def test_activity_uses_a_compact_two_row_filter_and_flat_tabs(self) -> None:
        activity = (FRONTEND / "fragments/pages/activity.html").read_text(encoding="utf-8")
        styles = ACTIVITY_STYLE.read_text(encoding="utf-8")

        for field_class in (
            "activity-filter-time",
            "activity-filter-outcome",
            "activity-filter-provider",
            "activity-filter-actor",
            "activity-filter-request",
        ):
            self.assertIn(field_class, activity)
        self.assertIn('data-i18n="activity.from_time"', activity)
        self.assertIn('data-i18n="activity.to_time"', activity)
        self.assertIn("grid-template-columns: repeat(12, minmax(0, 1fr))", styles)
        self.assertIn("border-bottom: 1px solid var(--border)", styles)
        self.assertIn("background: transparent", styles)

    def test_operational_retention_is_configured_from_settings(self) -> None:
        traces = (FRONTEND / "fragments/pages/logs.html").read_text(encoding="utf-8")
        audit = (FRONTEND / "fragments/pages/audit.html").read_text(encoding="utf-8")
        settings = (FRONTEND / "fragments/pages/settings.html").read_text(encoding="utf-8")

        for form_id in ("traceRetentionForm", "auditRetentionForm"):
            self.assertNotIn(f'id="{form_id}"', traces)
            self.assertNotIn(f'id="{form_id}"', audit)
            self.assertEqual(settings.count(f'id="{form_id}"'), 1)

    def test_load_errors_never_render_as_empty_results(self) -> None:
        for feature, state, render, list_id in (
            ("traces.js", "TraceConsoleState", "renderTraces", "traceList"),
            ("audit.js", "AuditConsoleState", "renderAuditEvents", "auditEventList"),
        ):
            source = (FRONTEND / "js/features" / feature).read_text(encoding="utf-8")
            harness = f"""
const vm = require('vm');
const items = [];
global.document = {{addEventListener() {{}}, getElementById(id) {{
    return id === '{list_id}' ? {{replaceChildren() {{items.length = 0;}}, append(item) {{items.push(item);}}}} : null;
}}, createElement() {{return {{}};}}}};
global.t = key => key;
vm.runInThisContext({json.dumps(source)});
{state}.loaded = true;
{state}.loadError = true;
{render}();
if (items.length) throw new Error('Load failure must not render an empty-result message');
{state}.loadError = false;
{state}.loading = true;
{render}();
if (items.length) throw new Error('Loading must not render an empty-result message');
{state}.loading = false;
{render}();
if (items.length !== 1) throw new Error('Successful empty response needs an empty message');
"""
            result = subprocess.run(
                [shutil.which("node"), "-e", harness], capture_output=True, text=True, timeout=15
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
