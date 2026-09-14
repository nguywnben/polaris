"""Reusable W4.16 semantics for every identity-security coordination backend."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable

from core.coordination import CoordinationUnavailableError, EpochState
from core.security_coordination import (
    AttemptClearRequest,
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

if TYPE_CHECKING:
    from core.security_coordination import IdentitySecurityCoordinationStore


class SecurityCoordinationStoreContract:
    """Behavioral fixture for the process-local security coordination store."""

    store: IdentitySecurityCoordinationStore
    advance_clock: Callable[[float], None]

    @staticmethod
    def _issue(
        suffix: str,
        *,
        operation_id: str | None = None,
    ) -> SessionIssueRequest:
        return SessionIssueRequest(
            session_digest=(suffix[0] * 64),
            session_reference=f"ssr_{suffix[1] * 32}",
            principal_index=(suffix[2] * 64),
            principal_type=SecurityPrincipalType.OIDC_USER,
            payload=f"payload-{suffix}".encode("ascii"),
            idle_ttl_seconds=300,
            absolute_ttl_seconds=900,
            fencing_epoch=1,
            operation_id=operation_id or f"issue-{suffix}",
        )

    async def assert_session_lifecycle_contract(self) -> None:
        first = self._issue("abc")
        issued = await self.store.issue_security_session(first)
        replayed = await self.store.issue_security_session(first)
        self.assertTrue(issued.applied)
        self.assertIsNotNone(issued.session)
        self.assertTrue(replayed.idempotent)

        issue_conflict = await self.store.issue_security_session(
            self._issue("fed", operation_id=first.operation_id)
        )
        self.assertEqual((issue_conflict.applied, issue_conflict.reason), (False, "conflict"))

        resolved = await self.store.resolve_security_session(
            SessionResolveRequest(first.session_digest, 300, 1, "resolve-abc")
        )
        self.assertTrue(resolved.resolved)
        self.assertEqual(resolved.session.payload, first.payload)

        self.advance_clock(10)
        touched = await self.store.resolve_security_session(
            SessionResolveRequest(first.session_digest, 300, 1, "touch-abc")
        )
        self.assertGreater(touched.session.last_seen_at, resolved.session.last_seen_at)
        self.assertGreater(touched.session.idle_expires_at, resolved.session.idle_expires_at)
        issue_replay_after_touch = await self.store.issue_security_session(first)
        self.assertTrue(issue_replay_after_touch.idempotent)
        self.assertEqual(
            issue_replay_after_touch.session.last_seen_at,
            touched.session.last_seen_at,
        )

        replacement = self._issue("def", operation_id="rotate-abc")
        rotated = await self.store.rotate_security_session(
            SessionRotateRequest(
                current_session_digest=first.session_digest,
                replacement=replacement,
                fencing_epoch=1,
                operation_id="rotate-abc",
            )
        )
        self.assertTrue(rotated.applied)
        missing = await self.store.resolve_security_session(
            SessionResolveRequest(first.session_digest, 300, 1, "resolve-old")
        )
        self.assertEqual((missing.resolved, missing.reason), (False, "not_found"))

        page = await self.store.list_security_sessions(
            SessionListRequest(limit=10, fencing_epoch=1)
        )
        self.assertEqual(
            [item.session_reference for item in page.sessions], [replacement.session_reference]
        )
        revoked = await self.store.revoke_security_sessions(
            SessionRevokeRequest(
                target=SessionRevokeTarget.REFERENCE,
                target_value=replacement.session_reference,
                fencing_epoch=1,
                operation_id="revoke-def",
            )
        )
        self.assertEqual(revoked.revoked_count, 1)
        issue_after_rotation = await self.store.issue_security_session(first)
        rotate_after_revocation = await self.store.rotate_security_session(
            SessionRotateRequest(
                current_session_digest=first.session_digest,
                replacement=replacement,
                fencing_epoch=1,
                operation_id="rotate-abc",
            )
        )
        self.assertEqual(
            (issue_after_rotation.applied, issue_after_rotation.reason),
            (False, "conflict"),
        )
        self.assertEqual(
            (rotate_after_revocation.applied, rotate_after_revocation.reason),
            (False, "not_found"),
        )

        expiring = self._issue("123", operation_id="issue-expiring")
        self.assertTrue((await self.store.issue_security_session(expiring)).applied)
        self.advance_clock(301)
        expired = await self.store.resolve_security_session(
            SessionResolveRequest(expiring.session_digest, 300, 1, "resolve-expired")
        )
        self.assertEqual((expired.resolved, expired.reason), (False, "expired"))

    async def assert_attempt_and_oidc_transaction_contract(self) -> None:
        request = AttemptReservationRequest(
            category=SecurityAttemptCategory.LOGIN,
            client_index="a" * 64,
            limit=2,
            window_seconds=300,
            fencing_epoch=1,
            operation_id="attempt-1",
        )
        first = await self.store.reserve_security_attempt(request)
        replayed = await self.store.reserve_security_attempt(request)
        second = await self.store.reserve_security_attempt(
            AttemptReservationRequest(
                category=SecurityAttemptCategory.LOGIN,
                client_index="a" * 64,
                limit=2,
                window_seconds=300,
                fencing_epoch=1,
                operation_id="attempt-2",
            )
        )
        denied = await self.store.reserve_security_attempt(
            AttemptReservationRequest(
                category=SecurityAttemptCategory.LOGIN,
                client_index="a" * 64,
                limit=2,
                window_seconds=300,
                fencing_epoch=1,
                operation_id="attempt-3",
            )
        )
        self.assertEqual((first.allowed, replayed.idempotent, second.allowed), (True, True, True))
        self.assertEqual((denied.allowed, denied.reason), (False, "limited"))
        cleared = await self.store.clear_security_attempts(
            AttemptClearRequest(
                category=SecurityAttemptCategory.LOGIN,
                client_index="a" * 64,
                fencing_epoch=1,
                operation_id="clear-attempts",
            )
        )
        self.assertTrue(cleared.cleared)
        after_clear = await self.store.reserve_security_attempt(
            AttemptReservationRequest(
                category=SecurityAttemptCategory.LOGIN,
                client_index="a" * 64,
                limit=2,
                window_seconds=300,
                fencing_epoch=1,
                operation_id="attempt-after-clear",
            )
        )
        isolated = await self.store.reserve_security_attempt(
            AttemptReservationRequest(
                category=SecurityAttemptCategory.RECOVERY,
                client_index="a" * 64,
                limit=1,
                window_seconds=300,
                fencing_epoch=1,
                operation_id="recovery-isolated",
            )
        )
        self.assertTrue(after_clear.allowed)
        self.assertTrue(isolated.allowed)

        create = OidcTransactionCreateRequest(
            state_index="b" * 64,
            browser_index="c" * 64,
            payload=b"opaque-transaction",
            ttl_seconds=300,
            fencing_epoch=1,
            operation_id="oidc-create",
        )
        self.assertTrue((await self.store.create_oidc_transaction(create)).applied)
        mismatch = await self.store.consume_oidc_transaction(
            OidcTransactionConsumeRequest(
                state_index="b" * 64,
                browser_index="d" * 64,
                fencing_epoch=1,
                operation_id="oidc-wrong-browser",
            )
        )
        consumed = await self.store.consume_oidc_transaction(
            OidcTransactionConsumeRequest(
                state_index="b" * 64,
                browser_index="c" * 64,
                fencing_epoch=1,
                operation_id="oidc-consume",
            )
        )
        replayed_consume = await self.store.consume_oidc_transaction(
            OidcTransactionConsumeRequest(
                state_index="b" * 64,
                browser_index="c" * 64,
                fencing_epoch=1,
                operation_id="oidc-consume",
            )
        )
        consumed_again = await self.store.consume_oidc_transaction(
            OidcTransactionConsumeRequest(
                state_index="b" * 64,
                browser_index="c" * 64,
                fencing_epoch=1,
                operation_id="oidc-consume-again",
            )
        )
        create_after_consume = await self.store.create_oidc_transaction(create)
        self.assertEqual((mismatch.consumed, mismatch.reason), (False, "browser_mismatch"))
        self.assertEqual((consumed.consumed, consumed.payload), (True, b"opaque-transaction"))
        self.assertEqual(
            (
                replayed_consume.consumed,
                replayed_consume.payload,
                replayed_consume.reason,
                replayed_consume.idempotent,
            ),
            (False, None, "not_found", True),
        )
        self.assertEqual((consumed_again.consumed, consumed_again.reason), (False, "not_found"))
        self.assertEqual(
            (create_after_consume.applied, create_after_consume.reason),
            (False, "conflict"),
        )

    async def assert_exact_ready_epoch_contract(self) -> None:
        await self.store.advance_epoch(1, "advance-security")
        issue = self._issue("abc")
        reconciling_issue = await self.store.issue_security_session(
            SessionIssueRequest(
                issue.session_digest,
                issue.session_reference,
                issue.principal_index,
                issue.principal_type,
                issue.payload,
                issue.idle_ttl_seconds,
                issue.absolute_ttl_seconds,
                2,
                issue.operation_id,
            )
        )
        reconciling_attempt = await self.store.reserve_security_attempt(
            AttemptReservationRequest(
                SecurityAttemptCategory.LOGIN,
                "a" * 64,
                2,
                300,
                2,
                "attempt-reconciling",
            )
        )
        self.assertEqual(reconciling_issue.reason, "reconciling")
        self.assertEqual(reconciling_attempt.reason, "reconciling")

        ready = await self.store.mark_epoch_ready(2, "ready-security")
        self.assertEqual(ready.state, EpochState.READY)
        stale_resolve = await self.store.resolve_security_session(
            SessionResolveRequest("a" * 64, 300, 1, "stale-resolve")
        )
        stale_consume = await self.store.consume_oidc_transaction(
            OidcTransactionConsumeRequest("b" * 64, "c" * 64, 1, "stale-consume")
        )
        self.assertEqual(stale_resolve.reason, "stale_epoch")
        self.assertEqual(stale_consume.reason, "stale_epoch")
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.list_security_sessions(SessionListRequest(10, 1))
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.clear_security_attempts(
                AttemptClearRequest(
                    SecurityAttemptCategory.LOGIN,
                    "a" * 64,
                    1,
                    "stale-clear",
                )
            )

    async def assert_atomic_attempt_and_consume_contract(self) -> None:
        reservations = await asyncio.gather(
            *(
                self.store.reserve_security_attempt(
                    AttemptReservationRequest(
                        SecurityAttemptCategory.LOGIN,
                        "a" * 64,
                        3,
                        300,
                        1,
                        f"concurrent-attempt-{index}",
                    )
                )
                for index in range(8)
            )
        )
        self.assertEqual(sum(decision.allowed for decision in reservations), 3)

        create = OidcTransactionCreateRequest(
            "b" * 64,
            "c" * 64,
            b"one-time-proof",
            300,
            1,
            "create-concurrent-proof",
        )
        self.assertTrue((await self.store.create_oidc_transaction(create)).applied)
        consumes = await asyncio.gather(
            *(
                self.store.consume_oidc_transaction(
                    OidcTransactionConsumeRequest(
                        create.state_index,
                        create.browser_index,
                        1,
                        f"concurrent-consume-{index}",
                    )
                )
                for index in range(8)
            )
        )
        self.assertEqual(sum(result.consumed for result in consumes), 1)

    async def assert_capacity_preserves_live_evidence_contract(
        self,
        limited_store: IdentitySecurityCoordinationStore,
    ) -> None:
        first = self._issue("abc")
        second = self._issue("def")
        self.assertTrue((await limited_store.issue_security_session(first)).applied)
        self.assertEqual(
            (await limited_store.issue_security_session(second)).reason,
            "capacity",
        )
        self.assertTrue(
            (
                await limited_store.resolve_security_session(
                    SessionResolveRequest(first.session_digest, 300, 1, "resolve-live")
                )
            ).resolved
        )

        attempt = AttemptReservationRequest(
            SecurityAttemptCategory.LOGIN,
            "a" * 64,
            2,
            300,
            1,
            "capacity-attempt-a",
        )
        self.assertTrue((await limited_store.reserve_security_attempt(attempt)).allowed)
        self.assertEqual(
            (
                await limited_store.reserve_security_attempt(
                    AttemptReservationRequest(
                        SecurityAttemptCategory.LOGIN,
                        "b" * 64,
                        2,
                        300,
                        1,
                        "capacity-attempt-b",
                    )
                )
            ).reason,
            "capacity",
        )
        retained_attempt = await limited_store.reserve_security_attempt(
            AttemptReservationRequest(
                SecurityAttemptCategory.LOGIN,
                "a" * 64,
                2,
                300,
                1,
                "capacity-attempt-a-second",
            )
        )
        self.assertEqual((retained_attempt.allowed, retained_attempt.remaining_attempts), (True, 0))

        transaction = OidcTransactionCreateRequest(
            "c" * 64,
            "d" * 64,
            b"first",
            300,
            1,
            "capacity-create-first",
        )
        self.assertTrue((await limited_store.create_oidc_transaction(transaction)).applied)
        self.assertEqual(
            (
                await limited_store.create_oidc_transaction(
                    OidcTransactionCreateRequest(
                        "e" * 64,
                        "f" * 64,
                        b"second",
                        300,
                        1,
                        "capacity-create-second",
                    )
                )
            ).reason,
            "capacity",
        )
        retained_transaction = await limited_store.consume_oidc_transaction(
            OidcTransactionConsumeRequest(
                transaction.state_index,
                transaction.browser_index,
                1,
                "capacity-consume-first",
            )
        )
        self.assertEqual(
            (retained_transaction.consumed, retained_transaction.payload),
            (True, b"first"),
        )

    async def assert_security_operations_fail_after_close(self) -> None:
        await self.store.close()
        await self.store.close()
        issue = self._issue("abc")
        replacement = self._issue("def", operation_id="close-rotate")
        operations = (
            lambda: self.store.issue_security_session(issue),
            lambda: self.store.resolve_security_session(
                SessionResolveRequest(issue.session_digest, 300, 1, "close-resolve")
            ),
            lambda: self.store.rotate_security_session(
                SessionRotateRequest(
                    issue.session_digest,
                    replacement,
                    1,
                    "close-rotate",
                )
            ),
            lambda: self.store.revoke_security_sessions(
                SessionRevokeRequest(
                    SessionRevokeTarget.DIGEST,
                    issue.session_digest,
                    1,
                    "close-revoke",
                )
            ),
            lambda: self.store.list_security_sessions(SessionListRequest(10, 1)),
            lambda: self.store.reserve_security_attempt(
                AttemptReservationRequest(
                    SecurityAttemptCategory.LOGIN,
                    "a" * 64,
                    1,
                    30,
                    1,
                    "close-reserve",
                )
            ),
            lambda: self.store.clear_security_attempts(
                AttemptClearRequest(
                    SecurityAttemptCategory.LOGIN,
                    "a" * 64,
                    1,
                    "close-clear",
                )
            ),
            lambda: self.store.create_oidc_transaction(
                OidcTransactionCreateRequest(
                    "b" * 64,
                    "c" * 64,
                    b"closed",
                    60,
                    1,
                    "close-create",
                )
            ),
            lambda: self.store.consume_oidc_transaction(
                OidcTransactionConsumeRequest(
                    "b" * 64,
                    "c" * 64,
                    1,
                    "close-consume",
                )
            ),
        )
        for operation in operations:
            with self.assertRaises(CoordinationUnavailableError):
                await operation()
