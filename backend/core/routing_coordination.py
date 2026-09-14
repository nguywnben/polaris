"""Fenced semantic coordination for routing, governance, and cache metadata."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import math
import secrets
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final

from core.coordination import (
    MAX_COORDINATION_INTEGER,
    MAX_PAYLOAD_BYTES,
    CasRequest,
    CasSettlementProof,
    CasSettlementTarget,
    CasSettlementTransition,
    CasSnapshot,
    CoordinationCorruptError,
    CoordinationReconciliationRequiredError,
    CoordinationUnavailableError,
    InvalidationRequest,
    validate_epoch,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAX_COORDINATION_RETRIES: Final = 8
MAX_CREDENTIAL_LEASES: Final = 128
LEASE_MUTATION_LOCK_STRIPES: Final = 64
MAX_LATENCY_SAMPLES: Final = 10
MAX_SHARED_CACHE_CONTENT_BYTES: Final = 10 * 1024
MAX_CREDENTIAL_TTL_SECONDS: Final = 15 * 60
ROUTE_RECORD_TTL_SECONDS: Final = 30 * 86_400
ROUTING_MUTATION_REPLAY_TTL_SECONDS: Final = 60
CACHE_SCOPE_EXACT: Final = "cache-exact"
CACHE_SCOPE_SEMANTIC: Final = "cache-semantic"
GOVERNANCE_SCOPE_CONFIG: Final = "governance-config"
GOVERNANCE_SCOPE_CREDENTIALS: Final = "governance-credentials"
GOVERNANCE_SCOPE_VIRTUAL_KEYS: Final = "governance-virtual-keys"
GOVERNANCE_SCOPE_MODEL_BLACKLIST: Final = "governance-model-blacklist"
GOVERNANCE_SCOPE_MODEL_CATALOG: Final = "governance-model-catalog"

VALID_INVALIDATION_SCOPES: Final = frozenset(
    {
        CACHE_SCOPE_EXACT,
        CACHE_SCOPE_SEMANTIC,
        GOVERNANCE_SCOPE_CONFIG,
        GOVERNANCE_SCOPE_CREDENTIALS,
        GOVERNANCE_SCOPE_VIRTUAL_KEYS,
        GOVERNANCE_SCOPE_MODEL_BLACKLIST,
        GOVERNANCE_SCOPE_MODEL_CATALOG,
    }
)
VALID_FAILURE_KINDS: Final = frozenset(
    {"", "authentication", "model_unavailable", "rate_limited", "transient"}
)
VALID_MEDIA_KINDS: Final = frozenset({"binary", "json", "text"})
_METRIC_OPERATIONS: Final = frozenset(
    {
        "credential_read",
        "lease_acquire",
        "lease_release",
        "route_read",
        "route_record",
        "generation_read",
        "invalidation",
        "cache_publish",
        "cache_resolve",
    }
)
_METRIC_RESULTS: Final = frozenset({"success", "rejected", "hit", "miss", "conflict"})
_METRIC_LOCK = threading.Lock()
_METRICS: dict[tuple[str, str], int] = {}


def _increment_metric(operation: object, result: object) -> None:
    normalized_operation = operation if operation in _METRIC_OPERATIONS else "generation_read"
    normalized_result = result if result in _METRIC_RESULTS else "conflict"
    key = (str(normalized_operation), str(normalized_result))
    with _METRIC_LOCK:
        _METRICS[key] = _METRICS.get(key, 0) + 1


def render_routing_coordination_metrics() -> str:
    """Render fixed-cardinality semantic routing/cache coordination counters."""

    with _METRIC_LOCK:
        snapshot = dict(_METRICS)
    lines = [
        "# HELP polaris_routing_coordination_events_total Routing and cache coordination decisions.",
        "# TYPE polaris_routing_coordination_events_total counter",
    ]
    for (operation, result), count in sorted(snapshot.items()):
        lines.append(
            "polaris_routing_coordination_events_total"
            f'{{operation="{operation}",result="{result}"}} {count}'
        )
    return "\n".join(lines) + "\n"


def clear_routing_coordination_metrics_for_testing() -> None:
    with _METRIC_LOCK:
        _METRICS.clear()


def record_routing_coordination_metric_for_testing(operation: object, result: object) -> None:
    _increment_metric(operation, result)


class CacheKind(str, Enum):
    EXACT = "exact"
    SEMANTIC = "semantic"


@dataclass(frozen=True, slots=True)
class CredentialLease:
    record_key: str = field(repr=False)
    lease_id: str = field(repr=False)
    in_flight: int
    admission: CasRequest | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class CredentialCoordinationSnapshot:
    in_flight: int = 0
    last_selected_ms: int = 0


@dataclass(frozen=True, slots=True)
class RouteOutcomeSnapshot:
    failure_count: int = 0
    failure_kind: str = ""
    retry_after_seconds: float = 0.0
    latency_samples_ms: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class CacheMetadata:
    content_digest: str
    media_kind: str
    generation: int
    content: bytes | None = field(default=None, repr=False)
    media_type: str | None = None


def _require_text(value: object, label: str, *, maximum: int = 255) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise ValueError(f"{label} is invalid.")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{label} is invalid.")
    return value


def _require_positive_number(value: object, label: str, *, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} is invalid.")
    number = float(value)
    if not math.isfinite(number) or not 0 < number <= maximum:
        raise ValueError(f"{label} is invalid.")
    return number


def _encode(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("ascii")


def _decode(payload: bytes, expected_keys: frozenset[str], record_type: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinationCorruptError("Coordination payload is invalid.") from exc
    if (
        not isinstance(value, dict)
        or set(value) != expected_keys
        or value.get("schema_version") != 1
        or value.get("type") != record_type
    ):
        raise CoordinationCorruptError("Coordination payload is invalid.")
    return value


class RoutingCoordinationAdapter:
    """Domain-separated, bounded CAS composition over one selected state store."""

    def __init__(self, store: Any, *, identifier_key: bytes, fencing_epoch: int) -> None:
        if store is None:
            raise ValueError("Coordination store is required.")
        if not isinstance(identifier_key, bytes) or not 32 <= len(identifier_key) <= 64:
            raise ValueError("Coordination identifier key is invalid.")
        self._store = store
        self._identifier_key = bytes(identifier_key)
        self._cache_content_key = hmac.digest(
            self._identifier_key,
            b"polaris:cache-content-encryption:v1\0",
            hashlib.sha256,
        )
        self._fencing_epoch = validate_epoch(fencing_epoch)
        self._lease_mutation_locks = tuple(
            asyncio.Lock() for _index in range(LEASE_MUTATION_LOCK_STRIPES)
        )

    @property
    def fencing_epoch(self) -> int:
        return self._fencing_epoch

    def _digest(self, domain: str, *parts: str) -> str:
        message = bytearray(domain.encode("ascii"))
        for part in parts:
            encoded = part.encode("utf-8")
            message.extend(len(encoded).to_bytes(4, "big"))
            message.extend(encoded)
        return hmac.new(self._identifier_key, message, hashlib.sha256).hexdigest()

    def _lease_key(self, mode: str, filename: str) -> str:
        return "routing-lease:" + self._digest(
            "routing-lease-v1",
            _require_text(mode, "Routing mode", maximum=32),
            _require_text(filename, "Credential name"),
        )

    def _lease_mutation_lock(self, key: str) -> asyncio.Lock:
        stripe = hashlib.sha256(key.encode("ascii")).digest()[0] % len(self._lease_mutation_locks)
        return self._lease_mutation_locks[stripe]

    def _route_key(self, mode: str, filename: str, model_name: str) -> str:
        clean_model = str(model_name or "")
        if len(clean_model) > 255 or any(ord(character) < 32 for character in clean_model):
            raise ValueError("Model name is invalid.")
        return "routing-outcome:" + self._digest(
            "routing-outcome-v1",
            _require_text(mode, "Routing mode", maximum=32),
            _require_text(filename, "Credential name"),
            clean_model,
        )

    def _cache_key(self, kind: CacheKind, cache_key: str) -> str:
        if not isinstance(kind, CacheKind):
            raise ValueError("Cache kind is invalid.")
        return "cache-metadata:" + self._digest(
            "cache-metadata-v1", kind.value, _require_text(cache_key, "Cache key")
        )

    async def _now_ms(self) -> int:
        value = await self._store.read_coordination_time(epoch=self._fencing_epoch)
        return value.milliseconds

    @staticmethod
    def _operation_id(prefix: str) -> str:
        return f"{prefix}-{secrets.token_hex(16)}"

    async def _compare_and_set_with_replay(self, request: CasRequest):
        """Retry one unknown transport outcome with the identical operation ID."""

        try:
            return await self._store.compare_and_set(request)
        except CoordinationReconciliationRequiredError:
            raise
        except CoordinationUnavailableError:
            return await self._store.compare_and_set(request)

    async def _invalidate_with_replay(self, request: InvalidationRequest):
        """Resolve one unknown invalidation outcome through backend replay evidence."""

        try:
            return await self._store.invalidate(request)
        except CoordinationReconciliationRequiredError:
            raise
        except CoordinationUnavailableError:
            return await self._store.invalidate(request)

    @staticmethod
    def _decode_lease(snapshot: CasSnapshot) -> tuple[list[tuple[str, int]], int]:
        if snapshot.payload is None:
            return [], 0
        value = _decode(
            snapshot.payload,
            frozenset({"schema_version", "type", "leases", "last_selected_ms"}),
            "credential_lease",
        )
        leases = value["leases"]
        last_selected = value["last_selected_ms"]
        if (
            not isinstance(leases, list)
            or len(leases) > MAX_CREDENTIAL_LEASES
            or isinstance(last_selected, bool)
            or not isinstance(last_selected, int)
            or not 0 <= last_selected <= MAX_COORDINATION_INTEGER
        ):
            raise CoordinationCorruptError("Credential lease payload is invalid.")
        decoded: list[tuple[str, int]] = []
        seen: set[str] = set()
        for item in leases:
            if not isinstance(item, list) or len(item) != 2:
                raise CoordinationCorruptError("Credential lease payload is invalid.")
            lease_id, expires_ms = item
            if (
                not isinstance(lease_id, str)
                or len(lease_id) != 32
                or any(character not in "0123456789abcdef" for character in lease_id)
                or lease_id in seen
                or isinstance(expires_ms, bool)
                or not isinstance(expires_ms, int)
                or not 0 <= expires_ms <= MAX_COORDINATION_INTEGER
            ):
                raise CoordinationCorruptError("Credential lease payload is invalid.")
            seen.add(lease_id)
            decoded.append((lease_id, expires_ms))
        return decoded, last_selected

    @staticmethod
    def _lease_payload(leases: list[tuple[str, int]], last_selected_ms: int) -> bytes:
        return _encode(
            {
                "schema_version": 1,
                "type": "credential_lease",
                "leases": [[lease_id, expires_ms] for lease_id, expires_ms in leases],
                "last_selected_ms": last_selected_ms,
            }
        )

    async def read_credential(self, mode: str, filename: str) -> CredentialCoordinationSnapshot:
        key = self._lease_key(mode, filename)
        now_ms = await self._now_ms()
        snapshot = await self._store.read_cas(key, epoch=self._fencing_epoch)
        leases, last_selected = self._decode_lease(snapshot)
        active = [lease for lease in leases if lease[1] > now_ms]
        _increment_metric("credential_read", "success")
        return CredentialCoordinationSnapshot(len(active), last_selected)

    async def acquire_credential(
        self,
        mode: str,
        filename: str,
        *,
        ttl_seconds: float,
        max_concurrency: int = MAX_CREDENTIAL_LEASES,
    ) -> CredentialLease | None:
        ttl = _require_positive_number(
            ttl_seconds, "Credential lease TTL", maximum=MAX_CREDENTIAL_TTL_SECONDS
        )
        if (
            isinstance(max_concurrency, bool)
            or not isinstance(max_concurrency, int)
            or not 1 <= max_concurrency <= MAX_CREDENTIAL_LEASES
        ):
            raise ValueError("Credential concurrency is invalid.")
        key = self._lease_key(mode, filename)
        lock = self._lease_mutation_lock(key)
        async with lock:
            lease_id = secrets.token_hex(16)
            for _attempt in range(MAX_COORDINATION_RETRIES):
                now_ms = await self._now_ms()
                snapshot = await self._store.read_cas(key, epoch=self._fencing_epoch)
                leases, _last_selected = self._decode_lease(snapshot)
                active = [lease for lease in leases if lease[1] > now_ms]
                if len(active) >= max_concurrency:
                    _increment_metric("lease_acquire", "rejected")
                    return None
                expires_ms = now_ms + math.ceil(ttl * 1000)
                active.append((lease_id, expires_ms))
                admission = CasRequest(
                    key,
                    snapshot.revision or 0,
                    self._lease_payload(active, now_ms),
                    ROUTE_RECORD_TTL_SECONDS,
                    self._fencing_epoch,
                    self._operation_id("lease-acquire"),
                    settlement_targets=(CasSettlementTarget(key, CasSettlementTransition.UPDATE),),
                    replay_ttl_seconds=max(ttl, ROUTING_MUTATION_REPLAY_TTL_SECONDS),
                )
                result = await self._compare_and_set_with_replay(admission)
                if result.applied:
                    _increment_metric("lease_acquire", "success")
                    return CredentialLease(key, lease_id, len(active), admission)
        _increment_metric("lease_acquire", "conflict")
        raise CoordinationUnavailableError("Credential lease coordination conflicted.")

    async def release_credential(self, lease: CredentialLease) -> bool:
        if not isinstance(lease, CredentialLease):
            raise ValueError("Credential lease is invalid.")
        lock = self._lease_mutation_lock(lease.record_key)
        async with lock:
            for _attempt in range(MAX_COORDINATION_RETRIES):
                now_ms = await self._now_ms()
                snapshot = await self._store.read_cas(lease.record_key, epoch=self._fencing_epoch)
                leases, last_selected = self._decode_lease(snapshot)
                active = [item for item in leases if item[1] > now_ms]
                retained = [item for item in active if item[0] != lease.lease_id]
                if len(retained) == len(active):
                    _increment_metric("lease_release", "miss")
                    return False
                result = await self._compare_and_set_with_replay(
                    CasRequest(
                        lease.record_key,
                        snapshot.revision or 0,
                        self._lease_payload(retained, last_selected),
                        ROUTE_RECORD_TTL_SECONDS,
                        self._fencing_epoch,
                        self._operation_id("lease-release"),
                        settlement=(
                            CasSettlementProof(
                                lease.admission,
                                CasSettlementTarget(
                                    lease.record_key, CasSettlementTransition.UPDATE
                                ),
                            )
                            if lease.admission
                            else None
                        ),
                        replay_ttl_seconds=ROUTING_MUTATION_REPLAY_TTL_SECONDS,
                    )
                )
                if result.applied:
                    _increment_metric("lease_release", "success")
                    return True
        _increment_metric("lease_release", "conflict")
        raise CoordinationUnavailableError("Credential lease coordination conflicted.")

    @staticmethod
    def _decode_route(snapshot: CasSnapshot) -> tuple[int, str, int, list[int]]:
        if snapshot.payload is None:
            return 0, "", 0, []
        value = _decode(
            snapshot.payload,
            frozenset(
                {
                    "schema_version",
                    "type",
                    "failure_count",
                    "failure_kind",
                    "retry_after_ms",
                    "latency_samples_ms",
                }
            ),
            "route_outcome",
        )
        count = value["failure_count"]
        kind = value["failure_kind"]
        retry = value["retry_after_ms"]
        latencies = value["latency_samples_ms"]
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 0 <= count <= MAX_COORDINATION_INTEGER
            or kind not in VALID_FAILURE_KINDS
            or isinstance(retry, bool)
            or not isinstance(retry, int)
            or not 0 <= retry <= MAX_COORDINATION_INTEGER
            or not isinstance(latencies, list)
            or len(latencies) > MAX_LATENCY_SAMPLES
            or any(
                isinstance(item, bool)
                or not isinstance(item, int)
                or not 1 <= item <= MAX_COORDINATION_INTEGER
                for item in latencies
            )
        ):
            raise CoordinationCorruptError("Route outcome payload is invalid.")
        return count, kind, retry, latencies

    @staticmethod
    def _route_payload(count: int, kind: str, retry_ms: int, latencies: list[int]) -> bytes:
        return _encode(
            {
                "schema_version": 1,
                "type": "route_outcome",
                "failure_count": count,
                "failure_kind": kind,
                "retry_after_ms": retry_ms,
                "latency_samples_ms": latencies,
            }
        )

    async def read_route_outcome(
        self, mode: str, filename: str, model_name: str = ""
    ) -> RouteOutcomeSnapshot:
        key = self._route_key(mode, filename, model_name)
        now_ms = await self._now_ms()
        snapshot = await self._store.read_cas(key, epoch=self._fencing_epoch)
        count, kind, retry_ms, latencies = self._decode_route(snapshot)
        if retry_ms <= now_ms:
            retry_ms = 0
        result = RouteOutcomeSnapshot(
            count,
            kind,
            max(0.0, (retry_ms - now_ms) / 1000),
            tuple(float(value) for value in latencies),
        )
        _increment_metric("route_read", "success")
        return result

    async def record_route_outcome(
        self,
        mode: str,
        filename: str,
        model_name: str,
        *,
        success: bool,
        failure_kind: str,
        retry_after_seconds: float,
        latency_ms: float | None,
    ) -> None:
        if not isinstance(success, bool) or failure_kind not in VALID_FAILURE_KINDS:
            raise ValueError("Route outcome is invalid.")
        retry_seconds = float(retry_after_seconds)
        if not math.isfinite(retry_seconds) or retry_seconds < 0:
            raise ValueError("Route retry delay is invalid.")
        if not success and not failure_kind:
            raise ValueError("Route failure kind is required.")
        latency = None
        if latency_ms is not None:
            latency = round(
                _require_positive_number(latency_ms, "Route latency", maximum=3_600_000)
            )
        key = self._route_key(mode, filename, model_name)
        for _attempt in range(MAX_COORDINATION_RETRIES):
            now_ms = await self._now_ms()
            snapshot = await self._store.read_cas(key, epoch=self._fencing_epoch)
            count, _kind, _retry, latencies = self._decode_route(snapshot)
            if success:
                count, failure_kind, retry_ms = 0, "", 0
            else:
                count = min(MAX_COORDINATION_INTEGER, count + 1)
                retry_ms = min(
                    MAX_COORDINATION_INTEGER,
                    now_ms + math.ceil(retry_seconds * 1000),
                )
            if latency is not None:
                latencies = [*latencies, latency][-MAX_LATENCY_SAMPLES:]
            result = await self._compare_and_set_with_replay(
                CasRequest(
                    key,
                    snapshot.revision or 0,
                    self._route_payload(count, failure_kind, retry_ms, latencies),
                    ROUTE_RECORD_TTL_SECONDS,
                    self._fencing_epoch,
                    self._operation_id("route-outcome"),
                    replay_ttl_seconds=ROUTING_MUTATION_REPLAY_TTL_SECONDS,
                )
            )
            if result.applied:
                _increment_metric("route_record", "success")
                return
        _increment_metric("route_record", "conflict")
        raise CoordinationUnavailableError("Route outcome coordination conflicted.")

    @staticmethod
    def _cache_scope(kind: CacheKind) -> str:
        if kind is CacheKind.EXACT:
            return CACHE_SCOPE_EXACT
        if kind is CacheKind.SEMANTIC:
            return CACHE_SCOPE_SEMANTIC
        raise ValueError("Cache kind is invalid.")

    async def current_generation(self, scope: str) -> int:
        if scope not in VALID_INVALIDATION_SCOPES:
            raise ValueError("Invalidation scope is invalid.")
        await self._now_ms()
        snapshot = await self._store.read_invalidation_generation(scope)
        if snapshot.generation is None:
            _increment_metric("generation_read", "conflict")
            raise CoordinationCorruptError("Invalidation authority is missing.")
        _increment_metric("generation_read", "success")
        return snapshot.generation

    async def invalidate(self, scope: str) -> int:
        if scope not in VALID_INVALIDATION_SCOPES:
            raise ValueError("Invalidation scope is invalid.")
        result = await self._invalidate_with_replay(
            InvalidationRequest(
                scope,
                self._fencing_epoch,
                self._operation_id("invalidate"),
                replay_ttl_seconds=300,
            )
        )
        if not result.applied or result.generation is None:
            _increment_metric("invalidation", "rejected")
            raise CoordinationUnavailableError("Invalidation was not applied.")
        _increment_metric("invalidation", "success")
        return result.generation

    async def publish_cache_metadata(
        self,
        kind: CacheKind,
        cache_key: str,
        *,
        content_digest: str,
        media_kind: str,
        generation: int,
        ttl_seconds: float,
        content: bytes | None = None,
        media_type: str | None = None,
    ) -> bool:
        key = self._cache_key(kind, cache_key)
        if (
            not isinstance(content_digest, str)
            or len(content_digest) != 64
            or any(character not in "0123456789abcdef" for character in content_digest)
            or media_kind not in VALID_MEDIA_KINDS
            or isinstance(generation, bool)
            or not isinstance(generation, int)
            or not 0 <= generation <= MAX_COORDINATION_INTEGER
        ):
            raise ValueError("Cache metadata is invalid.")
        ttl = _require_positive_number(ttl_seconds, "Cache metadata TTL", maximum=30 * 86_400)
        base_payload: dict[str, object] = {
            "schema_version": 1,
            "type": "cache_metadata",
            "kind": kind.value,
            "content_digest": content_digest,
            "media_kind": media_kind,
            "generation": generation,
        }
        payload = _encode(base_payload)
        if content is not None:
            if (
                not isinstance(content, bytes)
                or not isinstance(media_type, str)
                or not 1 <= len(media_type) <= 255
                or any(ord(character) < 32 for character in media_type)
                or hashlib.sha256(
                    len(media_type.encode("utf-8")).to_bytes(4, "big")
                    + media_type.encode("utf-8")
                    + len(content).to_bytes(8, "big")
                    + content
                ).hexdigest()
                != content_digest
            ):
                raise ValueError("Cache content is invalid.")
            if len(content) <= MAX_SHARED_CACHE_CONTENT_BYTES:
                nonce = secrets.token_bytes(12)
                aad = _encode(base_payload)
                sealed = nonce + AESGCM(self._cache_content_key).encrypt(nonce, content, aad)
                shared_payload = {
                    **base_payload,
                    "schema_version": 2,
                    "media_type": media_type,
                    "sealed_content": base64.b64encode(sealed).decode("ascii"),
                }
                encoded_shared = _encode(shared_payload)
                if len(encoded_shared) <= MAX_PAYLOAD_BYTES:
                    payload = encoded_shared
        for _attempt in range(MAX_COORDINATION_RETRIES):
            snapshot = await self._store.read_cas(key, epoch=self._fencing_epoch)
            result = await self._compare_and_set_with_replay(
                CasRequest(
                    key,
                    snapshot.revision or 0,
                    payload,
                    ttl,
                    self._fencing_epoch,
                    self._operation_id("cache-publish"),
                    replay_ttl_seconds=ROUTING_MUTATION_REPLAY_TTL_SECONDS,
                )
            )
            if result.applied:
                _increment_metric("cache_publish", "success")
                return True
        _increment_metric("cache_publish", "conflict")
        raise CoordinationUnavailableError("Cache metadata coordination conflicted.")

    async def resolve_cache_metadata(
        self,
        kind: CacheKind,
        cache_key: str,
        *,
        generation: int,
    ) -> CacheMetadata | None:
        key = self._cache_key(kind, cache_key)
        snapshot = await self._store.read_cas(key, epoch=self._fencing_epoch)
        if snapshot.payload is None:
            _increment_metric("cache_resolve", "miss")
            return None
        try:
            value = json.loads(snapshot.payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CoordinationCorruptError("Cache metadata payload is invalid.") from exc
        base_keys = {
            "schema_version",
            "type",
            "kind",
            "content_digest",
            "media_kind",
            "generation",
        }
        schema_version = value.get("schema_version") if isinstance(value, dict) else None
        expected_keys = (
            base_keys
            if schema_version == 1
            else base_keys
            | {
                "media_type",
                "sealed_content",
            }
        )
        if (
            not isinstance(value, dict)
            or set(value) != expected_keys
            or schema_version not in {1, 2}
            or value.get("type") != "cache_metadata"
        ):
            raise CoordinationCorruptError("Cache metadata payload is invalid.")
        digest = value["content_digest"]
        media_kind = value["media_kind"]
        stored_generation = value["generation"]
        if (
            value["kind"] != kind.value
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or media_kind not in VALID_MEDIA_KINDS
            or isinstance(stored_generation, bool)
            or not isinstance(stored_generation, int)
            or not 0 <= stored_generation <= MAX_COORDINATION_INTEGER
        ):
            raise CoordinationCorruptError("Cache metadata payload is invalid.")
        if stored_generation != generation:
            _increment_metric("cache_resolve", "miss")
            return None
        content = None
        media_type = None
        if schema_version == 2:
            media_type = value["media_type"]
            sealed_content = value["sealed_content"]
            if (
                not isinstance(media_type, str)
                or not 1 <= len(media_type) <= 255
                or any(ord(character) < 32 for character in media_type)
                or not isinstance(sealed_content, str)
            ):
                raise CoordinationCorruptError("Cache metadata payload is invalid.")
            try:
                sealed = base64.b64decode(sealed_content, validate=True)
                if len(sealed) < 29:
                    raise ValueError("sealed cache content is too short")
                base_payload = {key: value[key] for key in base_keys}
                base_payload["schema_version"] = 1
                content = AESGCM(self._cache_content_key).decrypt(
                    sealed[:12],
                    sealed[12:],
                    _encode(base_payload),
                )
            except Exception as exc:
                raise CoordinationCorruptError("Cache content authentication failed.") from exc
            encoded_media = media_type.encode("utf-8")
            actual_digest = hashlib.sha256(
                len(encoded_media).to_bytes(4, "big")
                + encoded_media
                + len(content).to_bytes(8, "big")
                + content
            ).hexdigest()
            normalized_media = (
                "json"
                if "json" in media_type.lower()
                else "text"
                if media_type.lower().startswith("text/")
                else "binary"
            )
            if actual_digest != digest or normalized_media != media_kind:
                raise CoordinationCorruptError("Cache content evidence is invalid.")
        _increment_metric("cache_resolve", "hit")
        return CacheMetadata(digest, media_kind, stored_generation, content, media_type)
