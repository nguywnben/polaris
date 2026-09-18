"""Onboarding response semantics without live credentials or upstream traffic."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.extended_provider_runtime import discover_extended_models
from core.hosted_providers import HostedProviderError
from core.panel.providers import extended
from core.provider_registry import EXTENDED_PROVIDERS
from core.provider_store import store_extended_credential

TEST_KEY = "synthetic-onboarding-secret"


class ExtendedCredentialStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_key_onboarding_does_not_claim_file_import_or_verified_inference(self):
        with patch(
            "core.provider_store.credential_manager.add_primary_credential", new_callable=AsyncMock
        ) as save:
            save.return_value = {"action": "created"}
            result = await store_extended_credential(
                {"provider": "kimi", "api_key": TEST_KEY}, ["kimi-test"]
            )
        filename, payload = save.call_args.args
        self.assertEqual(result["filename"], filename)
        self.assertEqual(payload["model_ids"], ["kimi-test"])
        self.assertNotIn("validation_status", payload)
        self.assertNotIn(TEST_KEY, json.dumps(result))


def request(**extra):
    return extended.ExtendedCredentialRequest(api_key=TEST_KEY, **extra)


class ExtendedProviderOnboardingTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_eight_providers_reach_onboarding_with_required_context(self):
        for provider in EXTENDED_PROVIDERS:
            with (
                self.subTest(provider=provider),
                patch.object(
                    extended, "discover_extended_models", AsyncMock(return_value=["model"])
                ),
                patch.object(
                    extended,
                    "store_extended_credential",
                    AsyncMock(return_value={"action": "created", "filename": "safe.json"}),
                ) as store,
            ):
                extra = {"account_id": "a" * 32} if provider == "cloudflare" else {}
                if provider == "muse_code":
                    with self.assertRaises(HTTPException) as rejected:
                        await extended.add_extended_credential(provider, request(), token="session")
                    self.assertEqual(rejected.exception.status_code, 404)
                    store.assert_not_awaited()
                    continue
                response = await extended.add_extended_credential(
                    provider, request(**extra), token="session"
                )
                self.assertEqual(response.status_code, 201)
                self.assertEqual(store.await_args.args[0]["provider"], provider)
                self.assertEqual(store.await_args.args[0]["credential_type"], "api_key")

    async def test_create_and_update_status_with_secret_free_response(self):
        for action, status in (("created", 201), ("updated", 200)):
            with (
                self.subTest(action=action),
                patch.object(
                    extended, "discover_extended_models", AsyncMock(return_value=["kimi-k2"])
                ),
                patch.object(
                    extended,
                    "store_extended_credential",
                    AsyncMock(return_value={"action": action, "filename": "kimi-safe.json"}),
                ) as store,
            ):
                response = await extended.add_extended_credential(
                    "kimi", request(credential_label="Work"), token="test-panel-session"
                )
                body = json.loads(response.body)
                self.assertEqual(response.status_code, status)
                self.assertTrue(body["credential_saved"])
                self.assertEqual(body["credential_action"], action)
                self.assertEqual(body["provider"], "kimi")
                self.assertEqual(body["model_count"], 1)
                self.assertNotIn(TEST_KEY, response.body.decode())
                self.assertNotIn("test-panel-session", response.body.decode())
                self.assertEqual(store.await_args.args[0]["api_key"], TEST_KEY)
                self.assertEqual(store.await_args.args[0]["credential_label"], "Work")
                self.assertEqual(store.await_args.args[1], ["kimi-k2"])

    async def test_unknown_provider_never_discovers_or_stores(self):
        with (
            patch.object(extended, "discover_extended_models", new_callable=AsyncMock) as discover,
            patch.object(extended, "store_extended_credential", new_callable=AsyncMock) as store,
        ):
            with self.assertRaises(HTTPException) as raised:
                await extended.add_extended_credential("unknown", request(), token="session")
        self.assertEqual(raised.exception.status_code, 404)
        discover.assert_not_awaited()
        store.assert_not_awaited()

    def test_missing_and_empty_key_fail_schema_validation(self):
        for data in ({}, {"api_key": ""}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                extended.ExtendedCredentialRequest(**data)

    async def test_whitespace_key_is_rejected_before_network_or_storage(self):
        with (
            patch.object(extended, "discover_extended_models", new_callable=AsyncMock) as discover,
            patch.object(extended, "store_extended_credential", new_callable=AsyncMock) as store,
        ):
            with self.assertRaises(HTTPException) as raised:
                await extended.add_extended_credential(
                    "kimi", extended.ExtendedCredentialRequest(api_key="   "), token="session"
                )
        self.assertEqual(raised.exception.status_code, 400)
        discover.assert_not_awaited()
        store.assert_not_awaited()

    async def test_public_catalog_requires_explicit_inference_test(self):
        with (
            patch.object(extended, "discover_extended_models", AsyncMock(return_value=["gpt-5"])),
            patch.object(
                extended,
                "store_extended_credential",
                AsyncMock(return_value={"action": "created", "filename": "opencode-safe.json"}),
            ) as store,
            patch(
                "core.extended_provider_runtime.test_extended_credential", new_callable=AsyncMock
            ) as inference,
        ):
            response = await extended.add_extended_credential(
                "opencode", request(plan="go"), token="session"
            )
        body = json.loads(response.body)
        self.assertTrue(body["connection_test_required"])
        self.assertNotEqual(body.get("validation_status"), "verified")
        self.assertFalse(body.get("inference_verified", False))
        self.assertEqual(store.await_args.args[0]["plan"], "go")
        self.assertEqual(store.await_args.args[0]["base_url"], "https://opencode.ai/zen/go/v1")
        inference.assert_not_awaited()

    async def test_runtime_discovery_timeout_becomes_safe_504_and_never_stores(self):
        with (
            patch.object(extended, "discover_extended_models", discover_extended_models),
            patch("core.opencode.discover_models", AsyncMock(side_effect=TimeoutError(TEST_KEY))),
            patch.object(extended, "store_extended_credential", new_callable=AsyncMock) as store,
        ):
            with self.assertRaises(HTTPException) as raised:
                await extended.add_extended_credential("opencode", request(), token="session")
        self.assertEqual(raised.exception.status_code, 504)
        self.assertNotIn(TEST_KEY, str(raised.exception.detail))
        self.assertIn("timed out", raised.exception.detail)
        store.assert_not_awaited()

    async def test_safe_upstream_auth_failure_retains_status_without_storing(self):
        with (
            patch.object(
                extended,
                "discover_extended_models",
                AsyncMock(side_effect=HostedProviderError("Provider rejected this API key.", 401)),
            ),
            patch.object(extended, "store_extended_credential", new_callable=AsyncMock) as store,
        ):
            with self.assertRaises(HTTPException) as raised:
                await extended.add_extended_credential("kimi", request(), token="session")
        self.assertEqual(raised.exception.status_code, 401)
        self.assertNotIn(TEST_KEY, str(raised.exception.detail))
        store.assert_not_awaited()
