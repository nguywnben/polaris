"""Request trace collection, redaction, lifecycle, and retention tests."""

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.request_trace import RequestTracePage, RequestTraceQuery, RequestTraceRetentionPolicy
from core.request_trace_service import (
    REQUEST_TRACE_MASTER_KEY_CONFIG,
    REQUEST_TRACE_RETENTION_CONFIG,
    RequestTraceCollector,
    RequestTraceService,
    request_trace_scope,
    trace_decision,
)


class _Repository:
    def __init__(self):
        self.traces = []
        self.prunes = []
        self.queries = []
        self.page = RequestTracePage(traces=())

    async def append(self, trace):
        self.traces.append(trace)

    async def query(self, query):
        self.queries.append(query)
        return self.page

    async def prune(self, policy, *, now):
        self.prunes.append((policy, now))
        return 0


class _ConcurrentRepository(_Repository):
    def __init__(self):
        super().__init__()
        self.started = 0
        self.both_started = asyncio.Event()

    async def append(self, trace):
        self.started += 1
        if self.started == 2:
            self.both_started.set()
        await asyncio.wait_for(self.both_started.wait(), timeout=0.25)
        self.traces.append(trace)


class _Storage:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.set_calls = []
        self.keys = []
        self.repositories = []

    async def get_config(self, key, default=None):
        return self.values.get(key, default)

    async def set_config(self, key, value):
        self.values[key] = value
        self.set_calls.append((key, value))
        return True

    async def create_request_trace_repository(self, *, cursor_signing_key):
        self.keys.append(cursor_signing_key)
        repository = _Repository()
        self.repositories.append(repository)
        return repository


class RequestTraceCollectorTests(unittest.TestCase):
    def test_collector_builds_one_content_free_trace_and_bounds_steps(self):
        collector = RequestTraceCollector("request-123", "openai_chat")
        for _ in range(80):
            collector.record(
                category="routing",
                action="selected",
                result="succeeded",
                reason="healthy_candidate",
                provider="openai",
                model="gpt-5",
            )
        collector.set_usage(input_tokens=100, output_tokens=20, cost_usd=0.001)
        trace = collector.complete(status_code=200)

        self.assertEqual(trace.request_id, "request-123")
        self.assertEqual(len(trace.decisions), 64)
        self.assertTrue(trace.decisions_truncated)
        self.assertEqual(trace.total_tokens, 120)
        self.assertNotIn("prompt", repr(trace.to_record()).lower())

    def test_scope_helper_drops_unallowlisted_metadata_without_breaking_request(self):
        with request_trace_scope("request-123", "anthropic_messages") as collector:
            self.assertFalse(
                trace_decision(
                    category="routing",
                    action="selected",
                    result="succeeded",
                    reason="private free text",
                )
            )
            self.assertTrue(
                trace_decision(
                    category="routing",
                    action="selected",
                    result="succeeded",
                    reason="healthy_candidate",
                )
            )
        self.assertEqual(len(collector.decisions), 2)  # accepted + selected

    def test_failure_outcomes_are_canonical(self):
        matrix = {
            400: "client_error",
            401: "denied",
            429: "rate_limited",
            503: "unavailable",
            500: "internal_error",
        }
        for status_code, outcome in matrix.items():
            with self.subTest(status_code=status_code):
                collector = RequestTraceCollector("request-123", "gemini_generate")
                self.assertEqual(collector.complete(status_code=status_code).outcome, outcome)

    def test_recovered_upstream_failure_keeps_final_request_successful(self):
        collector = RequestTraceCollector("request-123", "openai_chat")
        collector.record(
            category="upstream",
            action="failed",
            result="failed",
            reason="provider_error",
            provider="openai",
            model="gpt-5",
            status_code=503,
        )
        collector.record(
            category="upstream",
            action="succeeded",
            result="succeeded",
            reason="completed",
            provider="xai",
            model="grok-4",
            status_code=200,
        )

        trace = collector.complete(status_code=200)

        self.assertEqual(trace.outcome, "succeeded")


class RequestTraceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_restart_reuses_signing_key_and_retention_is_independent(self):
        storage = _Storage()
        first = await RequestTraceService.create(storage)
        second = await RequestTraceService.create(storage)

        self.assertEqual(storage.keys[0], storage.keys[1])
        self.assertEqual(
            len([key for key, _ in storage.set_calls if key == REQUEST_TRACE_MASTER_KEY_CONFIG]), 1
        )
        self.assertNotIn("audit_retention_v1", storage.values)
        self.assertEqual(first.retention_policy, RequestTraceRetentionPolicy())
        self.assertEqual(second.retention_policy, RequestTraceRetentionPolicy())

    async def test_record_query_and_retention_use_validated_repository_boundary(self):
        storage = _Storage()
        service = await RequestTraceService.create(storage)
        collector = RequestTraceCollector("request-123", "openai_responses")
        trace = collector.complete(status_code=200)

        await service.record(trace)
        query = RequestTraceQuery(request_id="request-123")
        self.assertIs(await service.query(query), storage.repositories[0].page)
        policy = RequestTraceRetentionPolicy(retention_days=3, max_traces=2_000)
        removed = await service.update_retention(
            policy,
            now=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )

        self.assertEqual(removed, 0)
        self.assertEqual(storage.repositories[0].traces, [trace])
        self.assertEqual(storage.repositories[0].queries, [query])
        self.assertEqual(
            storage.values[REQUEST_TRACE_RETENTION_CONFIG],
            {"retention_days": 3, "max_traces": 2_000},
        )

    async def test_record_appends_are_concurrent_and_retention_is_amortized(self):
        storage = _Storage()
        service = await RequestTraceService.create(storage)
        repository = _ConcurrentRepository()
        service._repository = repository
        traces = [
            RequestTraceCollector(f"request-{index}", "openai_responses").complete(status_code=200)
            for index in range(2)
        ]

        await asyncio.gather(*(service.record(trace) for trace in traces))

        self.assertCountEqual(repository.traces, traces)
        self.assertEqual(len(repository.prunes), 1)


if __name__ == "__main__":
    unittest.main()
