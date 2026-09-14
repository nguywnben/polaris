"""MongoDB repository for bounded request decision traces."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from core.request_trace import (
    RequestTrace,
    RequestTraceAlreadyExistsError,
    RequestTracePage,
    RequestTraceQuery,
    RequestTraceRetentionPolicy,
    decode_request_trace_cursor,
    encode_request_trace_cursor,
    request_trace_from_record,
)
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import DuplicateKeyError


class MongoRequestTraceRepository:
    def __init__(self, collection: Any, *, cursor_signing_key: bytes) -> None:
        self._collection = collection
        self._cursor_signing_key = cursor_signing_key
        self._initialized = False

    async def initialize(self) -> None:
        await self._collection.create_indexes(
            [
                IndexModel(
                    [("trace_id", ASCENDING)], unique=True, name="idx_request_trace_id_unique"
                ),
                IndexModel(
                    [("started_at", DESCENDING), ("trace_id", DESCENDING)],
                    name="idx_request_traces_order",
                ),
                IndexModel([("request_id", ASCENDING)], name="idx_request_traces_request"),
                IndexModel(
                    [("protocol", ASCENDING), ("outcome", ASCENDING), ("started_at", DESCENDING)],
                    name="idx_request_traces_protocol_outcome",
                ),
                IndexModel(
                    [
                        ("selected_provider", ASCENDING),
                        ("requested_model", ASCENDING),
                        ("started_at", DESCENDING),
                    ],
                    name="idx_request_traces_route",
                ),
            ]
        )
        self._initialized = True

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("MongoDB request trace repository is not initialized.")

    async def append(self, trace: RequestTrace) -> None:
        self._ensure_initialized()
        document = request_trace_from_record(trace.to_record()).to_record()
        document["started_at"] = datetime.fromisoformat(document["started_at"])
        document["completed_at"] = datetime.fromisoformat(document["completed_at"])
        try:
            await self._collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise RequestTraceAlreadyExistsError("Request trace already exists.") from exc

    async def query(self, query: RequestTraceQuery) -> RequestTracePage:
        self._ensure_initialized()
        filters: dict[str, Any] = {}
        for field, values in (
            ("trace_id", query.trace_ids),
            ("protocol", query.protocols),
            ("outcome", query.outcomes),
            ("selected_provider", query.providers),
            ("requested_model", query.models),
        ):
            if values:
                filters[field] = {"$in": list(values)}
        if query.request_id is not None:
            filters["request_id"] = query.request_id
        time_filter: dict[str, Any] = {}
        if query.started_after is not None:
            time_filter["$gte"] = query.started_after
        if query.started_before is not None:
            time_filter["$lte"] = query.started_before
        if time_filter:
            filters["started_at"] = time_filter
        if query.cursor is not None:
            cursor_time, cursor_id = decode_request_trace_cursor(
                query.cursor, signing_key=self._cursor_signing_key
            )
            cursor_date = datetime.fromisoformat(cursor_time)
            filters["$or"] = [
                {"started_at": {"$lt": cursor_date}},
                {"started_at": cursor_date, "trace_id": {"$lt": cursor_id}},
            ]
        cursor = self._collection.find(filters, {"_id": False})
        cursor = cursor.sort([("started_at", DESCENDING), ("trace_id", DESCENDING)])
        cursor = cursor.limit(query.page_size + 1)
        records = [record async for record in cursor]
        has_more = len(records) > query.page_size
        traces = tuple(self._from_document(record) for record in records[: query.page_size])
        next_cursor = None
        if has_more and traces:
            last = traces[-1]
            next_cursor = encode_request_trace_cursor(
                started_at=last.started_at,
                trace_id=last.trace_id,
                signing_key=self._cursor_signing_key,
            )
        return RequestTracePage(traces=traces, next_cursor=next_cursor)

    @staticmethod
    def _from_document(document: Any) -> RequestTrace:
        record = dict(document)
        for field in ("started_at", "completed_at"):
            if isinstance(record.get(field), datetime):
                value = record[field]
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                record[field] = value.astimezone(timezone.utc).isoformat()
        return request_trace_from_record(record)

    async def prune(self, policy: RequestTraceRetentionPolicy, *, now: datetime) -> int:
        self._ensure_initialized()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("Request trace prune timestamp must be timezone-aware.")
        cutoff = now.astimezone(timezone.utc) - timedelta(days=policy.retention_days)
        expired = await self._collection.delete_many({"started_at": {"$lt": cutoff}})
        remaining = await self._collection.count_documents({})
        surplus = max(0, remaining - policy.max_traces)
        removed_surplus = 0
        if surplus:
            cursor = self._collection.find({}, {"_id": False, "trace_id": True})
            cursor = cursor.sort([("started_at", ASCENDING), ("trace_id", ASCENDING)]).limit(
                surplus
            )
            trace_ids = [record["trace_id"] async for record in cursor]
            if trace_ids:
                removed_surplus = (
                    await self._collection.delete_many({"trace_id": {"$in": trace_ids}})
                ).deleted_count
        return int(expired.deleted_count) + int(removed_surplus)
