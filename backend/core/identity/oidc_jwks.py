"""Bounded, rotation-safe JWKS parsing and single-flight caching."""

from __future__ import annotations

import asyncio
import base64
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from core.identity.oidc_discovery import OidcDiscoveryDocument
from core.identity.oidc_http import OidcHttpError, validate_oidc_endpoint_url
from core.identity.oidc_policy import OidcPolicy
from cryptography.hazmat.primitives.asymmetric import ec, rsa

_MAX_JWKS_KEYS = 64
_MAX_JWK_FIELDS = 32
_MAX_JWK_FIELD_NAME_LENGTH = 64
_MAX_KID_LENGTH = 128
_MAX_RSA_MODULUS_BYTES = 1_024
_MIN_RSA_MODULUS_BYTES = 256
_PRIVATE_JWK_FIELDS = frozenset({"d", "p", "q", "dp", "dq", "qi", "oth", "k"})
_RSA_ALGORITHMS = frozenset({"RS256", "PS256"})
_EC_ALGORITHMS = frozenset({"ES256"})


class OidcJwksError(RuntimeError):
    """Content-free boundary for invalid, unavailable, or poisoned JWKS data."""

    def __init__(self) -> None:
        super().__init__("OIDC JWKS failed.")


class OidcJwksClient(Protocol):
    async def get_json(self, url: str) -> object: ...


@dataclass(frozen=True, slots=True)
class OidcJwk:
    kid: str
    kty: str
    use: str | None
    key_ops: tuple[str, ...]
    alg: str | None
    supported_algorithms: tuple[str, ...]
    _material: tuple[tuple[str, str], ...]

    def to_public_jwk(self) -> dict[str, object]:
        value: dict[str, object] = dict(self._material)
        if self.use is not None:
            value["use"] = self.use
        if self.key_ops:
            value["key_ops"] = list(self.key_ops)
        if self.alg is not None:
            value["alg"] = self.alg
        return value

    def __repr__(self) -> str:
        return (
            "OidcJwk("
            f"kid={self.kid!r}, kty={self.kty!r}, alg={self.alg!r}, "
            f"supported_algorithms={self.supported_algorithms!r})"
        )


def _visible_text(value: object, *, maximum: int) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(not 0x21 <= ord(character) <= 0x7E for character in value)
    ):
        raise OidcJwksError
    return value


def _base64url(value: object, *, minimum: int, maximum: int) -> bytes:
    text = _visible_text(value, maximum=maximum * 2)
    if "=" in text:
        raise OidcJwksError
    try:
        padding = "=" * (-len(text) % 4)
        decoded = base64.b64decode(text + padding, altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise OidcJwksError from exc
    if (
        not minimum <= len(decoded) <= maximum
        or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != text
    ):
        raise OidcJwksError
    return decoded


def _optional_use(key: dict[str, object]) -> str | None:
    if "use" not in key:
        return None
    use = _visible_text(key["use"], maximum=16)
    if use != "sig":
        raise OidcJwksError
    return use


def _optional_key_ops(key: dict[str, object]) -> tuple[str, ...]:
    if "key_ops" not in key:
        return ()
    value = key["key_ops"]
    if type(value) is not list or value != ["verify"]:
        raise OidcJwksError
    return ("verify",)


def _optional_algorithm(
    key: dict[str, object],
    *,
    candidates: frozenset[str],
    allowed_algorithms: tuple[str, ...],
) -> tuple[str | None, tuple[str, ...]]:
    if "alg" in key:
        algorithm = _visible_text(key["alg"], maximum=16)
        if algorithm not in candidates or algorithm not in allowed_algorithms:
            raise OidcJwksError
        return algorithm, (algorithm,)
    supported = tuple(algorithm for algorithm in allowed_algorithms if algorithm in candidates)
    if not supported:
        raise OidcJwksError
    return None, supported


def _rsa_material(key: dict[str, object]) -> tuple[tuple[str, str], ...]:
    modulus = _base64url(
        key.get("n"),
        minimum=_MIN_RSA_MODULUS_BYTES,
        maximum=_MAX_RSA_MODULUS_BYTES,
    )
    exponent = _base64url(key.get("e"), minimum=1, maximum=4)
    exponent_value = int.from_bytes(exponent, "big")
    if modulus[0] == 0 or exponent[0] == 0 or exponent_value < 3 or exponent_value % 2 == 0:
        raise OidcJwksError
    try:
        rsa.RSAPublicNumbers(exponent_value, int.from_bytes(modulus, "big")).public_key()
    except ValueError as exc:
        raise OidcJwksError from exc
    return (("kty", "RSA"), ("kid", str(key["kid"])), ("n", str(key["n"])), ("e", str(key["e"])))


def _ec_material(key: dict[str, object]) -> tuple[tuple[str, str], ...]:
    if key.get("crv") != "P-256":
        raise OidcJwksError
    x = _base64url(key.get("x"), minimum=32, maximum=32)
    y = _base64url(key.get("y"), minimum=32, maximum=32)
    try:
        ec.EllipticCurvePublicNumbers(
            int.from_bytes(x, "big"),
            int.from_bytes(y, "big"),
            ec.SECP256R1(),
        ).public_key()
    except ValueError as exc:
        raise OidcJwksError from exc
    return (
        ("kty", "EC"),
        ("kid", str(key["kid"])),
        ("crv", "P-256"),
        ("x", str(key["x"])),
        ("y", str(key["y"])),
    )


def _jwk(value: object, *, allowed_algorithms: tuple[str, ...]) -> OidcJwk:
    if type(value) is not dict or not 1 <= len(value) <= _MAX_JWK_FIELDS:
        raise OidcJwksError
    key: dict[str, object] = value
    if any(
        type(name) is not str
        or not name
        or len(name) > _MAX_JWK_FIELD_NAME_LENGTH
        or any(not 0x21 <= ord(character) <= 0x7E for character in name)
        for name in key
    ):
        raise OidcJwksError
    if _PRIVATE_JWK_FIELDS.intersection(key):
        raise OidcJwksError
    kid = _visible_text(key.get("kid"), maximum=_MAX_KID_LENGTH)
    key_type = _visible_text(key.get("kty"), maximum=16)
    use = _optional_use(key)
    key_ops = _optional_key_ops(key)
    if key_type == "RSA":
        algorithm, supported = _optional_algorithm(
            key,
            candidates=_RSA_ALGORITHMS,
            allowed_algorithms=allowed_algorithms,
        )
        material = _rsa_material(key)
    elif key_type == "EC":
        algorithm, supported = _optional_algorithm(
            key,
            candidates=_EC_ALGORITHMS,
            allowed_algorithms=allowed_algorithms,
        )
        material = _ec_material(key)
    else:
        raise OidcJwksError
    return OidcJwk(
        kid=kid,
        kty=key_type,
        use=use,
        key_ops=key_ops,
        alg=algorithm,
        supported_algorithms=supported,
        _material=material,
    )


def _jwks(payload: object, *, allowed_algorithms: tuple[str, ...]) -> tuple[OidcJwk, ...]:
    if type(payload) is not dict or "keys" not in payload:
        raise OidcJwksError
    values = payload["keys"]
    if type(values) is not list or not 1 <= len(values) <= _MAX_JWKS_KEYS:
        raise OidcJwksError
    keys = tuple(_jwk(value, allowed_algorithms=allowed_algorithms) for value in values)
    kids = tuple(key.kid for key in keys)
    if len(kids) != len(set(kids)):
        raise OidcJwksError
    return keys


class OidcJwksCache:
    """One-policy JWKS snapshot with atomic bounded rotation and single-flight refresh."""

    def __init__(
        self,
        policy: OidcPolicy,
        discovery: OidcDiscoveryDocument,
        client: OidcJwksClient,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            type(policy) is not OidcPolicy
            or not policy.enabled
            or type(discovery) is not OidcDiscoveryDocument
            or discovery.issuer != policy.issuer
            or not discovery.jwks_uri
            or not discovery.id_token_signing_algorithms
            or any(
                algorithm not in policy.id_token_signing_algorithms
                for algorithm in discovery.id_token_signing_algorithms
            )
        ):
            raise OidcJwksError
        try:
            validate_oidc_endpoint_url(policy, discovery.jwks_uri)
        except OidcHttpError as exc:
            raise OidcJwksError from exc
        self._policy = policy
        self._discovery = discovery
        self._client = client
        self._clock = clock
        self._keys: tuple[OidcJwk, ...] = ()
        self._by_kid: dict[str, OidcJwk] = {}
        self._expires_at = 0.0
        self._retry_after = 0.0
        self._retry_delay_seconds = min(5, max(1, policy.connect_timeout_seconds))
        self._unknown_refresh_after = 0.0
        self._generation = 0
        self._refresh_attempt = 0
        self._lock = asyncio.Lock()

    @property
    def policy_revision(self) -> int:
        return self._policy.revision

    @property
    def generation(self) -> int:
        return self._generation

    def matches_configuration(
        self,
        policy: OidcPolicy,
        discovery: OidcDiscoveryDocument,
    ) -> bool:
        """Return whether this cache is bound to the exact immutable trust configuration."""
        return self._policy == policy and self._discovery == discovery

    def _now(self) -> float:
        try:
            value = float(self._clock())
        except (TypeError, ValueError) as exc:
            raise OidcJwksError from exc
        if not math.isfinite(value) or value < 0:
            raise OidcJwksError
        return value

    def _fresh(self, now: float) -> bool:
        return self._generation > 0 and now < self._expires_at

    async def _fetch(self) -> tuple[OidcJwk, ...]:
        try:
            payload = await self._client.get_json(self._discovery.jwks_uri)
            return _jwks(
                payload,
                allowed_algorithms=self._discovery.id_token_signing_algorithms,
            )
        except asyncio.CancelledError:
            raise
        except OidcJwksError:
            raise
        except Exception as exc:
            raise OidcJwksError from exc

    async def get_keys(self, *, force_refresh: bool = False) -> tuple[OidcJwk, ...]:
        if type(force_refresh) is not bool:
            raise OidcJwksError
        observed_generation = self._generation
        observed_attempt = self._refresh_attempt
        now = self._now()
        if not force_refresh and self._fresh(now):
            return self._keys
        if now < self._retry_after:
            raise OidcJwksError
        async with self._lock:
            now = self._now()
            if not force_refresh and self._fresh(now):
                return self._keys
            if now < self._retry_after:
                raise OidcJwksError
            if self._refresh_attempt != observed_attempt:
                if self._fresh(now):
                    return self._keys
                raise OidcJwksError
            if force_refresh and self._generation != observed_generation and self._fresh(now):
                return self._keys
            self._refresh_attempt += 1
            try:
                keys = await self._fetch()
            except asyncio.CancelledError:
                raise
            except OidcJwksError:
                self._retry_after = self._now() + self._retry_delay_seconds
                raise
            refreshed_at = self._now()
            by_kid = {key.kid: key for key in keys}
            self._keys = keys
            self._by_kid = by_kid
            self._expires_at = refreshed_at + self._policy.jwks_ttl_seconds
            self._retry_after = 0.0
            self._generation += 1
            return self._keys

    async def get_key(
        self,
        kid: str,
        *,
        refresh_if_missing: bool = True,
    ) -> OidcJwk | None:
        normalized_kid = _visible_text(kid, maximum=_MAX_KID_LENGTH)
        if type(refresh_if_missing) is not bool:
            raise OidcJwksError
        initial_generation = self._generation
        had_snapshot = initial_generation > 0
        await self.get_keys()
        found = self._by_kid.get(normalized_kid)
        if found is not None or not refresh_if_missing:
            return found
        if had_snapshot and self._generation != initial_generation:
            return None
        if self._now() < self._unknown_refresh_after:
            return None
        await self.get_keys(force_refresh=True)
        self._unknown_refresh_after = self._now() + self._retry_delay_seconds
        return self._by_kid.get(normalized_kid)
