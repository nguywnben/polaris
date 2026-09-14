"""Polaris public-brand and compatibility migration contracts."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PUBLIC_SOURCE_ROOTS = (
    ROOT / "frontend",
    ROOT / "backend",
    ROOT / "deploy",
    ROOT / "docs",
)
PUBLIC_TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
}
PUBLIC_ROOT_FILES = (
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    ROOT / "CODE_OF_CONDUCT.md",
    ROOT / ".env.example",
    ROOT / "render.yaml",
)


def _public_text_files() -> list[Path]:
    files = [path for path in PUBLIC_ROOT_FILES if path.is_file()]
    for source_root in PUBLIC_SOURCE_ROOTS:
        files.extend(
            path
            for path in source_root.rglob("*")
            if path.is_file()
            and path.suffix in PUBLIC_TEXT_SUFFIXES
            and "tests" not in path.parts
            and "evidence" not in path.parts
            and "migrations" not in path.parts
        )
    return files


class ProductRebrandContractTests(unittest.TestCase):
    def test_public_product_name_is_polaris(self):
        stale: list[str] = []
        for path in _public_text_files():
            if "Omni Gateway" in path.read_text(encoding="utf-8"):
                stale.append(path.relative_to(ROOT).as_posix())

        self.assertEqual(stale, [])
        self.assertIn(
            "Polaris",
            (ROOT / "frontend" / "fragments" / "layout" / "sidebar.html").read_text(
                encoding="utf-8"
            ),
        )

    def test_canonical_repository_and_container_names_are_polaris(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
        compose_environment = (ROOT / "deploy" / "compose.env.example").read_text(encoding="utf-8")
        dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
        version_endpoint = (ROOT / "backend" / "core" / "panel" / "version.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("github.com/nguywnben/polaris", readme)
        self.assertIn("hub.docker.com/r/nguywnben/polaris", readme)
        self.assertIn("ghcr.io/nguywnben/polaris", readme)
        self.assertIn("${IMAGE:-nguywnben/polaris:latest}", compose)
        self.assertIn("${DATA_VOLUME:-polaris-data}", compose)
        self.assertIn("IMAGE=nguywnben/polaris:", compose_environment)
        self.assertIn("DATA_VOLUME=polaris-data", compose_environment)
        self.assertIn('org.opencontainers.image.title="Polaris"', dockerfile)
        self.assertIn("github.com/nguywnben/polaris", dockerfile)
        self.assertIn("repos/nguywnben/polaris/releases/latest", version_endpoint)

    def test_new_install_and_observability_defaults_use_polaris(self):
        configuration = (ROOT / "backend" / "config.py").read_text(encoding="utf-8")
        paths = (ROOT / "backend" / "paths.py").read_text(encoding="utf-8")
        telemetry = (ROOT / "backend" / "core" / "otel_exporter.py").read_text(encoding="utf-8")
        render = (ROOT / "deploy" / "render.yaml").read_text(encoding="utf-8")
        install = (ROOT / "deploy" / "scripts" / "install.sh").read_text(encoding="utf-8")
        playground = (ROOT / "frontend" / "js" / "features" / "playground.js").read_text(
            encoding="utf-8"
        )
        installation = (ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
        updater = (ROOT / "tools" / "compose_update.py").read_text(encoding="utf-8")

        self.assertIn('DEFAULT_XAI_USER_AGENT = "grok-cli/polaris"', configuration)
        self.assertIn('DEFAULT_CLAUDE_USER_AGENT = "claude-cli/polaris"', configuration)
        self.assertIn('DEFAULT_LOG_FILE = DEFAULT_LOGS_DIR / "polaris.log"', paths)
        self.assertIn('"service.name", "value": {"stringValue": "polaris"}', telemetry)
        self.assertIn("name: polaris", render)
        self.assertIn('PROJECT_DIR="${PROJECT_DIR:-polaris}"', install)
        self.assertIn("<YOUR_POLARIS_KEY>", playground)
        self.assertIn("cd polaris", installation)
        self.assertIn('Path.home() / ".polaris" / "recovery"', updater)

    def test_container_publish_keeps_temporary_legacy_aliases(self):
        workflow = (ROOT / ".github" / "workflows" / "docker-publish.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("DOCKERHUB_IMAGE: nguywnben/polaris", workflow)
        self.assertIn("GHCR_IMAGE: ghcr.io/nguywnben/polaris", workflow)
        self.assertIn("LEGACY_DOCKERHUB_IMAGE: nguywnben/omni-gateway", workflow)
        self.assertIn("LEGACY_GHCR_IMAGE: ghcr.io/nguywnben/omni-gateway", workflow)
        self.assertIn("${{ env.LEGACY_DOCKERHUB_IMAGE }}", workflow)
        self.assertIn("${{ env.LEGACY_GHCR_IMAGE }}", workflow)

    def test_migration_guide_documents_stable_legacy_contracts(self):
        guide = ROOT / "docs" / "migrations" / "polaris.md"

        self.assertTrue(guide.is_file())
        content = guide.read_text(encoding="utf-8")
        for marker in (
            "sk-ogw-",
            "omway",
            "OMNI_RUNTIME_MODE",
            "omni-gateway-data",
            "nguywnben/polaris",
            "ghcr.io/nguywnben/polaris",
        ):
            self.assertIn(marker, content)

    def test_stable_client_contracts_remain_compatible_during_rebrand(self):
        configuration = (ROOT / "backend" / "config.py").read_text(encoding="utf-8")
        model_pool = (ROOT / "backend" / "core" / "model_pool.py").read_text(encoding="utf-8")

        self.assertIn('API_KEY_PREFIX = "sk-ogw-"', configuration)
        self.assertIn('DEFAULT_VIRTUAL_MODEL_ALIAS = "omway"', model_pool)


if __name__ == "__main__":
    unittest.main()
