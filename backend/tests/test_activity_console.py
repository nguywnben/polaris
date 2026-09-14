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
            ('traces.js', 'TraceConsoleState', 'renderTraces', 'traceList'),
            ('audit.js', 'AuditConsoleState', 'renderAuditEvents', 'auditEventList'),
        ):
            source = (FRONTEND / 'js/features' / feature).read_text(encoding='utf-8')
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
            result = subprocess.run([shutil.which('node'), '-e', harness], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
