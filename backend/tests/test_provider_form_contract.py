"""Static audit tests for the declarative provider form contract."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROVIDER_HTML = (ROOT / "frontend/fragments/pages/providers.html").read_text(encoding="utf-8")
CONTRACT_SOURCE = (ROOT / "frontend/js/features/provider-settings-shared.js").read_text(
    encoding="utf-8"
)
LOCALE_SOURCE = (ROOT / "frontend/js/core/page-locales.js").read_text(encoding="utf-8")

EXPECTED_FIELDS = {
    "grokApiUrl",
    "googleOauthUrl",
    "googleUserinfoUrl",
    "codeAssistEndpoint",
    "codeAssistClientId",
    "codeAssistClientSecret",
    "codeAssistResourceManager",
    "codeAssistServiceUsage",
    "xaiAuthorizationCode",
    "xaiClientId",
    "xaiOauthIssuer",
    "xaiApiKey",
    "xaiApiUrl",
    "xaiUserAgent",
    "googleAiStudioApiKey",
    "googleAiStudioApiUrl",
    "codexApiUrl",
    "codexUsageUrl",
    "codexAuthBase",
    "codexClientId",
    "codexUserAgent",
    "openaiPlatformApiKey",
    "openaiApiUrl",
    "claudeAuthorizationCode",
    "claudeAuthorizeUrl",
    "claudeTokenUrl",
    "claudeClientId",
    "claudeUserAgent",
    "claudePlatformApiKey",
    "anthropicApiUrlPlatform",
    "ollamaBaseUrl",
    "ollamaApiKey",
    "primaryCallbackUrlInput",
    "antigravityOauthClientId",
    "antigravityOauthClientSecret",
    "antigravityApiUrl",
    "antigravityUserAgent",
    "antigravityPayloadUserAgent",
}

SECRET_FIELDS = {
    "codeAssistClientSecret",
    "xaiAuthorizationCode",
    "xaiApiKey",
    "googleAiStudioApiKey",
    "openaiPlatformApiKey",
    "claudeAuthorizationCode",
    "claudePlatformApiKey",
    "ollamaApiKey",
    "primaryCallbackUrlInput",
    "antigravityOauthClientSecret",
}

GOOGLE_HELP_FIELDS = {
    "googleAiStudioApiKey",
    "googleAiStudioApiUrl",
    "primaryCallbackUrlInput",
    "antigravityOauthClientId",
    "antigravityOauthClientSecret",
    "antigravityApiUrl",
    "antigravityUserAgent",
    "antigravityPayloadUserAgent",
}


class ProviderFormContractTests(unittest.TestCase):
    def test_manifest_covers_every_supported_provider_field(self):
        self.assertIn("const PROVIDER_FORM_CONTRACT", CONTRACT_SOURCE)
        for field_id in EXPECTED_FIELDS:
            with self.subTest(field_id=field_id):
                self.assertIn(f"id: '{field_id}'", CONTRACT_SOURCE)
                self.assertRegex(PROVIDER_HTML, rf'id="{re.escape(field_id)}"')

    def test_every_visible_contract_field_has_an_explicit_label(self):
        for field_id in EXPECTED_FIELDS:
            with self.subTest(field_id=field_id):
                self.assertRegex(PROVIDER_HTML, rf'<label[^>]+for="{re.escape(field_id)}"')

    def test_contract_declares_all_required_enterprise_behaviors(self):
        for property_name in (
            "type",
            "required",
            "minLength",
            "maxLength",
            "autocomplete",
            "secretLifetime",
            "environmentLock",
            "helpKey",
            "advanced",
            "validation",
            "resetBehavior",
        ):
            with self.subTest(property_name=property_name):
                self.assertIn(f"{property_name}:", CONTRACT_SOURCE)

        for helper_name in (
            "applyProviderFormContract",
            "applyProviderEnvironmentLocks",
            "validateProviderFormScope",
            "resetProviderTransientSecrets",
        ):
            with self.subTest(helper_name=helper_name):
                self.assertIn(f"function {helper_name}", CONTRACT_SOURCE)

    def test_secret_fields_are_never_plain_text_and_have_bounded_lifetimes(self):
        for field_id in SECRET_FIELDS:
            with self.subTest(field_id=field_id):
                field_entry = CONTRACT_SOURCE.split(f"id: '{field_id}'", 1)[1].split("}", 1)[0]
                expected_type = "textarea" if field_id == "primaryCallbackUrlInput" else "password"
                self.assertIn(f"type: '{expected_type}'", field_entry)
                self.assertRegex(field_entry, r"maxLength:\s*[1-9][0-9]*")
                self.assertRegex(field_entry, r"secretLifetime:\s*'(submit|edit-session)'")
                self.assertIn("resetBehavior: 'clear'", field_entry)

    def test_runtime_enforces_contract_without_persisting_form_state(self):
        self.assertIn(
            "document.addEventListener('DOMContentLoaded', applyProviderFormContract",
            CONTRACT_SOURCE,
        )
        self.assertIn("field.dataset.secretLifetime", CONTRACT_SOURCE)
        self.assertIn("field.setCustomValidity", CONTRACT_SOURCE)
        self.assertNotIn("provider-field-help", CONTRACT_SOURCE)
        self.assertNotIn("field.insertAdjacentElement('afterend', help)", CONTRACT_SOURCE)
        self.assertNotIn("localStorage", CONTRACT_SOURCE)
        self.assertNotIn("sessionStorage", CONTRACT_SOURCE)

    def test_form_guidance_is_curated_for_every_supported_locale(self):
        block = LOCALE_SOURCE.split("const PROVIDER_FORM_VALUES = {", 1)[1].split("\n};", 1)[0]
        locales = {
            left or right
            for left, right in re.findall(
                r"^    (?:'([^']+)'|([a-z]{2})):\s*\[", block, re.MULTILINE
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
        self.assertIn("values.length !== PROVIDER_FORM_KEYS.length", LOCALE_SOURCE)

        label_block = LOCALE_SOURCE.split("const PROVIDER_FORM_LABEL_VALUES = {", 1)[1].split(
            "\n};", 1
        )[0]
        label_locales = {
            left or right
            for left, right in re.findall(
                r"^    (?:'([^']+)'|([a-z]{2})):\s*\[", label_block, re.MULTILINE
            )
        }
        self.assertEqual(label_locales, locales)
        self.assertIn("values.length !== PROVIDER_FORM_LABEL_KEYS.length", LOCALE_SOURCE)

    def test_google_family_fields_do_not_render_below_field_notes(self):
        for field_id in GOOGLE_HELP_FIELDS:
            with self.subTest(field_id=field_id):
                self.assertNotIn(f'id="{field_id}Help"', PROVIDER_HTML)

        google_script = (ROOT / "frontend/js/features/google-ai-studio-settings.js").read_text(
            encoding="utf-8"
        )
        antigravity_script = (ROOT / "frontend/js/features/antigravity-settings.js").read_text(
            encoding="utf-8"
        )
        authentication_script = (
            ROOT / "frontend/js/features/antigravity-authentication.js"
        ).read_text(encoding="utf-8")
        self.assertIn("validateProviderFormScope('google-ai-studio.settings')", google_script)
        self.assertIn("validateProviderFormScope('google-ai-studio.credential')", google_script)
        self.assertIn("applyProviderEnvironmentLocks('google-ai-studio.settings'", google_script)
        self.assertIn("resetProviderTransientSecrets('google-ai-studio.credential')", google_script)
        self.assertIn("validateProviderFormScope('antigravity.settings')", antigravity_script)
        self.assertRegex(
            antigravity_script,
            r"applyProviderEnvironmentLocks\(\s*'antigravity\.settings'",
        )
        self.assertIn("resetProviderTransientSecrets('antigravity.oauth')", authentication_script)

    def test_remaining_provider_families_consume_the_shared_contract(self):
        scripts = {
            name: (ROOT / f"frontend/js/features/{name}-settings.js").read_text(encoding="utf-8")
            for name in ("xai", "openai", "anthropic", "ollama")
        }
        expected_calls = {
            "xai": (
                "validateProviderFormScope(contractScope)",
                "applyProviderEnvironmentLocks(['grok.settings', 'xai.settings', 'xai.shared']",
                "resetProviderTransientSecrets('xai.credential')",
                "resetProviderTransientSecrets('grok.oauth')",
            ),
            "openai": (
                "validateProviderFormScope(contractScope)",
                "applyProviderEnvironmentLocks(['codex.settings', 'openai-platform.settings']",
                "resetProviderTransientSecrets('openai-platform.credential')",
            ),
            "anthropic": (
                "validateProviderFormScope(contractScope)",
                "applyProviderEnvironmentLocks(['claude-code.settings', 'claude-platform.settings']",
                "resetProviderTransientSecrets('claude-platform.credential')",
                "resetProviderTransientSecrets('claude-code.oauth')",
            ),
            "ollama": (
                "validateProviderFormScope('ollama.credential')",
                "resetProviderTransientSecrets('ollama.credential')",
            ),
        }
        for family, calls in expected_calls.items():
            for call in calls:
                with self.subTest(family=family, call=call):
                    self.assertIn(call, scripts[family])

        google_script = (ROOT / "frontend/js/features/google-ai-studio-settings.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("const XAI_CONFIG_FIELDS", scripts["xai"])
        self.assertNotIn("const XAI_CONFIG_FIELDS", google_script)

    def test_provider_specific_secret_bounds_are_preserved(self):
        expected_bounds = {
            "xaiApiKey": (16, 1024),
            "googleAiStudioApiKey": (1, 4096),
            "openaiPlatformApiKey": (1, 1024),
            "claudePlatformApiKey": (1, 1024),
            "ollamaApiKey": (0, 4096),
        }
        for field_id, (minimum, maximum) in expected_bounds.items():
            with self.subTest(field_id=field_id):
                field_entry = CONTRACT_SOURCE.split(f"id: '{field_id}'", 1)[1].split("}", 1)[0]
                self.assertIn(f"minLength: {minimum}", field_entry)
                self.assertIn(f"maxLength: {maximum}", field_entry)


if __name__ == "__main__":
    unittest.main()
