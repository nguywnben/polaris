import asyncio
import base64
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity.oidc_discovery import OidcDiscoveryDocument  # noqa: E402
from core.identity.oidc_jwks import OidcJwksCache, OidcJwksError  # noqa: E402
from core.identity.oidc_policy import load_oidc_configuration  # noqa: E402
from core.identity.repository import OidcPolicyRevisionRecord  # noqa: E402


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _rsa_key(kid="rsa-1", **overrides):
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "key_ops": ["verify"],
        "alg": "RS256",
        "n": _base64url(b"\x80" + b"\x01" * 255),
        "e": "AQAB",
        "x5c": ["ignored-certificate-extension"],
    } | overrides


def _ec_key(kid="ec-1", **overrides):
    return {
        "kty": "EC",
        "kid": kid,
        "use": "sig",
        "key_ops": ["verify"],
        "alg": "ES256",
        "crv": "P-256",
        "x": _base64url(
            bytes.fromhex("6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296")
        ),
        "y": _base64url(
            bytes.fromhex("4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5")
        ),
    } | overrides


def _policy(**environment_overrides):
    environment = {
        "OIDC_ENABLED": "true",
        "OIDC_ISSUER": "https://identity.example.com/tenant",
        "OIDC_CLIENT_ID": "polaris",
        "OIDC_CLIENT_SECRET": "enterprise-client-secret",
        "OIDC_REDIRECT_URI": "https://gateway.example.com/api/identity/oidc/callback",
        "OIDC_ID_TOKEN_SIGNING_ALGORITHMS": "RS256,ES256",
        "OIDC_JWKS_TTL_SECONDS": "30",
    } | environment_overrides
    revision = OidcPolicyRevisionRecord.initial(
        now=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    )
    return load_oidc_configuration(revision, environ=environment).policy


def _discovery():
    return OidcDiscoveryDocument(
        issuer="https://identity.example.com/tenant",
        authorization_endpoint="https://identity.example.com/authorize",
        token_endpoint="https://identity.example.com/token",
        jwks_uri="https://identity.example.com/jwks",
        userinfo_endpoint="https://identity.example.com/userinfo",
        response_types=("code",),
        subject_types=("public",),
        id_token_signing_algorithms=("RS256", "ES256"),
        token_endpoint_auth_methods=("client_secret_basic",),
        code_challenge_methods=("S256",),
        scopes_supported=("openid",),
        claims_supported=(),
    )


class QueueClient:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    async def get_json(self, url):
        self.calls.append(url)
        if not self.payloads:
            raise AssertionError("Unexpected JWKS fetch")
        return self.payloads.pop(0)


class OidcJwksCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_keys_are_reduced_and_indexed_without_extensions(self):
        client = QueueClient({"keys": [_rsa_key(), _ec_key()]})
        cache = OidcJwksCache(_policy(), _discovery(), client)

        keys = await cache.get_keys()

        self.assertEqual(tuple(key.kid for key in keys), ("rsa-1", "ec-1"))
        self.assertEqual(keys[0].supported_algorithms, ("RS256",))
        self.assertEqual(keys[1].supported_algorithms, ("ES256",))
        self.assertNotIn("x5c", keys[0].to_public_jwk())
        self.assertNotIn("d", keys[0].to_public_jwk())
        self.assertEqual((await cache.get_key("rsa-1")).kid, "rsa-1")
        self.assertEqual(client.calls, ["https://identity.example.com/jwks"])
        self.assertEqual(cache.policy_revision, 1)

    async def test_fresh_cache_does_not_refetch_and_expired_cache_rotates_atomically(self):
        now = [100.0]
        client = QueueClient(
            {"keys": [_rsa_key("old")]},
            {"keys": [_rsa_key("new")]},
        )
        cache = OidcJwksCache(_policy(), _discovery(), client, clock=lambda: now[0])

        self.assertEqual((await cache.get_keys())[0].kid, "old")
        now[0] = 129.999
        self.assertEqual((await cache.get_keys())[0].kid, "old")
        self.assertEqual(len(client.calls), 1)

        now[0] = 130.0
        self.assertEqual((await cache.get_keys())[0].kid, "new")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(cache.generation, 2)

    async def test_concurrent_cold_cache_fetch_is_single_flight(self):
        started = asyncio.Event()
        release = asyncio.Event()

        class SlowClient:
            def __init__(self):
                self.calls = 0

            async def get_json(self, url):
                self.calls += 1
                started.set()
                await release.wait()
                return {"keys": [_rsa_key()]}

        client = SlowClient()
        cache = OidcJwksCache(_policy(), _discovery(), client)
        tasks = [asyncio.create_task(cache.get_keys()) for _ in range(20)]
        await started.wait()
        release.set()
        results = await asyncio.gather(*tasks)

        self.assertTrue(all(result[0].kid == "rsa-1" for result in results))
        self.assertEqual(client.calls, 1)

    async def test_concurrent_unknown_kid_causes_only_one_forced_rotation(self):
        client = QueueClient(
            {"keys": [_rsa_key("old")]},
            {"keys": [_rsa_key("new")]},
        )
        cache = OidcJwksCache(_policy(), _discovery(), client)
        await cache.get_keys()

        results = await asyncio.gather(*(cache.get_key("new") for _ in range(20)))

        self.assertTrue(all(result is not None and result.kid == "new" for result in results))
        self.assertEqual(len(client.calls), 2)

    async def test_concurrent_failed_refresh_is_coalesced_without_retry_storm(self):
        started = asyncio.Event()
        release = asyncio.Event()
        now = [100.0]

        class FailingClient:
            def __init__(self):
                self.calls = 0

            async def get_json(self, url):
                self.calls += 1
                started.set()
                await release.wait()
                raise RuntimeError("provider detail must not escape")

        client = FailingClient()
        cache = OidcJwksCache(_policy(), _discovery(), client, clock=lambda: now[0])
        tasks = [asyncio.create_task(cache.get_keys()) for _ in range(20)]
        await started.wait()
        release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)

        self.assertTrue(all(type(result) is OidcJwksError for result in results))
        self.assertEqual(client.calls, 1)

        now[0] = 105.0
        with self.assertRaises(OidcJwksError):
            await cache.get_keys()
        self.assertEqual(client.calls, 2)

    async def test_unknown_kid_refreshes_once_then_returns_none(self):
        client = QueueClient(
            {"keys": [_rsa_key("old")]},
            {"keys": [_rsa_key("still-old")]},
        )
        cache = OidcJwksCache(_policy(), _discovery(), client)
        await cache.get_keys()

        self.assertIsNone(await cache.get_key("missing"))
        self.assertEqual(len(client.calls), 2)
        with self.assertRaises(OidcJwksError):
            await cache.get_key("x" * 129)

    async def test_sequential_unknown_kids_share_a_bounded_refresh_cooldown(self):
        now = [100.0]
        client = QueueClient(
            {"keys": [_rsa_key("old")]},
            {"keys": [_rsa_key("still-old")]},
            {"keys": [_rsa_key("latest-old")]},
        )
        cache = OidcJwksCache(_policy(), _discovery(), client, clock=lambda: now[0])
        await cache.get_keys()

        self.assertIsNone(await cache.get_key("attacker-kid-1"))
        self.assertIsNone(await cache.get_key("attacker-kid-2"))
        self.assertEqual(len(client.calls), 2)

        now[0] = 105.0
        self.assertIsNone(await cache.get_key("attacker-kid-3"))
        self.assertEqual(len(client.calls), 3)

    async def test_failed_unknown_kid_refresh_does_not_poison_fresh_known_keys(self):
        client = QueueClient(
            {"keys": [_rsa_key("known")]},
            RuntimeError("provider detail must not escape"),
        )
        cache = OidcJwksCache(_policy(), _discovery(), client, clock=lambda: 100.0)
        await cache.get_keys()

        with self.assertRaisesRegex(OidcJwksError, "OIDC JWKS failed"):
            await cache.get_key("unknown")

        self.assertEqual((await cache.get_key("known")).kid, "known")
        self.assertEqual(len(client.calls), 2)

    async def test_poisoned_rotation_never_replaces_last_valid_snapshot(self):
        now = [100.0]
        client = QueueClient(
            {"keys": [_rsa_key("valid")]},
            {"keys": [_rsa_key("poisoned", d="private-material")]},
            {"keys": [_rsa_key("recovered")]},
        )
        cache = OidcJwksCache(_policy(), _discovery(), client, clock=lambda: now[0])
        self.assertEqual((await cache.get_keys())[0].kid, "valid")

        now[0] = 130.0
        with self.assertRaises(OidcJwksError):
            await cache.get_keys()
        self.assertEqual(cache.generation, 1)

        now[0] = 135.0
        self.assertEqual((await cache.get_keys())[0].kid, "recovered")
        self.assertEqual(cache.generation, 2)

    async def test_malformed_private_symmetric_duplicate_and_oversized_sets_fail_closed(self):
        invalid_sets = (
            [],
            {"keys": "not-a-list"},
            {"keys": []},
            {"keys": [_rsa_key("same"), _rsa_key("same")]},
            {"keys": [_rsa_key(str(index)) for index in range(65)]},
            {"keys": [_rsa_key(d="private-material")]},
            {"keys": [{"kty": "oct", "kid": "symmetric", "k": "secret"}]},
            {"keys": [_rsa_key(alg="HS256")]},
            {"keys": [_rsa_key(use="enc")]},
            {"keys": [_rsa_key(key_ops=["sign"])]},
            {"keys": [_rsa_key(n="not+base64")]},
            {"keys": [_rsa_key(n=_base64url(b"small"))]},
            {"keys": [_rsa_key(e="Ag")]},
            {"keys": [_ec_key(crv="P-384")]},
            {"keys": [_ec_key(x=_base64url(b"short"))]},
            {
                "keys": [
                    _ec_key(
                        x=_base64url(b"\x00" * 32),
                        y=_base64url(b"\x00" * 32),
                    )
                ]
            },
            {"keys": [_rsa_key(kid="x" * 129)]},
        )
        for payload in invalid_sets:
            with self.subTest(payload_type=type(payload).__name__):
                cache = OidcJwksCache(_policy(), _discovery(), QueueClient(payload))
                with self.assertRaisesRegex(OidcJwksError, "OIDC JWKS failed"):
                    await cache.get_keys()

    async def test_policy_and_discovery_must_match_before_any_fetch(self):
        client = QueueClient({"keys": [_rsa_key()]})
        mismatch = dataclasses_replace(_discovery(), issuer="https://identity.example.com/other")
        with self.assertRaises(OidcJwksError):
            OidcJwksCache(_policy(), mismatch, client)
        poisoned_uri = dataclasses_replace(
            _discovery(), jwks_uri="https://attacker.example.net/jwks"
        )
        with self.assertRaises(OidcJwksError):
            OidcJwksCache(_policy(), poisoned_uri, client)
        self.assertEqual(client.calls, [])


def dataclasses_replace(document, **changes):
    values = {field: getattr(document, field) for field in document.__dataclass_fields__}
    values.update(changes)
    return type(document)(**values)


if __name__ == "__main__":
    unittest.main()
