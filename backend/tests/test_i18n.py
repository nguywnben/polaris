"""Locale negotiation and user-facing message localization."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.i18n import (
    MESSAGES,
    SUPPORTED_LOCALES,
    LocalizedJSONResponse,
    locale_context,
    resolve_locale,
    translate,
    translate_payload,
)


class LocaleNegotiationTests(unittest.TestCase):
    def test_defaults_to_english(self):
        self.assertEqual(resolve_locale(None), "en")
        self.assertEqual(resolve_locale("pl-PL,pl;q=0.9"), "en")

    def test_matches_supported_language_from_accept_language(self):
        self.assertEqual(resolve_locale("fr-FR,fr;q=0.9,en;q=0.8"), "fr")
        self.assertEqual(resolve_locale("vi-VN,vi;q=0.9"), "vi")

    def test_distinguishes_simplified_and_traditional_chinese(self):
        self.assertEqual(resolve_locale("zh-Hant-HK,zh;q=0.9"), "zh-TW")
        self.assertEqual(resolve_locale("zh-SG,zh;q=0.9"), "zh-CN")

    def test_honors_quality_weights(self):
        self.assertEqual(resolve_locale("de;q=0.4,fr;q=0.9"), "fr")


class MessageLocalizationTests(unittest.TestCase):
    def test_every_backend_message_covers_every_supported_locale(self):
        expected = set(SUPPORTED_LOCALES)
        missing = {
            key: sorted(expected.difference(translations))
            for key, translations in MESSAGES.items()
            if expected.difference(translations)
        }
        self.assertEqual(missing, {})

    def test_translates_message_with_context_local_locale(self):
        with locale_context("vi"):
            self.assertEqual(translate("auth.incorrect_password"), "Mật khẩu không đúng.")

    def test_localizes_oauth_completion_without_translating_account_identity(self):
        with locale_context("vi"):
            message = translate(
                "oauth.credential_saved",
                provider="Claude Code",
                account="user@example.com",
            )

        self.assertIn("Đã lưu thông tin xác thực Claude Code", message)
        self.assertIn("user@example.com", message)

    def test_interpolates_named_values_without_translating_identifiers(self):
        with locale_context("de"):
            self.assertEqual(
                translate("credentials.model_unavailable", model="gemini-2.5-flash"),
                "Das Modell gemini-2.5-flash ist für diesen Zugang nicht verfügbar.",
            )

    def test_localizes_nested_panel_payloads(self):
        with locale_context("es", enabled=True):
            payload = translate_payload(
                {
                    "success": False,
                    "detail": "Incorrect password.",
                    "provider": "Google Antigravity",
                }
            )

        self.assertEqual(payload["detail"], "Contraseña incorrecta.")
        self.assertEqual(payload["provider"], "Google Antigravity")

    def test_localizes_console_validation_messages_by_semantic_family(self):
        with locale_context("vi", enabled=True):
            payload = translate_payload(
                {"detail": "Port number must be an integer between 1 and 65535."}
            )

        self.assertEqual(
            payload["detail"],
            "Một hoặc nhiều giá trị không hợp lệ. Hãy kiểm tra yêu cầu của từng trường rồi thử lại.",
        )

    def test_setup_token_errors_do_not_translate_as_success(self):
        with locale_context("vi", enabled=True):
            payload = translate_payload(
                {
                    "detail": (
                        "Remote setup requires a strong SETUP_TOKEN configured in the "
                        "service environment. Restart the service after changing it."
                    )
                }
            )

        self.assertEqual(
            payload["detail"],
            "Thiết lập ban đầu từ xa yêu cầu SETUP_TOKEN đủ mạnh do người vận hành cấu hình.",
        )
        self.assertNotEqual(payload["detail"], "Đã hoàn tất thao tác.")

    def test_does_not_translate_technical_payload_values(self):
        with locale_context("vi", enabled=True):
            payload = translate_payload(
                {
                    "provider": "OpenAI",
                    "model_ids": ["models/gemini-2.5-flash"],
                    "message": "Credential enabled.",
                }
            )

        self.assertEqual(payload["provider"], "OpenAI")
        self.assertEqual(payload["model_ids"], ["models/gemini-2.5-flash"])
        self.assertEqual(payload["message"], "Đã bật thông tin xác thực.")

    def test_preserves_messages_when_localization_is_disabled(self):
        with locale_context("vi", enabled=False):
            self.assertEqual(
                translate_payload({"detail": "Incorrect password."}),
                {"detail": "Incorrect password."},
            )

    def test_localized_json_response_translates_explicit_panel_responses(self):
        with locale_context("vi", enabled=True):
            response = LocalizedJSONResponse({"message": "Signed in."})

        self.assertIn("Đã đăng nhập.".encode("utf-8"), response.body)


if __name__ == "__main__":
    unittest.main()
