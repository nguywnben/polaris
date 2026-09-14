"""MongoDB implementation of the append-only audit repository contract."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from core.audit import (
    AuditEvent,
    AuditEventAlreadyExistsError,
    AuditPage,
    AuditQuery,
    AuditRetentionPolicy,
    audit_event_from_record,
    decode_audit_cursor,
    encode_audit_cursor,
)
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import DuplicateKeyError


class MongoAuditRepository:
    """Durable audit storage over an asynchronous MongoDB collection."""

    def __init__(self, collection: Any, *, cursor_signing_key: bytes) -> None:
        self._collection = collection
        self._cursor_signing_key = cursor_signing_key
        self._initialized = False

    async def initialize(self) -> None:
        await self._collection.create_indexes(
            [
                IndexModel(
                    [("event_id", ASCENDING)],
                    unique=True,
                    name="idx_audit_event_id_unique",
                ),
                IndexModel(
                    [("occurred_at", DESCENDING), ("event_id", DESCENDING)],
                    name="idx_audit_events_order",
                ),
                IndexModel(
                    [("request_id", ASCENDING)],
                    name="idx_audit_events_request",
                ),
                IndexModel(
                    [
                        ("action", ASCENDING),
                        ("outcome", ASCENDING),
                        ("occurred_at", DESCENDING),
                    ],
                    name="idx_audit_events_action_outcome",
                ),
                IndexModel(
                    [
                        ("target_type", ASCENDING),
                        ("target_fingerprint", ASCENDING),
                        ("occurred_at", DESCENDING),
                    ],
                    name="idx_audit_events_target",
                ),
            ]
        )
        self._initialized = True

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("MongoDB audit repository is not initialized.")

    async def append(self, event: AuditEvent) -> None:
        self._ensure_initialized()
        document = audit_event_from_record(event.to_record()).to_record()
        document["occurred_at"] = datetime.fromisoformat(document["occurred_at"])
        try:
            await self._collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise AuditEventAlreadyExistsError("Audit event already exists.") from exc

    async def query(self, query: AuditQuery) -> AuditPage:
        self._ensure_initialized()
        document_filter: dict[str, Any] = {}
        self._add_exact_filters(query, document_filter)
        if query.request_id is not None:
            document_filter["request_id"] = query.request_id
        if query.occurred_after is not None or query.occurred_before is not None:
            time_filter: dict[str, datetime] = {}
            if query.occurred_after is not None:
                time_filter["$gte"] = query.occurred_after
            if query.occurred_before is not None:
                time_filter["$lte"] = query.occurred_before
            document_filter["occurred_at"] = time_filter
        if query.cursor is not None:
            cursor_time, cursor_event_id = decode_audit_cursor(
                query.cursor,
                signing_key=self._cursor_signing_key,
            )
            cursor_datetime = datetime.fromisoformat(cursor_time)
            document_filter["$or"] = [
                {"occurred_at": {"$lt": cursor_datetime}},
                {
                    "occurred_at": cursor_datetime,
                    "event_id": {"$lt": cursor_event_id},
                },
            ]

        cursor = self._collection.find(document_filter, {"_id": False})
        cursor = cursor.sort([("occurred_at", DESCENDING), ("event_id", DESCENDING)])
        cursor = cursor.limit(query.page_size + 1)
        documents = [document async for document in cursor]

        has_more = len(documents) > query.page_size
        events = tuple(
            self._event_from_document(document) for document in documents[: query.page_size]
        )
        next_cursor = None
        if has_more and events:
            last_event = events[-1]
            next_cursor = encode_audit_cursor(
                occurred_at=last_event.occurred_at,
                event_id=last_event.event_id,
                signing_key=self._cursor_signing_key,
            )
        return AuditPage(events=events, next_cursor=next_cursor)

    @staticmethod
    def _add_exact_filters(query: AuditQuery, document_filter: dict[str, Any]) -> None:
        filters = (
            ("actor_type", query.actor_types),
            ("actor_fingerprint", query.actor_fingerprints),
            ("action", query.actions),
            ("target_type", query.target_types),
            ("target_fingerprint", query.target_fingerprints),
            ("outcome", query.outcomes),
        )
        for field_name, values in filters:
            if values:
                document_filter[field_name] = {"$in": list(values)}

    @staticmethod
    def _event_from_document(document: dict[str, Any]) -> AuditEvent:
        record = dict(document)
        occurred_at = record.get("occurred_at")
        if isinstance(occurred_at, datetime):
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=timezone.utc)
            record["occurred_at"] = occurred_at.astimezone(timezone.utc).isoformat()
        return audit_event_from_record(record)

    async def prune(self, policy: AuditRetentionPolicy, *, now: datetime) -> int:
        self._ensure_initialized()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("Audit prune timestamp must be timezone-aware.")
        cutoff = now.astimezone(timezone.utc) - timedelta(days=policy.retention_days)
        expired_result = await self._collection.delete_many({"occurred_at": {"$lt": cutoff}})
        removed = int(expired_result.deleted_count)

        remaining = int(await self._collection.count_documents({}))
        surplus = max(0, remaining - policy.max_events)
        if surplus:
            cursor = self._collection.find({}, {"_id": False, "event_id": True})
            cursor = cursor.sort([("occurred_at", ASCENDING), ("event_id", ASCENDING)])
            cursor = cursor.limit(surplus)
            event_ids = [document["event_id"] async for document in cursor]
            if event_ids:
                surplus_result = await self._collection.delete_many(
                    {"event_id": {"$in": event_ids}}
                )
                removed += int(surplus_result.deleted_count)
        return removed
