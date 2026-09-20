"""Transaction-only MongoDB durable usage ledger and hard-budget journal."""

from __future__ import annotations

import math
import uuid
from dataclasses import replace
from typing import Any

from core.usage_ledger import (
    DAILY_WINDOW_SECONDS,
    MAX_COST_NANOS,
    MAX_RECONCILE_BATCH,
    MAX_USAGE_REPORT_ROWS,
    MONTHLY_WINDOW_SECONDS,
    BudgetCommitResult,
    BudgetReleaseResult,
    BudgetReservation,
    BudgetReservationDecision,
    BudgetReservationRequest,
    BudgetReservationState,
    CredentialUsageAggregate,
    ProviderUsageAggregate,
    SpendSnapshot,
    UsageAppendResult,
    UsageLedgerConflict,
    UsageLedgerCorrupt,
    UsageLedgerEntry,
    UsageLedgerError,
    UsageLedgerStateConflict,
    UsageLiabilityPage,
    UsageTimeBucket,
    budget_reservation_from_record,
    usage_entry_from_record,
    usage_liability_page,
    validate_usage_liability_cursor,
)
from pymongo import ASCENDING, IndexModel
from pymongo.errors import DuplicateKeyError

_DOCUMENT_FIELDS = {
    "_id",
    "record_id",
    "kind",
    "state",
    "revision",
    "key_id",
    "created_at",
    "expires_at",
    "transitioned_at",
    "estimated_cost_nanos",
    "daily_budget_nanos",
    "monthly_budget_nanos",
    "event_id",
    "occurred_at",
    "credential_ref",
    "provider",
    "success",
    "total_tokens",
    "cost_nanos",
    "api_key_id",
    "payload",
}


class MongoDBUsageLedgerRepository:
    """MongoDB implementation requiring replica-set/sharded transactions."""

    def __init__(self, client: Any, ledger_collection: Any, budget_keys_collection: Any) -> None:
        self._client = client
        self._ledger = ledger_collection
        self._budget_keys = budget_keys_collection
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = False
        await self._ledger.create_indexes(
            [
                IndexModel(
                    [("event_id", ASCENDING)],
                    unique=True,
                    name="idx_durable_usage_mongo_event_unique",
                    partialFilterExpression={"event_id": {"$type": "string"}},
                ),
                IndexModel(
                    [("api_key_id", ASCENDING), ("occurred_at", ASCENDING)],
                    name="idx_durable_usage_mongo_spend",
                ),
                IndexModel(
                    [("key_id", ASCENDING), ("state", ASCENDING), ("expires_at", ASCENDING)],
                    name="idx_durable_usage_mongo_budget",
                ),
                IndexModel(
                    [("credential_ref", ASCENDING), ("occurred_at", ASCENDING)],
                    name="idx_durable_usage_mongo_credential",
                ),
            ]
        )
        await self._budget_keys.create_indexes(
            [
                IndexModel(
                    [("revision", ASCENDING)],
                    name="idx_durable_usage_mongo_key_revision",
                )
            ]
        )
        probe_id = f"usage-ledger-transaction-probe-{uuid.uuid4().hex}"

        async def probe(session: Any) -> None:
            await self._ledger.insert_one(
                {"_id": probe_id, "kind": "capability_probe"}, session=session
            )
            result = await self._ledger.delete_one({"_id": probe_id}, session=session)
            if result.deleted_count != 1:
                raise UsageLedgerError("MongoDB transaction capability probe failed.")

        try:
            await self._run_transaction(probe)
        except UsageLedgerError:
            raise
        except Exception as exc:
            raise UsageLedgerError(
                "MongoDB usage ledger requires transaction-capable deployment."
            ) from exc
        self._initialized = True

    async def check_available(self) -> None:
        self._ensure_initialized()
        names = await self._ledger.database.list_collection_names(
            filter={"name": self._ledger.name}
        )
        if self._ledger.name not in names:
            raise UsageLedgerCorrupt("Usage ledger collection is unavailable.")

    async def append_usage(self, entry: UsageLedgerEntry) -> UsageAppendResult:
        self._ensure_initialized()
        if type(entry) is not UsageLedgerEntry:
            raise ValueError("Usage ledger entry is invalid.")
        try:
            await self._ledger.insert_one(self._usage_document(entry))
            return UsageAppendResult(True, False)
        except DuplicateKeyError:
            document = await self._ledger.find_one({"event_id": entry.event_id})
            if document is not None and self._decode(document) == entry:
                return UsageAppendResult(False, True)
            raise UsageLedgerConflict("Usage event idempotency conflict.") from None

    async def reserve_budget(self, request: BudgetReservationRequest) -> BudgetReservationDecision:
        self._ensure_initialized()
        if type(request) is not BudgetReservationRequest:
            raise ValueError("Budget reservation request is invalid.")
        await self._ensure_key(request.key_id)

        async def reserve(session: Any) -> BudgetReservationDecision:
            await self._lock_key(session, request.key_id)
            await self._ledger.update_many(
                {
                    "kind": "reservation",
                    "state": "active",
                    "key_id": request.key_id,
                    "expires_at": {"$lte": request.created_at},
                },
                [
                    {
                        "$set": {
                            "state": "expired",
                            "revision": 2,
                            "transitioned_at": "$expires_at",
                            "payload.state": "expired",
                            "payload.revision": 2,
                            "payload.transitioned_at": "$expires_at",
                        }
                    }
                ],
                session=session,
            )
            existing = await self._ledger.find_one({"_id": request.reservation_id}, session=session)
            if existing is not None:
                reservation = self._decode_reservation(existing)
                if reservation.admits_delivery_replay(request):
                    return BudgetReservationDecision(
                        True,
                        request.reservation_id,
                        idempotent=True,
                        replayed=True,
                    )
                if (
                    reservation.state is BudgetReservationState.COMMITTED
                    and reservation.matches_operation(request)
                ):
                    raise UsageLedgerStateConflict("Budget reservation replay window expired.")
                if self._request(reservation) != request:
                    raise UsageLedgerConflict("Budget reservation idempotency conflict.")
                if reservation.state is not BudgetReservationState.ACTIVE:
                    raise UsageLedgerStateConflict("Budget reservation state conflict.")
                return BudgetReservationDecision(True, request.reservation_id, idempotent=True)
            active = await self._sum(
                {
                    "kind": "reservation",
                    "state": "active",
                    "key_id": request.key_id,
                    "expires_at": {"$gt": request.created_at},
                },
                "estimated_cost_nanos",
                session,
            )
            if request.daily_budget_nanos is not None:
                committed = await self._committed_cost(
                    request.key_id,
                    request.created_at - DAILY_WINDOW_SECONDS,
                    session,
                )
                if committed + active + request.estimated_cost_nanos > request.daily_budget_nanos:
                    return BudgetReservationDecision(
                        False, request.reservation_id, reason="daily_budget"
                    )
            if request.monthly_budget_nanos is not None:
                committed = await self._committed_cost(
                    request.key_id,
                    request.created_at - MONTHLY_WINDOW_SECONDS,
                    session,
                )
                if committed + active + request.estimated_cost_nanos > request.monthly_budget_nanos:
                    return BudgetReservationDecision(
                        False, request.reservation_id, reason="monthly_budget"
                    )
            try:
                await self._ledger.insert_one(
                    self._reservation_document(BudgetReservation.active(request)),
                    session=session,
                )
            except DuplicateKeyError as exc:
                raise UsageLedgerConflict("Budget reservation idempotency conflict.") from exc
            return BudgetReservationDecision(True, request.reservation_id)

        return await self._run_transaction(reserve)

    async def commit_reservation(
        self,
        reservation_id: str,
        usage: UsageLedgerEntry,
        *,
        transitioned_at: float,
    ) -> BudgetCommitResult:
        self._ensure_initialized()
        if type(usage) is not UsageLedgerEntry:
            raise ValueError("Usage ledger entry is invalid.")
        transitioned_at = self._timestamp(transitioned_at)
        initial_document = await self._ledger.find_one({"_id": reservation_id})
        if initial_document is None:
            raise UsageLedgerStateConflict("Budget reservation state conflict.")
        await self._ensure_key(self._decode_reservation(initial_document).key_id)

        async def commit(session: Any) -> tuple[BudgetCommitResult | None, bool]:
            await self._lock_key(session, self._decode_reservation(initial_document).key_id)
            document = await self._ledger.find_one({"_id": reservation_id}, session=session)
            if document is None:
                raise UsageLedgerStateConflict("Budget reservation state conflict.")
            reservation = self._decode_reservation(document)
            if reservation.state is BudgetReservationState.COMMITTED:
                if reservation.usage != usage:
                    raise UsageLedgerConflict("Budget commit idempotency conflict.")
                return BudgetCommitResult(False, idempotent=True), False
            if reservation.state is not BudgetReservationState.ACTIVE:
                raise UsageLedgerStateConflict("Budget reservation state conflict.")
            if usage.api_key_id != reservation.key_id:
                raise UsageLedgerConflict("Budget commit attribution conflict.")
            if transitioned_at >= reservation.expires_at:
                await self._replace_reservation(
                    replace(
                        reservation,
                        state=BudgetReservationState.EXPIRED,
                        revision=2,
                        transitioned_at=transitioned_at,
                    ),
                    session,
                )
                return None, True
            return await self._commit_active(reservation, usage, transitioned_at, session), False

        result, expired = await self._run_transaction(commit)
        if expired:
            raise UsageLedgerStateConflict("Budget reservation expired before commit.")
        if result is None:
            raise UsageLedgerStateConflict("Budget reservation state conflict.")
        return result

    async def release_reservation(
        self, reservation_id: str, *, transitioned_at: float
    ) -> BudgetReleaseResult:
        self._ensure_initialized()
        transitioned_at = self._timestamp(transitioned_at)
        initial_document = await self._ledger.find_one({"_id": reservation_id})
        if initial_document is None:
            raise UsageLedgerStateConflict("Budget reservation state conflict.")
        await self._ensure_key(self._decode_reservation(initial_document).key_id)

        async def release(session: Any) -> tuple[BudgetReleaseResult | None, bool]:
            await self._lock_key(session, self._decode_reservation(initial_document).key_id)
            document = await self._ledger.find_one({"_id": reservation_id}, session=session)
            if document is None:
                raise UsageLedgerStateConflict("Budget reservation state conflict.")
            reservation = self._decode_reservation(document)
            if reservation.state is BudgetReservationState.RELEASED:
                return BudgetReleaseResult(False, idempotent=True), False
            if reservation.state is not BudgetReservationState.ACTIVE:
                raise UsageLedgerStateConflict("Budget reservation state conflict.")
            state = (
                BudgetReservationState.EXPIRED
                if transitioned_at >= reservation.expires_at
                else BudgetReservationState.RELEASED
            )
            await self._replace_reservation(
                replace(
                    reservation,
                    state=state,
                    revision=2,
                    transitioned_at=transitioned_at,
                ),
                session,
            )
            if state is BudgetReservationState.EXPIRED:
                return None, True
            return BudgetReleaseResult(True), False

        result, expired = await self._run_transaction(release)
        if expired:
            raise UsageLedgerStateConflict("Budget reservation expired before release.")
        if result is None:
            raise UsageLedgerStateConflict("Budget reservation state conflict.")
        return result

    async def reconcile_expired(self, *, now: float, limit: int) -> int:
        self._ensure_initialized()
        now = self._timestamp(now)
        self._limit(limit)

        async def reconcile(session: Any) -> int:
            cursor = (
                self._ledger.find(
                    {
                        "kind": "reservation",
                        "state": "active",
                        "expires_at": {"$lte": now},
                    },
                    session=session,
                )
                .sort([("expires_at", ASCENDING), ("_id", ASCENDING)])
                .limit(limit)
            )
            documents = [document async for document in cursor]
            for document in documents:
                reservation = self._decode_reservation(document)
                await self._replace_reservation(
                    replace(
                        reservation,
                        state=BudgetReservationState.EXPIRED,
                        revision=2,
                        transitioned_at=reservation.expires_at,
                    ),
                    session,
                )
            return len(documents)

        return await self._run_transaction(reconcile)

    async def reconciliation_page(self, *, after: str | None, limit: int) -> UsageLiabilityPage:
        self._ensure_initialized()
        after = validate_usage_liability_cursor(after)
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("Usage liability page size is invalid.")
        query: dict[str, object] = {"kind": "reservation", "state": "active"}
        if after is not None:
            query["_id"] = {"$gt": after}
        cursor_reader = self._ledger.find(query).sort("_id", ASCENDING).limit(limit + 1)
        documents = [document async for document in cursor_reader]
        records = tuple(self._decode(document) for document in documents[:limit])
        complete = len(documents) <= limit
        cursor = None
        if not complete:
            last = records[-1]
            if type(last) is not BudgetReservation:
                raise UsageLedgerCorrupt("Usage liability row is not an active reservation.")
            cursor = last.reservation_id
        return usage_liability_page(records, complete=complete, cursor=cursor)

    async def get_spend(self, *, since: float, api_key_id: str = "") -> SpendSnapshot:
        self._ensure_initialized()
        query: dict[str, Any] = {
            "occurred_at": {"$gte": self._timestamp(since)},
            "cost_nanos": {"$ne": None},
        }
        if api_key_id:
            query["api_key_id"] = api_key_id
        cursor = await self._ledger.aggregate(
            [
                {"$match": query},
                {
                    "$group": {
                        "_id": None,
                        "cost": {"$sum": "$cost_nanos"},
                        "tokens": {"$sum": "$total_tokens"},
                        "calls": {"$sum": 1},
                    }
                },
            ]
        )
        documents = [document async for document in cursor]
        document = documents[0] if documents else {"cost": 0, "tokens": 0, "calls": 0}
        return SpendSnapshot(
            int(document["cost"]), int(document["tokens"]), int(document["calls"]), True
        )

    async def aggregate_credentials(
        self, *, since: float | None = None
    ) -> list[CredentialUsageAggregate]:
        return self._aggregate_credentials(await self._entries(since=since))

    async def aggregate_providers(self) -> list[ProviderUsageAggregate]:
        return self._aggregate_providers(await self._entries())

    async def aggregate_time_series(
        self, *, since: float, until: float, points: int
    ) -> list[UsageTimeBucket]:
        since = self._timestamp(since)
        until = self._timestamp(until)
        if until <= since or type(points) is not int or not 1 <= points <= 1_000:
            raise ValueError("Usage time-series interval is invalid.")
        return self._aggregate_time(
            await self._entries(since=since, until=until), since, until, points
        )

    async def retire_credential(
        self,
        credential_ref: str,
        replacement_ref: str,
        *,
        provider: str,
        limit: int,
    ) -> int:
        self._attribution(credential_ref, provider, limit)
        self._attribution(replacement_ref, provider, limit)
        if credential_ref == replacement_ref:
            return 0

        async def retire(session: Any) -> int:
            cursor = (
                self._ledger.find(
                    {"occurred_at": {"$ne": None}, "credential_ref": credential_ref},
                    session=session,
                )
                .sort([("occurred_at", ASCENDING), ("_id", ASCENDING)])
                .limit(limit)
            )
            documents = [document async for document in cursor]
            for document in documents:
                decoded = self._decode(document)
                if type(decoded) is UsageLedgerEntry:
                    rewritten: UsageLedgerEntry | BudgetReservation = replace(
                        decoded, credential_ref=replacement_ref, provider=provider
                    )
                else:
                    if decoded.usage is None:
                        raise UsageLedgerCorrupt("Committed reservation usage is missing.")
                    rewritten = replace(
                        decoded,
                        usage=replace(
                            decoded.usage,
                            credential_ref=replacement_ref,
                            provider=provider,
                        ),
                    )
                result = await self._ledger.replace_one(
                    {
                        "_id": document["_id"],
                        "revision": document["revision"],
                        "credential_ref": credential_ref,
                    },
                    self._document(rewritten),
                    session=session,
                )
                if result.modified_count != 1:
                    raise UsageLedgerStateConflict("Usage attribution revision conflict.")
            return len(documents)

        return await self._run_transaction(retire)

    async def _entries(
        self, *, since: float | None = None, until: float | None = None
    ) -> list[UsageLedgerEntry]:
        occurred: dict[str, float | None] = {"$ne": None}
        if since is not None:
            occurred["$gte"] = self._timestamp(since)
        if until is not None:
            occurred["$lt"] = self._timestamp(until)
        cursor = (
            self._ledger.find({"occurred_at": occurred})
            .sort([("occurred_at", ASCENDING), ("_id", ASCENDING)])
            .limit(MAX_USAGE_REPORT_ROWS + 1)
        )
        entries: list[UsageLedgerEntry] = []
        async for document in cursor:
            if len(entries) >= MAX_USAGE_REPORT_ROWS:
                raise UsageLedgerCorrupt("Usage report exceeds the bounded row limit.")
            decoded = self._decode(document)
            if type(decoded) is UsageLedgerEntry:
                entries.append(decoded)
            elif decoded.state is BudgetReservationState.COMMITTED and decoded.usage is not None:
                entries.append(decoded.usage)
            else:
                raise UsageLedgerCorrupt("Stored committed usage document is invalid.")
        return entries

    async def _commit_active(
        self,
        reservation: BudgetReservation,
        usage: UsageLedgerEntry,
        transitioned_at: float,
        session: Any,
    ) -> BudgetCommitResult:
        if await self._ledger.find_one({"event_id": usage.event_id}, session=session) is not None:
            raise UsageLedgerConflict("Usage event idempotency conflict.")
        active = await self._sum(
            {
                "kind": "reservation",
                "state": "active",
                "key_id": reservation.key_id,
                "expires_at": {"$gt": transitioned_at},
                "_id": {"$ne": reservation.reservation_id},
            },
            "estimated_cost_nanos",
            session,
        )
        overspent = usage.cost_nanos > reservation.estimated_cost_nanos
        if reservation.daily_budget_nanos is not None:
            daily = await self._committed_cost(
                reservation.key_id, transitioned_at - DAILY_WINDOW_SECONDS, session
            )
            overspent = (
                overspent or daily + active + usage.cost_nanos > reservation.daily_budget_nanos
            )
        if reservation.monthly_budget_nanos is not None:
            monthly = await self._committed_cost(
                reservation.key_id, transitioned_at - MONTHLY_WINDOW_SECONDS, session
            )
            overspent = (
                overspent or monthly + active + usage.cost_nanos > reservation.monthly_budget_nanos
            )
        await self._replace_reservation(
            replace(
                reservation,
                state=BudgetReservationState.COMMITTED,
                revision=2,
                transitioned_at=transitioned_at,
                usage=usage,
            ),
            session,
        )
        return BudgetCommitResult(True, overspent=overspent)

    async def _replace_reservation(self, value: BudgetReservation, session: Any) -> None:
        try:
            result = await self._ledger.replace_one(
                {"_id": value.reservation_id, "kind": "reservation", "revision": 1},
                self._reservation_document(value),
                session=session,
            )
        except DuplicateKeyError as exc:
            raise UsageLedgerConflict("Usage event idempotency conflict.") from exc
        if result.modified_count != 1:
            raise UsageLedgerStateConflict("Budget reservation revision conflict.")

    async def _lock_key(self, session: Any, key_id: str) -> None:
        result = await self._budget_keys.update_one(
            {"_id": key_id},
            {"$inc": {"revision": 1}},
            session=session,
        )
        if result.matched_count != 1:
            raise UsageLedgerStateConflict("Budget key lock is unavailable.")

    async def _ensure_key(self, key_id: str) -> None:
        await self._budget_keys.update_one(
            {"_id": key_id},
            {"$setOnInsert": {"key_id": key_id, "revision": 0}},
            upsert=True,
        )

    async def _committed_cost(self, key_id: str, since: float, session: Any) -> int:
        committed = await self._sum(
            {
                "api_key_id": key_id,
                "occurred_at": {"$gte": since},
                "cost_nanos": {"$ne": None},
            },
            "cost_nanos",
            session,
        )
        unresolved = await self._sum(
            {
                "kind": "reservation",
                "state": "expired",
                "key_id": key_id,
                "created_at": {"$gte": since},
                "estimated_cost_nanos": {"$ne": None},
            },
            "estimated_cost_nanos",
            session,
        )
        return committed + unresolved

    async def _sum(self, query: dict[str, Any], field: str, session: Any) -> int:
        cursor = await self._ledger.aggregate(
            [
                {"$match": query},
                {"$group": {"_id": None, "value": {"$sum": f"${field}"}}},
            ],
            session=session,
        )
        documents = [document async for document in cursor]
        return int(documents[0]["value"]) if documents else 0

    async def _run_transaction(self, callback: Any) -> Any:
        async with self._client.start_session() as session:
            return await session.with_transaction(callback)

    def _decode(self, document: Any) -> UsageLedgerEntry | BudgetReservation:
        try:
            if not isinstance(document, dict) or set(document) != _DOCUMENT_FIELDS:
                raise ValueError
            if document["kind"] == "usage":
                value: UsageLedgerEntry | BudgetReservation = usage_entry_from_record(
                    document["payload"]
                )
            elif document["kind"] == "reservation":
                value = budget_reservation_from_record(document["payload"])
            else:
                raise ValueError
            expected = self._materialized(value)
            if any(document[name] != expected[name] for name in expected):
                raise ValueError
            if document["_id"] != document["record_id"]:
                raise ValueError
            return value
        except (KeyError, TypeError, ValueError) as exc:
            raise UsageLedgerCorrupt("Stored usage ledger document is invalid.") from exc

    def _decode_reservation(self, document: Any) -> BudgetReservation:
        value = self._decode(document)
        if type(value) is not BudgetReservation:
            raise UsageLedgerConflict("Usage ledger record kind conflict.")
        return value

    def _usage_document(self, entry: UsageLedgerEntry) -> dict[str, object]:
        return self._document(entry)

    def _reservation_document(self, value: BudgetReservation) -> dict[str, object]:
        return self._document(value)

    def _document(self, value: UsageLedgerEntry | BudgetReservation) -> dict[str, object]:
        materialized = self._materialized(value)
        return {
            "_id": materialized["record_id"],
            **materialized,
            "payload": value.to_record(),
        }

    @staticmethod
    def _materialized(value: UsageLedgerEntry | BudgetReservation) -> dict[str, object]:
        usage = value if type(value) is UsageLedgerEntry else value.usage
        return {
            "record_id": value.event_id
            if type(value) is UsageLedgerEntry
            else value.reservation_id,
            "kind": "usage" if type(value) is UsageLedgerEntry else "reservation",
            "state": "committed" if type(value) is UsageLedgerEntry else value.state.value,
            "revision": 1 if type(value) is UsageLedgerEntry else value.revision,
            "key_id": value.api_key_id if type(value) is UsageLedgerEntry else value.key_id,
            "created_at": value.occurred_at
            if type(value) is UsageLedgerEntry
            else value.created_at,
            "expires_at": None if type(value) is UsageLedgerEntry else value.expires_at,
            "transitioned_at": None if type(value) is UsageLedgerEntry else value.transitioned_at,
            "estimated_cost_nanos": None
            if type(value) is UsageLedgerEntry
            else value.estimated_cost_nanos,
            "daily_budget_nanos": None
            if type(value) is UsageLedgerEntry
            else value.daily_budget_nanos,
            "monthly_budget_nanos": None
            if type(value) is UsageLedgerEntry
            else value.monthly_budget_nanos,
            "event_id": None if usage is None else usage.event_id,
            "occurred_at": None if usage is None else usage.occurred_at,
            "credential_ref": None if usage is None else usage.credential_ref,
            "provider": None if usage is None else usage.provider,
            "success": None if usage is None else usage.success,
            "total_tokens": None if usage is None else usage.total_tokens,
            "cost_nanos": None if usage is None else usage.cost_nanos,
            "api_key_id": None if usage is None else usage.api_key_id,
        }

    @staticmethod
    def _request(value: BudgetReservation) -> BudgetReservationRequest:
        return BudgetReservationRequest(
            schema_version=value.schema_version,
            reservation_id=value.reservation_id,
            key_id=value.key_id,
            created_at=value.created_at,
            expires_at=value.expires_at,
            estimated_tokens=value.estimated_tokens,
            estimated_cost_nanos=value.estimated_cost_nanos,
            daily_budget_nanos=value.daily_budget_nanos,
            monthly_budget_nanos=value.monthly_budget_nanos,
        )

    @staticmethod
    def _timestamp(value: float) -> float:
        if type(value) not in {int, float} or not math.isfinite(float(value)) or value < 0:
            raise ValueError("Usage timestamp is invalid.")
        return float(value)

    @staticmethod
    def _limit(limit: int) -> None:
        if type(limit) is not int or not 1 <= limit <= MAX_RECONCILE_BATCH:
            raise ValueError("Usage batch limit is invalid.")

    @classmethod
    def _attribution(cls, credential_ref: str, provider: str, limit: int) -> None:
        cls._limit(limit)
        if (
            not isinstance(credential_ref, str)
            or not credential_ref
            or len(credential_ref) > 255
            or credential_ref in {".", ".."}
            or "/" in credential_ref
            or "\\" in credential_ref
            or any(ord(character) < 32 or ord(character) == 127 for character in credential_ref)
        ):
            raise ValueError("Usage credential reference is invalid.")
        if (
            not isinstance(provider, str)
            or len(provider) > 64
            or any(ord(character) < 32 or ord(character) == 127 for character in provider)
        ):
            raise ValueError("Usage provider is invalid.")

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("MongoDB usage ledger repository is not initialized.")

    @staticmethod
    def _checked(current: int, value: int) -> int:
        total = current + value
        if total > MAX_COST_NANOS:
            raise UsageLedgerCorrupt("Usage aggregate exceeds the supported range.")
        return total

    @classmethod
    def _aggregate_credentials(
        cls, entries: list[UsageLedgerEntry]
    ) -> list[CredentialUsageAggregate]:
        grouped: dict[str, list[int]] = {}
        providers: dict[str, str] = {}
        for entry in entries:
            totals = grouped.setdefault(entry.credential_ref, [0] * 17)
            providers[entry.credential_ref] = max(
                providers.get(entry.credential_ref, ""), entry.provider
            )
            values = (
                1,
                int(entry.success),
                int(not entry.success),
                entry.input_tokens,
                entry.output_tokens,
                entry.total_tokens,
                entry.cached_tokens,
                entry.reasoning_tokens,
                entry.estimated_input_tokens,
                entry.estimated_tokens_saved,
                entry.compressed_messages,
                entry.latency_ms,
                entry.retry_count,
                entry.cost_nanos,
                entry.cache_creation_tokens,
                int(entry.success and entry.usage_reported),
                int(entry.success and entry.cost_status in {"estimated", "reported", "free"}),
            )
            for index, item in enumerate(values):
                totals[index] = cls._checked(totals[index], item)
        return [
            CredentialUsageAggregate(ref, providers[ref], *values)
            for ref, values in sorted(grouped.items())
        ]

    @classmethod
    def _aggregate_providers(cls, entries: list[UsageLedgerEntry]) -> list[ProviderUsageAggregate]:
        grouped: dict[str, list[int]] = {}
        for entry in entries:
            provider = entry.provider or "unknown"
            totals = grouped.setdefault(provider, [0] * 6)
            values = (
                1,
                int(entry.success),
                int(not entry.success),
                entry.total_tokens,
                entry.latency_ms,
                entry.cost_nanos,
            )
            for index, item in enumerate(values):
                totals[index] = cls._checked(totals[index], item)
        return [
            ProviderUsageAggregate(provider, *values)
            for provider, values in sorted(grouped.items())
        ]

    @classmethod
    def _aggregate_time(
        cls, entries: list[UsageLedgerEntry], since: float, until: float, points: int
    ) -> list[UsageTimeBucket]:
        step = (until - since) / points
        grouped = [[0] * 6 for _ in range(points)]
        for entry in entries:
            index = min(int((entry.occurred_at - since) / step), points - 1)
            values = (
                1,
                int(entry.success),
                int(not entry.success),
                entry.total_tokens,
                entry.cached_tokens,
                entry.cost_nanos,
            )
            for position, item in enumerate(values):
                grouped[index][position] = cls._checked(grouped[index][position], item)
        return [
            UsageTimeBucket(since + index * step, since + (index + 1) * step, *values)
            for index, values in enumerate(grouped)
        ]
