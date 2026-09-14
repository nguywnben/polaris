import asyncio
import base64
import dataclasses
import hashlib
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.coordination import CoordinationUnavailableError  # noqa: E402
from core.identity.oidc_discovery import OidcDiscoveryDocument  # noqa: E402
from core.identity.oidc_policy import load_oidc_configuration  # noqa: E402
from core.identity.oidc_transaction import (  # noqa: E402
    OidcAuthorizationTransactionError,
    OidcAuthorizationTransactionService,
)
from core.identity.repository import OidcPolicyRevisionRecord  # noqa: E402
from core.state_store import InMemoryStateStore  # noqa: E402

_ISSUER = "https://identity.example.com/tenant"
_STATE = "A" * 43
_BROWSER = "B" * 43
_SECOND_STATE = "C" * 43
_SECOND_BROWSER = "D" * 43
_THIRD_STATE = "E" * 43
_THIRD_BROWSER = "F" * 43
_HMAC_KEY = b"transaction-test-key-material-32b"


def _policy():
    revision = OidcPolicyRevisionRecord.initial(
        now=datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    )
    return load_oidc_configuration(
        revision,
        environ={
            "OIDC_ENABLED": "true",
            "OIDC_ISSUER": _ISSUER,
            "OIDC_CLIENT_ID": "polaris",
            "OIDC_CLIENT_SECRET": "enterprise-client-secret",
            "OIDC_REDIRECT_URI": "https://gateway.example.com/api/identity/oidc/callback",
            "OIDC_SCOPES": "openid profile email",
        },
    ).policy


def _discovery(**overrides):
    values = {
        "issuer": _ISSUER,
        "authorization_endpoint": "https://identity.example.com/authorize?tenant=enterprise",
        "token_endpoint": "https://identity.example.com/token",
        "jwks_uri": "https://identity.example.com/jwks",
        "userinfo_endpoint": "https://identity.example.com/userinfo",
        "response_types": ("code",),
        "subject_types": ("public",),
        "id_token_signing_algorithms": ("RS256",),
        "token_endpoint_auth_methods": ("client_secret_basic",),
        "code_challenge_methods": ("S256",),
        "scopes_supported": ("openid", "profile", "email"),
        "claims_supported": (),
    }
    values.update(overrides)
    return OidcDiscoveryDocument(**values)


def _tokens(*values):
    queue = list(values)

    def token_factory(_size):
        if not queue:
            raise AssertionError("Unexpected token allocation")
        return queue.pop(0)

    return token_factory


class UnknownConsumeStore:
    def __init__(self, store):
        self.store = store
        self.fail_after_consume = True

    async def create_oidc_transaction(self, request):
        return await self.store.create_oidc_transaction(request)

    async def consume_oidc_transaction(self, request):
        result = await self.store.consume_oidc_transaction(request)
        if self.fail_after_consume:
            self.fail_after_consume = False
            raise CoordinationUnavailableError("unknown result")
        return result


class FalsyCoordinationStore:
    """A valid selected backend whose truthiness must not trigger local fallback."""

    def __init__(self, store):
        self.store = store

    def __bool__(self):
        return False

    async def create_oidc_transaction(self, request):
        return await self.store.create_oidc_transaction(request)

    async def consume_oidc_transaction(self, request):
        return await self.store.consume_oidc_transaction(request)


class OidcAuthorizationTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_falsy_backend_and_exact_nondefault_epoch_are_preserved(self):
        backend = InMemoryStateStore(clock=lambda: 2_000_000_000.0)
        await backend.advance_epoch(1, "oidc-advance-epoch")
        await backend.mark_epoch_ready(2, "oidc-mark-ready")
        selected = FalsyCoordinationStore(backend)
        service = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            coordination=selected,
            fencing_epoch=2,
            token_factory=_tokens(_STATE, _BROWSER),
        )

        await service.begin()
        proof = await service.consume(state=_STATE, browser_token=_BROWSER)

        self.assertEqual(proof.issuer, _ISSUER)
        self.assertIs(service._coordination, selected)

    def test_fencing_epoch_is_strictly_validated(self):
        for epoch in (True, 0, -1, 1.0):
            with self.subTest(epoch=epoch), self.assertRaises(OidcAuthorizationTransactionError):
                OidcAuthorizationTransactionService(
                    _policy(),
                    _discovery(),
                    hmac_key=_HMAC_KEY,
                    fencing_epoch=epoch,
                )

    async def test_unknown_consume_result_never_releases_proof_twice(self):
        backend = InMemoryStateStore(clock=lambda: 2_000_000_000.0)
        uncertain = UnknownConsumeStore(backend)
        first = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            coordination=uncertain,
            token_factory=_tokens(_STATE, _BROWSER),
        )
        await first.begin()

        with self.assertRaises(OidcAuthorizationTransactionError):
            await first.consume(state=_STATE, browser_token=_BROWSER)

        verifier = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            coordination=backend,
        )
        with self.assertRaises(OidcAuthorizationTransactionError):
            await verifier.consume(state=_STATE, browser_token=_BROWSER)

    async def test_two_instances_share_one_time_proof_and_policy_drift_burns_it(self):
        backend = InMemoryStateStore(clock=lambda: 2_000_000_000.0)
        first = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            coordination=backend,
            token_factory=_tokens(_STATE, _BROWSER),
        )
        second = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            coordination=backend,
        )

        await first.begin()
        proof = await second.consume(state=_STATE, browser_token=_BROWSER)
        self.assertEqual(proof.issuer, _ISSUER)
        with self.assertRaises(OidcAuthorizationTransactionError):
            await first.consume(state=_STATE, browser_token=_BROWSER)

        drift_state, drift_browser = "G" * 43, "H" * 43
        drift_source = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            coordination=backend,
            token_factory=_tokens(drift_state, drift_browser),
        )
        await drift_source.begin()
        drifted_policy = dataclasses.replace(_policy(), revision=_policy().revision + 1)
        drifted = OidcAuthorizationTransactionService(
            drifted_policy,
            _discovery(),
            hmac_key=_HMAC_KEY,
            coordination=backend,
        )
        with self.assertRaises(OidcAuthorizationTransactionError):
            await drifted.consume(state=drift_state, browser_token=drift_browser)
        with self.assertRaises(OidcAuthorizationTransactionError):
            await drift_source.consume(state=drift_state, browser_token=drift_browser)

    async def test_begin_builds_exact_pkce_request_without_storing_plaintext_secrets(self):
        service = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            clock=lambda: 2_000_000_000.0,
            token_factory=_tokens(_STATE, _BROWSER),
        )

        request = await service.begin()

        parsed = urlsplit(request.authorization_url)
        parameters = parse_qs(parsed.query, strict_parsing=True)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "identity.example.com")
        self.assertEqual(parsed.path, "/authorize")
        self.assertEqual(parameters["tenant"], ["enterprise"])
        self.assertEqual(parameters["response_type"], ["code"])
        self.assertEqual(parameters["client_id"], ["polaris"])
        self.assertEqual(
            parameters["redirect_uri"],
            ["https://gateway.example.com/api/identity/oidc/callback"],
        )
        self.assertEqual(parameters["scope"], ["openid profile email"])
        self.assertEqual(parameters["state"], [_STATE])
        self.assertEqual(parameters["code_challenge_method"], ["S256"])
        self.assertEqual(request.browser_token, _BROWSER)
        self.assertEqual(request.expires_in_seconds, 300)
        self.assertNotIn(_STATE, repr(service))
        self.assertNotIn(_BROWSER, repr(service))
        record = next(iter(service._coordination._oidc_transactions.values()))
        self.assertNotIn(_STATE, repr(record))
        self.assertNotIn(_BROWSER, repr(record))

        proof = await service.consume(state=_STATE, browser_token=_BROWSER)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(proof.code_verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        self.assertEqual(parameters["code_challenge"], [challenge])
        self.assertEqual(parameters["nonce"], [proof.nonce])
        self.assertNotIn(proof.code_verifier, repr(record))
        self.assertNotIn(proof.nonce, repr(record))

    async def test_consume_is_browser_bound_issuer_bound_and_single_use(self):
        service = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            clock=lambda: 2_000_000_000.0,
            token_factory=_tokens(_STATE, _BROWSER),
        )
        request = await service.begin()
        parameters = parse_qs(urlsplit(request.authorization_url).query, strict_parsing=True)

        with self.assertRaises(OidcAuthorizationTransactionError):
            await service.consume(
                state=_STATE,
                browser_token=_SECOND_BROWSER,
                response_issuer=_ISSUER,
            )

        proof = await service.consume(
            state=_STATE,
            browser_token=_BROWSER,
            response_issuer=_ISSUER,
        )
        self.assertEqual(parameters["nonce"], [proof.nonce])
        self.assertEqual(proof.issuer, _ISSUER)
        self.assertEqual(
            proof.authorization_endpoint,
            "https://identity.example.com/authorize?tenant=enterprise",
        )
        self.assertEqual(proof.token_endpoint, "https://identity.example.com/token")
        self.assertEqual(proof.token_endpoint_auth_method, "client_secret_basic")
        self.assertNotIn(proof.code_verifier, repr(proof))
        self.assertNotIn(proof.nonce, repr(proof))

        with self.assertRaises(OidcAuthorizationTransactionError):
            await service.consume(
                state=_STATE,
                browser_token=_BROWSER,
                response_issuer=_ISSUER,
            )

    async def test_wrong_response_issuer_consumes_the_browser_bound_transaction(self):
        service = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            clock=lambda: 2_000_000_000.0,
            token_factory=_tokens(_STATE, _BROWSER),
        )
        await service.begin()

        with self.assertRaises(OidcAuthorizationTransactionError) as wrong_issuer:
            await service.consume(
                state=_STATE,
                browser_token=_BROWSER,
                response_issuer="https://attacker.example.com",
            )
        self._assert_content_free(wrong_issuer.exception)
        with self.assertRaises(OidcAuthorizationTransactionError):
            await service.consume(
                state=_STATE,
                browser_token=_BROWSER,
                response_issuer=_ISSUER,
            )

    async def test_wrong_browser_dominates_wrong_issuer_without_burning_transaction(self):
        service = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            token_factory=_tokens(_STATE, _BROWSER),
        )
        await service.begin()

        with self.assertRaises(OidcAuthorizationTransactionError):
            await service.consume(
                state=_STATE,
                browser_token=_SECOND_BROWSER,
                response_issuer="https://attacker.example.com",
            )

        proof = await service.consume(
            state=_STATE,
            browser_token=_BROWSER,
            response_issuer=_ISSUER,
        )
        self.assertEqual(proof.issuer, _ISSUER)

    async def test_expiry_capacity_and_invalid_endpoint_parameters_fail_closed(self):
        now = [2_000_000_000.0]
        service = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            clock=lambda: now[0],
            ttl_seconds=60,
            max_pending=1,
            token_factory=_tokens(
                _STATE,
                _BROWSER,
                _SECOND_STATE,
                _SECOND_BROWSER,
                _THIRD_STATE,
                _THIRD_BROWSER,
            ),
        )
        await service.begin()
        with self.assertRaises(OidcAuthorizationTransactionError):
            await service.begin()

        now[0] += 60
        with self.assertRaises(OidcAuthorizationTransactionError) as expired:
            await service.consume(state=_STATE, browser_token=_BROWSER)
        self._assert_content_free(expired.exception)
        replacement = await service.begin()
        self.assertEqual(replacement.browser_token, _THIRD_BROWSER)

        with self.assertRaises(OidcAuthorizationTransactionError):
            OidcAuthorizationTransactionService(
                _policy(),
                _discovery(authorization_endpoint="https://identity.example.com/authorize?state=x"),
                hmac_key=_HMAC_KEY,
            )
        with self.assertRaises(OidcAuthorizationTransactionError):
            OidcAuthorizationTransactionService(
                _policy(),
                _discovery(authorization_endpoint="https://identity.example.com/authorize?State=x"),
                hmac_key=_HMAC_KEY,
            )

    async def test_concurrent_consume_has_exactly_one_winner(self):
        service = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            clock=lambda: 2_000_000_000.0,
            token_factory=_tokens(_STATE, _BROWSER),
        )
        await service.begin()

        results = await asyncio.gather(
            service.consume(state=_STATE, browser_token=_BROWSER),
            service.consume(state=_STATE, browser_token=_BROWSER),
            return_exceptions=True,
        )

        self.assertEqual(sum(not isinstance(item, Exception) for item in results), 1)
        self.assertEqual(
            sum(isinstance(item, OidcAuthorizationTransactionError) for item in results),
            1,
        )

    async def test_configuration_and_generated_token_bounds_are_enforced(self):
        invalid_discoveries = (
            _discovery(issuer="https://identity.example.com/other"),
            _discovery(code_challenge_methods=("plain",)),
            _discovery(code_challenge_methods=("S256", "plain")),
            _discovery(token_endpoint_auth_methods=("none",)),
        )
        for discovery in invalid_discoveries:
            with self.subTest(discovery=discovery):
                with self.assertRaises(OidcAuthorizationTransactionError):
                    OidcAuthorizationTransactionService(_policy(), discovery, hmac_key=_HMAC_KEY)

        service = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            token_factory=_tokens("short", _BROWSER),
        )
        with self.assertRaises(OidcAuthorizationTransactionError):
            await service.begin()

    async def test_configuration_drift_and_begin_revision_are_explicit(self):
        policy = _policy()
        discovery = _discovery()
        service = OidcAuthorizationTransactionService(
            policy,
            discovery,
            hmac_key=_HMAC_KEY,
            token_factory=_tokens(_STATE, _BROWSER),
        )
        await service.begin()

        self.assertTrue(service.matches_configuration(policy, discovery))
        self.assertFalse(
            service.matches_configuration(
                dataclasses.replace(policy, revision=policy.revision + 1),
                discovery,
            )
        )
        self.assertFalse(
            service.matches_configuration(
                policy,
                dataclasses.replace(
                    discovery,
                    token_endpoint="https://identity.example.com/token-v2",
                ),
            )
        )
        proof = await service.consume(state=_STATE, browser_token=_BROWSER)
        self.assertEqual(proof.policy_revision, policy.revision)

    async def test_malformed_inputs_are_content_free_and_do_not_burn_transaction(self):
        malformed_values = (
            None,
            b"A" * 43,
            "short",
            "Ａ" * 43,
            "+" * 43,
            "=" * 43,
            "A" * 44,
        )
        for malformed in malformed_values:
            with self.subTest(malformed=repr(malformed)):
                service = OidcAuthorizationTransactionService(
                    _policy(),
                    _discovery(),
                    hmac_key=_HMAC_KEY,
                    token_factory=_tokens(_STATE, _BROWSER),
                )
                await service.begin()
                with self.assertRaises(OidcAuthorizationTransactionError) as caught:
                    await service.consume(state=malformed, browser_token=_BROWSER)
                self._assert_content_free(caught.exception)
                proof = await service.consume(state=_STATE, browser_token=_BROWSER)
                self.assertEqual(proof.issuer, _ISSUER)

        for malformed in malformed_values:
            with self.subTest(malformed_browser=repr(malformed)):
                service = OidcAuthorizationTransactionService(
                    _policy(),
                    _discovery(),
                    hmac_key=_HMAC_KEY,
                    token_factory=_tokens(_STATE, _BROWSER),
                )
                await service.begin()
                with self.assertRaises(OidcAuthorizationTransactionError) as caught:
                    await service.consume(state=_STATE, browser_token=malformed)
                self._assert_content_free(caught.exception)
                proof = await service.consume(state=_STATE, browser_token=_BROWSER)
                self.assertEqual(proof.issuer, _ISSUER)

        for malformed_issuer in ("", 123, b"issuer", "x" * 2_049):
            with self.subTest(malformed_issuer=type(malformed_issuer).__name__):
                service = OidcAuthorizationTransactionService(
                    _policy(),
                    _discovery(),
                    hmac_key=_HMAC_KEY,
                    token_factory=_tokens(_STATE, _BROWSER),
                )
                await service.begin()
                with self.assertRaises(OidcAuthorizationTransactionError) as caught:
                    await service.consume(
                        state=_STATE,
                        browser_token=_BROWSER,
                        response_issuer=malformed_issuer,
                    )
                self._assert_content_free(caught.exception)
                proof = await service.consume(state=_STATE, browser_token=_BROWSER)
                self.assertEqual(proof.issuer, _ISSUER)

    async def test_cancellation_while_waiting_for_lock_preserves_transaction(self):
        service = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            token_factory=_tokens(_STATE, _BROWSER),
        )
        await service.begin()
        await service._coordination._async_lock.acquire()
        task = asyncio.create_task(service.consume(state=_STATE, browser_token=_BROWSER))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        service._coordination._async_lock.release()

        proof = await service.consume(state=_STATE, browser_token=_BROWSER)
        self.assertEqual(proof.issuer, _ISSUER)

    async def test_capacity_failure_preserves_existing_transaction(self):
        service = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            max_pending=1,
            token_factory=_tokens(_STATE, _BROWSER),
        )
        await service.begin()
        with self.assertRaises(OidcAuthorizationTransactionError):
            await service.begin()

        proof = await service.consume(state=_STATE, browser_token=_BROWSER)
        self.assertEqual(proof.issuer, _ISSUER)

    async def test_default_generator_and_duplicate_state_are_bounded(self):
        service = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
        )
        request = await service.begin()
        parameters = parse_qs(urlsplit(request.authorization_url).query, strict_parsing=True)
        self.assertRegex(parameters["state"][0], re.compile(r"^[A-Za-z0-9_-]{43}$"))
        self.assertRegex(request.browser_token, re.compile(r"^[A-Za-z0-9_-]{43}$"))

        duplicate = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            token_factory=_tokens(_STATE, _BROWSER, _STATE, _SECOND_BROWSER),
        )
        await duplicate.begin()
        with self.assertRaises(OidcAuthorizationTransactionError):
            await duplicate.begin()
        proof = await duplicate.consume(state=_STATE, browser_token=_BROWSER)
        self.assertEqual(proof.issuer, _ISSUER)

    async def test_public_errors_suppress_provider_controlled_exception_chains(self):
        with self.assertRaises(OidcAuthorizationTransactionError) as constructor_error:
            OidcAuthorizationTransactionService(
                _policy(),
                _discovery(authorization_endpoint="https://identity.example.com/authorize?bad"),
                hmac_key=_HMAC_KEY,
            )
        self._assert_content_free(constructor_error.exception)

        service = OidcAuthorizationTransactionService(
            _policy(),
            _discovery(),
            hmac_key=_HMAC_KEY,
            token_factory=_tokens("provider-controlled-invalid-token", _BROWSER),
        )
        with self.assertRaises(OidcAuthorizationTransactionError) as begin_error:
            await service.begin()
        self._assert_content_free(begin_error.exception)

    def _assert_content_free(self, error):
        self.assertEqual(error.args, ("OIDC authorization transaction failed.",))
        self.assertIsNone(error.__cause__)
        self.assertTrue(error.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
