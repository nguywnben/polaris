import asyncio
import dataclasses
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity.oidc_discovery import (  # noqa: E402
    OidcDiscoveryError,
    discover_oidc,
)
from core.identity.oidc_http import OidcHttpClient  # noqa: E402
from core.identity.oidc_policy import load_oidc_configuration  # noqa: E402
from core.identity.repository import OidcPolicyRevisionRecord  # noqa: E402


def _policy(**environment_overrides):
    environment = {
        "OIDC_ENABLED": "true",
        "OIDC_ISSUER": "https://identity.example.com/tenant",
        "OIDC_CLIENT_ID": "polaris",
        "OIDC_CLIENT_SECRET": "enterprise-client-secret",
        "OIDC_REDIRECT_URI": "https://gateway.example.com/api/identity/oidc/callback",
    } | environment_overrides
    revision = OidcPolicyRevisionRecord.initial(
        now=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    )
    return load_oidc_configuration(revision, environ=environment).policy


def _metadata(**overrides):
    return {
        "issuer": "https://identity.example.com/tenant",
        "authorization_endpoint": "https://identity.example.com/authorize",
        "token_endpoint": "https://identity.example.com/token",
        "jwks_uri": "https://identity.example.com/jwks",
        "userinfo_endpoint": "https://identity.example.com/userinfo",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256", "PS256"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["openid", "profile", "email"],
        "claims_supported": ["sub", "preferred_username", "name", "email", "groups"],
    } | overrides


class FakeDiscoveryClient:
    def __init__(self, policy, payload):
        self.payload = payload
        self.requested_urls = []
        self.validator = OidcHttpClient(
            policy,
            resolver=lambda host, port: asyncio.sleep(0, result=("93.184.216.34",)),
        )

    async def get_json(self, url):
        self.requested_urls.append(url)
        return self.payload

    def validate_endpoint_url(self, url):
        self.validator.validate_endpoint_url(url)


class OidcDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_metadata_is_reduced_to_a_typed_bounded_contract(self):
        policy = _policy()
        client = FakeDiscoveryClient(policy, _metadata(extension_field="ignored"))

        document = await discover_oidc(policy, client)

        self.assertEqual(
            client.requested_urls,
            ["https://identity.example.com/tenant/.well-known/openid-configuration"],
        )
        self.assertEqual(document.issuer, policy.issuer)
        self.assertEqual(document.authorization_endpoint, _metadata()["authorization_endpoint"])
        self.assertEqual(document.token_endpoint, _metadata()["token_endpoint"])
        self.assertEqual(document.jwks_uri, _metadata()["jwks_uri"])
        self.assertEqual(document.id_token_signing_algorithms, ("RS256",))
        self.assertEqual(document.token_endpoint_auth_methods, ("client_secret_basic",))
        self.assertEqual(document.code_challenge_methods, ("S256",))
        self.assertNotIn("extension_field", dataclasses.asdict(document))

    async def test_issuer_with_trailing_slash_preserves_exact_identity(self):
        issuer = "https://identity.example.com/tenant/"
        policy = _policy(OIDC_ISSUER=issuer)
        client = FakeDiscoveryClient(policy, _metadata(issuer=issuer))

        document = await discover_oidc(policy, client)

        self.assertEqual(document.issuer, issuer)
        self.assertEqual(
            client.requested_urls,
            ["https://identity.example.com/tenant/.well-known/openid-configuration"],
        )

    async def test_near_match_issuer_values_fail_exact_validation(self):
        for issuer in (
            "https://identity.example.com/tenant/",
            "https://IDENTITY.example.com/tenant",
            "https://identity.example.com/other",
        ):
            with self.subTest(issuer=issuer):
                policy = _policy()
                client = FakeDiscoveryClient(policy, _metadata(issuer=issuer))
                with self.assertRaises(OidcDiscoveryError):
                    await discover_oidc(policy, client)

    async def test_endpoint_origin_poisoning_fails_unless_exact_origin_is_allowlisted(self):
        poisoned = _metadata(jwks_uri="https://keys.example.net/jwks")
        policy = _policy()
        with self.assertRaises(OidcDiscoveryError):
            await discover_oidc(policy, FakeDiscoveryClient(policy, poisoned))

        allowed = _policy(OIDC_ALLOWED_ENDPOINT_ORIGINS="https://keys.example.net")
        document = await discover_oidc(allowed, FakeDiscoveryClient(allowed, poisoned))
        self.assertEqual(document.jwks_uri, "https://keys.example.net/jwks")

    async def test_required_protocol_capabilities_must_intersect_policy(self):
        invalid_documents = (
            _metadata(response_types_supported=["id_token"]),
            _metadata(subject_types_supported=["sectoral"]),
            _metadata(id_token_signing_alg_values_supported=["HS256", "none"]),
            _metadata(token_endpoint_auth_methods_supported=["none"]),
            _metadata(code_challenge_methods_supported=["plain"]),
            _metadata(code_challenge_methods_supported=[]),
            _metadata(code_challenge_methods_supported="S256"),
            _metadata(scopes_supported=["profile", "email"]),
            _metadata(claims_supported=["sub", "email"]),
        )
        for metadata in invalid_documents:
            with self.subTest(metadata=metadata):
                policy = _policy()
                client = FakeDiscoveryClient(policy, metadata)
                with self.assertRaises(OidcDiscoveryError):
                    await discover_oidc(policy, client)

        missing_pkce = _metadata()
        missing_pkce.pop("code_challenge_methods_supported")
        with self.assertRaises(OidcDiscoveryError):
            await discover_oidc(policy, FakeDiscoveryClient(policy, missing_pkce))

    async def test_missing_wrong_type_duplicate_and_oversized_metadata_fail_closed(self):
        invalid_documents = (
            [],
            _metadata(issuer=None),
            _metadata(response_types_supported="code"),
            _metadata(response_types_supported=["code", "code"]),
            _metadata(response_types_supported=["code"] * 65),
            _metadata(**{f"extension_{index}": index for index in range(129)}),
            _metadata(authorization_endpoint="https://identity.example.com/" + "x" * 2049),
        )
        for metadata in invalid_documents:
            with self.subTest(metadata_type=type(metadata).__name__):
                policy = _policy()
                client = FakeDiscoveryClient(policy, metadata)
                with self.assertRaisesRegex(OidcDiscoveryError, "OIDC discovery failed") as caught:
                    await discover_oidc(policy, client)
                self.assertNotIn("identity.example.com", str(caught.exception))

    async def test_disabled_policy_never_fetches_metadata(self):
        revision = OidcPolicyRevisionRecord.initial(
            now=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
        )
        disabled = load_oidc_configuration(revision, environ={}).policy

        class NeverCalled:
            async def get_json(self, url):
                self.fail("Disabled OIDC must not fetch metadata.")

            def validate_endpoint_url(self, url):
                self.fail("Disabled OIDC must not validate endpoints.")

        with self.assertRaises(OidcDiscoveryError):
            await discover_oidc(disabled, NeverCalled())


if __name__ == "__main__":
    unittest.main()
