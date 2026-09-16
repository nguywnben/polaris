"""Muse account identity, eligibility and inference credential separation."""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import muse_code as muse
from core.credential_manager import CredentialManager
from core.muse_oauth import MuseOAuthError
from core.provider_import_normalization import normalize_provider_import
from core.provider_registry import get_provider_capabilities, get_static_credential_identity


def credential(**updates):
    return {
        "provider": "muse_code",
        "credential_type": "oauth",
        "access_token": "oauth-secret",
        "api_key": "inference-secret",
        "account_id": "a" * 64,
        **updates,
    }


class MuseCredentialTests(unittest.IsolatedAsyncioTestCase):
    def test_subscription_name_is_independent_of_quota_availability(self):
        view = muse.quota_view(credential(subscription_plan="Muse Code Power Usage"))
        self.assertEqual(view["plan"], "Muse Code Power Usage")
        self.assertTrue(view["supported"])
        self.assertEqual(view["quota_status"], "unavailable")
        self.assertEqual(view["windows"], [])
        self.assertNotIn("secret", str(view))

    def test_missing_quota_is_unknown_and_observations_keep_server_time(self):
        self.assertEqual(muse.quota_view(credential())["quota_status"], "unavailable")
        usage = {
            "window": {"used_percent": 35, "window_duration_mins": 300, "resets_at": 1789547671},
            "weekly": {"used_percent": 120, "resets_at": 1789948800},
            "tier": "opaque-tier",
            "observed_at": 1789534990,
        }
        view = muse.quota_view(credential(subscription_usage=usage))
        self.assertEqual(view["windows"][0]["remaining_percentage"], 65)
        self.assertEqual(view["windows"][1]["remaining_percentage"], 0)
        self.assertEqual(view["observed_at"], 1789534990)
        self.assertEqual(view["subscription_tier"], "opaque-tier")
        self.assertNotIn("plan", view)  # An upstream tier code is not a retail plan name.
        self.assertNotIn("secret", str(view))

    def test_missing_or_unknown_tier_does_not_invent_a_plan(self):
        self.assertNotIn("subscription_tier", muse.quota_view(credential()))
        for tier in ("", "   ", "unknown", "UNKNOWN", "not_applicable"):
            usage = {
                "tier": tier,
                "observed_at": 1,
                "window": {"used_percent": 0, "window_duration_mins": 300, "resets_at": 2},
                "weekly": {"used_percent": 0, "resets_at": 3},
            }
            with self.subTest(tier=tier):
                view = muse.quota_view(credential(subscription_usage=usage))
                self.assertNotIn("subscription_tier", view)
                self.assertNotIn("plan", view)
                self.assertEqual(len(view["windows"]), 2)

    def test_public_models_are_isolated_from_payg_credentials(self):
        from core.provider_registry import credential_supports_model

        scoped = "muse-code/muse-spark-1.3"
        muse_account = credential(model_ids=[scoped])
        self.assertTrue(credential_supports_model(muse_account, scoped))
        self.assertFalse(credential_supports_model(muse_account, "muse-spark-1.3"))
        self.assertFalse(
            credential_supports_model(
                {
                    "provider": "meta",
                    "credential_type": "api_key",
                    "api_key": "key",
                    "model_ids": ["muse-spark-1.3"],
                },
                scoped,
            )
        )

    def test_native_history_is_bound_to_oauth_provider(self):
        from core.meta_native_boundary import seal_native_request, validate_native_request

        mirror = {"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]}
        native = {"input": "Hello", "store": False}
        sealed = seal_native_request(mirror, native, provider="muse_code")
        self.assertEqual(validate_native_request(sealed, "muse_code"), native)
        with self.assertRaises(ValueError):
            validate_native_request(sealed, "meta")
        _, _, body = muse.prepare_request(credential(), sealed, "muse-code/muse-spark-1.3", True)
        self.assertEqual(body["input"], "Hello")
        self.assertEqual(body["model"], "muse-spark-1.3")

    def test_registry_keeps_oauth_account_identity_stable_across_key_rotation(self):
        self.assertEqual(get_provider_capabilities("muse_code").credential_types, ("oauth",))
        self.assertEqual(get_static_credential_identity(credential()), "muse_code:" + "a" * 64)
        self.assertEqual(
            get_static_credential_identity(credential(api_key="new-key")), "muse_code:" + "a" * 64
        )

    def test_native_cli_import_is_muse_not_meta_and_discards_untrusted_quota(self):
        result = normalize_provider_import(
            {
                "schema_version": 1,
                "providers": {
                    "meta": {
                        "mechanism": "oauth",
                        "obtained_via": "device_code",
                        "access_token": "oauth-secret",
                        "api_key": "inference-secret",
                        "api_base_url": "https://api.meta.ai/v1",
                        "user_email": "fixture@example.test",
                        "subs_usage": {"used_percent": 0},
                    }
                },
            },
            variant="muse_code",
        )
        self.assertEqual(result["provider"], "muse_code")
        self.assertNotIn("model_ids", result)
        self.assertNotIn("subscription_usage", result)
        self.assertNotIn("user_email", result)

    def test_import_rejects_conflicting_account_or_provider_material(self):
        for changes in (
            {"provider": "meta"},
            {"credential_type": "api_key"},
            {"mechanism": "api_key"},
            {"base_url": "https://evil.test"},
        ):
            with self.assertRaises(ValueError):
                normalize_provider_import(credential(**changes), variant="muse_code")

    async def test_manager_checks_muse_eligibility_without_google_refresh(self):
        manager = CredentialManager()
        self.assertTrue(await manager._should_refresh_token(credential()))
        with (
            patch.object(manager, "_ensure_initialized", AsyncMock()),
            patch.object(
                muse, "refresh_credential", AsyncMock(return_value=credential(api_key="fresh"))
            ) as refresh,
            patch.object(manager, "_storage_adapter") as storage,
        ):
            storage.store_credential = AsyncMock()
            result = await manager._refresh_token(
                credential(), "muse_code-account.json", mode="primary"
            )
        self.assertEqual(result["api_key"], "fresh")
        refresh.assert_awaited_once()

    async def test_manager_does_not_dispatch_when_refreshed_key_cannot_be_stored(self):
        manager = CredentialManager()
        with (
            patch.object(manager, "_ensure_initialized", AsyncMock()),
            patch.object(
                muse, "refresh_credential", AsyncMock(return_value=credential(api_key="fresh"))
            ),
            patch.object(manager, "_storage_adapter") as storage,
        ):
            storage.store_credential = AsyncMock(return_value=False)
            result = await manager._refresh_token(credential(), "muse.json", mode="primary")
        self.assertIsNone(result)

    def test_oauth_not_misrepresented_as_api_key(self):
        result = muse.normalize_credential(credential())
        self.assertEqual(result["provider"], "muse_code")
        self.assertEqual(result["credential_type"], "oauth")
        self.assertNotIn("refresh_token", result)
        self.assertNotIn("expiry", result)

    def test_rejects_mismatched_provider_and_api_key_only_credentials(self):
        for changes in (
            {"provider": "meta"},
            {"credential_type": "api_key"},
            {"access_token": ""},
            {"account_id": "../bad"},
            {"base_url": "https://evil.test"},
        ):
            with self.assertRaises(MuseOAuthError):
                muse.normalize_credential(credential(**changes))

    async def test_refresh_mints_for_same_account_without_conventional_refresh_grant(self):
        source = credential(model_ids=["muse-spark-1.3"], credential_label="Work")
        with patch.object(
            muse, "mint_key", AsyncMock(return_value=credential(api_key="new-key"))
        ) as mint:
            result = await muse.refresh_credential(source)
        mint.assert_awaited_once_with("oauth-secret")
        self.assertEqual(result["api_key"], "new-key")
        self.assertEqual(result["credential_label"], "Work")
        self.assertEqual(source["api_key"], "inference-secret")

    async def test_forged_imported_account_identity_cannot_replace_another_account(self):
        with patch.object(
            muse, "mint_key", AsyncMock(return_value=credential(account_id="b" * 64))
        ):
            with self.assertRaises(MuseOAuthError):
                await muse.refresh_credential(credential())

    async def test_discovery_uses_minted_key_not_the_account_token(self):
        with (
            patch.object(muse, "mint_key", AsyncMock(return_value=credential(api_key="new-key"))),
            patch.object(
                muse.meta, "discover_models", AsyncMock(return_value=["muse-spark-1.3"])
            ) as catalog,
        ):
            self.assertEqual(await muse.discover_models(credential()), ["muse-code/muse-spark-1.3"])
        self.assertEqual(catalog.call_args.args[0]["api_key"], "new-key")
        self.assertNotIn("access_token", catalog.call_args.args[0])

    def test_request_uses_inference_key_and_rejects_forced_tool_choice(self):
        source = {"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]}
        url, headers, body = muse.prepare_request(
            credential(), source, "muse-code/muse-spark-1.3", True
        )
        self.assertEqual(url, "https://api.meta.ai/v1/responses")
        self.assertEqual(headers["Authorization"], "Bearer inference-secret")
        self.assertFalse(body["store"])
        self.assertEqual(body["model"], "muse-spark-1.3")
        source["tools"] = [
            {"functionDeclarations": [{"name": "f", "parameters": {"type": "object"}}]}
        ]
        for mode in ("ANY", "NONE"):
            source["toolConfig"] = {"functionCallingConfig": {"mode": mode}}
            with self.assertRaises(MuseOAuthError):
                muse.prepare_request(credential(), source, "muse-code/muse-spark-1.3", True)

    def test_no_silent_contributor_or_non_text_model_substitution(self):
        source = {"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]}
        for model in ("muse-image-1.0", "muse-voice-transcribe-1.0", "unknown"):
            with self.assertRaises(ValueError):
                muse.prepare_request(credential(), source, model, False)
        _, _, body = muse.prepare_request(
            credential(), source, "muse-code/muse-spark-1.3-contributor", False
        )
        self.assertEqual(body["model"], "muse-spark-1.3-contributor")
