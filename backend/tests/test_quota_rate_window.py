"""Exact behavioral contract for the bounded quota rate window."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.coordination import MAX_COORDINATION_INTEGER, CoordinationCorruptError
from core.quota_rate_window import QuotaRateWindow, RateTotals, _RateBucket


class QuotaRateWindowTests(unittest.TestCase):
    def test_boundary_second_is_conservatively_included(self) -> None:
        window = QuotaRateWindow()
        window.reserve(1_000.999, 7)

        self.assertEqual(window.totals(1_060.999), RateTotals(requests=1, tokens=7))
        self.assertEqual(window.totals(1_061.000), RateTotals(requests=0, tokens=0))

    def test_commit_replaces_the_estimate_exactly_once(self) -> None:
        window = QuotaRateWindow()
        window.reserve(1_000.1, 100)

        window.commit(1_000.1, 100, 1_001.2, 250)

        self.assertEqual(window.totals(1_001.2), RateTotals(requests=1, tokens=250))

    def test_commit_after_estimate_ages_out_adds_only_actual_usage(self) -> None:
        window = QuotaRateWindow()
        window.reserve(1_000.1, 100)

        window.commit(1_000.1, 100, 1_061.0, 250)

        self.assertEqual(window.totals(1_061.0), RateTotals(requests=1, tokens=250))

    def test_release_reverses_a_live_estimate(self) -> None:
        window = QuotaRateWindow()
        window.reserve(1_000.1, 100)

        window.release(1_000.1, 100, 1_001.0)

        self.assertEqual(window.totals(1_001.0), RateTotals(requests=0, tokens=0))

    def test_storage_never_exceeds_61_slots(self) -> None:
        window = QuotaRateWindow()
        for second in range(10_000):
            window.reserve(float(second), 1)

        self.assertEqual(window.slot_count, 61)
        self.assertEqual(window.totals(9_999.0), RateTotals(requests=61, tokens=61))

    def test_retry_after_uses_the_conservative_bucket_expiry(self) -> None:
        window = QuotaRateWindow()
        window.reserve(1_000.9, 1)

        self.assertEqual(window.retry_after_seconds(1_001.1), 60)
        self.assertEqual(window.retry_after_seconds(1_060.9), 1)

    def test_underflow_overflow_and_future_bucket_fail_closed(self) -> None:
        with self.subTest(case="underflow"):
            window = QuotaRateWindow()
            window.reserve(1_000.0, 1)
            with self.assertRaises(CoordinationCorruptError):
                window.release(1_000.0, 2, 1_000.0)

        with self.subTest(case="overflow"):
            window = QuotaRateWindow()
            window.reserve(1_000.0, MAX_COORDINATION_INTEGER)
            with self.assertRaises(CoordinationCorruptError):
                window.reserve(1_000.0, 1)

        with self.subTest(case="future"):
            window = QuotaRateWindow()
            future_second = 1_001
            window._slots[future_second % 61] = _RateBucket(future_second, 1, 1)
            with self.assertRaises(CoordinationCorruptError):
                window.totals(1_000.0)


if __name__ == "__main__":
    unittest.main()
