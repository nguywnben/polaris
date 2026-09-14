"""Lifecycle and write boundary for durable management audit evidence."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Any

from core.audit import (
    AuditEvent,
    AuditPage,
    AuditQuery,
    AuditRepository,
    AuditRetentionPolicy,
    create_audit_event,
)
from core.management_audit import ManagementMutation

AUDIT_MASTER_KEY_CONFIG = "_internal_audit_master_key_v1"
AUDIT_RETENTION_CONFIG = "_internal_audit_retention_v1"
_MASTER_KEY_BYTES = 32
_FINGERPRINT_DOMAIN = b"omni-gateway:audit:fingerprint:v1"
_CURSOR_DOMAIN = b"omni-gateway:audit:cursor:v1"
_INFERENCE_RETENTION_PRUNE_INTERVAL = 256


def _encode_master_key(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _decode_master_key(value: Any) -> bytes:
    if not isinstance(value, str) or len(value) > 128:
        raise RuntimeError("Stored audit master key is invalid.")
    try:
        decoded = base64.b64decode(
            value,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("Stored audit master key is invalid.") from exc
    if len(decoded) != _MASTER_KEY_BYTES or _encode_master_key(decoded) != value:
        raise RuntimeError("Stored audit master key is invalid.")
    return decoded


def _derive_key(master_key: bytes, domain: bytes) -> bytes:
    return hmac.new(master_key, domain, hashlib.sha256).digest()


def _decode_retention_policy(value: Any) -> AuditRetentionPolicy:
    if value is None:
        return AuditRetentionPolicy()
    if not isinstance(value, dict) or set(value) != {"retention_days", "max_events"}:
        raise RuntimeError("Stored audit retention policy is invalid.")
    if type(value["retention_days"]) is not int or type(value["max_events"]) is not int:
        raise RuntimeError("Stored audit retention policy is invalid.")
    try:
        return AuditRetentionPolicy(
            retention_days=value["retention_days"],
            max_events=value["max_events"],
        )
    except ValueError as exc:
        raise RuntimeError("Stored audit retention policy is invalid.") from exc


class AuditService:
    """Create redacted immutable events and append them to selected durable storage."""

    def __init__(
        self,
        repository: AuditRepository,
        *,
        storage: Any,
        fingerprint_key: bytes,
        retention_policy: AuditRetentionPolicy,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._fingerprint_key = fingerprint_key
        self._retention_policy = retention_policy
        self._retention_lock = asyncio.Lock()
        self._inference_since_prune = 0

    @classmethod
    async def create(cls, storage: Any) -> "AuditService":
        retention_policy = _decode_retention_policy(
            await storage.get_config(AUDIT_RETENTION_CONFIG, None)
        )
        encoded_master = await storage.get_config(AUDIT_MASTER_KEY_CONFIG, None)
        if encoded_master is None:
            encoded_master = _encode_master_key(secrets.token_bytes(_MASTER_KEY_BYTES))
            if not await storage.set_config(AUDIT_MASTER_KEY_CONFIG, encoded_master):
                raise RuntimeError("Unable to persist the audit master key.")
            encoded_master = await storage.get_config(AUDIT_MASTER_KEY_CONFIG, None)
        master_key = _decode_master_key(encoded_master)
        cursor_key = _derive_key(master_key, _CURSOR_DOMAIN)
        repository = await storage.create_audit_repository(
            cursor_signing_key=cursor_key,
        )
        return cls(
            repository,
            storage=storage,
            fingerprint_key=_derive_key(master_key, _FINGERPRINT_DOMAIN),
            retention_policy=retention_policy,
        )

    @property
    def retention_policy(self) -> AuditRetentionPolicy:
        return self._retention_policy

    async def query(self, query: AuditQuery) -> AuditPage:
        if not isinstance(query, AuditQuery):
            raise ValueError("A validated AuditQuery is required.")
        return await self._repository.query(query)

    async def update_retention(
        self,
        policy: AuditRetentionPolicy,
        *,
        now: datetime | None = None,
    ) -> int:
        if not isinstance(policy, AuditRetentionPolicy):
            raise ValueError("A validated AuditRetentionPolicy is required.")
        prune_time = now or datetime.now(timezone.utc)
        if not isinstance(prune_time, datetime) or prune_time.tzinfo is None:
            raise ValueError("Audit retention timestamp must be timezone-aware.")
        prune_time = prune_time.astimezone(timezone.utc)
        record = {
            "retention_days": policy.retention_days,
            "max_events": policy.max_events,
        }
        async with self._retention_lock:
            if not await self._storage.set_config(AUDIT_RETENTION_CONFIG, record):
                raise RuntimeError("Unable to persist the audit retention policy.")
            self._retention_policy = policy
            return await self._repository.prune(policy, now=prune_time)

    async def record(
        self,
        mutation: ManagementMutation,
        *,
        request_id: str,
        actor_type: str,
        actor_identifier: str,
        outcome: str,
    ) -> AuditEvent:
        if not isinstance(mutation, ManagementMutation) or not mutation.target_identifier:
            raise ValueError("A classified management mutation is required.")
        event = create_audit_event(
            request_id=request_id,
            actor_type=actor_type,
            actor_identifier=actor_identifier,
            action=mutation.action,
            target_type=mutation.target_type,
            target_identifier=mutation.target_identifier,
            outcome=outcome,
            change_codes=mutation.change_codes,
            fingerprint_key=self._fingerprint_key,
        )
        async with self._retention_lock:
            await self._repository.append(event)
            await self._repository.prune(
                self._retention_policy,
                now=datetime.now(timezone.utc),
            )
        return event

    async def record_inference(
        self,
        *,
        request_id: str,
        protocol: str,
        status_code: int,
    ) -> AuditEvent:
        """Append one redacted audit fact for a completed inference admission."""

        if not isinstance(protocol, str) or not protocol:
            raise ValueError("A classified inference protocol is required.")
        if type(status_code) is not int or not 100 <= status_code <= 599:
            raise ValueError("Inference audit status is invalid.")
        outcome = (
            "succeeded"
            if status_code < 400
            else "denied"
            if status_code in {401, 403, 429}
            else "failed"
        )
        event = create_audit_event(
            request_id=request_id,
            actor_type="system",
            actor_identifier="polaris",
            action="inference.execute",
            target_type="inference_route",
            target_identifier=protocol,
            outcome=outcome,
            change_codes=("no_change",),
            fingerprint_key=self._fingerprint_key,
        )
        async with self._retention_lock:
            await self._repository.append(event)
            self._inference_since_prune += 1
            if self._inference_since_prune >= _INFERENCE_RETENTION_PRUNE_INTERVAL:
                await self._repository.prune(
                    self._retention_policy,
                    now=datetime.now(timezone.utc),
                )
                self._inference_since_prune = 0
        return event


_audit_service: AuditService | None = None
_audit_service_lock = asyncio.Lock()


async def initialize_audit_service(storage: Any | None = None) -> AuditService:
    global _audit_service
    async with _audit_service_lock:
        if _audit_service is None:
            if storage is None:
                from core.storage_adapter import get_storage_adapter

                storage = await get_storage_adapter()
            _audit_service = await AuditService.create(storage)
        return _audit_service


def get_audit_service() -> AuditService:
    if _audit_service is None:
        raise RuntimeError("Audit service is not initialized.")
    return _audit_service


_CREDENTIAL_ACTIONS = {
    "enable": ("credential.toggle", "enabled"),
    "disable": ("credential.toggle", "disabled"),
    "delete": ("credential.delete", "deleted"),
    "enable_credit": ("credential.credit_mode", "enabled"),
    "disable_credit": ("credential.credit_mode", "disabled"),
}
_CREDENTIAL_OUTCOMES = {
    "succeeded": "succeeded",
    "unsupported": "invalid",
    "not_found": "not_found",
    "invalid": "invalid",
    "duplicate": "conflict",
    "timed_out": "timed_out",
    "failed": "failed",
    "cancelled": "cancelled",
    "unknown": "failed",
}


async def record_credential_response(
    *,
    request_id: str,
    action: str,
    mode: str,
    filename: str,
    outcome: str,
) -> AuditEvent:
    """Bridge one W2 per-target credential result into durable audit storage."""

    try:
        audit_action, change_code = _CREDENTIAL_ACTIONS[action]
        audit_outcome = _CREDENTIAL_OUTCOMES[outcome]
    except KeyError as exc:
        raise ValueError("Unsupported credential audit evidence.") from exc
    mutation = ManagementMutation(
        action=audit_action,
        target_type="credential",
        change_codes=(change_code,),
        target_identifier=f"{mode}:{filename}",
    )
    return await get_audit_service().record(
        mutation,
        request_id=request_id,
        actor_type="panel_session",
        actor_identifier="panel-owner",
        outcome=audit_outcome,
    )


async def close_audit_service() -> None:
    global _audit_service
    async with _audit_service_lock:
        _audit_service = None
