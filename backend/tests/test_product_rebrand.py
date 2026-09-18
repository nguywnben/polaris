"""Polaris product identity and breaking cutover contracts."""

from __future__ import annotations

import re
import subprocess
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

# RR5: the owner explicitly retained legacy release provenance on 2026-09-18.
# Only historical prose/archive refs in these records are allowed, not old runtime
# aliases, environment names, API keys or product names elsewhere.
HISTORICAL_RELEASE_RECORDS = {
    "CHANGELOG.md",
    "docs/audits/release-readiness-2026-09-18.md",
    "docs/releases/1.0.0-preparation.md",
    "docs/releases/1.0.0-registry-inventory.md",
    "docs/releases/tag-migration-2026-09-18.md",
    "tasks/current.md",
    "tasks/release-readiness-2026-09-18.md",
}


def _without_historical_release_mentions(relative_path: str, content: str) -> str:
    if relative_path not in HISTORICAL_RELEASE_RECORDS:
        return content
    content = re.sub(r"Om" + r"ni\s+Gateway", "Legacy product", content)
    return content.replace("om" + "ni-gateway/", "archived/")


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
    def test_historical_exemption_does_not_allow_runtime_legacy_identifiers(self):
        historical = "Om" + "ni Gateway: om" + "ni-gateway/v1.0.0"
        self.assertEqual(
            _without_historical_release_mentions("CHANGELOG.md", historical),
            "Legacy product: archived/v1.0.0",
        )
        for path in ("backend/config.py", "frontend/index.html", "README.md"):
            self.assertEqual(_without_historical_release_mentions(path, historical), historical)
        identifiers = "OM" + "NI_API_KEY sk-og" + "w-example om" + "ni-gateway:1.0.0"
        self.assertEqual(
            _without_historical_release_mentions("CHANGELOG.md", identifiers), identifiers
        )

    def test_tracked_text_has_no_legacy_product_identifiers(self):
        tracked = (
            subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            )
            .stdout.decode("utf-8")
            .split("\0")
        )
        legacy_pattern = re.compile(
            "|".join(
                (
                    r"\bom" + r"ni(?:[\s._-]|$)",
                    r"\bom" + r"way\b",
                    r"\bsk-" + r"og" + r"w-",
                    r"\bog" + r"w(?:[\s._-]|$)",
                )
            ),
            re.IGNORECASE,
        )
        stale: dict[str, list[str]] = {}

        for relative_path in filter(None, tracked):
            path = ROOT / relative_path
            # Include new files while allowing tracked files removed by an unstaged rename.
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            content = _without_historical_release_mentions(relative_path, content)
            matches = sorted({match.group(0) for match in legacy_pattern.finditer(content)})
            if matches:
                stale[relative_path] = matches

        self.assertEqual(stale, {})

    def test_public_product_name_is_polaris(self):
        stale: list[str] = []
        for path in _public_text_files():
            content = _without_historical_release_mentions(
                path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8")
            )
            if "Om" + "ni Gateway" in content:
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
        self.assertIn("${IMAGE:-nguywnben/polaris:1.0.0}", compose)
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
        environment_example = (ROOT / ".env.example").read_text(encoding="utf-8")
        audit_service = (ROOT / "backend" / "core" / "audit_service.py").read_text(encoding="utf-8")

        self.assertIn('DEFAULT_XAI_USER_AGENT = "grok-cli/polaris"', configuration)
        self.assertIn('DEFAULT_CLAUDE_USER_AGENT = "claude-cli/polaris"', configuration)
        self.assertIn('DEFAULT_LOG_FILE = DEFAULT_LOGS_DIR / "polaris.log"', paths)
        self.assertIn('"service.name", "value": {"stringValue": "polaris"}', telemetry)
        self.assertIn("name: polaris", render)
        self.assertIn('PROJECT_DIR="${PROJECT_DIR:-polaris}"', install)
        self.assertIn("<YOUR_POLARIS_KEY>", playground)
        self.assertIn("cd polaris", installation)
        self.assertIn('Path.home() / ".polaris" / "recovery"', updater)
        self.assertIn("OIDC_CLIENT_ID=polaris", environment_example)
        self.assertIn("/run/secrets/polaris-oidc", environment_example)
        self.assertIn('actor_identifier="polaris"', audit_service)

    def test_container_publish_uses_only_canonical_names(self):
        workflow = (ROOT / ".github" / "workflows" / "docker-publish.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("DOCKERHUB_IMAGE: ${{ vars.IMAGE_NAME || 'nguywnben/polaris' }}", workflow)
        self.assertIn("GHCR_IMAGE: ghcr.io/nguywnben/polaris", workflow)
        self.assertNotIn("LEGACY_DOCKERHUB_IMAGE", workflow)
        self.assertNotIn("LEGACY_GHCR_IMAGE", workflow)

    def test_client_contracts_use_canonical_polaris_identifiers(self):
        configuration = (ROOT / "backend" / "config.py").read_text(encoding="utf-8")
        model_pool = (ROOT / "backend" / "core" / "model_pool.py").read_text(encoding="utf-8")

        self.assertIn('API_KEY_PREFIX = "sk-polaris-"', configuration)
        self.assertIn('DEFAULT_VIRTUAL_MODEL_ALIAS = "polaris"', model_pool)


if __name__ == "__main__":
    unittest.main()
