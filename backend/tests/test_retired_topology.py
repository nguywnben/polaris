from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.capability_registry import get_capability_snapshot
from core.configuration_schema import CONFIGURATION_FIELDS


class RetiredTopologyContractTests(unittest.TestCase):
    def test_unreachable_topology_implementation_and_assets_are_removed(self) -> None:
        retired_paths = (
            "backend/core/redis_state_store.py",
            "backend/core/quota_redis_scripts.py",
            "backend/core/ha_activation.py",
            "backend/core/ha_coordination_binding.py",
            "backend/core/ha_operator.py",
            "backend/core/ha_reconciliation.py",
            "backend/core/ha_runtime.py",
            "backend/core/ha_runtime_policy.py",
            "backend/ha_admin.py",
            "backend/ha_evidence.py",
            "tools/ha_topology_evidence",
            "deploy/evidence/compose.ha.yml",
            "deploy/evidence/redis-primary.conf",
            "deploy/evidence/redis-standby.conf",
            "deploy/helm/polaris",
            "docs/runbooks/high-availability.md",
        )

        remaining = []
        for path in retired_paths:
            candidate = ROOT / path
            if candidate.is_file():
                remaining.append(path)
            elif candidate.is_dir() and any(
                item.is_file() and "__pycache__" not in item.parts for item in candidate.rglob("*")
            ):
                remaining.append(path)
        self.assertEqual(remaining, [])

    def test_product_and_configuration_no_longer_advertise_retired_topology(self) -> None:
        capability_ids = {capability.id for capability in get_capability_snapshot({}).capabilities}
        self.assertNotIn("deployment.kubernetes", capability_ids)
        self.assertNotIn("runtime.coordinated", capability_ids)
        self.assertNotIn("runtime.multiple_replicas", capability_ids)

        for name in (
            "REDIS_URL",
            "POLARIS_COORDINATION_NAMESPACE",
            "POLARIS_DEPLOYMENT_ID",
            "POLARIS_COORDINATION_KEY",
            "POLARIS_COORDINATION_EPOCH",
            "POLARIS_EXPERIMENTAL_COORDINATION",
        ):
            self.assertNotIn(name, CONFIGURATION_FIELDS)

    def test_core_install_has_no_redis_dependency_or_configuration(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        advanced_compose = (ROOT / "deploy" / "compose.advanced.yml").read_text(encoding="utf-8")
        environment_example = (ROOT / ".env.example").read_text(encoding="utf-8")

        self.assertNotRegex(requirements, r"(?m)^redis(?:\[|=|<|>|$)")
        self.assertNotIn("REDIS_URL", advanced_compose)
        self.assertNotIn("POLARIS_RUNTIME_MODE=coordinated", environment_example)


if __name__ == "__main__":
    unittest.main()
