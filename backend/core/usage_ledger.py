"""Strict W4.14 usage/cost ledger and durable hard-budget journal domain."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, fields
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Mapping, Protocol, Sequence

from core.quality_decision import COMPRESSION_REASONS, MAX_POLICY_REVISION, QUALITY_PROFILES

USAGE_LEDGER_SCHEMA_VERSION = 1
NANOS_PER_USD = 1_000_000_000
MAX_COST_NANOS = 9_000_000_000_000_000_000
MAX_RESERVATION_TTL_SECONDS = 86_400.0
DAILY_WINDOW_SECONDS = 86_400.0
MONTHLY_WINDOW_SECONDS = 30 * DAILY_WINDOW_SECONDS
MAX_RECONCILE_BATCH = 1_000
MAX_USAGE_REPORT_ROWS = 100_000
MAX_LIABILITY_PAGE = 256

_EVENT_ID = re.compile(r"use_[0-9a-f]{32}")
_RESERVATION_ID = re.compile(r"qrs_[0-9a-f]{32}")
_KEY_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{0,128}")
_QUALITY_PROFILES = frozenset(QUALITY_PROFILES)
_COMPRESSION_REASONS = frozenset(COMPRESSION_REASONS) | {"unknown"}


class UsageLedgerError(RuntimeError):
    """Generic durable-ledger failure with no record attribution."""


class UsageLedgerConflict(UsageLedgerError):
    """An idempotency key was replayed with different immutable content."""


class UsageLedgerStateConflict(UsageLedgerError):
    """A requested journal transition contradicts its durable state."""


class UsageLedgerCorrupt(UsageLedgerError):
    """Stored usage or reservation data failed strict reconstruction."""


class UsageMigrationRequired(UsageLedgerError):
    """Host-local legacy usage exists without verified external migration evidence."""


def _strict_int(value: object, label: str, *, minimum: int = 0, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} is invalid.")
    return value


def _timestamp(value: object, label: str) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{label} is invalid.")
    timestamp = float(value)
    if not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError(f"{label} is invalid.")
    return timestamp


def _bounded_text(value: object, label: str, *, maximum: int, required: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum or (required and not value):
        raise ValueError(f"{label} is invalid.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{label} is invalid.")
    return value


def _optional_cost(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _strict_int(value, label, maximum=MAX_COST_NANOS)


def usd_to_nanos(value: object) -> int:
    """Convert a non-negative USD value conservatively to integer nano-USD."""

    if isinstance(value, bool):
        raise ValueError("USD cost is invalid.")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("USD cost is invalid.") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("USD cost is invalid.")
    nanos = int((amount * NANOS_PER_USD).to_integral_value(rounding=ROUND_CEILING))
    if nanos > MAX_COST_NANOS:
        raise ValueError("USD cost is invalid.")
    return nanos


def nanos_to_usd(value: int) -> float:
    nanos = _strict_int(value, "Nano-USD cost", maximum=MAX_COST_NANOS)
    return float(Decimal(nanos) / NANOS_PER_USD)


@dataclass(frozen=True, slots=True)
class UsageAppendResult:
    inserted: bool
    idempotent: bool

    def __post_init__(self) -> None:
        if type(self.inserted) is not bool or type(self.idempotent) is not bool:
            raise ValueError("Usage append result is invalid.")
        if self.inserted == self.idempotent:
            raise ValueError("Usage append result is contradictory.")


@dataclass(frozen=True, slots=True)
class BudgetReservationDecision:
    accepted: bool
    reservation_id: str
    reason: str = ""
    idempotent: bool = False
    replayed: bool = False

    def __post_init__(self) -> None:
        if any(
            type(value) is not bool for value in (self.accepted, self.idempotent, self.replayed)
        ):
            raise ValueError("Budget reservation decision is invalid.")
        if not isinstance(self.reservation_id, str) or not _RESERVATION_ID.fullmatch(
            self.reservation_id
        ):
            raise ValueError("Budget reservation decision ID is invalid.")
        if self.reason not in {"", "daily_budget", "monthly_budget"}:
            raise ValueError("Budget reservation decision reason is invalid.")
        if (
            self.accepted == bool(self.reason)
            or (not self.accepted and self.idempotent)
            or (self.replayed and (not self.accepted or not self.idempotent))
        ):
            raise ValueError("Budget reservation decision is contradictory.")


@dataclass(frozen=True, slots=True)
class BudgetCommitResult:
    committed: bool
    overspent: bool = False
    idempotent: bool = False

    def __post_init__(self) -> None:
        if any(
            type(value) is not bool for value in (self.committed, self.overspent, self.idempotent)
        ):
            raise ValueError("Budget commit result is invalid.")
        if self.committed and self.idempotent:
            raise ValueError("Budget commit result is contradictory.")


@dataclass(frozen=True, slots=True)
class BudgetReleaseResult:
    released: bool
    idempotent: bool = False

    def __post_init__(self) -> None:
        if type(self.released) is not bool or type(self.idempotent) is not bool:
            raise ValueError("Budget release result is invalid.")
        if self.released and self.idempotent:
            raise ValueError("Budget release result is contradictory.")


@dataclass(frozen=True, slots=True)
class SpendSnapshot:
    cost_nanos: int
    total_tokens: int
    calls: int
    available: bool

    def __post_init__(self) -> None:
        _strict_int(self.cost_nanos, "Spend cost", maximum=MAX_COST_NANOS)
        _strict_int(self.total_tokens, "Spend token count", maximum=9_223_372_036_854_775_807)
        _strict_int(self.calls, "Spend call count", maximum=9_223_372_036_854_775_807)
        if type(self.available) is not bool:
            raise ValueError("Spend availability is invalid.")


@dataclass(frozen=True, slots=True)
class CredentialUsageAggregate:
    credential_ref: str
    provider: str
    calls: int
    successful_calls: int
    failed_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    estimated_input_tokens: int
    estimated_tokens_saved: int
    compressed_messages: int
    total_latency_ms: int
    retry_count: int
    cost_nanos: int
    cache_creation_tokens: int
    reported_usage_calls: int

    def __post_init__(self) -> None:
        _bounded_text(
            self.credential_ref,
            "Usage aggregate credential reference",
            maximum=255,
            required=True,
        )
        _bounded_text(self.provider, "Usage aggregate provider", maximum=64)
        for field in fields(self):
            if field.name not in {"credential_ref", "provider"}:
                _strict_int(
                    getattr(self, field.name),
                    f"Usage aggregate {field.name}",
                    maximum=MAX_COST_NANOS,
                )
        if self.successful_calls + self.failed_calls != self.calls:
            raise ValueError("Usage aggregate call totals are contradictory.")


@dataclass(frozen=True, slots=True)
class ProviderUsageAggregate:
    provider: str
    calls: int
    successful_calls: int
    failed_calls: int
    total_tokens: int
    total_latency_ms: int
    cost_nanos: int

    def __post_init__(self) -> None:
        _bounded_text(self.provider, "Provider usage aggregate", maximum=64, required=True)
        for field in fields(self):
            if field.name != "provider":
                _strict_int(
                    getattr(self, field.name),
                    f"Provider usage aggregate {field.name}",
                    maximum=MAX_COST_NANOS,
                )
        if self.successful_calls + self.failed_calls != self.calls:
            raise ValueError("Provider usage aggregate call totals are contradictory.")


@dataclass(frozen=True, slots=True)
class UsageTimeBucket:
    started_at: float
    ended_at: float
    requests: int
    successful_requests: int
    failed_requests: int
    tokens: int
    cached_tokens: int
    cost_nanos: int

    def __post_init__(self) -> None:
        started_at = _timestamp(self.started_at, "Usage bucket start")
        ended_at = _timestamp(self.ended_at, "Usage bucket end")
        if ended_at <= started_at:
            raise ValueError("Usage bucket interval is invalid.")
        for field in fields(self):
            if field.name not in {"started_at", "ended_at"}:
                _strict_int(
                    getattr(self, field.name),
                    f"Usage bucket {field.name}",
                    maximum=MAX_COST_NANOS,
                )
        if self.successful_requests + self.failed_requests != self.requests:
            raise ValueError("Usage bucket request totals are contradictory.")


@dataclass(frozen=True, slots=True)
class UsageLiabilityPage:
    scanned: int
    complete: bool
    cursor: str | None
    snapshot_digest: str
    active_liability_nanos: int
    active_reservations: int = 0

    def __post_init__(self) -> None:
        _strict_int(self.scanned, "Usage liability page count", maximum=MAX_LIABILITY_PAGE)
        if type(self.complete) is not bool or self.complete != (self.cursor is None):
            raise ValueError("Usage liability page is invalid.")
        if self.cursor is not None and (
            not isinstance(self.cursor, str)
            or not 1 <= len(self.cursor) <= 64
            or not (_EVENT_ID.fullmatch(self.cursor) or _RESERVATION_ID.fullmatch(self.cursor))
        ):
            raise ValueError("Usage liability cursor is invalid.")
        if not isinstance(self.snapshot_digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.snapshot_digest
        ):
            raise ValueError("Usage liability digest is invalid.")
        _strict_int(
            self.active_liability_nanos,
            "Usage active liability",
            maximum=MAX_COST_NANOS,
        )
        _strict_int(
            self.active_reservations,
            "Usage active reservation count",
            maximum=MAX_LIABILITY_PAGE,
        )


def validate_usage_liability_cursor(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not (
        _EVENT_ID.fullmatch(value) or _RESERVATION_ID.fullmatch(value)
    ):
        raise ValueError("Usage liability cursor is invalid.")
    return value


class UsageLedgerRepository(Protocol):
    async def initialize(self) -> None: ...

    async def check_available(self) -> None: ...

    async def append_usage(self, entry: UsageLedgerEntry) -> UsageAppendResult: ...

    async def reserve_budget(
        self, request: BudgetReservationRequest
    ) -> BudgetReservationDecision: ...

    async def commit_reservation(
        self,
        reservation_id: str,
        usage: UsageLedgerEntry,
        *,
        transitioned_at: float,
    ) -> BudgetCommitResult: ...

    async def release_reservation(
        self,
        reservation_id: str,
        *,
        transitioned_at: float,
    ) -> BudgetReleaseResult: ...

    async def reconcile_expired(self, *, now: float, limit: int) -> int: ...

    async def reconciliation_page(self, *, after: str | None, limit: int) -> UsageLiabilityPage: ...

    async def get_spend(self, *, since: float, api_key_id: str = "") -> SpendSnapshot: ...

    async def aggregate_credentials(
        self, *, since: float | None = None
    ) -> list[CredentialUsageAggregate]: ...

    async def aggregate_providers(self) -> list[ProviderUsageAggregate]: ...

    async def aggregate_time_series(
        self, *, since: float, until: float, points: int
    ) -> list[UsageTimeBucket]: ...

    async def retire_credential(
        self,
        credential_ref: str,
        replacement_ref: str,
        *,
        provider: str,
        limit: int,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class UsageLedgerEntry:
    schema_version: int
    event_id: str
    occurred_at: float
    credential_ref: str
    request_id: str
    model: str
    provider: str
    status_code: int
    success: bool
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    estimated_input_tokens: int
    estimated_tokens_saved: int
    compressed_messages: int
    quality_profile: str
    quality_policy_revision: int
    compression_reason: str
    latency_ms: int
    retry_count: int
    cost_nanos: int
    api_key_id: str
    cache_creation_tokens: int = 0
    usage_reported: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != USAGE_LEDGER_SCHEMA_VERSION
        ):
            raise ValueError("Usage ledger schema version is unsupported.")
        if not isinstance(self.event_id, str) or not _EVENT_ID.fullmatch(self.event_id):
            raise ValueError("Usage event ID is invalid.")
        object.__setattr__(self, "occurred_at", _timestamp(self.occurred_at, "Usage timestamp"))
        credential_ref = _bounded_text(
            self.credential_ref, "Usage credential reference", maximum=255, required=True
        )
        if credential_ref in {".", ".."} or "/" in credential_ref or "\\" in credential_ref:
            raise ValueError("Usage credential reference is invalid.")
        if not isinstance(self.request_id, str) or not _SAFE_REQUEST_ID.fullmatch(self.request_id):
            raise ValueError("Usage request ID is invalid.")
        _bounded_text(self.model, "Usage model", maximum=256)
        _bounded_text(self.provider, "Usage provider", maximum=64)
        _strict_int(self.status_code, "Usage status code", minimum=100, maximum=599)
        if type(self.success) is not bool:
            raise ValueError("Usage success flag is invalid.")
        for value, label in (
            (self.input_tokens, "Usage input tokens"),
            (self.output_tokens, "Usage output tokens"),
            (self.total_tokens, "Usage total tokens"),
            (self.cached_tokens, "Usage cached tokens"),
            (self.cache_creation_tokens, "Usage cache creation tokens"),
            (self.reasoning_tokens, "Usage reasoning tokens"),
            (self.estimated_input_tokens, "Usage estimated input tokens"),
            (self.estimated_tokens_saved, "Usage estimated tokens saved"),
            (self.compressed_messages, "Usage compressed messages"),
            (self.latency_ms, "Usage latency"),
            (self.retry_count, "Usage retry count"),
        ):
            _strict_int(value, label, maximum=9_223_372_036_854_775_807)
        if type(self.usage_reported) is not bool:
            raise ValueError("Usage reported flag is invalid.")
        if self.quality_profile not in _QUALITY_PROFILES:
            raise ValueError("Usage quality profile is invalid.")
        _strict_int(
            self.quality_policy_revision,
            "Usage quality policy revision",
            maximum=MAX_POLICY_REVISION,
        )
        if self.compression_reason not in _COMPRESSION_REASONS:
            raise ValueError("Usage compression reason is invalid.")
        _strict_int(self.cost_nanos, "Usage cost", maximum=MAX_COST_NANOS)
        if self.api_key_id and (
            not isinstance(self.api_key_id, str) or not _KEY_ID.fullmatch(self.api_key_id)
        ):
            raise ValueError("Usage virtual-key ID is invalid.")

    def __repr__(self) -> str:
        return (
            "UsageLedgerEntry("
            f"schema_version={self.schema_version!r}, event_id={self.event_id!r}, "
            f"occurred_at={self.occurred_at!r}, attribution=<redacted>, "
            f"success={self.success!r}, total_tokens={self.total_tokens!r}, "
            f"cost_nanos={self.cost_nanos!r})"
        )

    def to_record(self) -> dict[str, object]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


class BudgetReservationState(StrEnum):
    ACTIVE = "active"
    COMMITTED = "committed"
    RELEASED = "released"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class BudgetReservationRequest:
    schema_version: int
    reservation_id: str
    key_id: str
    created_at: float
    expires_at: float
    estimated_tokens: int
    estimated_cost_nanos: int
    daily_budget_nanos: int | None
    monthly_budget_nanos: int | None

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != USAGE_LEDGER_SCHEMA_VERSION
        ):
            raise ValueError("Budget reservation schema version is unsupported.")
        if not isinstance(self.reservation_id, str) or not _RESERVATION_ID.fullmatch(
            self.reservation_id
        ):
            raise ValueError("Budget reservation ID is invalid.")
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("Budget reservation virtual-key ID is invalid.")
        created_at = _timestamp(self.created_at, "Budget reservation creation timestamp")
        expires_at = _timestamp(self.expires_at, "Budget reservation expiry timestamp")
        if not created_at < expires_at <= created_at + MAX_RESERVATION_TTL_SECONDS:
            raise ValueError("Budget reservation expiry is invalid.")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)
        _strict_int(
            self.estimated_tokens,
            "Budget reservation estimated tokens",
            maximum=9_223_372_036_854_775_807,
        )
        _strict_int(
            self.estimated_cost_nanos,
            "Budget reservation estimated cost",
            maximum=MAX_COST_NANOS,
        )
        daily = _optional_cost(self.daily_budget_nanos, "Budget reservation daily limit")
        monthly = _optional_cost(self.monthly_budget_nanos, "Budget reservation monthly limit")
        if daily is None and monthly is None:
            raise ValueError("Budget reservation requires a hard budget.")

    def to_record(self) -> dict[str, object]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    schema_version: int
    reservation_id: str
    key_id: str
    created_at: float
    expires_at: float
    estimated_tokens: int
    estimated_cost_nanos: int
    daily_budget_nanos: int | None
    monthly_budget_nanos: int | None
    state: BudgetReservationState
    revision: int
    transitioned_at: float | None
    usage: UsageLedgerEntry | None

    def __post_init__(self) -> None:
        request = BudgetReservationRequest(
            schema_version=self.schema_version,
            reservation_id=self.reservation_id,
            key_id=self.key_id,
            created_at=self.created_at,
            expires_at=self.expires_at,
            estimated_tokens=self.estimated_tokens,
            estimated_cost_nanos=self.estimated_cost_nanos,
            daily_budget_nanos=self.daily_budget_nanos,
            monthly_budget_nanos=self.monthly_budget_nanos,
        )
        if type(self.state) is not BudgetReservationState:
            raise ValueError("Budget reservation state is invalid.")
        _strict_int(self.revision, "Budget reservation revision", minimum=1, maximum=2)
        if self.state is BudgetReservationState.ACTIVE:
            if self.revision != 1 or self.transitioned_at is not None or self.usage is not None:
                raise ValueError("Active budget reservation evidence is invalid.")
            return
        if self.revision != 2 or self.transitioned_at is None:
            raise ValueError("Terminal budget reservation evidence is invalid.")
        transitioned_at = _timestamp(
            self.transitioned_at, "Budget reservation transition timestamp"
        )
        if transitioned_at < request.created_at:
            raise ValueError("Budget reservation transition timestamp is invalid.")
        object.__setattr__(self, "transitioned_at", transitioned_at)
        if self.state is BudgetReservationState.COMMITTED:
            if type(self.usage) is not UsageLedgerEntry or self.usage.api_key_id != self.key_id:
                raise ValueError("Committed budget reservation usage is invalid.")
            if not request.created_at <= self.usage.occurred_at <= transitioned_at:
                raise ValueError("Committed budget reservation usage timestamp is invalid.")
        elif self.usage is not None:
            raise ValueError("Uncommitted budget reservation cannot contain usage.")
        if self.state is BudgetReservationState.EXPIRED and transitioned_at < request.expires_at:
            raise ValueError("Budget reservation expired before its deadline.")

    @classmethod
    def active(cls, request: BudgetReservationRequest) -> BudgetReservation:
        return cls(
            **request.to_record(),
            state=BudgetReservationState.ACTIVE,
            revision=1,
            transitioned_at=None,
            usage=None,
        )

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "reservation_id": self.reservation_id,
            "key_id": self.key_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "estimated_tokens": self.estimated_tokens,
            "estimated_cost_nanos": self.estimated_cost_nanos,
            "daily_budget_nanos": self.daily_budget_nanos,
            "monthly_budget_nanos": self.monthly_budget_nanos,
            "state": self.state.value,
            "revision": self.revision,
            "transitioned_at": self.transitioned_at,
            "usage": None if self.usage is None else self.usage.to_record(),
        }

    def matches_operation(self, request: BudgetReservationRequest) -> bool:
        """Compare the immutable billable operation fingerprint."""

        return (
            self.schema_version == request.schema_version
            and self.reservation_id == request.reservation_id
            and self.key_id == request.key_id
            and self.estimated_tokens == request.estimated_tokens
            and self.estimated_cost_nanos == request.estimated_cost_nanos
            and self.daily_budget_nanos == request.daily_budget_nanos
            and self.monthly_budget_nanos == request.monthly_budget_nanos
        )

    def admits_delivery_replay(self, request: BudgetReservationRequest) -> bool:
        """Match one completed logical operation inside its bounded replay window.

        Creation/expiry timestamps describe individual delivery attempts and therefore
        are deliberately excluded from the operation fingerprint. The original
        reservation expiry remains the replay deadline.
        """

        return (
            self.state is BudgetReservationState.COMMITTED
            and self.created_at <= request.created_at < self.expires_at
            and self.matches_operation(request)
        )


def _exact_record(record: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(record, Mapping) or set(record) != expected:
        raise ValueError(f"Stored {label} is invalid.")
    return dict(record)


def usage_entry_from_record(record: object) -> UsageLedgerEntry:
    expected = {field.name for field in fields(UsageLedgerEntry)}
    optional_since_r2 = {"cache_creation_tokens", "usage_reported"}
    if not isinstance(record, Mapping):
        raise ValueError("Stored usage entry is invalid.")
    unknown = set(record) - expected
    missing = expected - set(record)
    if unknown or missing - optional_since_r2:
        raise ValueError("Stored usage entry is invalid.")
    values = dict(record)
    values.setdefault("cache_creation_tokens", 0)
    if "usage_reported" not in values:
        values["usage_reported"] = bool(
            values.get("success")
            and any(
                type(values.get(field)) is int and values[field] > 0
                for field in (
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "cached_tokens",
                    "reasoning_tokens",
                )
            )
        )
    try:
        return UsageLedgerEntry(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored usage entry is invalid.") from exc


def budget_reservation_from_record(record: object) -> BudgetReservation:
    values = _exact_record(
        record,
        {field.name for field in fields(BudgetReservation)},
        "budget reservation",
    )
    try:
        values["state"] = BudgetReservationState(values["state"])
        if values["usage"] is not None:
            values["usage"] = usage_entry_from_record(values["usage"])
        return BudgetReservation(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError("Stored budget reservation is invalid.") from exc


def usage_liability_page(
    records: Sequence[UsageLedgerEntry | BudgetReservation],
    *,
    complete: bool,
    cursor: str | None,
) -> UsageLiabilityPage:
    """Build content-addressed, attribution-safe evidence for one bounded ledger page."""

    if not isinstance(records, Sequence) or len(records) > MAX_LIABILITY_PAGE:
        raise ValueError("Usage liability records are invalid.")
    hasher = hashlib.sha256(b"polaris-usage-liability-page-v1\x00")
    liability = 0
    active_reservations = 0
    identifiers: list[str] = []
    for record in records:
        if type(record) is UsageLedgerEntry:
            identifier = record.event_id
            kind = "usage"
        elif type(record) is BudgetReservation:
            identifier = record.reservation_id
            kind = "reservation"
            if record.state is BudgetReservationState.ACTIVE:
                active_reservations += 1
                liability += record.estimated_cost_nanos
                if liability > MAX_COST_NANOS:
                    raise ValueError("Usage active liability is invalid.")
        else:
            raise ValueError("Usage liability record is invalid.")
        identifiers.append(identifier)
        payload = json.dumps(
            {"kind": kind, "record": record.to_record()},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        hasher.update(len(payload).to_bytes(8, "big"))
        hasher.update(payload)
    if identifiers != sorted(set(identifiers)):
        raise ValueError("Usage liability record order is invalid.")
    return UsageLiabilityPage(
        len(records),
        complete,
        cursor,
        hasher.hexdigest(),
        liability,
        active_reservations,
    )
