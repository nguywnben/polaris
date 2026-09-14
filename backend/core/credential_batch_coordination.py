"""Shared preview and chunked idempotency state for credential batch work."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import struct
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field

from core.coordination import (
    CasRequest,
    CasSettlementProof,
    CasSettlementTarget,
    CasSettlementTransition,
    CoordinationStore,
    validate_epoch,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PREVIEW_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_OWNER_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_IDEMPOTENCY_ROOT_PATTERN = re.compile(r"^credential-batch-idempotency-[0-9a-f]{64}$")
_HMAC_DOMAIN = b"polaris:credential-batch:v1\0"
_PAYLOAD_KEY_DOMAIN = b"polaris:credential-batch-payload-key:v1\0"
_PAYLOAD_AAD = b"polaris:credential-batch-payload:v1"
_PREVIEW_TTL_SECONDS = 300.0
_IDEMPOTENCY_TTL_SECONDS = 86_400.0
_RELEASE_TTL_SECONDS = 60.0
_MAX_RESPONSE_BYTES = 256 * 1024
_CHUNK_BYTES = 12 * 1024
_MAX_CHUNKS = 32
_MAX_CAS_RETRIES = 4
_MAX_REGISTRY_CAS_RETRIES = 16
_DOMAIN_CAPACITY = 256
_REGISTRY_TTL_SECONDS = 30.0 * 86_400.0
_REGISTRY_HEADER = struct.Struct(">BH")
_REGISTRY_ENTRY = struct.Struct(">32sQ")


class CredentialBatchCoordinationError(RuntimeError):
    """Content-free boundary for invalid or unavailable batch coordination."""

    def __init__(self) -> None:
        super().__init__("Credential batch coordination failed.")


class CredentialBatchCapacityError(CredentialBatchCoordinationError):
    """The bounded preview or idempotency domain has no free admission slot."""


class BatchIdempotencyConflictError(CredentialBatchCoordinationError):
    """An idempotency key is already bound to another request fingerprint."""


class BatchIdempotencyInProgressError(CredentialBatchCoordinationError):
    """The matching idempotent request has an active owner."""


@dataclass(frozen=True, slots=True)
class BatchIdempotencyReplay:
    status_code: int
    body: dict[str, object]


@dataclass(frozen=True, slots=True)
class BatchIdempotencyReservation:
    root_key: str = field(repr=False)
    fingerprint: str = field(repr=False)
    owner_token: str = field(repr=False)
    revision: int
    registry_digest: bytes = field(repr=False)
    admission: CasRequest | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.root_key) is not str
            or not _IDEMPOTENCY_ROOT_PATTERN.fullmatch(self.root_key)
            or type(self.fingerprint) is not str
            or not _FINGERPRINT_PATTERN.fullmatch(self.fingerprint)
            or type(self.owner_token) is not str
            or not _OWNER_PATTERN.fullmatch(self.owner_token)
            or type(self.revision) is not int
            or self.revision <= 0
            or type(self.registry_digest) is not bytes
            or len(self.registry_digest) != 32
        ):
            raise CredentialBatchCoordinationError

    def __repr__(self) -> str:
        return f"BatchIdempotencyReservation(revision={self.revision!r}, owner='<redacted>')"


def _fingerprint(value: object) -> str:
    if type(value) is not str or not _FINGERPRINT_PATTERN.fullmatch(value):
        raise CredentialBatchCoordinationError
    return value


def _idempotency_key(value: object) -> str:
    if (
        type(value) is not str
        or not 8 <= len(value) <= 128
        or any(ord(character) < 32 or ord(character) > 126 for character in value)
    ):
        raise CredentialBatchCoordinationError
    return value


class CredentialBatchCoordinationService:
    """Coordinate previews and idempotent batch results across replicas."""

    __slots__ = (
        "_coordination",
        "_fencing_epoch",
        "_hmac_key",
        "_payload_key",
        "_token_factory",
    )

    def __init__(
        self,
        coordination: CoordinationStore,
        *,
        key: bytes,
        fencing_epoch: int,
        token_factory: Callable[[int], str] = secrets.token_urlsafe,
    ) -> None:
        try:
            if type(key) is not bytes or len(key) < 32 or not callable(token_factory):
                raise CredentialBatchCoordinationError
            validate_epoch(fencing_epoch)
            if any(
                not callable(getattr(coordination, method, None))
                for method in ("compare_and_set", "read_cas", "read_coordination_time")
            ):
                raise CredentialBatchCoordinationError
        except CredentialBatchCoordinationError:
            raise CredentialBatchCoordinationError from None
        except Exception:
            raise CredentialBatchCoordinationError from None
        self._coordination = coordination
        self._fencing_epoch = fencing_epoch
        self._token_factory = token_factory
        self._hmac_key = hmac.digest(key, _HMAC_DOMAIN + b"index-key", hashlib.sha256)
        self._payload_key = hmac.digest(key, _PAYLOAD_KEY_DOMAIN, hashlib.sha256)

    def __repr__(self) -> str:
        return (
            "CredentialBatchCoordinationService("
            f"fencing_epoch={self._fencing_epoch!r}, key='<redacted>')"
        )

    @staticmethod
    def _operation_id(action: str) -> str:
        return f"credential-batch-{action}-{secrets.token_hex(16)}"

    def _key(self, label: bytes, value: str) -> str:
        digest = hmac.digest(
            self._hmac_key,
            _HMAC_DOMAIN + label + b"\0" + value.encode("utf-8"),
            hashlib.sha256,
        ).hex()
        return f"credential-batch-{label.decode('ascii')}-{digest}"

    def _chunk_key(self, root_key: str, owner_token: str, index: int) -> str:
        return self._key(b"chunk", f"{root_key}\0{owner_token}\0{index}")

    @staticmethod
    def _settlement_proof(
        reservation: BatchIdempotencyReservation,
        key: str,
        transition: CasSettlementTransition,
    ) -> CasSettlementProof | None:
        if reservation.admission is None:
            return None
        return CasSettlementProof(
            reservation.admission,
            CasSettlementTarget(key, transition),
        )

    def _registry_key(self, domain: str) -> str:
        return self._key(b"capacity", domain)

    def _registry_digest(self, domain: str, identifier: str) -> bytes:
        return hmac.digest(
            self._hmac_key,
            _HMAC_DOMAIN + b"capacity\0" + domain.encode("ascii") + b"\0" + identifier.encode(),
            hashlib.sha256,
        )

    def _encrypt(self, key: str, payload: bytes) -> bytes:
        nonce = secrets.token_bytes(12)
        return (
            b"\x01"
            + nonce
            + AESGCM(self._payload_key).encrypt(
                nonce,
                payload,
                b"\0".join((_PAYLOAD_AAD, key.encode("ascii"))),
            )
        )

    def _decrypt(self, key: str, payload: bytes) -> bytes:
        try:
            if len(payload) < 30 or payload[0] != 1:
                raise ValueError
            return AESGCM(self._payload_key).decrypt(
                payload[1:13],
                payload[13:],
                b"\0".join((_PAYLOAD_AAD, key.encode("ascii"))),
            )
        except Exception:
            raise CredentialBatchCoordinationError from None

    def _encode_record(self, key: str, record: dict[str, object]) -> bytes:
        return self._encrypt(
            key,
            json.dumps(
                record,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii"),
        )

    def _decode_record(self, key: str, payload: bytes) -> dict[str, object]:
        try:
            pairs = json.loads(self._decrypt(key, payload), object_pairs_hook=lambda values: values)
            if type(pairs) is not list or any(type(pair) is not tuple for pair in pairs):
                raise ValueError
            record = dict(pairs)
            if len(record) != len(pairs) or set(record) != {
                "chunk_count",
                "fingerprint",
                "owner_token",
                "response_digest",
                "schema_version",
                "status",
                "status_code",
            }:
                raise ValueError
            status = record["status"]
            owner_token = record["owner_token"]
            chunk_count = record["chunk_count"]
            status_code = record["status_code"]
            response_digest = record["response_digest"]
            if (
                record["schema_version"] != 1
                or status not in {"pending", "completed", "released"}
                or type(record["fingerprint"]) is not str
                or not _FINGERPRINT_PATTERN.fullmatch(record["fingerprint"])
                or type(owner_token) is not str
                or type(chunk_count) is not int
                or type(status_code) is not int
                or type(response_digest) is not str
            ):
                raise ValueError
            if status == "pending" and (
                not _OWNER_PATTERN.fullmatch(owner_token)
                or chunk_count != 0
                or status_code != 0
                or response_digest
            ):
                raise ValueError
            if status == "completed" and (
                not _OWNER_PATTERN.fullmatch(owner_token)
                or not 1 <= chunk_count <= _MAX_CHUNKS
                or not 100 <= status_code <= 599
                or not _FINGERPRINT_PATTERN.fullmatch(response_digest)
            ):
                raise ValueError
            if status == "released" and (
                owner_token or chunk_count != 0 or status_code != 0 or response_digest
            ):
                raise ValueError
            return record
        except CredentialBatchCoordinationError:
            raise CredentialBatchCoordinationError from None

    def _encode_registry(self, key: str, entries: dict[bytes, int]) -> bytes:
        if len(entries) > _DOMAIN_CAPACITY:
            raise CredentialBatchCoordinationError
        raw = bytearray(_REGISTRY_HEADER.pack(1, len(entries)))
        for digest, expires_at_ms in sorted(entries.items()):
            if type(digest) is not bytes or len(digest) != 32 or type(expires_at_ms) is not int:
                raise CredentialBatchCoordinationError
            raw.extend(_REGISTRY_ENTRY.pack(digest, expires_at_ms))
        return self._encrypt(key, bytes(raw))

    def _decode_registry(self, key: str, payload: bytes) -> dict[bytes, int]:
        try:
            raw = self._decrypt(key, payload)
            if len(raw) < _REGISTRY_HEADER.size:
                raise ValueError
            version, count = _REGISTRY_HEADER.unpack_from(raw)
            if (
                version != 1
                or count > _DOMAIN_CAPACITY
                or len(raw) != _REGISTRY_HEADER.size + count * _REGISTRY_ENTRY.size
            ):
                raise ValueError
            entries: dict[bytes, int] = {}
            offset = _REGISTRY_HEADER.size
            for _ in range(count):
                digest, expires_at_ms = _REGISTRY_ENTRY.unpack_from(raw, offset)
                offset += _REGISTRY_ENTRY.size
                if digest in entries:
                    raise ValueError
                entries[digest] = expires_at_ms
            return entries
        except CredentialBatchCoordinationError:
            raise CredentialBatchCoordinationError from None
        except Exception:
            raise CredentialBatchCoordinationError from None

    async def _set_admission(
        self,
        domain: str,
        digest: bytes,
        ttl_seconds: float,
        *,
        require_existing: bool,
        settlement: CasSettlementProof | None = None,
    ) -> None:
        registry_key = self._registry_key(domain)
        try:
            if type(digest) is not bytes or len(digest) != 32:
                raise CredentialBatchCoordinationError
            now_ms = (
                await self._coordination.read_coordination_time(epoch=self._fencing_epoch)
            ).milliseconds
            expires_at_ms = now_ms + int(ttl_seconds * 1000)
            for _attempt in range(_MAX_REGISTRY_CAS_RETRIES):
                snapshot = await self._coordination.read_cas(
                    registry_key, epoch=self._fencing_epoch
                )
                entries = (
                    {}
                    if snapshot.payload is None
                    else self._decode_registry(registry_key, snapshot.payload)
                )
                entries = {
                    entry_digest: expiry
                    for entry_digest, expiry in entries.items()
                    if expiry > now_ms
                }
                if digest not in entries:
                    if require_existing:
                        raise CredentialBatchCoordinationError
                    if len(entries) >= _DOMAIN_CAPACITY:
                        raise CredentialBatchCapacityError
                entries[digest] = expires_at_ms
                result = await self._coordination.compare_and_set(
                    CasRequest(
                        registry_key,
                        snapshot.revision or 0,
                        self._encode_registry(registry_key, entries),
                        _REGISTRY_TTL_SECONDS,
                        self._fencing_epoch,
                        self._operation_id(f"{domain}-admit"),
                        settlement=settlement,
                    )
                )
                if result.applied:
                    return
            raise CredentialBatchCoordinationError
        except asyncio.CancelledError:
            raise
        except CredentialBatchCapacityError:
            raise CredentialBatchCapacityError from None
        except CredentialBatchCoordinationError:
            raise CredentialBatchCoordinationError from None
        except Exception:
            raise CredentialBatchCoordinationError from None

    async def _admit(self, domain: str, identifier: str, ttl_seconds: float) -> bytes:
        digest = self._registry_digest(domain, identifier)
        await self._set_admission(
            domain,
            digest,
            ttl_seconds,
            require_existing=False,
        )
        return digest

    async def _refresh_admission(
        self,
        domain: str,
        digest: bytes,
        ttl_seconds: float,
        settlement: CasSettlementProof | None = None,
    ) -> None:
        await self._set_admission(
            domain,
            digest,
            ttl_seconds,
            require_existing=True,
            settlement=settlement,
        )

    async def _remove_admission(
        self,
        domain: str,
        digest: bytes,
        settlement: CasSettlementProof | None = None,
    ) -> None:
        registry_key = self._registry_key(domain)
        try:
            now_ms = (
                await self._coordination.read_coordination_time(epoch=self._fencing_epoch)
            ).milliseconds
            for _attempt in range(_MAX_REGISTRY_CAS_RETRIES):
                snapshot = await self._coordination.read_cas(
                    registry_key, epoch=self._fencing_epoch
                )
                if snapshot.payload is None:
                    return
                entries = {
                    entry_digest: expiry
                    for entry_digest, expiry in self._decode_registry(
                        registry_key, snapshot.payload
                    ).items()
                    if expiry > now_ms and entry_digest != digest
                }
                result = await self._coordination.compare_and_set(
                    CasRequest(
                        registry_key,
                        snapshot.revision or 0,
                        self._encode_registry(registry_key, entries),
                        _REGISTRY_TTL_SECONDS,
                        self._fencing_epoch,
                        self._operation_id(f"{domain}-remove"),
                        settlement=settlement,
                    )
                )
                if result.applied:
                    return
            raise CredentialBatchCoordinationError
        except asyncio.CancelledError:
            raise
        except CredentialBatchCoordinationError:
            raise CredentialBatchCoordinationError from None
        except Exception:
            raise CredentialBatchCoordinationError from None

    @staticmethod
    def _pending_record(fingerprint: str, owner_token: str) -> dict[str, object]:
        return {
            "chunk_count": 0,
            "fingerprint": fingerprint,
            "owner_token": owner_token,
            "response_digest": "",
            "schema_version": 1,
            "status": "pending",
            "status_code": 0,
        }

    async def issue_preview(self, fingerprint: str) -> str:
        """Create one exact-selection preview token in shared coordination."""
        try:
            fingerprint = _fingerprint(fingerprint)
            token = self._token_factory(32)
            if type(token) is not str or not _PREVIEW_PATTERN.fullmatch(token):
                raise CredentialBatchCoordinationError
            await self._admit("preview", token, _PREVIEW_TTL_SECONDS)
            key = self._key(b"preview", token)
            payload = self._encode_record(
                key,
                {
                    "chunk_count": 0,
                    "fingerprint": fingerprint,
                    "owner_token": "",
                    "response_digest": "",
                    "schema_version": 1,
                    "status": "released",
                    "status_code": 0,
                },
            )
            result = await self._coordination.compare_and_set(
                CasRequest(
                    key,
                    0,
                    payload,
                    _PREVIEW_TTL_SECONDS,
                    self._fencing_epoch,
                    self._operation_id("preview"),
                )
            )
            if not result.applied:
                raise CredentialBatchCoordinationError
            return token
        except asyncio.CancelledError:
            raise
        except CredentialBatchCapacityError:
            raise CredentialBatchCapacityError from None
        except CredentialBatchCoordinationError:
            raise CredentialBatchCoordinationError from None
        except Exception:
            raise CredentialBatchCoordinationError from None

    async def preview_matches(self, token: str | None, fingerprint: str) -> bool:
        """Match one opaque preview against the exact batch fingerprint."""
        try:
            fingerprint = _fingerprint(fingerprint)
            if type(token) is not str or not _PREVIEW_PATTERN.fullmatch(token):
                return False
            key = self._key(b"preview", token)
            snapshot = await self._coordination.read_cas(key, epoch=self._fencing_epoch)
            if snapshot.payload is None:
                return False
            record = self._decode_record(key, snapshot.payload)
            if record["status"] != "released":
                raise CredentialBatchCoordinationError
            return hmac.compare_digest(str(record["fingerprint"]), fingerprint)
        except asyncio.CancelledError:
            raise
        except CredentialBatchCoordinationError:
            raise CredentialBatchCoordinationError from None
        except Exception:
            raise CredentialBatchCoordinationError from None

    async def _load_replay(
        self, root_key: str, record: dict[str, object]
    ) -> BatchIdempotencyReplay:
        owner_token = str(record["owner_token"])
        chunks: list[bytes] = []
        for index in range(int(record["chunk_count"])):
            chunk_key = self._chunk_key(root_key, owner_token, index)
            snapshot = await self._coordination.read_cas(chunk_key, epoch=self._fencing_epoch)
            if snapshot.payload is None:
                raise CredentialBatchCoordinationError
            chunks.append(self._decrypt(chunk_key, snapshot.payload))
        compressed = b"".join(chunks)
        if not hmac.compare_digest(
            hashlib.sha256(compressed).hexdigest(), str(record["response_digest"])
        ):
            raise CredentialBatchCoordinationError
        try:
            decompressor = zlib.decompressobj()
            raw = decompressor.decompress(compressed, _MAX_RESPONSE_BYTES + 1)
            if (
                len(raw) > _MAX_RESPONSE_BYTES
                or decompressor.unconsumed_tail
                or not decompressor.eof
                or decompressor.unused_data
            ):
                raise ValueError
            body = json.loads(raw)
            if type(body) is not dict:
                raise ValueError
            return BatchIdempotencyReplay(int(record["status_code"]), body)
        except Exception:
            raise CredentialBatchCoordinationError from None

    async def lookup(self, idempotency_key: str, fingerprint: str) -> BatchIdempotencyReplay | None:
        """Return a completed response or the exact active/conflict state."""
        try:
            idempotency_key = _idempotency_key(idempotency_key)
            fingerprint = _fingerprint(fingerprint)
            root_key = self._key(b"idempotency", idempotency_key)
            snapshot = await self._coordination.read_cas(root_key, epoch=self._fencing_epoch)
            if snapshot.payload is None:
                return None
            record = self._decode_record(root_key, snapshot.payload)
            if record["status"] == "released":
                return None
            if not hmac.compare_digest(str(record["fingerprint"]), fingerprint):
                raise BatchIdempotencyConflictError
            if record["status"] == "pending":
                raise BatchIdempotencyInProgressError
            return await self._load_replay(root_key, record)
        except asyncio.CancelledError:
            raise
        except BatchIdempotencyConflictError:
            raise BatchIdempotencyConflictError from None
        except BatchIdempotencyInProgressError:
            raise BatchIdempotencyInProgressError from None
        except CredentialBatchCoordinationError:
            raise CredentialBatchCoordinationError from None
        except Exception:
            raise CredentialBatchCoordinationError from None

    async def reserve(
        self, idempotency_key: str, fingerprint: str
    ) -> BatchIdempotencyReservation | BatchIdempotencyReplay:
        """Atomically reserve a request; active reservations never auto-take over."""
        try:
            idempotency_key = _idempotency_key(idempotency_key)
            fingerprint = _fingerprint(fingerprint)
            root_key = self._key(b"idempotency", idempotency_key)
            for _attempt in range(_MAX_CAS_RETRIES):
                snapshot = await self._coordination.read_cas(root_key, epoch=self._fencing_epoch)
                expected_revision = snapshot.revision or 0
                if snapshot.payload is not None:
                    record = self._decode_record(root_key, snapshot.payload)
                    if record["status"] != "released":
                        if not hmac.compare_digest(str(record["fingerprint"]), fingerprint):
                            raise BatchIdempotencyConflictError
                        if record["status"] == "pending":
                            raise BatchIdempotencyInProgressError
                        return await self._load_replay(root_key, record)
                owner_token = self._token_factory(32)
                if type(owner_token) is not str or not _OWNER_PATTERN.fullmatch(owner_token):
                    raise CredentialBatchCoordinationError
                registry_digest = await self._admit(
                    "idempotency", idempotency_key, _IDEMPOTENCY_TTL_SECONDS
                )
                admission = CasRequest(
                    root_key,
                    expected_revision,
                    self._encode_record(
                        root_key,
                        self._pending_record(fingerprint, owner_token),
                    ),
                    _IDEMPOTENCY_TTL_SECONDS,
                    self._fencing_epoch,
                    self._operation_id("reserve"),
                    settlement_targets=(
                        CasSettlementTarget(root_key, CasSettlementTransition.UPDATE),
                        CasSettlementTarget(
                            self._registry_key("idempotency"),
                            CasSettlementTransition.UPDATE,
                        ),
                        *(
                            CasSettlementTarget(
                                self._chunk_key(root_key, owner_token, index),
                                CasSettlementTransition.CREATE,
                            )
                            for index in range(_MAX_CHUNKS)
                        ),
                    ),
                )
                result = await self._coordination.compare_and_set(admission)
                if result.applied and result.revision is not None:
                    return BatchIdempotencyReservation(
                        root_key,
                        fingerprint,
                        owner_token,
                        result.revision,
                        registry_digest,
                        admission,
                    )
            raise CredentialBatchCoordinationError
        except asyncio.CancelledError:
            raise
        except BatchIdempotencyConflictError:
            raise BatchIdempotencyConflictError from None
        except BatchIdempotencyInProgressError:
            raise BatchIdempotencyInProgressError from None
        except CredentialBatchCapacityError:
            raise CredentialBatchCapacityError from None
        except CredentialBatchCoordinationError:
            raise CredentialBatchCoordinationError from None
        except Exception:
            raise CredentialBatchCoordinationError from None

    async def assert_owner(self, reservation: BatchIdempotencyReservation) -> None:
        """Fence each mutation against the exact live reservation revision."""
        try:
            if type(reservation) is not BatchIdempotencyReservation:
                raise CredentialBatchCoordinationError
            snapshot = await self._coordination.read_cas(
                reservation.root_key, epoch=self._fencing_epoch
            )
            if snapshot.revision != reservation.revision or snapshot.payload is None:
                raise CredentialBatchCoordinationError
            record = self._decode_record(reservation.root_key, snapshot.payload)
            if (
                record["status"] != "pending"
                or not hmac.compare_digest(str(record["fingerprint"]), reservation.fingerprint)
                or not hmac.compare_digest(str(record["owner_token"]), reservation.owner_token)
            ):
                raise CredentialBatchCoordinationError
        except asyncio.CancelledError:
            raise
        except CredentialBatchCoordinationError:
            raise CredentialBatchCoordinationError from None
        except Exception:
            raise CredentialBatchCoordinationError from None

    async def complete(
        self,
        reservation: BatchIdempotencyReservation,
        status_code: int,
        body: dict[str, object],
    ) -> None:
        """Write bounded chunks, then atomically publish the completed root."""
        try:
            if (
                type(reservation) is not BatchIdempotencyReservation
                or type(status_code) is not int
                or not 100 <= status_code <= 599
                or type(body) is not dict
            ):
                raise CredentialBatchCoordinationError
            snapshot = await self._coordination.read_cas(
                reservation.root_key, epoch=self._fencing_epoch
            )
            if snapshot.payload is not None:
                current = self._decode_record(reservation.root_key, snapshot.payload)
                if current["status"] == "completed":
                    if (
                        current["owner_token"] != reservation.owner_token
                        or current["fingerprint"] != reservation.fingerprint
                        or await self._load_replay(reservation.root_key, current)
                        != BatchIdempotencyReplay(status_code, body)
                    ):
                        raise CredentialBatchCoordinationError
                    return
            await self.assert_owner(reservation)
            await self._refresh_admission(
                "idempotency",
                reservation.registry_digest,
                _IDEMPOTENCY_TTL_SECONDS,
                self._settlement_proof(
                    reservation,
                    self._registry_key("idempotency"),
                    CasSettlementTransition.UPDATE,
                ),
            )
            raw = json.dumps(
                body,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(raw) > _MAX_RESPONSE_BYTES:
                raise CredentialBatchCoordinationError
            compressed = zlib.compress(raw, level=9)
            chunks = [
                compressed[offset : offset + _CHUNK_BYTES]
                for offset in range(0, len(compressed), _CHUNK_BYTES)
            ]
            if not 1 <= len(chunks) <= _MAX_CHUNKS:
                raise CredentialBatchCoordinationError
            for index, chunk in enumerate(chunks):
                chunk_key = self._chunk_key(reservation.root_key, reservation.owner_token, index)
                existing_chunk = await self._coordination.read_cas(
                    chunk_key, epoch=self._fencing_epoch
                )
                if existing_chunk.payload is not None:
                    if self._decrypt(chunk_key, existing_chunk.payload) != chunk:
                        raise CredentialBatchCoordinationError
                    continue
                result = await self._coordination.compare_and_set(
                    CasRequest(
                        chunk_key,
                        0,
                        self._encrypt(chunk_key, chunk),
                        _IDEMPOTENCY_TTL_SECONDS,
                        self._fencing_epoch,
                        self._operation_id("chunk"),
                        settlement=self._settlement_proof(
                            reservation,
                            chunk_key,
                            CasSettlementTransition.CREATE,
                        ),
                    )
                )
                if not result.applied:
                    raise CredentialBatchCoordinationError
            completed = {
                "chunk_count": len(chunks),
                "fingerprint": reservation.fingerprint,
                "owner_token": reservation.owner_token,
                "response_digest": hashlib.sha256(compressed).hexdigest(),
                "schema_version": 1,
                "status": "completed",
                "status_code": status_code,
            }
            result = await self._coordination.compare_and_set(
                CasRequest(
                    reservation.root_key,
                    reservation.revision,
                    self._encode_record(reservation.root_key, completed),
                    _IDEMPOTENCY_TTL_SECONDS,
                    self._fencing_epoch,
                    self._operation_id("complete"),
                    settlement=self._settlement_proof(
                        reservation,
                        reservation.root_key,
                        CasSettlementTransition.UPDATE,
                    ),
                )
            )
            if not result.applied:
                raise CredentialBatchCoordinationError
        except asyncio.CancelledError:
            raise
        except CredentialBatchCoordinationError:
            raise CredentialBatchCoordinationError from None
        except Exception:
            raise CredentialBatchCoordinationError from None

    async def release(self, reservation: BatchIdempotencyReservation) -> None:
        """Release an unstarted reservation so a safe retry may acquire it."""
        try:
            if type(reservation) is not BatchIdempotencyReservation:
                raise CredentialBatchCoordinationError
            snapshot = await self._coordination.read_cas(
                reservation.root_key, epoch=self._fencing_epoch
            )
            if snapshot.payload is not None and snapshot.revision == reservation.revision + 1:
                current = self._decode_record(reservation.root_key, snapshot.payload)
                if (
                    current["status"] == "released"
                    and current["fingerprint"] == reservation.fingerprint
                ):
                    await self._remove_admission(
                        "idempotency",
                        reservation.registry_digest,
                        self._settlement_proof(
                            reservation,
                            self._registry_key("idempotency"),
                            CasSettlementTransition.UPDATE,
                        ),
                    )
                    return
            await self.assert_owner(reservation)
            released = {
                "chunk_count": 0,
                "fingerprint": reservation.fingerprint,
                "owner_token": "",
                "response_digest": "",
                "schema_version": 1,
                "status": "released",
                "status_code": 0,
            }
            result = await self._coordination.compare_and_set(
                CasRequest(
                    reservation.root_key,
                    reservation.revision,
                    self._encode_record(reservation.root_key, released),
                    _RELEASE_TTL_SECONDS,
                    self._fencing_epoch,
                    self._operation_id("release"),
                    settlement=self._settlement_proof(
                        reservation,
                        reservation.root_key,
                        CasSettlementTransition.UPDATE,
                    ),
                )
            )
            if not result.applied:
                raise CredentialBatchCoordinationError
            await self._remove_admission(
                "idempotency",
                reservation.registry_digest,
                self._settlement_proof(
                    reservation,
                    self._registry_key("idempotency"),
                    CasSettlementTransition.UPDATE,
                ),
            )
        except asyncio.CancelledError:
            raise
        except CredentialBatchCoordinationError:
            raise CredentialBatchCoordinationError from None
        except Exception:
            raise CredentialBatchCoordinationError from None


_credential_batch_coordination_service: CredentialBatchCoordinationService | None = None


def configure_credential_batch_coordination_service(
    service: CredentialBatchCoordinationService | None,
) -> None:
    if service is not None and type(service) is not CredentialBatchCoordinationService:
        raise CredentialBatchCoordinationError
    global _credential_batch_coordination_service
    _credential_batch_coordination_service = service


def get_credential_batch_coordination_service() -> CredentialBatchCoordinationService:
    service = _credential_batch_coordination_service
    if service is None:
        raise CredentialBatchCoordinationError
    return service
