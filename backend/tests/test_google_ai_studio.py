"""Tests for Google AI Studio provider contracts."""

from __future__ import annotations

import io
import json
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi import UploadFile

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.google_ai_studio import (
    GoogleAIStudioError,
    GoogleAIStudioValidation,
    build_api_key_headers,
    build_generation_url,
    parse_api_key_import_payload,
    parse_model_ids,
    validate_api_key,
)
from core.panel.providers.google_ai_studio import (
    _extract_ai_studio_import_file,
    import_google_ai_studio_credentials,
)
from core.provider_registry import (
    GOOGLE_AI_STUDIO,
    GOOGLE_ANTIGRAVITY,
    api_key_fingerprint,
    credential_supports_model,
    get_credential_provider,
    get_static_credential_identity,
)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class GoogleAIStudioImportPayloadTests(unittest.TestCase):
    def test_parses_single_key_object(self):
        self.assertEqual(
            parse_api_key_import_payload(
                {"provider": "google_ai_studio", "api_key": " example-key "}
            ),
            ["example-key"],
        )

    def test_parses_mixed_key_array(self):
        self.assertEqual(
            parse_api_key_import_payload(["first-key", {"api_key": "second-key"}]),
            ["first-key", "second-key"],
        )

    def test_parses_api_keys_container(self):
        self.assertEqual(
            parse_api_key_import_payload({"api_keys": ["first-key", "second-key"]}),
            ["first-key", "second-key"],
        )

    def test_rejects_payload_for_another_provider(self):
        with self.assertRaisesRegex(ValueError, "different provider"):
            parse_api_key_import_payload(
                {"provider": "google_antigravity", "api_key": "example-key"}
            )


class GoogleAIStudioImportArchiveTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def build_zip(entries):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, payload in entries.items():
                archive.writestr(name, json.dumps(payload))
        return buffer.getvalue()

    async def test_extracts_api_keys_from_zip_without_writing_files(self):
        upload = UploadFile(
            filename="keys.zip",
            file=io.BytesIO(
                self.build_zip(
                    {
                        "one.json": {"api_key": "first-key"},
                        "nested/two.json": {"api_keys": ["second-key", "third-key"]},
                    }
                )
            ),
        )

        candidates, errors = await _extract_ai_studio_import_file(upload)

        self.assertEqual([key for _, key in candidates], ["first-key", "second-key", "third-key"])
        self.assertEqual(errors, [])

    async def test_keeps_valid_zip_entries_when_another_entry_is_invalid(self):
        upload = UploadFile(
            filename="mixed.zip",
            file=io.BytesIO(
                self.build_zip(
                    {
                        "valid.json": {"api_key": "valid-key"},
                        "invalid.json": {"provider": "google_antigravity", "api_key": "wrong"},
                    }
                )
            ),
        )

        candidates, errors = await _extract_ai_studio_import_file(upload)

        self.assertEqual([key for _, key in candidates], ["valid-key"])
        self.assertEqual(len(errors), 1)
        self.assertIn("different provider", errors[0]["message"])

    async def test_batch_import_deduplicates_and_never_returns_key_values(self):
        first_key = "example-google-key-value-one"
        second_key = "example-google-key-value-two"
        upload = UploadFile(
            filename="keys.json",
            file=io.BytesIO(json.dumps({"api_keys": [first_key, first_key, second_key]}).encode()),
        )
        validation = GoogleAIStudioValidation(model_ids=["gemini-test"])

        with (
            patch(
                "core.panel.providers.google_ai_studio.validate_api_key",
                new=AsyncMock(return_value=validation),
            ) as validate_mock,
            patch(
                "core.panel.providers.google_ai_studio.store_imported_connection",
                new=AsyncMock(
                    side_effect=[
                        {
                            "status": "success",
                            "action": "created",
                            "filename": "first.json",
                            "label": "First",
                        },
                        {
                            "status": "success",
                            "action": "created",
                            "filename": "second.json",
                            "label": "Second",
                        },
                    ]
                ),
            ),
        ):
            response = await import_google_ai_studio_credentials(files=[upload], token="test")

        payload = json.loads(response.body)
        response_text = response.body.decode()
        self.assertEqual(payload["uploaded_count"], 2)
        self.assertEqual(payload["skipped_count"], 1)
        self.assertEqual(payload["error_count"], 0)
        validate_mock.assert_not_awaited()
        self.assertNotIn(first_key, response_text)
        self.assertNotIn(second_key, response_text)


class ProviderRegistryTests(unittest.TestCase):
    def test_legacy_oauth_credentials_default_to_antigravity(self):
        credential = {"token": "access", "refresh_token": "refresh"}
        self.assertEqual(get_credential_provider(credential), GOOGLE_ANTIGRAVITY)

    def test_ai_studio_key_has_stable_non_secret_identity(self):
        credential = {
            "provider": GOOGLE_AI_STUDIO,
            "credential_type": "api_key",
            "api_key": "example-google-key-value",
        }
        identity = get_static_credential_identity(credential)
        self.assertEqual(
            identity,
            f"{GOOGLE_AI_STUDIO}:{api_key_fingerprint(credential['api_key'])}",
        )
        self.assertNotIn(credential["api_key"], identity)

    def test_ai_studio_only_accepts_gemini_and_gemma_models(self):
        credential = {
            "provider": GOOGLE_AI_STUDIO,
            "credential_type": "api_key",
            "api_key": "example-google-key-value",
        }
        self.assertTrue(credential_supports_model(credential, "gemini-2.5-flash"))
        self.assertTrue(credential_supports_model(credential, "gemma-3-27b-it"))
        self.assertFalse(credential_supports_model(credential, "claude-sonnet-4-6"))


class GoogleAIStudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_reads_next_page_after_filtered_empty_page(self):
        pages = [
            FakeResponse(200, {"models": [], "nextPageToken": "next+/="}),
            FakeResponse(
                200,
                {
                    "models": [
                        {
                            "name": "models/gemini-test",
                            "supportedGenerationMethods": ["generateContent"],
                        }
                    ]
                },
            ),
        ]
        with (
            patch(
                "core.google_ai_studio.get_google_ai_studio_api_url",
                AsyncMock(return_value="https://generativelanguage.googleapis.com"),
            ),
            patch("core.google_ai_studio.get_async", AsyncMock(side_effect=pages)) as request,
        ):
            result = await validate_api_key("example-google-key-value")
        self.assertEqual(result.model_ids, ["gemini-test"])
        self.assertEqual(
            parse_qs(urlparse(request.call_args.args[0]).query)["pageToken"], ["next+/="]
        )

    async def test_discovery_rejects_repeated_cursor_instead_of_partial_success(self):
        page = FakeResponse(
            200,
            {
                "models": [
                    {
                        "name": "models/gemini-test",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ],
                "nextPageToken": "repeat",
            },
        )
        with (
            patch(
                "core.google_ai_studio.get_google_ai_studio_api_url",
                AsyncMock(return_value="https://generativelanguage.googleapis.com"),
            ),
            patch("core.google_ai_studio.get_async", AsyncMock(return_value=page)),
        ):
            with self.assertRaises(GoogleAIStudioError) as caught:
                await validate_api_key("example-google-key-value")
        self.assertEqual(caught.exception.status_code, 502)

    def test_generation_url_encodes_untrusted_model_path(self):
        url = build_generation_url(
            "https://generativelanguage.googleapis.com",
            "gemini-2.5-flash/../../unsafe",
            streaming=True,
        )
        self.assertIn("gemini-2.5-flash%2F..%2F..%2Funsafe", url)
        self.assertTrue(url.endswith(":streamGenerateContent?alt=sse"))

    def test_api_key_is_sent_in_google_header(self):
        headers = build_api_key_headers("example-key")
        self.assertEqual(headers["x-goog-api-key"], "example-key")
        self.assertNotIn("Authorization", headers)

    def test_model_parser_only_keeps_generate_content_models(self):
        models = parse_model_ids(
            {
                "models": [
                    {
                        "name": "models/gemini-2.5-flash",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-embedding-001",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            }
        )
        self.assertEqual(models, ["gemini-2.5-flash"])

    async def test_key_validation_returns_available_models(self):
        response = FakeResponse(
            200,
            {
                "models": [
                    {
                        "name": "models/gemini-2.5-flash",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ]
            },
        )
        with (
            patch(
                "core.google_ai_studio.get_google_ai_studio_api_url",
                AsyncMock(return_value="https://generativelanguage.googleapis.com"),
            ),
            patch(
                "core.google_ai_studio.get_async",
                AsyncMock(return_value=response),
            ),
        ):
            result = await validate_api_key("example-google-key-value")

        self.assertEqual(result.model_ids, ["gemini-2.5-flash"])
        self.assertEqual(result.model_count, 1)

    async def test_key_validation_sanitizes_rejected_key_error(self):
        response = FakeResponse(403, {"error": {"message": "sensitive upstream"}})
        with (
            patch(
                "core.google_ai_studio.get_google_ai_studio_api_url",
                AsyncMock(return_value="https://generativelanguage.googleapis.com"),
            ),
            patch(
                "core.google_ai_studio.get_async",
                AsyncMock(return_value=response),
            ),
        ):
            with self.assertRaises(GoogleAIStudioError) as context:
                await validate_api_key("example-google-key-value")

        self.assertNotIn("sensitive upstream", str(context.exception))


if __name__ == "__main__":
    unittest.main()
