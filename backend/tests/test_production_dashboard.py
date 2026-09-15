"""Production dashboard state, request-budget, and bounded-list contracts."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel.usage_routes import get_usage_stats, get_usage_stats_page

ROOT = BACKEND_DIR.parent
DASHBOARD_FRAGMENT = ROOT / "frontend/fragments/pages/dashboard.html"
DASHBOARD_SCRIPT = ROOT / "frontend/js/features/dashboard.js"
USAGE_PAGINATION_SCRIPT = ROOT / "frontend/js/features/usage-pagination.js"
DASHBOARD_STYLES = ROOT / "frontend/css/observability.css"
NUMBER_FORMAT_SCRIPT = ROOT / "frontend/js/core/number-format.js"


class ProductionDashboardContractTests(unittest.TestCase):
    def _source(self, path: Path) -> str:
        self.assertTrue(path.is_file(), f"Missing dashboard asset: {path}")
        return path.read_text(encoding="utf-8")

    def _run_state_contract(self, assertions: str) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the dashboard state contract.")
        harness = f"""
const fs = require('fs');
const vm = require('vm');
const numberSource = fs.readFileSync({json.dumps(str(NUMBER_FORMAT_SCRIPT))}, 'utf8');
const source = fs.readFileSync({json.dumps(str(DASHBOARD_SCRIPT))}, 'utf8');
const paginationSource = fs.readFileSync({json.dumps(str(USAGE_PAGINATION_SCRIPT))}, 'utf8');
vm.runInThisContext(numberSource);
vm.runInThisContext(paginationSource);
vm.runInThisContext(source + `\n;globalThis.__renderDashboardTimeline = renderTimelineChart;`);
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

    def test_primary_dashboard_surfaces_match_the_production_information_order(self):
        fragment = self._source(DASHBOARD_FRAGMENT)

        for element_id in (
            "totalCostUsd",
            "pricingSourceDetail",
            "dashboardP95Latency",
            "recentActivityList",
        ):
            self.assertIn(f'id="{element_id}"', fragment)
        for removed_surface in (
            "dashboardReadiness",
            "dashboardQuickActions",
            "sloSampleNotice",
            "sloPrometheusStatus",
            "sloOtelStatus",
        ):
            self.assertNotIn(f'id="{removed_surface}"', fragment)
        self.assertNotIn('data-i18n="slo.kicker"', fragment)
        self.assertNotIn("Service objectives", fragment)
        self.assertNotIn("slo-export-status", fragment)
        self.assertNotIn("dashboard-readiness", fragment)
        self.assertIn("renderPricingSource(aggData.pricing)", self._source(DASHBOARD_SCRIPT))
        self.assertLess(
            fragment.index('id="operationalHealthCard"'), fragment.index('id="providerHealthCard"')
        )

    def test_stale_dashboard_refresh_cannot_replace_metrics_or_finish_newer_refresh(self):
        self._run_state_contract("""
const elements = new Map(), statuses = [], secondary = [], details = [], renders = [];
globalThis.document = {getElementById: id => {
    if (!elements.has(id)) elements.set(id, {hidden: false, dataset: {}, textContent: '',
        innerHTML: '', setAttribute(name, value) {this[name] = value;}, closest() {return this;}});
    return elements.get(id);
}};
globalThis.AppState = {usagePeriod: '1d', usageStatsLoaded: false};
globalThis.t = key => key;
globalThis.getAuthHeaders = () => ({});
globalThis.clearPageState = () => {};
globalThis.showPageState = () => statuses.push('page-error');
globalThis.showStatus = () => statuses.push('status');
updateUsagePeriodLabels = () => {};
setDashboardTrafficState = () => {};
setDashboardSummaryMetric = (id, value) => {document.getElementById(id).textContent = String(value);};
formatUsageNumber = String;
renderPricingSource = () => {};
renderTokenDistribution = () => {};
renderProviderHealthMatrix = () => renders.push('providers');
renderUsageList = () => renders.push('usage');
refreshOperationalHealth = async () => secondary.push('health');
refreshRecentActivity = async () => secondary.push('activity');
loadUsagePages = async () => {details.push(AppState.usagePeriod); return true;};
const defer = () => {let resolve, reject; const promise = new Promise((yes, no) => {
    resolve = yes; reject = no;
}); return {promise, resolve, reject};};
const response = calls => ({ok: true, json: async () => ({success: true, data: {total_calls: calls}})});
(async () => {
    for (const failure of [false, true]) {
        AppState.usagePeriod = '1d';
        const oldResponse = defer();
        globalThis.fetch = () => oldResponse.promise;
        const oldRefresh = refreshUsageStats();
        AppState.usagePeriod = '7d';
        globalThis.fetch = async () => response(70);
        await refreshUsageStats();
        const detailCount = details.length, secondaryCount = secondary.length;
        const statusCount = statuses.length, renderCount = renders.length;
        if (failure) oldResponse.reject(new Error('outdated failure'));
        else oldResponse.resolve(response(1));
        await oldRefresh;
        assert(AppState.dashboardAggregate.total_calls === 70, 'Old aggregate overwrote current period');
        assert(document.getElementById('totalApiCalls').textContent === '70', 'Old metric was rendered');
        assert(details.length === detailCount, 'Stale aggregate started a detail query');
        assert(secondary.length === secondaryCount, 'Stale finally launched secondary queries');
        assert(statuses.length === statusCount, 'Stale failure displayed an error');
        assert(renders.length === renderCount, 'Stale refresh rendered a table');
    }
    // The generation guard also protects overlapping refreshes of the same period.
    const oldDetails = defer(), detailStarted = defer(), newResponse = defer();
    loadUsagePages = async () => {detailStarted.resolve(); return oldDetails.promise;};
    globalThis.fetch = async () => response(70);
    const oldRefresh = refreshUsageStats({preserveContent: false});
    await detailStarted.promise;
    globalThis.fetch = () => newResponse.promise;
    const newRefresh = refreshUsageStats({preserveContent: false});
    const secondaryCount = secondary.length, renderCount = renders.length;
    oldDetails.resolve(true);
    await oldRefresh;
    assert(renders.length === renderCount, 'Old detail completion rendered after a newer refresh began');
    assert(secondary.length === secondaryCount, 'Old detail completion started secondary refresh');
    assert(document.getElementById('dashboardStats')['aria-busy'] === 'true', 'Old finally cleared newer busy state');
    assert(!document.getElementById('usageLoading').hidden, 'Old finally hid newer loading indicator');
    loadUsagePages = async () => true;
    newResponse.resolve(response(71));
    await newRefresh;
    assert(AppState.dashboardAggregate.total_calls === 71, 'Latest refresh did not complete');
})().catch(error => {console.error(error); process.exitCode = 1;});
""")

    def test_zero_traffic_uses_a_guided_first_run_state(self):
        fragment = self._source(DASHBOARD_FRAGMENT)
        source = self._source(DASHBOARD_SCRIPT)

        self.assertIn('id="dashboardFirstRun"', fragment)
        self.assertIn('class="stat-item dashboard-traffic-only"', fragment)
        self.assertIn('class="card span-12 chart-card dashboard-traffic-only"', fragment)
        self.assertIn("setDashboardTrafficState(totalCalls)", source)

    def test_dashboard_load_has_a_fixed_request_budget_and_bounded_lists(self):
        source = self._source(DASHBOARD_SCRIPT)
        pagination = self._source(USAGE_PAGINATION_SCRIPT)

        self.assertEqual(len(re.findall(r"\bfetch\(", source)), 3)
        self.assertEqual(len(re.findall(r"\bfetch\(", pagination)), 1)
        self.assertIn("['current', 'historical'].map", pagination)
        self.assertIn("./api/usage/stats/page?", pagination)
        self.assertIn("page_size: size || 10", pagination)
        self.assertIn("await loadUsagePages()", source)
        self.assertIn("./api/traces?page_size=5", source)
        self.assertIn("routes.slice(0, 10)", source)
        self.assertIn("traces.slice(0, DASHBOARD_RECENT_ACTIVITY_PAGE_SIZE)", source)

    def test_empty_guidance_prioritizes_provider_connection_only_for_an_empty_pool(self):
        self._run_state_contract("""
const elements = new Map();
globalThis.document = {getElementById: id => {
    if (!elements.has(id)) elements.set(id, {hidden: false, dataset: {}, classList: {toggle() {}}, textContent: ''});
    return elements.get(id);
}};
globalThis.t = key => key;
globalThis.AppState = {dashboardAggregate: {total_files: 0}};
setDashboardTrafficState(0);
assert(elements.get('dashboardStartAction').dataset.tab === 'providers', 'Empty pool must start with providers');
AppState.dashboardAggregate.total_files = 2;
setDashboardTrafficState(0);
assert(elements.get('dashboardStartAction').dataset.tab === 'playground', 'Existing credentials must not be described as a fresh install');
setDashboardTrafficState(4);
assert(elements.get('dashboardFirstRun').hidden, 'Populated traffic hides guidance');
""")

    def test_health_without_samples_does_not_claim_zero_latency_or_error_rate(self):
        self._run_state_contract("""
const elements = new Map();
globalThis.document = {getElementById: id => {
    if (!elements.has(id)) elements.set(id, {hidden: false, textContent: '', dataset: {}, setAttribute() {},
        querySelector() { return {textContent: ''}; }, replaceChildren() {},
        insertRow() { return {insertCell() {return {};}, dataset: {}}; }});
    return elements.get(id);
}};
globalThis.AppState = {};
document.querySelector = () => ({textContent: ''});
globalThis.getAuthHeaders = () => ({});
globalThis.t = key => key;
globalThis.getActiveLocale = () => 'vi-VN';
globalThis.setDashboardSummaryMetric = (id, value) => { document.getElementById(id).textContent = String(value); };
globalThis.fetch = async () => ({ok: true, json: async () => ({status: 'no_data', red: {requests: 0, p95_duration_ms: 0}, routes: []})});
(async () => {
    await refreshOperationalHealth();
    assert(elements.get('sloP95').textContent === '—', 'No samples cannot mean 0 ms');
    assert(elements.get('sloErrorRate').textContent === '—', 'No samples cannot mean 0% errors');
    assert(!elements.get('operationalHealthEmpty').hidden, 'Show compact no-sample explanation');
    globalThis.fetch = async () => ({ok: false, status: 503});
    await refreshOperationalHealth();
    assert(elements.get('operationalHealthEmpty').textContent === 'slo.load_failed', 'Unavailable is not empty or critical traffic');
})().catch(error => { console.error(error); process.exitCode = 1; });
""")

    def test_primary_metrics_precede_secondary_dashboard_queries(self):
        source = self._source(DASHBOARD_SCRIPT)
        refresh_body = source.split("async function refreshUsageStats", 1)[1].split(
            "function setOperationalHealthStatus", 1
        )[0]

        aggregate_fetch = refresh_body.index("const aggregatedResponse = await fetch")
        detail_fetch = refresh_body.index("await loadUsagePages()")
        self.assertLess(aggregate_fetch, detail_fetch)
        self.assertLess(detail_fetch, refresh_body.index("void refreshOperationalHealth();"))
        self.assertLess(detail_fetch, refresh_body.index("void refreshRecentActivity();"))
        self.assertNotIn("renderDashboardReadiness", source)

    def test_dashboard_tables_fit_their_cards_without_horizontal_scrolling(self):
        fragment = self._source(DASHBOARD_FRAGMENT)
        styles = self._source(ROOT / "frontend/css/forms-and-data.css")
        responsive = self._source(ROOT / "frontend/css/responsive.css")

        self.assertIn('class="usage-table slo-route-table"', fragment)
        self.assertRegex(
            styles,
            r"(?s)\.usage-table-wrapper\s*\{[^}]*overflow:\s*hidden;",
        )
        self.assertRegex(
            styles,
            r"(?s)\.usage-table\s*\{[^}]*min-width:\s*0;[^}]*table-layout:\s*fixed;",
        )
        self.assertNotIn("min-width: 640px", styles)
        self.assertRegex(
            styles,
            r"(?s)\.health-matrix-legend,\s*\.chart-legend\s*\{[^}]*flex-wrap:\s*wrap;",
        )
        self.assertIn(".usage-table:not(.slo-route-table) tr", responsive)
        self.assertIn(".timeline-bar-col:first-child .timeline-tooltip", styles)
        self.assertIn(".timeline-bar-col:last-child .timeline-tooltip", styles)

    def test_dashboard_header_collapses_at_the_tablet_breakpoint(self):
        styles = self._source(DASHBOARD_STYLES)

        self.assertRegex(
            styles,
            r"(?s)@media \(max-width: 960px\).*?#dashboardTab \.page-header\s*\{\s*display: grid;",
        )

    def test_empty_timeline_reports_zero_peak_requests(self):
        self._run_state_contract(
            """
const wrapper = { innerHTML: '' };
const maxInfo = { textContent: '' };
globalThis.document = { getElementById: (id) => id === 'timelineBarsWrapper' ? wrapper : maxInfo };
globalThis.t = (_key, values = {}) => String(values.count ?? '');
globalThis.escapeHtml = (value) => String(value);
globalThis.escapeAttribute = (value) => String(value);
globalThis.getActiveLocale = () => 'en-US';
globalThis.__renderDashboardTimeline([{ requests: 0, successful_requests: 0, failed_requests: 0, tokens: 0 }]);
assert(maxInfo.textContent === '0', `zero traffic peak: received ${maxInfo.textContent}`);
"""
        )

    def test_token_distribution_does_not_count_cached_input_twice(self):
        source = self._source(DASHBOARD_SCRIPT)

        self.assertIn(
            "const uncachedInputTokens = Math.max(inputTokens - cachedTokens, 0);", source
        )
        self.assertIn(
            "const totalCalculated = uncachedInputTokens + outputTokens + cachedTokens + reasoningTokens;",
            source,
        )

    def test_usage_summary_labels_provider_attempts_separately_from_logical_requests(self):
        fragment = self._source(DASHBOARD_FRAGMENT)
        source = self._source(DASHBOARD_SCRIPT)

        self.assertIn('data-i18n="dashboard.attempt_success_rate"', fragment)
        self.assertIn("dashboard.provider_attempts_period", source)
        self.assertIn("aggData.total_upstream_attempts", source)

    def test_timeline_uses_browser_timezone_and_fixed_axis_boundaries(self):
        fragment = self._source(DASHBOARD_FRAGMENT)
        source = self._source(DASHBOARD_SCRIPT)

        self.assertIn("timezone_offset_minutes", source)
        self.assertIn("new Date().getTimezoneOffset()", source)
        self.assertIn("updateTimelineAxisLabels(timeline)", source)
        self.assertIn('id="timelineStartLabel"', fragment)
        self.assertIn('id="timelineMidLabel"', fragment)
        self.assertIn('id="timelineNowLabel"', fragment)
        self.assertIn("formatTimelineTimestamp(last.timestamp)", source)
        self.assertNotIn("`${startTime}–${endTime}`", source)


class BoundedUsageDashboardApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_usage_stats_returns_only_the_requested_bounded_page(self):
        rows = {
            "low.json": {"calls": 1},
            "high.json": {"calls": 9},
            "middle.json": {"calls": 4},
        }
        with patch(
            "core.panel.usage_routes.get_stats_for_period",
            new=AsyncMock(return_value=rows),
        ) as stats:
            response = await get_usage_stats_page(
                period="1d", timezone_offset_minutes=-420, page_size=2, token="panel"
            )
            legacy = await get_usage_stats(period="1d", timezone_offset_minutes=-420, token="panel")

        self.assertEqual(legacy["data"], rows)

        self.assertEqual(list(response["data"]), ["high.json", "middle.json"])
        self.assertEqual(response["page_size"], 2)
        self.assertEqual(response["total_items"], 3)
        self.assertTrue(response["has_more"])
        self.assertEqual(stats.await_args_list[0].args, ("1d", -420))
        self.assertEqual(stats.await_args_list[1].args, ("1d", -420))


if __name__ == "__main__":
    unittest.main()
