"""Authenticated request trace query/detail/retention/export API tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import httpx
import main
from core.request_trace import RequestTracePage, RequestTraceRetentionPolicy
from core.request_trace_service import RequestTraceCollector
from core.utils import verify_panel_token


def _trace():
    collector = RequestTraceCollector("request-123", "openai_chat")
    collector.record(
        category="routing",
        action="selected",
        result="succeeded",
        reason="healthy_candidate",
        provider="openai",
        model="gpt-5",
    )
    return collector.complete(status_code=200)


class _Service:
    def __init__(self):
        self.trace = _trace()
        self.retention_policy = RequestTraceRetentionPolicy()
        self.queries = []
        self.updates = []

    async def query(self, query):
        self.queries.append(query)
        traces = (
            (self.trace,) if not query.trace_ids or self.trace.trace_id in query.trace_ids else ()
        )
        return RequestTracePage(traces=traces)

    async def update_retention(self, policy):
        self.updates.append(policy)
        self.retention_policy = policy
        return 3


class _AuditService:
    def __init__(self):
        self.records = []

    async def record(self, mutation, **context):
        self.records.append((mutation, context))


class RequestTraceRouteTests(unittest.IsolatedAsyncioTestCase):
    async def _client(self):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        )

    async def test_routes_are_authenticated(self):
        paths = main.app.openapi()["paths"]
        self.assertIn("/api/traces", paths)
        self.assertIn("/api/traces/{trace_id}", paths)
        self.assertIn("/api/traces/retention", paths)
        self.assertIn("/api/traces/export", paths)
        async with await self._client() as client:
            responses = (
                await client.get("/api/traces"),
                await client.get("/api/traces/" + "a" * 32),
                await client.get("/api/traces/retention"),
                await client.get("/api/traces/export"),
            )
        self.assertEqual([response.status_code for response in responses], [401, 401, 401, 401])

    async def test_query_detail_retention_and_export_are_strict_and_content_free(self):
        service = _Service()
        audit_service = _AuditService()
        main.app.dependency_overrides[verify_panel_token] = lambda: "session"
        try:
            with (
                patch("core.panel.trace_routes.get_request_trace_service", return_value=service),
                patch("core.panel.trace_routes.get_audit_service", return_value=audit_service),
            ):
                async with await self._client() as client:
                    page = await client.get(
                        "/api/traces",
                        params=[
                            ("protocols", "openai_chat"),
                            ("outcomes", "succeeded"),
                            ("request_id", "request-123"),
                            ("page_size", "25"),
                        ],
                    )
                    detail = await client.get(f"/api/traces/{service.trace.trace_id}")
                    retention = await client.put(
                        "/api/traces/retention",
                        json={"retention_days": 3, "max_traces": 2_000},
                    )
                    export = await client.get("/api/traces/export?format=jsonl")
        finally:
            main.app.dependency_overrides.pop(verify_panel_token, None)

        self.assertEqual(
            [page.status_code, detail.status_code, retention.status_code, export.status_code],
            [200, 200, 200, 200],
        )
        self.assertEqual(page.json()["traces"], [service.trace.to_record()])
        self.assertEqual(detail.json(), service.trace.to_record())
        self.assertEqual(retention.json()["removed_traces"], 3)
        self.assertEqual(json.loads(export.content), service.trace.to_record())
        self.assertNotIn("prompt", export.text.lower())
        self.assertEqual(service.queries[0].page_size, 25)
        self.assertEqual(
            service.updates, [RequestTraceRetentionPolicy(retention_days=3, max_traces=2_000)]
        )
        mutation, context = audit_service.records[0]
        self.assertEqual((mutation.action, mutation.target_type), ("trace.export", "trace_policy"))
        self.assertEqual(mutation.change_codes, ("exported",))
        self.assertEqual(context["outcome"], "succeeded")

    async def test_invalid_id_and_storage_error_are_sanitized(self):
        service = _Service()
        service.query = AsyncMock(side_effect=RuntimeError("database password"))
        main.app.dependency_overrides[verify_panel_token] = lambda: "session"
        try:
            with patch("core.panel.trace_routes.get_request_trace_service", return_value=service):
                async with await self._client() as client:
                    invalid = await client.get("/api/traces/not-valid")
                    unavailable = await client.get("/api/traces")
        finally:
            main.app.dependency_overrides.pop(verify_panel_token, None)
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(unavailable.status_code, 503)
        self.assertNotIn("database password", unavailable.text)


if __name__ == "__main__":
    unittest.main()
