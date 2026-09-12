"""Locale-aware number presentation contracts for the management console."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORMAT_SCRIPT = ROOT / "frontend/js/core/number-format.js"


class ConsoleNumberFormatTests(unittest.TestCase):
    def _run_contract(self, assertions: str) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the number-format contract.")
        harness = f"""
const fs = require('fs');
let locale = 'en-US';
globalThis.getActiveLocale = () => locale;
const source = fs.readFileSync({json.dumps(str(FORMAT_SCRIPT))}, 'utf8');
eval(source);
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

    def test_summary_numbers_compact_only_at_the_readability_threshold(self) -> None:
        self._run_contract(
            """
assert(formatConsoleNumber(9999, {compact: true}) === '9,999', 'small value was compacted');
assert(formatConsoleNumber(10000, {compact: true}) === '10K', 'threshold value was not compacted');
assert(formatConsoleNumber(1250000000, {compact: true}) === '1.25B', 'large value lost useful precision');
assert(formatConsoleNumber(1250000000) === '1,250,000,000', 'exact formatter changed detail values');
assert(formatConsoleNumber(12.345) === '12.345', 'exact formatter discarded a valid fraction');
assert(formatConsoleNumber(Number.NaN) === '0', 'invalid value did not use a safe zero');
locale = 'vi-VN';
const expectedVietnamese = new Intl.NumberFormat('vi-VN', {
    notation: 'compact', compactDisplay: 'short', maximumFractionDigits: 2
}).format(1250000000);
assert(formatConsoleNumber(1250000000, {compact: true}) === expectedVietnamese, 'compact value ignored the active locale');
delete globalThis.getActiveLocale;
assert(formatConsoleNumber(1000) === '1,000', 'formatter failed before locale initialization');
"""
        )

    def test_compact_metric_preserves_the_exact_accessible_value(self) -> None:
        self._run_contract(
            """
const attributes = {};
const element = {
    textContent: '', title: '',
    setAttribute(name, value) { attributes[name] = String(value); },
    removeAttribute(name) { delete attributes[name]; }
};
setCompactMetricValue(element, 1250000000);
assert(element.textContent === '1.25B', 'summary value was not compact');
assert(element.title === '1,250,000,000', 'exact hover value is missing');
assert(attributes['aria-label'] === '1,250,000,000', 'exact accessible value is missing');
setCompactMetricValue(element, 42);
assert(element.textContent === '42', 'small summary value changed');
assert(element.title === '', 'stale exact hover value remained');
assert(!('aria-label' in attributes), 'stale accessible value remained');
"""
        )

    def test_currency_keeps_small_cost_precision_and_compacts_large_totals(self) -> None:
        self._run_contract(
            """
assert(formatConsoleCurrency(0.0012) === '$0.0012', 'small cost lost precision');
assert(formatConsoleCurrency(1250000, {compact: true}) === '$1.25M', 'large cost was not compact');
assert(formatConsoleCurrency(-1) === '$0.00', 'negative cost did not use a safe zero');
"""
        )

    def test_console_surfaces_use_summary_or_detail_precision_consistently(self) -> None:
        dashboard = (ROOT / "frontend/js/features/dashboard.js").read_text(encoding="utf-8")
        playground = (ROOT / "frontend/js/features/playground.js").read_text(encoding="utf-8")
        traces = (ROOT / "frontend/js/features/traces.js").read_text(encoding="utf-8")
        virtual_keys = (ROOT / "frontend/js/features/virtual-keys.js").read_text(
            encoding="utf-8"
        )
        quotas = (ROOT / "frontend/js/ui/credential-dialogs.js").read_text(
            encoding="utf-8"
        )

        for element_id in (
            "totalApiCalls",
            "totalCostUsd",
            "totalTokens24h",
            "distInputTokens",
            "distOutputTokens",
            "distCachedTokens",
            "distReasoningTokens",
        ):
            self.assertIn(f"setDashboardSummaryMetric('{element_id}'", dashboard)
        self.assertIn("formatConsoleNumber(usage.input_tokens", playground)
        self.assertIn("formatConsoleNumber(trace.total_tokens)", traces)
        self.assertIn("return formatConsoleNumber(value, {maximumFractionDigits: 2})", virtual_keys)
        self.assertIn("return Number.isFinite(number) ? formatConsoleNumber(number)", quotas)


if __name__ == "__main__":
    unittest.main()
