"""Static coverage checks for the management console translation contract."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
LOCALE_SOURCE = (FRONTEND / "js" / "core" / "locales.js").read_text(encoding="utf-8")
PAGE_LOCALE_SOURCE = (FRONTEND / "js" / "core" / "page-locales.js").read_text(encoding="utf-8")
AUDIT_LOCALE_SOURCE = (FRONTEND / "js" / "core" / "audit-locales.js").read_text(encoding="utf-8")
IDENTITY_LOCALE_SOURCE = (FRONTEND / "js" / "core" / "identity-locales.js").read_text(
    encoding="utf-8"
)
TRACE_LOCALE_SOURCE = (FRONTEND / "js" / "core" / "trace-locales.js").read_text(encoding="utf-8")
OPERATIONAL_LOCALE_SOURCE = (FRONTEND / "js" / "core" / "operational-locales.js").read_text(
    encoding="utf-8"
)
I18N_SOURCE = (FRONTEND / "js" / "core" / "i18n.js").read_text(encoding="utf-8")


def _extract_array(source: str, variable: str) -> str:
    match = re.search(rf"const\s+{re.escape(variable)}\s*=\s*\[(.*?)\];", source, re.DOTALL)
    return match.group(1) if match else ""


def _frontend_sources() -> list[Path]:
    return sorted((FRONTEND / "fragments").rglob("*.html")) + sorted(
        (FRONTEND / "js").rglob("*.js")
    )


class FrontendLocaleContractTests(unittest.TestCase):
    def test_javascript_audit_accepts_namespaced_translation_keys(self):
        audit = (ROOT / "tools/i18n-js-audit.py").read_text(encoding="utf-8")
        self.assertIn(r"(?:\.[a-z][a-z0-9_-]*)*", audit)

    def test_identity_aliases_resolve_to_localized_copy(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the locale behavior contract.")
        source = "\n".join(
            (
                LOCALE_SOURCE,
                PAGE_LOCALE_SOURCE,
                AUDIT_LOCALE_SOURCE,
                TRACE_LOCALE_SOURCE,
                OPERATIONAL_LOCALE_SOURCE,
                I18N_SOURCE.split("installLocalizedFetch();", 1)[0],
                IDENTITY_LOCALE_SOURCE,
                "console.log(JSON.stringify(Object.fromEntries(Object.entries("
                "PAGE_LOCALE_TRANSLATIONS).map(([locale, messages]) => [locale, {"
                "cancel: messages['identity.cancel'], close: messages['identity.close']}]))));",
            )
        )
        result = subprocess.run(
            [node],
            cwd=ROOT,
            capture_output=True,
            encoding="utf-8",
            input=source,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        aliases = json.loads(result.stdout)
        self.assertEqual(len(aliases), 15)
        for locale, messages in aliases.items():
            with self.subTest(locale=locale):
                self.assertNotEqual(messages["cancel"], "btn_cancel")
                self.assertNotEqual(messages["close"], "btn_close")

    def test_trace_catalog_is_complete_for_every_locale(self):
        keys = re.findall(
            r"'(trace\.[a-z0-9_]+)'", _extract_array(TRACE_LOCALE_SOURCE, "TRACE_KEYS")
        )
        values_block = TRACE_LOCALE_SOURCE.split("const TRACE_LOCALE_VALUES = {", 1)[1].split(
            "\n};", 1
        )[0]
        catalogs = {
            match.group(1) or match.group(2): json.loads(match.group(3))
            for match in re.finditer(
                r"^    (?:'([^']+)'|([a-z]{2})): (\[.*\]),?$",
                values_block,
                re.MULTILINE,
            )
        }
        expected = {
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
        }
        self.assertEqual(set(catalogs), expected)
        for locale in expected:
            with self.subTest(locale=locale):
                self.assertEqual(len(catalogs[locale]), len(keys))
                self.assertTrue(all(isinstance(value, str) and value for value in catalogs[locale]))
        context_keys = re.findall(
            r"'(trace\.[a-z0-9_]+)'",
            _extract_array(TRACE_LOCALE_SOURCE, "TRACE_CONTEXT_KEYS"),
        )
        context_block = TRACE_LOCALE_SOURCE.split("const TRACE_CONTEXT_VALUES = {", 1)[1].split(
            "\n};", 1
        )[0]
        context_catalogs = {
            match.group(1) or match.group(2): json.loads(match.group(3))
            for match in re.finditer(
                r"^    (?:'([^']+)'|([a-z]{2})): (\[.*\]),?$",
                context_block,
                re.MULTILINE,
            )
        }
        self.assertEqual(set(context_catalogs), expected)
        for locale in expected:
            self.assertEqual(len(context_catalogs[locale]), len(context_keys), locale)

    def test_operational_health_catalog_is_complete_for_every_locale(self):
        keys = re.findall(
            r"'(slo\.[a-z0-9_]+)'",
            _extract_array(OPERATIONAL_LOCALE_SOURCE, "OPERATIONAL_HEALTH_KEYS"),
        )
        values_block = OPERATIONAL_LOCALE_SOURCE.split("const OPERATIONAL_HEALTH_VALUES = {", 1)[
            1
        ].split("\n};", 1)[0]
        catalogs = {
            match.group(1) or match.group(2): json.loads(match.group(3))
            for match in re.finditer(
                r"^    (?:'([^']+)'|([a-z]{2})): (\[.*\]),?$", values_block, re.MULTILINE
            )
        }
        self.assertEqual(len(catalogs), 15)
        for locale, values in catalogs.items():
            self.assertEqual(len(values), len(keys), locale)

    def test_audit_catalog_is_complete_for_every_locale(self):
        keys = re.findall(
            r"^    '(audit\.[a-z0-9_]+)',?$",
            AUDIT_LOCALE_SOURCE.split("const AUDIT_KEYS = [", 1)[1].split("];", 1)[0],
            re.MULTILINE,
        )
        values_block = AUDIT_LOCALE_SOURCE.split("const AUDIT_LOCALE_VALUES = {", 1)[1].split(
            "\n};", 1
        )[0]
        catalogs = {
            match.group(1) or match.group(2): json.loads(match.group(3))
            for match in re.finditer(
                r"^    (?:'([^']+)'|([a-z]{2})): (\[.*\]),?$",
                values_block,
                re.MULTILINE,
            )
        }

        expected_locales = {
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
        }
        self.assertEqual(set(catalogs), expected_locales)
        for locale in expected_locales:
            with self.subTest(locale=locale):
                self.assertEqual(len(catalogs[locale]), len(keys))
                self.assertTrue(all(isinstance(value, str) and value for value in catalogs[locale]))

    def test_quality_policy_catalog_is_complete_for_every_locale(self):
        block = PAGE_LOCALE_SOURCE.split("const QUALITY_POLICY_EXTENDED_MESSAGES = {", 1)[1].split(
            "\n};", 1
        )[0]
        locale_matches = list(
            re.finditer(
                r"^    (?:'([^']+)'|([a-z]{2})): \{",
                block,
                re.MULTILINE,
            )
        )
        catalogs = {}
        for index, match in enumerate(locale_matches):
            locale = match.group(1) or match.group(2)
            end = (
                locale_matches[index + 1].start() if index + 1 < len(locale_matches) else len(block)
            )
            catalogs[locale] = set(
                re.findall(r"'((?:quality)\.[a-z0-9_]+)'\s*:", block[match.start() : end])
            )

        expected_locales = {
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
        }
        self.assertEqual(set(catalogs), expected_locales)
        for locale in expected_locales:
            with self.subTest(locale=locale):
                self.assertEqual(catalogs[locale], catalogs["en"])

    def test_virtual_key_catalog_is_complete_for_every_locale(self):
        block = PAGE_LOCALE_SOURCE.split("const ACCESS_VIRTUAL_KEY_MESSAGES = {", 1)[1].split(
            "\n};", 1
        )[0]
        locale_matches = list(
            re.finditer(
                r"^    (?:'([^']+)'|([a-z]{2})): \{",
                block,
                re.MULTILINE,
            )
        )
        catalogs = {}
        for index, match in enumerate(locale_matches):
            locale = match.group(1) or match.group(2)
            end = (
                locale_matches[index + 1].start() if index + 1 < len(locale_matches) else len(block)
            )
            catalogs[locale] = set(
                re.findall(r"'(access\.[a-z0-9_]+)'\s*:", block[match.start() : end])
            )

        values_block = PAGE_LOCALE_SOURCE.split("const ACCESS_VIRTUAL_KEY_LOCALE_VALUES = {", 1)[
            1
        ].split("\n};", 1)[0]
        for match in re.finditer(
            r"^    (?:'([^']+)'|([a-z]{2})): (\[.*?\])(?:,)?$",
            values_block,
            re.MULTILINE | re.DOTALL,
        ):
            locale = match.group(1) or match.group(2)
            values = json.loads(match.group(3))
            self.assertEqual(len(values), len(catalogs["en"]), locale)
            catalogs[locale] = set(catalogs["en"])

        expected_locales = {
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
        }
        self.assertEqual(set(catalogs), expected_locales)
        for locale in expected_locales:
            with self.subTest(locale=locale):
                self.assertEqual(catalogs[locale], catalogs["en"])

    def test_page_locale_catalog_executes_without_runtime_failure(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the locale runtime contract.")
        result = subprocess.run(
            [node, str(FRONTEND / "js" / "core" / "page-locales.js")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_language_control_only_appears_in_settings(self):
        locations = []
        for path in _frontend_sources():
            source = path.read_text(encoding="utf-8")
            if 'class="lang-switcher"' in source:
                locations.append(path.relative_to(ROOT).as_posix())

        self.assertEqual(locations, ["frontend/fragments/pages/settings.html"])

    def test_every_referenced_translation_key_has_an_english_source(self):
        references: set[str] = set()
        patterns = (
            re.compile(r"\bt\(\s*['\"]([^'\"]+)['\"]"),
            re.compile(r"data-i18n(?:-(?:title|alt|placeholder|aria-label))?=['\"]([^'\"]+)['\"]"),
        )
        for path in _frontend_sources():
            source = path.read_text(encoding="utf-8")
            for pattern in patterns:
                references.update(pattern.findall(source))

        combined_catalog = (
            LOCALE_SOURCE
            + PAGE_LOCALE_SOURCE
            + IDENTITY_LOCALE_SOURCE
            + AUDIT_LOCALE_SOURCE
            + TRACE_LOCALE_SOURCE
            + OPERATIONAL_LOCALE_SOURCE
            + I18N_SOURCE
        )
        generated_keys: set[str] = set()
        for variable in (
            "SETTINGS_PAGE_KEYS",
            "PROVIDER_CATALOG_KEYS",
            "PROVIDER_WORKFLOW_KEYS",
            "PROVIDER_REMEDIATION_LOCALE_KEYS",
            "CONSOLE_CHROME_KEYS",
            "RUNTIME_UI_KEYS",
            "PROVIDER_ACTION_KEYS",
            "PROVIDER_DIALOG_KEYS",
            "PROVIDER_AUTHORIZATION_KEYS",
            "PROVIDER_FORM_KEYS",
            "PROVIDER_FORM_LABEL_KEYS",
            "DASHBOARD_METRICS_ENHANCEMENT_KEYS",
            "ROUTING_STRATEGY_KEYS",
            "OPERATION_COPY_KEYS",
            "CREDENTIAL_CARD_KEYS",
            "CREDENTIAL_MODAL_KEYS",
            "UPDATE_GUIDE_KEYS",
            "CREDENTIAL_FLEET_KEYS",
            "CREDENTIAL_OPERATION_KEYS",
            "CREDENTIAL_ACTION_KEYS",
            "CREDENTIAL_TIER_KEYS",
            "IDENTITY_KEYS",
            "AUDIT_KEYS",
            "TRACE_KEYS",
            "TRACE_CONTEXT_KEYS",
            "OPERATIONAL_HEALTH_KEYS",
        ):
            source = (
                IDENTITY_LOCALE_SOURCE
                if variable == "IDENTITY_KEYS"
                else AUDIT_LOCALE_SOURCE
                if variable == "AUDIT_KEYS"
                else TRACE_LOCALE_SOURCE
                if variable in {"TRACE_KEYS", "TRACE_CONTEXT_KEYS"}
                else OPERATIONAL_LOCALE_SOURCE
                if variable == "OPERATIONAL_HEALTH_KEYS"
                else PAGE_LOCALE_SOURCE
            )
            generated_keys.update(
                re.findall(r"['\"]([a-z][a-z0-9_.-]+)['\"]", _extract_array(source, variable))
            )
        missing = sorted(
            key
            for key in references
            if key not in generated_keys
            and not re.search(
                rf"(?:['\"]{re.escape(key)}['\"]|\b{re.escape(key)})\s*:", combined_catalog
            )
        )
        self.assertEqual(missing, [], f"Missing English translations: {missing}")

    def test_locale_selector_covers_every_supported_locale(self):
        expected = {
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
        }
        locale_blocks = set(
            re.findall(r"^\s{4}(?:'([^']+)'|([a-z]{2})):\s*\{", LOCALE_SOURCE, re.MULTILINE)
        )
        discovered = {left or right for left, right in locale_blocks}
        self.assertTrue(expected.issubset(discovered))

    def test_management_requests_include_the_active_locale(self):
        self.assertIn("function installLocalizedFetch()", I18N_SOURCE)
        self.assertIn("headers.set('Accept-Language', getActiveLocale()", I18N_SOURCE)
        self.assertIn("requestUrl.pathname.startsWith('/api/')", I18N_SOURCE)

    def test_legacy_dynamic_messages_have_curated_locale_fallbacks(self):
        self.assertIn("const LEGACY_UI_FALLBACKS", I18N_SOURCE)
        self.assertIn("function resolveLegacyFallback", I18N_SOURCE)

    def test_automatic_copy_can_be_restored_when_language_changes(self):
        self.assertIn("const AUTO_TRANSLATED_TEXT = new WeakMap()", I18N_SOURCE)
        self.assertIn("locale === 'en'", I18N_SOURCE)

    def test_translation_lookup_reuses_prebuilt_message_catalogs(self):
        self.assertIn("const MESSAGE_CATALOGS = Object.fromEntries", I18N_SOURCE)
        translation_lookup = I18N_SOURCE.split("function t(key, vars = {})", 1)[1].split(
            "function formatCountLabel", 1
        )[0]
        self.assertIn("MESSAGE_CATALOGS[lang]", translation_lookup)
        self.assertNotIn("...COMMON_UI_TRANSLATIONS", translation_lookup)

    def test_runtime_ui_does_not_embed_known_english_copy(self):
        runtime_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((FRONTEND / "js").rglob("*.js"))
            if path.name
            not in {
                "i18n.js",
                "locales.js",
                "page-locales.js",
                "audit-locales.js",
                "trace-locales.js",
            }
        )
        forbidden_literals = {
            "Close navigation",
            "Open navigation",
            "Credential file",
            "Credential import",
            "Import completed.",
            "Provider Summary",
            "Check for updates",
            "Test Model",
            "Select a model",
            "The selected model test could not be completed.",
            "The credential completed a live model test successfully.",
            "The credential responded, but the provider reported a temporary rate limit. The router can continue with another available credential.",
            "Failure summary",
            "Test summary",
            "Rate limited",
            "Successful",
            "Verification failed.",
            "Credential verified.",
            "Verified",
            "Details",
            "Error details",
            "Summary",
            "Setting ID",
            "Binding ID",
            "provider credential",
            "credential files",
            "email addresses",
        }
        offenders = sorted(
            literal
            for literal in forbidden_literals
            if re.search(rf"(['\"`]){re.escape(literal)}\1", runtime_source)
        )

        self.assertEqual(offenders, [], f"Unlocalized runtime UI copy: {offenders}")

    def test_pre_state_factories_do_not_translate_during_app_state_initialization(self):
        upload_source = (FRONTEND / "js" / "core" / "upload-manager.js").read_text(encoding="utf-8")
        factory_prelude = upload_source.split("return {", 1)[0]

        self.assertNotIn(
            "t(",
            factory_prelude,
            "createUploadManager runs while AppState is in its temporal dead zone",
        )


if __name__ == "__main__":
    unittest.main()
