"""Synthetic native OAuth import fixtures; no external credentials or upstream calls."""

from __future__ import annotations

import base64
import io
import json
import shutil
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.credential_fleet_query import enrich_credential_summary
from core.credential_pool import resolve_credential_email
from core.panel.providers.anthropic import _parse_anthropic_json
from core.panel.providers.openai import _parse_openai_json
from core.panel.providers.xai import _parse_xai_import_document
from core.pool_import import extract_pool_archive, restore_openai_credential, restore_xai_credential
from core.provider_import_normalization import normalize_provider_import
from fastapi import UploadFile


def fixture_jwt(claims):
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"fixture.{encoded}.unsigned"


def codex_fixture():
    return {
        "OPENAI_API_KEY": None,
        "tokens": {
            "access_token": fixture_jwt({"exp": 1800000000}),
            "refresh_token": "fixture-refresh",
            "id_token": fixture_jwt(
                {
                    "email": "fixture@example.invalid",
                    "https://api.openai.com/auth": {"chatgpt_account_id": "fixture-account"},
                }
            ),
        },
        "last_refresh": "2026-09-15T00:00:00Z",
    }


class ProviderImportNormalizationTests(unittest.TestCase):
    def test_fleet_projects_only_allowlisted_import_provenance_without_changing_health(self):
        for value in ("unverified", "verified", "SECRET"):
            result = enrich_credential_summary(
                {"filename": "fixture.json", "disabled": False},
                {
                    "provider": "openai",
                    "credential_type": "oauth",
                    "access_token": "SECRET",
                    "validation_status": value,
                },
                backend_type="sqlite",
                mode="provider",
            )
            self.assertEqual(
                result.get("validation_status"), "unverified" if value == "unverified" else None
            )
            self.assertEqual(result["health"], "healthy")
            self.assertFalse(result["disabled"])
            self.assertNotIn("SECRET", json.dumps(result))

    def test_unverified_import_console_contract(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the import DOM contract")
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [node, str(root / "backend/tests/provider_import_contract.cjs")],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_codex_tokens_keep_account_and_absolute_expiry(self):
        payload = normalize_provider_import(codex_fixture(), "codex")
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["credential_type"], "oauth")
        self.assertEqual(payload["account_id"], "fixture-account")
        self.assertEqual(payload["user_email"], "fixture@example.invalid")
        self.assertEqual(payload["expiry"], "2027-01-15T08:00:00+00:00")
        self.assertNotIn("tokens", payload)

    def test_native_claude_block_normalizes_millisecond_expiry(self):
        payload = normalize_provider_import(
            {
                "claudeAiOauth": {
                    "accessToken": "fixture-access",
                    "refreshToken": "fixture-refresh",
                    "expiresAt": 1800000000000,
                    "scopes": ["user:inference"],
                }
            },
            "claude_code",
        )
        self.assertEqual(payload["provider"], "anthropic")
        self.assertEqual(payload["access_token"], "fixture-access")
        self.assertEqual(payload["expiry"], "2027-01-15T08:00:00+00:00")
        self.assertEqual(payload["scopes"], ["user:inference"])

    def test_grok_auth_json_and_cli_proxy_exports_normalize(self):
        native = {
            "https://auth.x.ai::fixture-client": {
                "key": "fixture-access",
                "refresh_token": "fixture-refresh",
                "expiresAt": "2026-10-01T02:00:00+02:00",
            }
        }
        exported = {
            "type": "xai",
            "auth_kind": "oauth",
            "access_token": "fixture-access",
            "refresh_token": "fixture-refresh",
            "expired": "2026-10-01T00:00:00Z",
            "email": "fixture@example.invalid",
            "base_url": "https://api.x.ai/v1",
        }
        for source in [native, exported]:
            with self.subTest(source=list(source)):
                payload = normalize_provider_import(source)
                self.assertEqual(payload["provider"], "xai")
                self.assertEqual(payload["expiry"], "2026-10-01T00:00:00+00:00")
                self.assertEqual(payload["refresh_token"], "fixture-refresh")

    def test_rejects_conflicting_provider_markers_without_echoing_values(self):
        examples = [
            ({**codex_fixture(), "provider": "anthropic"}, "codex"),
            ({**codex_fixture(), "claudeAiOauth": {"accessToken": "SECRET"}}, None),
            ({"provider": "SECRET-provider", "tokens": {"access_token": "SECRET"}}, None),
            ({"provider": "xai", "credential_type": "api_key", "api_key": "SECRET"}, "codex"),
            ({"provider": "openai", "provider_id": "anthropic", "access_token": "SECRET"}, "codex"),
            ({**codex_fixture(), "OPENAI_API_KEY": "SECRET-key"}, "codex"),
            ({"provider": "SECRET-provider", "access_token": "SECRET"}, None),
            ({"provider": "grok", "credential_type": "api_key", "api_key": "SECRET"}, None),
            (
                {"provider": "xai_console", "credential_type": "oauth", "access_token": "SECRET"},
                None,
            ),
            ({"tokens": {"provider": "anthropic", "access_token": "SECRET"}}, "codex"),
            ({"tokens": {"access_token": "SECRET", "credential_type": "api_key"}}, "codex"),
        ]
        for source, variant in examples:
            with self.subTest(variant=variant):
                with self.assertRaises(ValueError) as error:
                    normalize_provider_import(source, variant)
                self.assertNotIn("SECRET", str(error.exception))

    def test_rejects_multiple_grok_accounts_and_invalid_token_shapes(self):
        cases = [
            {"https://auth.x.ai::one": {"key": "one"}, "https://auth.x.ai::two": {"key": "two"}},
            {"tokens": {"access_token": {"secret": "SECRET"}}},
            {"tokens": {"access_token": "x" * 32769}},
            {"tokens": {"access_token": "SECRET\r\nheader"}},
            {"claudeAiOauth": {"accessToken": "SECRET", "expiresAt": "SECRET-expiry"}},
            {"tokens": {}},
        ]
        for source in cases:
            with self.subTest(source=list(source)):
                with self.assertRaises(ValueError) as error:
                    normalize_provider_import(source)
                self.assertNotIn("SECRET", str(error.exception))

    def test_flat_aliases_remain_supported_and_input_is_not_mutated(self):
        source = {
            "accessToken": "fixture-access",
            "refreshToken": "fixture-refresh",
            "accountId": "fixture-account",
            "expired": "2026-10-01T00:00:00Z",
        }
        original = dict(source)
        result = normalize_provider_import(source, "codex")
        self.assertEqual(result["account_id"], "fixture-account")
        self.assertEqual(source, original)

    def test_boundaries_and_conflicting_aliases_are_rejected(self):
        for source in [
            [],
            {str(index): index for index in range(65)},
            {"tokens": []},
            {"tokens": {"access_token": "a"}, "access_token": "b"},
            {"tokens": {"access_token": "a", "accessToken": "b"}},
            {"tokens": {"access_token": "a", "expiry": "2026-10-01", "expired": "2026-11-01"}},
            {"tokens": {"access_token": "a", "expiresAt": True}},
            {"tokens": {"access_token": "a", "scopes": "scope"}},
            {"tokens": {"access_token": "a", "model_ids": ["m"] * 501}},
            {"type": "xai", "auth_kind": "api_key", "access_token": "a"},
        ]:
            with self.subTest(source=str(source)[:80]), self.assertRaises(ValueError):
                normalize_provider_import(source)

    def test_expiry_aliases_and_invalid_jwt_hints_are_safe(self):
        for expiry in [1800000000, 1800000000000, "2027-01-15T08:00:00Z", "2027-01-15T08:00:00"]:
            result = normalize_provider_import(
                {"access_token": "fixture", "expiry": expiry}, "grok"
            )
            self.assertEqual(result["expiry"], "2027-01-15T08:00:00+00:00")
        for token in ["fixture", "fixture.invalid.unsigned", fixture_jwt([])]:
            result = normalize_provider_import({"access_token": token}, "codex")
            self.assertNotIn("user_email", result)

    def test_api_variants_accept_only_their_canonical_provider(self):
        for variant in ("openai_platform", "claude_platform", "xai_console"):
            source = {"api_key": "fixture", "provider": variant, "credential_type": "api_key"}
            self.assertEqual(normalize_provider_import(source, variant), source)
            with self.assertRaises(ValueError):
                normalize_provider_import(
                    {"access_token": "fixture", "credential_type": "oauth"}, variant
                )
        for source, variant in [
            ({"provider": "codex", "api_key": "fixture"}, "openai_platform"),
            ({"provider": "openai_platform", "access_token": "fixture"}, "codex"),
        ]:
            with self.assertRaises(ValueError):
                normalize_provider_import(source, variant)

    def test_canonical_refresh_endpoint_and_cli_proxy_alias_are_preserved(self):
        for key in ("token_uri", "token_endpoint"):
            result = normalize_provider_import(
                {"access_token": "fixture", key: "https://auth.x.ai/oauth2/token"}, "grok"
            )
            self.assertEqual(result["token_uri"], "https://auth.x.ai/oauth2/token")

    def test_conflicting_account_identity_hints_are_rejected(self):
        source = codex_fixture()
        source["tokens"]["account_id"] = "different-account"
        with self.assertRaises(ValueError):
            normalize_provider_import(source, "codex")

    def test_native_oauth_cannot_hide_api_key_in_nested_container(self):
        with self.assertRaises(ValueError):
            normalize_provider_import(
                {"tokens": {"access_token": "fixture", "api_key": "fixture-key"}}
            )

    def test_other_canonical_provider_payloads_are_preserved(self):
        for source in [
            {"provider": "ollama", "base_url": "http://localhost:11434"},
            {"client_id": "fixture", "client_secret": "fixture", "refresh_token": "fixture"},
        ]:
            self.assertEqual(normalize_provider_import(source), source)

    def test_provider_parsers_accept_native_and_reject_other_products(self):
        parsed = _parse_openai_json(json.dumps(codex_fixture()).encode(), "fixture.json", "oauth")
        self.assertEqual(parsed[0]["payload"]["account_id"], "fixture-account")
        exported = {"type": "xai", "auth_kind": "oauth", "access_token": "fixture-access"}
        self.assertEqual(
            _parse_xai_import_document(json.dumps(exported).encode(), "fixture.json")["provider"],
            "xai",
        )
        with self.assertRaises(ValueError):
            _parse_openai_json(json.dumps(exported).encode(), "fixture.json", "oauth")

    def test_claude_parser_uses_native_normalization_and_rejects_other_products(self):
        source = {"claudeAiOauth": {"accessToken": "fixture-access", "expiresAt": 1800000000000}}
        parsed = _parse_anthropic_json(json.dumps(source).encode(), "fixture.json", "oauth")
        self.assertEqual(parsed[0]["payload"]["access_token"], "fixture-access")
        self.assertEqual(parsed[0]["payload"]["expiry"], "2027-01-15T08:00:00+00:00")
        for credential_type in ("oauth", "api_key"):
            with self.assertRaises(ValueError):
                _parse_anthropic_json(
                    json.dumps(codex_fixture()).encode(), "fixture.json", credential_type
                )


class ProviderImportIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_foreign_oauth_without_email_never_calls_google_userinfo(self):
        lookup = AsyncMock(return_value="fixture@example.invalid")
        with patch("core.google_oauth_api.get_user_email", lookup):
            for provider in ("openai", "anthropic", "xai", "unknown"):
                self.assertEqual(
                    await resolve_credential_email(
                        {"provider": provider, "access_token": "fixture-access"}
                    ),
                    "",
                )
            lookup.assert_not_awaited()
            for provider in (None, "google_antigravity"):
                payload = {"access_token": "fixture-access"}
                if provider:
                    payload["provider"] = provider
                self.assertEqual(await resolve_credential_email(payload), "fixture@example.invalid")
            self.assertEqual(lookup.await_count, 2)

    async def test_mixed_pool_archive_detects_native_oauth_formats(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            for name, payload in [
                ("codex.json", codex_fixture()),
                ("claude.json", {"claudeAiOauth": {"accessToken": "fixture-access"}}),
                (
                    "grok.json",
                    {"type": "xai", "auth_kind": "oauth", "access_token": "fixture-access"},
                ),
            ]:
                output.writestr(name, json.dumps(payload))
        candidates, errors = await extract_pool_archive(
            UploadFile(filename="fixture.zip", file=io.BytesIO(archive.getvalue()))
        )
        self.assertEqual(errors, [])
        self.assertEqual([item["provider"] for item in candidates], ["openai", "anthropic", "xai"])

    async def test_offline_oauth_imports_are_truthfully_unverified(self):
        stored = AsyncMock(
            return_value={"action": "created", "stored": True, "filename": "fixture.json"}
        )
        with patch("core.pool_import.credential_manager.add_primary_credential", stored):
            for provider, restore in [
                ("openai", restore_openai_credential),
                ("xai", restore_xai_credential),
            ]:
                result = await restore(
                    {
                        "payload": {
                            "provider": provider,
                            "credential_type": "oauth",
                            "refresh_token": "SECRET",
                        }
                    }
                )
                self.assertEqual(result["validation_status"], "unverified")
                self.assertIn("not verified", result["message"])
                self.assertNotIn("SECRET", json.dumps(result))
                self.assertEqual(stored.await_args.args[1]["validation_status"], "unverified")
