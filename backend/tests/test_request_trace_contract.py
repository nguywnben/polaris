"""Versioned, bounded, content-free request trace contract tests."""

from __future__ import annotations

import json
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.request_trace import (
    REQUEST_TRACE_SCHEMA_VERSION,
    RequestDecision,
    RequestTrace,
    RequestTraceQuery,
    RequestTraceRetentionPolicy,
    classify_request_protocol,
    request_trace_from_record,
)


class RequestTraceContractTests(unittest.TestCase):
    def _trace(self) -> RequestTrace:
        started = datetime(2026, 8, 25, 1, 2, 3, tzinfo=timezone.utc)
        return RequestTrace(
            schema_version=REQUEST_TRACE_SCHEMA_VERSION,
            trace_id="a" * 32,
            request_id="req-safe-123",
            protocol="openai_chat",
            started_at=started.isoformat(),
            completed_at=(started + timedelta(milliseconds=125)).isoformat(),
            outcome="succeeded",
            status_code=200,
            duration_ms=125,
            requested_model="gpt-5",
            selected_provider="openai",
            input_tokens=120,
            output_tokens=30,
            total_tokens=150,
            cost_usd=0.0025,
            decisions=(
                RequestDecision(
                    sequence=1,
                    elapsed_ms=3,
                    category="routing",
                    action="selected",
                    result="succeeded",
                    reason="healthy_candidate",
                    provider="openai",
                    model="gpt-5",
                    candidate_count=3,
                ),
                RequestDecision(
                    sequence=2,
                    elapsed_ms=125,
                    category="outcome",
                    action="completed",
                    result="succeeded",
                    reason="completed",
                    status_code=200,
                ),
            ),
        )

    def test_exact_round_trip_shape_has_no_content_or_secret_fields(self):
        trace = self._trace()
        record = trace.to_record()

        self.assertEqual(request_trace_from_record(record), trace)
        self.assertEqual(
            set(record),
            {
                "schema_version",
                "trace_id",
                "request_id",
                "protocol",
                "started_at",
                "completed_at",
                "outcome",
                "status_code",
                "duration_ms",
                "requested_model",
                "selected_provider",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "cost_usd",
                "decisions",
                "decisions_truncated",
            },
        )
        serialized = json.dumps(record).lower()
        for forbidden in ("prompt", "response_body", "authorization", "api_key", "secret"):
            self.assertNotIn(forbidden, serialized)

    def test_unexpected_fields_and_free_text_fail_closed(self):
        record = self._trace().to_record()
        record["prompt"] = "private customer content"
        with self.assertRaises(ValueError):
            request_trace_from_record(record)

        invalid_decision = self._trace().to_record()
        invalid_decision["decisions"][0]["reason"] = "customer said something private"
        with self.assertRaises(ValueError):
            request_trace_from_record(invalid_decision)

    def test_decisions_and_numeric_cardinality_are_bounded(self):
        with self.assertRaises(ValueError):
            RequestDecision(
                sequence=1,
                elapsed_ms=0,
                category="routing",
                action="selected",
                result="succeeded",
                reason="healthy_candidate",
                candidate_count=10001,
            )
        trace = self._trace()
        with self.assertRaises(ValueError):
            replace(trace, decisions=trace.decisions * 33)

    def test_protocol_classifier_covers_supported_inference_surfaces(self):
        matrix = {
            "/v1/chat/completions": "openai_chat",
            "/v1/responses": "openai_responses",
            "/v1/messages": "anthropic_messages",
            "/v1/messages/count_tokens": "anthropic_count_tokens",
            "/v1beta/models/gemini-2.5:generateContent": "gemini_generate",
            "/v1beta/models/gemini-2.5:streamGenerateContent": "gemini_stream",
            "/v1beta/models/gemini-2.5:countTokens": "gemini_count_tokens",
            "/vertex/v1/chat/completions": "vertex_openai",
            "/vertex/v1/models/gemini:generateContent": "vertex_gemini_generate",
            "/vertex/v1/models/gemini:streamGenerateContent": "vertex_gemini_stream",
            "/vertex/v1/models/gemini:countTokens": "vertex_gemini_count_tokens",
        }
        for path, protocol in matrix.items():
            with self.subTest(path=path):
                self.assertEqual(classify_request_protocol("POST", path), protocol)
        self.assertIsNone(classify_request_protocol("GET", "/health"))
        self.assertIsNone(classify_request_protocol("POST", "/api/config/save"))

    def test_query_and_independent_retention_are_bounded(self):
        query = RequestTraceQuery(
            protocols=("openai_chat",),
            outcomes=("upstream_error",),
            request_id="req-safe-123",
            page_size=200,
        )
        policy = RequestTraceRetentionPolicy(retention_days=7, max_traces=100_000)

        self.assertEqual(query.page_size, 200)
        self.assertEqual(policy.retention_days, 7)
        for invalid in (0, 201):
            with self.assertRaises(ValueError):
                RequestTraceQuery(page_size=invalid)
        with self.assertRaises(ValueError):
            RequestTraceRetentionPolicy(retention_days=91)
        with self.assertRaises(ValueError):
            RequestTraceRetentionPolicy(max_traces=999)


if __name__ == "__main__":
    unittest.main()
