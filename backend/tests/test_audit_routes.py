"""Authenticated audit query and retention management API contracts."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import httpx
import main
from core.audit import AuditPage, AuditQuery, AuditRetentionPolicy, create_audit_event
from core.audit_export import AuditExportLimitError
from core.panel.audit_routes import (
    AuditExportParams,
    AuditQueryParams,
    AuditRetentionUpdateRequest,
    export_audit_events,
    get_audit_events,
    get_audit_retention,
    update_audit_retention,
)
from core.utils import verify_panel_token
from starlette.requests import Request


def _event():
    return create_audit_event(
        request_id="request-123",
        actor_type="panel_session",
        actor_identifier="panel-owner",
        action="credential.delete",
        target_type="credential",
        target_identifier="private-credential.json",
        outcome="succeeded",
        change_codes=("deleted",),
        fingerprint_key=b"audit-route-fingerprint-key-32bytes",
        occurred_at=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
    )


def _body(response) -> dict:
    return json.loads(response.body)


class _AuditService:
    def __init__(self):
        self.retention_policy = AuditRetentionPolicy()
        self.query_calls = []
        self.update_calls = []
        self.record_calls = []
        self.page = AuditPage(events=(_event(),), next_cursor="opaque-cursor")

    async def query(self, query):
        self.query_calls.append(query)
        return self.page

    async def update_retention(self, policy):
        self.update_calls.append(policy)
        self.retention_policy = policy
        return 7

    async def record(self, mutation, **kwargs):
        self.record_calls.append((mutation, kwargs))


def _request(request_id="export-request"):
    request = Request({"type": "http", "method": "GET", "path": "/api/audit/export"})
    request.state.request_id = request_id
    return request


class AuditRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_routes_are_authenticated_and_exposed_under_stable_resource_paths(self):
        paths = main.app.openapi()["paths"]
        self.assertIn("/api/audit/events", paths)
        self.assertIn("/api/audit/retention", paths)
        self.assertEqual(
            paths["/api/audit/events"]["get"]["responses"]["200"]["content"]["application/json"][
                "schema"
            ]["$ref"],
            "#/components/schemas/AuditPageResponse",
        )
        self.assertEqual(
            paths["/api/audit/retention"]["put"]["responses"]["200"]["content"]["application/json"][
                "schema"
            ]["$ref"],
            "#/components/schemas/AuditRetentionUpdateResponse",
        )

        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            responses = (
                await client.get("/api/audit/events?page_size=25"),
                await client.get("/api/audit/retention"),
                await client.get("/api/audit/export?format=csv"),
                await client.put(
                    "/api/audit/retention",
                    json={"retention_days": 90, "max_events": 1_000_000},
                ),
            )

        self.assertEqual(
            [response.status_code for response in responses],
            [401, 401, 401, 401],
        )

    async def test_query_maps_all_bounded_filters_and_returns_opaque_page(self):
        service = _AuditService()
        params = AuditQueryParams(
            actor_types=["panel_session"],
            actor_fingerprints=["a" * 20],
            actions=["credential.delete"],
            target_types=["credential"],
            target_fingerprints=["b" * 20],
            outcomes=["succeeded"],
            request_id="request-123",
            occurred_after=datetime(2026, 8, 1, tzinfo=timezone.utc),
            occurred_before=datetime(2026, 8, 31, tzinfo=timezone.utc),
            page_size=25,
            cursor="opaque-input",
        )
        with patch("core.panel.audit_routes.get_audit_service", return_value=service):
            response = await get_audit_events(params=params, token="session")

        body = _body(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["events"], [service.page.events[0].to_record()])
        self.assertEqual(body["next_cursor"], "opaque-cursor")
        self.assertEqual(body["page_size"], 25)
        self.assertTrue(body["has_more"])
        self.assertEqual(
            service.query_calls,
            [
                AuditQuery(
                    actor_types=("panel_session",),
                    actor_fingerprints=("a" * 20,),
                    actions=("credential.delete",),
                    target_types=("credential",),
                    target_fingerprints=("b" * 20,),
                    outcomes=("succeeded",),
                    request_id="request-123",
                    occurred_after=datetime(2026, 8, 1, tzinfo=timezone.utc),
                    occurred_before=datetime(2026, 8, 31, tzinfo=timezone.utc),
                    page_size=25,
                    cursor="opaque-input",
                )
            ],
        )
        serialized = response.body.decode()
        self.assertNotIn("panel-owner", serialized)
        self.assertNotIn("private-credential.json", serialized)

    async def test_query_http_contract_accepts_repeated_filters_and_integer_page_size(self):
        service = _AuditService()
        service.page = AuditPage(events=service.page.events)
        main.app.dependency_overrides[verify_panel_token] = lambda: "session"
        try:
            with patch("core.panel.audit_routes.get_audit_service", return_value=service):
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://test",
                ) as client:
                    response = await client.get(
                        "/api/audit/events",
                        params=[
                            ("actions", "credential.delete"),
                            ("outcomes", "failed"),
                            ("outcomes", "succeeded"),
                            ("page_size", "25"),
                        ],
                    )
        finally:
            main.app.dependency_overrides.pop(verify_panel_token, None)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(service.query_calls[0].actions, ("credential.delete",))
        self.assertEqual(service.query_calls[0].outcomes, ("failed", "succeeded"))
        self.assertEqual(service.query_calls[0].page_size, 25)

    async def test_invalid_filter_or_tampered_cursor_has_stable_secret_free_error(self):
        service = _AuditService()
        service.query = AsyncMock(side_effect=ValueError("signature secret should not leak"))
        with patch("core.panel.audit_routes.get_audit_service", return_value=service):
            response = await get_audit_events(
                params=AuditQueryParams(cursor="tampered"),
                token="session",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(_body(response)["error"]["code"], "audit_query_invalid")
        self.assertNotIn("signature secret", response.body.decode())

    async def test_query_storage_failure_is_sanitized(self):
        service = _AuditService()
        service.query = AsyncMock(side_effect=RuntimeError("database password should not leak"))
        with patch("core.panel.audit_routes.get_audit_service", return_value=service):
            response = await get_audit_events(
                params=AuditQueryParams(),
                token="session",
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(_body(response)["error"]["code"], "audit_unavailable")
        self.assertNotIn("database password", response.body.decode())

    async def test_retention_read_exposes_policy_and_documented_bounds(self):
        service = _AuditService()
        with patch("core.panel.audit_routes.get_audit_service", return_value=service):
            response = await get_audit_retention(token="session")

        body = _body(response)
        self.assertEqual(body["policy"], {"retention_days": 90, "max_events": 1_000_000})
        self.assertEqual(body["bounds"]["retention_days"], {"minimum": 7, "maximum": 3650})
        self.assertEqual(body["bounds"]["max_events"], {"minimum": 1000, "maximum": 10_000_000})

    async def test_retention_update_is_strict_persists_then_reports_exact_prune_count(self):
        service = _AuditService()
        request = AuditRetentionUpdateRequest(retention_days=30, max_events=5_000)
        with patch("core.panel.audit_routes.get_audit_service", return_value=service):
            response = await update_audit_retention(request=request, token="session")

        self.assertEqual(
            service.update_calls,
            [AuditRetentionPolicy(retention_days=30, max_events=5_000)],
        )
        self.assertEqual(
            _body(response),
            {
                "policy": {"retention_days": 30, "max_events": 5_000},
                "removed_events": 7,
            },
        )
        for invalid in (
            {"retention_days": "30", "max_events": 5_000},
            {"retention_days": 30, "max_events": 5_000, "extra": True},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                AuditRetentionUpdateRequest.model_validate(invalid)

    async def test_export_streams_fixed_attachment_and_records_successful_operation(self):
        service = _AuditService()
        service.page = AuditPage(events=service.page.events)
        with patch("core.panel.audit_routes.get_audit_service", return_value=service):
            response = await export_audit_events(
                request=_request(),
                params=AuditExportParams(format="jsonl", actions=["credential.delete"]),
                token="session",
            )

        chunks = [chunk async for chunk in response.body_iterator]
        payload = b"".join(chunk.encode() if isinstance(chunk, str) else chunk for chunk in chunks)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "application/x-ndjson")
        self.assertRegex(
            response.headers["content-disposition"],
            r'^attachment; filename="polaris-audit-\d{8}T\d{6}Z\.jsonl"$',
        )
        self.assertEqual(response.headers["x-audit-event-count"], "1")
        self.assertEqual(json.loads(payload), service.page.events[0].to_record())
        mutation, evidence = service.record_calls[0]
        self.assertEqual(mutation.action, "audit.export")
        self.assertEqual(mutation.target_type, "audit_policy")
        self.assertEqual(mutation.change_codes, ("exported",))
        self.assertEqual(evidence["request_id"], "export-request")
        self.assertEqual(evidence["outcome"], "succeeded")

    async def test_export_limit_error_is_413_and_does_not_claim_success(self):
        service = _AuditService()
        with (
            patch("core.panel.audit_routes.get_audit_service", return_value=service),
            patch(
                "core.panel.audit_routes.build_audit_export",
                new=AsyncMock(side_effect=AuditExportLimitError("too many events")),
            ),
        ):
            response = await export_audit_events(
                request=_request(),
                params=AuditExportParams(format="csv"),
                token="session",
            )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(_body(response)["error"]["code"], "audit_export_limit_exceeded")
        self.assertEqual(service.record_calls, [])


if __name__ == "__main__":
    unittest.main()
