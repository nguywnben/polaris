"""Validation and wire-contract tests for coordination primitives."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.coordination import (
    MAX_PAYLOAD_BYTES,
    CasRequest,
    CasResult,
    CasSettlementProof,
    CasSettlementTarget,
    CasSettlementTransition,
    CoordinationCorruptError,
    CoordinationReconciliationRequiredError,
    Epoch,
    EpochState,
    InvalidationGeneration,
    InvalidationRequest,
    InvalidationResult,
    QuotaCommitResult,
    QuotaReconciliationResult,
    QuotaReservationDecision,
    QuotaReservationRequest,
    decode_cas_result,
    decode_epoch,
    decode_invalidation_generation,
    decode_invalidation_result,
    validate_deployment_namespace,
)


def _quota_request(**overrides: object) -> QuotaReservationRequest:
    values: dict[str, object] = {
        "reservation_id": "reservation",
        "key_id": "key",
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


class CoordinationDomainTests(unittest.TestCase):
    def test_quota_reconciliation_result_is_closed_and_bounded(self) -> None:
        self.assertEqual(QuotaReconciliationResult(0, True, None, "a" * 64).scanned, 0)
        self.assertEqual(
            QuotaReconciliationResult(256, False, "cursor", "a" * 64).cursor,
            "cursor",
        )
        for values in ((257, False, "cursor"), (0, True, "cursor"), (0, False, None)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                QuotaReconciliationResult(*values, "a" * 64)

    def test_quota_reservation_ttl_covers_the_conservative_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "Quota TTL"):
            _quota_request(ttl_seconds=60.999)
        self.assertEqual(_quota_request(ttl_seconds=61.0).ttl_seconds, 61.0)

    def test_reconciliation_required_is_a_typed_unavailable_error(self) -> None:
        from core.coordination import CoordinationUnavailableError

        self.assertTrue(
            issubclass(CoordinationReconciliationRequiredError, CoordinationUnavailableError)
        )

    def test_deployment_namespace_accepts_only_bounded_lowercase_ascii(self) -> None:
        for namespace in ("abc", "tenant-1", "a" * 64):
            with self.subTest(namespace=namespace):
                self.assertEqual(validate_deployment_namespace(namespace), namespace)
        for namespace in ("ab", "a" * 65, "Upper", "under_score", "has space", b"bytes"):
            with self.subTest(namespace=namespace), self.assertRaises(ValueError):
                validate_deployment_namespace(namespace)

    def test_requests_reject_boolean_integer_fields(self) -> None:
        with self.assertRaises(ValueError):
            Epoch(epoch=True, state=EpochState.READY)
        with self.assertRaises(ValueError):
            CasRequest("key", 0, b"payload", 1.0, 1, True)
        with self.assertRaises(ValueError):
            InvalidationRequest("scope", 1, "op", replay_ttl_seconds=True)
        from core.coordination import QuotaReservationRequest

        with self.assertRaises(ValueError):
            QuotaReservationRequest(
                "reservation",
                "key",
                1.0,
                61.0,
                1,
                0.0,
                None,
                None,
                None,
                None,
                0.0,
                0.0,
                0.0,
                0.0,
                True,
            )

    def test_requests_reject_non_finite_and_out_of_range_values(self) -> None:
        for value in (math.nan, math.inf, -math.inf, 0.0, 30 * 86_400 + 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                CasRequest("key", 0, b"payload", value, 1, "op")
        for value in (math.nan, math.inf, -math.inf, 0.0, 30 * 86_400 + 1):
            with self.subTest(replay_ttl=value), self.assertRaises(ValueError):
                CasRequest(
                    "key",
                    0,
                    b"payload",
                    300.0,
                    1,
                    "op",
                    replay_ttl_seconds=value,
                )
        for revision in (-1, 2**63):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                CasRequest("key", revision, b"payload", 1.0, 1, "op")
        for epoch in (0, -1, 2**63):
            with self.subTest(epoch=epoch), self.assertRaises(ValueError):
                InvalidationRequest("scope", epoch, "op")

    def test_cas_replay_ttl_defaults_to_record_ttl_and_can_be_bounded_separately(self) -> None:
        defaulted = CasRequest("key", 0, b"payload", 300.0, 1, "defaulted")
        bounded = CasRequest(
            "key",
            0,
            b"payload",
            300.0,
            1,
            "bounded",
            replay_ttl_seconds=60.0,
        )

        self.assertEqual(defaulted.effective_replay_ttl_seconds, 300.0)
        self.assertEqual(bounded.effective_replay_ttl_seconds, 60.0)

    def test_quota_snapshots_must_be_ordered_and_not_from_the_future(self) -> None:
        for overrides in (
            {"daily_snapshot_started_at": 1_001.0},
            {
                "daily_snapshot_started_at": 999.0,
                "monthly_snapshot_started_at": 999.5,
            },
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                _quota_request(**overrides)

    def test_quota_result_objects_reject_cross_field_contradictions(self) -> None:
        non_rate_denials = (
            "daily_budget",
            "monthly_budget",
            "capacity",
            "conflict",
            "stale_epoch",
            "reconciling",
            "reconciliation_required",
        )
        invalid_decisions = (
            (True, "rpm", 1),
            (True, "", 1),
            (False, "", 0),
            (False, "rpm", 0),
            (False, "tpm", 0),
            (False, "unknown", 0),
            (False, [], 0),
            *((False, reason, 1) for reason in non_rate_denials),
        )
        for accepted, reason, retry_after in invalid_decisions:
            with (
                self.subTest(accepted=accepted, reason=reason, retry_after=retry_after),
                self.assertRaises(ValueError),
            ):
                QuotaReservationDecision(
                    accepted,
                    "reservation",
                    reason,
                    retry_after,  # type: ignore[arg-type]
                )

        for reason, retry_after in (
            ("rpm", 1),
            ("tpm", 2),
            *((reason, 0) for reason in non_rate_denials),
        ):
            with self.subTest(reason=reason):
                QuotaReservationDecision(False, "reservation", reason, retry_after, True)
        QuotaReservationDecision(True, "reservation")

        with self.assertRaises(ValueError):
            QuotaCommitResult(False, overspent=True)
        QuotaCommitResult(False, idempotent=True)

    def test_requests_reject_malformed_identifiers_and_oversized_payloads(self) -> None:
        for identifier in ("", "\n", "has\x00control", "x" * 129):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                CasRequest(identifier, 0, b"payload", 1.0, 1, "op")
        with self.assertRaises(ValueError):
            CasRequest("key", 0, b"x" * (MAX_PAYLOAD_BYTES + 1), 1.0, 1, "op")
        with self.assertRaises(ValueError):
            InvalidationRequest("scope", 1, "\tbad")

    def test_cas_settlement_capabilities_are_typed_finite_and_admission_bound(self) -> None:
        target = CasSettlementTarget("root", CasSettlementTransition.UPDATE)
        admission = CasRequest(
            "root",
            0,
            b"payload",
            1.0,
            1,
            "admit",
            settlement_targets=(target,),
        )
        self.assertEqual(CasSettlementProof(admission, target).target, target)
        for invalid_targets in (
            [target],
            (target, target),
            tuple(
                CasSettlementTarget(f"target-{index}", CasSettlementTransition.CREATE)
                for index in range(65)
            ),
        ):
            with self.subTest(size=len(invalid_targets)), self.assertRaises(ValueError):
                CasRequest(
                    "root",
                    0,
                    b"payload",
                    1.0,
                    1,
                    "bad-targets",
                    settlement_targets=invalid_targets,  # type: ignore[arg-type]
                )
        with self.assertRaises(ValueError):
            CasSettlementProof(
                admission,
                CasSettlementTarget("invented", CasSettlementTransition.CREATE),
            )
        with self.assertRaises(ValueError):
            CasRequest(
                "root",
                1,
                b"settled",
                1.0,
                1,
                "settle",
                settlement_targets=(target,),
                settlement=CasSettlementProof(admission, target),
            )

    def test_stored_reply_decoders_require_exact_schema_and_types(self) -> None:
        self.assertEqual(
            decode_epoch({"schema_version": 1, "epoch": 2, "state": "ready"}),
            Epoch(epoch=2, state=EpochState.READY),
        )
        self.assertEqual(
            decode_cas_result(
                {
                    "schema_version": 1,
                    "applied": True,
                    "revision": 2,
                    "idempotent": False,
                }
            ),
            CasResult(applied=True, revision=2),
        )
        self.assertEqual(
            decode_invalidation_result(
                {
                    "schema_version": 1,
                    "applied": True,
                    "generation": 2,
                    "idempotent": True,
                }
            ),
            InvalidationResult(applied=True, generation=2, idempotent=True),
        )
        self.assertEqual(
            decode_invalidation_generation({"schema_version": 1, "generation": 2}),
            InvalidationGeneration(generation=2),
        )
        for reply in (
            {"schema_version": 1, "epoch": 2, "state": "ready", "extra": "no"},
            {"schema_version": 1, "epoch": True, "state": "ready"},
            {"schema_version": 1.0, "epoch": 2, "state": "ready"},
            {"schema_version": 1, "epoch": 2, "state": "unknown"},
        ):
            with self.subTest(reply=reply), self.assertRaises(CoordinationCorruptError):
                decode_epoch(reply)

    def test_representations_never_include_payload_or_operation_id(self) -> None:
        secret = "Bearer top-secret-token"
        values = (
            CasRequest(secret, 0, secret.encode(), 1.0, 1, secret),
            InvalidationRequest(secret, 1, secret),
        )
        for value in values:
            with self.subTest(value=type(value).__name__):
                self.assertNotIn(secret, repr(value))


if __name__ == "__main__":
    unittest.main()
