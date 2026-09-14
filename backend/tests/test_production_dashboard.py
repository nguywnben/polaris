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
vm.runInThisContext(numberSource);
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

    def test_zero_traffic_uses_a_guided_first_run_state(self):
        fragment = self._source(DASHBOARD_FRAGMENT)
        source = self._source(DASHBOARD_SCRIPT)

        self.assertIn('id="dashboardFirstRun"', fragment)
        self.assertIn('class="stat-item dashboard-traffic-only"', fragment)
        self.assertIn('class="card span-12 chart-card dashboard-traffic-only"', fragment)
        self.assertIn("setDashboardTrafficState(totalCalls)", source)

    def test_dashboard_load_has_a_fixed_request_budget_and_bounded_lists(self):
        source = self._source(DASHBOARD_SCRIPT)

        self.assertEqual(len(re.findall(r"\bfetch\(", source)), 4)
        self.assertIn("./api/usage/stats/page?", source)
        self.assertIn("page_size=100", source)
        self.assertIn("./api/traces?page_size=5", source)
        self.assertIn("routes.slice(0, 10)", source)
        self.assertIn("traces.slice(0, DASHBOARD_RECENT_ACTIVITY_PAGE_SIZE)", source)

    def test_primary_metrics_precede_secondary_dashboard_queries(self):
        source = self._source(DASHBOARD_SCRIPT)
        refresh_body = source.split("async function refreshUsageStats", 1)[1].split(
            "function setOperationalHealthStatus", 1
        )[0]

        aggregate_fetch = refresh_body.index("const aggregatedResponse = await fetch")
        detail_fetch = refresh_body.index("const statsResponse = await fetch")
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
