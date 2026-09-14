"""Bounded, injection-safe audit export contract tests."""

from __future__ import annotations

import csv
import io
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.audit import AuditPage, AuditQuery, create_audit_event
from core.audit_export import (
    AuditExportLimitError,
    _formula_safe_csv_cell,
    build_audit_export,
)


def _event(index: int):
    return create_audit_event(
        request_id=f"request-{index}",
        actor_type="panel_session",
        actor_identifier="owner@example.com",
        action="credential.delete",
        target_type="credential",
        target_identifier=f"secret-credential-{index}.json",
        outcome="succeeded",
        change_codes=("deleted",),
        fingerprint_key=b"audit-export-fingerprint-key-32b",
        occurred_at=datetime(2026, 8, 24, 12, index, tzinfo=timezone.utc),
    )


class _PagedService:
    def __init__(self, pages):
        self.pages = list(pages)
        self.queries = []

    async def query(self, query):
        self.queries.append(query)
        return self.pages.pop(0)


class AuditExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_jsonl_stream_is_filter_consistent_redacted_and_deterministic(self):
        events = (_event(0), _event(1))
        service = _PagedService([AuditPage(events=events)])
        query = AuditQuery(
            actions=("credential.delete",),
            outcomes=("succeeded",),
            request_id="request-0",
        )

        export = await build_audit_export(service, query, export_format="jsonl")

        records = [json.loads(line) for line in b"".join(export.chunks).splitlines()]
        self.assertEqual(records, [event.to_record() for event in events])
        self.assertEqual(export.event_count, 2)
        self.assertEqual(export.media_type, "application/x-ndjson")
        self.assertEqual(export.extension, "jsonl")
        self.assertEqual(service.queries[0].actions, query.actions)
        self.assertEqual(service.queries[0].outcomes, query.outcomes)
        self.assertEqual(service.queries[0].request_id, query.request_id)
        self.assertEqual(service.queries[0].page_size, 200)
        payload = b"".join(export.chunks).decode()
        self.assertNotIn("owner@example.com", payload)
        self.assertNotIn("secret-credential", payload)

    async def test_csv_has_fixed_columns_and_formula_safe_cells(self):
        event = _event(0)
        service = _PagedService([AuditPage(events=(event,))])

        export = await build_audit_export(service, AuditQuery(), export_format="csv")

        rows = list(csv.reader(io.StringIO(b"".join(export.chunks).decode("utf-8"))))
        self.assertEqual(
            rows[0],
            [
                "schema_version",
                "event_id",
                "occurred_at",
                "request_id",
                "actor_type",
                "actor_fingerprint",
                "action",
                "target_type",
                "target_fingerprint",
                "outcome",
                "change_codes",
            ],
        )
        self.assertEqual(rows[1][-1], "deleted")
        self.assertEqual(export.media_type, "text/csv")
        for dangerous in ("=cmd()", "+SUM(1,1)", "-2+3", "@IMPORTXML()", "  =1+1"):
            with self.subTest(dangerous=dangerous):
                escaped = _formula_safe_csv_cell(dangerous)
                self.assertTrue(escaped.startswith("'"))
                self.assertEqual(escaped[1:], dangerous)
        self.assertEqual(_formula_safe_csv_cell("credential.delete"), "credential.delete")

    async def test_export_follows_opaque_pages_without_changing_filters(self):
        first = _event(0)
        second = _event(1)
        service = _PagedService(
            [
                AuditPage(events=(first,), next_cursor="cursor-1"),
                AuditPage(events=(second,)),
            ]
        )
        query = AuditQuery(actor_types=("panel_session",), page_size=7)

        export = await build_audit_export(service, query, export_format="jsonl")

        self.assertEqual(export.event_count, 2)
        self.assertEqual([call.cursor for call in service.queries], [None, "cursor-1"])
        self.assertTrue(all(call.actor_types == query.actor_types for call in service.queries))
        self.assertTrue(all(call.page_size == 200 for call in service.queries))

    async def test_event_and_byte_limits_reject_instead_of_silently_truncating(self):
        events = (_event(0), _event(1))
        event_limited = _PagedService([AuditPage(events=events, next_cursor="more-results")])
        with self.assertRaisesRegex(AuditExportLimitError, "event limit"):
            await build_audit_export(
                event_limited,
                AuditQuery(),
                export_format="jsonl",
                max_events=2,
            )

        byte_limited = _PagedService([AuditPage(events=(_event(0),))])
        with self.assertRaisesRegex(AuditExportLimitError, "byte limit"):
            await build_audit_export(
                byte_limited,
                AuditQuery(),
                export_format="jsonl",
                max_bytes=10,
            )

        csv_header_limited = _PagedService([])
        with self.assertRaisesRegex(AuditExportLimitError, "byte limit"):
            await build_audit_export(
                csv_header_limited,
                AuditQuery(),
                export_format="csv",
                max_bytes=10,
            )

    async def test_export_rejects_unsupported_format_and_input_cursor(self):
        service = _PagedService([])
        with self.assertRaises(ValueError):
            await build_audit_export(service, AuditQuery(), export_format="xlsx")
        with self.assertRaises(ValueError):
            await build_audit_export(
                service,
                AuditQuery(cursor="consumer-cursor"),
                export_format="jsonl",
            )


if __name__ == "__main__":
    unittest.main()
