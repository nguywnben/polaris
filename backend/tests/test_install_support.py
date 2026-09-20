"""Contracts for the Production Self-Hosted R1 installation surface."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from backend.app_version import DEFAULT_APPLICATION_VERSION

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "deploy" / "install-support.json"
GUIDE_PATH = ROOT / "docs" / "installation.md"
ENV_TEMPLATE_PATH = ROOT / "deploy" / "compose.env.example"

CANONICAL_HOSTS = {
    "windows-docker-desktop-wsl2": ("core", "local-runtime"),
    "linux-docker-engine": ("core", "required-ci"),
    "macos-docker-desktop": ("core", "manual-check"),
}

COMPATIBILITY_SCRIPTS = {
    "deploy/scripts/install.ps1",
    "deploy/scripts/install.sh",
    "deploy/scripts/macos-install.sh",
    "deploy/scripts/start.bat",
    "deploy/scripts/start.sh",
    "deploy/scripts/termux-install.sh",
    "deploy/scripts/termux-start.sh",
}


def _matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


class InstallSupportContractTests(unittest.TestCase):
    def test_matrix_has_one_canonical_compose_contract(self):
        matrix = _matrix()
        canonical = matrix["canonical"]

        self.assertEqual(matrix["schema_version"], 1)
        self.assertEqual(canonical["deployment"], "docker-compose")
        self.assertEqual(canonical["compose_file"], "deploy/docker-compose.yml")
        self.assertEqual(canonical["environment_template"], "deploy/compose.env.example")
        self.assertEqual(canonical["guide"], "docs/installation.md")
        self.assertEqual(canonical["workers"], 1)
        self.assertEqual(canonical["replicas"], 1)

    def test_host_support_and_verification_statuses_are_explicit(self):
        hosts = {host["id"]: host for host in _matrix()["hosts"]}

        self.assertEqual(set(hosts), set(CANONICAL_HOSTS))
        for host_id, (tier, verification) in CANONICAL_HOSTS.items():
            self.assertEqual(hosts[host_id]["tier"], tier)
            self.assertEqual(hosts[host_id]["verification"], verification)
            self.assertTrue(hosts[host_id]["prerequisites"])
            self.assertTrue(hosts[host_id]["known_differences"])

    def test_architecture_claim_matches_the_publishing_workflow(self):
        architectures = {item["platform"]: item for item in _matrix()["architectures"]}
        workflow = (ROOT / ".github" / "workflows" / "docker-publish.yml").read_text(
            encoding="utf-8"
        )

        self.assertEqual(architectures["linux/amd64"]["status"], "published-supported")
        self.assertEqual(architectures["linux/arm64"]["status"], "not-published")
        self.assertIn("platforms: linux/amd64", workflow)
        self.assertNotRegex(workflow, re.compile(r"platforms:\s*[^\n]*arm64"))

    def test_every_user_facing_native_script_is_classified_and_self_labels(self):
        alternatives = {item["path"]: item for item in _matrix()["alternatives"]}
        user_facing_scripts = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "deploy" / "scripts").iterdir()
            if path.is_file() and path.name != "docker-entrypoint.sh"
        }

        guided = _matrix()["guided"]
        self.assertEqual(
            user_facing_scripts,
            COMPATIBILITY_SCRIPTS | {guided["installer"], guided["powershell_installer"]},
        )
        self.assertTrue((ROOT / guided["powershell_installer"]).is_file())
        self.assertTrue(guided["powershell_requires"])
        self.assertIn("manual-check-pending", guided["macos_verification"])
        self.assertEqual(guided["deployment"], "docker-run")
        self.assertEqual(guided["target"], "linux/amd64")
        self.assertTrue(guided["no_clone_required"])
        self.assertFalse(guided["compose_updater_supported"])
        self.assertTrue((ROOT / guided["guide"]).is_file())
        self.assertEqual(
            {path for path in alternatives if path.startswith("deploy/scripts/")},
            COMPATIBILITY_SCRIPTS,
        )
        for path in COMPATIBILITY_SCRIPTS:
            self.assertEqual(alternatives[path]["tier"], "compatibility")
            prefix = (ROOT / path).read_text(encoding="utf-8")[:500]
            self.assertIn("Compatibility path", prefix)
            self.assertIn("docs/installation.md", prefix)

    def test_compose_environment_template_is_minimal_and_pinned(self):
        values = {}
        for raw_line in ENV_TEMPLATE_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            values[key] = value

        self.assertEqual(
            set(values),
            {
                "IMAGE",
                "HOST_PORT",
                "DATA_VOLUME",
                "LOG_LEVEL",
                "API_KEY",
                "PANEL_PASSWORD",
                "SETUP_TOKEN",
                "SETUP_ALLOW_INSECURE_HTTP",
            },
        )
        self.assertRegex(
            values["IMAGE"],
            r"^nguywnben/polaris:\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$",
        )
        self.assertEqual(values["IMAGE"], f"nguywnben/polaris:{DEFAULT_APPLICATION_VERSION}")
        self.assertEqual(values["HOST_PORT"], "4283")
        self.assertEqual(values["DATA_VOLUME"], "polaris-data")
        self.assertEqual(values["API_KEY"], "")
        self.assertEqual(values["PANEL_PASSWORD"], "")
        self.assertEqual(values["SETUP_TOKEN"], "")
        self.assertEqual(values["SETUP_ALLOW_INSECURE_HTTP"], "false")

    def test_guided_platform_docs_distinguish_source_from_publication(self):
        guide = (ROOT / "docs/docker-install.md").read_text(encoding="utf-8")
        self.assertIn("### Windows (PowerShell)", guide)
        self.assertIn("### Linux / macOS Intel (Bash)", guide)
        self.assertIn("Source-ready, not published yet", guide)
        self.assertIn("RELEASE_TAG/deploy/scripts/docker-install.ps1", guide)
        self.assertNotIn("v1.0.0/deploy/scripts/docker-install.ps1", guide)
        self.assertIn("Invoke-RestMethod", guide)
        self.assertIn("-ErrorAction Stop", guide)
        self.assertIn("Native Mac verification is **pending**", guide)
        self.assertIn("docker-maintenance.md", guide)
        evidence = _matrix()["guided"]["powershell_runtime_evidence"]
        self.assertTrue((ROOT / evidence).is_file())

    def test_install_guide_is_one_ordered_path_to_authenticated_health(self):
        guide = GUIDE_PATH.read_text(encoding="utf-8")
        markers = (
            "## 1. Check the host",
            "## 2. Download one release",
            "## 3. Create the minimal configuration",
            "## 4. Start and wait for readiness",
            "## 5. Complete first-run setup",
            "## 6. Verify authenticated operation",
        )

        offsets = [guide.index(marker) for marker in markers]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn("docker compose -f deploy/docker-compose.yml config --quiet", guide)
        self.assertIn(
            "docker compose -f deploy/docker-compose.yml up --detach --wait --wait-timeout 60",
            guide,
        )
        self.assertIn("http://127.0.0.1:4283/ready", guide)
        self.assertIn("http://127.0.0.1:4283/dashboard", guide)
        self.assertIn("linux/arm64", guide)
        self.assertIn("not published", guide.lower())

    def test_readme_routes_production_installers_to_the_canonical_guide(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("[Canonical installation guide](docs/installation.md)", readme)
        self.assertIn("[Installation support matrix](docs/installation.md#support-matrix)", readme)
        self.assertIn("Compatibility-only native scripts", readme)

        vietnamese = (ROOT / "docs" / "locales" / "README.vi.md").read_text(encoding="utf-8")
        self.assertIn("[Hướng dẫn cài đặt chuẩn](../installation.md)", vietnamese)
        self.assertIn("[Ma trận hỗ trợ cài đặt](../installation.md#support-matrix)", vietnamese)

    def test_all_readmes_describe_guided_install_and_complete_volume_storage(self):
        documents = [ROOT / "README.md", *(ROOT / "docs/locales").glob("README.*.md")]
        self.assertEqual(len(documents), 15)
        for document in documents:
            with self.subTest(document=document.name):
                source = document.read_text(encoding="utf-8")
                self.assertIn("docker-install.md)", source)
                self.assertIn("docker-maintenance.md)", source)
                self.assertIn("`/app/backend/data`", source)
                self.assertNotIn("`/opt/polaris/creds`", source)


if __name__ == "__main__":
    unittest.main()
