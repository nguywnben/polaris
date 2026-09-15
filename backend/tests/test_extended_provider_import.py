"""Extended provider archive imports use catalogs, not inference probes."""

from __future__ import annotations

import asyncio
import io
import json
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import UploadFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.pool_import import classify_pool_credential, restore_pool_archive
from core.provider_import_normalization import normalize_provider_import
from core.provider_registry import EXTENDED_PROVIDERS
from core.provider_store import store_extended_credential


def credential(provider, **extra):
    result = {"provider": provider, "api_key": "test-key-never-live", **extra}
    if provider == "cloudflare":
        result.setdefault("account_id", "a" * 32)
    return result


def archive(payloads):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as output:
        for index, payload in enumerate(payloads):
            output.writestr(f"credential-{index}.json", json.dumps(payload))
    buffer.seek(0)
    return UploadFile(filename="credentials.zip", file=buffer)


class ExtendedImportNormalizationTests(unittest.TestCase):
    def test_all_extended_providers_normalize_and_classify_without_network(self):
        for provider in EXTENDED_PROVIDERS:
            with self.subTest(provider=provider):
                result = normalize_provider_import(credential(provider))
                self.assertEqual(result["provider"], provider)
                self.assertEqual(result["credential_type"], "api_key")
                self.assertEqual(classify_pool_credential(result), provider)

    def test_constrained_import_and_provider_id_alias(self):
        self.assertEqual(
            normalize_provider_import({"api_key": "test-key"}, "opencode")["plan"], "zen"
        )
        self.assertEqual(
            normalize_provider_import({"provider_id": "opencode", "api_key": "test-key"})[
                "provider"
            ],
            "opencode",
        )

    def test_rejects_mismatched_authentication_or_connection(self):
        invalid = [
            credential("opencode", credential_type="oauth"),
            credential("opencode", access_token="unexpected-oauth"),
            credential("opencode", refresh_token="unexpected-oauth"),
            credential("opencode", tokens={"access_token": "nested"}),
            credential("cloudflare", account_id=""),
            credential("kiro", region="invalid"),
            credential("opencode", plan="unknown"),
            credential("kilo", organization_id="bad\nheader"),
            credential("kimi", base_url="https://attacker.example/v1"),
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                normalize_provider_import(payload)
        with self.assertRaises(ValueError):
            normalize_provider_import(credential("kilo"), "kimi")

    def test_drops_untrusted_state_and_unrelated_connection_fields(self):
        payload = credential(
            "opencode",
            plan="go",
            credential_label="Work",
            enabled=True,
            validation_status="verified",
            model_ids=["untrusted"],
            organization_id="irrelevant",
        )
        result = normalize_provider_import(payload)
        self.assertEqual(result["credential_label"], "Work")
        for field in ("enabled", "validation_status", "model_ids", "organization_id"):
            self.assertNotIn(field, result)
        self.assertIn("enabled", payload)


class ExtendedPoolImportTests(unittest.IsolatedAsyncioTestCase):
    async def test_mixed_archive_imports_all_extended_catalogs(self):
        stored = {"filename": "safe.json", "action": "created", "label": "Account"}
        with (
            patch("core.pool_import.discover_extended_models", new_callable=AsyncMock) as discover,
            patch(
                "core.pool_import.store_extended_credential",
                new_callable=AsyncMock,
                return_value=stored,
            ) as store,
        ):
            discover.side_effect = lambda data: [
                "muse-spark-1.3" if data["provider"] == "meta" else "gpt-5"
            ]
            report = await restore_pool_archive(
                archive([credential(p) for p in EXTENDED_PROVIDERS])
            )
        self.assertEqual(report["uploaded_count"], 13)
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(discover.await_count, 13)
        self.assertEqual(store.await_count, 13)
        self.assertEqual(
            {call.args[0]["provider"] for call in store.await_args_list},
            {
                "kimi",
                "kiro",
                "cloudflare",
                "nvidia",
                "opencode",
                "poolside",
                "kimchi",
                "kilo",
                "meta",
                "groq",
                "deepseek",
                "mistral",
                "cerebras",
            },
        )
        for result in report["results"]:
            self.assertEqual(result["validation_status"], "unverified")
        self.assertNotIn("test-key-never-live", json.dumps(report))

    async def test_connection_identity_not_key_alone_determines_duplicates(self):
        payloads = [
            credential("opencode", plan="zen"),
            credential("opencode", plan="zen", base_url="https://opencode.ai/zen/v1/"),
            credential("opencode", plan="go"),
            credential("cloudflare", account_id="a" * 32),
            credential("cloudflare", account_id="b" * 32),
            credential("kilo", organization_id="one"),
            credential("kilo", organization_id="two"),
            credential("kimi", base_url="https://api.moonshot.ai/v1"),
            credential("kimi", base_url="https://api.moonshot.cn/v1"),
            credential("kiro", region="us-east-1"),
            credential("kiro", region="eu-central-1"),
        ]
        with (
            patch("core.pool_import.discover_extended_models", AsyncMock(return_value=["gpt-5"])),
            patch(
                "core.pool_import.store_extended_credential",
                AsyncMock(return_value={"filename": "safe.json", "action": "created"}),
            ),
        ):
            report = await restore_pool_archive(archive(payloads))
        self.assertEqual(report["uploaded_count"], 10)
        self.assertEqual(report["skipped_count"], 1)

    async def test_failed_catalog_never_stores_or_exposes_upstream_error(self):
        with (
            patch(
                "core.pool_import.discover_extended_models",
                AsyncMock(side_effect=RuntimeError("upstream leaked test-key-never-live")),
            ),
            patch("core.pool_import.store_extended_credential", new_callable=AsyncMock) as store,
        ):
            report = await restore_pool_archive(archive([credential("opencode")]))
        store.assert_not_awaited()
        self.assertEqual(report["error_count"], 1)
        self.assertNotIn("test-key-never-live", json.dumps(report))

    async def test_cancellation_propagates_without_storing(self):
        with (
            patch(
                "core.pool_import.discover_extended_models",
                AsyncMock(side_effect=asyncio.CancelledError),
            ),
            patch("core.pool_import.store_extended_credential", new_callable=AsyncMock) as store,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await restore_pool_archive(archive([credential("opencode")]))
        store.assert_not_awaited()

    async def test_real_store_marks_catalog_access_unverified_for_every_provider(self):
        with patch(
            "core.provider_store.credential_manager.add_primary_credential",
            AsyncMock(return_value={"action": "created", "filename": "safe.json"}),
        ) as persist:
            for provider in EXTENDED_PROVIDERS:
                with self.subTest(provider=provider):
                    data = normalize_provider_import(credential(provider, credential_label="Work"))
                    models = ["muse-spark-1.3"] if provider == "meta" else ["gpt-5"]
                    await store_extended_credential(data, models, file_import=True)
                    stored = persist.await_args.args[1]
                    self.assertEqual(stored["validation_status"], "unverified")
                    self.assertEqual(stored["model_ids"], models)
                    self.assertEqual(stored["credential_label"], "Work")

    async def test_bad_entry_does_not_prevent_valid_entry(self):
        with (
            patch("core.pool_import.discover_extended_models", AsyncMock(return_value=["gpt-5"])),
            patch(
                "core.pool_import.store_extended_credential",
                AsyncMock(return_value={"filename": "safe.json", "action": "created"}),
            ),
        ):
            report = await restore_pool_archive(
                archive([credential("opencode", credential_type="oauth"), credential("kimi")])
            )
        self.assertEqual(report["uploaded_count"], 1)
        self.assertEqual(report["error_count"], 1)
