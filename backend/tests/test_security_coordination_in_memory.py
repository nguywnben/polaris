"""Behavioral tests for the in-process W4.16 security-state reference."""

from __future__ import annotations

import asyncio
import copy
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from core.coordination import (
    CoordinationCorruptError,
    CoordinationReconciliationRequiredError,
)
from core.security_coordination import (
    AttemptReservationRequest,
    OidcTransactionConsumeRequest,
    OidcTransactionCreateRequest,
    SecurityAttemptCategory,
    SecurityPrincipalType,
    SessionIssueRequest,
    SessionListRequest,
    SessionResolveRequest,
    SessionRevokeRequest,
    SessionRevokeTarget,
    SessionRotateRequest,
)
from core.state_store import InMemoryStateStore
from security_coordination_store_contract import SecurityCoordinationStoreContract


class _Clock:
    def __init__(self) -> None:
        self.value = 1_000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class InMemorySecurityCoordinationTests(
    SecurityCoordinationStoreContract,
    unittest.IsolatedAsyncioTestCase,
):
    async def asyncSetUp(self) -> None:
        self.clock = _Clock()
        self.advance_clock = self.clock.advance
        self.store = InMemoryStateStore(clock=self.clock)

    async def test_shared_security_coordination_contract(self) -> None:
        await self.assert_session_lifecycle_contract()
        await self.assert_attempt_and_oidc_transaction_contract()

    async def test_security_operations_require_exact_ready_epoch(self) -> None:
        await self.assert_exact_ready_epoch_contract()

    async def test_session_indexes_rotation_revocation_and_listing_are_atomic(self) -> None:
        local = SessionIssueRequest(
            "a" * 64,
            "ssr_" + "a" * 32,
            "1" * 64,
            SecurityPrincipalType.LOCAL_OWNER,
            b"local",
            300,
            900,
            1,
            "issue-local",
        )
        oidc_a = SessionIssueRequest(
            "b" * 64,
            "ssr_" + "b" * 32,
            "2" * 64,
            SecurityPrincipalType.OIDC_USER,
            b"oidc-a",
            300,
            900,
            1,
            "issue-oidc-a",
        )
        oidc_b = SessionIssueRequest(
            "c" * 64,
            "ssr_" + "c" * 32,
            "2" * 64,
            SecurityPrincipalType.OIDC_USER,
            b"oidc-b",
            300,
            900,
            1,
            "issue-oidc-b",
        )
        await asyncio.gather(
            self.store.issue_security_session(local),
            self.store.issue_security_session(oidc_a),
            self.store.issue_security_session(oidc_b),
        )

        first_page = await self.store.list_security_sessions(SessionListRequest(2, 1))
        second_page = await self.store.list_security_sessions(
            SessionListRequest(2, 1, first_page.next_reference)
        )
        self.assertEqual(
            [item.session_reference for item in first_page.sessions + second_page.sessions],
            [local.session_reference, oidc_a.session_reference, oidc_b.session_reference],
        )

        replacement = SessionIssueRequest(
            "d" * 64,
            "ssr_" + "d" * 32,
            oidc_a.principal_index,
            SecurityPrincipalType.OIDC_USER,
            b"rotated",
            300,
            900,
            1,
            "rotate-oidc-a",
        )
        rotated = await self.store.rotate_security_session(
            SessionRotateRequest(oidc_a.session_digest, replacement, 1, "rotate-oidc-a")
        )
        self.assertTrue(rotated.applied)
        self.assertEqual(
            (
                await self.store.resolve_security_session(
                    SessionResolveRequest(oidc_a.session_digest, 300, 1, "old-after-rotate")
                )
            ).reason,
            "not_found",
        )

        revoked = await self.store.revoke_security_sessions(
            SessionRevokeRequest(
                SessionRevokeTarget.PRINCIPAL,
                oidc_a.principal_index,
                1,
                "revoke-oidc-principal",
            )
        )
        self.assertEqual(revoked.revoked_count, 2)
        remaining = await self.store.list_security_sessions(SessionListRequest(10, 1))
        self.assertEqual(
            [item.session_reference for item in remaining.sessions], [local.session_reference]
        )

    async def test_capacity_never_evicts_live_security_state(self) -> None:
        store = InMemoryStateStore(
            clock=self.clock,
            _security_session_limit_for_testing=1,
            _security_attempt_limit_for_testing=1,
            _oidc_transaction_limit_for_testing=1,
        )
        await self.assert_capacity_preserves_live_evidence_contract(store)

    async def test_attempt_threshold_and_oidc_consume_have_one_atomic_winner(self) -> None:
        await self.assert_atomic_attempt_and_consume_contract()

    async def test_resolve_replay_cannot_resurrect_a_revoked_session(self) -> None:
        session = self._issue("abc")
        self.assertTrue((await self.store.issue_security_session(session)).applied)
        resolve = SessionResolveRequest(session.session_digest, 300, 1, "resolve-before-revoke")
        self.assertTrue((await self.store.resolve_security_session(resolve)).resolved)
        self.assertEqual(
            (
                await self.store.revoke_security_sessions(
                    SessionRevokeRequest(
                        SessionRevokeTarget.DIGEST,
                        session.session_digest,
                        1,
                        "revoke-before-replay",
                    )
                )
            ).revoked_count,
            1,
        )

        replay_after_revoke = await self.store.resolve_security_session(resolve)

        self.assertEqual(
            (replay_after_revoke.resolved, replay_after_revoke.reason),
            (False, "not_found"),
        )

    async def test_absent_oidc_consume_replay_does_not_outlive_maximum_transaction(self) -> None:
        request = OidcTransactionConsumeRequest(
            "a" * 64,
            "b" * 64,
            1,
            "consume-absent",
        )
        first = await self.store.consume_oidc_transaction(request)
        replay = await self.store.consume_oidc_transaction(request)
        self.clock.advance(901)
        after_maximum_transaction_lifetime = await self.store.consume_oidc_transaction(request)

        self.assertEqual(first.reason, "not_found")
        self.assertTrue(replay.idempotent)
        self.assertFalse(after_maximum_transaction_lifetime.idempotent)

    async def test_regressing_store_clock_fails_closed_without_rewriting_session_time(self) -> None:
        session = self._issue("abc")
        self.assertTrue((await self.store.issue_security_session(session)).applied)
        self.clock.advance(10)
        touched = await self.store.resolve_security_session(
            SessionResolveRequest(session.session_digest, 300, 1, "touch-forward")
        )
        before = copy.deepcopy(self.store._security_sessions)
        self.clock.value -= 5

        with self.assertRaises(CoordinationCorruptError):
            await self.store.resolve_security_session(
                SessionResolveRequest(session.session_digest, 300, 1, "touch-backward")
            )
        self.assertEqual(self.store._security_sessions, before)
        self.assertEqual(touched.session.last_seen_at, 1_010.0)

    async def test_combined_record_and_replay_cleanup_is_bounded_and_transactional(self) -> None:
        store = InMemoryStateStore(
            clock=self.clock,
            _security_attempt_limit_for_testing=300,
            _security_replay_limit_for_testing=600,
        )
        # Each admitted attempt creates one record and one replay. 129 of each means
        # 258 due entries, proving the ceiling applies across both indexes together.
        for index in range(129):
            decision = await store.reserve_security_attempt(
                AttemptReservationRequest(
                    SecurityAttemptCategory.LOGIN,
                    f"{index:064x}",
                    1,
                    30,
                    1,
                    f"fill-login-{index}",
                )
            )
            self.assertTrue(decision.allowed)
        self.clock.advance(31)
        before = copy.deepcopy(
            (
                store._security_attempts,
                store._security_attempt_expiries,
                store._security_attempt_replays,
                store._security_attempt_replay_expiries,
            )
        )

        for attempt in range(2):
            with self.subTest(attempt=attempt):
                denied = await store.reserve_security_attempt(
                    AttemptReservationRequest(
                        SecurityAttemptCategory.LOGIN,
                        "f" * 64,
                        1,
                        30,
                        1,
                        "after-backlog",
                    )
                )
                self.assertEqual(denied.reason, "reconciliation_required")
                self.assertEqual(
                    (
                        store._security_attempts,
                        store._security_attempt_expiries,
                        store._security_attempt_replays,
                        store._security_attempt_replay_expiries,
                    ),
                    before,
                )

        recovery = await store.reserve_security_attempt(
            AttemptReservationRequest(
                SecurityAttemptCategory.RECOVERY,
                "f" * 64,
                1,
                30,
                1,
                "recovery-not-blocked",
            )
        )
        self.assertTrue(recovery.allowed)

    async def test_corrupt_indexes_fail_closed_without_partial_mutation(self) -> None:
        first = self._issue("abc")
        second = self._issue("def")
        await self.store.issue_security_session(first)
        await self.store.issue_security_session(second)
        self.store._security_digest_by_reference[first.session_reference] = second.session_digest
        before = copy.deepcopy(
            (
                self.store._security_sessions,
                self.store._security_digest_by_reference,
                self.store._security_digests_by_principal,
                self.store._security_digests_by_principal_type,
            )
        )

        with self.assertRaises(CoordinationCorruptError):
            await self.store.revoke_security_sessions(
                SessionRevokeRequest(
                    SessionRevokeTarget.PRINCIPAL_TYPE,
                    SecurityPrincipalType.OIDC_USER.value,
                    1,
                    "revoke-corrupt",
                )
            )
        self.assertEqual(
            (
                self.store._security_sessions,
                self.store._security_digest_by_reference,
                self.store._security_digests_by_principal,
                self.store._security_digests_by_principal_type,
            ),
            before,
        )

    async def test_missing_principal_index_member_blocks_revocation_without_partial_mutation(
        self,
    ) -> None:
        first = self._issue("abc")
        second = SessionIssueRequest(
            "d" * 64,
            "ssr_" + "e" * 32,
            first.principal_index,
            first.principal_type,
            b"second",
            300,
            900,
            1,
            "issue-second-principal-session",
        )
        await self.store.issue_security_session(first)
        await self.store.issue_security_session(second)
        self.store._security_digests_by_principal[first.principal_index].remove(
            first.session_digest
        )
        before = copy.deepcopy(
            (
                self.store._security_sessions,
                self.store._security_digest_by_reference,
                self.store._security_digests_by_principal,
                self.store._security_digests_by_principal_type,
            )
        )

        with self.assertRaises(CoordinationCorruptError):
            await self.store.revoke_security_sessions(
                SessionRevokeRequest(
                    SessionRevokeTarget.PRINCIPAL,
                    first.principal_index,
                    1,
                    "revoke-incomplete-principal-index",
                )
            )
        self.assertEqual(
            (
                self.store._security_sessions,
                self.store._security_digest_by_reference,
                self.store._security_digests_by_principal,
                self.store._security_digests_by_principal_type,
            ),
            before,
        )

    async def test_missing_expiry_indexes_fail_closed_for_session_and_oidc(self) -> None:
        session = self._issue("abc")
        await self.store.issue_security_session(session)
        self.store._security_session_expiries.discard(session.session_digest)
        with self.assertRaises(CoordinationCorruptError):
            await self.store.resolve_security_session(
                SessionResolveRequest(session.session_digest, 300, 1, "resolve-partial-index")
            )

        store = InMemoryStateStore(clock=self.clock)
        transaction = OidcTransactionCreateRequest(
            "d" * 64,
            "e" * 64,
            b"opaque-proof",
            300,
            1,
            "create-partial-index",
        )
        await store.create_oidc_transaction(transaction)
        store._oidc_transaction_expiries.discard(transaction.state_index)
        with self.assertRaises(CoordinationCorruptError):
            await store.consume_oidc_transaction(
                OidcTransactionConsumeRequest(
                    transaction.state_index,
                    transaction.browser_index,
                    1,
                    "consume-partial-index",
                )
            )

    async def test_replay_never_adopts_reused_session_or_transaction_identifiers(self) -> None:
        first = self._issue("abc")
        await self.store.issue_security_session(first)
        await self.store.revoke_security_sessions(
            SessionRevokeRequest(
                SessionRevokeTarget.DIGEST,
                first.session_digest,
                1,
                "revoke-first-before-reuse",
            )
        )
        reused_session = SessionIssueRequest(
            first.session_digest,
            "ssr_" + "d" * 32,
            "e" * 64,
            SecurityPrincipalType.LOCAL_OWNER,
            b"different-session",
            300,
            900,
            1,
            "issue-reused-session",
        )
        self.assertTrue((await self.store.issue_security_session(reused_session)).applied)
        old_issue_replay = await self.store.issue_security_session(first)
        self.assertEqual(
            (old_issue_replay.applied, old_issue_replay.reason),
            (False, "conflict"),
        )

        transaction = OidcTransactionCreateRequest(
            "1" * 64,
            "2" * 64,
            b"first-proof",
            300,
            1,
            "create-first-proof",
        )
        await self.store.create_oidc_transaction(transaction)
        await self.store.consume_oidc_transaction(
            OidcTransactionConsumeRequest(
                transaction.state_index,
                transaction.browser_index,
                1,
                "consume-first-proof",
            )
        )
        reused_transaction = OidcTransactionCreateRequest(
            transaction.state_index,
            "3" * 64,
            b"different-proof",
            300,
            1,
            "create-reused-proof",
        )
        self.assertTrue((await self.store.create_oidc_transaction(reused_transaction)).applied)
        old_create_replay = await self.store.create_oidc_transaction(transaction)
        self.assertEqual(
            (old_create_replay.applied, old_create_replay.reason),
            (False, "conflict"),
        )

    async def test_repeated_session_touch_keeps_one_indexed_expiry_entry(self) -> None:
        session = self._issue("abc")
        self.assertTrue((await self.store.issue_security_session(session)).applied)

        for index in range(300):
            self.clock.advance(0.5)
            self.assertTrue(
                (
                    await self.store.resolve_security_session(
                        SessionResolveRequest(
                            session.session_digest,
                            300,
                            1,
                            f"touch-indexed-expiry-{index}",
                        )
                    )
                ).resolved
            )

        self.assertEqual(len(self.store._security_sessions), 1)
        self.assertEqual(len(self.store._security_session_expiries), 1)

    async def test_close_is_idempotent_and_all_security_operations_fail_after_close(self) -> None:
        await self.assert_security_operations_fail_after_close()

    async def test_security_cleanup_backlog_raises_for_non_decision_operations(self) -> None:
        store = InMemoryStateStore(
            clock=self.clock,
            _security_session_limit_for_testing=300,
            _security_replay_limit_for_testing=600,
        )
        for index in range(257):
            suffix = f"{index:064x}"
            request = SessionIssueRequest(
                suffix,
                "ssr_" + f"{index:032x}",
                f"{index + 1:064x}",
                SecurityPrincipalType.OIDC_USER,
                b"payload",
                300,
                301,
                1,
                f"expire-session-{index}",
            )
            self.assertTrue((await store.issue_security_session(request)).applied)
        self.clock.advance(302)

        with self.assertRaises(CoordinationReconciliationRequiredError):
            await store.list_security_sessions(SessionListRequest(10, 1))


if __name__ == "__main__":
    unittest.main()
