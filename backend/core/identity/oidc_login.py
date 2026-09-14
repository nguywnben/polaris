"""Lazy browser OIDC composition that preserves local recovery during IdP outages."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import math
import secrets
import time
from typing import Any

from core.identity.oidc_code_flow import OidcAuthorizationCodeFlow
from core.identity.oidc_discovery import discover_oidc
from core.identity.oidc_http import OidcHttpClient
from core.identity.oidc_id_token import OidcIdTokenVerifier
from core.identity.oidc_identity import OidcIdentityResolver
from core.identity.oidc_jwks import OidcJwksCache
from core.identity.oidc_policy import OidcConfiguration, load_oidc_configuration
from core.identity.oidc_transaction import (
    OidcAuthorizationRequest,
    OidcAuthorizationTransactionService,
)
from core.identity.repository import IdentityRepository, OidcPolicyRevisionRecord
from core.identity.sessions import IssuedSession, SessionService, get_session_service
from core.security_coordination import IdentitySecurityCoordinationStore

_OIDC_TRANSACTION_MASTER_KEY_CONFIG = "_internal_oidc_transaction_master_key_v1"
_OIDC_TRANSACTION_MASTER_KEY_BYTES = 32
_OIDC_TRANSACTION_HMAC_DOMAIN = b"polaris:oidc-transaction-master:v1\0"


class OidcLoginError(RuntimeError):
    """Content-free boundary for an unavailable or failed browser OIDC login."""

    def __init__(self) -> None:
        super().__init__("OIDC login failed.")


class OidcLoginDisabled(OidcLoginError):
    """OIDC is intentionally disabled for this process configuration."""


def _encode_master_key(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _decode_master_key(value: object) -> bytes:
    if type(value) is not str or len(value) > 128:
        raise OidcLoginError
    try:
        decoded = base64.b64decode(value, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise OidcLoginError from exc
    if len(decoded) != _OIDC_TRANSACTION_MASTER_KEY_BYTES or _encode_master_key(decoded) != value:
        raise OidcLoginError
    return decoded


async def _transaction_hmac_key(storage: Any) -> bytes:
    encoded = await storage.get_config(_OIDC_TRANSACTION_MASTER_KEY_CONFIG, None)
    if encoded is None:
        generated = _encode_master_key(secrets.token_bytes(_OIDC_TRANSACTION_MASTER_KEY_BYTES))
        if not await storage.set_config(_OIDC_TRANSACTION_MASTER_KEY_CONFIG, generated):
            raise OidcLoginError
        encoded = await storage.get_config(_OIDC_TRANSACTION_MASTER_KEY_CONFIG, None)
    master_key = _decode_master_key(encoded)
    return hmac.digest(
        master_key,
        _OIDC_TRANSACTION_HMAC_DOMAIN + b"runtime-key",
        hashlib.sha256,
    )


class OidcLoginService:
    """Compose discovery, transaction, verification, identity, and session boundaries lazily."""

    __slots__ = (
        "_component_admission_lock",
        "_component_waiters",
        "_components_lock",
        "_configuration",
        "_discovery_failure_backoff_seconds",
        "_discovery_retry_after",
        "_flow",
        "_hmac_key",
        "_max_component_waiters",
        "_repository",
        "_resolver",
        "_session_service",
        "_transactions",
        "_transaction_coordination",
        "_transaction_fencing_epoch",
    )

    def __init__(
        self,
        configuration: OidcConfiguration,
        repository: IdentityRepository,
        session_service: SessionService,
        *,
        hmac_key: bytes | None,
        transaction_coordination: IdentitySecurityCoordinationStore | None = None,
        transaction_fencing_epoch: int = 1,
        max_component_waiters: int = 32,
        discovery_failure_backoff_seconds: float = 5.0,
    ) -> None:
        if type(configuration) is not OidcConfiguration:
            raise OidcLoginError
        if configuration.policy.enabled:
            if type(hmac_key) is not bytes or len(hmac_key) < 32:
                raise OidcLoginError
        elif hmac_key is not None:
            raise OidcLoginError
        if (
            type(max_component_waiters) is not int
            or not 1 <= max_component_waiters <= 1024
            or type(transaction_fencing_epoch) is not int
            or transaction_fencing_epoch < 1
            or type(discovery_failure_backoff_seconds) not in {int, float}
            or not math.isfinite(discovery_failure_backoff_seconds)
            or not 0.1 <= discovery_failure_backoff_seconds <= 300.0
        ):
            raise OidcLoginError
        self._configuration = configuration
        self._repository = repository
        self._session_service = session_service
        self._hmac_key = hmac_key
        self._transaction_coordination = transaction_coordination
        self._transaction_fencing_epoch = transaction_fencing_epoch
        self._flow: OidcAuthorizationCodeFlow | None = None
        self._transactions: OidcAuthorizationTransactionService | None = None
        self._resolver: OidcIdentityResolver | None = None
        self._components_lock = asyncio.Lock()
        self._component_admission_lock = asyncio.Lock()
        self._component_waiters = 0
        self._max_component_waiters = max_component_waiters
        self._discovery_failure_backoff_seconds = float(discovery_failure_backoff_seconds)
        self._discovery_retry_after = 0.0

    @classmethod
    async def create(
        cls,
        storage: Any,
        *,
        session_service: SessionService,
        transaction_coordination: IdentitySecurityCoordinationStore | None = None,
        transaction_fencing_epoch: int = 1,
    ) -> OidcLoginService:
        if type(transaction_fencing_epoch) is not int or transaction_fencing_epoch < 1:
            raise OidcLoginError
        try:
            repository = await storage.create_identity_repository()
            revision = await repository.get_oidc_policy_revision()
            configuration = load_oidc_configuration(revision)
            key = await _transaction_hmac_key(storage) if configuration.policy.enabled else None
            return cls(
                configuration,
                repository,
                session_service,
                hmac_key=key,
                transaction_coordination=transaction_coordination,
                transaction_fencing_epoch=transaction_fencing_epoch,
            )
        except asyncio.CancelledError:
            raise
        except OidcLoginError:
            raise OidcLoginError from None
        except Exception:
            raise OidcLoginError from None

    @property
    def enabled(self) -> bool:
        return self._configuration.policy.enabled

    def __repr__(self) -> str:
        return (
            "OidcLoginService("
            f"enabled={self.enabled!r}, "
            f"policy_revision={self._configuration.policy.revision!r}, "
            f"components_ready={self._flow is not None!r})"
        )

    async def _current_policy(self) -> OidcPolicyRevisionRecord:
        current = await self._repository.get_oidc_policy_revision()
        policy = self._configuration.policy
        if (
            type(current) is not OidcPolicyRevisionRecord
            or current.revision != policy.revision
            or current.authorization_epoch != policy.authorization_epoch
        ):
            raise OidcLoginError
        return current

    async def _components(
        self,
    ) -> tuple[
        OidcAuthorizationCodeFlow,
        OidcAuthorizationTransactionService,
        OidcIdentityResolver,
    ]:
        if not self.enabled:
            raise OidcLoginDisabled
        await self._current_policy()
        if self._flow is not None and self._transactions is not None and self._resolver is not None:
            return self._flow, self._transactions, self._resolver
        if time.monotonic() < self._discovery_retry_after:
            raise OidcLoginError
        async with self._component_admission_lock:
            if self._component_waiters >= self._max_component_waiters:
                raise OidcLoginError
            self._component_waiters += 1
        try:
            async with self._components_lock:
                if (
                    self._flow is not None
                    and self._transactions is not None
                    and self._resolver is not None
                ):
                    return self._flow, self._transactions, self._resolver
                if time.monotonic() < self._discovery_retry_after:
                    raise OidcLoginError
                policy = self._configuration.policy
                client = OidcHttpClient(policy)
                try:
                    discovery = await discover_oidc(policy, client)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self._discovery_retry_after = (
                        time.monotonic() + self._discovery_failure_backoff_seconds
                    )
                    raise OidcLoginError from None
                await self._current_policy()
                transactions = OidcAuthorizationTransactionService(
                    policy,
                    discovery,
                    hmac_key=self._hmac_key or b"",
                    coordination=self._transaction_coordination,
                    fencing_epoch=self._transaction_fencing_epoch,
                )
                jwks = OidcJwksCache(policy, discovery, client)
                verifier = OidcIdTokenVerifier(policy, discovery, jwks)
                flow = OidcAuthorizationCodeFlow(
                    self._configuration,
                    discovery,
                    transactions,
                    client,
                    verifier,
                )
                resolver = OidcIdentityResolver(policy, self._repository)
                self._transactions = transactions
                self._resolver = resolver
                self._flow = flow
                self._discovery_retry_after = 0.0
                return flow, transactions, resolver
        finally:
            async with self._component_admission_lock:
                self._component_waiters -= 1

    async def begin(self) -> OidcAuthorizationRequest:
        try:
            _flow, transactions, _resolver = await self._components()
            return await transactions.begin()
        except asyncio.CancelledError:
            raise
        except OidcLoginDisabled:
            raise OidcLoginDisabled from None
        except Exception:
            raise OidcLoginError from None

    async def complete(
        self,
        raw_query: bytes,
        *,
        browser_token: str,
        now: float,
    ) -> IssuedSession:
        try:
            flow, _transactions, resolver = await self._components()
            verified = await flow.complete(raw_query, browser_token=browser_token)
            resolved = await resolver.resolve(verified)
            return await self._session_service.issue_oidc(resolved, now=now)
        except asyncio.CancelledError:
            raise
        except OidcLoginDisabled:
            raise OidcLoginDisabled from None
        except Exception:
            raise OidcLoginError from None


_oidc_login_service: OidcLoginService | None = None
_oidc_login_service_lock = asyncio.Lock()
_oidc_transaction_coordination: IdentitySecurityCoordinationStore | None = None
_oidc_transaction_fencing_epoch = 1


def configure_oidc_transaction_coordination(
    coordination: IdentitySecurityCoordinationStore | None,
    *,
    fencing_epoch: int = 1,
) -> None:
    """Bind the lifecycle-owned transaction store before lazy OIDC initialization."""

    global _oidc_transaction_coordination, _oidc_transaction_fencing_epoch
    if type(fencing_epoch) is not int or fencing_epoch < 1:
        raise ValueError("OIDC transaction fencing epoch is invalid.")
    _oidc_transaction_coordination = coordination
    _oidc_transaction_fencing_epoch = fencing_epoch


async def get_or_initialize_oidc_login_service() -> OidcLoginService:
    global _oidc_login_service
    async with _oidc_login_service_lock:
        if _oidc_login_service is None:
            try:
                from core.storage_adapter import get_storage_adapter

                storage = await get_storage_adapter()
                _oidc_login_service = await OidcLoginService.create(
                    storage,
                    session_service=get_session_service(),
                    transaction_coordination=_oidc_transaction_coordination,
                    transaction_fencing_epoch=_oidc_transaction_fencing_epoch,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                raise OidcLoginError from None
        return _oidc_login_service


async def close_oidc_login_service() -> None:
    global _oidc_login_service
    async with _oidc_login_service_lock:
        _oidc_login_service = None
