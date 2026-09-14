"""Versioned, bounded, content-free request decision trace contract."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

REQUEST_TRACE_SCHEMA_VERSION = 1
MAX_TRACE_DECISIONS = 64
MAX_TRACE_DURATION_MS = 86_400_000
MAX_TRACE_TOKENS = 2_000_000_000
MAX_TRACE_COST_USD = 1_000_000.0
MIN_TRACE_RETENTION_DAYS = 1
MAX_TRACE_RETENTION_DAYS = 90
MIN_TRACE_RETENTION_COUNT = 1_000
MAX_TRACE_RETENTION_COUNT = 1_000_000

REQUEST_TRACE_PROTOCOLS = frozenset(
    {
        "openai_chat",
        "openai_responses",
        "anthropic_messages",
        "anthropic_count_tokens",
        "gemini_generate",
        "gemini_stream",
        "gemini_count_tokens",
        "vertex_openai",
        "vertex_gemini_generate",
        "vertex_gemini_stream",
        "vertex_gemini_count_tokens",
    }
)
REQUEST_TRACE_OUTCOMES = frozenset(
    {
        "succeeded",
        "client_error",
        "denied",
        "rate_limited",
        "upstream_error",
        "unavailable",
        "internal_error",
        "cancelled",
    }
)
TRACE_DECISION_CATEGORIES = frozenset(
    {
        "request",
        "routing",
        "fallback",
        "retry",
        "cooldown",
        "compression",
        "guardrail",
        "cache",
        "quota",
        "upstream",
        "usage",
        "outcome",
    }
)
TRACE_DECISION_ACTIONS = frozenset(
    {
        "accepted",
        "selected",
        "unavailable",
        "attempted",
        "switched",
        "scheduled",
        "exhausted",
        "applied",
        "skipped",
        "evaluated",
        "blocked",
        "masked",
        "hit",
        "miss",
        "stored",
        "reserved",
        "denied",
        "committed",
        "released",
        "succeeded",
        "failed",
        "recorded",
        "completed",
        "cancelled",
    }
)
TRACE_DECISION_RESULTS = frozenset(
    {"succeeded", "failed", "skipped", "allowed", "denied", "hit", "miss"}
)
TRACE_REASON_CODES = frozenset(
    {
        "none",
        "request_received",
        "feature_disabled",
        "not_eligible",
        "healthy_candidate",
        "no_candidate",
        "provider_fallback",
        "credential_switched",
        "retryable_status",
        "retry_limit",
        "cooldown_active",
        "quota_cooldown",
        "model_cooldown",
        "history_within_limit",
        "token_budget",
        "content_limit",
        "policy_unavailable",
        "policy_passed",
        "pii_masked",
        "injection_detected",
        "blocked_keyword",
        "cache_hit",
        "cache_miss",
        "cache_stored",
        "quota_reserved",
        "quota_exceeded",
        "budget_exceeded",
        "provider_error",
        "rate_limited",
        "timeout",
        "model_unavailable",
        "usage_recorded",
        "completed",
        "client_error",
        "server_error",
        "cancelled",
    }
)

_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SAFE_DIMENSION = re.compile(r"^[A-Za-z0-9._:/+@*-]{1,128}$")


def _normalize_timestamp(value: str | datetime, field_name: str) -> str:
    try:
        timestamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid request trace {field_name}.") from exc
    if timestamp.tzinfo is None:
        raise ValueError(f"Request trace {field_name} must be timezone-aware.")
    return timestamp.astimezone(timezone.utc).isoformat()


def _require_vocabulary(value: Any, vocabulary: frozenset[str], field_name: str) -> str:
    candidate = str(value or "")
    if candidate not in vocabulary:
        raise ValueError(f"Invalid request trace {field_name}.")
    return candidate


def _optional_dimension(value: Any, field_name: str) -> str:
    candidate = str(value or "")
    if candidate and not _SAFE_DIMENSION.fullmatch(candidate):
        raise ValueError(f"Invalid request trace {field_name}.")
    return candidate


def _bounded_int(value: Any, field_name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Invalid request trace {field_name}.")
    return value


@dataclass(frozen=True, slots=True)
class RequestDecision:
    """One allowlisted decision; arbitrary metadata and free text are intentionally absent."""

    sequence: int
    elapsed_ms: int
    category: str
    action: str
    result: str
    reason: str = "none"
    provider: str = ""
    model: str = ""
    attempt: int = 0
    status_code: int = 0
    latency_ms: int = 0
    candidate_count: int = 0
    original_tokens: int = 0
    final_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _bounded_int(self.sequence, "sequence", 1, 64))
        object.__setattr__(
            self,
            "elapsed_ms",
            _bounded_int(self.elapsed_ms, "elapsed time", 0, MAX_TRACE_DURATION_MS),
        )
        object.__setattr__(
            self,
            "category",
            _require_vocabulary(self.category, TRACE_DECISION_CATEGORIES, "decision category"),
        )
        object.__setattr__(
            self,
            "action",
            _require_vocabulary(self.action, TRACE_DECISION_ACTIONS, "decision action"),
        )
        object.__setattr__(
            self,
            "result",
            _require_vocabulary(self.result, TRACE_DECISION_RESULTS, "decision result"),
        )
        object.__setattr__(
            self,
            "reason",
            _require_vocabulary(self.reason, TRACE_REASON_CODES, "decision reason"),
        )
        object.__setattr__(self, "provider", _optional_dimension(self.provider, "provider"))
        object.__setattr__(self, "model", _optional_dimension(self.model, "model"))
        object.__setattr__(self, "attempt", _bounded_int(self.attempt, "attempt", 0, 32))
        if self.status_code != 0:
            _bounded_int(self.status_code, "status code", 100, 599)
        for field_name in (
            "latency_ms",
            "original_tokens",
            "final_tokens",
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "reasoning_tokens",
        ):
            upper = MAX_TRACE_DURATION_MS if field_name == "latency_ms" else MAX_TRACE_TOKENS
            _bounded_int(getattr(self, field_name), field_name, 0, upper)
        _bounded_int(self.candidate_count, "candidate count", 0, 10_000)
        if (
            isinstance(self.cost_usd, bool)
            or not isinstance(self.cost_usd, (int, float))
            or not math.isfinite(float(self.cost_usd))
            or not 0 <= float(self.cost_usd) <= MAX_TRACE_COST_USD
        ):
            raise ValueError("Invalid request trace cost.")
        object.__setattr__(self, "cost_usd", round(float(self.cost_usd), 8))

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


_TRACE_FIELDS = {
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
}
_DECISION_FIELDS = set(RequestDecision.__dataclass_fields__)


@dataclass(frozen=True, slots=True)
class RequestTrace:
    schema_version: int
    trace_id: str
    request_id: str
    protocol: str
    started_at: str
    completed_at: str
    outcome: str
    status_code: int
    duration_ms: int
    requested_model: str = ""
    selected_provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    decisions: tuple[RequestDecision, ...] = ()
    decisions_truncated: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != REQUEST_TRACE_SCHEMA_VERSION:
            raise ValueError("Unsupported request trace schema version.")
        if not _TRACE_ID.fullmatch(str(self.trace_id or "")):
            raise ValueError("Invalid request trace ID.")
        if not _REQUEST_ID.fullmatch(str(self.request_id or "")):
            raise ValueError("Invalid request trace request ID.")
        object.__setattr__(
            self,
            "protocol",
            _require_vocabulary(self.protocol, REQUEST_TRACE_PROTOCOLS, "protocol"),
        )
        started_at = _normalize_timestamp(self.started_at, "start timestamp")
        completed_at = _normalize_timestamp(self.completed_at, "completion timestamp")
        if datetime.fromisoformat(completed_at) < datetime.fromisoformat(started_at):
            raise ValueError("Request trace completion precedes its start.")
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "completed_at", completed_at)
        object.__setattr__(
            self,
            "outcome",
            _require_vocabulary(self.outcome, REQUEST_TRACE_OUTCOMES, "outcome"),
        )
        _bounded_int(self.status_code, "status code", 100, 599)
        _bounded_int(self.duration_ms, "duration", 0, MAX_TRACE_DURATION_MS)
        object.__setattr__(
            self, "requested_model", _optional_dimension(self.requested_model, "requested model")
        )
        object.__setattr__(
            self,
            "selected_provider",
            _optional_dimension(self.selected_provider, "selected provider"),
        )
        for field_name in ("input_tokens", "output_tokens", "total_tokens"):
            _bounded_int(getattr(self, field_name), field_name, 0, MAX_TRACE_TOKENS)
        if self.total_tokens and self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("Request trace token totals are inconsistent.")
        if len(self.decisions) > MAX_TRACE_DECISIONS or any(
            not isinstance(item, RequestDecision) for item in self.decisions
        ):
            raise ValueError("Request trace decisions are invalid or exceed the bound.")
        if tuple(item.sequence for item in self.decisions) != tuple(
            range(1, len(self.decisions) + 1)
        ):
            raise ValueError("Request trace decision sequence is invalid.")
        if type(self.decisions_truncated) is not bool:
            raise ValueError("Invalid request trace truncation flag.")
        if (
            isinstance(self.cost_usd, bool)
            or not isinstance(self.cost_usd, (int, float))
            or not math.isfinite(float(self.cost_usd))
            or not 0 <= float(self.cost_usd) <= MAX_TRACE_COST_USD
        ):
            raise ValueError("Invalid request trace cost.")
        object.__setattr__(self, "cost_usd", round(float(self.cost_usd), 8))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "protocol": self.protocol,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "outcome": self.outcome,
            "status_code": self.status_code,
            "duration_ms": self.duration_ms,
            "requested_model": self.requested_model,
            "selected_provider": self.selected_provider,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "decisions": [decision.to_record() for decision in self.decisions],
            "decisions_truncated": self.decisions_truncated,
        }


def request_trace_from_record(record: Mapping[str, Any]) -> RequestTrace:
    """Strictly revalidate an untrusted durable record."""
    if not isinstance(record, Mapping) or set(record) != _TRACE_FIELDS:
        raise ValueError("Invalid stored request trace shape.")
    decisions = record["decisions"]
    if not isinstance(decisions, (list, tuple)):
        raise ValueError("Invalid stored request trace decisions.")
    parsed: list[RequestDecision] = []
    for decision in decisions:
        if not isinstance(decision, Mapping) or set(decision) != _DECISION_FIELDS:
            raise ValueError("Invalid stored request trace decision shape.")
        parsed.append(RequestDecision(**decision))
    return RequestTrace(
        **{key: record[key] for key in _TRACE_FIELDS - {"decisions"}},
        decisions=tuple(parsed),
    )


@dataclass(frozen=True, slots=True)
class RequestTraceQuery:
    trace_ids: tuple[str, ...] = ()
    protocols: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    providers: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    request_id: str | None = None
    started_after: datetime | None = None
    started_before: datetime | None = None
    page_size: int = 50
    cursor: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.trace_ids, tuple) or len(self.trace_ids) > 32:
            raise ValueError("Invalid request trace ID filter.")
        normalized_trace_ids = tuple(dict.fromkeys(str(value or "") for value in self.trace_ids))
        if any(not _TRACE_ID.fullmatch(value) for value in normalized_trace_ids):
            raise ValueError("Invalid request trace ID filter.")
        object.__setattr__(self, "trace_ids", normalized_trace_ids)
        object.__setattr__(
            self, "protocols", _normalize_filters(self.protocols, REQUEST_TRACE_PROTOCOLS)
        )
        object.__setattr__(
            self, "outcomes", _normalize_filters(self.outcomes, REQUEST_TRACE_OUTCOMES)
        )
        object.__setattr__(self, "providers", _normalize_dimensions(self.providers, "provider"))
        object.__setattr__(self, "models", _normalize_dimensions(self.models, "model"))
        if self.request_id is not None and not _REQUEST_ID.fullmatch(str(self.request_id)):
            raise ValueError("Invalid request trace request ID filter.")
        if type(self.page_size) is not int or not 1 <= self.page_size <= 200:
            raise ValueError("Request trace page size must be between 1 and 200.")
        if self.cursor is not None and (
            not isinstance(self.cursor, str) or not 1 <= len(self.cursor) <= 1024
        ):
            raise ValueError("Invalid request trace cursor.")
        after = _normalize_query_time(self.started_after, "start")
        before = _normalize_query_time(self.started_before, "end")
        object.__setattr__(self, "started_after", after)
        object.__setattr__(self, "started_before", before)
        if after is not None and before is not None and after > before:
            raise ValueError("Request trace start filter exceeds its end filter.")


def _normalize_filters(values: tuple[str, ...], vocabulary: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) > 32:
        raise ValueError("Invalid request trace vocabulary filter.")
    return tuple(
        dict.fromkeys(_require_vocabulary(value, vocabulary, "filter") for value in values)
    )


def _normalize_dimensions(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) > 32:
        raise ValueError(f"Invalid request trace {field_name} filter.")
    return tuple(dict.fromkeys(_optional_dimension(value, field_name) for value in values))


def _normalize_query_time(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(_normalize_timestamp(value, f"{field_name} filter"))


@dataclass(frozen=True, slots=True)
class RequestTraceRetentionPolicy:
    retention_days: int = 7
    max_traces: int = 100_000

    def __post_init__(self) -> None:
        _bounded_int(
            self.retention_days,
            "retention days",
            MIN_TRACE_RETENTION_DAYS,
            MAX_TRACE_RETENTION_DAYS,
        )
        _bounded_int(
            self.max_traces,
            "retention trace count",
            MIN_TRACE_RETENTION_COUNT,
            MAX_TRACE_RETENTION_COUNT,
        )


@dataclass(frozen=True, slots=True)
class RequestTracePage:
    traces: tuple[RequestTrace, ...]
    next_cursor: str | None = None


class RequestTraceRepository(Protocol):
    async def append(self, trace: RequestTrace) -> None: ...

    async def query(self, query: RequestTraceQuery) -> RequestTracePage: ...

    async def prune(self, policy: RequestTraceRetentionPolicy, *, now: datetime) -> int: ...


class RequestTraceAlreadyExistsError(RuntimeError):
    pass


def encode_request_trace_cursor(*, started_at: str, trace_id: str, signing_key: bytes) -> str:
    if len(signing_key) < 32:
        raise ValueError("Request trace cursor signing key is too short.")
    payload = json.dumps(
        [_normalize_timestamp(started_at, "cursor"), trace_id], separators=(",", ":")
    ).encode()
    signature = hmac.new(signing_key, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + signature).rstrip(b"=").decode("ascii")


def decode_request_trace_cursor(value: str, *, signing_key: bytes) -> tuple[str, str]:
    if not isinstance(value, str) or len(signing_key) < 32:
        raise ValueError("Invalid request trace cursor.")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload, supplied = raw[:-32], raw[-32:]
        if not hmac.compare_digest(
            supplied, hmac.new(signing_key, payload, hashlib.sha256).digest()
        ):
            raise ValueError
        started_at, trace_id = json.loads(payload)
        if not _TRACE_ID.fullmatch(str(trace_id)):
            raise ValueError
        return _normalize_timestamp(started_at, "cursor"), trace_id
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid request trace cursor.") from exc


def classify_request_protocol(method: str, path: str) -> str | None:
    """Map supported inference paths to a closed protocol vocabulary."""
    if str(method).upper() != "POST":
        return None
    normalized = str(path or "")
    exact = {
        "/v1/chat/completions": "openai_chat",
        "/v1/responses": "openai_responses",
        "/v1/messages": "anthropic_messages",
        "/v1/messages/count_tokens": "anthropic_count_tokens",
        "/vertex/v1/chat/completions": "vertex_openai",
    }
    if normalized in exact:
        return exact[normalized]
    vertex = normalized.startswith("/vertex/")
    if re.fullmatch(r"/(?:vertex/)?v1(?:beta)?/models/.+:generateContent", normalized):
        return "vertex_gemini_generate" if vertex else "gemini_generate"
    if re.fullmatch(r"/(?:vertex/)?v1(?:beta)?/models/.+:streamGenerateContent", normalized):
        return "vertex_gemini_stream" if vertex else "gemini_stream"
    if re.fullmatch(r"/(?:vertex/)?v1(?:beta)?/models/.+:countTokens", normalized):
        return "vertex_gemini_count_tokens" if vertex else "gemini_count_tokens"
    return None
