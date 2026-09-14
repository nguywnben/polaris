import asyncio
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.identity.oidc_code_flow import (  # noqa: E402
    OidcAuthorizationCodeError,
    OidcAuthorizationCodeFlow,
)
from core.identity.oidc_discovery import OidcDiscoveryDocument  # noqa: E402
from core.identity.oidc_http import OidcHttpError  # noqa: E402
from core.identity.oidc_id_token import VerifiedOidcIdToken  # noqa: E402
from core.identity.oidc_policy import load_oidc_configuration  # noqa: E402
from core.identity.oidc_transaction import (  # noqa: E402
    OidcAuthorizationTransactionService,
)
from core.identity.repository import OidcPolicyRevisionRecord  # noqa: E402

_ISSUER = "https://identity.example.com/tenant"
_CLIENT_ID = "polaris"
_CLIENT_SECRET = "enterprise-client-secret"
_HMAC_KEY = b"code-flow-test-key-material-32byt"
_STATE = "A" * 43
_BROWSER = "B" * 43


def _configuration(*, revision_number=1):
    revision = OidcPolicyRevisionRecord.initial(
        now=datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    )
    if revision_number != 1:
        revision = replace(revision, revision=revision_number)
    return load_oidc_configuration(
        revision,
        environ={
            "OIDC_ENABLED": "true",
            "OIDC_ISSUER": _ISSUER,
            "OIDC_CLIENT_ID": _CLIENT_ID,
            "OIDC_CLIENT_SECRET": _CLIENT_SECRET,
            "OIDC_REDIRECT_URI": "https://gateway.example.com/api/identity/oidc/callback",
        },
    )


def _discovery(*, auth_method="client_secret_basic", **overrides):
    values = {
        "issuer": _ISSUER,
        "authorization_endpoint": "https://identity.example.com/authorize",
        "token_endpoint": "https://identity.example.com/token",
        "jwks_uri": "https://identity.example.com/jwks",
        "userinfo_endpoint": None,
        "response_types": ("code",),
        "subject_types": ("public",),
        "id_token_signing_algorithms": ("RS256",),
        "token_endpoint_auth_methods": (auth_method,),
        "code_challenge_methods": ("S256",),
        "scopes_supported": ("openid",),
        "claims_supported": (),
    }
    values.update(overrides)
    return OidcDiscoveryDocument(**values)


def _verified(nonce="verified-nonce"):
    return VerifiedOidcIdToken(
        issuer=_ISSUER,
        subject="subject-123",
        audiences=(_CLIENT_ID,),
        authorized_party=None,
        expires_at=2_000_000_300,
        issued_at=2_000_000_000,
        not_before=None,
        nonce=nonce,
        username="operator",
        display_name="Enterprise Operator",
        email="operator@example.com",
        groups=("gateway-operators",),
        userinfo_subject_validated=False,
        policy_revision=1,
        jwks_generation=1,
    )


class QueueTokenClient:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def post_form_json(self, url, fields, *, basic_auth=None):
        self.calls.append((url, fields, basic_auth))
        if not self.outcomes:
            raise AssertionError("Unexpected token exchange")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return await outcome()
        return outcome


class RecordingVerifier:
    def __init__(self, policy, discovery, result=None):
        self.policy = policy
        self.discovery = discovery
        self.result = result or _verified()
        self.calls = []

    def matches_configuration(self, policy, discovery):
        return self.policy == policy and self.discovery == discovery

    async def verify(self, token, *, expected_nonce, userinfo=None):
        self.calls.append((token, expected_nonce, userinfo))
        return replace(self.result, nonce=expected_nonce)


def _tokens(*values):
    queue = list(values)

    def token_factory(_size):
        if not queue:
            raise AssertionError("Unexpected token allocation")
        return queue.pop(0)

    return token_factory


def _token_response(**overrides):
    return {
        "token_type": "Bearer",
        "access_token": "provider-access-token",
        "id_token": "provider.id.token",
        "expires_in": 3600,
        "refresh_token": "provider-refresh-token",
        "extension": {"ignored": True},
    } | overrides


class OidcAuthorizationCodeFlowTests(unittest.IsolatedAsyncioTestCase):
    def _flow(self, *outcomes, auth_method="client_secret_basic"):
        configuration = _configuration()
        discovery = _discovery(auth_method=auth_method)
        transactions = OidcAuthorizationTransactionService(
            configuration.policy,
            discovery,
            hmac_key=_HMAC_KEY,
            token_factory=_tokens(_STATE, _BROWSER),
        )
        client = QueueTokenClient(*outcomes)
        verifier = RecordingVerifier(configuration.policy, discovery)
        flow = OidcAuthorizationCodeFlow(
            configuration,
            discovery,
            transactions,
            client,
            verifier,
        )
        return flow, transactions, client, verifier

    async def _begin(self, transactions):
        request = await transactions.begin()
        state = parse_qs(urlsplit(request.authorization_url).query, strict_parsing=True)["state"][0]
        return state, request.browser_token

    async def test_basic_exchange_returns_only_verified_identity_and_is_single_use(self):
        response = _token_response()
        flow, transactions, client, verifier = self._flow(response)
        state, browser_token = await self._begin(transactions)

        result = await flow.complete(
            urlencode({"code": "provider-code", "state": state, "iss": _ISSUER}).encode("ascii"),
            browser_token=browser_token,
        )

        self.assertIsInstance(result, VerifiedOidcIdToken)
        self.assertEqual(result.subject, "subject-123")
        self.assertNotIn("provider-access-token", repr(result))
        self.assertNotIn("provider-refresh-token", repr(result))
        self.assertEqual(len(client.calls), 1)
        endpoint, fields, basic_auth = client.calls[0]
        self.assertEqual(endpoint, "https://identity.example.com/token")
        field_map = dict(fields)
        self.assertEqual(set(field_map), {"grant_type", "code", "redirect_uri", "code_verifier"})
        self.assertEqual(field_map["grant_type"], "authorization_code")
        self.assertEqual(field_map["code"], "provider-code")
        self.assertEqual(
            field_map["redirect_uri"],
            "https://gateway.example.com/api/identity/oidc/callback",
        )
        self.assertRegex(field_map["code_verifier"], r"^[A-Za-z0-9_-]{43}$")
        self.assertEqual(basic_auth, (_CLIENT_ID, _CLIENT_SECRET))
        self.assertEqual(verifier.calls[0][0], "provider.id.token")
        self.assertEqual(verifier.calls[0][2], None)
        self.assertEqual(result.nonce, verifier.calls[0][1])
        self.assertNotIn("provider-code", repr(flow))
        self.assertNotIn(_CLIENT_SECRET, repr(flow))

        with self.assertRaises(OidcAuthorizationCodeError):
            await flow.complete(
                urlencode({"code": "provider-code", "state": state}).encode("ascii"),
                browser_token=browser_token,
            )

    async def test_client_secret_post_is_used_only_when_discovery_requires_it(self):
        flow, transactions, client, _verifier = self._flow(
            _token_response(),
            auth_method="client_secret_post",
        )
        state, browser_token = await self._begin(transactions)

        await flow.complete(
            urlencode({"code": "provider-code", "state": state}).encode("ascii"),
            browser_token=browser_token,
        )

        fields = dict(client.calls[0][1])
        self.assertEqual(fields["client_id"], _CLIENT_ID)
        self.assertEqual(fields["client_secret"], _CLIENT_SECRET)
        self.assertIsNone(client.calls[0][2])

    async def test_provider_error_is_content_free_and_consumes_matching_transaction(self):
        flow, transactions, client, verifier = self._flow()
        state, browser_token = await self._begin(transactions)
        raw_query = urlencode(
            {
                "error": "access_denied",
                "error_description": "provider-secret-detail",
                "error_uri": "https://identity.example.com/error?id=secret",
                "state": state,
                "iss": _ISSUER,
            }
        ).encode("ascii")

        with self.assertRaises(OidcAuthorizationCodeError) as caught:
            await flow.complete(raw_query, browser_token=browser_token)
        self._assert_content_free(caught.exception)
        self.assertEqual(client.calls, [])
        self.assertEqual(verifier.calls, [])

        with self.assertRaises(OidcAuthorizationCodeError):
            await flow.complete(raw_query, browser_token=browser_token)

    async def test_duplicate_unknown_query_tokens_and_malformed_queries_do_not_burn_state(self):
        invalid_queries = (
            f"code=one&state={_STATE}&state={_STATE}".encode("ascii"),
            f"code=one&state={_STATE}&access_token=query-token".encode("ascii"),
            f"code=one&state={_STATE}&unknown=value".encode("ascii"),
            f"code=one&state={_STATE}&bad=%ZZ".encode("ascii"),
            b"\xff",
            b"x" * 8_193,
        )
        for raw_query in invalid_queries:
            with self.subTest(raw_query=raw_query[:40]):
                flow, transactions, _client, _verifier = self._flow(_token_response())
                state, browser_token = await self._begin(transactions)
                raw_query = raw_query.replace(_STATE.encode("ascii"), state.encode("ascii"))
                with self.assertRaises(OidcAuthorizationCodeError) as caught:
                    await flow.complete(raw_query, browser_token=browser_token)
                self._assert_content_free(caught.exception)

                result = await flow.complete(
                    urlencode({"code": "valid-code", "state": state}).encode("ascii"),
                    browser_token=browser_token,
                )
                self.assertEqual(result.subject, "subject-123")

    async def test_wrong_browser_does_not_burn_but_mixed_issuer_does(self):
        flow, transactions, _client, _verifier = self._flow(_token_response())
        state, browser_token = await self._begin(transactions)
        callback = urlencode({"code": "provider-code", "state": state, "iss": _ISSUER}).encode(
            "ascii"
        )

        with self.assertRaises(OidcAuthorizationCodeError):
            await flow.complete(callback, browser_token="C" * 43)
        with self.assertRaises(OidcAuthorizationCodeError):
            await flow.complete(
                urlencode(
                    {
                        "code": "provider-code",
                        "state": state,
                        "iss": "https://attacker.example.com",
                    }
                ).encode("ascii"),
                browser_token=browser_token,
            )
        with self.assertRaises(OidcAuthorizationCodeError):
            await flow.complete(callback, browser_token=browser_token)

    async def test_invalid_token_responses_are_rejected_before_verification(self):
        invalid_responses = (
            [],
            {},
            _token_response(token_type="MAC"),
            _token_response(access_token=""),
            _token_response(id_token=""),
            _token_response(expires_in=True),
            _token_response(refresh_token="line\nbreak"),
            _token_response(**{f"extension_{index}": index for index in range(33)}),
        )
        for response in invalid_responses:
            with self.subTest(response_type=type(response).__name__):
                flow, transactions, _client, verifier = self._flow(response)
                state, browser_token = await self._begin(transactions)
                with self.assertRaises(OidcAuthorizationCodeError) as caught:
                    await flow.complete(
                        urlencode({"code": "provider-code", "state": state}).encode("ascii"),
                        browser_token=browser_token,
                    )
                self._assert_content_free(caught.exception)
                self.assertEqual(verifier.calls, [])

    async def test_outage_and_cancellation_consume_transaction_without_leaking_details(self):
        flow, transactions, _client, _verifier = self._flow(
            OidcHttpError(),
        )
        state, browser_token = await self._begin(transactions)
        callback = urlencode({"code": "provider-code", "state": state}).encode("ascii")
        with self.assertRaises(OidcAuthorizationCodeError) as outage:
            await flow.complete(callback, browser_token=browser_token)
        self._assert_content_free(outage.exception)
        with self.assertRaises(OidcAuthorizationCodeError):
            await flow.complete(callback, browser_token=browser_token)

        async def cancelled():
            raise asyncio.CancelledError

        flow, transactions, _client, _verifier = self._flow(cancelled)
        state, browser_token = await self._begin(transactions)
        callback = urlencode({"code": "provider-code", "state": state}).encode("ascii")
        with self.assertRaises(asyncio.CancelledError):
            await flow.complete(callback, browser_token=browser_token)
        with self.assertRaises(OidcAuthorizationCodeError):
            await flow.complete(callback, browser_token=browser_token)

    async def test_constructor_rejects_every_mismatched_trust_component(self):
        configuration = _configuration()
        discovery = _discovery()
        transactions = OidcAuthorizationTransactionService(
            configuration.policy,
            discovery,
            hmac_key=_HMAC_KEY,
        )
        client = QueueTokenClient(_token_response())
        verifier = RecordingVerifier(configuration.policy, discovery)
        mismatches = (
            (
                _configuration(revision_number=2),
                discovery,
                transactions,
                verifier,
            ),
            (
                configuration,
                replace(discovery, token_endpoint="https://identity.example.com/token-v2"),
                transactions,
                verifier,
            ),
            (
                configuration,
                discovery,
                transactions,
                RecordingVerifier(
                    configuration.policy,
                    replace(discovery, issuer="https://identity.example.com/other"),
                ),
            ),
        )
        for config, metadata, store, token_verifier in mismatches:
            with self.subTest(revision=config.policy.revision, endpoint=metadata.token_endpoint):
                with self.assertRaises(OidcAuthorizationCodeError):
                    OidcAuthorizationCodeFlow(
                        config,
                        metadata,
                        store,
                        client,
                        token_verifier,
                    )

    def _assert_content_free(self, error):
        self.assertEqual(error.args, ("OIDC authorization code failed.",))
        self.assertIsNone(error.__cause__)
        self.assertTrue(error.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
