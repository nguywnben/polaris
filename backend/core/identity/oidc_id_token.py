"""Strict, bounded OpenID Connect ID Token verification."""

from __future__ import annotations

import asyncio
import base64
import hmac
import json
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import jwt
from core.identity.oidc_discovery import OidcDiscoveryDocument
from core.identity.oidc_jwks import OidcJwksCache, OidcJwksError
from core.identity.oidc_policy import OidcPolicy

_MAX_TOKEN_BYTES = 65_536
_MAX_HEADER_BYTES = 4_096
_MAX_PAYLOAD_BYTES = 32_768
_MAX_SIGNATURE_BYTES = 4_096
_MAX_HEADER_FIELDS = 8
_MAX_CLAIMS = 64
_MAX_CLAIM_NAME_LENGTH = 128
_MAX_NONCE_LENGTH = 512
_MAX_AUDIENCES = 16
_MAX_AUDIENCE_LENGTH = 2_048
_MAX_PROFILE_TEXT_LENGTH = 512
_MAX_EMAIL_LENGTH = 320
_MAX_GROUPS = 128
_MAX_GROUP_LENGTH = 256
_MAX_USERINFO_BYTES = 32_768
_MAX_NUMERIC_DATE = 9_007_199_254_740_991
_ALLOWED_HEADER_FIELDS = frozenset({"alg", "kid", "typ"})


class OidcIdTokenError(RuntimeError):
    """Content-free boundary for every ID Token verification failure."""

    def __init__(self) -> None:
        super().__init__("OIDC ID Token failed.")


@dataclass(frozen=True, slots=True)
class VerifiedOidcIdToken:
    """Allowlisted identity data from a fully verified ID Token."""

    issuer: str
    subject: str
    audiences: tuple[str, ...]
    authorized_party: str | None
    expires_at: int
    issued_at: int
    not_before: int | None
    nonce: str
    username: str | None
    display_name: str | None
    email: str | None
    groups: tuple[str, ...]
    userinfo_subject_validated: bool
    policy_revision: int
    jwks_generation: int


def _base64url_segment(value: str, *, minimum: int, maximum: int) -> bytes:
    if (
        type(value) is not str
        or not value
        or "=" in value
        or len(value) > maximum * 2
        or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            for character in value
        )
    ):
        raise OidcIdTokenError
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (TypeError, ValueError) as exc:
        raise OidcIdTokenError from exc
    if (
        not minimum <= len(decoded) <= maximum
        or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value
    ):
        raise OidcIdTokenError
    return decoded


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise OidcIdTokenError
        result[name] = value
    return result


def _json_object(value: bytes, *, maximum_fields: int) -> dict[str, object]:
    try:
        document = json.loads(
            value.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(OidcIdTokenError()),
        )
    except OidcIdTokenError:
        raise
    except (RecursionError, UnicodeError, ValueError, TypeError) as exc:
        raise OidcIdTokenError from exc
    if type(document) is not dict or not 1 <= len(document) <= maximum_fields:
        raise OidcIdTokenError
    if any(
        type(name) is not str
        or not name
        or len(name) > _MAX_CLAIM_NAME_LENGTH
        or any(not 0x21 <= ord(character) <= 0x7E for character in name)
        for name in document
    ):
        raise OidcIdTokenError
    return document


def _compact_token(token: object) -> tuple[dict[str, object], dict[str, object]]:
    if (
        type(token) is not str
        or not token
        or len(token.encode("utf-8")) > _MAX_TOKEN_BYTES
        or token != token.strip()
    ):
        raise OidcIdTokenError
    segments = token.split(".")
    if len(segments) != 3:
        raise OidcIdTokenError
    header_raw = _base64url_segment(segments[0], minimum=2, maximum=_MAX_HEADER_BYTES)
    payload_raw = _base64url_segment(segments[1], minimum=2, maximum=_MAX_PAYLOAD_BYTES)
    _base64url_segment(segments[2], minimum=1, maximum=_MAX_SIGNATURE_BYTES)
    header = _json_object(header_raw, maximum_fields=_MAX_HEADER_FIELDS)
    claims = _json_object(payload_raw, maximum_fields=_MAX_CLAIMS)
    if not set(header).issubset(_ALLOWED_HEADER_FIELDS):
        raise OidcIdTokenError
    if "typ" in header and header["typ"] != "JWT":
        raise OidcIdTokenError
    return header, claims


def _visible_text(value: object, *, maximum: int, ascii_only: bool = False) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(
            ord(character) < 0x20 or ord(character) == 0x7F or ascii_only and ord(character) > 0x7F
            for character in value
        )
    ):
        raise OidcIdTokenError
    return value


def _numeric_date(claims: Mapping[str, object], name: str, *, required: bool) -> int | None:
    if name not in claims and not required:
        return None
    value = claims.get(name)
    if type(value) is not int or not 0 <= value <= _MAX_NUMERIC_DATE:
        raise OidcIdTokenError
    return value


def _audiences(value: object) -> tuple[str, ...]:
    if type(value) is str:
        result = (_visible_text(value, maximum=_MAX_AUDIENCE_LENGTH),)
    elif type(value) is list and 1 <= len(value) <= _MAX_AUDIENCES:
        result = tuple(_visible_text(item, maximum=_MAX_AUDIENCE_LENGTH) for item in value)
    else:
        raise OidcIdTokenError
    if len(result) != len(set(result)):
        raise OidcIdTokenError
    return result


def _optional_profile_text(
    claims: Mapping[str, object],
    name: str,
    *,
    maximum: int = _MAX_PROFILE_TEXT_LENGTH,
) -> str | None:
    if name not in claims:
        return None
    return _visible_text(claims[name], maximum=maximum)


def _groups(claims: Mapping[str, object], name: str) -> tuple[str, ...]:
    if name not in claims:
        return ()
    value = claims[name]
    if type(value) is not list or len(value) > _MAX_GROUPS:
        raise OidcIdTokenError
    result = tuple(_visible_text(item, maximum=_MAX_GROUP_LENGTH) for item in value)
    if len(result) != len(set(result)):
        raise OidcIdTokenError
    return result


def _userinfo_matches(userinfo: object, subject: str) -> bool:
    if type(userinfo) is not dict or not 1 <= len(userinfo) <= _MAX_CLAIMS:
        raise OidcIdTokenError
    if any(
        type(name) is not str
        or not name
        or len(name) > _MAX_CLAIM_NAME_LENGTH
        or any(not 0x21 <= ord(character) <= 0x7E for character in name)
        for name in userinfo
    ):
        raise OidcIdTokenError
    try:
        encoded = json.dumps(
            userinfo,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError, UnicodeError) as exc:
        raise OidcIdTokenError from exc
    if len(encoded) > _MAX_USERINFO_BYTES:
        raise OidcIdTokenError
    userinfo_subject = _visible_text(userinfo.get("sub"), maximum=255, ascii_only=True)
    return hmac.compare_digest(userinfo_subject, subject)


class OidcIdTokenVerifier:
    """Verify one transaction-bound ID Token against one immutable OIDC policy."""

    def __init__(
        self,
        policy: OidcPolicy,
        discovery: OidcDiscoveryDocument,
        jwks_cache: OidcJwksCache,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if (
            type(policy) is not OidcPolicy
            or not policy.enabled
            or policy.issuer is None
            or policy.client_id is None
            or type(discovery) is not OidcDiscoveryDocument
            or discovery.issuer != policy.issuer
            or not discovery.id_token_signing_algorithms
            or any(
                algorithm not in policy.id_token_signing_algorithms
                for algorithm in discovery.id_token_signing_algorithms
            )
            or type(jwks_cache) is not OidcJwksCache
            or not jwks_cache.matches_configuration(policy, discovery)
            or not callable(clock)
        ):
            raise OidcIdTokenError
        self._policy = policy
        self._discovery = discovery
        self._jwks_cache = jwks_cache
        self._clock = clock

    def _now(self) -> float:
        try:
            value = float(self._clock())
        except (TypeError, ValueError) as exc:
            raise OidcIdTokenError from exc
        if not math.isfinite(value) or value < 0:
            raise OidcIdTokenError
        return value

    def matches_configuration(
        self,
        policy: OidcPolicy,
        discovery: OidcDiscoveryDocument,
    ) -> bool:
        """Return whether this verifier is bound to the exact current trust snapshot."""
        return self._policy == policy and self._discovery == discovery

    def _validate_claims(
        self,
        claims: dict[str, object],
        *,
        expected_nonce: str,
        userinfo: object | None,
    ) -> VerifiedOidcIdToken:
        issuer = _visible_text(claims.get("iss"), maximum=2_048)
        subject = _visible_text(claims.get("sub"), maximum=255, ascii_only=True)
        audiences = _audiences(claims.get("aud"))
        nonce = _visible_text(claims.get("nonce"), maximum=_MAX_NONCE_LENGTH)
        if issuer != self._policy.issuer or self._policy.client_id not in audiences:
            raise OidcIdTokenError
        if not hmac.compare_digest(nonce, expected_nonce):
            raise OidcIdTokenError

        authorized_party = None
        if "azp" in claims:
            authorized_party = _visible_text(claims["azp"], maximum=256)
            if not hmac.compare_digest(authorized_party, self._policy.client_id):
                raise OidcIdTokenError
        if len(audiences) > 1 and authorized_party is None:
            raise OidcIdTokenError

        expires_at = _numeric_date(claims, "exp", required=True)
        issued_at = _numeric_date(claims, "iat", required=True)
        not_before = _numeric_date(claims, "nbf", required=False)
        if expires_at is None or issued_at is None:  # pragma: no cover - required above
            raise OidcIdTokenError
        now = self._now()
        skew = self._policy.clock_skew_seconds
        if (
            now > expires_at + skew
            or issued_at > now + skew
            or now - issued_at > self._policy.max_id_token_age_seconds + skew
            or expires_at < issued_at
            or not_before is not None
            and (not_before > now + skew or not_before > expires_at)
        ):
            raise OidcIdTokenError

        userinfo_validated = False
        if userinfo is not None:
            if not _userinfo_matches(userinfo, subject):
                raise OidcIdTokenError
            userinfo_validated = True
        claim_policy = self._policy.claims
        return VerifiedOidcIdToken(
            issuer=issuer,
            subject=subject,
            audiences=audiences,
            authorized_party=authorized_party,
            expires_at=expires_at,
            issued_at=issued_at,
            not_before=not_before,
            nonce=nonce,
            username=_optional_profile_text(claims, claim_policy.username),
            display_name=_optional_profile_text(claims, claim_policy.display_name),
            email=_optional_profile_text(
                claims,
                claim_policy.email,
                maximum=_MAX_EMAIL_LENGTH,
            ),
            groups=_groups(claims, claim_policy.groups),
            userinfo_subject_validated=userinfo_validated,
            policy_revision=self._policy.revision,
            jwks_generation=self._jwks_cache.generation,
        )

    async def verify(
        self,
        token: str,
        *,
        expected_nonce: str,
        userinfo: object | None = None,
    ) -> VerifiedOidcIdToken:
        """Verify signature and exact transaction claims, returning only allowlisted data."""
        try:
            expected_nonce = _visible_text(expected_nonce, maximum=_MAX_NONCE_LENGTH)
            header, claims = _compact_token(token)
            algorithm = _visible_text(header.get("alg"), maximum=16, ascii_only=True)
            kid = _visible_text(header.get("kid"), maximum=128, ascii_only=True)
            if (
                algorithm not in self._policy.id_token_signing_algorithms
                or algorithm not in self._discovery.id_token_signing_algorithms
            ):
                raise OidcIdTokenError
            key = await self._jwks_cache.get_key(kid)
            if key is None or algorithm not in key.supported_algorithms:
                raise OidcIdTokenError
            public_key = jwt.PyJWK.from_dict(
                key.to_public_jwk(),
                algorithm=algorithm,
            ).key
            decoded = jwt.decode_complete(
                token,
                key=public_key,
                algorithms=[algorithm],
                options={
                    "verify_signature": True,
                    "verify_aud": False,
                    "verify_iss": False,
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                    "verify_sub": False,
                },
            )
            if decoded.get("payload") != claims:
                raise OidcIdTokenError
            return self._validate_claims(
                claims,
                expected_nonce=expected_nonce,
                userinfo=userinfo,
            )
        except asyncio.CancelledError:
            raise
        except OidcIdTokenError:
            raise OidcIdTokenError from None
        except (OidcJwksError, jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise OidcIdTokenError from None
        except Exception:
            raise OidcIdTokenError from None
