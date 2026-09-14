"""Fail-closed OIDC authorization-code callback and token exchange."""

from __future__ import annotations

import asyncio
import hmac
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qsl

from core.identity.oidc_discovery import OidcDiscoveryDocument
from core.identity.oidc_id_token import VerifiedOidcIdToken
from core.identity.oidc_policy import OidcConfiguration
from core.identity.oidc_transaction import (
    OidcAuthorizationTransactionService,
    OidcTransactionProof,
)

_MAX_CALLBACK_QUERY_BYTES = 8_192
_MAX_CALLBACK_FIELDS = 7
_MAX_TOKEN_RESPONSE_FIELDS = 32
_MAX_TOKEN_RESPONSE_FIELD_NAME = 64
_MAX_CODE_LENGTH = 2_048
_MAX_PROVIDER_TOKEN_LENGTH = 16_384
_MAX_ID_TOKEN_LENGTH = 65_536
_MAX_ERROR_VALUE_LENGTH = 2_048
_ALLOWED_CALLBACK_FIELDS = frozenset(
    {
        "code",
        "error",
        "error_description",
        "error_uri",
        "iss",
        "session_state",
        "state",
    }
)
_FORM_METHODS = frozenset({"client_secret_basic", "client_secret_post"})
_HEX_BYTES = frozenset(b"0123456789abcdefABCDEF")
_FIELD_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")


class OidcAuthorizationCodeError(RuntimeError):
    """Content-free boundary for every callback and token-exchange failure."""

    def __init__(self) -> None:
        super().__init__("OIDC authorization code failed.")


class OidcTokenClient(Protocol):
    async def post_form_json(
        self,
        url: str,
        fields: tuple[tuple[str, str], ...],
        *,
        basic_auth: tuple[str, str] | None = None,
    ) -> object: ...


class OidcTokenVerifier(Protocol):
    def matches_configuration(
        self,
        policy: object,
        discovery: OidcDiscoveryDocument,
    ) -> bool: ...

    async def verify(
        self,
        token: str,
        *,
        expected_nonce: str,
        userinfo: object | None = None,
    ) -> VerifiedOidcIdToken: ...


@dataclass(frozen=True, slots=True)
class _CallbackParameters:
    state: str
    code: str | None
    response_issuer: str | None
    provider_error: bool


def _visible_text(
    value: object,
    *,
    maximum: int,
    allow_space: bool,
) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(
            ord(character) < (0x20 if allow_space else 0x21) or ord(character) > 0x7E
            for character in value
        )
    ):
        raise OidcAuthorizationCodeError
    return value


def _validate_percent_encoding(raw_query: bytes) -> None:
    for index, value in enumerate(raw_query):
        if value < 0x21 or value > 0x7E or value == ord("#"):
            raise OidcAuthorizationCodeError
        if value == ord("%") and (
            index + 2 >= len(raw_query)
            or raw_query[index + 1] not in _HEX_BYTES
            or raw_query[index + 2] not in _HEX_BYTES
        ):
            raise OidcAuthorizationCodeError


def _callback_parameters(raw_query: object) -> _CallbackParameters:
    if type(raw_query) is not bytes or not raw_query or len(raw_query) > _MAX_CALLBACK_QUERY_BYTES:
        raise OidcAuthorizationCodeError
    _validate_percent_encoding(raw_query)
    try:
        pairs = parse_qsl(
            raw_query.decode("ascii"),
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=_MAX_CALLBACK_FIELDS,
        )
    except (UnicodeError, ValueError) as exc:
        raise OidcAuthorizationCodeError from exc
    names = [name for name, _value in pairs]
    if (
        not 2 <= len(pairs) <= _MAX_CALLBACK_FIELDS
        or len(names) != len(set(names))
        or not set(names).issubset(_ALLOWED_CALLBACK_FIELDS)
    ):
        raise OidcAuthorizationCodeError
    values = dict(pairs)
    state = _visible_text(values.get("state"), maximum=128, allow_space=False)
    response_issuer = None
    if "iss" in values:
        response_issuer = _visible_text(
            values["iss"],
            maximum=_MAX_ERROR_VALUE_LENGTH,
            allow_space=False,
        )
    if "session_state" in values:
        _visible_text(values["session_state"], maximum=1_024, allow_space=False)

    has_code = "code" in values
    has_error = "error" in values
    if has_code == has_error:
        raise OidcAuthorizationCodeError
    if has_error:
        _visible_text(values["error"], maximum=256, allow_space=False)
        if "error_description" in values:
            _visible_text(
                values["error_description"],
                maximum=_MAX_ERROR_VALUE_LENGTH,
                allow_space=True,
            )
        if "error_uri" in values:
            _visible_text(
                values["error_uri"],
                maximum=_MAX_ERROR_VALUE_LENGTH,
                allow_space=False,
            )
        return _CallbackParameters(
            state=state,
            code=None,
            response_issuer=response_issuer,
            provider_error=True,
        )
    if "error_description" in values or "error_uri" in values:
        raise OidcAuthorizationCodeError
    return _CallbackParameters(
        state=state,
        code=_visible_text(
            values["code"],
            maximum=_MAX_CODE_LENGTH,
            allow_space=False,
        ),
        response_issuer=response_issuer,
        provider_error=False,
    )


def _token_response(payload: object) -> str:
    if type(payload) is not dict or not 3 <= len(payload) <= _MAX_TOKEN_RESPONSE_FIELDS:
        raise OidcAuthorizationCodeError
    if any(
        type(name) is not str
        or not _FIELD_NAME_PATTERN.fullmatch(name)
        or len(name) > _MAX_TOKEN_RESPONSE_FIELD_NAME
        for name in payload
    ):
        raise OidcAuthorizationCodeError
    token_type = _visible_text(payload.get("token_type"), maximum=32, allow_space=False)
    if token_type.casefold() != "bearer":
        raise OidcAuthorizationCodeError
    _visible_text(
        payload.get("access_token"),
        maximum=_MAX_PROVIDER_TOKEN_LENGTH,
        allow_space=False,
    )
    id_token = _visible_text(
        payload.get("id_token"),
        maximum=_MAX_ID_TOKEN_LENGTH,
        allow_space=False,
    )
    if "refresh_token" in payload:
        _visible_text(
            payload["refresh_token"],
            maximum=_MAX_PROVIDER_TOKEN_LENGTH,
            allow_space=False,
        )
    if "expires_in" in payload and (
        type(payload["expires_in"]) is not int or not 1 <= payload["expires_in"] <= 604_800
    ):
        raise OidcAuthorizationCodeError
    if "scope" in payload:
        _visible_text(payload["scope"], maximum=2_048, allow_space=True)
    return id_token


class OidcAuthorizationCodeFlow:
    """Consume one callback, exchange its code once, and return verified identity only."""

    def __init__(
        self,
        configuration: OidcConfiguration,
        discovery: OidcDiscoveryDocument,
        transactions: OidcAuthorizationTransactionService,
        token_client: OidcTokenClient,
        token_verifier: OidcTokenVerifier,
    ) -> None:
        try:
            policy = configuration.policy if type(configuration) is OidcConfiguration else None
            if (
                policy is None
                or not policy.enabled
                or not configuration.secret_configured
                or type(discovery) is not OidcDiscoveryDocument
                or discovery.issuer != policy.issuer
                or len(discovery.token_endpoint_auth_methods) != 1
                or discovery.token_endpoint_auth_methods[0] not in _FORM_METHODS
                or type(transactions) is not OidcAuthorizationTransactionService
                or not transactions.matches_configuration(policy, discovery)
                or not callable(getattr(token_client, "post_form_json", None))
                or not callable(getattr(token_verifier, "matches_configuration", None))
                or not callable(getattr(token_verifier, "verify", None))
                or not token_verifier.matches_configuration(policy, discovery)
            ):
                raise OidcAuthorizationCodeError
        except OidcAuthorizationCodeError:
            raise OidcAuthorizationCodeError from None
        except Exception:
            raise OidcAuthorizationCodeError from None
        self._configuration = configuration
        self._discovery = discovery
        self._transactions = transactions
        self._token_client = token_client
        self._token_verifier = token_verifier

    def __repr__(self) -> str:
        return (
            "OidcAuthorizationCodeFlow("
            f"issuer={self._configuration.policy.issuer!r}, "
            f"policy_revision={self._configuration.policy.revision!r}, "
            f"token_endpoint_auth_method={self._discovery.token_endpoint_auth_methods[0]!r})"
        )

    def matches_configuration(
        self,
        configuration: OidcConfiguration,
        discovery: OidcDiscoveryDocument,
    ) -> bool:
        return (
            self._configuration.policy == configuration.policy
            and self._discovery == discovery
            and self._transactions.matches_configuration(configuration.policy, discovery)
            and self._token_verifier.matches_configuration(configuration.policy, discovery)
        )

    def _proof_matches(self, proof: OidcTransactionProof) -> bool:
        policy = self._configuration.policy
        return (
            proof.issuer == policy.issuer
            and proof.client_id == policy.client_id
            and proof.redirect_uri == policy.redirect_uri
            and proof.authorization_endpoint == self._discovery.authorization_endpoint
            and proof.token_endpoint == self._discovery.token_endpoint
            and proof.token_endpoint_auth_method == self._discovery.token_endpoint_auth_methods[0]
            and proof.policy_revision == policy.revision
        )

    async def complete(
        self,
        raw_query: bytes,
        *,
        browser_token: str,
    ) -> VerifiedOidcIdToken:
        """Complete one raw callback query without retaining any provider credential."""
        try:
            callback = _callback_parameters(raw_query)
            proof = await self._transactions.consume(
                state=callback.state,
                browser_token=browser_token,
                response_issuer=callback.response_issuer,
            )
            if callback.provider_error or callback.code is None or not self._proof_matches(proof):
                raise OidcAuthorizationCodeError
            fields: tuple[tuple[str, str], ...] = (
                ("grant_type", "authorization_code"),
                ("code", callback.code),
                ("redirect_uri", proof.redirect_uri),
                ("code_verifier", proof.code_verifier),
            )
            basic_auth = None
            if proof.token_endpoint_auth_method == "client_secret_basic":
                basic_auth = (
                    proof.client_id,
                    self._configuration.reveal_client_secret(),
                )
            elif proof.token_endpoint_auth_method == "client_secret_post":
                fields += (
                    ("client_id", proof.client_id),
                    ("client_secret", self._configuration.reveal_client_secret()),
                )
            else:  # pragma: no cover - constructor and proof binding guard this
                raise OidcAuthorizationCodeError
            payload = await self._token_client.post_form_json(
                proof.token_endpoint,
                fields,
                basic_auth=basic_auth,
            )
            id_token = _token_response(payload)
            verified = await self._token_verifier.verify(
                id_token,
                expected_nonce=proof.nonce,
            )
            if (
                type(verified) is not VerifiedOidcIdToken
                or verified.issuer != proof.issuer
                or verified.policy_revision != proof.policy_revision
                or not hmac.compare_digest(
                    verified.nonce.encode("utf-8"),
                    proof.nonce.encode("utf-8"),
                )
            ):
                raise OidcAuthorizationCodeError
            return verified
        except asyncio.CancelledError:
            raise
        except OidcAuthorizationCodeError:
            raise OidcAuthorizationCodeError from None
        except Exception:
            raise OidcAuthorizationCodeError from None
