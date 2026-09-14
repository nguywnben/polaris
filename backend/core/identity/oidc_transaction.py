"""Bounded, one-time OIDC authorization transactions for standalone mode."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core.identity.oidc_discovery import OidcDiscoveryDocument
from core.identity.oidc_http import OidcHttpError, validate_oidc_endpoint_url
from core.identity.oidc_policy import OidcPolicy
from core.security_coordination import (
    IdentitySecurityCoordinationStore,
    OidcTransactionConsumeRequest,
    OidcTransactionCreateRequest,
)
from core.state_store import InMemoryStateStore
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_HMAC_DOMAIN = b"polaris:oidc-transaction:v1\0"
_PAYLOAD_KEY_DOMAIN = b"polaris:oidc-transaction-payload-key:v1\0"
_PAYLOAD_AAD = b"polaris:oidc-transaction-payload:v1"
_MAX_AUTHORIZATION_URL_LENGTH = 8_192
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_TOKEN_AUTH_METHODS = frozenset({"client_secret_basic", "client_secret_post"})
_RESERVED_AUTHORIZATION_PARAMETERS = frozenset(
    {
        "client_id",
        "code_challenge",
        "code_challenge_method",
        "nonce",
        "redirect_uri",
        "response_type",
        "scope",
        "state",
    }
)


class OidcAuthorizationTransactionError(RuntimeError):
    """Content-free boundary for unavailable or invalid OIDC transactions."""

    def __init__(self) -> None:
        super().__init__("OIDC authorization transaction failed.")


@dataclass(frozen=True, slots=True)
class OidcAuthorizationRequest:
    """Browser redirect material; callers must never log or persist this object."""

    authorization_url: str
    browser_token: str
    expires_in_seconds: int

    def __repr__(self) -> str:
        return (
            "OidcAuthorizationRequest(authorization_url='<redacted>', "
            "browser_token='<redacted>', "
            f"expires_in_seconds={self.expires_in_seconds!r})"
        )


@dataclass(frozen=True, slots=True)
class OidcTransactionProof:
    """Consumed transaction proof for the immediate token-exchange boundary."""

    issuer: str
    client_id: str
    redirect_uri: str
    authorization_endpoint: str
    token_endpoint: str
    token_endpoint_auth_method: str
    code_verifier: str
    nonce: str
    policy_revision: int

    def __repr__(self) -> str:
        return (
            "OidcTransactionProof("
            f"issuer={self.issuer!r}, client_id={self.client_id!r}, "
            f"redirect_uri={self.redirect_uri!r}, "
            f"authorization_endpoint={self.authorization_endpoint!r}, "
            f"token_endpoint={self.token_endpoint!r}, "
            f"token_endpoint_auth_method={self.token_endpoint_auth_method!r}, "
            "code_verifier='<redacted>', nonce='<redacted>', "
            f"policy_revision={self.policy_revision!r})"
        )


def _token(value: object) -> str:
    if type(value) is not str or not _TOKEN_PATTERN.fullmatch(value):
        raise OidcAuthorizationTransactionError
    return value


def _digest(key: bytes, label: bytes, value: str) -> str:
    return hmac.digest(
        key,
        _HMAC_DOMAIN + label + b"\0" + value.encode("ascii"),
        hashlib.sha256,
    ).hex()


def _derived_token(key: bytes, label: bytes, state: str) -> str:
    value = hmac.digest(
        key,
        _HMAC_DOMAIN + label + b"\0" + state.encode("ascii"),
        hashlib.sha256,
    )
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _authorization_url(
    policy: OidcPolicy,
    discovery: OidcDiscoveryDocument,
    *,
    state: str,
    nonce: str,
    code_challenge: str,
) -> str:
    try:
        parsed = urlsplit(discovery.authorization_endpoint)
        existing = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=32,
        )
    except (TypeError, ValueError) as exc:
        raise OidcAuthorizationTransactionError from exc
    names = [name.lower() for name, _value in existing]
    if (
        len(names) != len(set(names))
        or any(name in _RESERVED_AUTHORIZATION_PARAMETERS for name in names)
        or policy.client_id is None
        or policy.redirect_uri is None
    ):
        raise OidcAuthorizationTransactionError
    parameters = existing + [
        ("response_type", "code"),
        ("client_id", policy.client_id),
        ("redirect_uri", policy.redirect_uri),
        ("scope", " ".join(policy.scopes)),
        ("state", state),
        ("nonce", nonce),
        ("code_challenge", code_challenge),
        ("code_challenge_method", "S256"),
    ]
    result = urlunsplit(parsed._replace(query=urlencode(parameters)))
    if len(result) > _MAX_AUTHORIZATION_URL_LENGTH:
        raise OidcAuthorizationTransactionError
    return result


class OidcAuthorizationTransactionService:
    """One-time browser transaction adapter over fenced security coordination."""

    __slots__ = (
        "_coordination",
        "_discovery",
        "_fencing_epoch",
        "_hmac_key",
        "_max_pending",
        "_payload_key",
        "_policy",
        "_token_factory",
        "_ttl_seconds",
    )

    def __init__(
        self,
        policy: OidcPolicy,
        discovery: OidcDiscoveryDocument,
        *,
        hmac_key: bytes,
        coordination: IdentitySecurityCoordinationStore | None = None,
        fencing_epoch: int = 1,
        clock: Callable[[], float] = time.monotonic,
        token_factory: Callable[[int], str] = secrets.token_urlsafe,
        ttl_seconds: int = 300,
        max_pending: int = 1_000,
    ) -> None:
        """Create a standalone store.

        ``token_factory`` is a deterministic test seam; production callers must keep the default
        cryptographic generator, which returns 32 random bytes as canonical base64url text.
        """
        try:
            if (
                type(policy) is not OidcPolicy
                or not policy.enabled
                or policy.issuer is None
                or policy.client_id is None
                or policy.redirect_uri is None
                or type(discovery) is not OidcDiscoveryDocument
                or discovery.issuer != policy.issuer
                or "code" not in discovery.response_types
                or discovery.code_challenge_methods != ("S256",)
                or not discovery.token_endpoint_auth_methods
                or any(
                    method not in _TOKEN_AUTH_METHODS
                    for method in discovery.token_endpoint_auth_methods
                )
                or type(hmac_key) is not bytes
                or len(hmac_key) < 32
                or type(fencing_epoch) is not int
                or fencing_epoch < 1
                or not callable(clock)
                or not callable(token_factory)
                or type(ttl_seconds) is not int
                or not 60 <= ttl_seconds <= 900
                or type(max_pending) is not int
                or not 1 <= max_pending <= 10_000
            ):
                raise OidcAuthorizationTransactionError
            validate_oidc_endpoint_url(policy, discovery.authorization_endpoint)
            validate_oidc_endpoint_url(policy, discovery.token_endpoint)
            _authorization_url(
                policy,
                discovery,
                state="A" * 43,
                nonce="B" * 43,
                code_challenge="C" * 43,
            )
        except (OidcAuthorizationTransactionError, OidcHttpError):
            raise OidcAuthorizationTransactionError from None
        self._policy = policy
        self._discovery = discovery
        self._hmac_key = hmac_key
        self._fencing_epoch = fencing_epoch
        self._token_factory = token_factory
        self._ttl_seconds = ttl_seconds
        self._max_pending = max_pending
        self._coordination = (
            coordination
            if coordination is not None
            else InMemoryStateStore(
                clock=clock,
                _oidc_transaction_limit_for_testing=max_pending,
            )
        )
        if any(
            not callable(getattr(self._coordination, method, None))
            for method in ("create_oidc_transaction", "consume_oidc_transaction")
        ):
            raise OidcAuthorizationTransactionError
        self._payload_key = hmac.digest(
            hmac_key,
            _PAYLOAD_KEY_DOMAIN,
            hashlib.sha256,
        )

    def __repr__(self) -> str:
        return (
            "OidcAuthorizationTransactionService("
            f"policy_revision={self._policy.revision!r}, "
            f"issuer={self._policy.issuer!r}, "
            f"fencing_epoch={self._fencing_epoch!r}, "
            f"ttl_seconds={self._ttl_seconds!r}, max_pending={self._max_pending!r})"
        )

    def matches_configuration(
        self,
        policy: OidcPolicy,
        discovery: OidcDiscoveryDocument,
    ) -> bool:
        """Return whether callers may reuse this service for the current trust snapshot.

        A false result requires replacing the service and dropping its pending transactions before
        accepting another begin or callback operation.
        """
        return self._policy == policy and self._discovery == discovery

    @staticmethod
    def _operation_id(action: str) -> str:
        return f"oidc-{action}-{secrets.token_hex(16)}"

    @staticmethod
    def _payload_aad(state_digest: str, browser_digest: str) -> bytes:
        return b"\0".join(
            (
                _PAYLOAD_AAD,
                state_digest.encode("ascii"),
                browser_digest.encode("ascii"),
            )
        )

    def _encode_payload(self, state_digest: str, browser_digest: str) -> bytes:
        body = json.dumps(
            {
                "authorization_endpoint": self._discovery.authorization_endpoint,
                "client_id": self._policy.client_id,
                "issuer": self._policy.issuer,
                "policy_revision": self._policy.revision,
                "redirect_uri": self._policy.redirect_uri,
                "schema_version": 1,
                "token_endpoint": self._discovery.token_endpoint,
                "token_endpoint_auth_method": self._discovery.token_endpoint_auth_methods[0],
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        nonce = secrets.token_bytes(12)
        return (
            b"\x01"
            + nonce
            + AESGCM(self._payload_key).encrypt(
                nonce,
                body,
                self._payload_aad(state_digest, browser_digest),
            )
        )

    def _decode_payload(
        self,
        payload: bytes,
        *,
        state_digest: str,
        browser_digest: str,
    ) -> dict[str, object]:
        try:
            if len(payload) < 30 or payload[0] != 1:
                raise ValueError
            plaintext = AESGCM(self._payload_key).decrypt(
                payload[1:13],
                payload[13:],
                self._payload_aad(state_digest, browser_digest),
            )
            pairs = json.loads(plaintext, object_pairs_hook=lambda values: values)
            if type(pairs) is not list or any(
                type(pair) is not tuple or len(pair) != 2 for pair in pairs
            ):
                raise ValueError
            data = dict(pairs)
            if len(data) != len(pairs) or set(data) != {
                "authorization_endpoint",
                "client_id",
                "issuer",
                "policy_revision",
                "redirect_uri",
                "schema_version",
                "token_endpoint",
                "token_endpoint_auth_method",
            }:
                raise ValueError
            expected = {
                "authorization_endpoint": self._discovery.authorization_endpoint,
                "client_id": self._policy.client_id,
                "issuer": self._policy.issuer,
                "policy_revision": self._policy.revision,
                "redirect_uri": self._policy.redirect_uri,
                "schema_version": 1,
                "token_endpoint": self._discovery.token_endpoint,
                "token_endpoint_auth_method": self._discovery.token_endpoint_auth_methods[0],
            }
            if data != expected:
                raise ValueError
            return data
        except Exception:
            raise OidcAuthorizationTransactionError from None

    async def begin(self) -> OidcAuthorizationRequest:
        """Create one transaction and return browser-only redirect material."""
        try:
            state = _token(self._token_factory(32))
            browser_token = _token(self._token_factory(32))
            state_digest = _digest(self._hmac_key, b"state", state)
            browser_digest = _digest(self._hmac_key, b"browser", browser_token)
            nonce = _derived_token(self._hmac_key, b"nonce", state)
            verifier = _derived_token(self._hmac_key, b"verifier", state)
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
                .rstrip(b"=")
                .decode("ascii")
            )
            authorization_url = _authorization_url(
                self._policy,
                self._discovery,
                state=state,
                nonce=nonce,
                code_challenge=challenge,
            )
            result = await self._coordination.create_oidc_transaction(
                OidcTransactionCreateRequest(
                    state_digest,
                    browser_digest,
                    self._encode_payload(state_digest, browser_digest),
                    self._ttl_seconds,
                    self._fencing_epoch,
                    self._operation_id("create"),
                )
            )
            if not result.applied:
                raise OidcAuthorizationTransactionError
            return OidcAuthorizationRequest(
                authorization_url=authorization_url,
                browser_token=browser_token,
                expires_in_seconds=self._ttl_seconds,
            )
        except asyncio.CancelledError:
            raise
        except OidcAuthorizationTransactionError:
            raise OidcAuthorizationTransactionError from None
        except Exception:
            raise OidcAuthorizationTransactionError from None

    async def consume(
        self,
        *,
        state: str,
        browser_token: str,
        response_issuer: str | None = None,
    ) -> OidcTransactionProof:
        """Consume one browser-bound transaction; pass the response issuer whenever supplied."""
        try:
            state = _token(state)
            browser_token = _token(browser_token)
            if response_issuer is not None and (
                type(response_issuer) is not str
                or not response_issuer
                or len(response_issuer) > 2_048
                or response_issuer != response_issuer.strip()
                or any(
                    ord(character) < 0x20 or ord(character) > 0x7E for character in response_issuer
                )
            ):
                raise OidcAuthorizationTransactionError
            state_digest = _digest(self._hmac_key, b"state", state)
            browser_digest = _digest(self._hmac_key, b"browser", browser_token)
            result = await self._coordination.consume_oidc_transaction(
                OidcTransactionConsumeRequest(
                    state_digest,
                    browser_digest,
                    self._fencing_epoch,
                    self._operation_id("consume"),
                )
            )
            if not result.consumed or result.payload is None:
                raise OidcAuthorizationTransactionError
            record = self._decode_payload(
                result.payload,
                state_digest=state_digest,
                browser_digest=browser_digest,
            )
            if response_issuer is not None and not hmac.compare_digest(
                response_issuer.encode("ascii"),
                str(record["issuer"]).encode("ascii"),
            ):
                raise OidcAuthorizationTransactionError
            return OidcTransactionProof(
                issuer=str(record["issuer"]),
                client_id=str(record["client_id"]),
                redirect_uri=str(record["redirect_uri"]),
                authorization_endpoint=str(record["authorization_endpoint"]),
                token_endpoint=str(record["token_endpoint"]),
                token_endpoint_auth_method=str(record["token_endpoint_auth_method"]),
                code_verifier=_derived_token(self._hmac_key, b"verifier", state),
                nonce=_derived_token(self._hmac_key, b"nonce", state),
                policy_revision=int(record["policy_revision"]),
            )
        except asyncio.CancelledError:
            raise
        except OidcAuthorizationTransactionError:
            raise OidcAuthorizationTransactionError from None
        except Exception:
            raise OidcAuthorizationTransactionError from None
