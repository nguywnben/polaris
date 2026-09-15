"""Kiro OAuth contracts with synthetic credentials only."""

import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.kiro import normalize_credential, prepare_request
from core.provider_import_normalization import normalize_provider_import
from core.provider_registry import get_static_credential_identity


class KiroOAuthCredentialTests(unittest.TestCase):
    def credential(self, **values):
        return {
            "provider": "kiro",
            "credential_type": "oauth",
            "access_token": "synthetic-access",
            "refresh_token": "synthetic-refresh",
            "auth_method": "social",
            "region": "us-east-1",
            **values,
        }

    def test_oauth_request_uses_access_token_without_api_key_marker(self):
        _, headers, _ = prepare_request(
            self.credential(),
            {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
            "model",
            False,
        )
        self.assertEqual(headers["Authorization"], "Bearer synthetic-access")
        self.assertNotIn("tokentype", headers)

    def test_cockpit_import_accepts_token_aliases_without_trusting_catalog(self):
        value = normalize_provider_import(
            {
                "accessToken": "synthetic-access",
                "refreshToken": "synthetic-refresh",
                "authMethod": "social",
                "model_ids": ["untrusted-model"],
            },
            variant="kiro",
        )
        self.assertEqual(value["credential_type"], "oauth")
        self.assertEqual(value["access_token"], "synthetic-access")
        self.assertNotIn("model_ids", value)

    def test_identity_does_not_depend_on_rotating_access_token(self):
        before = get_static_credential_identity(normalize_credential(self.credential()))
        after = get_static_credential_identity(
            normalize_credential(self.credential(access_token="new-access"))
        )
        self.assertTrue(before.startswith("kiro:"))
        self.assertEqual(before, after)

    def test_cockpit_timestamp_and_nested_idc_credentials(self):
        value = normalize_provider_import(
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_at": 1800000000,
                "idc_region": "eu-west-1",
                "kiro_auth_token_raw": {
                    "accessToken": "access",
                    "refreshToken": "refresh",
                    "authMethod": "IdC",
                    "clientId": "id",
                    "clientSecret": "secret",
                    "region": "us-east-1",
                },
            },
            variant="kiro",
        )
        self.assertEqual(value["auth_method"], "idc")
        self.assertEqual(value["client_secret"], "secret")
        self.assertEqual(value["token_region"], "eu-west-1")
        self.assertTrue(value["expiry"].startswith("2027-"))
        with self.assertRaises(ValueError):
            normalize_provider_import(
                {"access_token": "one", "kiro_auth_token_raw": {"accessToken": "two"}},
                variant="kiro",
            )

    def test_ambiguous_or_incomplete_authentication_is_rejected(self):
        for values in (
            {"api_key": "synthetic-key"},
            {"accessToken": "conflicting-token"},
            {"auth_method": "idc"},
            {"auth_method": "unknown"},
            {"region": "us-east-1.attacker.example"},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                normalize_credential(self.credential(**values))

    def test_cockpit_container_is_detected_in_mixed_pool_and_conflicts_rejected(self):
        data = {
            "kiro_auth_token_raw": {"refreshToken": "synthetic-refresh", "authMethod": "social"}
        }
        self.assertEqual(normalize_provider_import(data)["provider"], "kiro")
        with self.assertRaises(ValueError):
            normalize_provider_import({**data, "tokens": {"access_token": "other"}})

    def test_refresh_only_cannot_send_an_empty_bearer_token(self):
        from core.kiro import _headers

        with self.assertRaises(ValueError):
            _headers(normalize_credential(self.credential(access_token="")))

    def test_vendor_conflicting_token_aliases_are_rejected(self):
        from core.kiro_oauth import token_credential

        with self.assertRaises(ValueError):
            token_credential(self.credential(), {"accessToken": "one", "access_token": "two"})


class KiroOAuthRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_access_only_import_without_expiry_does_not_attempt_impossible_refresh(self):
        from core.credential_manager import credential_manager

        self.assertFalse(
            await credential_manager._should_refresh_token(
                KiroOAuthCredentialTests().credential(refresh_token="")
            )
        )

    async def test_refresh_preserves_account_identity_and_connection_metadata(self):
        from core.kiro_oauth import refresh_credential

        original = normalize_credential(KiroOAuthCredentialTests().credential())
        original.update(model_ids=["known-model"], credential_label="Personal Kiro")
        with patch(
            "core.kiro_oauth.auth_request",
            new=AsyncMock(
                return_value=(
                    200,
                    {
                        "accessToken": "refreshed-access",
                        "refreshToken": "rotated-refresh",
                        "expiresIn": 3600,
                    },
                )
            ),
        ) as request:
            result = await refresh_credential(original)
        self.assertEqual(result["access_token"], "refreshed-access")
        self.assertEqual(result["refresh_token"], "rotated-refresh")
        self.assertEqual(result["account_fingerprint"], original["account_fingerprint"])
        self.assertEqual(result["model_ids"], ["known-model"])
        self.assertIn("/refreshToken", request.call_args.args[0])

    async def test_idc_refresh_uses_token_region_not_runtime_region(self):
        from core.kiro_oauth import refresh_credential

        data = KiroOAuthCredentialTests().credential(
            auth_method="idc",
            client_id="test-client",
            client_secret="test-client-secret",
            token_region="ap-southeast-1",
        )
        with patch(
            "core.kiro_oauth.auth_request",
            new=AsyncMock(
                return_value=(
                    200,
                    {
                        "accessToken": "refreshed-access",
                        "expiresIn": 3600,
                    },
                )
            ),
        ) as request:
            result = await refresh_credential(data)
        self.assertEqual(
            request.call_args.args[0], "https://oidc.ap-southeast-1.amazonaws.com/token"
        )
        self.assertEqual(result["region"], "us-east-1")
        self.assertEqual(result["refresh_token"], "synthetic-refresh")

    async def test_rejected_refresh_does_not_echo_upstream_body(self):
        from core.kiro_oauth import refresh_credential

        with patch(
            "core.kiro_oauth.auth_request",
            new=AsyncMock(
                return_value=(
                    400,
                    {
                        "error": "invalid_grant",
                        "error_description": "SECRET-MUST-NOT-LEAK",
                    },
                )
            ),
        ):
            with self.assertRaises(ValueError) as caught:
                await refresh_credential(KiroOAuthCredentialTests().credential())
        self.assertNotIn("SECRET-MUST-NOT-LEAK", str(caught.exception))

    async def test_auth_transport_bounds_response_and_does_not_follow_redirects(self):
        from core.kiro_oauth import auth_request

        @asynccontextmanager
        async def client(**kwargs):
            self.assertFalse(kwargs["follow_redirects"])
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, content=b"x" * 65537)
                )
            ) as instance:
                yield instance

        with patch("core.kiro_oauth.http_client.get_client", client):
            with self.assertRaises(ValueError):
                await auth_request("https://prod.us-east-1.auth.desktop.kiro.dev/refreshToken", {})
