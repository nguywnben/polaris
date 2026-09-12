"""Virtual API keys with per-key budgets, rate limits, and model allowlists.

Design distilled from LiteLLM's proxy auth (`user_api_key_auth.py` /
`auth_checks.py`) adapted to Omni Gateway's single-process architecture:

- Keys are stored in the storage backend under the ``virtual_keys`` config
  entry. Only the SHA-256 hash of the secret is persisted; the plaintext is
  shown exactly once at creation time.
- RPM, TPM, and budget capacity are reserved atomically before provider work.
  Estimates are committed as actual usage or released at request completion.
- Durable rolling spend comes from ``usage_stats`` and is reconciled with
  in-process reservations so concurrent requests cannot knowingly oversubscribe.
"""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.coordination import validate_epoch
from core.governance_coordination import GovernanceGenerationObserver
from core.pricing import ZERO_COST_PROVIDERS, calculate_cost_usd, find_model_pricing
from core.quality_policy import normalize_compression_restriction
from core.request_trace_service import trace_decision
from core.routing_coordination import GOVERNANCE_SCOPE_VIRTUAL_KEYS
from core.state_store import (
    BaseStateStore,
    InMemoryStateStore,
    QuotaCommitRequest,
    QuotaCommitResult,
    QuotaReservationRequest,
)
from core.token_estimator import estimate_input_tokens
from core.usage_ledger import (
    USAGE_LEDGER_SCHEMA_VERSION,
    BudgetReservationRequest,
    usd_to_nanos,
)
from fastapi import HTTPException, status
from log import log

VIRTUAL_KEYS_CONFIG_KEY = "virtual_keys"
KEY_ID_PREFIX = "vk_"
DAILY_WINDOW_SECONDS = 86_400
MONTHLY_WINDOW_SECONDS = 30 * 86_400
LAST_USED_PERSIST_INTERVAL_SECONDS = 60.0
RESERVATION_TTL_SECONDS = 15 * 60.0
DEFAULT_RESERVED_OUTPUT_TOKENS = 4096
MAX_RESERVED_TOKENS = 2_000_000
MAX_LOCAL_DURABLE_RESERVATIONS = 100_000
VIRTUAL_KEY_SCHEMA_VERSION = 2
MAX_MODEL_PATTERNS = 64
MAX_MODEL_PATTERN_LENGTH = 128
MAX_FALLBACK_PRICE_USD_PER_MILLION = 100_000.0

# Only fields that contribute prompt/context tokens belong in an input reservation.
# Transport and sampling controls (model, stream, temperature, generation config,
# and similar fields) must not consume a customer's TPM or hard-budget allowance.
_INPUT_CONTEXT_FIELDS = (
    "messages",
    "input",
    "prompt",
    "instructions",
    "system",
    "tools",
    "functions",
    "tool_choice",
    "contents",
    "systemInstruction",
    "cachedContent",
    "toolConfig",
    "response_format",
)

INFERENCE_SCOPES = (
    "inference:openai",
    "inference:anthropic",
    "inference:gemini",
)


class QuotaReservationHandle(str):
    """String-compatible reservation identity with terminal replay evidence."""

    replayed: bool

    def __new__(cls, value: str, *, replayed: bool = False):
        instance = super().__new__(cls, value)
        instance.replayed = bool(replayed)
        return instance


MANAGEMENT_SCOPES = ("management:read", "management:write")
VIRTUAL_KEY_SCOPES = INFERENCE_SCOPES + MANAGEMENT_SCOPES
DEFAULT_INFERENCE_SCOPES = INFERENCE_SCOPES
UNKNOWN_PRICING_POLICIES = ("deny", "warn", "fallback")

_GEMINI_MODEL_PATH_RE = re.compile(r"/models/([^/:?]+)")
_MODEL_PATTERN_RE = re.compile(r"^(?=.{1,128}$)(?=.*[A-Za-z0-9])[A-Za-z0-9._:/+*?-]+$")
_QUOTA_METRIC_LOCK = threading.Lock()
_QUOTA_METRICS: Dict[str, int] = {}


class VirtualKeyConflictError(ValueError):
    """Raised when a lifecycle mutation uses a stale record revision."""


def _increment_quota_metric(event: str) -> None:
    with _QUOTA_METRIC_LOCK:
        _QUOTA_METRICS[event] = _QUOTA_METRICS.get(event, 0) + 1


def render_virtual_key_quota_metrics() -> str:
    """Render low-cardinality reservation and pricing-policy counters."""
    with _QUOTA_METRIC_LOCK:
        snapshot = dict(_QUOTA_METRICS)
    lines = [
        "# HELP omni_virtual_key_quota_events_total Virtual-key quota lifecycle events.",
        "# TYPE omni_virtual_key_quota_events_total counter",
    ]
    for event in sorted(snapshot):
        lines.append(f'omni_virtual_key_quota_events_total{{event="{event}"}} {snapshot[event]}')
    return "\n".join(lines) + "\n"


def hash_key(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _key_preview(token: str) -> str:
    if len(token) <= 16:
        return token[:4] + "..."
    return f"{token[:12]}...{token[-4:]}"


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _int_or_none(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def normalize_virtual_key_scopes(value: Any, *, legacy_default: bool = False) -> Tuple[str, ...]:
    if value is None and legacy_default:
        return DEFAULT_INFERENCE_SCOPES
    if not isinstance(value, (list, tuple)):
        raise ValueError("Virtual key scopes must be a list.")
    requested = {str(scope).strip().lower() for scope in value if str(scope).strip()}
    unknown = requested.difference(VIRTUAL_KEY_SCOPES)
    if unknown:
        raise ValueError("Virtual key scopes contain an unknown value.")
    if not requested:
        raise ValueError("At least one virtual key scope is required.")
    if "management:write" in requested and "management:read" not in requested:
        raise ValueError("The management:write scope requires management:read.")
    return tuple(scope for scope in VIRTUAL_KEY_SCOPES if scope in requested)


def normalize_model_patterns(value: Any) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError("Virtual key model patterns must be a list.")
    if len(value) > MAX_MODEL_PATTERNS:
        raise ValueError(f"At most {MAX_MODEL_PATTERNS} model patterns are allowed.")
    normalized: List[str] = []
    seen = set()
    for candidate in value:
        pattern = str(candidate).strip()
        if not _MODEL_PATTERN_RE.fullmatch(pattern):
            raise ValueError("Each model pattern must use only bounded safe glob characters.")
        folded = pattern.lower()
        if folded not in seen:
            normalized.append(pattern)
            seen.add(folded)
    return normalized


def normalize_unknown_pricing_policy(policy: Any, fallback: Any) -> Tuple[str, Optional[float]]:
    normalized_policy = str(policy or "deny").strip().lower()
    if normalized_policy not in UNKNOWN_PRICING_POLICIES:
        raise ValueError("Unknown pricing policy must be deny, warn, or fallback.")
    normalized_fallback = _float_or_none(fallback)
    if normalized_fallback is not None and normalized_fallback > MAX_FALLBACK_PRICE_USD_PER_MILLION:
        raise ValueError("Unknown-pricing fallback price exceeds the supported maximum.")
    if normalized_policy == "fallback" and normalized_fallback is None:
        raise ValueError("A positive fallback price is required for fallback pricing policy.")
    if normalized_policy != "fallback" and fallback is not None and fallback != "":
        raise ValueError("A fallback price is only valid with fallback pricing policy.")
    return normalized_policy, normalized_fallback


@dataclass
class VirtualKey:
    """A single virtual API key record (secret stored as SHA-256 hash)."""

    id: str
    name: str
    key_hash: str
    key_preview: str
    enabled: bool = True
    created_at: float = 0.0
    expires_at: Optional[float] = None
    budget_daily_usd: Optional[float] = None
    budget_monthly_usd: Optional[float] = None
    rpm_limit: Optional[int] = None
    tpm_limit: Optional[int] = None
    allowed_models: List[str] = field(default_factory=list)
    schema_version: int = VIRTUAL_KEY_SCHEMA_VERSION
    scopes: Tuple[str, ...] = DEFAULT_INFERENCE_SCOPES
    unknown_pricing_policy: str = "deny"
    fallback_price_usd_per_million: Optional[float] = None
    compression_policy: str = "inherit"
    last_used_at: Optional[float] = None
    revision: int = 1
    revoked_at: Optional[float] = None

    @property
    def status(self) -> str:
        if self.revoked_at is not None:
            return "revoked"
        if not self.enabled:
            return "disabled"
        if self.is_expired():
            return "expired"
        return "active"

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "key_preview": self.key_preview,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "budget_daily_usd": self.budget_daily_usd,
            "budget_monthly_usd": self.budget_monthly_usd,
            "rpm_limit": self.rpm_limit,
            "tpm_limit": self.tpm_limit,
            "allowed_models": list(self.allowed_models),
            "scopes": list(self.scopes),
            "unknown_pricing_policy": self.unknown_pricing_policy,
            "fallback_price_usd_per_million": self.fallback_price_usd_per_million,
            "compression_policy": self.compression_policy,
            "last_used_at": self.last_used_at,
            "revision": self.revision,
            "revoked_at": self.revoked_at,
            "status": self.status,
        }

    def to_storage_dict(self) -> Dict[str, Any]:
        payload = self.to_public_dict()
        payload.pop("status", None)
        payload["key_hash"] = self.key_hash
        return payload

    @classmethod
    def from_storage_dict(cls, raw: Dict[str, Any]) -> Optional["VirtualKey"]:
        if not isinstance(raw, dict):
            return None
        key_id = str(raw.get("id") or "").strip()
        key_hash = str(raw.get("key_hash") or "").strip()
        if not key_id or not key_hash:
            return None
        raw_version = raw.get("schema_version")
        is_legacy = raw_version is None
        if not is_legacy and raw_version != VIRTUAL_KEY_SCHEMA_VERSION:
            return None
        try:
            scopes = normalize_virtual_key_scopes(raw.get("scopes"), legacy_default=is_legacy)
            allowed_models = normalize_model_patterns(raw.get("allowed_models") or [])
            pricing_policy, fallback_price = normalize_unknown_pricing_policy(
                raw.get("unknown_pricing_policy"),
                raw.get("fallback_price_usd_per_million"),
            )
            return cls(
                id=key_id,
                name=str(raw.get("name") or key_id),
                key_hash=key_hash,
                key_preview=str(raw.get("key_preview") or ""),
                enabled=bool(raw.get("enabled", True)),
                created_at=float(raw.get("created_at") or 0.0),
                expires_at=_float_or_none(raw.get("expires_at")),
                budget_daily_usd=_float_or_none(raw.get("budget_daily_usd")),
                budget_monthly_usd=_float_or_none(raw.get("budget_monthly_usd")),
                rpm_limit=_int_or_none(raw.get("rpm_limit")),
                tpm_limit=_int_or_none(raw.get("tpm_limit")),
                allowed_models=allowed_models,
                schema_version=VIRTUAL_KEY_SCHEMA_VERSION,
                scopes=scopes,
                unknown_pricing_policy=pricing_policy,
                fallback_price_usd_per_million=fallback_price,
                compression_policy=normalize_compression_restriction(
                    raw.get("compression_policy"), layer="virtual-key"
                ),
                last_used_at=_float_or_none(raw.get("last_used_at")),
                revision=max(1, int(raw.get("revision") or 1)),
                revoked_at=_float_or_none(raw.get("revoked_at")),
            )
        except (TypeError, ValueError):
            return None

    def is_expired(self, now: Optional[float] = None) -> bool:
        if self.expires_at is None:
            return False
        return (now if now is not None else time.time()) >= self.expires_at

    def allows_model(self, model: str) -> bool:
        if not self.allowed_models:
            return True
        candidate = str(model or "").strip().lower()
        if not candidate:
            # Requests without a resolvable model (for example ``GET
            # /v1/models``) are allowed; enforcement happens on inference.
            return True
        return any(
            fnmatch.fnmatchcase(candidate, pattern.strip().lower())
            for pattern in self.allowed_models
        )


class VirtualKeyManager:
    """Loads, verifies, and enforces virtual API keys."""

    def __init__(
        self,
        *,
        state_store: Optional[BaseStateStore] = None,
        usage_ledger_service: Any = None,
        fencing_epoch: int = 1,
    ) -> None:
        self._keys_by_hash: Dict[str, VirtualKey] = {}
        self._loaded = False
        self._lock = asyncio.Lock()
        self._state_store = state_store if state_store is not None else InMemoryStateStore()
        self._fencing_epoch = validate_epoch(fencing_epoch)
        self._usage_ledger_service = usage_ledger_service
        self._durable_reservation_ids: set[str] = set()
        self._pending_durable_settlement_ids: set[str] = set()
        self._durable_reservation_expiries: dict[str, float] = {}
        self._durable_tracking_lock = threading.Lock()
        self._generation = GovernanceGenerationObserver(GOVERNANCE_SCOPE_VIRTUAL_KEYS)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def configure_coordination(self, state_store: BaseStateStore, *, fencing_epoch: int) -> None:
        """Bind a lifecycle-owned store before request admission begins."""

        if state_store is None:
            raise ValueError("A coordination store is required.")
        if self._durable_reservation_ids or self._pending_durable_settlement_ids:
            raise RuntimeError("Virtual-key coordination cannot change with active reservations.")
        self._state_store = state_store
        self._fencing_epoch = validate_epoch(fencing_epoch)
        self._generation = GovernanceGenerationObserver(GOVERNANCE_SCOPE_VIRTUAL_KEYS)
        self._keys_by_hash = {}
        self._loaded = False

    def reset_coordination(self) -> None:
        """Restore process-local quota state after the runtime-owned store closes."""

        if self._durable_reservation_ids or self._pending_durable_settlement_ids:
            raise RuntimeError("Virtual-key coordination cannot reset with active reservations.")
        self._state_store = InMemoryStateStore()
        self._fencing_epoch = 1
        self._generation = GovernanceGenerationObserver(GOVERNANCE_SCOPE_VIRTUAL_KEYS)
        self._keys_by_hash = {}
        self._loaded = False

    async def _ensure_loaded(self, *, force_generation_poll: bool = False) -> None:
        await self._generation.synchronize(
            self._invalidate_cached_keys,
            force=force_generation_poll,
        )
        if self._loaded:
            return
        async with self._lock:
            if self._loaded:
                return
            from core.storage_adapter import get_storage_adapter

            storage_adapter = await get_storage_adapter()
            raw_keys = await storage_adapter.get_config(VIRTUAL_KEYS_CONFIG_KEY, [])
            keys: Dict[str, VirtualKey] = {}
            needs_migration = False
            invalid_record_found = False
            if isinstance(raw_keys, list):
                for raw in raw_keys:
                    record = VirtualKey.from_storage_dict(raw)
                    if record is not None:
                        keys[record.key_hash] = record
                        needs_migration = needs_migration or "schema_version" not in raw
                    else:
                        invalid_record_found = True
            self._keys_by_hash = keys
            self._loaded = True
            if needs_migration and not invalid_record_found:
                await storage_adapter.set_config(
                    VIRTUAL_KEYS_CONFIG_KEY,
                    [record.to_storage_dict() for record in keys.values()],
                )
            if keys:
                log.info(f"[virtual-keys] loaded {len(keys)} virtual API keys")

    async def _invalidate_cached_keys(self) -> None:
        from core.storage_adapter import get_storage_adapter

        storage_adapter = await get_storage_adapter()
        await storage_adapter.reload_config_cache()
        self._keys_by_hash = {}
        self._loaded = False

    async def _persist(self) -> None:
        from core.storage_adapter import get_storage_adapter

        storage_adapter = await get_storage_adapter()
        payload = [record.to_storage_dict() for record in self._keys_by_hash.values()]
        await storage_adapter.set_config(VIRTUAL_KEYS_CONFIG_KEY, payload)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def list_keys(self) -> List[Dict[str, Any]]:
        await self._ensure_loaded()
        records = sorted(self._keys_by_hash.values(), key=lambda item: item.created_at)
        return [record.to_public_dict() for record in records]

    async def create_key(
        self,
        name: str,
        *,
        budget_daily_usd: Optional[float] = None,
        budget_monthly_usd: Optional[float] = None,
        rpm_limit: Optional[int] = None,
        tpm_limit: Optional[int] = None,
        expires_at: Optional[float] = None,
        allowed_models: Optional[List[str]] = None,
        scopes: Optional[List[str]] = None,
        unknown_pricing_policy: str = "deny",
        fallback_price_usd_per_million: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """Create a key and return ``(public_record, plaintext_secret)``."""
        from config import API_KEY_PREFIX

        await self._ensure_loaded()
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("Virtual key name is required.")
        normalized_scopes = normalize_virtual_key_scopes(
            list(DEFAULT_INFERENCE_SCOPES) if scopes is None else scopes
        )
        normalized_models = normalize_model_patterns(allowed_models or [])
        pricing_policy, fallback_price = normalize_unknown_pricing_policy(
            unknown_pricing_policy,
            fallback_price_usd_per_million,
        )

        plaintext = f"{API_KEY_PREFIX}vk-{secrets.token_hex(20)}"
        record = VirtualKey(
            id=f"{KEY_ID_PREFIX}{secrets.token_hex(6)}",
            name=clean_name[:128],
            key_hash=hash_key(plaintext),
            key_preview=_key_preview(plaintext),
            enabled=True,
            created_at=time.time(),
            expires_at=_float_or_none(expires_at),
            budget_daily_usd=_float_or_none(budget_daily_usd),
            budget_monthly_usd=_float_or_none(budget_monthly_usd),
            rpm_limit=_int_or_none(rpm_limit),
            tpm_limit=_int_or_none(tpm_limit),
            allowed_models=normalized_models,
            scopes=normalized_scopes,
            unknown_pricing_policy=pricing_policy,
            fallback_price_usd_per_million=fallback_price,
        )
        async with self._lock:
            self._keys_by_hash[record.key_hash] = record
            await self._persist()
        log.info("[virtual-keys] created a virtual key")
        return record.to_public_dict(), plaintext

    async def update_key(
        self,
        key_id: str,
        patch: Dict[str, Any],
        *,
        expected_revision: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        await self._ensure_loaded()
        async with self._lock:
            record = self._find_by_id_locked(key_id)
            if record is None:
                return None
            self._assert_expected_revision(record, expected_revision)
            normalized_scopes = (
                normalize_virtual_key_scopes(patch.get("scopes")) if "scopes" in patch else None
            )
            normalized_models = (
                normalize_model_patterns(patch.get("allowed_models"))
                if "allowed_models" in patch
                else None
            )
            compression_policy = (
                normalize_compression_restriction(
                    patch.get("compression_policy"), layer="virtual-key"
                )
                if "compression_policy" in patch
                else record.compression_policy
            )
            pricing_policy = record.unknown_pricing_policy
            fallback_price = record.fallback_price_usd_per_million
            if "unknown_pricing_policy" in patch or "fallback_price_usd_per_million" in patch:
                requested_policy = patch.get(
                    "unknown_pricing_policy", record.unknown_pricing_policy
                )
                if "fallback_price_usd_per_million" in patch:
                    requested_fallback = patch.get("fallback_price_usd_per_million")
                elif str(requested_policy).strip().lower() == "fallback":
                    requested_fallback = record.fallback_price_usd_per_million
                else:
                    requested_fallback = None
                pricing_policy, fallback_price = normalize_unknown_pricing_policy(
                    requested_policy,
                    requested_fallback,
                )
            if "name" in patch:
                new_name = str(patch.get("name") or "").strip()
                if new_name:
                    record.name = new_name[:128]
            if "enabled" in patch:
                if record.revoked_at is not None and bool(patch.get("enabled")):
                    raise ValueError("A revoked virtual key cannot be enabled.")
                record.enabled = bool(patch.get("enabled"))
            if "budget_daily_usd" in patch:
                record.budget_daily_usd = _float_or_none(patch.get("budget_daily_usd"))
            if "budget_monthly_usd" in patch:
                record.budget_monthly_usd = _float_or_none(patch.get("budget_monthly_usd"))
            if "rpm_limit" in patch:
                record.rpm_limit = _int_or_none(patch.get("rpm_limit"))
            if "tpm_limit" in patch:
                record.tpm_limit = _int_or_none(patch.get("tpm_limit"))
            if "expires_at" in patch:
                record.expires_at = _float_or_none(patch.get("expires_at"))
            if "allowed_models" in patch:
                record.allowed_models = normalized_models or []
            if normalized_scopes is not None:
                record.scopes = normalized_scopes
            record.unknown_pricing_policy = pricing_policy
            record.fallback_price_usd_per_million = fallback_price
            record.compression_policy = compression_policy
            record.revision += 1
            await self._persist()
            return record.to_public_dict()

    async def rotate_key(
        self,
        key_id: str,
        *,
        expected_revision: int,
    ) -> Optional[Tuple[Dict[str, Any], str]]:
        """Replace a key secret atomically and reveal the new plaintext once."""
        from config import API_KEY_PREFIX

        await self._ensure_loaded()
        plaintext = f"{API_KEY_PREFIX}vk-{secrets.token_hex(20)}"
        async with self._lock:
            record = self._find_by_id_locked(key_id)
            if record is None:
                return None
            self._assert_expected_revision(record, expected_revision)
            if record.revoked_at is not None:
                raise ValueError("A revoked virtual key cannot be rotated.")
            old_hash = record.key_hash
            record.key_hash = hash_key(plaintext)
            record.key_preview = _key_preview(plaintext)
            record.revision += 1
            self._keys_by_hash.pop(old_hash, None)
            self._keys_by_hash[record.key_hash] = record
            await self._persist()
            log.info("[virtual-keys] rotated a virtual key")
            return record.to_public_dict(), plaintext

    async def revoke_key(
        self,
        key_id: str,
        *,
        expected_revision: int,
    ) -> Optional[Dict[str, Any]]:
        """Permanently disable a key while retaining its audit-safe identity."""
        await self._ensure_loaded()
        async with self._lock:
            record = self._find_by_id_locked(key_id)
            if record is None:
                return None
            self._assert_expected_revision(record, expected_revision)
            if record.revoked_at is not None:
                return record.to_public_dict()
            record.enabled = False
            record.revoked_at = time.time()
            record.revision += 1
            await self._persist()
            log.info("[virtual-keys] revoked a virtual key")
            return record.to_public_dict()

    async def delete_key(self, key_id: str) -> bool:
        await self._ensure_loaded()
        async with self._lock:
            record = self._find_by_id_locked(key_id)
            if record is None:
                return False
            self._keys_by_hash.pop(record.key_hash, None)
            await self._persist()
            log.info("[virtual-keys] deleted a virtual key")
            return True

    def _find_by_id_locked(self, key_id: str) -> Optional[VirtualKey]:
        for record in self._keys_by_hash.values():
            if record.id == key_id:
                return record
        return None

    @staticmethod
    def _assert_expected_revision(
        record: VirtualKey,
        expected_revision: Optional[int],
    ) -> None:
        if expected_revision is not None and record.revision != expected_revision:
            raise VirtualKeyConflictError(
                "The virtual key changed. Refresh its current state and try again."
            )

    # ------------------------------------------------------------------
    # Verification and enforcement
    # ------------------------------------------------------------------

    async def verify(self, token: str) -> Optional[VirtualKey]:
        """Constant-time hash comparison against every stored key."""
        await self._ensure_loaded()
        candidate_hash = hash_key(token)
        matched = self._match_hash(candidate_hash)
        if matched is not None:
            return matched
        await self._ensure_loaded(force_generation_poll=True)
        return self._match_hash(candidate_hash)

    def _match_hash(self, candidate_hash: str) -> Optional[VirtualKey]:
        matched: Optional[VirtualKey] = None
        for stored_hash, record in self._keys_by_hash.items():
            if secrets.compare_digest(candidate_hash, stored_hash):
                matched = record
        return matched

    @staticmethod
    def _enforce_active(record: VirtualKey) -> None:
        """Reject disabled or expired keys before evaluating any permission."""
        now = time.time()
        if record.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This API key has been revoked.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not record.enabled:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This API key has been disabled.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if record.is_expired(now):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This API key has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def enforce(
        self,
        record: VirtualKey,
        *,
        protocol: str = "openai",
        requested_model: str = "",
        request_body: Any = None,
        candidate_models: Optional[Sequence[str]] = None,
        reservation_id: str = "",
        operation_id: str = "",
        now: Optional[float] = None,
    ) -> Optional[str]:
        """Authorize and atomically reserve constrained inference capacity."""
        current = time.time() if now is None else float(now)
        self._prune_local_durable_reservations(current)
        self._enforce_active(record)
        required_scope = f"inference:{str(protocol or '').strip().lower()}"
        if required_scope not in INFERENCE_SCOPES or required_scope not in record.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This API key is not allowed to use the requested inference protocol.",
            )
        if not record.allows_model(requested_model):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This API key is not allowed to access model '{requested_model}'.",
            )

        constrained = any(
            limit is not None
            for limit in (
                record.rpm_limit,
                record.tpm_limit,
                record.budget_daily_usd,
                record.budget_monthly_usd,
            )
        )
        if not constrained:
            trace_decision(
                category="quota",
                action="skipped",
                result="skipped",
                reason="not_eligible",
                model=requested_model,
            )
            return None

        estimated_input, estimated_output = self._estimate_tokens(request_body)
        estimated_tokens = min(
            MAX_RESERVED_TOKENS,
            max(0, estimated_input) + max(0, estimated_output),
        )
        models = self._reservation_models(requested_model, candidate_models)
        estimated_cost = self._estimate_cost(
            record,
            models=models,
            input_tokens=estimated_input,
            output_tokens=estimated_output,
        )
        hard_budget = self._has_hard_budget(record)
        supplied_id = str(reservation_id or "")
        supplied_operation = str(operation_id or "")
        if supplied_operation and not 1 <= len(supplied_operation) <= 128:
            raise ValueError("Quota operation identity is invalid.")
        deterministic_suffix = (
            hashlib.sha256(
                b"omni-gateway:quota-reservation:v1\0"
                + record.id.encode("utf-8")
                + b"\0"
                + supplied_operation.encode("utf-8")
            ).hexdigest()[:32]
            if supplied_operation
            else ""
        )
        if hard_budget:
            internal_id = (
                supplied_id
                if re.fullmatch(r"qrs_[0-9a-f]{32}", supplied_id)
                else (
                    f"qrs_{deterministic_suffix}"
                    if deterministic_suffix
                    else f"qrs_{secrets.token_hex(16)}"
                )
            )
            if not self._claim_local_durable_reservation(
                internal_id,
                now=current,
                expires_at=current + RESERVATION_TTL_SECONDS,
            ):
                _increment_quota_metric("ledger_capacity_denied")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="API key budget enforcement is temporarily unavailable.",
                )
            try:
                durable_decision = await self._usage_ledger().reserve_budget(
                    BudgetReservationRequest(
                        schema_version=USAGE_LEDGER_SCHEMA_VERSION,
                        reservation_id=internal_id,
                        key_id=record.id,
                        created_at=current,
                        expires_at=current + RESERVATION_TTL_SECONDS,
                        estimated_tokens=estimated_tokens,
                        estimated_cost_nanos=usd_to_nanos(estimated_cost),
                        daily_budget_nanos=(
                            None
                            if record.budget_daily_usd is None
                            else usd_to_nanos(record.budget_daily_usd)
                        ),
                        monthly_budget_nanos=(
                            None
                            if record.budget_monthly_usd is None
                            else usd_to_nanos(record.budget_monthly_usd)
                        ),
                    )
                )
            except Exception as exc:
                self._discard_local_durable_reservation(internal_id)
                _increment_quota_metric("ledger_unavailable")
                log.error(
                    f"[virtual-keys] durable budget unavailable (error_type={type(exc).__name__})"
                )
                trace_decision(
                    category="quota",
                    action="denied",
                    result="failed",
                    reason="policy_unavailable",
                    model=requested_model,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="API key budget enforcement is temporarily unavailable.",
                ) from exc
            if not durable_decision.accepted:
                self._discard_local_durable_reservation(internal_id)
                _increment_quota_metric(f"rejected_{durable_decision.reason or 'unknown'}")
                self._raise_reservation_rejection(
                    record,
                    durable_decision.reason,
                    0,
                )
            if durable_decision.replayed:
                self._discard_local_durable_reservation(internal_id)
                _increment_quota_metric("delivery_replayed")
                trace_decision(
                    category="quota",
                    action="replayed",
                    result="succeeded",
                    reason="operation_already_committed",
                    model=requested_model,
                )
                return QuotaReservationHandle(internal_id, replayed=True)
        else:
            internal_id = str(
                supplied_id
                or (
                    f"qrr_{deterministic_suffix}"
                    if deterministic_suffix
                    else f"qrr_{secrets.token_hex(16)}"
                )
            )[:128]
        try:
            decision = await self._state_store.reserve_quota(
                QuotaReservationRequest(
                    reservation_id=internal_id,
                    key_id=record.id,
                    now=current,
                    ttl_seconds=RESERVATION_TTL_SECONDS,
                    estimated_tokens=estimated_tokens,
                    estimated_cost_usd=0.0,
                    rpm_limit=record.rpm_limit,
                    tpm_limit=record.tpm_limit,
                    daily_budget_usd=None,
                    monthly_budget_usd=None,
                    daily_spend_usd=0.0,
                    monthly_spend_usd=0.0,
                    daily_snapshot_started_at=current,
                    monthly_snapshot_started_at=current,
                    fencing_epoch=self._fencing_epoch,
                    operation_id=supplied_operation or internal_id,
                )
            )
        except Exception as exc:
            await self._release_durable_after_admission_failure(internal_id, current)
            log.error(f"[virtual-keys] quota state unavailable (error_type={type(exc).__name__})")
            trace_decision(
                category="quota",
                action="denied",
                result="failed",
                reason="policy_unavailable",
                model=requested_model,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API key quota enforcement is temporarily unavailable.",
            ) from exc
        if not decision.accepted:
            await self._release_durable_after_admission_failure(internal_id, current)
            _increment_quota_metric(f"rejected_{decision.reason or 'unknown'}")
            if decision.reason in {
                "reconciling",
                "stale_epoch",
                "capacity",
                "reconciliation_required",
                "conflict",
            }:
                trace_decision(
                    category="quota",
                    action="denied",
                    result="failed",
                    reason="policy_unavailable",
                    model=requested_model,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="API key quota enforcement is temporarily unavailable.",
                )
            trace_decision(
                category="quota",
                action="denied",
                result="denied",
                reason=(
                    "quota_exceeded" if decision.reason in {"rpm", "tpm"} else "budget_exceeded"
                ),
                model=requested_model,
                original_tokens=estimated_tokens,
                cost_usd=estimated_cost,
            )
            self._raise_reservation_rejection(record, decision.reason, decision.retry_after_seconds)
        _increment_quota_metric("accepted")
        trace_decision(
            category="quota",
            action="reserved",
            result="succeeded",
            reason="quota_reserved",
            model=requested_model,
            original_tokens=estimated_tokens,
            cost_usd=estimated_cost,
        )
        return QuotaReservationHandle(decision.reservation_id)

    def authorize_management(self, record: VirtualKey, *, write: bool) -> None:
        """Authorize a management read or write without consuming inference limits."""
        self._enforce_active(record)
        required_scope = "management:write" if write else "management:read"
        if required_scope not in record.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This API key does not have the required management scope.",
            )

    async def note_last_used(self, record: VirtualKey, *, now: Optional[float] = None) -> None:
        """Persist bounded last-used metadata without writing on every request."""
        current = now if now is not None else time.time()
        async with self._lock:
            if (
                record.last_used_at is not None
                and current - record.last_used_at < LAST_USED_PERSIST_INTERVAL_SECONDS
            ):
                return
            record.last_used_at = current
            await self._persist()

    @staticmethod
    def _estimate_tokens(request_body: Any) -> Tuple[int, int]:
        if not isinstance(request_body, dict) or not request_body:
            return 0, 0

        protocol_request = request_body.get("request")
        if not isinstance(protocol_request, dict):
            protocol_request = request_body
        prompt_payload = {
            field_name: protocol_request[field_name]
            for field_name in _INPUT_CONTEXT_FIELDS
            if field_name in protocol_request
        }
        # Unknown provider shapes remain conservative rather than silently becoming
        # a zero-token reservation. Recognized protocols exclude non-context controls.
        input_tokens = min(
            MAX_RESERVED_TOKENS,
            estimate_input_tokens(prompt_payload or protocol_request),
        )
        raw_output = None
        for field_name in ("max_output_tokens", "max_completion_tokens", "max_tokens"):
            if protocol_request.get(field_name) is not None:
                raw_output = protocol_request.get(field_name)
                break
        generation_config = protocol_request.get("generationConfig")
        if raw_output is None and isinstance(generation_config, dict):
            raw_output = generation_config.get("maxOutputTokens")
        try:
            output_tokens = (
                int(raw_output) if raw_output is not None else DEFAULT_RESERVED_OUTPUT_TOKENS
            )
        except (TypeError, ValueError):
            output_tokens = DEFAULT_RESERVED_OUTPUT_TOKENS
        return input_tokens, min(MAX_RESERVED_TOKENS, max(0, output_tokens))

    @staticmethod
    def _reservation_models(
        requested_model: str,
        candidate_models: Optional[Sequence[str]],
    ) -> Tuple[str, ...]:
        raw_models = candidate_models if candidate_models is not None else (requested_model,)
        normalized: List[str] = []
        for value in raw_models:
            model = str(value or "").strip()
            if model and model not in normalized:
                normalized.append(model)
        return tuple(normalized)

    @staticmethod
    def _has_hard_budget(record: VirtualKey) -> bool:
        return record.budget_daily_usd is not None or record.budget_monthly_usd is not None

    def _usage_ledger(self) -> Any:
        if self._usage_ledger_service is not None:
            return self._usage_ledger_service
        from core.usage_ledger_service import get_usage_ledger_service

        return get_usage_ledger_service()

    def is_durable_reservation(self, reservation_id: Optional[str]) -> bool:
        with self._durable_tracking_lock:
            return bool(reservation_id and reservation_id in self._durable_reservation_ids)

    def _claim_local_durable_reservation(
        self,
        reservation_id: str,
        *,
        now: float,
        expires_at: float,
    ) -> bool:
        with self._durable_tracking_lock:
            self._prune_local_durable_reservations_locked(now)
            if reservation_id in self._durable_reservation_expiries:
                return True
            if len(self._durable_reservation_expiries) >= MAX_LOCAL_DURABLE_RESERVATIONS:
                return False
            self._durable_reservation_ids.add(reservation_id)
            self._durable_reservation_expiries[reservation_id] = expires_at
            return True

    def _discard_local_durable_reservation(self, reservation_id: str) -> None:
        with self._durable_tracking_lock:
            self._durable_reservation_expiries.pop(reservation_id, None)
            self._durable_reservation_ids.discard(reservation_id)
            self._pending_durable_settlement_ids.discard(reservation_id)

    def _prune_local_durable_reservations(self, now: float) -> None:
        with self._durable_tracking_lock:
            self._prune_local_durable_reservations_locked(now)

    def _prune_local_durable_reservations_locked(self, now: float) -> None:
        expired_ids = tuple(
            reservation_id
            for reservation_id, expires_at in self._durable_reservation_expiries.items()
            if expires_at <= now
        )
        for reservation_id in expired_ids:
            self._durable_reservation_expiries.pop(reservation_id, None)
            self._durable_reservation_ids.discard(reservation_id)
            self._pending_durable_settlement_ids.discard(reservation_id)

    async def _release_durable_after_admission_failure(
        self, reservation_id: str, transitioned_at: float
    ) -> None:
        if reservation_id not in self._durable_reservation_ids:
            return
        try:
            await self._usage_ledger().release_reservation(
                reservation_id,
                transitioned_at=transitioned_at,
            )
        except Exception as exc:
            log.error(
                "[virtual-keys] failed to release durable budget after admission failure "
                f"(error_type={type(exc).__name__})"
            )
        finally:
            self._discard_local_durable_reservation(reservation_id)

    def _estimate_cost(
        self,
        record: VirtualKey,
        *,
        models: Sequence[str],
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        estimates: List[float] = []
        unknown_models: List[str] = []
        for model in models:
            if find_model_pricing(model) is None:
                unknown_models.append(model)
                if record.unknown_pricing_policy == "fallback":
                    fallback = float(record.fallback_price_usd_per_million or 0.0)
                    estimates.append((input_tokens + output_tokens) * fallback / 1_000_000.0)
                continue
            estimates.append(
                calculate_cost_usd(
                    model,
                    input_tokens=input_tokens,
                    cache_creation_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            )

        if unknown_models and self._has_hard_budget(record):
            if record.unknown_pricing_policy in {"deny", "warn"}:
                if record.unknown_pricing_policy == "warn":
                    _increment_quota_metric("pricing_warned")
                    log.warning(
                        "[virtual-keys] denying an unpriced hard-budget request under warn policy"
                    )
                else:
                    _increment_quota_metric("pricing_denied")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        "Budget enforcement denied this request because pricing is unavailable "
                        "for one or more candidate models."
                    ),
                )
            if record.unknown_pricing_policy == "fallback":
                _increment_quota_metric("pricing_fallback")
        return max(estimates, default=0.0)

    @staticmethod
    def _raise_reservation_rejection(
        record: VirtualKey,
        reason: str,
        retry_after_seconds: int,
    ) -> None:
        headers = (
            {"Retry-After": str(max(1, int(retry_after_seconds)))}
            if reason in {"rpm", "tpm"}
            else None
        )
        if reason == "rpm":
            detail = (
                f"Rate limit exceeded: {record.rpm_limit} requests per minute for this API key."
            )
        elif reason == "tpm":
            detail = (
                f"Token rate limit exceeded: {record.tpm_limit} tokens per minute for this API key."
            )
        elif reason == "daily_budget":
            detail = (
                "Budget exceeded: the estimated request would cross this API key's daily budget."
            )
        else:
            detail = (
                "Budget exceeded: the estimated request would cross this API key's monthly budget."
            )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers=headers,
        )

    async def commit_reservation(
        self,
        reservation_id: str,
        *,
        actual_tokens: Optional[int],
        actual_cost_usd: Optional[float],
        durable_cost_recorded: bool,
        now: Optional[float] = None,
    ) -> QuotaCommitResult:
        if not reservation_id:
            return QuotaCommitResult(False)
        internal_id = str(reservation_id)
        transitioned_at = time.time() if now is None else float(now)
        self._prune_local_durable_reservations(transitioned_at)
        with self._durable_tracking_lock:
            if internal_id in self._durable_reservation_ids:
                if durable_cost_recorded:
                    self._durable_reservation_ids.discard(internal_id)
                    self._pending_durable_settlement_ids.discard(internal_id)
                    self._durable_reservation_expiries.pop(internal_id, None)
                else:
                    # The provider response succeeded but durable settlement did not.
                    # Retain the durable reservation so final request cleanup cannot
                    # erase the only crash-safe evidence of the admitted spend.
                    self._pending_durable_settlement_ids.add(internal_id)
        result = await self._state_store.commit_quota(
            QuotaCommitRequest(
                reservation_id=internal_id,
                now=transitioned_at,
                actual_tokens=None if actual_tokens is None else max(0, int(actual_tokens)),
                actual_cost_usd=(
                    None if actual_cost_usd is None else max(0.0, float(actual_cost_usd))
                ),
                durable_cost_recorded=bool(durable_cost_recorded),
                fencing_epoch=self._fencing_epoch,
            )
        )
        if result.committed:
            _increment_quota_metric("committed")
        elif result.idempotent:
            _increment_quota_metric("commit_idempotent")
        if result.overspent:
            _increment_quota_metric("actual_overspend")
        trace_decision(
            category="quota",
            action="committed",
            result="succeeded" if result.committed or result.idempotent else "skipped",
            reason="usage_recorded",
            final_tokens=max(0, int(actual_tokens or 0)),
            cost_usd=max(0.0, float(actual_cost_usd or 0.0)),
        )
        return result

    async def release_reservation(
        self,
        reservation_id: Optional[str],
        *,
        now: Optional[float] = None,
    ) -> bool:
        if not reservation_id:
            return False
        internal_id = str(reservation_id)
        transitioned_at = time.time() if now is None else float(now)
        self._prune_local_durable_reservations(transitioned_at)
        released = False
        state_error: Exception | None = None
        try:
            released = await self._state_store.release_quota(
                internal_id,
                now=transitioned_at,
                fencing_epoch=self._fencing_epoch,
            )
        except Exception as exc:
            state_error = exc
        durable_released = False
        with self._durable_tracking_lock:
            should_release_durable = (
                internal_id in self._durable_reservation_ids
                and internal_id not in self._pending_durable_settlement_ids
            )
        if should_release_durable:
            result = await self._usage_ledger().release_reservation(
                internal_id,
                transitioned_at=transitioned_at,
            )
            durable_released = result.released or result.idempotent
            if durable_released:
                self._discard_local_durable_reservation(internal_id)
        if released or durable_released:
            _increment_quota_metric("released")
            trace_decision(
                category="quota",
                action="released",
                result="succeeded",
                reason="completed",
            )
        if state_error is not None:
            raise state_error
        return released or durable_released

    async def calculate_actual_cost(
        self,
        key_id: str,
        *,
        model: str,
        provider: str,
        token_usage: Optional[Dict[str, Any]],
    ) -> float:
        if str(provider or "").strip().lower() in ZERO_COST_PROVIDERS:
            return 0.0
        await self._ensure_loaded()
        async with self._lock:
            record = self._find_by_id_locked(key_id)
        from core.usage_stats import normalize_token_usage

        tokens = normalize_token_usage(token_usage)
        if find_model_pricing(model, provider=provider) is not None:
            return calculate_cost_usd(
                model,
                input_tokens=tokens["input_tokens"],
                output_tokens=tokens["output_tokens"],
                cached_tokens=tokens["cached_tokens"],
                cache_creation_tokens=tokens["cache_creation_tokens"],
                reasoning_tokens=tokens["reasoning_tokens"],
                provider=provider,
            )
        if record is not None and record.unknown_pricing_policy == "fallback":
            return round(
                tokens["total_tokens"]
                * float(record.fallback_price_usd_per_million or 0.0)
                / 1_000_000.0,
                10,
            )
        return 0.0

    async def get_key_usage(self, key_id: str) -> Dict[str, Any]:
        """Spend snapshot used by the panel key list."""
        from core.usage_stats import get_spend_since

        now = time.time()
        daily = await get_spend_since(now - DAILY_WINDOW_SECONDS, key_id)
        monthly = await get_spend_since(now - MONTHLY_WINDOW_SECONDS, key_id)
        return {"daily": daily, "monthly": monthly}

    def reset_runtime_state(self) -> None:
        """Clear request-local tracking without replacing the selected coordination store."""
        with self._durable_tracking_lock:
            self._durable_reservation_ids.clear()
            self._pending_durable_settlement_ids.clear()
            self._durable_reservation_expiries.clear()

    def invalidate(self) -> None:
        """Force a reload from storage on next access."""
        self._loaded = False


def extract_requested_model(path: str, body: Any) -> str:
    """Best-effort extraction of the requested model for allowlist checks."""
    match = _GEMINI_MODEL_PATH_RE.search(str(path or ""))
    if match:
        return match.group(1)
    if isinstance(body, dict):
        return str(body.get("model") or "")
    return ""


virtual_key_manager = VirtualKeyManager()
