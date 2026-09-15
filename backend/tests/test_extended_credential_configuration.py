"""Extended provider pool editing, discovery and explicit-test boundaries."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, Response

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.hosted_providers import HostedProviderError
from core.models import CredentialModelTestRequest, CredentialUpdateRequest
from core.panel import credentials as panel


def credential(provider="kimi", **values):
    return {
        "provider": provider,
        "credential_type": "api_key",
        "api_key": "synthetic-secret",
        "credential_label": "Keep label",
        "model_ids": ["model-old"],
        **values,
    }


def storage_for(data, others=None):
    storage = AsyncMock()
    storage.get_credential.return_value = data
    storage.get_all_credentials.return_value = {"current.json": data, **(others or {})}
    storage.store_credential.return_value = True
    return storage


class ExtendedCredentialConfigurationTests(unittest.IsolatedAsyncioTestCase):
    def test_editor_exposes_only_provider_relevant_fields(self):
        cases = {
            "kimi": {"base_url"},
            "cloudflare": {"base_url", "account_id"},
            "nvidia": {"base_url"},
            "poolside": {"base_url"},
            "kimchi": {"base_url"},
            "kilo": {"base_url", "organization_id"},
            "opencode": {"base_url", "plan"},
            "kiro": {"region", "profile_arn"},
        }
        for provider, fields in cases.items():
            with self.subTest(provider=provider):
                data = credential(
                    provider,
                    base_url="https://example.invalid",
                    account_id="account",
                    organization_id="organization",
                    region="us-east-1",
                    profile_arn="profile",
                    plan="zen",
                    refresh_token="never-return-this",
                )
                payload = panel._credential_configuration_payload("current.json", data)
                self.assertEqual(
                    set(payload["editable_fields"]), {"api_key", "credential_label"} | fields
                )
                for field in fields:
                    self.assertEqual(payload[field], data[field])
                    self.assertTrue(payload[f"has_{field}"])
                self.assertNotIn("synthetic-secret", json.dumps(payload))
                self.assertNotIn("never-return-this", json.dumps(payload))
                for field in {
                    "base_url",
                    "account_id",
                    "organization_id",
                    "plan",
                    "region",
                    "profile_arn",
                } - fields:
                    self.assertNotIn(field, payload)

    async def test_blank_key_preserved_and_connection_edit_discovers_without_inference(self):
        data = credential("cloudflare", account_id="a" * 32)
        storage = storage_for(data)
        with (
            patch.object(panel, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(
                panel, "discover_extended_models", AsyncMock(return_value=["@cf/model"])
            ) as discover,
            patch.object(panel, "test_extended_credential", AsyncMock()) as inference,
        ):
            response = await panel.update_credential_configuration(
                "current.json",
                CredentialUpdateRequest(api_key=None, account_id="B" * 32),
                token="session",
                mode="provider",
            )
        saved = storage.store_credential.call_args.args[1]
        self.assertEqual(saved["api_key"], "synthetic-secret")
        self.assertEqual(saved["account_id"], "b" * 32)
        self.assertEqual(saved["model_ids"], ["@cf/model"])
        self.assertEqual(saved["credential_label"], "Keep label")
        self.assertNotIn("api_key", json.loads(response.body)["changed_fields"])
        discover.assert_awaited_once()
        inference.assert_not_awaited()
        self.assertNotIn("synthetic-secret", response.body.decode())

    async def test_label_only_edit_does_not_need_network(self):
        storage = storage_for(credential())
        with (
            patch.object(panel, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(panel, "discover_extended_models", AsyncMock()) as discover,
        ):
            await panel.update_credential_configuration(
                "current.json",
                CredentialUpdateRequest(credential_label="Rename"),
                token="session",
                mode="provider",
            )
        discover.assert_not_awaited()
        self.assertEqual(storage.store_credential.call_args.args[1]["api_key"], "synthetic-secret")

    async def test_invalid_endpoint_is_rejected_before_any_network_or_write(self):
        storage = storage_for(credential())
        with (
            patch.object(panel, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(panel, "discover_extended_models", AsyncMock()) as discover,
        ):
            with self.assertRaises(HTTPException) as raised:
                await panel.update_credential_configuration(
                    "current.json",
                    CredentialUpdateRequest(base_url="http://127.0.0.1:4444"),
                    token="session",
                    mode="provider",
                )
        self.assertEqual(raised.exception.status_code, 400)
        discover.assert_not_awaited()
        storage.store_credential.assert_not_awaited()

    async def test_unrelated_provider_fields_are_rejected(self):
        storage = storage_for(credential())
        with patch.object(panel, "get_storage_adapter", AsyncMock(return_value=storage)):
            with self.assertRaises(HTTPException) as raised:
                await panel.update_credential_configuration(
                    "current.json",
                    CredentialUpdateRequest(account_id="a" * 32),
                    token="session",
                    mode="provider",
                )
        self.assertEqual(raised.exception.status_code, 422)
        storage.store_credential.assert_not_awaited()

    async def test_discovery_failure_leaves_stored_credential_untouched(self):
        storage = storage_for(credential())
        with (
            patch.object(panel, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(
                panel,
                "discover_extended_models",
                AsyncMock(
                    side_effect=HostedProviderError(
                        "Provider model discovery failed with HTTP 401.", 401
                    )
                ),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await panel.update_credential_configuration(
                    "current.json",
                    CredentialUpdateRequest(api_key="replacement-secret"),
                    token="session",
                    mode="provider",
                )
        self.assertEqual(raised.exception.status_code, 401)
        storage.store_credential.assert_not_awaited()

    async def test_connection_context_duplicate_is_rejected(self):
        data = credential(
            "cloudflare", account_id="a" * 32, base_url="https://api.cloudflare.com/client/v4"
        )
        storage = storage_for(data, {"other.json": {**data, "account_id": "b" * 32}})
        with (
            patch.object(panel, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(panel, "discover_extended_models", AsyncMock(return_value=["@cf/model"])),
        ):
            with self.assertRaises(HTTPException) as raised:
                await panel.update_credential_configuration(
                    "current.json",
                    CredentialUpdateRequest(account_id="b" * 32),
                    token="session",
                    mode="provider",
                )
        self.assertEqual(raised.exception.status_code, 409)
        storage.store_credential.assert_not_awaited()

    async def test_models_refresh_updates_catalog_without_claiming_key_validity(self):
        storage = storage_for(credential())
        with (
            patch.object(panel, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(
                panel, "discover_extended_models", AsyncMock(return_value=["model-fresh"])
            ) as discover,
            patch.object(panel, "test_extended_credential", AsyncMock()) as inference,
        ):
            response = await panel.get_credential_models(
                "current.json", token="session", mode="provider"
            )
        self.assertEqual(json.loads(response.body)["model_ids"], ["model-fresh"])
        self.assertEqual(storage.store_credential.call_args.args[1]["model_ids"], ["model-fresh"])
        discover.assert_awaited_once()
        inference.assert_not_awaited()
        storage.update_credential_state.assert_not_awaited()

    async def test_explicit_model_test_uses_extended_transport_and_429_is_not_success(self):
        for code in [200, 401, 429, 502]:
            with self.subTest(code=code):
                storage = storage_for(credential())
                with (
                    patch.object(panel, "get_storage_adapter", AsyncMock(return_value=storage)),
                    patch.object(
                        panel,
                        "test_extended_credential",
                        AsyncMock(return_value=Response("{}", status_code=code)),
                    ) as test,
                    patch.object(panel, "discover_extended_models", AsyncMock()) as discover,
                ):
                    response = await panel._test_credential_unbounded(
                        "current.json",
                        CredentialModelTestRequest(model="model-old"),
                        mode="provider",
                    )
                body = json.loads(response.body)
                self.assertEqual(body["success"], code == 200)
                self.assertEqual(response.status_code, code)
                test.assert_awaited_once()
                discover.assert_not_awaited()

    async def test_plan_change_uses_new_endpoint_and_preserves_metadata(self):
        storage = storage_for(
            credential(
                "opencode",
                plan="zen",
                base_url="https://opencode.ai/zen/v1",
                model_ids=["claude-old"],
            )
        )
        with (
            patch.object(panel, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(panel, "discover_extended_models", AsyncMock(return_value=["glm-5"])),
        ):
            await panel.update_credential_configuration(
                "current.json", CredentialUpdateRequest(plan="go"), token="session", mode="provider"
            )
        saved = storage.store_credential.call_args.args[1]
        self.assertEqual(saved["plan"], "go")
        self.assertEqual(saved["base_url"], "https://opencode.ai/zen/go/v1")
        self.assertEqual(saved["model_ids"], ["glm-5"])
        self.assertEqual(saved["credential_label"], "Keep label")

    async def test_kiro_region_edit_retains_label_but_clears_explicit_profile(self):
        storage = storage_for(
            credential(
                "kiro",
                region="us-east-1",
                profile_arn="arn:aws:codewhisperer:us-east-1:123456789012:profile/test",
            )
        )
        with (
            patch.object(panel, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(
                panel, "discover_extended_models", AsyncMock(return_value=["claude-model"])
            ),
        ):
            await panel.update_credential_configuration(
                "current.json",
                CredentialUpdateRequest(region="eu-central-1", profile_arn=""),
                token="session",
                mode="provider",
            )
        saved = storage.store_credential.call_args.args[1]
        self.assertEqual(saved["region"], "eu-central-1")
        self.assertFalse(saved.get("profile_arn"))
        self.assertEqual(saved["credential_label"], "Keep label")

    async def test_missing_extended_catalog_does_not_borrow_another_credentials_models(self):
        with patch.object(panel.model_catalog_service, "get_catalog", AsyncMock()) as catalog:
            models = await panel._get_available_credential_models(credential(model_ids=[]))
        self.assertEqual(models, [])
        catalog.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
