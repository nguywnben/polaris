"""Bounded streaming payload construction for redacted audit evidence."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol

from core.audit import AuditPage, AuditQuery

MAX_AUDIT_EXPORT_EVENTS = 10_000
MAX_AUDIT_EXPORT_BYTES = 8 * 1024 * 1024

_EXPORT_COLUMNS = (
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
)


class _AuditQueryService(Protocol):
    async def query(self, query: AuditQuery) -> AuditPage: ...


class AuditExportLimitError(RuntimeError):
    """Raised instead of returning an incomplete audit export."""


@dataclass(frozen=True, slots=True)
class AuditExport:
    chunks: tuple[bytes, ...]
    event_count: int
    byte_count: int
    media_type: str
    extension: str


def _formula_safe_csv_cell(value: Any) -> str:
    """Prevent spreadsheet software from interpreting exported text as a formula."""

    text = str(value)
    stripped = text.lstrip(" \t\r\n")
    if text.startswith(("\t", "\r", "\n")) or (stripped and stripped[0] in {"=", "+", "-", "@"}):
        return f"'{text}"
    return text


def _csv_line(values: list[Any]) -> bytes:
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerow(
        [_formula_safe_csv_cell(value) for value in values]
    )
    return output.getvalue().encode("utf-8")


def _event_chunk(record: dict[str, Any], export_format: Literal["jsonl", "csv"]) -> bytes:
    if export_format == "jsonl":
        return (
            json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        ).encode("utf-8")
    return _csv_line(
        [
            "|".join(record[column]) if column == "change_codes" else record[column]
            for column in _EXPORT_COLUMNS
        ]
    )


async def build_audit_export(
    service: _AuditQueryService,
    query: AuditQuery,
    *,
    export_format: Literal["jsonl", "csv"],
    max_events: int = MAX_AUDIT_EXPORT_EVENTS,
    max_bytes: int = MAX_AUDIT_EXPORT_BYTES,
) -> AuditExport:
    """Collect a filter-consistent snapshot into bounded chunks for StreamingResponse."""

    if not isinstance(query, AuditQuery) or query.cursor is not None:
        raise ValueError("Audit exports require a validated cursor-free query.")
    if export_format not in {"jsonl", "csv"}:
        raise ValueError("Unsupported audit export format.")
    if type(max_events) is not int or not 1 <= max_events <= MAX_AUDIT_EXPORT_EVENTS:
        raise ValueError("Invalid audit export event limit.")
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_AUDIT_EXPORT_BYTES:
        raise ValueError("Invalid audit export byte limit.")

    chunks: list[bytes] = []
    byte_count = 0
    event_count = 0
    if export_format == "csv":
        header = _csv_line(list(_EXPORT_COLUMNS))
        if len(header) > max_bytes:
            raise AuditExportLimitError("Audit export byte limit exceeded.")
        chunks.append(header)
        byte_count = len(header)

    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        remaining = max_events - event_count
        if remaining <= 0:
            raise AuditExportLimitError("Audit export event limit exceeded.")
        page = await service.query(
            replace(
                query,
                page_size=min(200, remaining),
                cursor=cursor,
            )
        )
        if len(page.events) > remaining:
            raise AuditExportLimitError("Audit export event limit exceeded.")
        for event in page.events:
            chunk = _event_chunk(event.to_record(), export_format)
            if byte_count + len(chunk) > max_bytes:
                raise AuditExportLimitError("Audit export byte limit exceeded.")
            chunks.append(chunk)
            byte_count += len(chunk)
            event_count += 1

        if page.next_cursor is None:
            break
        if event_count >= max_events:
            raise AuditExportLimitError("Audit export event limit exceeded.")
        if page.next_cursor in seen_cursors:
            raise ValueError("Audit repository returned a repeated cursor.")
        seen_cursors.add(page.next_cursor)
        cursor = page.next_cursor

    media_type = "application/x-ndjson" if export_format == "jsonl" else "text/csv"
    return AuditExport(
        chunks=tuple(chunks),
        event_count=event_count,
        byte_count=byte_count,
        media_type=media_type,
        extension=export_format,
    )
