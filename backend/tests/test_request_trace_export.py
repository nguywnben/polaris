"""Bounded, formula-safe request trace export tests."""

from __future__ import annotations

import csv
import io
import json
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.request_trace import RequestTracePage, RequestTraceQuery
from core.request_trace_export import (
    RequestTraceExportLimitError,
    build_request_trace_export,
)
from core.request_trace_service import RequestTraceCollector


def _trace(index: int):
    collector = RequestTraceCollector(f"request-{index}", "openai_chat")
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
    def __init__(self, pages):
        self.pages = list(pages)
        self.queries = []

    async def query(self, query):
        self.queries.append(query)
        return self.pages.pop(0)


class RequestTraceExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_jsonl_follows_cursors_and_preserves_filter_snapshot(self):
        traces = (_trace(1), _trace(2))
        service = _Service(
            [
                RequestTracePage(traces=(traces[0],), next_cursor="next"),
                RequestTracePage(traces=(traces[1],)),
            ]
        )
        query = RequestTraceQuery(protocols=("openai_chat",), request_id="request-1")

        export = await build_request_trace_export(service, query, export_format="jsonl")

        records = [json.loads(line) for line in b"".join(export.chunks).splitlines()]
        self.assertEqual(records, [trace.to_record() for trace in traces])
        self.assertEqual([call.cursor for call in service.queries], [None, "next"])
        self.assertTrue(all(call.protocols == query.protocols for call in service.queries))
        self.assertNotIn("prompt", b"".join(export.chunks).decode().lower())

    async def test_csv_has_fixed_columns_and_serialized_decisions(self):
        trace = _trace(1)
        service = _Service([RequestTracePage(traces=(trace,))])

        export = await build_request_trace_export(service, RequestTraceQuery(), export_format="csv")

        rows = list(csv.reader(io.StringIO(b"".join(export.chunks).decode())))
        self.assertEqual(rows[0][0:4], ["schema_version", "trace_id", "request_id", "protocol"])
        self.assertEqual(json.loads(rows[1][-2]), trace.to_record()["decisions"])
        self.assertEqual(rows[1][-1], "False")

    async def test_limits_reject_instead_of_truncating(self):
        traces = (_trace(1), _trace(2))
        service = _Service([RequestTracePage(traces=traces, next_cursor="more")])
        with self.assertRaises(RequestTraceExportLimitError):
            await build_request_trace_export(
                service,
                RequestTraceQuery(),
                export_format="jsonl",
                max_traces=2,
            )


if __name__ == "__main__":
    unittest.main()
