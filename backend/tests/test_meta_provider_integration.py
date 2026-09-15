"""Meta management contracts use real normalization and offline import parsing."""

import io
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import UploadFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.panel.providers import extended
from core.pool_import import PoolImportError, _parse_archive_payload
from core.provider_registry import (
    EXTENDED_PROVIDERS,
    credential_supports_operation,
    get_static_credential_identity,
)


class MetaProviderIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_polaris_meta_alias_uses_native_adapter_on_first_tool_request(self):
        from core.meta_responses_models import MetaResponsesRequest
        from core.model_pool import resolve_model_request
        from core.models import OpenAIResponsesRequest
        from core.router.primary.responses import create_response
        from fastapi.responses import JSONResponse
        from pydantic import TypeAdapter

        request = TypeAdapter(OpenAIResponsesRequest | MetaResponsesRequest).validate_python(
            {
                "model": "polaris",
                "input": "hello",
                "stream": True,
                "tools": [{"type": "function", "name": "read", "parameters": {"type": "object"}}],
            }
        )
        with (
            patch(
                "core.model_pool.get_virtual_model_pool",
                AsyncMock(return_value={"enabled": True, "selected_models": ["muse-spark-1.3"]}),
            ),
            patch(
                "core.router.primary.meta_responses.create_meta_response",
                AsyncMock(return_value=JSONResponse({"native": True})),
            ),
        ):
            self.assertEqual(
                (await resolve_model_request("polaris")).candidates, ("muse-spark-1.3",)
            )
            response = await create_response(request, "fixture")
        self.assertEqual(json.loads(response.body), {"native": True})

    async def test_native_response_drains_terminal_before_closing_accounting_pipeline(self):
        from core.meta_responses_models import MetaResponsesRequest
        from core.router.primary.meta_responses import create_meta_response

        accounted = False

        async def upstream(**kwargs):
            nonlocal accounted
            yield (
                "data: "
                + json.dumps(
                    {
                        "_polaris_meta_event": {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_fixture",
                                "status": "completed",
                                "output": [],
                                "usage": {"input_tokens": 2, "output_tokens": 1},
                            },
                        }
                    }
                )
                + "\n\n"
            )
            # The real primary stream records token usage and provider health here.
            accounted = True

        with patch("core.api.primary.stream_request", upstream):
            response = await create_meta_response(
                MetaResponsesRequest(model="alias", input="hello"),
                "fixture",
                resolution=SimpleNamespace(
                    candidates=["muse-spark-1.3"], response_model="alias", is_virtual=True
                ),
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(accounted, "Native terminal must not abandon primary usage accounting")

    def test_meta_console_errors_cover_all_locales_and_preserve_english_detail(self):
        from core.i18n import locale_context, translate_text
        from core.meta_provider_i18n import LOCALES, MESSAGES, SOURCE_KEYS

        for key, translations in MESSAGES.items():
            self.assertEqual(set(translations), set(LOCALES), key)
            for locale in LOCALES:
                with locale_context(locale):
                    self.assertEqual(translate_text(translations["en"]), translations[locale])
                self.assertTrue(translations[locale].strip())
                if locale != "en":
                    self.assertNotEqual(translations[locale], translations["en"])
        for source, key in SOURCE_KEYS.items():
            with locale_context("en"):
                self.assertEqual(translate_text(source), source)
            with locale_context("vi"):
                self.assertEqual(translate_text(source), MESSAGES[key]["vi"])

    def test_meta_is_a_complete_api_key_management_provider(self):
        self.assertEqual(EXTENDED_PROVIDERS.get("meta"), "Meta Model API")
        for operation in ("edit", "verify", "test", "model_discovery", "export", "delete"):
            self.assertTrue(
                credential_supports_operation({"provider": "meta", "api_key": "fixture"}, operation)
            )

    def test_meta_archive_normalizes_endpoint_without_trusting_catalog(self):
        payload = _parse_archive_payload(
            json.dumps(
                {
                    "provider": "meta",
                    "api_key": "fixture",
                    "model_ids": ["muse-spark-1.3-contributor"],
                    "validation_status": "verified",
                }
            ).encode(),
            "meta.json",
            variant="meta",
        )
        self.assertEqual(payload["provider"], "meta")
        self.assertEqual(payload["base_url"], "https://api.meta.ai/v1")
        self.assertNotIn("model_ids", payload)
        self.assertNotIn("validation_status", payload)

    def test_meta_archive_rejects_credentials_for_another_provider(self):
        with self.assertRaises(PoolImportError):
            _parse_archive_payload(
                json.dumps({"provider": "kimi", "api_key": "fixture"}).encode(),
                "wrong.json",
                variant="meta",
            )

    def test_meta_key_identity_is_isolated_from_other_providers(self):
        self.assertNotEqual(
            get_static_credential_identity(
                {"provider": "meta", "credential_type": "api_key", "api_key": "fixture"}
            ),
            get_static_credential_identity(
                {"provider": "kimi", "credential_type": "api_key", "api_key": "fixture"}
            ),
        )

    async def test_meta_onboarding_discovers_catalog_without_claiming_inference_access(self):
        secret = "synthetic-meta-onboarding-not-a-real-key"
        with (
            patch(
                "core.panel.providers.extended.discover_extended_models",
                AsyncMock(return_value=["muse-spark-1.3", "muse-spark-1.3-contributor"]),
            ),
            patch(
                "core.panel.providers.extended.store_extended_credential",
                AsyncMock(return_value={"action": "created", "filename": "meta_fixture.json"}),
            ),
        ):
            response = await extended.add_extended_credential(
                "meta", extended.ExtendedCredentialRequest(api_key=secret), token="fixture"
            )
        report = json.loads(response.body)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(report["provider"], "meta")
        self.assertEqual(report["model_count"], 2)
        self.assertTrue(report["connection_test_required"])
        self.assertNotIn(secret, json.dumps(report))

    def test_meta_management_mutations_have_scoped_audit_actions(self):
        from core.management_audit import classify_management_mutation

        for suffix, action in (
            ("credentials", "credential.create"),
            ("credentials/import", "credential.import"),
        ):
            mutation = classify_management_mutation(
                "POST", f"/api/providers/extended/meta/{suffix}"
            )
            self.assertIsNotNone(mutation)
            self.assertEqual(mutation.action, action)

    async def test_meta_import_is_offline_unverified_and_never_returns_secret(self):
        secret = "synthetic-meta-import-not-a-real-key"
        source = UploadFile(
            filename="meta.json",
            file=io.BytesIO(json.dumps({"provider": "meta", "api_key": secret}).encode()),
        )
        with (
            patch(
                "core.httpx_client.http_client.get_client",
                side_effect=AssertionError("offline import must not use network"),
            ),
            patch(
                "core.provider_scoped_import.store_extended_credential",
                AsyncMock(return_value={"action": "created", "filename": "meta_fixture.json"}),
            ),
        ):
            response = await extended.import_extended_credentials("meta", [source], token="fixture")
        report = json.loads(response.body)
        self.assertEqual(report["uploaded_count"], 1)
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(report["results"][0]["validation_status"], "unverified")
        self.assertEqual(report["results"][0]["model_count"], 0)
        self.assertNotIn(secret, json.dumps(report))


if __name__ == "__main__":
    unittest.main()
