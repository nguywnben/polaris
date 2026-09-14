"""Static contract for the production self-hosted product surface inventory."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

INVENTORY_PATH = ROOT / "docs" / "audits" / "product-surface-inventory.json"
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}


def _load_inventory() -> dict[str, object]:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _matches(pattern: str, value: str) -> bool:
    return re.fullmatch(pattern, value) is not None


class ProductSurfaceInventoryTests(unittest.TestCase):
    def test_inventory_has_a_supported_owner_journey_for_every_entry(self) -> None:
        inventory = _load_inventory()
        self.assertEqual(inventory["schema_version"], 1)
        self.assertEqual(inventory["profile"], "self_hosted")
        self.assertEqual(
            set(inventory["support_tiers"]),
            {"core", "advanced", "compatibility", "experimental"},
        )
        for collection in (
            "pages",
            "route_groups",
            "settings_controls",
            "environment_groups",
            "advertised_claims",
        ):
            entries = inventory[collection]
            self.assertTrue(entries, collection)
            identifiers = [entry["id"] for entry in entries]
            self.assertEqual(len(identifiers), len(set(identifiers)), collection)
            for entry in entries:
                with self.subTest(collection=collection, entry=entry["id"]):
                    self.assertIn(entry["tier"], inventory["support_tiers"])
                    self.assertIn(entry["journey"], inventory["owner_journeys"])

    def test_every_page_fragment_and_sidebar_tab_is_inventoried(self) -> None:
        inventory = _load_inventory()
        pages = inventory["pages"]
        fragments = {
            path.name for path in (ROOT / "frontend" / "fragments" / "pages").glob("*.html")
        }
        sidebar = (ROOT / "frontend" / "fragments" / "layout" / "sidebar.html").read_text(
            encoding="utf-8"
        )
        tabs = set(re.findall(r'data-tab="([^"]+)"', sidebar))

        self.assertEqual({entry["fragment"] for entry in pages}, fragments)
        self.assertEqual({entry["tab"] for entry in pages}, tabs)

    def test_every_openapi_operation_matches_exactly_one_route_group(self) -> None:
        from main import app

        inventory = _load_inventory()
        groups = inventory["route_groups"]
        operations = {
            (method.upper(), path)
            for path, path_item in app.openapi()["paths"].items()
            for method in path_item
            if method in HTTP_METHODS
        }
        self.assertTrue(operations)
        for method, path in operations:
            matches = [group["id"] for group in groups if _matches(group["pattern"], path)]
            with self.subTest(method=method, path=path):
                self.assertEqual(len(matches), 1, matches)

    def test_every_settings_control_is_inventoried(self) -> None:
        inventory = _load_inventory()
        settings = (ROOT / "frontend" / "fragments" / "pages" / "settings.html").read_text(
            encoding="utf-8"
        )
        controls = set(re.findall(r'<(?:input|select|textarea)\b[^>]*\bid="([^"]+)"', settings))
        self.assertEqual(
            {entry["id"] for entry in inventory["settings_controls"]},
            controls,
        )

    def test_every_example_environment_variable_matches_exactly_one_group(self) -> None:
        inventory = _load_inventory()
        source = (ROOT / ".env.example").read_text(encoding="utf-8")
        variables = set(re.findall(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=", source, flags=re.MULTILINE))
        self.assertTrue(variables)
        for variable in variables:
            matches = [
                group["id"]
                for group in inventory["environment_groups"]
                if _matches(group["pattern"], variable)
            ]
            with self.subTest(variable=variable):
                self.assertEqual(len(matches), 1, matches)

    def test_active_docs_have_no_broken_relative_markdown_links(self) -> None:
        inventory = _load_inventory()
        documents = [ROOT / path for path in inventory["active_documents"]]
        for document in documents:
            self.assertTrue(document.is_file(), document)
            source = document.read_text(encoding="utf-8")
            for target in re.findall(r"(?<!!)\[[^]]+\]\(([^)]+)\)", source):
                target = target.strip().split("#", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                linked = (document.parent / unquote(target)).resolve()
                with self.subTest(document=document.name, target=target):
                    self.assertTrue(linked.exists(), linked)

    def test_locale_ownership_and_claim_sources_are_explicit(self) -> None:
        inventory = _load_inventory()
        policies = inventory["translation_policy"]
        locales = {
            locale
            for policy in policies
            for locale in policy.get("locales", [policy.get("locale")])
        }
        self.assertEqual(
            locales,
            {
                "de",
                "en",
                "es",
                "fr",
                "id",
                "it",
                "ja",
                "ko",
                "pt",
                "ru",
                "th",
                "tr",
                "vi",
                "zh-CN",
                "zh-TW",
            },
        )
        for policy in policies:
            self.assertIn(policy["tier"], inventory["support_tiers"])
            self.assertIn(policy["owner"], {"maintainers", "community"})
        for claim in inventory["advertised_claims"]:
            source = claim["source"].split("#", 1)[0]
            self.assertTrue((ROOT / source).is_file(), claim)

    def test_production_copy_and_curated_locales_use_product_terms(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        readme_vi = (ROOT / "docs" / "locales" / "README.vi.md").read_text(encoding="utf-8")
        env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
        sidebar = (ROOT / "frontend" / "fragments" / "layout" / "sidebar.html").read_text(
            encoding="utf-8"
        )
        identity = (ROOT / "frontend" / "fragments" / "pages" / "identity.html").read_text(
            encoding="utf-8"
        )
        identity_locales = (ROOT / "frontend" / "js" / "core" / "identity-locales.js").read_text(
            encoding="utf-8"
        )

        active_copy = "\n".join((readme, readme_vi, env_example, sidebar, identity))
        for stale_term in ("enterprise governance", "Enterprise OIDC", "W4."):
            self.assertNotIn(stale_term, active_copy)
        self.assertNotIn("quản trị doanh nghiệp", active_copy)
        self.assertNotIn("Virtual API keys let one gateway", readme_vi)
        self.assertNotIn("Polaris records request volume", readme_vi)
        self.assertIn("Team access", sidebar)
        self.assertIn('data-conditional-navigation="team-access"', sidebar)
        self.assertIn("Access &amp; team", identity)
        self.assertIn(
            '"en": {"identity.already_exists": "An identity with this exact issuer and subject already exists.", "identity.governance": "Access & team"}',
            identity_locales,
        )
        self.assertIn(
            '"vi": {"identity.already_exists": "Đã tồn tại một danh tính có chính xác nhà phát hành và chủ thể này.", "identity.governance": "Truy cập và nhóm"}',
            identity_locales,
        )

    def test_only_semantically_reviewed_readmes_are_published(self) -> None:
        localized_readmes = {
            document.name for document in (ROOT / "docs" / "locales").glob("README.*.md")
        }
        self.assertEqual(localized_readmes, {"README.vi.md"})

    def test_current_constraints_and_spec_describe_the_balanced_product(self) -> None:
        constraints = (ROOT / "CONSTRAINTS.md").read_text(encoding="utf-8")
        specification = (ROOT / "docs/specs/production-self-hosted.md").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn("PROD-BALANCE-R2", constraints)
        self.assertIn("120-second", constraints)
        self.assertNotIn("release gate is a reproducible 10-minute", constraints)
        self.assertNotIn("Freeze as experimental", specification)
        self.assertNotIn("Helm, alerts, and ServiceMonitor exist", specification)
        self.assertNotIn("No user-facing changes yet.", changelog)


if __name__ == "__main__":
    unittest.main()
