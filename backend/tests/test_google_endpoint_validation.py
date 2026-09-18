"""Validation tests for configurable Google service endpoints."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.google_endpoint_validation import (
    normalize_google_api_base_url,
    normalize_google_oauth_base_url,
)


class GoogleEndpointValidationTests(unittest.TestCase):
    def test_trusted_oauth_endpoint_is_normalized(self):
        self.assertEqual(
            normalize_google_oauth_base_url(
                "https://oauth2.googleapis.com/", setting_name="oauth_url"
            ),
            "https://oauth2.googleapis.com",
        )

    def test_oauth_endpoint_rejects_untrusted_lookalike_and_url_components(self):
        rejected = (
            "https://oauth2.googleapis.com.attacker.test",
            "http://oauth2.googleapis.com",
            "https://user@oauth2.googleapis.com",
            "https://oauth2.googleapis.com/token",
            "https://oauth2.googleapis.com?next=https://attacker.test",
            "https://oauth2.googleapis.com#fragment",
            "https://oauth2.googleapis.com:444",
        )

        for value in rejected:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_google_oauth_base_url(value, setting_name="oauth_url")

    def test_userinfo_endpoint_accepts_only_its_exact_trusted_origin(self):
        self.assertEqual(
            normalize_google_oauth_base_url(
                "https://www.googleapis.com", setting_name="google_apis_url"
            ),
            "https://www.googleapis.com",
        )
        with self.assertRaises(ValueError):
            normalize_google_oauth_base_url(
                "https://oauth2.googleapis.com", setting_name="google_apis_url"
            )

    def test_provider_api_endpoint_allows_explicit_http_proxy_with_path(self):
        self.assertEqual(
            normalize_google_api_base_url(
                " http://127.0.0.1:8080/google/code-assist/ ",
                setting_name="code_assist_endpoint",
            ),
            "http://127.0.0.1:8080/google/code-assist",
        )

    def test_provider_api_endpoint_rejects_ambiguous_or_credential_bearing_urls(self):
        rejected = (
            "ftp://proxy.test/google",
            "https://user:secret@proxy.test/google",
            "https://proxy.test/google?target=other",
            "https://proxy.test/google#fragment",
            "https:///missing-host",
            "https://proxy.test\\@attacker.test",
        )

        for value in rejected:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_google_api_base_url(value, setting_name="code_assist_endpoint")


if __name__ == "__main__":
    unittest.main()
