"""Strict OpenID Provider metadata discovery and reduction."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from core.identity.oidc_http import OidcHttpError
from core.identity.oidc_policy import OidcPolicy

_MAX_METADATA_FIELDS = 128
_MAX_METADATA_KEY_LENGTH = 128
_MAX_METADATA_STRING_LENGTH = 2_048
_MAX_METADATA_LIST_ITEMS = 64
_MAX_METADATA_LIST_VALUE_LENGTH = 256
_SUPPORTED_SUBJECT_TYPES = frozenset({"public", "pairwise"})
_SUPPORTED_TOKEN_AUTH_METHODS = ("client_secret_basic", "client_secret_post")


class OidcDiscoveryError(RuntimeError):
    """Content-free boundary for invalid or unsafe provider metadata."""

    def __init__(self) -> None:
        super().__init__("OIDC discovery failed.")


class OidcDiscoveryClient(Protocol):
    async def get_json(self, url: str) -> object: ...

    def validate_endpoint_url(self, url: str) -> None: ...


@dataclass(frozen=True, slots=True)
class OidcDiscoveryDocument:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str | None
    response_types: tuple[str, ...]
    subject_types: tuple[str, ...]
    id_token_signing_algorithms: tuple[str, ...]
    token_endpoint_auth_methods: tuple[str, ...]
    code_challenge_methods: tuple[str, ...]
    scopes_supported: tuple[str, ...]
    claims_supported: tuple[str, ...]


def _metadata_document(payload: object) -> dict[str, object]:
    if type(payload) is not dict or not 1 <= len(payload) <= _MAX_METADATA_FIELDS:
        raise OidcDiscoveryError
    for key in payload:
        if (
            type(key) is not str
            or not key
            or len(key) > _MAX_METADATA_KEY_LENGTH
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in key)
        ):
            raise OidcDiscoveryError
    return payload


def _required_string(
    document: dict[str, object],
    name: str,
    *,
    maximum: int = _MAX_METADATA_STRING_LENGTH,
) -> str:
    value = document.get(name)
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise OidcDiscoveryError
    return value


def _string_list(
    document: dict[str, object],
    name: str,
    *,
    required: bool = True,
    default: tuple[str, ...] = (),
) -> tuple[str, ...]:
    if name not in document and not required:
        return default
    value = document.get(name)
    if type(value) is not list or not value or len(value) > _MAX_METADATA_LIST_ITEMS:
        raise OidcDiscoveryError
    result = tuple(value)
    if len(result) != len(set(result)) or any(
        type(item) is not str
        or not item
        or item != item.strip()
        or len(item) > _MAX_METADATA_LIST_VALUE_LENGTH
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in item)
        for item in result
    ):
        raise OidcDiscoveryError
    return result


def _endpoint(
    document: dict[str, object],
    name: str,
    client: OidcDiscoveryClient,
    *,
    required: bool = True,
) -> str | None:
    if name not in document and not required:
        return None
    value = _required_string(document, name)
    try:
        client.validate_endpoint_url(value)
    except (OidcHttpError, ValueError, TypeError) as exc:
        raise OidcDiscoveryError from exc
    return value


async def discover_oidc(
    policy: OidcPolicy,
    client: OidcDiscoveryClient,
) -> OidcDiscoveryDocument:
    """Fetch and reduce metadata to the exact capabilities Polaris can trust."""
    if type(policy) is not OidcPolicy or not policy.enabled or policy.issuer is None:
        raise OidcDiscoveryError
    discovery_url = policy.issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        payload = await client.get_json(discovery_url)
        document = _metadata_document(payload)
        issuer = _required_string(document, "issuer")
        if issuer != policy.issuer:
            raise OidcDiscoveryError
        authorization_endpoint = _endpoint(document, "authorization_endpoint", client)
        token_endpoint = _endpoint(document, "token_endpoint", client)
        jwks_uri = _endpoint(document, "jwks_uri", client)
        userinfo_endpoint = _endpoint(document, "userinfo_endpoint", client, required=False)
        if authorization_endpoint is None or token_endpoint is None or jwks_uri is None:
            raise OidcDiscoveryError

        response_types = _string_list(document, "response_types_supported")
        if "code" not in response_types:
            raise OidcDiscoveryError
        subject_types = _string_list(document, "subject_types_supported")
        if not _SUPPORTED_SUBJECT_TYPES.intersection(subject_types):
            raise OidcDiscoveryError
        advertised_algorithms = _string_list(
            document,
            "id_token_signing_alg_values_supported",
        )
        algorithms = tuple(
            algorithm
            for algorithm in policy.id_token_signing_algorithms
            if algorithm in advertised_algorithms
        )
        if not algorithms:
            raise OidcDiscoveryError
        advertised_auth_methods = _string_list(
            document,
            "token_endpoint_auth_methods_supported",
            required=False,
            default=("client_secret_basic",),
        )
        auth_methods = tuple(
            method for method in _SUPPORTED_TOKEN_AUTH_METHODS if method in advertised_auth_methods
        )
        if not auth_methods:
            raise OidcDiscoveryError
        code_challenge_methods = _string_list(
            document,
            "code_challenge_methods_supported",
        )
        if "S256" not in code_challenge_methods:
            raise OidcDiscoveryError
        scopes = _string_list(document, "scopes_supported", required=False)
        if scopes and "openid" not in scopes:
            raise OidcDiscoveryError
        claims = _string_list(document, "claims_supported", required=False)
        configured_claims = {
            policy.claims.subject,
            policy.claims.username,
            policy.claims.display_name,
            policy.claims.email,
            policy.claims.groups,
        }
        if claims and not configured_claims.issubset(claims):
            raise OidcDiscoveryError
        return OidcDiscoveryDocument(
            issuer=issuer,
            authorization_endpoint=authorization_endpoint,
            token_endpoint=token_endpoint,
            jwks_uri=jwks_uri,
            userinfo_endpoint=userinfo_endpoint,
            response_types=response_types,
            subject_types=subject_types,
            id_token_signing_algorithms=algorithms,
            token_endpoint_auth_methods=auth_methods,
            code_challenge_methods=("S256",),
            scopes_supported=scopes,
            claims_supported=claims,
        )
    except asyncio.CancelledError:
        raise
    except OidcDiscoveryError:
        raise
    except Exception as exc:
        raise OidcDiscoveryError from exc
