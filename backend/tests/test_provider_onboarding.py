"""Production provider-onboarding contract tests for P3.4."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROVIDER_HTML = (ROOT / "frontend/fragments/pages/providers.html").read_text(encoding="utf-8")
ONBOARDING_SOURCE = ROOT / "frontend/js/features/provider-onboarding.js"
NAVIGATION_SOURCE = (ROOT / "frontend/js/core/navigation.js").read_text(encoding="utf-8")
SHARED_SOURCE = (ROOT / "frontend/js/features/provider-settings-shared.js").read_text(
    encoding="utf-8"
)
LOCALE_SOURCE = (ROOT / "frontend/js/core/page-locales.js").read_text(encoding="utf-8")

VARIANTS = {
    "google_antigravity": (
        "providerSelectorGoogleAntigravity",
        "providerWorkspaceGoogleAntigravity",
    ),
    "google_ai_studio": ("providerSelectorGoogleAiStudio", "providerWorkspaceGoogleAiStudio"),
    "grok": ("providerSelectorGrok", "providerWorkspaceGrok"),
    "xai_console": ("providerSelectorXaiConsole", "providerWorkspaceXaiConsole"),
    "codex": ("providerSelectorCodex", "providerWorkspaceCodex"),
    "openai_platform": ("providerSelectorOpenAiPlatform", "providerWorkspaceOpenAiPlatform"),
    "claude_code": ("providerSelectorClaudeCode", "providerWorkspaceClaudeCode"),
    "claude_platform": ("providerSelectorClaudePlatform", "providerWorkspaceClaudePlatform"),
    "ollama": ("providerSelectorOllama", "providerWorkspaceOllama"),
}


class ProviderOnboardingContractTests(unittest.TestCase):
    def test_onboarding_completion_clears_transient_ui_without_rendering_payloads(self):
        source = (ROOT / "frontend/js/features/antigravity-authentication.js").read_text(
            encoding="utf-8"
        )
        completion = source.split("async function completePrimaryCredentialSave", 1)[1].split(
            "async function getPrimaryCredentials", 1
        )[0]
        self.assertNotIn("JSON.stringify(data.credentials", completion)
        self.assertNotIn('id="primaryCredsContent"', PROVIDER_HTML)
        results = (ROOT / "frontend/js/features/provider-save-results.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("completeProviderEntry", results)
        self.assertIn("prepareProviderKeyEntries", ONBOARDING_SOURCE.read_text(encoding="utf-8"))

    def test_every_advertised_variant_maps_to_one_selector_and_workspace(self) -> None:
        source = (ROOT / "frontend/js/features/navigation.js").read_text(
            encoding="utf-8"
        ) + ONBOARDING_SOURCE.read_text(encoding="utf-8")
        for variant, (selector_id, workspace_id) in VARIANTS.items():
            with self.subTest(variant=variant):
                self.assertIn(f"{variant}:", source)
                self.assertIn(f"selectorId: '{selector_id}'", source)
                self.assertIn(f"panelId: '{workspace_id}'", source)
                self.assertRegex(
                    PROVIDER_HTML,
                    rf'id="{selector_id}"[^>]+data-provider="{variant}"',
                )
                self.assertIn(f'id="{workspace_id}"', PROVIDER_HTML)

    def test_catalog_is_server_authoritative_and_recoverable(self) -> None:
        source = ONBOARDING_SOURCE.read_text(encoding="utf-8")
        self.assertIn("fetch('./api/providers/capabilities'", source)
        self.assertIn("payload.schema_version !== PROVIDER_CAPABILITY_SCHEMA_VERSION", source)
        self.assertIn("PROVIDER_REQUIRED_OPERATIONS", source)
        for operation in ("add", "test", "model_discovery", "disable", "delete"):
            self.assertIn(f"'{operation}'", source)
        self.assertIn("function retryProviderCapabilities()", source)
        self.assertIn('id="providerCapabilityStatus"', PROVIDER_HTML)
        self.assertIn('data-ui-action="retry-provider-capabilities"', PROVIDER_HTML)

    def test_ready_capability_status_is_silent_and_pagination_stays_with_catalog(
        self,
    ) -> None:
        onboarding = ONBOARDING_SOURCE.read_text(encoding="utf-8")
        navigation = (ROOT / "frontend/js/features/navigation.js").read_text(encoding="utf-8")

        self.assertIn("container.classList.toggle('hidden', state === 'ready')", onboarding)
        self.assertNotIn("activeHeader?.append(paginationContainer)", navigation)
        self.assertEqual(PROVIDER_HTML.count('id="providerCatalogPagination"'), 1)
        self.assertLess(
            PROVIDER_HTML.index('id="providerCatalogPagination"'),
            PROVIDER_HTML.index('<section class="provider-workspace'),
        )

    def test_import_is_always_visible_while_settings_are_progressively_disclosed(self) -> None:
        source = ONBOARDING_SOURCE.read_text(encoding="utf-8")
        styles = (ROOT / "frontend/css/providers-and-models.css").read_text(encoding="utf-8")

        self.assertIn("function presentProviderImportPanel(panel, providerId)", source)
        self.assertIn("addProviderCredentialExample(panel, providerId)", source)
        self.assertIn("title.dataset.providerStaticLabel = 'import'", source)
        self.assertNotIn("createProviderDisclosure(importPanel", source)
        self.assertIn("document.createElement('details')", source)
        self.assertIn("provider-secondary-disclosure", source)
        self.assertIn("createProviderDisclosure(settingsPanel", source)
        self.assertIn("details.addEventListener('toggle'", source)
        self.assertIn("loadProviderWorkspaceSettings", source)
        self.assertIn(".tool-panel.provider-secondary-disclosure", styles)
        self.assertIn(".provider-disclosure-summary::-webkit-details-marker", styles)
        self.assertIn(".provider-disclosure-summary::marker", styles)
        self.assertIn("background-image: var(--select-chevron)", styles)
        self.assertRegex(
            styles,
            r"\.provider-secondary-disclosure\[open\][^{]*\.provider-disclosure-summary::after\s*\{[^}]*transform:\s*rotate\(180deg\)",
        )

    def test_provider_route_no_longer_eager_loads_unrelated_settings(self) -> None:
        provider_loader = NAVIGATION_SOURCE.split("providers: () =>", 1)[1].split(
            "config: () =>", 1
        )[0]
        self.assertIn("loadProviderOnboarding", provider_loader)
        for eager_loader in (
            "loadAntigravitySettings",
            "loadGoogleAIStudioSettings",
            "loadXaiSettings",
            "loadOpenAISettings",
            "loadAnthropicSettings",
        ):
            self.assertNotIn(eager_loader, provider_loader)

    def test_connection_failures_have_safe_actionable_remediation(self) -> None:
        self.assertIn("function createProviderRequestError(response, data)", SHARED_SOURCE)
        self.assertIn("function formatProviderRequestError(error)", SHARED_SOURCE)
        for category in (
            "credential",
            "permission",
            "quota",
            "rate_limit",
            "invalid_model",
            "network",
            "upstream",
        ):
            self.assertRegex(SHARED_SOURCE, rf"\b{re.escape(category)}:")
        self.assertIn("providerDiagnostic?.remediation", SHARED_SOURCE)

    def test_new_provider_workflow_copy_covers_every_supported_locale(self) -> None:
        keys = LOCALE_SOURCE.split("const PROVIDER_WORKFLOW_KEYS = [", 1)[1].split("];", 1)[0]
        values = LOCALE_SOURCE.split("const PROVIDER_WORKFLOW_VALUES = {", 1)[1].split("\n};", 1)[0]
        self.assertIn("providers.capabilities_loading", keys)
        self.assertIn("providers.capabilities_ready", keys)
        self.assertIn("providers.capabilities_failed", keys)
        self.assertIn("providers.retry", keys)
        self.assertIn("providers.import_credentials", keys)
        self.assertIn("providers.advanced_settings", keys)
        locales = {
            left or right
            for left, right in re.findall(
                r"^    (?:'([^']+)'|([a-z]{2})):\s*\[", values, re.MULTILINE
            )
        }
        self.assertEqual(
            locales,
            {
                "en",
                "zh-CN",
                "zh-TW",
                "de",
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
            },
        )


if __name__ == "__main__":
    unittest.main()
