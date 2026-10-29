"""Contracts for routine and optional production reliability profiles."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tools.reliability_profile import (
    MemorySample,
    WorkloadMetrics,
    analyze_memory,
    evaluate_profile,
    load_profile,
    percentile,
)

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / "tools" / "reliability-profile.json"
SOAK_PROFILE_PATH = ROOT / "tools" / "reliability-soak-profile.json"


class ReliabilityProfileContractTests(unittest.TestCase):
    def test_benchmark_disables_background_network_pricing_sync(self) -> None:
        from tools.reliability_profile import CandidateRuntime

        self.assertIn('PRICING_SYNC_ENABLED="false"', inspect.getsource(CandidateRuntime.start))

    def test_working_tree_snapshot_uses_current_bytes_and_records_digest(self) -> None:
        from tools.reliability_profile import snapshot_working_tree

        with tempfile.TemporaryDirectory(dir=ROOT / "temp") as directory:
            root = Path(directory) / "repo"
            target = Path(directory) / "snapshot"
            (root / "backend").mkdir(parents=True)
            (root / "frontend").mkdir()
            target.mkdir()
            (root / "backend/main.py").write_text("changed", encoding="utf-8")
            (root / "frontend/new.js").write_text("new", encoding="utf-8")
            with (
                patch("tools.reliability_profile.ROOT", root),
                patch(
                    "tools.reliability_profile._git_output",
                    return_value="backend/main.py\0frontend/new.js\0backend/deleted.py\0",
                ),
            ):
                result = snapshot_working_tree(target)
            self.assertEqual((target / "backend/main.py").read_text(), "changed")
            self.assertEqual((target / "frontend/new.js").read_text(), "new")
            self.assertFalse((target / "backend/deleted.py").exists())
            self.assertEqual(result["file_count"], 2)
            self.assertEqual(len(result["sha256"]), 64)
            self.assertEqual(
                result["files"]["backend/main.py"], hashlib.sha256(b"changed").hexdigest()
            )

    def test_routine_profile_is_bounded_for_small_team_releases(self) -> None:
        profile = load_profile(PROFILE_PATH)

        self.assertEqual(profile.schema_version, "polaris.reliability-profile.v1")
        self.assertEqual(profile.duration_seconds, 120)
        self.assertEqual(profile.offered_rps, 5)
        self.assertEqual(profile.concurrency, 8)
        self.assertEqual(profile.expected_requests, 600)
        self.assertEqual(profile.dashboard_viewport, (1440, 900))
        self.assertEqual(profile.thresholds.gateway_p95_ms, 100)
        self.assertEqual(profile.thresholds.error_rate_exclusive, 0.001)
        self.assertEqual(profile.thresholds.dashboard_usable_ms, 2_500)
        self.assertEqual(profile.thresholds.max_rss_mib, 512)

        canonical = json.dumps(
            json.loads(PROFILE_PATH.read_text(encoding="utf-8")),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(profile.digest, hashlib.sha256(canonical).hexdigest())

    def test_optional_soak_preserves_the_original_ten_minute_profile(self) -> None:
        profile = load_profile(SOAK_PROFILE_PATH)

        self.assertEqual(profile.duration_seconds, 600)
        self.assertEqual(profile.offered_rps, 10)
        self.assertEqual(profile.concurrency, 16)
        self.assertEqual(profile.expected_requests, 6_000)
        self.assertEqual(profile.thresholds, load_profile(PROFILE_PATH).thresholds)

    def test_percentile_uses_nearest_rank_and_rejects_invalid_input(self) -> None:
        self.assertEqual(percentile([40.0, 10.0, 30.0, 20.0], 0.50), 20.0)
        self.assertEqual(percentile([40.0, 10.0, 30.0, 20.0], 0.95), 40.0)
        with self.assertRaises(ValueError):
            percentile([], 0.95)
        with self.assertRaises(ValueError):
            percentile([1.0], 0.0)

    def test_memory_analysis_ignores_warmup_and_exposes_bounded_trend(self) -> None:
        samples = [
            MemorySample(elapsed_seconds=float(second), rss_bytes=(100 + second // 60) * 2**20)
            for second in range(0, 601, 5)
        ]

        trend = analyze_memory(samples, warmup_seconds=60)

        self.assertEqual(trend.sample_count, 121)
        self.assertEqual(trend.stable_sample_count, 109)
        self.assertEqual(trend.peak_rss_mib, 110.0)
        self.assertGreater(trend.growth_mib, 0)
        self.assertGreater(trend.slope_mib_per_minute, 0)
        self.assertGreater(trend.monotonic_increase_ratio, 0)

    def test_evaluation_fails_closed_on_each_release_boundary(self) -> None:
        profile = load_profile(PROFILE_PATH)
        memory = analyze_memory(
            [
                MemorySample(float(second), 128 * 2**20)
                for second in range(0, profile.duration_seconds + 1, 5)
            ],
            warmup_seconds=profile.memory_warmup_seconds,
        )
        healthy = WorkloadMetrics(
            attempted=profile.expected_requests,
            succeeded=profile.expected_requests,
            failed=0,
            elapsed_seconds=profile.duration_seconds + 0.1,
            p50_ms=12.0,
            p95_ms=25.0,
            p99_ms=40.0,
            max_in_flight=4,
            max_queue_depth=0,
            deadline_failures=0,
            response_validation_failures=0,
        )

        passing = evaluate_profile(
            profile,
            workload=healthy,
            memory=memory,
            dashboard_usable_ms=420.0,
            graceful_shutdown_seconds=0.5,
            restart_ready_seconds=1.2,
            post_restart_status=200,
            exhaustion={"quota": 0, "budget": 0, "rate_limit": 0, "cooldown": 0, "capacity": 0},
        )
        self.assertTrue(all(check.passed for check in passing))

        failing = evaluate_profile(
            profile,
            workload=replace(
                healthy,
                succeeded=profile.expected_requests - 6,
                failed=6,
                p95_ms=101.0,
                max_queue_depth=profile.max_client_queue_depth + 1,
            ),
            memory=memory,
            dashboard_usable_ms=2_501.0,
            graceful_shutdown_seconds=16.0,
            restart_ready_seconds=31.0,
            post_restart_status=503,
            exhaustion={"capacity": 1},
        )
        failed_ids = {check.id for check in failing if not check.passed}
        self.assertTrue(
            {
                "workload.error_rate",
                "workload.gateway_p95",
                "workload.client_queue",
                "gateway.exhaustion",
                "dashboard.usable",
                "restart.graceful_shutdown",
                "restart.ready",
                "restart.post_request",
            }.issubset(failed_ids)
        )

    def test_process_tree_closure_includes_nested_children_only(self) -> None:
        from tools import reliability_profile

        self.assertEqual(
            reliability_profile.descendant_process_ids(
                os.getpid(),
                (
                    (os.getpid(), 1),
                    (20_001, os.getpid()),
                    (20_002, 20_001),
                    (30_001, 99),
                ),
            ),
            {os.getpid(), 20_001, 20_002},
        )

    def test_memory_probe_cannot_pause_the_async_load_scheduler(self) -> None:
        from tools import reliability_profile

        source = inspect.getsource(reliability_profile._run_workload)
        self.assertIn(
            "await asyncio.to_thread(_process_tree_rss_bytes, pid)",
            source,
        )

    def test_dashboard_warmup_settles_before_timed_reload(self) -> None:
        from tools import reliability_profile

        source = inspect.getsource(reliability_profile._measure_dashboard)
        settled = source.index('page.wait_for_load_state("networkidle"')
        timed = source.index("started = time.perf_counter()")
        self.assertLess(settled, timed)

    def test_zero_exit_is_graceful_without_requiring_disabled_info_logs(self) -> None:
        from tools import reliability_profile

        self.assertTrue(reliability_profile.graceful_exit_completed(0))
        self.assertFalse(reliability_profile.graceful_exit_completed(None))
        self.assertFalse(reliability_profile.graceful_exit_completed(1))


class ReliabilityProfileReleaseGateTests(unittest.TestCase):
    def test_release_gate_uses_routine_and_soak_stays_optional(self) -> None:
        from tools.quality_gate import OPTIONAL_SUITES, build_gate_plan

        steps = {step.id: step for step in build_gate_plan("release")}
        reliability = steps["reliability-profile"]

        self.assertEqual(reliability.status, "active")
        self.assertEqual(reliability.owner, "PB6")
        self.assertEqual(
            reliability.commands,
            (
                (
                    "{python}",
                    "tools/reliability_profile.py",
                    "--profile",
                    "routine",
                    "--verify",
                ),
            ),
        )
        self.assertEqual(OPTIONAL_SUITES["reliability-soak"].classification, "optional")
        self.assertIn("--profile soak --verify", OPTIONAL_SUITES["reliability-soak"].command)


if __name__ == "__main__":
    unittest.main()
