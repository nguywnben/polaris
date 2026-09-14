"""Release metadata and maintained-documentation contracts for 1.5.0."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from backend.app_version import DEFAULT_APPLICATION_VERSION

ROOT = Path(__file__).resolve().parents[2]
RELEASE_VERSION = "1.5.0"
RELEASE_DATE = "2026-09-12"
MAINTAINED_DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "SECURITY.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "docs" / "architecture.md",
    ROOT / "docs" / "identity-console.md",
    ROOT / "docs" / "identity-management-api.md",
    ROOT / "docs" / "identity-repository.md",
    ROOT / "docs" / "installation.md",
    ROOT / "docs" / "management-sessions.md",
    ROOT / "docs" / "oidc-foundation.md",
    ROOT / "docs" / "updating.md",
    ROOT / "docs" / "backup-and-restore.md",
    ROOT / "docs" / "troubleshooting.md",
    ROOT / "docs" / "quality-gates.md",
    ROOT / "docs" / "release-checklist.md",
    ROOT / "docs" / "reference" / "configuration.md",
    ROOT / "docs" / "storage.md",
    ROOT / "docs" / "observability.md",
    ROOT / "docs" / "compatibility.md",
)


class ReleaseCandidateContractTests(unittest.TestCase):
    def test_release_version_is_consistent_across_runtime_install_and_changelog(self):
        self.assertEqual(DEFAULT_APPLICATION_VERSION, RELEASE_VERSION)

        compose_environment = (ROOT / "deploy" / "compose.env.example").read_text(encoding="utf-8")
        self.assertIn(f"IMAGE=nguywnben/polaris:{RELEASE_VERSION}", compose_environment)

        installation = (ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
        self.assertIn(f"current `{RELEASE_VERSION}` release", installation)
        self.assertIn(f"--branch v{RELEASE_VERSION}", installation)
        self.assertNotIn("1.4.0", installation)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"pins release `{RELEASE_VERSION}`", readme)
        self.assertNotIn("1.4.0", readme)

        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"## [{RELEASE_VERSION}] - {RELEASE_DATE}", changelog)
        self.assertIn(
            f"[Unreleased]: https://github.com/nguywnben/polaris/compare/v{RELEASE_VERSION}...HEAD",
            changelog,
        )
        self.assertIn(
            f"[{RELEASE_VERSION}]: https://github.com/nguywnben/polaris/compare/v1.4.0...v{RELEASE_VERSION}",
            changelog,
        )

    def test_maintained_document_links_resolve_inside_the_repository(self):
        markdown_link = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
        missing: list[str] = []
        for document in MAINTAINED_DOCUMENTS:
            self.assertTrue(document.is_file(), document.relative_to(ROOT).as_posix())
            source = document.read_text(encoding="utf-8")
            for raw_target in markdown_link.findall(source):
                target = raw_target.strip().split("#", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                linked_path = (document.parent / target).resolve()
                if not linked_path.is_file() and not linked_path.is_dir():
                    missing.append(f"{document.relative_to(ROOT).as_posix()} -> {raw_target}")

        self.assertEqual(missing, [])

    def test_release_handoff_documents_recovery_and_support_boundaries(self):
        troubleshooting = (ROOT / "docs" / "troubleshooting.md").read_text(encoding="utf-8")
        for marker in (
            "GET /health",
            "GET /ready",
            "X-Request-ID",
            "Explicit rollback",
            "Do not delete the data volume",
        ):
            self.assertIn(marker, troubleshooting)

        architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
        self.assertNotIn("W4.", architecture)
        self.assertNotIn("remains subject to checkpoint", architecture)
        self.assertIn("Standalone coordination boundary", architecture)


if __name__ == "__main__":
    unittest.main()
