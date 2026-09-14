"""Strict domain contracts for bounded coordination inside one process."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Final, Protocol

COORDINATION_SCHEMA_VERSION = 1
MAX_IDENTIFIER_LENGTH = 128
MAX_PAYLOAD_BYTES = 16 * 1024
MIN_TTL_SECONDS = 1.0
MIN_QUOTA_RESERVATION_TTL_SECONDS: Final[float] = 61.0
MAX_TTL_SECONDS = 30.0 * 86_400.0
MAX_COORDINATION_INTEGER = 2**63 - 1
MAX_CAS_SETTLEMENT_TARGETS: Final[int] = 64


class CoordinationError(RuntimeError):
    """Base error for a coordination backend that cannot safely decide."""


class CoordinationUnavailableError(CoordinationError):
    """The backend was unavailable or returned an unusable response."""


class CoordinationUninitializedError(CoordinationUnavailableError):
    """The coordination namespace has never been explicitly initialized."""


class CoordinationReconciliationRequiredError(CoordinationUnavailableError):
    """Bounded cleanup found more expired state than this mutation may reconcile."""


class CoordinationAdmissionFencedError(CoordinationUnavailableError):
    """The deployment drain atomically closed new admission."""


class CoordinationCorruptError(CoordinationError, ValueError):
    """Stored coordination state did not satisfy the closed version-one schema."""


class EpochState(str, Enum):
    READY = "ready"
    RECONCILING = "reconciling"


def _require_int(value: object, label: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} is invalid.")
    return value


def _require_finite_float(value: object, label: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} is invalid.")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{label} is invalid.")
    return number


def _require_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_IDENTIFIER_LENGTH:
        raise ValueError(f"{label} is invalid.")
    if any(ord(character) < 32 or ord(character) > 126 for character in value):
        raise ValueError(f"{label} is invalid.")
    return value


def validate_epoch(value: object) -> int:
    """Validate an epoch at raw method boundaries and in typed requests."""
    return _require_int(value, "Epoch", minimum=1, maximum=MAX_COORDINATION_INTEGER)


def validate_operation_id(value: object) -> str:
    """Validate a replay identifier at raw method boundaries and in typed requests."""
    return _require_identifier(value, "Operation ID")


def validate_deployment_namespace(value: object) -> str:
    """Validate the human-facing namespace before a backend hashes it for keys."""
    if not isinstance(value, str) or not 3 <= len(value) <= 64:
        raise ValueError("Deployment namespace is invalid.")
    if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in value):
        raise ValueError("Deployment namespace is invalid.")
    return value


@dataclass(frozen=True, slots=True)
class Epoch:
    epoch: int
    state: EpochState

    def __post_init__(self) -> None:
        validate_epoch(self.epoch)
        if not isinstance(self.state, EpochState):
            raise ValueError("Epoch state is invalid.")


@dataclass(frozen=True, slots=True)
class CoordinationTime:
    """Backend-owned monotonic-enough coordination clock in whole milliseconds."""

    milliseconds: int

    def __post_init__(self) -> None:
        _require_int(
            self.milliseconds,
            "Coordination time",
            minimum=0,
            maximum=MAX_COORDINATION_INTEGER,
        )


ADMISSION_FENCE_KEY: Final = "ha-runtime-drain-v1"
ADMISSION_BINDING_KEY: Final = "ha-runtime-binding-v1"


def decode_admission_json(value: object) -> dict[str, object]:
    """Bound and reject ambiguous JSON before validating either admission record."""
    if isinstance(value, (str, bytes)):
        if len(value) > MAX_PAYLOAD_BYTES:
            raise ValueError("Coordination admission record is invalid.")

        def unique_pairs(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError("Coordination admission record is invalid.")
                result[key] = item
            return result

        value = json.loads(value, object_pairs_hook=unique_pairs)
    if not isinstance(value, dict):
        raise ValueError("Coordination admission record is invalid.")
    return value


@dataclass(frozen=True, slots=True)
class AdmissionFence:
    namespace_digest: str = field(repr=False)
    epoch: int
    reconciliation_receipt_checksum: str | None = field(repr=False)
    reconciliation_complete: bool
    schema_version: int = 3

    def encode(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def decode(cls, value: object) -> AdmissionFence:
        try:
            value = decode_admission_json(value)
            if set(value) != {
                "schema_version",
                "namespace_digest",
                "epoch",
                "reconciliation_receipt_checksum",
                "reconciliation_complete",
            }:
                raise ValueError
            return cls(**value)
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise CoordinationCorruptError("Coordination drain record is invalid.") from None

    def __post_init__(self) -> None:
        validate_epoch(self.epoch)
        checksum = self.reconciliation_receipt_checksum
        if (
            type(self.schema_version) is not int
            or self.schema_version != 3
            or not isinstance(self.namespace_digest, str)
            or len(self.namespace_digest) != 64
            or any(char not in "0123456789abcdef" for char in self.namespace_digest)
            or type(self.reconciliation_complete) is not bool
            or self.reconciliation_complete != (checksum is not None)
            or (
                checksum is not None
                and (
                    not isinstance(checksum, str)
                    or len(checksum) != 64
                    or any(char not in "0123456789abcdef" for char in checksum)
                )
            )
        ):
            raise ValueError("Coordination drain record is invalid.")


class CasSettlementTransition(str, Enum):
    CREATE = "create"
    UPDATE = "update"


@dataclass(frozen=True, slots=True)
class CasSettlementTarget:
    """One exact logical key and CAS transition an admission may later settle."""

    key: str = field(repr=False)
    transition: CasSettlementTransition

    def __post_init__(self) -> None:
        _require_identifier(self.key, "CAS settlement key")
        if type(self.transition) is not CasSettlementTransition:
            raise ValueError("CAS settlement transition is invalid.")

    @classmethod
    def from_request(cls, request: CasRequest) -> CasSettlementTarget:
        return cls(
            request.key,
            CasSettlementTransition.CREATE
            if request.expected_revision == 0
            else CasSettlementTransition.UPDATE,
        )


@dataclass(frozen=True, slots=True)
class CasRequest:
    key: str = field(repr=False)
    expected_revision: int
    payload: bytes = field(repr=False)
    ttl_seconds: float
    epoch: int
    operation_id: str = field(repr=False)
    settlement_targets: tuple[CasSettlementTarget, ...] = field(default=(), repr=False)
    settlement: CasSettlementProof | None = field(default=None, repr=False)
    replay_ttl_seconds: float | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _require_identifier(self.key, "Coordination key")
        _require_int(
            self.expected_revision,
            "Expected revision",
            minimum=0,
            maximum=MAX_COORDINATION_INTEGER,
        )
        if not isinstance(self.payload, bytes) or len(self.payload) > MAX_PAYLOAD_BYTES:
            raise ValueError("Coordination payload is invalid.")
        _require_finite_float(
            self.ttl_seconds,
            "Coordination TTL",
            minimum=MIN_TTL_SECONDS,
            maximum=MAX_TTL_SECONDS,
        )
        validate_epoch(self.epoch)
        validate_operation_id(self.operation_id)
        if self.replay_ttl_seconds is not None:
            _require_finite_float(
                self.replay_ttl_seconds,
                "Coordination replay TTL",
                minimum=MIN_TTL_SECONDS,
                maximum=MAX_TTL_SECONDS,
            )
        if (
            type(self.settlement_targets) is not tuple
            or len(self.settlement_targets) > MAX_CAS_SETTLEMENT_TARGETS
            or any(type(target) is not CasSettlementTarget for target in self.settlement_targets)
            or len(set(self.settlement_targets)) != len(self.settlement_targets)
        ):
            raise ValueError("CAS settlement targets are invalid.")
        if self.settlement is not None and (
            type(self.settlement) is not CasSettlementProof
            or self.settlement.admission.epoch != self.epoch
            or self.settlement_targets
        ):
            raise ValueError("CAS settlement proof is invalid.")

    @property
    def effective_replay_ttl_seconds(self) -> float:
        """Retention for idempotency evidence, independent of record lifetime."""

        return float(
            self.ttl_seconds if self.replay_ttl_seconds is None else self.replay_ttl_seconds
        )


@dataclass(frozen=True, slots=True)
class CasSettlementProof:
    """Exact accepted admission request; the store verifies its retained success atomically.

    Domain settlement APIs own this evidence, never an HTTP caller-controlled bypass flag.
    """

    admission: CasRequest = field(repr=False)
    target: CasSettlementTarget = field(repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.admission) is not CasRequest
            or self.admission.settlement is not None
            or type(self.target) is not CasSettlementTarget
            or self.target not in self.admission.settlement_targets
        ):
            raise ValueError("CAS settlement proof is invalid.")


@dataclass(frozen=True, slots=True)
class CasResult:
    applied: bool
    revision: int | None
    idempotent: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.applied, bool) or not isinstance(self.idempotent, bool):
            raise ValueError("CAS result is invalid.")
        if self.revision is None:
            if self.applied:
                raise ValueError("CAS result is invalid.")
            return
        _require_int(
            self.revision,
            "CAS revision",
            minimum=1,
            maximum=MAX_COORDINATION_INTEGER,
        )


@dataclass(frozen=True, slots=True)
class CasSnapshot:
    """One fenced CAS record; both fields are ``None`` when the key is absent."""

    revision: int | None
    payload: bytes | None = field(repr=False)

    def __post_init__(self) -> None:
        if (self.revision is None) != (self.payload is None):
            raise ValueError("CAS snapshot is invalid.")
        if self.revision is not None:
            _require_int(
                self.revision,
                "CAS revision",
                minimum=1,
                maximum=MAX_COORDINATION_INTEGER,
            )
        if self.payload is not None and (
            not isinstance(self.payload, bytes) or len(self.payload) > MAX_PAYLOAD_BYTES
        ):
            raise ValueError("CAS snapshot is invalid.")


@dataclass(frozen=True, slots=True)
class InvalidationRequest:
    scope: str = field(repr=False)
    epoch: int
    operation_id: str = field(repr=False)
    replay_ttl_seconds: float = MIN_TTL_SECONDS

    def __post_init__(self) -> None:
        _require_identifier(self.scope, "Invalidation scope")
        validate_epoch(self.epoch)
        validate_operation_id(self.operation_id)
        _require_finite_float(
            self.replay_ttl_seconds,
            "Replay TTL",
            minimum=MIN_TTL_SECONDS,
            maximum=MAX_TTL_SECONDS,
        )


@dataclass(frozen=True, slots=True)
class InvalidationResult:
    applied: bool
    generation: int | None
    idempotent: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.applied, bool) or not isinstance(self.idempotent, bool):
            raise ValueError("Invalidation result is invalid.")
        if self.generation is None:
            if self.applied:
                raise ValueError("Invalidation result is invalid.")
            return
        _require_int(
            self.generation,
            "Invalidation generation",
            minimum=1,
            maximum=MAX_COORDINATION_INTEGER,
        )


@dataclass(frozen=True, slots=True)
class InvalidationGeneration:
    """The current generation for one scope; ``None`` means no invalidation yet."""

    generation: int | None

    def __post_init__(self) -> None:
        if self.generation is not None:
            _require_int(
                self.generation,
                "Invalidation generation",
                minimum=1,
                maximum=MAX_COORDINATION_INTEGER,
            )


@dataclass(frozen=True, slots=True)
class QuotaReservationRequest:
    """One atomic request against a virtual key's active quota windows."""

    reservation_id: str
    key_id: str
    now: float
    ttl_seconds: float
    estimated_tokens: int
    estimated_cost_usd: float
    rpm_limit: int | None
    tpm_limit: int | None
    daily_budget_usd: float | None
    monthly_budget_usd: float | None
    daily_spend_usd: float
    monthly_spend_usd: float
    daily_snapshot_started_at: float
    monthly_snapshot_started_at: float
    fencing_epoch: int = 1
    operation_id: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.reservation_id, "Reservation ID")
        _require_identifier(self.key_id, "Quota key ID")
        _require_finite_float(self.now, "Quota time", minimum=0.0, maximum=MAX_COORDINATION_INTEGER)
        _require_finite_float(
            self.ttl_seconds,
            "Quota TTL",
            minimum=MIN_QUOTA_RESERVATION_TTL_SECONDS,
            maximum=MAX_TTL_SECONDS,
        )
        _require_int(
            self.estimated_tokens, "Estimated tokens", minimum=0, maximum=MAX_COORDINATION_INTEGER
        )
        for value, label in (
            (self.estimated_cost_usd, "Estimated cost"),
            (self.daily_spend_usd, "Daily spend"),
            (self.monthly_spend_usd, "Monthly spend"),
            (self.daily_snapshot_started_at, "Daily snapshot time"),
            (self.monthly_snapshot_started_at, "Monthly snapshot time"),
        ):
            _require_finite_float(
                value, label, minimum=0.0, maximum=float(MAX_COORDINATION_INTEGER)
            )
        if not self.monthly_snapshot_started_at <= self.daily_snapshot_started_at <= self.now:
            raise ValueError("Quota snapshot times are invalid.")
        for value, label in ((self.rpm_limit, "RPM limit"), (self.tpm_limit, "TPM limit")):
            if value is not None:
                _require_int(value, label, minimum=1, maximum=MAX_COORDINATION_INTEGER)
        for value, label in (
            (self.daily_budget_usd, "Daily budget"),
            (self.monthly_budget_usd, "Monthly budget"),
        ):
            if value is not None:
                _require_finite_float(
                    value, label, minimum=0.0, maximum=float(MAX_COORDINATION_INTEGER)
                )
        validate_epoch(self.fencing_epoch)
        if self.operation_id is not None:
            validate_operation_id(self.operation_id)


@dataclass(frozen=True, slots=True)
class QuotaReconciliationResult:
    """One bounded page of quota-state migration evidence."""

    scanned: int
    complete: bool
    cursor: str | None
    snapshot_digest: str

    def __post_init__(self) -> None:
        _require_int(self.scanned, "Quota reconciliation count", minimum=0, maximum=256)
        if not isinstance(self.complete, bool) or self.complete != (self.cursor is None):
            raise ValueError("Quota reconciliation result is invalid.")
        if self.cursor is not None and (
            not isinstance(self.cursor, str)
            or not 1 <= len(self.cursor) <= 2048
            or any(
                not (character.isascii() and (character.isalnum() or character in "-_"))
                for character in self.cursor
            )
        ):
            raise ValueError("Quota reconciliation result is invalid.")
        if (
            not isinstance(self.snapshot_digest, str)
            or len(self.snapshot_digest) != 64
            or any(character not in "0123456789abcdef" for character in self.snapshot_digest)
            or self.snapshot_digest == "0" * 64
        ):
            raise ValueError("Quota reconciliation result is invalid.")


@dataclass(frozen=True, slots=True)
class QuotaReservationDecision:
    accepted: bool
    reservation_id: str
    reason: str = ""
    retry_after_seconds: int = 0
    idempotent: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool) or not isinstance(self.idempotent, bool):
            raise ValueError("Quota decision is invalid.")
        _require_identifier(self.reservation_id, "Reservation ID")
        denied_reasons = {
            "rpm",
            "tpm",
            "daily_budget",
            "monthly_budget",
            "reconciling",
            "stale_epoch",
            "capacity",
            "reconciliation_required",
            "conflict",
        }
        if not isinstance(self.reason, str):
            raise ValueError("Quota decision is invalid.")
        retry_after = _require_int(
            self.retry_after_seconds, "Retry-after", minimum=0, maximum=MAX_COORDINATION_INTEGER
        )
        if self.accepted:
            if self.reason or retry_after:
                raise ValueError("Quota decision is invalid.")
            return
        if self.reason not in denied_reasons:
            raise ValueError("Quota decision is invalid.")
        if (self.reason in {"rpm", "tpm"}) != (retry_after > 0):
            raise ValueError("Quota decision is invalid.")


@dataclass(frozen=True, slots=True)
class QuotaCommitRequest:
    reservation_id: str
    now: float
    actual_tokens: int | None
    actual_cost_usd: float | None
    durable_cost_recorded: bool
    fencing_epoch: int = 1
    operation_id: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.reservation_id, "Reservation ID")
        _require_finite_float(self.now, "Quota time", minimum=0.0, maximum=MAX_COORDINATION_INTEGER)
        if self.actual_tokens is not None:
            _require_int(
                self.actual_tokens, "Actual tokens", minimum=0, maximum=MAX_COORDINATION_INTEGER
            )
        if self.actual_cost_usd is not None:
            _require_finite_float(
                self.actual_cost_usd,
                "Actual cost",
                minimum=0.0,
                maximum=float(MAX_COORDINATION_INTEGER),
            )
        if not isinstance(self.durable_cost_recorded, bool):
            raise ValueError("Durable cost state is invalid.")
        validate_epoch(self.fencing_epoch)
        if self.operation_id is not None:
            validate_operation_id(self.operation_id)


@dataclass(frozen=True, slots=True)
class QuotaCommitResult:
    committed: bool
    overspent: bool = False
    idempotent: bool = False

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, bool) for value in (self.committed, self.overspent, self.idempotent)
        ):
            raise ValueError("Quota commit result is invalid.")
        if not self.committed and self.overspent:
            raise ValueError("Quota commit result is invalid.")


def _require_reply_fields(reply: object, expected: frozenset[str]) -> Mapping[str, object]:
    if not isinstance(reply, Mapping) or set(reply) != expected:
        raise CoordinationCorruptError("Coordination reply is invalid.")
    schema_version = reply.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != COORDINATION_SCHEMA_VERSION
    ):
        raise CoordinationCorruptError("Coordination reply is invalid.")
    return reply


def decode_epoch(reply: object) -> Epoch:
    """Decode a closed-schema stored epoch record, failing closed on corruption."""
    data = _require_reply_fields(reply, frozenset({"schema_version", "epoch", "state"}))
    try:
        return Epoch(epoch=data["epoch"], state=EpochState(data["state"]))
    except (TypeError, ValueError) as exc:
        raise CoordinationCorruptError("Coordination epoch reply is invalid.") from exc


def decode_cas_result(reply: object) -> CasResult:
    """Decode the exact transport-neutral stored result for a CAS mutation."""
    data = _require_reply_fields(
        reply, frozenset({"schema_version", "applied", "revision", "idempotent"})
    )
    try:
        return CasResult(
            applied=data["applied"], revision=data["revision"], idempotent=data["idempotent"]
        )
    except (TypeError, ValueError) as exc:
        raise CoordinationCorruptError("Coordination CAS reply is invalid.") from exc


def decode_invalidation_result(reply: object) -> InvalidationResult:
    """Decode the exact transport-neutral stored result for an invalidation mutation."""
    data = _require_reply_fields(
        reply, frozenset({"schema_version", "applied", "generation", "idempotent"})
    )
    try:
        return InvalidationResult(
            applied=data["applied"],
            generation=data["generation"],
            idempotent=data["idempotent"],
        )
    except (TypeError, ValueError) as exc:
        raise CoordinationCorruptError("Coordination invalidation reply is invalid.") from exc


def decode_invalidation_generation(reply: object) -> InvalidationGeneration:
    """Decode the exact transport-neutral result of a non-mutating generation read."""
    data = _require_reply_fields(reply, frozenset({"schema_version", "generation"}))
    try:
        return InvalidationGeneration(generation=data["generation"])
    except (TypeError, ValueError) as exc:
        raise CoordinationCorruptError(
            "Coordination invalidation generation reply is invalid."
        ) from exc


class CoordinationStore(Protocol):
    """The fenced coordination operations shared by every backend implementation."""

    async def initialize_epoch(self) -> Epoch: ...

    async def read_epoch(self) -> Epoch: ...

    async def read_coordination_time(self, *, epoch: int) -> CoordinationTime: ...

    async def advance_epoch(self, expected_epoch: int, operation_id: str) -> Epoch: ...

    async def mark_epoch_ready(self, epoch: int, operation_id: str) -> Epoch: ...

    async def complete_admission_drain(
        self, fence: AdmissionFence, *, epoch: int, operation_id: str
    ) -> None: ...

    async def compare_and_set(self, request: CasRequest) -> CasResult: ...

    async def read_cas(self, key: str, *, epoch: int) -> CasSnapshot: ...

    async def invalidate(self, request: InvalidationRequest) -> InvalidationResult: ...

    async def read_invalidation_generation(self, scope: str) -> InvalidationGeneration: ...

    async def reserve_quota(self, request: QuotaReservationRequest) -> QuotaReservationDecision: ...

    async def commit_quota(self, request: QuotaCommitRequest) -> QuotaCommitResult: ...

    async def release_quota(
        self,
        reservation_id: str,
        *,
        now: float,
        fencing_epoch: int = 1,
        operation_id: str | None = None,
    ) -> bool: ...

    async def reconcile_quota_state(
        self,
        *,
        epoch: int,
        cursor: str | None,
        limit: int,
        apply: bool,
        operation_id: str | None = None,
    ) -> QuotaReconciliationResult: ...

    async def close(self) -> None: ...
