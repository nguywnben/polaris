"""Atomic quota-reservation contract for W3.7."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.coordination import QuotaCommitRequest as CanonicalQuotaCommitRequest
from core.coordination import QuotaReservationRequest as CanonicalQuotaReservationRequest
from core.state_store import (
    InMemoryStateStore,
    QuotaCommitRequest,
    QuotaReservationRequest,
)


def _reservation(reservation_id: str, **overrides) -> QuotaReservationRequest:
    values = {
        "reservation_id": reservation_id,
        "key_id": "vk_customer",
        "now": 1_000.0,
        "ttl_seconds": 900.0,
        "estimated_tokens": 100,
        "estimated_cost_usd": 0.1,
        "rpm_limit": None,
        "tpm_limit": None,
        "daily_budget_usd": None,
        "monthly_budget_usd": None,
        "daily_spend_usd": 0.0,
        "monthly_spend_usd": 0.0,
        "daily_snapshot_started_at": 1_000.0,
        "monthly_snapshot_started_at": 1_000.0,
    }
    values.update(overrides)
    return QuotaReservationRequest(**values)


class AtomicQuotaReservationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.coordination_now = 1_000.0
        self.store = InMemoryStateStore(clock=lambda: self.coordination_now)

    async def test_concurrent_rpm_reservations_admit_only_one_request(self):
        first, second = await asyncio.gather(
            self.store.reserve_quota(_reservation("res_a", rpm_limit=1)),
            self.store.reserve_quota(_reservation("res_b", rpm_limit=1)),
        )

        self.assertEqual(sum(decision.accepted for decision in (first, second)), 1)
        rejected = first if not first.accepted else second
        self.assertEqual(rejected.reason, "rpm")
        self.assertGreaterEqual(rejected.retry_after_seconds, 1)

    async def test_release_is_idempotent_and_returns_capacity(self):
        accepted = await self.store.reserve_quota(_reservation("res_a", rpm_limit=1))
        released = await self.store.release_quota("res_a", now=1_001.0)
        released_again = await self.store.release_quota("res_a", now=1_001.0)
        replacement = await self.store.reserve_quota(
            _reservation("res_b", now=1_001.0, rpm_limit=1)
        )

        self.assertTrue(accepted.accepted)
        self.assertTrue(released)
        self.assertFalse(released_again)
        self.assertTrue(replacement.accepted)

    async def test_committed_actual_tokens_remain_in_the_sliding_window(self):
        accepted = await self.store.reserve_quota(
            _reservation("res_a", estimated_tokens=200, tpm_limit=1_000)
        )
        committed = await self.store.commit_quota(
            QuotaCommitRequest(
                reservation_id="res_a",
                now=1_001.0,
                actual_tokens=900,
                actual_cost_usd=0.0,
                durable_cost_recorded=True,
            )
        )
        rejected = await self.store.reserve_quota(
            _reservation("res_b", now=1_002.0, estimated_tokens=200, tpm_limit=1_000)
        )
        self.coordination_now = 1_062.0
        after_window = await self.store.reserve_quota(
            _reservation("res_c", now=1_062.0, estimated_tokens=200, tpm_limit=1_000)
        )

        self.assertTrue(accepted.accepted)
        self.assertTrue(committed.committed)
        self.assertEqual(rejected.reason, "tpm")
        self.assertTrue(after_window.accepted)

    async def test_coordination_does_not_own_budget_admission(self):
        first, second = await asyncio.gather(
            self.store.reserve_quota(
                _reservation("res_a", estimated_cost_usd=0.6, daily_budget_usd=1.0)
            ),
            self.store.reserve_quota(
                _reservation("res_b", estimated_cost_usd=0.6, daily_budget_usd=1.0)
            ),
        )

        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)

    async def test_legacy_budget_snapshots_do_not_affect_rate_admission(self):
        await self.store.reserve_quota(
            _reservation("res_a", estimated_cost_usd=0.4, daily_budget_usd=1.0)
        )
        await self.store.commit_quota(
            QuotaCommitRequest(
                reservation_id="res_a",
                now=1_001.0,
                actual_tokens=100,
                actual_cost_usd=0.4,
                durable_cost_recorded=True,
            )
        )

        decision = await self.store.reserve_quota(
            _reservation(
                "res_b",
                now=1_002.0,
                estimated_cost_usd=0.6,
                daily_budget_usd=1.0,
                daily_spend_usd=0.4,
                daily_snapshot_started_at=1_001.5,
            )
        )

        self.assertTrue(decision.accepted)

    async def test_snapshot_age_does_not_affect_rate_admission(self):
        await self.store.reserve_quota(
            _reservation("res_a", estimated_cost_usd=0.7, daily_budget_usd=1.0)
        )
        await self.store.commit_quota(
            QuotaCommitRequest(
                reservation_id="res_a",
                now=1_001.0,
                actual_tokens=100,
                actual_cost_usd=0.7,
                durable_cost_recorded=True,
            )
        )

        decision = await self.store.reserve_quota(
            _reservation(
                "res_b",
                now=1_002.0,
                estimated_cost_usd=0.4,
                daily_budget_usd=1.0,
                daily_spend_usd=0.0,
                daily_snapshot_started_at=1_000.5,
            )
        )

        self.assertTrue(decision.accepted)

    async def test_expired_reservation_is_reconciled(self):
        await self.store.reserve_quota(_reservation("res_a", rpm_limit=1, ttl_seconds=61.0))

        self.coordination_now = 1_062.0
        decision = await self.store.reserve_quota(_reservation("res_b", now=1_062.0, rpm_limit=1))

        self.assertTrue(decision.accepted)

    async def test_same_reservation_id_is_idempotent(self):
        first = await self.store.reserve_quota(_reservation("res_same", rpm_limit=1))
        repeated = await self.store.reserve_quota(_reservation("res_same", rpm_limit=1))

        self.assertTrue(first.accepted)
        self.assertTrue(repeated.accepted)
        self.assertTrue(repeated.idempotent)

    async def test_same_reservation_id_with_changed_request_conflicts(self):
        first = await self.store.reserve_quota(_reservation("res_same", estimated_tokens=100))
        changed = await self.store.reserve_quota(_reservation("res_same", estimated_tokens=101))

        self.assertTrue(first.accepted)
        self.assertFalse(changed.accepted)
        self.assertEqual(changed.reason, "conflict")

    def test_quota_request_imports_remain_compatible_aliases(self):
        self.assertIs(QuotaReservationRequest, CanonicalQuotaReservationRequest)
        self.assertIs(QuotaCommitRequest, CanonicalQuotaCommitRequest)

    async def test_commit_reports_only_tpm_overspend(self):
        await self.store.reserve_quota(
            _reservation(
                "res_a",
                estimated_tokens=1,
                estimated_cost_usd=0.4,
                tpm_limit=5,
                daily_budget_usd=1.0,
            )
        )

        result = await self.store.commit_quota(
            QuotaCommitRequest(
                reservation_id="res_a",
                now=1_001.0,
                actual_tokens=6,
                actual_cost_usd=1.1,
                durable_cost_recorded=True,
            )
        )

        self.assertTrue(result.committed)
        self.assertTrue(result.overspent)

    async def test_rate_windows_are_isolated_to_the_target_key(self):
        await self.store.reserve_quota(
            _reservation("first-key-request", key_id="vk_first", rpm_limit=1)
        )
        other_key = await self.store.reserve_quota(
            _reservation(
                "other-key-request",
                key_id="vk_other",
                rpm_limit=1,
            )
        )
        same_key = await self.store.reserve_quota(
            _reservation("same-key-request", key_id="vk_first", rpm_limit=1)
        )

        self.assertTrue(other_key.accepted)
        self.assertEqual(same_key.reason, "rpm")


if __name__ == "__main__":
    unittest.main()
