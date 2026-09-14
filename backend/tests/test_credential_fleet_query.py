"""Deterministic, secret-free credential fleet query tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.credential_fleet_query import (  # noqa: E402
    CredentialFleetFilters,
    CredentialSelectionRegistry,
    build_credential_fleet_page,
    enrich_credential_summary,
)
from core.panel.credential_operations import get_creds_status_common  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _item(
    filename: str,
    *,
    provider: str = "google_antigravity",
    credential_type: str = "oauth",
    disabled: bool = False,
    errors: list[int] | None = None,
    cooldowns: dict | None = None,
    tier: str = "pro",
    source: str | None = None,
) -> dict:
    summary = {
        "filename": filename,
        "user_email": f"{filename}@example.com",
        "disabled": disabled,
        "error_codes": errors or [],
        "last_success": 100,
        "model_cooldowns": cooldowns or {},
        "tier": tier,
        "enable_credit": False,
    }
    credential = {
        "provider": provider,
        "credential_type": credential_type,
        "credential_label": filename,
        "token": "must-never-leak",
        "api_key": "must-never-leak",
    }
    if source:
        credential["source"] = source
    return enrich_credential_summary(summary, credential, backend_type="sqlite", mode="primary")


class CredentialFleetQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CredentialSelectionRegistry(ttl_seconds=300, max_entries=8)

    def test_mixed_filters_compose_and_items_are_secret_free(self):
        items = [
            _item("healthy.json"),
            _item("cooling.json", cooldowns={"gemini": 9999999999}),
            _item(
                "env-key.json",
                provider="google_ai_studio",
                credential_type="api_key",
                tier="free",
                source="environment",
            ),
        ]
        page = build_credential_fleet_page(
            items,
            CredentialFleetFilters(
                provider_variant="google_ai_studio",
                credential_kind="api_key",
                health="healthy",
                cooldown="no_cooldown",
                quota_state="unsupported",
                tier="not_applicable",
                source="environment",
            ),
            offset=0,
            limit=20,
            mode="primary",
            selection_registry=self.registry,
        )

        self.assertEqual([item["filename"] for item in page["items"]], ["env-key.json"])
        serialized = repr(page)
        self.assertNotIn("must-never-leak", serialized)
        self.assertNotIn("token", page["items"][0])
        self.assertEqual(page["facets"]["source"], {"environment": 1})

    def test_stable_sorting_prevents_page_overlap_for_large_input(self):
        items = [_item(f"credential-{index:03}.json") for index in reversed(range(125))]
        first = build_credential_fleet_page(
            items,
            CredentialFleetFilters(),
            offset=0,
            limit=50,
            mode="primary",
            selection_registry=self.registry,
        )
        second = build_credential_fleet_page(
            items,
            CredentialFleetFilters(),
            offset=50,
            limit=50,
            mode="primary",
            selection_registry=self.registry,
        )

        first_names = [item["filename"] for item in first["items"]]
        second_names = [item["filename"] for item in second["items"]]
        self.assertEqual(first_names, sorted(first_names))
        self.assertFalse(set(first_names) & set(second_names))
        self.assertEqual(first["selection"]["matching_count"], 125)
        self.assertEqual(
            first["selection"]["query_fingerprint"], second["selection"]["query_fingerprint"]
        )

    def test_empty_result_has_explicit_selection_without_token(self):
        page = build_credential_fleet_page(
            [_item("only.json")],
            CredentialFleetFilters(provider_variant="ollama"),
            offset=0,
            limit=20,
            mode="primary",
            selection_registry=self.registry,
        )

        self.assertEqual(page["items"], [])
        self.assertEqual(page["total"], 0)
        self.assertIsNone(page["selection"]["token"])
        self.assertEqual(page["selection"]["matching_count"], 0)

    def test_selection_token_resolves_filters_not_filenames(self):
        filters = CredentialFleetFilters(provider_variant="codex", health="healthy")
        original_items = [
            _item("codex-a.json", provider="openai", credential_type="oauth"),
        ]
        page = build_credential_fleet_page(
            original_items,
            filters,
            offset=0,
            limit=20,
            mode="primary",
            selection_registry=self.registry,
        )

        resolved = self.registry.resolve(page["selection"]["token"], mode="primary")
        self.assertEqual(resolved, filters)
        self.assertNotIn("filename", repr(self.registry._entries))
        changed_page = build_credential_fleet_page(
            [
                *original_items,
                _item("codex-b.json", provider="openai", credential_type="oauth"),
            ],
            resolved,
            offset=0,
            limit=20,
            mode="primary",
            selection_registry=self.registry,
        )
        self.assertEqual(changed_page["total"], 2)
        with self.assertRaises(ValueError):
            self.registry.resolve(page["selection"]["token"], mode="code_assist")

    def test_registry_is_bounded_and_rejects_unknown_token(self):
        small_registry = CredentialSelectionRegistry(ttl_seconds=300, max_entries=2)
        tokens = [
            small_registry.issue(CredentialFleetFilters(source=str(index)), mode="primary")
            for index in range(3)
        ]

        with self.assertRaises(ValueError):
            small_registry.resolve(tokens[0], mode="primary")
        self.assertEqual(
            small_registry.resolve(tokens[-1], mode="primary").source,
            "2",
        )
        with self.assertRaises(ValueError):
            small_registry.resolve("forged", mode="primary")


class CredentialFleetValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_filter_is_rejected_before_storage_access(self):
        with self.assertRaises(HTTPException) as raised:
            await get_creds_status_common(
                0,
                20,
                "all",
                mode="primary",
                provider_variant_filter="unknown-provider",
            )
        self.assertEqual(raised.exception.status_code, 400)

    async def test_conflicting_provider_filters_are_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            await get_creds_status_common(
                0,
                20,
                "all",
                mode="primary",
                provider_filter="codex",
                provider_variant_filter="claude_code",
            )
        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
