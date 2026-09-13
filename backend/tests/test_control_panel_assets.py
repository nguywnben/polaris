"""Regression tests for the management console entry point and asset names."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel.root import (
    CONSOLE_FRAGMENT_PATHS,
    CONSOLE_SCRIPT_ASSETS,
    CONSOLE_STYLE_ASSETS,
    _console_asset_version,
    _read_console_bundle,
    serve_control_panel,
)

FRONTEND_JS = BACKEND_DIR.parent / "frontend" / "js"


def read_scripts(*relative_paths: str) -> str:
    return "\n".join(
        (FRONTEND_JS / relative_path).read_text(encoding="utf-8")
        for relative_path in relative_paths
    )


class ControlPanelAssetTests(unittest.TestCase):
    def test_console_entry_point_references_versioned_assets(self):
        response = serve_control_panel()
        body = response.body.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertRegex(body, r"/frontend/theme\.js\?v=[0-9a-f]{20}")
        self.assertRegex(body, r"/frontend/console\.css\?v=[0-9a-f]{20}")
        self.assertRegex(body, r"/frontend/console\.js\?v=[0-9a-f]{20}")
        self.assertLess(
            body.index("/frontend/theme.js"),
            body.index("/frontend/console.css"),
            "Theme preference must be applied before styles to prevent a color-scheme flash.",
        )
        self.assertNotIn("/frontend/vendor/", body)
        self.assertNotIn("<!-- include:fragments/", body)
        self.assertNotIn("/frontend/control-panel.css", body)
        self.assertNotIn("/frontend/control-panel.js", body)
        self.assertNotIn("control_panel", body)
        self.assertNotIn("common.js", body)

    def test_theme_supports_system_light_and_dark_preferences(self):
        response = serve_control_panel()
        body = response.body.decode("utf-8")
        frontend_dir = BACKEND_DIR.parent / "frontend"
        theme_script = (frontend_dir / "js" / "core" / "theme.js").read_text(encoding="utf-8")
        foundation_styles = (frontend_dir / "css" / "foundation.css").read_text(encoding="utf-8")

        self.assertIn('id="themePreference"', body)
        self.assertIn('data-i18n="theme.label"', body)
        for mode in ("system", "light", "dark"):
            self.assertIn(f'<option value="{mode}"', body)
        self.assertIn("omni_gateway_theme", theme_script)
        self.assertIn("window.matchMedia('(prefers-color-scheme: dark)')", theme_script)
        self.assertIn("document.documentElement.dataset.theme", theme_script)
        self.assertIn("localStorage.setItem", theme_script)
        self.assertIn('[data-theme="dark"]', foundation_styles)
        self.assertIn("color-scheme: dark", foundation_styles)

    def test_theme_text_tokens_meet_wcag_normal_text_contrast(self):
        foundation_styles = (BACKEND_DIR.parent / "frontend" / "css" / "foundation.css").read_text(
            encoding="utf-8"
        )

        def selector_tokens(selector: str) -> dict[str, str]:
            block = re.search(rf"{re.escape(selector)}\s*\{{(.*?)\}}", foundation_styles, re.DOTALL)
            self.assertIsNotNone(block)
            return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", block.group(1)))

        def contrast_ratio(foreground: str, background: str) -> float:
            def luminance(value: str) -> float:
                channels = [int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)]
                linear = [
                    channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
                    for channel in channels
                ]
                return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

            lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
            return (lighter + 0.05) / (darker + 0.05)

        light = selector_tokens(":root")
        dark = selector_tokens('[data-theme="dark"]')
        for palette_name, palette in (("light", light), ("dark", dark)):
            for token in ("--text", "--text-muted", "--text-soft"):
                with self.subTest(palette=palette_name, token=token):
                    self.assertGreaterEqual(
                        contrast_ratio(palette[token], palette["--bg"]),
                        4.5,
                    )

    def test_console_manifest_covers_every_fragment_and_local_asset(self):
        response = serve_control_panel()
        body = response.body.decode("utf-8")
        frontend_dir = BACKEND_DIR.parent / "frontend"

        for relative_path in CONSOLE_FRAGMENT_PATHS:
            self.assertTrue((frontend_dir / "fragments" / relative_path).is_file())
        for relative_path in (
            *CONSOLE_STYLE_ASSETS,
            *CONSOLE_SCRIPT_ASSETS,
        ):
            self.assertTrue((frontend_dir / relative_path).is_file())

        asset_version = _console_asset_version()
        style_bundle = _read_console_bundle(CONSOLE_STYLE_ASSETS, asset_version, "\n")
        script_bundle = _read_console_bundle(CONSOLE_SCRIPT_ASSETS, asset_version, "\n;\n")
        self.assertIn(":root", style_bundle)
        self.assertIn("@media", style_bundle)
        self.assertIn("function applyLanguage", script_bundle)
        self.assertIn("function toggleMobileMenu", script_bundle)
        self.assertNotIn("/frontend/js/core/state.js", body)
        self.assertNotIn("/frontend/css/foundation.css", body)

        for legacy_path in (
            "control-panel.html",
            "control-panel.css",
            "js/core.js",
            "js/ui.js",
            "js/console.js",
            "js/credentials.js",
            "js/settings.js",
            "js/dashboard.js",
        ):
            self.assertFalse((frontend_dir / legacy_path).exists())

    def test_sidebar_active_state_uses_data_tab_contract(self):
        response = serve_control_panel()
        body = response.body.decode("utf-8")
        navigation_script = read_scripts("core/navigation.js")

        for tab_name in (
            "dashboard",
            "quality",
            "access",
            "pool",
            "models",
            "providers",
            "config",
            "activity",
            "about",
        ):
            self.assertIn(
                f'data-ui-action="switch-tab" data-tab="{tab_name}"',
                body,
            )

        self.assertIn(
            'document.querySelector(`.tab[data-tab="${tabName}"]`)',
            navigation_script,
        )
        self.assertNotIn(".tab[onclick*=", navigation_script)
        self.assertIn("const TAB_DATA_CACHE_MS = 30000", navigation_script)
        self.assertIn("AppState.tabLoadPromises[tabName]", navigation_script)
        self.assertIn("void triggerTabDataLoad(tabName)", navigation_script)

        responsive_styles = (BACKEND_DIR.parent / "frontend" / "css" / "responsive.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("scrollbar-gutter: stable", responsive_styles)

    def test_access_page_owns_root_key_and_sdk_integration(self):
        response = serve_control_panel()
        body = response.body.decode("utf-8")
        frontend_dir = BACKEND_DIR.parent / "frontend"
        dashboard_fragment = (frontend_dir / "fragments" / "pages" / "dashboard.html").read_text(
            encoding="utf-8"
        )
        access_fragment = (frontend_dir / "fragments" / "pages" / "access.html").read_text(
            encoding="utf-8"
        )
        navigation_script = read_scripts("core/navigation.js")
        integration_script = read_scripts("ui/api-integration.js")
        root_source = (BACKEND_DIR / "core" / "panel" / "root.py").read_text(encoding="utf-8")

        self.assertIn('id="accessTab"', body)
        self.assertIn('data-ui-action="switch-tab" data-tab="access"', body)
        self.assertNotIn('id="apiKey"', dashboard_fragment)
        self.assertNotIn('data-ui-action="regenerate-api-key"', dashboard_fragment)
        self.assertIn('id="apiKey"', access_fragment)
        self.assertIn('data-ui-action="regenerate-api-key"', access_fragment)
        self.assertIn('data-i18n="access.title"', access_fragment)
        self.assertIn("'/access': 'access'", navigation_script)
        self.assertIn("access: '/access'", navigation_script)
        self.assertIn("access: () => loadAccessPage()", navigation_script)
        self.assertIn('@router.get("/access"', root_source)
        self.assertIn("t('access.api_key_copy_label')", integration_script)
        self.assertIn("t('access.hide_api_key')", integration_script)
        self.assertIn("t('access.api_key_managed_env')", integration_script)
        self.assertNotIn("'API key. Copy API key.'", integration_script)
        self.assertNotIn("'Hide API key'", integration_script)

    def test_ai_quality_page_owns_output_and_context_controls(self):
        response = serve_control_panel()
        body = response.body.decode("utf-8")
        frontend_dir = BACKEND_DIR.parent / "frontend"
        settings_fragment = (frontend_dir / "fragments" / "pages" / "settings.html").read_text(
            encoding="utf-8"
        )
        quality_fragment = (frontend_dir / "fragments" / "pages" / "ai-quality.html").read_text(
            encoding="utf-8"
        )
        navigation_script = read_scripts("core/navigation.js")
        settings_script = read_scripts("features/system-settings.js")
        quality_script = read_scripts("features/quality-policy.js")
        root_source = (BACKEND_DIR / "core" / "panel" / "root.py").read_text(encoding="utf-8")

        self.assertIn('id="qualityTab"', body)
        self.assertIn('data-ui-action="switch-tab" data-tab="quality"', body)
        for control_id in (
            "compatibilityModeEnabled",
            "returnThoughtsToFrontend",
            "antiTruncationMaxAttempts",
            "tokenCompressionEnabled",
            "tokenCompressionThreshold",
            "tokenCompressionTarget",
            "tokenCompressionMinRecentTurns",
        ):
            self.assertNotIn(f'id="{control_id}"', settings_fragment)
            self.assertIn(f'id="{control_id}"', quality_fragment)
        self.assertIn('data-i18n="quality.title"', quality_fragment)
        self.assertIn('data-ui-action="save-quality-policy"', quality_fragment)
        self.assertIn('data-ui-action="preview-quality-policy"', quality_fragment)
        self.assertIn('data-ui-action="reset-quality-policy"', quality_fragment)
        self.assertIn('data-ui-change="quality-profile"', quality_fragment)
        self.assertIn('id="qualityPreviewResult"', quality_fragment)
        self.assertIn("'/ai-quality': 'quality'", navigation_script)
        self.assertIn("quality: '/ai-quality'", navigation_script)
        self.assertIn("quality: () => loadQualityPolicy()", navigation_script)
        self.assertNotIn("qualityLoading", settings_script)
        self.assertNotIn("qualityForm", settings_script)
        self.assertIn("./api/quality-policy", quality_script)
        self.assertIn("./api/quality-policy/preview", quality_script)
        self.assertIn("function syncQualityPolicyControls()", quality_script)
        self.assertIn("qualityEffectiveSettings", quality_script)
        self.assertIn("effectiveQualityPresetSettings", quality_script)
        self.assertIn("js/features/quality-policy.js", CONSOLE_SCRIPT_ASSETS)
        self.assertIn('@router.get("/ai-quality"', root_source)

    def test_dashboard_separates_historical_credential_usage(self):
        response = serve_control_panel()
        body = response.body.decode("utf-8")
        dashboard_script = read_scripts("features/dashboard.js")

        self.assertIn('id="historicalUsageSection"', body)
        self.assertIn('id="historicalUsageList"', body)
        self.assertIn("function getCurrentUsageEntriesWithTraffic()", dashboard_script)
        self.assertIn("function getHistoricalUsageEntriesWithTraffic()", dashboard_script)
        self.assertIn("Boolean(stats.is_historical || stats.is_deleted)", dashboard_script)
        self.assertIn(
            "for (const [filename, stats] of getCurrentUsageEntriesWithTraffic())",
            dashboard_script,
        )

    def test_dashboard_time_range_text_does_not_share_select_hover_state(self):
        body = serve_control_panel().body.decode("utf-8")

        self.assertIn('<div class="dashboard-range-control">', body)
        self.assertNotIn('<label class="dashboard-range-control"', body)
        self.assertIn(
            '<select id="usagePeriodSelect" class="filter-select" '
            'aria-label="Time range" data-i18n-aria-label="time_range"',
            body,
        )

    def test_provider_catalog_uses_pagination(self):
        response = serve_control_panel()
        body = response.body.decode("utf-8")
        navigation_script = read_scripts("features/navigation.js")
        provider_styles = (
            BACKEND_DIR.parent / "frontend" / "css" / "providers-and-models.css"
        ).read_text(encoding="utf-8")

        for element_id in (
            "providerCatalog",
            "providerCatalogPagination",
            "providerCatalogPrevBtn",
            "providerCatalogNextBtn",
            "providerCatalogPaginationInfo",
        ):
            self.assertIn(element_id, body)
        self.assertIn("provider-workspace-header", body)
        self.assertIn("change-provider-catalog-page", body)
        self.assertIn("PROVIDER_CATALOG_PAGE_SIZE = 8", navigation_script)
        self.assertIn("function changeProviderCatalogPage(delta)", navigation_script)
        self.assertIn("function updateProviderCatalogPagination()", navigation_script)
        self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr))", provider_styles)
        self.assertRegex(
            provider_styles,
            r"(?s)\.provider-catalog \.provider-hero-card\s*\{[^}]*min-height: 154px;[^}]*padding: 14px;",
        )
        self.assertRegex(
            provider_styles,
            r"(?s)\.provider-catalog \.provider-logo-frame\s*\{[^}]*width: 42px;[^}]*height: 42px;",
        )
        self.assertIn(".provider-workspace-header", provider_styles)
        self.assertNotIn('class="provider-catalog-search-label"', body)
        self.assertIn(
            'id="providerCatalogSearch" class="provider-catalog-search" '
            'aria-label="Find a provider"',
            body,
        )
        self.assertNotIn(".provider-catalog-search-label", provider_styles)

    def test_static_below_field_notes_are_not_rendered(self):
        body = serve_control_panel().body.decode("utf-8")
        virtual_key_script = read_scripts("features/virtual-keys.js")

        self.assertNotIn('class="form-help', body)
        for marker in (
            'data-i18n="setup_token_hint"',
            'data-i18n="setup_password_hint"',
            'id="consoleLanguageHint"',
            'id="modelRoutingStrategyHint"',
            'class="field-hint trace-filter-hint"',
            'class="field-hint activity-filter-hint"',
            'class="field-hint audit-filter-hint"',
            'class="field-hint quality-safety-copy"',
            'data-i18n="quality.blocked_keywords_hint"',
            'data-i18n="settings.listener_restart_hint"',
            'data-i18n="settings.log_rotation_hint"',
            'data-i18n="settings.proxy_hint"',
            'data-i18n="settings.credentials_restart_hint"',
            'data-i18n="settings.routing_fallback_hint"',
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, body)
        self.assertNotIn("access.allowed_models_hint", virtual_key_script)

    def test_xai_provider_ui_references_existing_assets_and_endpoints(self):
        response = serve_control_panel()
        body = response.body.decode("utf-8")
        settings_script = read_scripts(
            "features/provider-settings-shared.js",
            "features/google-ai-studio-settings.js",
            "features/xai-settings.js",
            "features/antigravity-settings.js",
        )
        upload_script = read_scripts("core/upload-manager.js", "core/state.js")
        provider_assets = BACKEND_DIR.parent / "frontend" / "assets" / "providers"
        self.assertTrue((provider_assets / "grok-build-logo.png").is_file())
        self.assertTrue((provider_assets / "spacexai-console-logo.png").is_file())
        for element_id in (
            "providerSelectorGrok",
            "providerWorkspaceGrok",
            "providerSelectorXaiConsole",
            "providerWorkspaceXaiConsole",
            "grokUploadArea",
            "grokFileInput",
            "xaiConsoleUploadArea",
            "xaiConsoleFileInput",
        ):
            self.assertIn(f'id="{element_id}"', body)
        self.assertIn("/frontend/assets/providers/grok-build-logo.png", body)
        self.assertIn("/frontend/assets/providers/spacexai-console-logo.png", body)
        self.assertIn('<strong class="provider-name">Grok Build</strong>', body)
        self.assertIn('<strong class="provider-name">SpaceXAI Console</strong>', body)
        self.assertIn(
            "./api/providers/xai/credentials/import?credential_type=oauth",
            upload_script,
        )
        self.assertIn(
            "./api/providers/xai/credentials/import?credential_type=api_key",
            upload_script,
        )
        for endpoint in (
            "./api/providers/xai/config",
            "./api/providers/xai/config/reset",
            "./api/providers/xai/credentials",
            "./api/providers/xai/oauth/start",
            "./api/providers/xai/oauth/complete",
        ):
            self.assertIn(endpoint, settings_script)
        self.assertNotIn("./api/providers/xai/oauth/callback", settings_script)
        self.assertIn('id="xaiAuthorizationCode"', body)
        self.assertIn('data-i18n="provider.authorization_code"', body)
        self.assertNotIn('id="xaiCallbackUrl"', body)
        self.assertIn(
            "authorizationLink.textContent = data.auth_url || t('runtime.authorization_unavailable')",
            settings_script,
        )
        self.assertNotIn("Open xAI authorization", body)
        self.assertNotIn("Open xAI authorization", settings_script)
        self.assertNotIn(">xAI<", body)
        self.assertNotIn("name: 'xAI'", upload_script)
        self.assertIn('<option value="xai">Grok Build</option>', body)

    def test_openai_provider_ui_references_existing_assets_and_endpoints(self):
        response = serve_control_panel()
        body = response.body.decode("utf-8")
        settings_script = read_scripts("features/openai-settings.js")
        upload_script = read_scripts("core/upload-manager.js", "core/state.js")
        provider_assets = BACKEND_DIR.parent / "frontend" / "assets" / "providers"
        self.assertTrue((provider_assets / "codex-logo.png").is_file())
        self.assertTrue((provider_assets / "openai-platform-logo.png").is_file())
        for element_id in (
            "providerCatalogSearch",
            "providerSelectorCodex",
            "providerWorkspaceCodex",
            "providerSelectorOpenAiPlatform",
            "providerWorkspaceOpenAiPlatform",
            "codexUploadArea",
            "openaiPlatformUploadArea",
        ):
            self.assertIn(f'id="{element_id}"', body)
        self.assertIn("/frontend/assets/providers/codex-logo.png", body)
        self.assertIn("/frontend/assets/providers/openai-platform-logo.png", body)
        self.assertIn('<strong class="provider-name">Codex</strong>', body)
        self.assertIn('<strong class="provider-name">OpenAI Platform</strong>', body)
        self.assertIn(
            'id="codexUserCode" class="endpoint-code-card device-code-button"',
            body,
        )
        self.assertIn('data-ui-action="copy-codex-device-code"', body)
        self.assertNotIn('data-copy-target="codexUserCode"', body)
        self.assertIn(
            'data-ui-action="copy-codex-verification-url">Copy</button>',
            body,
        )
        self.assertIn('class="device-verification-row"', body)
        self.assertNotIn('class="copy-field-row"', body)
        self.assertIn("./api/providers/openai/codex/oauth/start", settings_script)
        self.assertIn("./api/providers/openai/platform/credentials", settings_script)
        self.assertIn("codexUsageUrl: 'codex_usage_url'", settings_script)
        self.assertIn('id="codexUsageUrl"', body)
        self.assertIn(
            "./api/providers/openai/credentials/import?credential_type=oauth",
            upload_script,
        )
        self.assertIn(
            "./api/providers/openai/credentials/import?credential_type=api_key",
            upload_script,
        )

    def test_credential_verification_uses_provider_neutral_route(self):
        credential_manager_script = read_scripts("core/credential-manager.js")
        credential_script = read_scripts("features/credential-diagnostics.js")

        self.assertIn("./api/credentials/verify", credential_manager_script)
        self.assertIn("./api/credentials/verify/", credential_script)
        self.assertNotIn("./api/credentials/verify-project", credential_manager_script)
        self.assertNotIn("./api/credentials/verify-project", credential_script)

    def test_model_connection_test_is_cancelable_and_renders_safe_diagnostics(self):
        diagnostic_script = read_scripts("features/credential-diagnostics.js")
        dialog_script = read_scripts("ui/dialogs.js")
        content_script = read_scripts("ui/dialog-content.js")
        credential_dialog_script = read_scripts("ui/credential-dialogs.js")

        self.assertIn("new AbortController()", dialog_script)
        self.assertIn("activeController?.abort()", dialog_script)
        self.assertIn("options.onTest(model, activeController.signal)", dialog_script)
        self.assertIn("signal", diagnostic_script)
        self.assertIn("signal?.aborted", diagnostic_script)
        self.assertIn("data?.diagnostic?.message", diagnostic_script)
        self.assertIn("data?.diagnostic", content_script)
        self.assertIn("diagnostic.remediation", content_script)
        self.assertIn("diagnostic.provider_code", content_script)
        self.assertIn("async (model, signal)", credential_dialog_script)

    def test_batch_client_previews_guarded_work_and_sends_idempotency_key(self):
        credential_manager_script = read_scripts("core/credential-manager.js")

        self.assertIn("preview: true", credential_manager_script)
        self.assertIn("preview_token: previewData.preview_token", credential_manager_script)
        self.assertIn("idempotency_key: idempotencyKey", credential_manager_script)
        self.assertIn("crypto.randomUUID()", credential_manager_script)

    def test_pool_filters_and_selection_are_bounded_and_explicit(self):
        body = serve_control_panel().body.decode("utf-8")
        credential_manager_script = read_scripts("core/credential-manager.js")

        for control_id in (
            "primaryCredentialKindFilter",
            "primaryHealthFilter",
            "primaryQuotaStateFilter",
            "primarySourceFilter",
            "primarySelectAllMatchingBtn",
            "primaryClearSelectionBtn",
        ):
            self.assertIn(f'id="{control_id}"', body)
        self.assertIn("new URLSearchParams(window.location.search)", credential_manager_script)
        self.assertIn("raw.length <= 512", credential_manager_script)
        self.assertIn("serialized.length <= 512", credential_manager_script)
        self.assertIn("selectionScope: 'page'", credential_manager_script)
        self.assertIn("this.selectionScope = 'all_matching'", credential_manager_script)
        persistence_block = credential_manager_script.split("persistFilterState() {", 1)[1].split(
            "getElementId:", 1
        )[0]
        self.assertNotIn("selectedFiles", persistence_block)

    def test_pool_toolbar_uses_capability_intersection_and_preview_results(self):
        credential_manager_script = read_scripts("core/credential-manager.js")

        self.assertIn("fetch('./api/providers/capabilities'", credential_manager_script)
        self.assertIn("selectedVariantsSupport(operation)", credential_manager_script)
        self.assertIn(
            "selection_token: this.allMatchingSelection?.token", credential_manager_script
        )
        self.assertIn("pool.operation.unsupported", credential_manager_script)
        preview_index = credential_manager_script.index("const previewResponse = await fetch")
        confirmation_index = credential_manager_script.index(
            "await showConfirmModal(confirmMsg, confirmOptions)"
        )
        self.assertLess(preview_index, confirmation_index)
        self.assertIn("this.formatBatchResults(data)", credential_manager_script)
        self.assertIn("pool.batch.preview_stale", credential_manager_script)

    def test_credential_cards_derive_provider_actions_from_the_catalog(self):
        credential_manager_script = read_scripts("core/credential-manager.js")
        card_script = read_scripts("ui/credential-cards.js")

        self.assertIn(
            "credentialSupportsOperation(credential, operation)", credential_manager_script
        )
        for operation in (
            "disable",
            "export",
            "model_discovery",
            "quota",
            "verify",
            "test",
            "delete",
        ):
            self.assertIn(
                f"manager.credentialSupportsOperation(credInfo, '{operation}')",
                card_script,
            )
        self.assertNotIn("isAntigravity || isGrokOAuth || isCodexOAuth", card_script)

    def test_quota_capability_uses_the_shared_quota_dialog(self):
        card_script = read_scripts("ui/credential-cards.js")
        dialog_script = read_scripts("ui/credential-dialogs.js")

        self.assertIn("manager.credentialSupportsOperation(credInfo, 'quota')", card_script)
        self.assertIn("const quotaPreview = supportsQuotaPreview", card_script)
        self.assertIn("data?.quota_type === 'account_billing'", dialog_script)
        self.assertIn("t('modal.billing_periods')", dialog_script)
        self.assertIn("t('modal.lowest_billing_preview'", dialog_script)
        self.assertIn("data?.quota_type === 'account_rate_limits'", dialog_script)
        self.assertIn("t('modal.usage_windows')", dialog_script)
        self.assertIn("data.provider_variant === 'claude_code'", dialog_script)
        self.assertIn("'modal.claude_quota_intro'", dialog_script)
        self.assertIn("typeof data.limit_reached === 'boolean'", dialog_script)

    def test_subscription_plans_are_rendered_as_credential_badges(self):
        card_script = read_scripts("ui/credential-cards.js")
        dialog_script = read_scripts("ui/credential-dialogs.js")

        self.assertIn("renderCredentialSubscriptionBadge", card_script)
        self.assertIn("subscription-plan-${pathId}", card_script)
        self.assertIn("t('credential_badge_plan'", card_script)
        self.assertIn("t('credential_badge_tier'", card_script)
        self.assertIn("updateCredentialSubscriptionBadge", dialog_script)
        self.assertIn("cached.data?.plan", dialog_script)
        self.assertIn("cardContext.subscriptionPlan", dialog_script)

    def test_all_supported_credentials_have_an_authentication_badge(self):
        card_script = read_scripts("ui/credential-cards.js")

        self.assertIn("getCredentialAuthenticationType", card_script)
        self.assertIn("'google_antigravity', 'grok', 'codex'", card_script)
        self.assertIn("'google_ai_studio', 'xai_console', 'openai_platform'", card_script)
        self.assertIn("renderCredentialAuthenticationBadge", card_script)
        self.assertIn("${authenticationType}", card_script)


if __name__ == "__main__":
    unittest.main()
