"""Tests for the selected CoordinationStore lifecycle and evidence boundary."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.coordination import (
    CasRequest,
    CoordinationCorruptError,
    CoordinationReconciliationRequiredError,
    CoordinationUnavailableError,
    Epoch,
    EpochState,
    QuotaCommitRequest,
    QuotaCommitResult,
)
from core.coordination_service import (
    CoordinationService,
    clear_coordination_operation_metrics_for_testing,
    render_coordination_operation_metrics,
)
from core.security_coordination import (
    AttemptReservationRequest,
    SecurityAttemptCategory,
)
from core.state_store import InMemoryStateStore


class _UnavailableStore:
    async def read_epoch(self):
        raise CoordinationUnavailableError("backend://person:secret@example.invalid/state")

    async def close(self):
        return None


class _CorruptStore:
    async def read_epoch(self):
        raise CoordinationCorruptError("secret stored value")

    async def close(self):
        return None


class _RecoveringStore:
    def __init__(self) -> None:
        self.fail = True
        self.close_calls = 0

    async def read_epoch(self):
        if self.fail:
            self.fail = False
            raise CoordinationReconciliationRequiredError("must not be rendered")
        return Epoch(1, EpochState.READY)

    async def close(self):
        self.close_calls += 1


class _RejectedQuotaCommitStore:
    async def commit_quota(self, _request):
        return QuotaCommitResult(False)

    async def close(self):
        return None


class _ControlledCloseStore:
    def __init__(self) -> None:
        self.close_calls = 0
        self.close_started = asyncio.Event()
        self.allow_close = asyncio.Event()
        self.fail_close = False

    async def close(self) -> None:
        self.close_calls += 1
        self.close_started.set()
        await self.allow_close.wait()
        if self.fail_close:
            raise RuntimeError("close failure")

    async def read_epoch(self) -> Epoch:
        return Epoch(1, EpochState.READY)


class CoordinationServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        clear_coordination_operation_metrics_for_testing()

    async def test_backend_is_classified_from_a_closed_allowlist(self) -> None:
        self.assertEqual(
            CoordinationService(InMemoryStateStore()).health_snapshot()["backend"], "in_memory"
        )
        self.assertEqual(
            CoordinationService(_RecoveringStore()).health_snapshot()["backend"], "unknown"
        )

    async def test_result_labels_are_bounded_and_content_free(self) -> None:
        secret = "tenant/acme?token=top-secret"
        service = CoordinationService(InMemoryStateStore())
        applied = await service.compare_and_set(CasRequest(secret, 0, b"payload", 1.0, 1, secret))
        snapshot = await service.read_cas(secret, epoch=1)
        rejected = await service.compare_and_set(
            CasRequest(secret, 0, b"other", 1.0, 1, "other-op")
        )

        self.assertTrue(applied.applied)
        self.assertEqual(snapshot.payload, b"payload")
        self.assertFalse(rejected.applied)
        output = render_coordination_operation_metrics()
        self.assertIn('operation="compare_and_set",result="success"', output)
        self.assertIn('operation="read_cas",result="success"', output)
        self.assertIn('operation="compare_and_set",result="rejected"', output)
        self.assertNotIn(secret, output)
        self.assertNotIn("payload", output)

    async def test_stale_quota_commit_is_rejected_not_success(self) -> None:
        service = CoordinationService(_RejectedQuotaCommitStore())

        result = await service.commit_quota(QuotaCommitRequest("stale", 1.0, None, None, False))

        self.assertFalse(result.committed)
        output = render_coordination_operation_metrics()
        self.assertIn('operation="commit_quota",result="rejected"', output)
        self.assertNotIn('operation="commit_quota",result="success"', output)

    async def test_security_operation_metrics_are_bounded_and_secret_free(self) -> None:
        service = CoordinationService(InMemoryStateStore())
        client_index = "a" * 64
        allowed = await service.reserve_security_attempt(
            AttemptReservationRequest(
                SecurityAttemptCategory.LOGIN,
                client_index,
                1,
                300,
                1,
                "security-metric-allowed",
            )
        )
        denied = await service.reserve_security_attempt(
            AttemptReservationRequest(
                SecurityAttemptCategory.LOGIN,
                client_index,
                1,
                300,
                1,
                "security-metric-denied",
            )
        )

        self.assertTrue(allowed.allowed)
        self.assertFalse(denied.allowed)
        output = render_coordination_operation_metrics()
        self.assertIn('operation="reserve_security_attempt",result="success"', output)
        self.assertIn('operation="reserve_security_attempt",result="rejected"', output)
        self.assertNotIn(client_index, output)

    async def test_failure_categories_are_fixed_and_recovery_is_recorded(self) -> None:
        service = CoordinationService(_RecoveringStore())
        with self.assertRaises(CoordinationReconciliationRequiredError):
            await service.read_epoch()
        failed = service.health_snapshot()
        self.assertFalse(failed["available"])
        self.assertEqual(failed["last_error_category"], "reconciliation_required")

        await service.read_epoch()
        recovered = service.health_snapshot()
        self.assertTrue(recovered["available"])
        self.assertIsNotNone(recovered["recovered_at"])
        output = render_coordination_operation_metrics()
        self.assertIn('operation="read_epoch",result="reconciliation_required"', output)
        self.assertIn('operation="read_epoch",result="success"', output)

    async def test_unavailable_and_corrupt_errors_do_not_expose_error_text(self) -> None:
        for store, category in ((_UnavailableStore(), "unavailable"), (_CorruptStore(), "corrupt")):
            with self.subTest(category=category):
                service = CoordinationService(store)
                with self.assertRaises((CoordinationUnavailableError, CoordinationCorruptError)):
                    await service.read_epoch()
                snapshot = service.health_snapshot()
                self.assertEqual(snapshot["last_error_category"], category)
                self.assertNotIn("secret", repr(snapshot))

    async def test_concurrent_close_is_cancellation_safe_and_later_close_is_idempotent(
        self,
    ) -> None:
        store = _ControlledCloseStore()
        service = CoordinationService(store)
        cancelled_waiter = asyncio.create_task(service.close())
        await store.close_started.wait()
        successful_waiter = asyncio.create_task(service.close())
        await asyncio.sleep(0)

        cancelled_waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await cancelled_waiter
        self.assertEqual(store.close_calls, 1)
        with self.assertRaises(CoordinationUnavailableError):
            await service.read_epoch()

        store.allow_close.set()
        await successful_waiter
        await service.close()

        self.assertEqual(store.close_calls, 1)
        self.assertTrue(service.health_snapshot()["closed"])
        output = render_coordination_operation_metrics()
        self.assertEqual(output.count('operation="close",result="success"'), 1)
        self.assertEqual(output.count('operation="close",result="idempotent"'), 1)

    async def test_close_failure_is_shared_and_retry_can_close_without_false_success_health(
        self,
    ) -> None:
        store = _ControlledCloseStore()
        store.fail_close = True
        service = CoordinationService(store)
        first = asyncio.create_task(service.close())
        await store.close_started.wait()
        second = asyncio.create_task(service.close())
        await asyncio.sleep(0)
        store.allow_close.set()

        outcomes = await asyncio.gather(first, second, return_exceptions=True)
        self.assertEqual([type(outcome) for outcome in outcomes], [RuntimeError, RuntimeError])
        failed = service.health_snapshot()
        self.assertFalse(failed["closed"])
        self.assertFalse(failed["available"])
        self.assertEqual(failed["last_error_category"], "unexpected")
        output = render_coordination_operation_metrics()
        self.assertEqual(output.count('operation="close",result="unexpected"'), 1)
        self.assertNotIn('operation="close",result="success"', output)

        store.fail_close = False
        await service.close()

        recovered = service.health_snapshot()
        self.assertTrue(recovered["closed"])
        self.assertTrue(recovered["available"])
        self.assertIsNotNone(recovered["recovered_at"])
        self.assertEqual(store.close_calls, 2)

    def test_empty_renderer_still_has_help_and_type(self) -> None:
        self.assertEqual(
            render_coordination_operation_metrics(),
            "# HELP polaris_coordination_operations_total Coordination store operations.\n"
            "# TYPE polaris_coordination_operations_total counter\n",
        )


if __name__ == "__main__":
    unittest.main()
