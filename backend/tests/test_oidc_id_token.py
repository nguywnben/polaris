import asyncio
import base64
import json
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity.oidc_discovery import OidcDiscoveryDocument  # noqa: E402
from core.identity.oidc_id_token import (  # noqa: E402
    OidcIdTokenError,
    OidcIdTokenVerifier,
)
from core.identity.oidc_jwks import OidcJwksCache  # noqa: E402
from core.identity.oidc_policy import load_oidc_configuration  # noqa: E402
from core.identity.repository import OidcPolicyRevisionRecord  # noqa: E402

_MISSING = object()
_NOW = 2_000_000_000
_ISSUER = "https://identity.example.com/tenant"
_CLIENT_ID = "polaris"
_NONCE = "transaction-bound-nonce"
_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_RSA_PSS_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_EC_KEY = ec.generate_private_key(ec.SECP256R1())


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _integer_bytes(value: int, *, length: int | None = None) -> bytes:
    return value.to_bytes(length or max(1, (value.bit_length() + 7) // 8), "big")


def _public_jwk(private_key, *, kid: str, algorithm: str) -> dict[str, object]:
    public_key = private_key.public_key()
    if isinstance(public_key, rsa.RSAPublicKey):
        numbers = public_key.public_numbers()
        return {
            "kty": "RSA",
            "kid": kid,
            "use": "sig",
            "key_ops": ["verify"],
            "alg": algorithm,
            "n": _base64url(_integer_bytes(numbers.n)),
            "e": _base64url(_integer_bytes(numbers.e)),
        }
    numbers = public_key.public_numbers()
    return {
        "kty": "EC",
        "kid": kid,
        "use": "sig",
        "key_ops": ["verify"],
        "alg": algorithm,
        "crv": "P-256",
        "x": _base64url(_integer_bytes(numbers.x, length=32)),
        "y": _base64url(_integer_bytes(numbers.y, length=32)),
    }


def _policy(**environment_overrides):
    environment = {
        "OIDC_ENABLED": "true",
        "OIDC_ISSUER": _ISSUER,
        "OIDC_CLIENT_ID": _CLIENT_ID,
        "OIDC_CLIENT_SECRET": "enterprise-client-secret",
        "OIDC_REDIRECT_URI": "https://gateway.example.com/api/identity/oidc/callback",
        "OIDC_ID_TOKEN_SIGNING_ALGORITHMS": "RS256,PS256,ES256",
        "OIDC_CLOCK_SKEW_SECONDS": "60",
        "OIDC_MAX_ID_TOKEN_AGE_SECONDS": "300",
    } | environment_overrides
    revision = OidcPolicyRevisionRecord.initial(
        now=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    )
    return load_oidc_configuration(revision, environ=environment).policy


def _discovery():
    return OidcDiscoveryDocument(
        issuer=_ISSUER,
        authorization_endpoint="https://identity.example.com/authorize",
        token_endpoint="https://identity.example.com/token",
        jwks_uri="https://identity.example.com/jwks",
        userinfo_endpoint="https://identity.example.com/userinfo",
        response_types=("code",),
        subject_types=("public",),
        id_token_signing_algorithms=("RS256", "PS256", "ES256"),
        token_endpoint_auth_methods=("client_secret_basic",),
        code_challenge_methods=("S256",),
        scopes_supported=("openid",),
        claims_supported=(),
    )


class QueueClient:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls: list[str] = []

    async def get_json(self, url: str):
        self.calls.append(url)
        if not self.payloads:
            raise AssertionError("Unexpected JWKS fetch")
        return self.payloads.pop(0)


def _claims(**overrides) -> dict[str, object]:
    claims: dict[str, object] = {
        "iss": _ISSUER,
        "sub": "user-123",
        "aud": _CLIENT_ID,
        "exp": _NOW + 120,
        "iat": _NOW - 10,
        "nbf": _NOW - 10,
        "nonce": _NONCE,
        "preferred_username": "operator",
        "name": "Enterprise Operator",
        "email": "operator@example.com",
        "groups": ["gateway-operators", "security-reviewers"],
        "ignored_provider_claim": "must-not-cross-the-boundary",
    }
    for name, value in overrides.items():
        if value is _MISSING:
            claims.pop(name, None)
        else:
            claims[name] = value
    return claims


def _token(
    private_key=_RSA_KEY,
    *,
    algorithm: str = "RS256",
    kid: str = "rsa-1",
    claims: dict[str, object] | None = None,
    headers: dict[str, object] | None = None,
) -> str:
    payload = json.dumps(
        claims or _claims(),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return jwt.api_jws.PyJWS().encode(
        payload,
        private_key,
        algorithm=algorithm,
        headers={"kid": kid} | (headers or {}),
    )


def _jwks(*keys: dict[str, object]) -> dict[str, object]:
    return {"keys": list(keys)}


def _manual_token(header: str, payload: str, signature: bytes = b"invalid") -> str:
    return ".".join(
        (
            _base64url(header.encode("utf-8")),
            _base64url(payload.encode("utf-8")),
            _base64url(signature),
        )
    )


class OidcIdTokenVerifierTests(unittest.IsolatedAsyncioTestCase):
    def _verifier(self, *payloads):
        policy = _policy()
        client = QueueClient(*payloads)
        cache = OidcJwksCache(policy, _discovery(), client)
        return OidcIdTokenVerifier(policy, _discovery(), cache, clock=lambda: _NOW), client

    def test_verifier_exposes_exact_trust_snapshot_matching(self):
        verifier, _client = self._verifier()
        policy = _policy()
        discovery = _discovery()

        self.assertTrue(verifier.matches_configuration(policy, discovery))
        self.assertFalse(
            verifier.matches_configuration(
                replace(policy, revision=policy.revision + 1),
                discovery,
            )
        )

    async def _assert_rejected(self, verifier, token, **kwargs):
        with self.assertRaises(OidcIdTokenError) as caught:
            await verifier.verify(token, expected_nonce=_NONCE, **kwargs)
        self.assertEqual(str(caught.exception), "OIDC ID Token failed.")
        self.assertNotIn("provider", repr(caught.exception).lower())
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

    async def test_verifier_rejects_a_cache_bound_to_another_trust_configuration(self):
        policy = _policy()
        discovery = _discovery()
        other_discovery = replace(
            discovery,
            jwks_uri="https://identity.example.com/other-jwks",
        )
        other_cache = OidcJwksCache(policy, other_discovery, QueueClient())

        with self.assertRaises(OidcIdTokenError):
            OidcIdTokenVerifier(policy, discovery, other_cache, clock=lambda: _NOW)

    async def test_supported_asymmetric_algorithms_return_only_bounded_identity_claims(self):
        cases = (
            ("RS256", "rsa-1", _RSA_KEY),
            ("PS256", "pss-1", _RSA_PSS_KEY),
            ("ES256", "ec-1", _EC_KEY),
        )
        keys = tuple(
            _public_jwk(private_key, kid=kid, algorithm=algorithm)
            for algorithm, kid, private_key in cases
        )

        for algorithm, kid, private_key in cases:
            with self.subTest(algorithm=algorithm):
                verifier, _ = self._verifier(_jwks(*keys))
                verified = await verifier.verify(
                    _token(private_key, algorithm=algorithm, kid=kid),
                    expected_nonce=_NONCE,
                )

                self.assertEqual(verified.issuer, _ISSUER)
                self.assertEqual(verified.subject, "user-123")
                self.assertEqual(verified.audiences, (_CLIENT_ID,))
                self.assertIsNone(verified.authorized_party)
                self.assertEqual(verified.nonce, _NONCE)
                self.assertEqual(verified.username, "operator")
                self.assertEqual(verified.display_name, "Enterprise Operator")
                self.assertEqual(verified.email, "operator@example.com")
                self.assertEqual(
                    verified.groups,
                    ("gateway-operators", "security-reviewers"),
                )
                self.assertFalse(verified.userinfo_subject_validated)
                self.assertEqual(verified.policy_revision, 1)
                self.assertEqual(verified.jwks_generation, 1)
                self.assertNotIn("ignored_provider_claim", repr(verified))

    async def test_issuer_audience_authorized_party_subject_and_nonce_are_exact(self):
        key = _public_jwk(_RSA_KEY, kid="rsa-1", algorithm="RS256")
        invalid_claims = (
            _claims(iss="https://identity.example.com/other"),
            _claims(aud="other-client"),
            _claims(aud=[_CLIENT_ID, "other-client"], azp=_MISSING),
            _claims(aud=[_CLIENT_ID, "other-client"], azp="other-client"),
            _claims(azp="other-client"),
            _claims(sub="x" * 256),
            _claims(sub="user\n123"),
            _claims(nonce="other-transaction"),
            _claims(iss=True),
            _claims(aud=[_CLIENT_ID, _CLIENT_ID]),
            _claims(exp=_MISSING),
            _claims(iat=_MISSING),
            _claims(nonce=_MISSING),
        )

        for claims in invalid_claims:
            with self.subTest(claims=claims):
                verifier, _ = self._verifier(_jwks(key))
                await self._assert_rejected(verifier, _token(claims=claims))

        verifier, _ = self._verifier(_jwks(key))
        verified = await verifier.verify(
            _token(claims=_claims(aud=[_CLIENT_ID, "trusted-resource"], azp=_CLIENT_ID)),
            expected_nonce=_NONCE,
        )
        self.assertEqual(verified.audiences, (_CLIENT_ID, "trusted-resource"))
        self.assertEqual(verified.authorized_party, _CLIENT_ID)

    async def test_expiry_not_before_and_issue_time_use_bounded_clock_skew(self):
        key = _public_jwk(_RSA_KEY, kid="rsa-1", algorithm="RS256")
        invalid_claims = (
            _claims(exp=_NOW - 61),
            _claims(nbf=_NOW + 61),
            _claims(iat=_NOW + 61),
            _claims(iat=_NOW - 361),
            _claims(exp=True),
            _claims(iat=1.5),
            _claims(nbf="later"),
            _claims(exp=_NOW + 10, iat=_NOW + 20),
        )
        for claims in invalid_claims:
            with self.subTest(claims=claims):
                verifier, _ = self._verifier(_jwks(key))
                await self._assert_rejected(verifier, _token(claims=claims))

        verifier, _ = self._verifier(_jwks(key))
        verified = await verifier.verify(
            _token(claims=_claims(exp=_NOW - 60, nbf=_NOW - 360, iat=_NOW - 360)),
            expected_nonce=_NONCE,
        )
        self.assertEqual(verified.expires_at, _NOW - 60)

    async def test_header_rejects_symmetric_none_embedded_remote_and_critical_keys(self):
        key = _public_jwk(_RSA_KEY, kid="rsa-1", algorithm="RS256")
        invalid_tokens = (
            jwt.encode(
                _claims(),
                "symmetric-secret-at-least-32-bytes",
                algorithm="HS256",
                headers={"kid": "rsa-1"},
            ),
            jwt.encode(_claims(), key="", algorithm="none", headers={"kid": "rsa-1"}),
            _token(headers={"jku": "https://attacker.example/jwks"}),
            _token(headers={"jwk": key}),
            _token(headers={"x5u": "https://attacker.example/cert"}),
            _token(headers={"x5c": ["provider-certificate"]}),
            _token(headers={"crit": ["provider-extension"], "provider-extension": True}),
            _token(headers={"zip": "DEF"}),
            _token(headers={"kid": "x" * 129}),
        )
        for token in invalid_tokens:
            with self.subTest(header=token.split(".", 1)[0]):
                verifier, client = self._verifier(_jwks(key))
                await self._assert_rejected(verifier, token)
                self.assertEqual(client.calls, [])

    async def test_unknown_key_id_refreshes_once_and_invalid_signature_does_not_refresh(self):
        old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        verifier, client = self._verifier(
            _jwks(_public_jwk(old_key, kid="old", algorithm="RS256")),
            _jwks(_public_jwk(new_key, kid="new", algorithm="RS256")),
        )

        verified = await verifier.verify(
            _token(new_key, kid="new"),
            expected_nonce=_NONCE,
        )
        self.assertEqual(verified.jwks_generation, 2)
        self.assertEqual(len(client.calls), 2)

        verifier, client = self._verifier(_jwks(_public_jwk(old_key, kid="old", algorithm="RS256")))
        await self._assert_rejected(verifier, _token(new_key, kid="old"))
        self.assertEqual(len(client.calls), 1)

    async def test_userinfo_subject_must_match_before_it_is_marked_validated(self):
        key = _public_jwk(_RSA_KEY, kid="rsa-1", algorithm="RS256")
        verifier, _ = self._verifier(_jwks(key))
        verified = await verifier.verify(
            _token(),
            expected_nonce=_NONCE,
            userinfo={"sub": "user-123", "name": "Provider profile"},
        )
        self.assertTrue(verified.userinfo_subject_validated)

        for userinfo in (
            {"sub": "other-user"},
            {"sub": True},
            {"name": "missing subject"},
            {"sub": "user-123", **{f"claim_{index}": index for index in range(64)}},
            "provider text",
        ):
            with self.subTest(userinfo_type=type(userinfo).__name__):
                verifier, _ = self._verifier(_jwks(key))
                await self._assert_rejected(verifier, _token(), userinfo=userinfo)

    async def test_malformed_duplicate_and_oversized_tokens_fail_at_the_content_free_boundary(self):
        key = _public_jwk(_RSA_KEY, kid="rsa-1", algorithm="RS256")
        malformed = (
            "",
            "not-a-token",
            "a.b.c.d",
            "x" * 65_537,
            _manual_token('{"alg":"RS256","alg":"ES256","kid":"rsa-1"}', "{}"),
            _manual_token(
                '{"alg":"RS256","kid":"rsa-1"}',
                '{"iss":"%s","iss":"provider-text"}' % _ISSUER,
            ),
            _manual_token('{"alg":"RS256","kid":"rsa-1"}', "{not-json}"),
            _manual_token('{"alg":"RS256","kid":"rsa-1"}', "{}", b"x" * 4_097),
        )
        for token in malformed:
            with self.subTest(size=len(token)):
                verifier, client = self._verifier(_jwks(key))
                await self._assert_rejected(verifier, token)
                self.assertEqual(client.calls, [])

    async def test_profile_claims_are_type_bounded_and_deduplicated(self):
        key = _public_jwk(_RSA_KEY, kid="rsa-1", algorithm="RS256")
        invalid_claims = (
            _claims(preferred_username=True),
            _claims(name="x" * 513),
            _claims(email="x" * 321),
            _claims(groups="administrators"),
            _claims(groups=["same", "same"]),
            _claims(groups=[f"group-{index}" for index in range(129)]),
            _claims(groups=["unsafe\ngroup"]),
        )
        for claims in invalid_claims:
            with self.subTest(claims=claims):
                verifier, _ = self._verifier(_jwks(key))
                await self._assert_rejected(verifier, _token(claims=claims))

    async def test_provider_failure_is_content_free_and_cancellation_propagates(self):
        class FailingClient:
            async def get_json(self, url: str):
                raise RuntimeError("provider token and endpoint detail must not escape")

        class CancelledClient:
            async def get_json(self, url: str):
                raise asyncio.CancelledError

        policy = _policy()
        failing_cache = OidcJwksCache(policy, _discovery(), FailingClient())
        failing_verifier = OidcIdTokenVerifier(
            policy,
            _discovery(),
            failing_cache,
            clock=lambda: _NOW,
        )
        with self.assertRaises(OidcIdTokenError) as caught:
            await failing_verifier.verify(_token(), expected_nonce=_NONCE)
        self.assertEqual(str(caught.exception), "OIDC ID Token failed.")
        self.assertIsNone(caught.exception.__cause__)

        cancelled_cache = OidcJwksCache(policy, _discovery(), CancelledClient())
        cancelled_verifier = OidcIdTokenVerifier(
            policy,
            _discovery(),
            cancelled_cache,
            clock=lambda: _NOW,
        )
        with self.assertRaises(asyncio.CancelledError):
            await cancelled_verifier.verify(_token(), expected_nonce=_NONCE)


if __name__ == "__main__":
    unittest.main()
