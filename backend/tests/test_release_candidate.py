"""Release preparation, publication safety and maintained-documentation contracts."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

from backend.app_version import DEFAULT_APPLICATION_VERSION

ROOT = Path(__file__).resolve().parents[2]
RELEASE_VERSION = "1.0.0"
RELEASE_DATE = "2026-09-18"
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
        self.assertIn(f"prepares `{RELEASE_VERSION}`", installation)
        self.assertIn("Do not run the release download/pull commands yet", installation)
        self.assertIn(f"--branch v{RELEASE_VERSION}", installation)
        self.assertNotIn("1.4.0", installation)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"targets `{RELEASE_VERSION}`", readme)
        self.assertNotIn("1.4.0", readme)

        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"## [{RELEASE_VERSION}] - {RELEASE_DATE}", changelog)
        self.assertIn(
            "[Unreleased]: https://github.com/nguywnben/polaris/compare/v0.1.0-beta...HEAD",
            changelog,
        )
        self.assertIn(
            f"[{RELEASE_VERSION}]: docs/releases/1.0.0-preparation.md",
            changelog,
        )
        self.assertEqual(changelog.count(f"## [{RELEASE_VERSION}]"), 1)
        self.assertIn("## [1.0.0 (legacy)] - 2026-07-13", changelog)
        self.assertEqual(changelog.count("## [0.1.0-beta]"), 1)
        self.assertIn("## [0.1.0-beta (legacy)] - 2026-07-08", changelog)
        self.assertIn(
            "[0.1.0-beta (legacy)]: https://github.com/nguywnben/polaris/releases/tag/"
            + "omni"
            + "-gateway/v0.1.0-beta",
            changelog,
        )

    def test_all_readmes_distinguish_offline_import_and_unpublished_target(self):
        documents = [ROOT / "README.md", *sorted((ROOT / "docs/locales").glob("README.*.md"))]
        self.assertEqual(len(documents), 15)
        for document in documents:
            with self.subTest(document=document.name):
                source = document.read_text(encoding="utf-8")
                self.assertIn("`unverified`", source)
                self.assertIn("1.0.0-preparation.md", source)
                self.assertIn("`1.0.0`", source)

    def test_publication_rejects_wrong_version_ambiguous_and_unreleased_notes(self):
        from tools.release_preflight import release_notes

        valid = "## [1.0.0] - 2026-09-18\n\n### Fixed\n\n- Safe fix.\n\n## [old]\n"
        self.assertIn("Safe fix.", release_notes(valid, "v1.0.0", "1.0.0"))
        for source, tag in (
            (valid, "v1.1.0"),
            (valid, "1.0.0"),
            (valid + valid, "v1.0.0"),
            (valid.replace("2026-09-18", "Unreleased"), "v1.0.0"),
            (valid.replace("2026-09-18", "2026-02-31"), "v1.0.0"),
            ("## [1.0.0] - 2026-09-18\n\n## [old]", "v1.0.0"),
        ):
            with self.subTest(source=source, tag=tag), self.assertRaises(ValueError):
                release_notes(source, tag, "1.0.0")

    def test_container_publication_checks_metadata_before_registry_login(self):
        workflow = (ROOT / ".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
        self.assertLess(
            workflow.index("tools/release_preflight.py"), workflow.index("Log in to Docker Hub")
        )
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", workflow)

    def test_manual_ci_never_publishes_containers_or_releases(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        jobs = workflow["jobs"]
        self.assertEqual(
            jobs["publish-container"]["if"],
            "${{ github.event_name == 'push' && (github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v')) }}",
        )
        self.assertEqual(
            jobs["publish-release"]["if"],
            "${{ github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v') }}",
        )
        self.assertEqual(
            set(jobs["publish-container"]["needs"]),
            {"verify", "browser-smoke", "container-smoke"},
        )

    def test_stable_release_explicitly_becomes_latest_after_version_restart(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        script = workflow["jobs"]["publish-release"]["steps"][-1]["run"]
        self.assertRegex(
            script,
            r"(?s)if \[\[ .*? \]\]; then\s+release_args\+=\(--prerelease\)\s+else\s+release_args\+=\(--latest\)\s+fi",
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
