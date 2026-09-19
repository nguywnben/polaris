"""Bounded expiry recovery cannot relax session security or spin indefinitely."""

from __future__ import annotations

import asyncio
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.coordination import (
    CoordinationCorruptError,
    CoordinationReconciliationRequiredError,
    CoordinationUnavailableError,
)
from core.coordination_service import CoordinationService
from core.security_coordination import (
    SecurityPrincipalType,
    SessionIssueRequest,
    SessionListRequest,
    SessionMutationResult,
    SessionResolveRequest,
)
from core.state_store import InMemoryStateStore


class SessionExpiryMaintenanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.clock = 1_000.0
        self.store = InMemoryStateStore(clock=lambda: self.clock)
        self.request = SessionIssueRequest(
            "a" * 64,
            "ssr_" + "a" * 32,
            "b" * 64,
            SecurityPrincipalType.LOCAL_OWNER,
            b"opaque-test-payload",
            300,
            900,
            1,
            "issue",
        )

    async def asyncTearDown(self) -> None:
        await self.store.close()

    async def _backlog(self) -> None:
        await self.store.issue_security_session(self.request)
        for index in range(600):
            result = await self.store.resolve_security_session(
                SessionResolveRequest(self.request.session_digest, 300, 1, f"touch-{index}")
            )
            self.assertTrue(result.resolved)
        self.clock += 301

    async def test_each_batch_is_bounded_and_makes_progress(self) -> None:
        await self._backlog()
        before = len(self.store._security_sessions) + len(self.store._security_session_replays)
        self.assertEqual(await self.store.prune_expired_security_sessions(epoch=1), 256)
        after = len(self.store._security_sessions) + len(self.store._security_session_replays)
        self.assertEqual(before - after, 256)
        self.assertEqual(await self.store.prune_expired_security_sessions(epoch=1), 256)
        self.assertGreater(await self.store.prune_expired_security_sessions(epoch=1), 0)
        self.assertEqual(await self.store.prune_expired_security_sessions(epoch=1), 0)

    async def test_live_records_and_replay_evidence_are_preserved(self) -> None:
        first = await self.store.issue_security_session(self.request)
        self.assertEqual(await self.store.prune_expired_security_sessions(epoch=1), 0)
        replay = await self.store.issue_security_session(self.request)
        self.assertTrue(replay.idempotent)
        self.assertEqual(replay.session, first.session)

    async def test_corrupt_batch_fails_before_removing_any_record(self) -> None:
        await self._backlog()
        self.store._security_digest_by_reference.clear()
        before = dict(self.store._security_session_replays)
        with self.assertRaises(CoordinationCorruptError):
            await self.store.prune_expired_security_sessions(epoch=1)
        self.assertEqual(before, self.store._security_session_replays)
        self.assertIn(self.request.session_digest, self.store._security_sessions)

    async def test_invalid_limits_epochs_and_closed_store_fail_closed(self) -> None:
        for limit in (0, 257, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                await self.store.prune_expired_security_sessions(epoch=1, limit=limit)
        with self.assertRaises(ValueError):
            await self.store.prune_expired_security_sessions(epoch=True)
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.prune_expired_security_sessions(epoch=2)
        await self.store.close()
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.prune_expired_security_sessions(epoch=1)

    async def test_corrupt_replay_index_fails_before_removing_expired_session(self) -> None:
        await self._backlog()
        self.store._security_session_replay_expiries.positions.clear()
        with self.assertRaises(CoordinationCorruptError):
            await self.store.prune_expired_security_sessions(epoch=1)
        self.assertIn(self.request.session_digest, self.store._security_sessions)
        self.assertEqual(len(self.store._security_session_replays), 601)

    async def test_concurrent_recovery_preserves_unique_sessions(self) -> None:
        await self._backlog()
        service = CoordinationService(self.store)
        requests = [
            replace(
                self.request,
                session_digest=f"{index:064x}",
                session_reference=f"ssr_{index:032x}",
                operation_id=f"new-{index}",
            )
            for index in range(8)
        ]
        results = await asyncio.gather(*(service.issue_security_session(r) for r in requests))
        self.assertTrue(all(result.applied for result in results))
        self.assertEqual(set(self.store._security_sessions), {r.session_digest for r in requests})

    async def test_no_progress_returns_original_denial(self) -> None:
        denied = SessionMutationResult(False, None, "reconciliation_required")
        self.store.issue_security_session = AsyncMock(return_value=denied)
        self.store.prune_expired_security_sessions = AsyncMock(return_value=0)
        result = await CoordinationService(self.store).issue_security_session(self.request)
        self.assertIs(result, denied)
        self.store.issue_security_session.assert_awaited_once_with(self.request)

    async def test_non_expiry_reconciliation_exception_is_preserved(self) -> None:
        error = CoordinationReconciliationRequiredError("test")
        self.store.list_security_sessions = AsyncMock(side_effect=error)
        self.store.prune_expired_security_sessions = AsyncMock(return_value=0)
        with self.assertRaises(CoordinationReconciliationRequiredError) as caught:
            await CoordinationService(self.store).list_security_sessions(SessionListRequest(10, 1))
        self.assertIs(caught.exception, error)

    async def test_recovery_has_hard_retry_bound_and_reuses_request(self) -> None:
        denied = SessionMutationResult(False, None, "reconciliation_required")
        self.store.issue_security_session = AsyncMock(return_value=denied)
        self.store.prune_expired_security_sessions = AsyncMock(return_value=256)
        with patch("core.coordination_service._MAX_SESSION_MAINTENANCE_BATCHES", 2):
            result = await CoordinationService(self.store).issue_security_session(self.request)
        self.assertIs(result, denied)
        self.assertEqual(self.store.issue_security_session.await_count, 3)
        self.assertEqual(self.store.prune_expired_security_sessions.await_count, 2)
        for call in self.store.issue_security_session.await_args_list:
            self.assertIs(call.args[0], self.request)

    async def test_cancellation_between_batches_never_issues_session(self) -> None:
        await self._backlog()
        service = CoordinationService(self.store)
        task = asyncio.create_task(service.issue_security_session(self.request))
        # Recovery's yield lets cancellation interrupt between maintenance and retry.
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertNotIn(self.request.session_digest, self.store._security_sessions)


if __name__ == "__main__":
    unittest.main()
