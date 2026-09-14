"""Contracts for the fixed P0.5 task, phase, release, and optional gates."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from tools.quality_gate import OPTIONAL_SUITES, build_gate_plan

ROOT = Path(__file__).resolve().parents[2]


class QualityGatePlanTests(unittest.TestCase):
    def test_fast_gate_is_static_and_does_not_run_the_complete_core_suite(self) -> None:
        step_ids = {step.id for step in build_gate_plan("fast")}

        self.assertTrue(
            {
                "backend-lint",
                "backend-format",
                "python-compile",
                "test-partition",
                "javascript-syntax",
                "yaml-syntax",
                "shell-syntax",
                "whitespace",
            }.issubset(step_ids)
        )
        self.assertNotIn("core-suite", step_ids)

    def test_task_gate_requires_explicit_core_test_modules(self) -> None:
        with self.assertRaisesRegex(ValueError, "focused test module"):
            build_gate_plan("task")
        with self.assertRaisesRegex(ValueError, "production core suite"):
            build_gate_plan("task", ("backend.tests.test_missing_module",))

        plan = build_gate_plan("task", ("backend.tests.test_quality_gates",))
        self.assertEqual(plan[-1].id, "focused-tests")

    def test_phase_gate_adds_config_translation_and_only_the_affected_slice(self) -> None:
        plan = build_gate_plan("phase", ("backend.tests.test_quality_gates",))
        step_ids = {step.id for step in plan}
        configuration = next(step for step in plan if step.id == "configuration-contracts")

        self.assertIn("configuration-contracts", step_ids)
        self.assertIn("backend.tests.test_compatibility_guard", configuration.commands[0])
        self.assertIn("translation-audit", step_ids)
        self.assertIn("focused-tests", step_ids)
        self.assertNotIn("core-suite", step_ids)

    def test_release_gate_has_every_required_dimension_but_no_optional_suite(self) -> None:
        plan = build_gate_plan("release")
        steps = {step.id: step for step in plan}

        expected = {
            "backend-lint",
            "backend-format",
            "python-compile",
            "configuration-contracts",
            "javascript-syntax",
            "translation-audit",
            "dependency-compatibility",
            "dependency-audit",
            "core-suite",
            "application-smoke",
            "browser-smoke",
            "reliability-profile",
            "container-smoke",
            "whitespace",
        }
        self.assertTrue(expected.issubset(steps))
        self.assertEqual(steps["browser-smoke"].status, "active")
        self.assertEqual(steps["browser-smoke"].owner, "P5.4")
        self.assertEqual(
            steps["browser-smoke"].commands,
            (("{python}", "tools/browser_smoke.py"),),
        )
        self.assertEqual(steps["container-smoke"].status, "ci")
        self.assertTrue(set(OPTIONAL_SUITES).isdisjoint(steps))

    def test_optional_suites_are_separate_and_explicit(self) -> None:
        self.assertEqual(
            set(OPTIONAL_SUITES),
            {"storage-live", "provider-live", "reliability-soak"},
        )
        self.assertEqual(OPTIONAL_SUITES["storage-live"].classification, "optional")
        self.assertEqual(OPTIONAL_SUITES["provider-live"].mode, "manual")
        self.assertEqual(OPTIONAL_SUITES["reliability-soak"].mode, "automated")

    def test_release_dry_run_and_suite_listing_do_not_execute_checks(self) -> None:
        dry_run = subprocess.run(
            [sys.executable, "tools/quality_gate.py", "release", "--dry-run"],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )
        suites = subprocess.run(
            [sys.executable, "tools/quality_gate.py", "--list-suites"],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )

        self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
        self.assertIn("browser-smoke [active; owner=P5.4]", dry_run.stdout)
        self.assertIn("container-smoke [ci]", dry_run.stdout)
        self.assertEqual(suites.returncode, 0, suites.stderr)
        self.assertIn("storage-live [optional]", suites.stdout)
        self.assertIn("provider-live [optional; manual]", suites.stdout)
        self.assertIn("reliability-soak [optional]", suites.stdout)

    def test_phase_cli_can_resolve_a_core_module_from_the_tools_entrypoint(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "tools/quality_gate.py",
                "phase",
                "--test-module",
                "backend.tests.test_quality_gates",
                "--list",
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("focused-tests [active]", completed.stdout)


class QualityGateDocumentationTests(unittest.TestCase):
    def test_ci_and_docs_name_the_fixed_required_gates(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        checklist = (ROOT / "docs" / "release-checklist.md").read_text(encoding="utf-8")

        self.assertIn("Required: fast gate", workflow)
        self.assertIn("Required: production core tests", workflow)
        self.assertIn("Required: browser smoke", workflow)
        self.assertIn("Required: container smoke", workflow)
        self.assertIn("requirements-browser.txt", workflow)
        self.assertIn("python -m playwright install --with-deps chromium", workflow)
        self.assertIn("python tools/browser_smoke.py", workflow)
        self.assertNotIn("--suite experimental-ha", workflow)
        self.assertNotIn("playwright install firefox", workflow)
        self.assertNotIn("playwright install webkit", workflow)
        self.assertIn("python tools/quality_gate.py task --test-module", contributing)
        self.assertIn("python tools/quality_gate.py release", checklist)
        self.assertIn("--profile routine --verify", checklist)
        self.assertIn("--profile soak --verify", checklist)
        self.assertIn("release-blocking routine", checklist)
        self.assertIn("Optional soak", checklist)

    def test_browser_dependency_is_isolated_and_exactly_pinned(self) -> None:
        browser_requirements = (ROOT / "requirements-browser.txt").read_text(encoding="utf-8")

        self.assertEqual(browser_requirements.strip(), "playwright==1.62.0")


if __name__ == "__main__":
    unittest.main()
