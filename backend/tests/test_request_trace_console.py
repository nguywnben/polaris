"""Static security, privacy, and interaction contracts for request trace observability."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel.root import serve_control_panel

ROOT = BACKEND_DIR.parent
TRACE_SCRIPT = (ROOT / "frontend" / "js" / "features" / "traces.js").read_text(encoding="utf-8")
TRACE_STYLE = (ROOT / "frontend" / "css" / "observability.css").read_text(encoding="utf-8")


class RequestTraceConsoleContractTests(unittest.TestCase):
    def test_observability_surface_separates_traces_from_raw_logs(self):
        body = serve_control_panel().body.decode("utf-8")
        for element_id in (
            "traceFilterForm",
            "traceList",
            "traceRetentionForm",
            "traceDetailDialog",
            "traceDecisionList",
            "logContainer",
        ):
            self.assertIn(f'id="{element_id}"', body)
        self.assertLess(body.index('id="traceList"'), body.index('id="activityRuntimePanel"'))
        self.assertIn('data-activity-view="traces"', body)
        self.assertIn('data-activity-view="runtime"', body)
        self.assertIn('data-i18n="trace.content_free_description"', body)
        self.assertIn('data-i18n="trace.diagnostic_only"', body)

    def test_client_uses_bounded_authenticated_server_contracts(self):
        for endpoint in (
            "./api/traces?",
            "./api/traces/retention",
            "./api/traces/export?",
            "./api/traces/${encodeURIComponent(traceId)}",
        ):
            self.assertIn(endpoint, TRACE_SCRIPT)
        self.assertIn("abortController", TRACE_SCRIPT)
        self.assertIn("cursorStack", TRACE_SCRIPT)
        self.assertIn("next_cursor", TRACE_SCRIPT)
        self.assertIn("TRACE_EXPORT_FILENAME_PATTERN", TRACE_SCRIPT)
        self.assertIn("URL.revokeObjectURL", TRACE_SCRIPT)

    def test_untrusted_records_are_closed_schema_and_text_only(self):
        for field in (
            "schema_version",
            "trace_id",
            "request_id",
            "protocol",
            "outcome",
            "decisions",
            "decisions_truncated",
            "category",
            "action",
            "result",
            "reason",
        ):
            self.assertIn(f"'{field}'", TRACE_SCRIPT)
        self.assertIn("traceExactFields", TRACE_SCRIPT)
        self.assertIn("textContent", TRACE_SCRIPT)
        self.assertNotIn("innerHTML", TRACE_SCRIPT)
        for forbidden in ("prompt", "response_body", "api_key", "raw_secret", "exception_text"):
            self.assertNotIn(forbidden, TRACE_SCRIPT)

    def test_only_low_risk_filters_are_persisted(self):
        block = TRACE_SCRIPT.split("function persistTraceSafeFilters", 1)[1].split(
            "function restoreTraceSafeFilters", 1
        )[0]
        for safe in ("protocols", "page_size"):
            self.assertIn(safe, block)
        for transient in (
            "providers",
            "outcomes",
            "models",
            "request_id",
            "started_after",
            "started_before",
            "cursor",
        ):
            self.assertNotIn(transient, block)

    def test_observability_layout_is_responsive_and_keyboard_visible(self):
        self.assertIn(".trace-layout", TRACE_STYLE)
        self.assertIn(".raw-log-section", TRACE_STYLE)
        self.assertIn("@media (max-width: 760px)", TRACE_STYLE)
        self.assertIn(":focus-visible", TRACE_STYLE)

    def test_empty_trace_stream_hides_irrelevant_pagination(self):
        body = serve_control_panel().body.decode("utf-8")

        self.assertIn('class="trace-pagination" hidden', body)
        self.assertIn("pagination.hidden = !TraceConsoleState.traces.length", TRACE_SCRIPT)


if __name__ == "__main__":
    unittest.main()
