import inspect
import math
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.security_coordination import (  # noqa: E402
    MAX_SECURITY_PAYLOAD_BYTES,
    SECURITY_COORDINATION_SCHEMA_VERSION,
    AttemptClearRequest,
    AttemptClearResult,
    AttemptReservationDecision,
    AttemptReservationRequest,
    IdentitySecurityCoordinationStore,
    OidcTransactionConsumeRequest,
    OidcTransactionConsumeResult,
    OidcTransactionCreateRequest,
    SecurityAttemptCategory,
    SecurityPrincipalType,
    SecuritySessionState,
    SessionIssueRequest,
    SessionListRequest,
    SessionMutationResult,
    SessionPage,
    SessionResolveResult,
    SessionRevokeRequest,
    SessionRevokeResult,
    SessionRevokeTarget,
    SessionRotateRequest,
    TransactionCreateResult,
)


class SecurityCoordinationDomainTests(unittest.TestCase):
    def _issue(self, **overrides):
        values = {
            "session_digest": "a" * 64,
            "session_reference": "ssr_" + "b" * 32,
            "principal_index": "c" * 64,
            "principal_type": SecurityPrincipalType.OIDC_USER,
            "payload": b"encrypted-session-envelope",
            "idle_ttl_seconds": 300,
            "absolute_ttl_seconds": 900,
            "fencing_epoch": 1,
            "operation_id": "issue-session-1",
        }
        values.update(overrides)
        return SessionIssueRequest(**values)

    def _session(self, **overrides):
        values = {
            "session_digest": "a" * 64,
            "session_reference": "ssr_" + "b" * 32,
            "principal_index": "c" * 64,
            "principal_type": SecurityPrincipalType.OIDC_USER,
            "payload": b"encrypted-session-envelope",
            "issued_at": 100.0,
            "last_seen_at": 100.0,
            "idle_expires_at": 400.0,
            "absolute_expires_at": 1000.0,
        }
        values.update(overrides)
        return SecuritySessionState(**values)

    def test_valid_domain_is_frozen_and_secret_free(self):
        issue = self._issue()
        session = self._session()
        mutation = SessionMutationResult(True, session)
        resolved = SessionResolveResult(True, session)
        page = SessionPage((session,), None)

        self.assertEqual(SECURITY_COORDINATION_SCHEMA_VERSION, 1)
        self.assertEqual((mutation.applied, resolved.resolved, len(page.sessions)), (True, True, 1))
        for secret in (issue.session_digest, issue.principal_index, issue.payload.decode()):
            self.assertNotIn(secret, repr(issue))
        for secret in (session.session_digest, session.principal_index, session.payload.decode()):
            self.assertNotIn(secret, repr(session))
        with self.assertRaises(FrozenInstanceError):
            issue.fencing_epoch = 2

    def test_session_requests_reject_non_exact_identifiers_payloads_and_bounds(self):
        invalid = (
            {"session_digest": "A" * 64},
            {"session_digest": "a" * 63},
            {"session_reference": "ssr_" + "g" * 32},
            {"principal_index": "c" * 65},
            {"principal_type": "oidc_user"},
            {"payload": bytearray(b"x")},
            {"payload": b"x" * (MAX_SECURITY_PAYLOAD_BYTES + 1)},
            {"idle_ttl_seconds": True},
            {"idle_ttl_seconds": math.inf},
            {"idle_ttl_seconds": 299},
            {"absolute_ttl_seconds": 300},
            {"fencing_epoch": True},
            {"operation_id": "\n"},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    self._issue(**overrides)

        with self.assertRaises(ValueError):
            SessionRotateRequest("a" * 64, self._issue(), 1, "issue-session-1")
        with self.assertRaises(ValueError):
            SessionListRequest(limit=True, fencing_epoch=1)
        with self.assertRaises(ValueError):
            SessionRevokeRequest(
                SessionRevokeTarget.REFERENCE,
                "a" * 64,
                1,
                "revoke-session",
            )

    def test_session_state_and_results_reject_impossible_shapes(self):
        invalid_states = (
            {"issued_at": -1},
            {"last_seen_at": 99},
            {"idle_expires_at": 100},
            {"absolute_expires_at": 399},
            {"absolute_expires_at": math.nan},
            {"issued_at": 2**53},
        )
        for overrides in invalid_states:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    self._session(**overrides)

        with self.assertRaises(ValueError):
            SessionMutationResult(True, None)
        with self.assertRaises(ValueError):
            SessionMutationResult(False, self._session(), reason="capacity")
        with self.assertRaises(ValueError):
            SessionResolveResult(False, self._session(), reason="not_found")
        with self.assertRaises(ValueError):
            SessionResolveResult(False, None, reason="")
        with self.assertRaises(ValueError):
            SessionPage((self._session(), self._session()), None)
        with self.assertRaises(ValueError):
            SessionPage((), "ssr_" + "f" * 32)
        with self.assertRaises(ValueError):
            SessionRevokeResult(-1)

    def test_attempt_contract_rejects_cross_category_and_result_ambiguity(self):
        request = AttemptReservationRequest(
            SecurityAttemptCategory.LOGIN,
            "d" * 64,
            10,
            300,
            1,
            "attempt-1",
        )
        self.assertNotIn(request.client_index, repr(request))
        invalid = (
            {"category": "login"},
            {"client_index": "D" * 64},
            {"limit": True},
            {"limit": 0},
            {"window_seconds": 29},
            {"window_seconds": math.nan},
        )
        for overrides in invalid:
            values = {
                "category": SecurityAttemptCategory.LOGIN,
                "client_index": "d" * 64,
                "limit": 10,
                "window_seconds": 300,
                "fencing_epoch": 1,
                "operation_id": "attempt-1",
            }
            values.update(overrides)
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    AttemptReservationRequest(**values)

        with self.assertRaises(ValueError):
            AttemptReservationDecision(True, 0, 1)
        with self.assertRaises(ValueError):
            AttemptReservationDecision(False, 0, 0, reason="limited")
        with self.assertRaises(ValueError):
            AttemptReservationDecision(False, 1, 1, reason="limited")
        with self.assertRaises(ValueError):
            AttemptClearRequest(SecurityAttemptCategory.LOGIN, "bad", 1, "clear")
        with self.assertRaises(ValueError):
            AttemptClearResult(cleared=True, idempotent="yes")

    def test_oidc_transaction_contract_is_opaque_and_closed(self):
        create = OidcTransactionCreateRequest(
            "e" * 64,
            "f" * 64,
            b"encrypted-oidc-envelope",
            300,
            1,
            "oidc-create-1",
        )
        for secret in (create.state_index, create.browser_index, create.payload.decode()):
            self.assertNotIn(secret, repr(create))
        consumed = OidcTransactionConsumeResult(True, b"encrypted-oidc-envelope")
        self.assertNotIn("encrypted-oidc-envelope", repr(consumed))

        invalid = (
            {"state_index": "e" * 63},
            {"browser_index": "F" * 64},
            {"payload": memoryview(b"x")},
            {"ttl_seconds": 59},
            {"ttl_seconds": 901},
            {"browser_index": "e" * 64},
        )
        for overrides in invalid:
            values = {
                "state_index": "e" * 64,
                "browser_index": "f" * 64,
                "payload": b"opaque",
                "ttl_seconds": 300,
                "fencing_epoch": 1,
                "operation_id": "oidc-create-1",
            }
            values.update(overrides)
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    OidcTransactionCreateRequest(**values)

        with self.assertRaises(ValueError):
            TransactionCreateResult(True, reason="capacity")
        with self.assertRaises(ValueError):
            OidcTransactionConsumeResult(True, None)
        with self.assertRaises(ValueError):
            OidcTransactionConsumeResult(False, b"opaque", reason="not_found")
        with self.assertRaises(ValueError):
            OidcTransactionConsumeResult(False, None, reason="")
        with self.assertRaises(ValueError):
            OidcTransactionConsumeRequest("e" * 64, "bad", 1, "consume")

    def test_protocol_exposes_only_typed_security_operations(self):
        expected = {
            "issue_security_session",
            "resolve_security_session",
            "rotate_security_session",
            "revoke_security_sessions",
            "list_security_sessions",
            "reserve_security_attempt",
            "clear_security_attempts",
            "create_oidc_transaction",
            "consume_oidc_transaction",
        }
        self.assertTrue(expected.issubset(IdentitySecurityCoordinationStore.__dict__))
        for name in expected:
            self.assertTrue(
                inspect.iscoroutinefunction(IdentitySecurityCoordinationStore.__dict__[name])
            )


if __name__ == "__main__":
    unittest.main()
