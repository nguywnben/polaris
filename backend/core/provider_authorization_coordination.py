"""Encrypted, provider-bound authorization transactions over shared coordination."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
from collections.abc import Callable

from core.coordination import validate_epoch
from core.security_coordination import (
    IdentitySecurityCoordinationStore,
    OidcTransactionConsumeRequest,
    OidcTransactionCreateRequest,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ALLOWED_PROVIDERS = frozenset({"claude", "xai"})
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_HMAC_DOMAIN = b"polaris:provider-authorization:v1\0"
_PAYLOAD_KEY_DOMAIN = b"polaris:provider-authorization-payload-key:v1\0"
_PAYLOAD_AAD = b"polaris:provider-authorization-payload:v1"
_MAX_STORED_PAYLOAD_BYTES = 8 * 1024
_ENCRYPTION_OVERHEAD_BYTES = 1 + 12 + 16
MAX_PROVIDER_AUTHORIZATION_PAYLOAD_BYTES = _MAX_STORED_PAYLOAD_BYTES - _ENCRYPTION_OVERHEAD_BYTES


class ProviderAuthorizationError(RuntimeError):
    """Content-free boundary for unavailable or invalid provider transactions."""

    def __init__(self) -> None:
        super().__init__("Provider authorization transaction failed.")


def _provider(value: object) -> str:
    if type(value) is not str or value not in _ALLOWED_PROVIDERS:
        raise ProviderAuthorizationError
    return value


def _state(provider: str, value: object) -> str:
    prefix = f"{provider}_"
    if (
        type(value) is not str
        or not value.startswith(prefix)
        or not _TOKEN_PATTERN.fullmatch(value[len(prefix) :])
    ):
        raise ProviderAuthorizationError
    return value


def is_provider_authorization_state(provider: str, state: object) -> bool:
    """Classify callback state syntactically without reading shared secret state."""
    try:
        _state(_provider(provider), state)
    except ProviderAuthorizationError:
        return False
    return True


class ProviderAuthorizationService:
    """One-time authorization adapter over fenced identity coordination."""

    __slots__ = (
        "_coordination",
        "_fencing_epoch",
        "_hmac_key",
        "_payload_key",
        "_token_factory",
    )

    def __init__(
        self,
        coordination: IdentitySecurityCoordinationStore,
        *,
        key: bytes,
        fencing_epoch: int,
        token_factory: Callable[[int], str] = secrets.token_urlsafe,
    ) -> None:
        try:
            if type(key) is not bytes or len(key) < 32 or not callable(token_factory):
                raise ProviderAuthorizationError
            validate_epoch(fencing_epoch)
            if any(
                not callable(getattr(coordination, method, None))
                for method in ("create_oidc_transaction", "consume_oidc_transaction")
            ):
                raise ProviderAuthorizationError
        except ProviderAuthorizationError:
            raise ProviderAuthorizationError from None
        except Exception:
            raise ProviderAuthorizationError from None

        self._coordination = coordination
        self._fencing_epoch = fencing_epoch
        self._token_factory = token_factory
        self._hmac_key = hmac.digest(key, _HMAC_DOMAIN + b"index-key", hashlib.sha256)
        self._payload_key = hmac.digest(key, _PAYLOAD_KEY_DOMAIN, hashlib.sha256)

    def __repr__(self) -> str:
        return (
            f"ProviderAuthorizationService(fencing_epoch={self._fencing_epoch!r}, key='<redacted>')"
        )

    @staticmethod
    def _operation_id(action: str) -> str:
        return f"provider-auth-{action}-{secrets.token_hex(16)}"

    def _index(self, provider: str, label: bytes, state: str) -> str:
        return hmac.digest(
            self._hmac_key,
            _HMAC_DOMAIN + provider.encode("ascii") + b"\0" + label + b"\0" + state.encode("ascii"),
            hashlib.sha256,
        ).hex()

    @staticmethod
    def _payload_aad(provider: str, state_index: str, proof_index: str) -> bytes:
        return b"\0".join(
            (
                _PAYLOAD_AAD,
                provider.encode("ascii"),
                state_index.encode("ascii"),
                proof_index.encode("ascii"),
            )
        )

    def _encrypt(
        self,
        provider: str,
        payload: bytes,
        state_index: str,
        proof_index: str,
    ) -> bytes:
        nonce = secrets.token_bytes(12)
        return (
            b"\x01"
            + nonce
            + AESGCM(self._payload_key).encrypt(
                nonce,
                payload,
                self._payload_aad(provider, state_index, proof_index),
            )
        )

    def _decrypt(
        self,
        provider: str,
        payload: bytes,
        state_index: str,
        proof_index: str,
    ) -> bytes:
        if len(payload) < _ENCRYPTION_OVERHEAD_BYTES + 1 or payload[0] != 1:
            raise ProviderAuthorizationError
        plaintext = AESGCM(self._payload_key).decrypt(
            payload[1:13],
            payload[13:],
            self._payload_aad(provider, state_index, proof_index),
        )
        if not 1 <= len(plaintext) <= MAX_PROVIDER_AUTHORIZATION_PAYLOAD_BYTES:
            raise ProviderAuthorizationError
        return plaintext

    async def create(
        self,
        provider: str,
        payload: bytes,
        *,
        ttl_seconds: int | float,
    ) -> str:
        """Persist one encrypted transaction and return its provider-prefixed state."""
        try:
            provider = _provider(provider)
            if (
                type(payload) is not bytes
                or not 1 <= len(payload) <= MAX_PROVIDER_AUTHORIZATION_PAYLOAD_BYTES
                or isinstance(ttl_seconds, bool)
                or not isinstance(ttl_seconds, (int, float))
                or not 60 <= float(ttl_seconds) <= 900
            ):
                raise ProviderAuthorizationError
            token = self._token_factory(32)
            if type(token) is not str or not _TOKEN_PATTERN.fullmatch(token):
                raise ProviderAuthorizationError
            state = f"{provider}_{token}"
            state_index = self._index(provider, b"state", state)
            proof_index = self._index(provider, b"proof", state)
            result = await self._coordination.create_oidc_transaction(
                OidcTransactionCreateRequest(
                    state_index,
                    proof_index,
                    self._encrypt(provider, payload, state_index, proof_index),
                    float(ttl_seconds),
                    self._fencing_epoch,
                    self._operation_id("create"),
                )
            )
            if not result.applied:
                raise ProviderAuthorizationError
            return state
        except asyncio.CancelledError:
            raise
        except ProviderAuthorizationError:
            raise ProviderAuthorizationError from None
        except Exception:
            raise ProviderAuthorizationError from None

    async def consume(self, provider: str, state: str) -> bytes:
        """Atomically consume and decrypt a provider-bound transaction."""
        try:
            provider = _provider(provider)
            state = _state(provider, state)
            state_index = self._index(provider, b"state", state)
            proof_index = self._index(provider, b"proof", state)
            result = await self._coordination.consume_oidc_transaction(
                OidcTransactionConsumeRequest(
                    state_index,
                    proof_index,
                    self._fencing_epoch,
                    self._operation_id("consume"),
                )
            )
            if not result.consumed or result.payload is None:
                raise ProviderAuthorizationError
            return self._decrypt(
                provider,
                result.payload,
                state_index,
                proof_index,
            )
        except asyncio.CancelledError:
            raise
        except ProviderAuthorizationError:
            raise ProviderAuthorizationError from None
        except Exception:
            raise ProviderAuthorizationError from None


_provider_authorization_service: ProviderAuthorizationService | None = None


def configure_provider_authorization_service(
    service: ProviderAuthorizationService | None,
) -> None:
    """Inject or clear the lifecycle-owned provider authorization service."""
    if service is not None and type(service) is not ProviderAuthorizationService:
        raise ProviderAuthorizationError
    global _provider_authorization_service
    _provider_authorization_service = service


def get_provider_authorization_service() -> ProviderAuthorizationService:
    """Return the lifecycle-owned service and fail closed before initialization."""
    service = _provider_authorization_service
    if service is None:
        raise ProviderAuthorizationError
    return service
