"""Contract tests for the reproducible P0.4 maintainability baseline."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from tools.maintainability_inventory import INVENTORY_CATEGORIES, build_inventory

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / "docs" / "audits" / "maintainability-baseline.json"


class MaintainabilityBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    def test_current_inventory_improves_without_rewriting_historical_baseline(self) -> None:
        historical = self.baseline["inventory"]
        current = build_inventory(ROOT)

        self.assertEqual(self.baseline["profile"], "PROD-SELFHOST-R1")
        self.assertFalse(current["pydantic_deprecations"])
        self.assertLessEqual(
            current["broad_exception_handlers"]["handlers"],
            historical["broad_exception_handlers"]["handlers"],
        )
        self.assertNotIn(
            "experimental_coordination", current["broad_exception_handlers"]["by_area"]
        )
        self.assertIn("runtime_coordination", current["broad_exception_handlers"]["by_area"])
        current_paths = {module["path"] for module in current["large_modules"]["modules"]} | set(
            current["skipped_and_live_tests"]["live_modules"]
        )
        self.assertFalse(any("redis" in path or "ha_topology" in path for path in current_paths))

    def test_all_required_categories_have_inventory_and_risk_ownership(self) -> None:
        self.assertEqual(set(self.baseline["inventory"]), set(INVENTORY_CATEGORIES))
        covered = {risk["category"] for risk in self.baseline["risks"]}
        self.assertEqual(covered, set(INVENTORY_CATEGORIES))

    def test_every_risk_has_an_existing_plan_owner(self) -> None:
        plan = (ROOT / "tasks" / "plan.md").read_text(encoding="utf-8")
        valid_owners = set(re.findall(r"^### (P[0-5]\.[1-6])\b", plan, flags=re.MULTILINE))
        valid_owners.add("POST-R1")

        high_risks = 0
        for risk in self.baseline["risks"]:
            owners = risk.get("owners", [])
            self.assertTrue(owners, risk["id"])
            self.assertTrue(set(owners).issubset(valid_owners), risk["id"])
            if risk["severity"] in {"critical", "high"}:
                high_risks += 1
        self.assertGreater(high_risks, 0)

    def test_file_size_does_not_authorize_refactoring(self) -> None:
        large_module_risks = [
            risk for risk in self.baseline["risks"] if risk["category"] == "large_modules"
        ]
        self.assertTrue(large_module_risks)
        for risk in large_module_risks:
            self.assertFalse(risk["file_size_refactor_authorized"], risk["id"])

    def test_cli_emits_the_current_inventory(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "maintainability_inventory.py")],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), build_inventory(ROOT))


if __name__ == "__main__":
    unittest.main()
