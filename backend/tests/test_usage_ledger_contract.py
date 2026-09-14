"""Strict W4.14 usage-ledger and durable-budget domain contract."""

from __future__ import annotations

import dataclasses
import math
import sys
import unittest
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.usage_ledger import (
    MAX_COST_NANOS,
    USAGE_LEDGER_SCHEMA_VERSION,
    BudgetReservation,
    BudgetReservationRequest,
    BudgetReservationState,
    UsageLedgerEntry,
    budget_reservation_from_record,
    nanos_to_usd,
    usage_entry_from_record,
    usd_to_nanos,
)

EVENT_ID = "use_" + ("a" * 32)
RESERVATION_ID = "qrs_" + ("b" * 32)
KEY_ID = "vk_enterprise"


def _usage(**overrides) -> UsageLedgerEntry:
    values = {
        "schema_version": USAGE_LEDGER_SCHEMA_VERSION,
        "event_id": EVENT_ID,
        "occurred_at": 1_777_777_777.25,
        "credential_ref": "account.json",
        "request_id": "request-123",
        "model": "gpt-5.6",
        "provider": "openai",
        "status_code": 200,
        "success": True,
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
        "cached_tokens": 5,
        "reasoning_tokens": 3,
        "estimated_input_tokens": 110,
        "estimated_tokens_saved": 10,
        "compressed_messages": 2,
        "quality_profile": "balanced",
        "quality_policy_revision": 4,
        "compression_reason": "target_reached",
        "latency_ms": 250,
        "retry_count": 1,
        "cost_nanos": 125_000,
        "api_key_id": KEY_ID,
    }
    values.update(overrides)
    return UsageLedgerEntry(**values)


def _request(**overrides) -> BudgetReservationRequest:
    values = {
        "schema_version": USAGE_LEDGER_SCHEMA_VERSION,
        "reservation_id": RESERVATION_ID,
        "key_id": KEY_ID,
        "created_at": 1_777_777_700.0,
        "expires_at": 1_777_777_760.0,
        "estimated_tokens": 1_000,
        "estimated_cost_nanos": 500_000_000,
        "daily_budget_nanos": 2_000_000_000,
        "monthly_budget_nanos": 10_000_000_000,
    }
    values.update(overrides)
    return BudgetReservationRequest(**values)


class CostConversionTests(unittest.TestCase):
    def test_positive_fraction_never_rounds_down_to_silent_zero(self):
        self.assertEqual(usd_to_nanos("0.0000000001"), 1)
        self.assertEqual(usd_to_nanos(0), 0)
        self.assertEqual(nanos_to_usd(125_000), 0.000125)

    def test_invalid_or_unbounded_cost_is_rejected(self):
        for value in (True, -1, math.nan, math.inf, "not-a-number"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    usd_to_nanos(value)
        with self.assertRaises(ValueError):
            usd_to_nanos(str(Decimal(MAX_COST_NANOS + 1) / Decimal(1_000_000_000)))


class UsageLedgerEntryTests(unittest.TestCase):
    def test_exact_round_trip_and_payload_free_representation(self):
        entry = _usage()
        self.assertEqual(usage_entry_from_record(entry.to_record()), entry)
        rendered = repr(entry)
        self.assertNotIn("account.json", rendered)
        self.assertNotIn("request-123", rendered)
        self.assertNotIn(KEY_ID, rendered)

    def test_previous_payload_defaults_new_usage_metadata_without_accepting_unknown_fields(self):
        record = _usage().to_record()
        record.pop("cache_creation_tokens")
        record.pop("usage_reported")

        restored = usage_entry_from_record(record)

        self.assertEqual(restored.cache_creation_tokens, 0)
        self.assertTrue(restored.usage_reported)

        zero_record = _usage(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cached_tokens=0,
            reasoning_tokens=0,
        ).to_record()
        zero_record.pop("cache_creation_tokens")
        zero_record.pop("usage_reported")
        self.assertFalse(usage_entry_from_record(zero_record).usage_reported)

    def test_stored_record_rejects_unknown_or_missing_fields(self):
        record = _usage().to_record()
        record["unknown"] = "value"
        with self.assertRaises(ValueError):
            usage_entry_from_record(record)
        record = _usage().to_record()
        record.pop("provider")
        with self.assertRaises(ValueError):
            usage_entry_from_record(record)

    def test_ids_paths_controls_and_invalid_counters_fail_closed(self):
        invalid = (
            {"event_id": "use_invalid"},
            {"credential_ref": "../account.json"},
            {"request_id": "request\nforged"},
            {"model": "x" * 257},
            {"status_code": 99},
            {"success": 1},
            {"total_tokens": -1},
            {"cost_nanos": -1},
            {"quality_profile": "fastest"},
            {"compression_reason": "arbitrary"},
            {"occurred_at": math.nan},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    _usage(**overrides)


class BudgetReservationTests(unittest.TestCase):
    def test_request_requires_one_hard_budget_and_valid_window(self):
        with self.assertRaises(ValueError):
            _request(daily_budget_nanos=None, monthly_budget_nanos=None)
        with self.assertRaises(ValueError):
            _request(expires_at=1_777_777_699.0)
        with self.assertRaises(ValueError):
            _request(reservation_id="qrs_invalid")

    def test_active_committed_released_and_expired_invariants(self):
        active = BudgetReservation.active(_request())
        self.assertEqual(active.state, BudgetReservationState.ACTIVE)
        self.assertEqual(active.revision, 1)
        self.assertIsNone(active.usage)

        committed = dataclasses.replace(
            active,
            state=BudgetReservationState.COMMITTED,
            revision=2,
            transitioned_at=1_777_777_750.0,
            usage=_usage(occurred_at=1_777_777_750.0),
        )
        self.assertEqual(budget_reservation_from_record(committed.to_record()), committed)

        for state in (BudgetReservationState.RELEASED, BudgetReservationState.EXPIRED):
            terminal = dataclasses.replace(
                active,
                state=state,
                revision=2,
                transitioned_at=(
                    1_777_777_760.0 if state is BudgetReservationState.EXPIRED else 1_777_777_750.0
                ),
            )
            self.assertEqual(budget_reservation_from_record(terminal.to_record()), terminal)

    def test_invalid_terminal_or_committed_evidence_fails_closed(self):
        active = BudgetReservation.active(_request())
        base = active.to_record()
        invalid = []
        invalid.append({**base, "revision": 2})
        invalid.append({**base, "transitioned_at": 1_777_777_750.0})
        invalid.append(
            {
                **base,
                "state": BudgetReservationState.COMMITTED.value,
                "revision": 2,
                "transitioned_at": 1_777_777_750.0,
            }
        )
        invalid.append(
            {
                **base,
                "state": BudgetReservationState.RELEASED.value,
                "revision": 2,
                "transitioned_at": 1_777_777_750.0,
                "usage": _usage(occurred_at=1_777_777_750.0).to_record(),
            }
        )
        invalid.append(
            {
                **base,
                "state": BudgetReservationState.COMMITTED.value,
                "revision": 2,
                "transitioned_at": 1_777_777_750.0,
                "usage": _usage(occurred_at=1_777_777_750.0, api_key_id="vk_other").to_record(),
            }
        )
        for record in invalid:
            with self.subTest(record=record):
                with self.assertRaises(ValueError):
                    budget_reservation_from_record(record)

    def test_reservation_revision_rejects_bool_and_float(self):
        active = BudgetReservation.active(_request())
        for revision in (True, 1.0):
            with self.subTest(revision=revision):
                with self.assertRaises(ValueError):
                    dataclasses.replace(active, revision=revision)

    def test_stored_reservation_rejects_unknown_state_and_fields(self):
        record = BudgetReservation.active(_request()).to_record()
        record["state"] = "cancelled"
        with self.assertRaises(ValueError):
            budget_reservation_from_record(record)
        record = BudgetReservation.active(_request()).to_record()
        record["extra"] = False
        with self.assertRaises(ValueError):
            budget_reservation_from_record(record)


if __name__ == "__main__":
    unittest.main()
