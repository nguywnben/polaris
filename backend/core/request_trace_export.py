"""Bounded JSONL and formula-safe CSV export for request decision traces."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol

from core.request_trace import RequestTracePage, RequestTraceQuery

MAX_REQUEST_TRACE_EXPORT_TRACES = 10_000
MAX_REQUEST_TRACE_EXPORT_BYTES = 16 * 1024 * 1024
_COLUMNS = (
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
)


class _TraceQueryService(Protocol):
    async def query(self, query: RequestTraceQuery) -> RequestTracePage: ...


class RequestTraceExportLimitError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RequestTraceExport:
    chunks: tuple[bytes, ...]
    trace_count: int
    byte_count: int
    media_type: str
    extension: str


def _formula_safe(value: Any) -> str:
    text = str(value)
    stripped = text.lstrip(" \t\r\n")
    if text.startswith(("\t", "\r", "\n")) or (stripped and stripped[0] in {"=", "+", "-", "@"}):
        return f"'{text}"
    return text


def _csv_line(values: list[Any]) -> bytes:
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerow([_formula_safe(value) for value in values])
    return output.getvalue().encode("utf-8")


def _chunk(record: dict[str, Any], export_format: Literal["jsonl", "csv"]) -> bytes:
    if export_format == "jsonl":
        return (
            json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        ).encode("utf-8")
    return _csv_line(
        [
            json.dumps(record[column], separators=(",", ":"), ensure_ascii=False)
            if column == "decisions"
            else record[column]
            for column in _COLUMNS
        ]
    )


async def build_request_trace_export(
    service: _TraceQueryService,
    query: RequestTraceQuery,
    *,
    export_format: Literal["jsonl", "csv"],
    max_traces: int = MAX_REQUEST_TRACE_EXPORT_TRACES,
    max_bytes: int = MAX_REQUEST_TRACE_EXPORT_BYTES,
) -> RequestTraceExport:
    if not isinstance(query, RequestTraceQuery) or query.cursor is not None:
        raise ValueError("Request trace exports require a validated cursor-free query.")
    if export_format not in {"jsonl", "csv"}:
        raise ValueError("Unsupported request trace export format.")
    if type(max_traces) is not int or not 1 <= max_traces <= MAX_REQUEST_TRACE_EXPORT_TRACES:
        raise ValueError("Invalid request trace export count limit.")
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_REQUEST_TRACE_EXPORT_BYTES:
        raise ValueError("Invalid request trace export byte limit.")

    chunks: list[bytes] = []
    byte_count = 0
    trace_count = 0
    if export_format == "csv":
        header = _csv_line(list(_COLUMNS))
        if len(header) > max_bytes:
            raise RequestTraceExportLimitError("Request trace export byte limit exceeded.")
        chunks.append(header)
        byte_count = len(header)

    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        remaining = max_traces - trace_count
        if remaining <= 0:
            raise RequestTraceExportLimitError("Request trace export count limit exceeded.")
        page = await service.query(replace(query, page_size=min(200, remaining), cursor=cursor))
        if len(page.traces) > remaining:
            raise RequestTraceExportLimitError("Request trace export count limit exceeded.")
        for trace in page.traces:
            chunk = _chunk(trace.to_record(), export_format)
            if byte_count + len(chunk) > max_bytes:
                raise RequestTraceExportLimitError("Request trace export byte limit exceeded.")
            chunks.append(chunk)
            byte_count += len(chunk)
            trace_count += 1
        if page.next_cursor is None:
            break
        if trace_count >= max_traces:
            raise RequestTraceExportLimitError("Request trace export count limit exceeded.")
        if page.next_cursor in seen_cursors:
            raise ValueError("Request trace repository returned a repeated cursor.")
        seen_cursors.add(page.next_cursor)
        cursor = page.next_cursor

    return RequestTraceExport(
        chunks=tuple(chunks),
        trace_count=trace_count,
        byte_count=byte_count,
        media_type="application/x-ndjson" if export_format == "jsonl" else "text/csv",
        extension=export_format,
    )
