"""Behavioral tests for the in-process coordination reference."""

from __future__ import annotations

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

from coordination_store_contract import CoordinationStoreContract
from core.coordination import (
    CasRequest,
    CoordinationCorruptError,
    CoordinationReconciliationRequiredError,
    Epoch,
    EpochState,
    InvalidationRequest,
)
from core.state_store import InMemoryStateStore, QuotaCommitRequest, QuotaReservationRequest


class _Clock:
    def __init__(self) -> None:
        self.value = 1_000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _reservation(reservation_id: str, **overrides: object) -> QuotaReservationRequest:
    values: dict[str, object] = {
        "reservation_id": reservation_id,
        "key_id": "virtual-key",
        "now": 1_000.0,
        "ttl_seconds": 61.0,
        "estimated_tokens": 1,
        "estimated_cost_usd": 0.0,
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
    return QuotaReservationRequest(**values)  # type: ignore[arg-type]


class InMemoryCoordinationTests(CoordinationStoreContract, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.clock = _Clock()
        self.store = InMemoryStateStore(clock=self.clock)

    async def test_shared_coordination_contract(self) -> None:
        async def advance(seconds: float) -> None:
            self.clock.advance(seconds)

        await self.assert_epoch_cas_and_invalidation_contract(advance_cas_clock=advance)

    async def test_admission_fence_all_families(self) -> None:
        await self.assert_admission_fence_contract()

    async def test_admission_fence_linearization_and_settlement(self) -> None:
        await self.assert_fence_linearization_and_settlement_contract()

    async def test_device_authorization_settlement_during_drain(self) -> None:
        async def advance(seconds: float) -> None:
            self.clock.advance(seconds)

        await self.assert_device_authorization_settlement_contract(advance_device_clock=advance)

    async def test_cas_settlement_requires_accepted_proof(self) -> None:
        await self.assert_cas_settlement_proof_contract()

    async def test_cas_settlement_proof_rejects_cross_key_and_wrong_transition_reuse(
        self,
    ) -> None:
        await self.assert_cas_settlement_proof_cannot_be_reused_for_other_work()

    async def test_unknown_settlement_does_not_admit_replays(self) -> None:
        async def retained_count() -> int:
            return len(self.store._quota_replays) + len(self.store._oidc_transaction_replays)

        await self.assert_unknown_settlement_does_not_admit_replays(retained_count)

    async def test_batch_settlement_during_drain(self) -> None:
        await self.assert_batch_settlement_during_drain_contract()

    async def test_batch_partial_settlement_retry(self) -> None:
        await self.assert_batch_partial_settlement_retry_contract()

    async def test_drain_allows_expiry_but_rejects_expired_cas_proof(self) -> None:
        from core.coordination import (
            CasSettlementProof,
            CasSettlementTarget,
            CasSettlementTransition,
            CoordinationUnavailableError,
        )

        target = CasSettlementTarget("expiring-proof", CasSettlementTransition.UPDATE)
        admission = CasRequest(
            "expiring-proof",
            0,
            b"value",
            61,
            1,
            "expiring-admit",
            settlement_targets=(target,),
        )
        await self.store.compare_and_set(admission)
        await self.store.reserve_quota(_reservation("expire-during-drain"))
        await self.install_admission_fence()
        self.clock.advance(62)
        self.assertFalse(await self.store.release_quota("expire-during-drain", now=1_062))
        self.assertFalse(await self.store.release_quota("expire-during-drain", now=1_062))
        with self.assertRaises(CoordinationUnavailableError):
            await self.store.compare_and_set(
                CasRequest(
                    "expiring-proof",
                    1,
                    b"settled",
                    61,
                    1,
                    "expired-settle",
                    settlement=CasSettlementProof(admission, target),
                )
            )

    async def test_settlement_replay_outlives_its_admission_proof(self) -> None:
        async def advance(seconds: float) -> None:
            self.clock.advance(seconds)

        await self.assert_settlement_replay_after_proof_expiry(advance)

    async def test_expired_oidc_consume_during_drain_does_not_create_replay(self) -> None:
        from core.security_coordination import (
            OidcTransactionConsumeRequest,
            OidcTransactionCreateRequest,
        )

        await self.store.create_oidc_transaction(
            OidcTransactionCreateRequest("a" * 64, "b" * 64, b"expired", 60, 1, "expiring-oidc")
        )
        await self.install_admission_fence()
        self.clock.advance(61)
        request = OidcTransactionConsumeRequest("a" * 64, "b" * 64, 1, "expired-consume")
        self.assertEqual((await self.store.consume_oidc_transaction(request)).reason, "expired")
        self.assertFalse((await self.store.consume_oidc_transaction(request)).idempotent)
        self.assertEqual(self.store._oidc_transactions, {})
        self.assertEqual(self.store._oidc_transaction_replays, {})

    async def test_corrupt_fence_blocks_settlement(self) -> None:
        await self.assert_corrupt_fence_blocks_settlement_contract()

    async def test_ambiguous_fence_json_blocks_settlement(self) -> None:
        await self.assert_ambiguous_fence_json_blocks_settlement()

    async def test_drain_completion_identity(self) -> None:
        await self.assert_drain_completion_identity_contract()

    async def test_admission_fence_invalid_state_fails_closed(self) -> None:
        from core.coordination import CoordinationCorruptError

        for changes in (
            {"epoch": 2},
            {"namespace_digest": "f" * 64},
            {"epoch": True},
            {"schema_version": 2},
            {"unexpected": "value"},
        ):
            with self.subTest(changes=changes):
                await self.install_admission_fence(**changes)
                with self.assertRaises(CoordinationCorruptError):
                    await self.store.reserve_quota(_reservation("corrupt-fence"))

    async def test_corrupt_binding_schema_and_duplicate_fields_fail_closed(self) -> None:
        import json

        from core.coordination import CoordinationCorruptError

        await self.install_admission_fence()
        binding = json.loads(await self.store.get("ha-runtime-binding-v1"))
        for encoded in (
            json.dumps({**binding, "schema_version": True}),
            json.dumps({**binding, "schema_version": 1.0}),
            '{"schema_version":0,' + json.dumps(binding)[1:],
        ):
            with self.subTest(encoded=encoded):
                await self.store.set("ha-runtime-binding-v1", encoded)
                with self.assertRaises(CoordinationCorruptError):
                    await self.store.release_quota("unknown", now=1_001)

    async def test_shared_quota_contract(self) -> None:
        self.store = InMemoryStateStore(clock=self.clock, _quota_record_limit_for_testing=2)

        async def advance(seconds: float) -> None:
            self.clock.advance(seconds)

        await self.assert_quota_lifecycle_replay_expiry_and_capacity_contract(
            advance_quota_clock=advance
        )

    async def test_quota_mutations_require_the_exact_ready_epoch(self) -> None:
        advanced = await self.store.advance_epoch(1, "advance")
        self.assertEqual(advanced.state, EpochState.RECONCILING)

        reconciling = await self.store.reserve_quota(_reservation("reconciling", fencing_epoch=2))
        self.assertFalse(reconciling.accepted)
        self.assertEqual(reconciling.reason, "reconciling")

        await self.store.mark_epoch_ready(2, "ready")
        stale = await self.store.reserve_quota(_reservation("stale", fencing_epoch=1))
        self.assertFalse(stale.accepted)
        self.assertEqual(stale.reason, "stale_epoch")

        accepted = await self.store.reserve_quota(_reservation("ready", fencing_epoch=2))
        self.assertTrue(accepted.accepted)

    async def test_quota_window_includes_the_complete_boundary_second(self) -> None:
        self.clock.value = 1_000.9
        first = await self.store.reserve_quota(
            _reservation("boundary-first", now=1_000.9, rpm_limit=1)
        )
        self.clock.advance(60.0)

        denied = await self.store.reserve_quota(
            _reservation("boundary-second", now=1_060.9, rpm_limit=1)
        )

        self.assertTrue(first.accepted)
        self.assertEqual(denied.reason, "rpm")

    async def test_quota_coordination_ignores_legacy_budget_inputs(self) -> None:
        decision = await self.store.reserve_quota(
            _reservation(
                "rate-only",
                estimated_cost_usd=10.0,
                daily_budget_usd=0.0,
                monthly_budget_usd=0.0,
            )
        )

        self.assertTrue(decision.accepted)

    async def test_quota_coordination_time_comes_only_from_the_store_clock(self) -> None:
        with self.subTest(path="forward-dated-reserve"):
            store = InMemoryStateStore(clock=self.clock)
            self.assertTrue(
                (
                    await store.reserve_quota(_reservation("holder", now=1_000_000.0, rpm_limit=1))
                ).accepted
            )
            denied = await store.reserve_quota(_reservation("second", now=2_000_000.0, rpm_limit=1))
            self.assertEqual(denied.reason, "rpm")
            holder = store._quota_records["holder"]
            self.assertEqual((holder.accepted_at, holder.active_expires_at), (1_000.0, 1_061.0))

        with self.subTest(path="backdated-reserve"):
            clock = _Clock()
            store = InMemoryStateStore(clock=clock)
            self.assertTrue(
                (
                    await store.reserve_quota(_reservation("holder", now=1_000_000.0, rpm_limit=1))
                ).accepted
            )
            clock.advance(62.0)
            accepted = await store.reserve_quota(
                _reservation(
                    "second",
                    now=0.0,
                    rpm_limit=1,
                    daily_snapshot_started_at=0.0,
                    monthly_snapshot_started_at=0.0,
                )
            )
            self.assertTrue(accepted.accepted)

        for operation in ("commit", "release"):
            with self.subTest(path=f"expired-{operation}"):
                clock = _Clock()
                store = InMemoryStateStore(clock=clock)
                self.assertTrue(
                    (await store.reserve_quota(_reservation("expired", now=1_000_000.0))).accepted
                )
                clock.advance(62.0)
                if operation == "commit":
                    result = await store.commit_quota(
                        QuotaCommitRequest("expired", 0.0, 1, 0.0, False)
                    )
                    self.assertFalse(result.committed)
                else:
                    self.assertFalse(await store.release_quota("expired", now=0.0))

    async def test_stale_reserve_does_not_mutate_rate_state(self) -> None:
        accepted = await self.store.reserve_quota(_reservation("committed", ttl_seconds=61.0))
        self.assertTrue(accepted.accepted)
        self.assertTrue(
            (
                await self.store.commit_quota(
                    QuotaCommitRequest("committed", 1_001.0, 1, 0.1, True)
                )
            ).committed
        )
        before = self.store._quota_rate_windows["virtual-key"].totals(self.clock.value)
        await self.store.advance_epoch(1, "advance-for-stale")

        denied = await self.store.reserve_quota(
            _reservation(
                "stale",
                now=2_000.0,
                fencing_epoch=1,
                daily_snapshot_started_at=2_000.0,
            )
        )

        self.assertFalse(denied.accepted)
        self.assertEqual(
            self.store._quota_rate_windows["virtual-key"].totals(self.clock.value), before
        )

    async def test_quota_replay_with_changed_payload_conflicts(self) -> None:
        first = await self.store.reserve_quota(_reservation("same", fencing_epoch=1))
        replay = await self.store.reserve_quota(_reservation("same", fencing_epoch=1))
        conflict = await self.store.reserve_quota(
            _reservation("same", fencing_epoch=1, estimated_tokens=2)
        )

        self.assertTrue(first.accepted)
        self.assertTrue(replay.idempotent)
        self.assertFalse(conflict.accepted)
        self.assertEqual(conflict.reason, "conflict")

    async def test_quota_commit_and_release_are_fenced_and_replay_safe(self) -> None:
        await self.store.advance_epoch(1, "advance")
        await self.store.mark_epoch_ready(2, "ready")
        self.assertTrue(
            (
                await self.store.reserve_quota(
                    _reservation("reservation", fencing_epoch=2, ttl_seconds=61.0)
                )
            ).accepted
        )
        committed = await self.store.commit_quota(
            QuotaCommitRequest("reservation", 1_001.0, 2, 0.0, True, 2, "commit")
        )
        replay = await self.store.commit_quota(
            QuotaCommitRequest("reservation", 1_001.0, 2, 0.0, True, 2, "commit")
        )
        conflict = await self.store.commit_quota(
            QuotaCommitRequest("reservation", 1_003.0, 3, 0.0, True, 2, "commit")
        )
        self.assertTrue(
            (
                await self.store.reserve_quota(
                    _reservation("active-release", fencing_epoch=2, ttl_seconds=61.0)
                )
            ).accepted
        )
        await self.store.advance_epoch(2, "advance-again")
        stale_release = await self.store.release_quota(
            "active-release", now=1_004.0, fencing_epoch=2
        )
        await self.store.mark_epoch_ready(3, "ready-again")
        still_active = await self.store.release_quota(
            "active-release", now=1_004.0, fencing_epoch=3
        )

        self.assertTrue(committed.committed)
        self.assertTrue(replay.idempotent)
        self.assertFalse(conflict.committed)
        self.assertFalse(stale_release)
        self.assertTrue(still_active)

    async def test_commit_changed_time_is_a_conflict_but_exact_time_replays(self) -> None:
        self.assertTrue(
            (await self.store.reserve_quota(_reservation("commit-time", ttl_seconds=61.0))).accepted
        )
        request = QuotaCommitRequest("commit-time", 1_001.0, 2, 0.0, True, 1, "commit-time-op")
        committed = await self.store.commit_quota(request)
        replay = await self.store.commit_quota(request)
        changed_time = await self.store.commit_quota(
            QuotaCommitRequest("commit-time", 1_002.0, 2, 0.0, True, 1, "commit-time-op")
        )

        record = self.store._quota_records["commit-time"]
        assert record.committed is not None
        self.assertTrue(committed.committed)
        self.assertTrue(replay.committed)
        self.assertTrue(replay.idempotent)
        self.assertFalse(changed_time.committed)
        self.assertFalse(changed_time.idempotent)
        self.assertEqual(
            (record.committed.committed_at, record.committed.business_committed_at),
            (1_000.0, 1_001.0),
        )

    async def test_future_snapshot_is_rejected_before_rate_state_changes(self) -> None:
        self.assertTrue(
            (
                await self.store.reserve_quota(
                    _reservation(
                        "snapshot-evidence",
                        ttl_seconds=61.0,
                        daily_budget_usd=1.0,
                        monthly_budget_usd=1.0,
                    )
                )
            ).accepted
        )
        self.assertTrue(
            (
                await self.store.commit_quota(
                    QuotaCommitRequest(
                        "snapshot-evidence", 1_001.0, 1, 0.1, True, 1, "commit-snapshot"
                    )
                )
            ).committed
        )
        before = self.store._quota_rate_windows["virtual-key"].totals(self.clock.value)

        with self.assertRaises(ValueError):
            await self.store.reserve_quota(
                _reservation(
                    "future-snapshot",
                    now=1_002.0,
                    daily_snapshot_started_at=1_003.0,
                    monthly_snapshot_started_at=1_003.0,
                )
            )

        self.assertEqual(
            self.store._quota_rate_windows["virtual-key"].totals(self.clock.value), before
        )

    async def test_ready_denied_cas_replays_until_its_ttl_without_flipping(self) -> None:
        self.assertTrue(
            (
                await self.store.compare_and_set(
                    CasRequest("denied-cas", 0, b"initial", 1.0, 1, "create")
                )
            ).applied
        )
        denied_request = CasRequest("denied-cas", 0, b"denied", 10.0, 1, "denied")
        self.assertFalse((await self.store.compare_and_set(denied_request)).applied)

        self.clock.advance(2.0)
        replay = await self.store.compare_and_set(denied_request)
        conflict = await self.store.compare_and_set(
            CasRequest("denied-cas", 0, b"changed", 10.0, 1, "denied")
        )

        self.assertFalse(replay.applied)
        self.assertTrue(replay.idempotent)
        self.assertFalse(conflict.applied)

        self.clock.advance(8.1)
        after_replay_expiry = await self.store.compare_and_set(denied_request)
        self.assertTrue(after_replay_expiry.applied)
        self.assertFalse(after_replay_expiry.idempotent)

    async def test_ready_denied_reserve_replays_after_capacity_changes(self) -> None:
        self.assertTrue(
            (await self.store.reserve_quota(_reservation("holder", rpm_limit=1))).accepted
        )
        denied_request = _reservation("denied", ttl_seconds=61.0, rpm_limit=1)
        denied = await self.store.reserve_quota(denied_request)
        self.assertEqual(denied.reason, "rpm")
        self.assertTrue(await self.store.release_quota("holder", now=1_000.5))

        replay = await self.store.reserve_quota(denied_request)
        conflict = await self.store.reserve_quota(
            _reservation("denied", ttl_seconds=61.0, rpm_limit=1, estimated_tokens=2)
        )

        self.assertEqual(replay.reason, "rpm")
        self.assertTrue(replay.idempotent)
        self.assertEqual(conflict.reason, "conflict")

    async def test_accepted_id_cannot_reactivate_until_expired_tombstone_is_pruned(self) -> None:
        original = _reservation("expires", ttl_seconds=61.0)
        self.assertTrue((await self.store.reserve_quota(original)).accepted)

        exact_replay = await self.store.reserve_quota(original)
        changed_during_retention = await self.store.reserve_quota(
            _reservation("expires", now=1_002.0, ttl_seconds=61.0)
        )

        self.assertTrue(exact_replay.accepted)
        self.assertTrue(exact_replay.idempotent)
        self.assertEqual(changed_during_retention.reason, "conflict")

        self.clock.advance(62.0)
        after_retention = await self.store.reserve_quota(
            _reservation("expires", now=1_062.0, ttl_seconds=61.0)
        )
        self.assertTrue(after_retention.accepted)

    async def test_released_and_committed_ids_remain_tombstoned_until_retention(self) -> None:
        self.assertTrue(
            (await self.store.reserve_quota(_reservation("released", ttl_seconds=61.0))).accepted
        )
        self.assertTrue(await self.store.release_quota("released", now=1_001.0))
        self.assertEqual(
            (
                await self.store.reserve_quota(
                    _reservation("released", now=1_002.0, ttl_seconds=61.0)
                )
            ).reason,
            "conflict",
        )

        self.clock.advance(62.0)
        self.assertTrue(
            (await self.store.reserve_quota(_reservation("committed", ttl_seconds=61.0))).accepted
        )
        self.assertTrue(
            (
                await self.store.commit_quota(
                    QuotaCommitRequest("committed", 1_001.0, 1, 0.0, True, 1, "commit")
                )
            ).committed
        )
        self.assertEqual(
            (
                await self.store.reserve_quota(
                    _reservation("committed", now=1_002.0, ttl_seconds=61.0)
                )
            ).reason,
            "conflict",
        )

        self.clock.advance(62.0)
        self.assertTrue(
            (
                await self.store.reserve_quota(
                    _reservation("released", now=1_062.0, ttl_seconds=61.0)
                )
            ).accepted
        )
        self.assertTrue(
            (
                await self.store.reserve_quota(
                    _reservation("committed", now=1_062.0, ttl_seconds=61.0)
                )
            ).accepted
        )

    async def test_terminal_records_count_toward_capacity_without_cross_key_leakage(self) -> None:
        store = InMemoryStateStore(
            clock=self.clock,
            _quota_record_limit_for_testing=1,
            _quota_replay_limit_for_testing=4,
        )
        self.assertTrue((await store.reserve_quota(_reservation("first", key_id="key-a"))).accepted)
        self.assertTrue(await store.release_quota("first", now=1_000.5))

        retained_capacity = await store.reserve_quota(
            _reservation("same-key", key_id="key-a", now=1_002.0)
        )
        other_key = await store.reserve_quota(
            _reservation("other-key", key_id="key-b", now=1_002.0)
        )

        self.assertEqual(retained_capacity.reason, "capacity")
        self.assertTrue(other_key.accepted)

    async def test_operation_replay_capacity_fails_closed_without_mutating(self) -> None:
        store = InMemoryStateStore(
            clock=self.clock,
            _quota_record_limit_for_testing=4,
            _quota_replay_limit_for_testing=1,
        )
        self.assertTrue(
            (
                await store.reserve_quota(_reservation("holder", rpm_limit=1, ttl_seconds=120.0))
            ).accepted
        )
        first_denial = await store.reserve_quota(_reservation("denied-1", rpm_limit=1))
        second_denial = await store.reserve_quota(_reservation("denied-2", rpm_limit=1))

        self.assertEqual(first_denial.reason, "rpm")
        self.assertEqual(second_denial.reason, "reconciliation_required")
        with self.assertRaises(CoordinationReconciliationRequiredError):
            await store.release_quota("holder", now=1_000.5, operation_id="release")
        self.clock.advance(62.0)
        self.assertTrue(await store.release_quota("holder", now=1_062.0, operation_id="release"))

    async def test_explicit_success_replay_uses_the_accepted_retention_window(self) -> None:
        store = InMemoryStateStore(
            clock=self.clock,
            _quota_record_limit_for_testing=4,
            _quota_replay_limit_for_testing=1,
        )
        accepted = await store.reserve_quota(_reservation("accepted", operation_id="accepted-op"))
        blocked = await store.reserve_quota(_reservation("blocked", now=1_002.0))
        self.clock.advance(62.0)
        after_retention = await store.reserve_quota(_reservation("after-retention", now=1_062.0))

        self.assertTrue(accepted.accepted)
        self.assertEqual(blocked.reason, "reconciliation_required")
        self.assertTrue(after_retention.accepted)

    async def test_stale_quota_heap_nodes_do_not_consume_the_cleanup_budget(self) -> None:
        store = InMemoryStateStore(
            clock=self.clock,
            _quota_record_limit_for_testing=300,
            _quota_replay_limit_for_testing=300,
        )
        for index in range(257):
            reservation_id = f"stale-node-{index}"
            self.assertTrue(
                (await store.reserve_quota(_reservation(reservation_id, ttl_seconds=61.0))).accepted
            )
            self.assertTrue(
                await store.release_quota(
                    reservation_id, now=1_000.5, operation_id=f"release-{index}"
                )
            )

        self.clock.advance(2.0)
        admitted = await store.reserve_quota(_reservation("after-stale", now=1_002.0))
        self.assertTrue(admitted.accepted)

    async def test_commit_and_release_operation_ids_are_retained_and_conflict(self) -> None:
        for reservation_id in ("commit-a", "commit-b", "release-a", "release-b"):
            self.assertTrue(
                (
                    await self.store.reserve_quota(_reservation(reservation_id, ttl_seconds=61.0))
                ).accepted
            )

        commit_request = QuotaCommitRequest("commit-a", 1_000.5, 1, 0.0, True, 1, "commit-op")
        self.assertTrue((await self.store.commit_quota(commit_request)).committed)
        commit_replay = await self.store.commit_quota(commit_request)
        commit_conflict = await self.store.commit_quota(
            QuotaCommitRequest("commit-b", 1_000.5, 1, 0.0, True, 1, "commit-op")
        )
        self.assertTrue(commit_replay.idempotent)
        self.assertFalse(commit_conflict.committed)
        self.assertTrue(
            (
                await self.store.commit_quota(
                    QuotaCommitRequest("commit-b", 1_000.5, 1, 0.0, True, 1, "commit-b-op")
                )
            ).committed
        )

        self.assertTrue(
            await self.store.release_quota("release-a", now=1_000.5, operation_id="release-op")
        )
        self.assertFalse(
            await self.store.release_quota("release-a", now=1_001.0, operation_id="release-op")
        )
        self.assertFalse(
            await self.store.release_quota("release-b", now=1_000.5, operation_id="release-op")
        )
        self.assertTrue(
            await self.store.release_quota("release-b", now=1_000.5, operation_id="release-b-op")
        )

    async def test_release_rejects_malformed_untyped_arguments(self) -> None:
        with self.assertRaises(ValueError):
            await self.store.release_quota("release", now=1_000.0, fencing_epoch=True)
        with self.assertRaises(ValueError):
            await self.store.release_quota("", now=1_000.0)
        with self.assertRaises(ValueError):
            await self.store.release_quota("release", now=float("nan"))
        with self.assertRaises(ValueError):
            await self.store.release_quota("release", now=1_000.0, operation_id="bad\n")

    async def test_raw_epoch_mutations_validate_before_state_changes(self) -> None:
        invalid_epochs = (True, 1.0, 0, -1, 2**63)
        invalid_operations = ("", b"bytes", "bad\n", "x" * 129)
        for value in invalid_epochs:
            store = InMemoryStateStore(clock=self.clock)
            with self.subTest(method="advance", value=value), self.assertRaises(ValueError):
                await store.advance_epoch(value, "operation")  # type: ignore[arg-type]
            self.assertEqual(await store.read_epoch(), Epoch(1, EpochState.READY))
        for value in invalid_operations:
            store = InMemoryStateStore(clock=self.clock)
            with self.subTest(method="advance", value=value), self.assertRaises(ValueError):
                await store.advance_epoch(1, value)  # type: ignore[arg-type]
            self.assertEqual(await store.read_epoch(), Epoch(1, EpochState.READY))

        for value in (*invalid_epochs, *invalid_operations):
            store = InMemoryStateStore(clock=self.clock)
            await store.advance_epoch(1, "advance")
            with self.subTest(method="ready", value=value), self.assertRaises(ValueError):
                if value in invalid_epochs:
                    await store.mark_epoch_ready(value, "operation")  # type: ignore[arg-type]
                else:
                    await store.mark_epoch_ready(2, value)  # type: ignore[arg-type]
            self.assertEqual(await store.read_epoch(), Epoch(2, EpochState.RECONCILING))

    async def test_epoch_advance_replay_capacity_is_bounded_and_expires(self) -> None:
        store = InMemoryStateStore(clock=self.clock, _coordination_replay_limit_for_testing=1)
        first = await store.advance_epoch(1, "advance-1")
        self.assertEqual(await store.advance_epoch(1, "advance-1"), first)
        await store.mark_epoch_ready(2, "ready-2")

        with self.assertRaises(CoordinationReconciliationRequiredError):
            await store.advance_epoch(2, "advance-2")
        self.assertEqual(await store.read_epoch(), Epoch(2, EpochState.READY))

        self.clock.advance(30 * 86_400 + 1)
        advanced = await store.advance_epoch(2, "advance-2")
        self.assertEqual(advanced, Epoch(3, EpochState.RECONCILING))

    async def test_epoch_ready_replay_capacity_is_bounded_and_expires(self) -> None:
        store = InMemoryStateStore(clock=self.clock, _coordination_replay_limit_for_testing=1)
        store._epoch = Epoch(2, EpochState.RECONCILING)
        first = await store.mark_epoch_ready(2, "ready-2")
        self.assertEqual(await store.mark_epoch_ready(2, "ready-2"), first)
        store._epoch = Epoch(3, EpochState.RECONCILING)

        with self.assertRaises(CoordinationReconciliationRequiredError):
            await store.mark_epoch_ready(3, "ready-3")
        self.assertEqual(await store.read_epoch(), Epoch(3, EpochState.RECONCILING))

        self.clock.advance(30 * 86_400 + 1)
        ready = await store.mark_epoch_ready(3, "ready-3")
        self.assertEqual(ready, Epoch(3, EpochState.READY))

    async def test_cas_replay_capacity_is_bounded_and_expires(self) -> None:
        store = InMemoryStateStore(clock=self.clock, _coordination_replay_limit_for_testing=1)
        first_request = CasRequest("first", 0, b"first", 10.0, 1, "cas-1")
        first = await store.compare_and_set(first_request)
        replay = await store.compare_and_set(first_request)
        self.assertTrue(first.applied)
        self.assertTrue(replay.idempotent)

        with self.assertRaises(CoordinationReconciliationRequiredError):
            await store.compare_and_set(CasRequest("second", 0, b"second", 10.0, 1, "cas-2"))
        self.assertNotIn("second", store._cas)

        self.clock.advance(10.1)
        admitted = await store.compare_and_set(CasRequest("second", 0, b"second", 10.0, 1, "cas-2"))
        self.assertTrue(admitted.applied)

    async def test_cas_replay_can_expire_before_the_durable_record(self) -> None:
        store = InMemoryStateStore(clock=self.clock, _coordination_replay_limit_for_testing=1)
        first = CasRequest(
            "long-lived-record",
            0,
            b"first",
            300.0,
            1,
            "cas-short-replay-1",
            replay_ttl_seconds=1.0,
        )
        self.assertTrue((await store.compare_and_set(first)).applied)

        self.clock.advance(1.1)
        second = CasRequest(
            "long-lived-record",
            1,
            b"second",
            300.0,
            1,
            "cas-short-replay-2",
            replay_ttl_seconds=1.0,
        )
        self.assertTrue((await store.compare_and_set(second)).applied)
        snapshot = await store.read_cas("long-lived-record", epoch=1)
        self.assertEqual(snapshot.payload, b"second")

    async def test_invalidation_replay_capacity_is_bounded_and_expires(self) -> None:
        store = InMemoryStateStore(clock=self.clock, _coordination_replay_limit_for_testing=1)
        first_request = InvalidationRequest("scope-1", 1, "invalidate-1", 10.0)
        first = await store.invalidate(first_request)
        replay = await store.invalidate(first_request)
        self.assertTrue(first.applied)
        self.assertTrue(replay.idempotent)

        with self.assertRaises(CoordinationReconciliationRequiredError):
            await store.invalidate(InvalidationRequest("scope-2", 1, "invalidate-2", 10.0))
        self.assertNotIn("scope-2", store._invalidation_generations)

        self.clock.advance(10.1)
        admitted = await store.invalidate(InvalidationRequest("scope-2", 1, "invalidate-2", 10.0))
        self.assertTrue(admitted.applied)

    async def test_fully_expired_quota_key_removes_empty_heap_buckets(self) -> None:
        store = InMemoryStateStore(clock=self.clock)
        request = _reservation("one-shot", key_id="one-shot-key", operation_id="reserve-op")
        self.assertTrue((await store.reserve_quota(request)).accepted)

        self.clock.advance(62.0)
        self.assertFalse(await store.release_quota("one-shot", now=1_062.0))

        self.assertNotIn("one-shot-key", store._quota_lifecycle_expiries)
        self.assertNotIn("one-shot-key", store._quota_replay_expiries)
        self.assertNotIn("one-shot-key", store._quota_rate_windows)

    async def test_quota_reconciliation_is_bounded_resumable_and_dry_run_safe(self) -> None:
        for index in range(3):
            identifier = f"reconcile-{index}"
            self.assertTrue((await self.store.reserve_quota(_reservation(identifier))).accepted)
            self.assertTrue(
                await self.store.release_quota(
                    identifier, now=self.clock.value, operation_id=f"release-{index}"
                )
            )
        await self.store.advance_epoch(1, "advance-reconciliation")
        before = copy.deepcopy(
            (
                self.store._quota_records,
                self.store._quota_replays,
            )
        )
        before_totals = self.store._quota_rate_windows["virtual-key"].totals(self.clock.value)

        preview = await self.store.reconcile_quota_state(epoch=2, cursor=None, limit=2, apply=False)

        self.assertEqual(preview.scanned, 2)
        self.assertFalse(preview.complete)
        self.assertEqual(
            (
                self.store._quota_records,
                self.store._quota_replays,
            ),
            before,
        )
        self.assertEqual(
            self.store._quota_rate_windows["virtual-key"].totals(self.clock.value), before_totals
        )
        cursor = None
        pages = 0
        while True:
            page = await self.store.reconcile_quota_state(
                epoch=2, cursor=cursor, limit=2, apply=True
            )
            self.assertLessEqual(page.scanned, 2)
            pages += 1
            if page.complete:
                break
            cursor = page.cursor
        self.assertGreater(pages, 1)
        self.assertEqual(self.store._quota_records, {})
        self.assertEqual(self.store._quota_replays, {})
        self.assertEqual(self.store._quota_rate_windows, {})
        replayed_complete = await self.store.reconcile_quota_state(
            epoch=2, cursor=None, limit=2, apply=True
        )
        self.assertEqual((replayed_complete.scanned, replayed_complete.complete), (0, True))
        self.assertNotEqual(replayed_complete.snapshot_digest, "0" * 64)

    async def test_quota_reconciliation_rejects_active_state_and_malformed_cursor(self) -> None:
        self.assertTrue((await self.store.reserve_quota(_reservation("active"))).accepted)
        await self.store.advance_epoch(1, "advance-active")

        with self.assertRaises(CoordinationReconciliationRequiredError):
            await self.store.reconcile_quota_state(epoch=2, cursor=None, limit=256, apply=True)
        with self.assertRaises(ValueError):
            await self.store.reconcile_quota_state(
                epoch=2, cursor="not-a-valid-closed-cursor", limit=256, apply=True
            )
        self.assertIn("active", self.store._quota_records)

    async def test_quota_reconciliation_replays_exact_page_after_destructive_apply(self) -> None:
        decision = await self.store.reserve_quota(_reservation("replay-page"))
        self.assertTrue(decision.accepted)
        await self.store.release_quota(
            "replay-page", now=self.clock.value, operation_id="release-replay-page"
        )
        await self.store.advance_epoch(1, "advance-replay-page")

        first = await self.store.reconcile_quota_state(
            epoch=2,
            cursor=None,
            limit=1,
            apply=True,
            operation_id="quota-reconciliation-page-1",
        )
        replay = await self.store.reconcile_quota_state(
            epoch=2,
            cursor=None,
            limit=1,
            apply=True,
            operation_id="quota-reconciliation-page-1",
        )

        self.assertEqual(replay, first)
        self.assertNotEqual(first.snapshot_digest, "0" * 64)
        with self.assertRaises(CoordinationCorruptError):
            await self.store.reconcile_quota_state(
                epoch=2,
                cursor=first.cursor,
                limit=1,
                apply=True,
                operation_id="quota-reconciliation-page-1",
            )

    async def test_capacity_exhaustion_is_a_closed_admission_decision(self) -> None:
        store = InMemoryStateStore(clock=self.clock, _quota_record_limit_for_testing=2)

        self.assertTrue((await store.reserve_quota(_reservation("one"))).accepted)
        self.assertTrue((await store.reserve_quota(_reservation("two"))).accepted)
        exhausted = await store.reserve_quota(_reservation("three"))

        self.assertFalse(exhausted.accepted)
        self.assertEqual(exhausted.reason, "capacity")

    async def test_cleanup_backlog_fails_closed_without_unbounded_pruning(self) -> None:
        store = InMemoryStateStore(clock=self.clock, _quota_record_limit_for_testing=300)
        for index in range(257):
            decision = await store.reserve_quota(_reservation(f"expired-{index}"))
            self.assertTrue(decision.accepted)

        self.clock.advance(62.0)
        backlog = await store.reserve_quota(_reservation("after-expiry", now=1_062.0))

        self.assertFalse(backlog.accepted)
        self.assertEqual(backlog.reason, "reconciliation_required")

    async def test_quota_cleanup_backlog_preflight_is_transactional_and_repeatable(self) -> None:
        store = InMemoryStateStore(clock=self.clock, _quota_record_limit_for_testing=300)
        for index in range(257):
            self.assertTrue((await store.reserve_quota(_reservation(f"expired-{index}"))).accepted)
        self.clock.advance(62.0)

        def snapshot() -> object:
            return copy.deepcopy(
                (
                    store._quota_records,
                    store._quota_ids_by_key,
                    store._quota_lifecycle_expiries,
                    store._quota_replays,
                    store._quota_replay_expiries,
                    store._quota_replay_counts,
                )
            )

        before = snapshot()
        for attempt in range(2):
            with self.subTest(attempt=attempt):
                denied = await store.reserve_quota(_reservation("after-expiry"))
                self.assertEqual(denied.reason, "reconciliation_required")
                self.assertEqual(snapshot(), before)

    async def test_cleanup_is_operation_local_and_invalidation_reads_are_side_effect_free(
        self,
    ) -> None:
        store = InMemoryStateStore(clock=self.clock)
        for index in range(257):
            self.assertTrue(
                (
                    await store.compare_and_set(
                        CasRequest(
                            f"expired-cas-{index}",
                            0,
                            b"value",
                            1.0,
                            1,
                            f"cas-{index}",
                        )
                    )
                ).applied
            )
        self.clock.advance(2.0)

        invalidated = await store.invalidate(InvalidationRequest("scope", 1, "invalidate", 1.0))
        self.assertTrue(invalidated.applied)
        before_read = copy.deepcopy(
            (store._invalidation_replays, store._invalidation_replay_expiries)
        )
        self.clock.advance(2.0)
        self.assertEqual((await store.read_invalidation_generation("scope")).generation, 1)
        self.assertEqual(
            (store._invalidation_replays, store._invalidation_replay_expiries),
            before_read,
        )

    async def test_cas_cleanup_backlog_raises_a_typed_fail_closed_error(self) -> None:
        for index in range(257):
            result = await self.store.compare_and_set(
                CasRequest(f"expired-cas-{index}", 0, b"value", 1.0, 1, f"cas-{index}")
            )
            self.assertTrue(result.applied)
        self.clock.advance(2.0)

        before = copy.deepcopy(
            (
                self.store._cas,
                self.store._cas_replays,
                self.store._cas_expiries,
                self.store._cas_replay_expiries,
            )
        )
        for attempt in range(2):
            with (
                self.subTest(attempt=attempt),
                self.assertRaises(CoordinationReconciliationRequiredError),
            ):
                await self.store.compare_and_set(
                    CasRequest("after-expiry", 0, b"value", 1.0, 1, "after-expiry")
                )
            self.assertEqual(
                (
                    self.store._cas,
                    self.store._cas_replays,
                    self.store._cas_expiries,
                    self.store._cas_replay_expiries,
                ),
                before,
            )


if __name__ == "__main__":
    unittest.main()
