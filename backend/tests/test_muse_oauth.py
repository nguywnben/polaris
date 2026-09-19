"""Muse Code authorization boundary; synthetic secrets, no live network."""

import json
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import muse_oauth as muse


def device_payload(**updates):
    return {
        "device_code": "fixture-device-secret",
        "user_code": "ABCD-EFGH",
        "verification_uri": "https://auth.meta.com/oauth/device/",
        "verification_uri_complete": "https://auth.meta.com/oauth/device/?code=ABCD-EFGH",
        "expires_in": 600,
        "interval": 5,
        **updates,
    }


def key_payload(**updates):
    return {
        "api_key": "fixture-inference-secret",
        "base_url": "https://api.meta.ai/v1",
        "is_subs_active": True,
        "require_payment": False,
        "user_email": "fixture@example.test",
        "user_full_name": "Do not retain this name",
        "subs_usage": {
            "tier": "fixture-tier",
            "window": {"used_percent": 7, "window_duration_mins": 300, "resets_at": 1800000000},
            "weekly": {"used_percent": 3, "resets_at": 1800600000},
        },
        **updates,
    }


class MuseOAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_named_subscription_survives_missing_usage(self):
        payload = key_payload(subs_tier_name="Muse Code Power Usage")
        del payload["subs_usage"]
        async with self.upstream(httpx.Response(200, json=payload)):
            result = await muse.mint_key("fixture-oauth-secret")
        self.assertEqual(result["subscription_plan"], "Muse Code Power Usage")
        self.assertIsNone(result["subscription_usage"])

    async def test_invalid_subscription_name_does_not_hide_valid_quota(self):
        for value in (None, "", "unknown", True, {"name": "Power"}, "x" * 129, "bad\nname"):
            with self.subTest(value=value):
                async with self.upstream(
                    httpx.Response(200, json=key_payload(subs_tier_name=value))
                ):
                    result = await muse.mint_key("fixture-oauth-secret")
                self.assertIsNone(result["subscription_plan"])
                self.assertEqual(result["subscription_usage"]["window"]["used_percent"], 7)

    @asynccontextmanager
    async def upstream(self, response):
        requests = []

        def handler(request):
            requests.append(request)
            return response

        @asynccontextmanager
        async def client(**options):
            self.assertFalse(options["follow_redirects"])
            self.assertIn(options["destination_url"], muse.AUTH_ENDPOINTS)
            self.assertLessEqual(options["timeout"], 20)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
                yield session

        with patch.object(muse.http_client, "get_client", client):
            yield requests

    async def test_start_has_fixed_client_and_validated_device_url(self):
        async with self.upstream(httpx.Response(200, json=device_payload())) as requests:
            result = await muse.start_device_authorization()
        self.assertEqual(result, device_payload())
        self.assertEqual(str(requests[0].url), muse.DEVICE_ENDPOINT)
        self.assertEqual(parse_qs(requests[0].content.decode()), {"client_id": [muse.CLIENT_ID]})
        self.assertNotIn("authorization", requests[0].headers)

    async def test_device_urls_and_grant_fields_fail_closed(self):
        for changes in (
            {"verification_uri": "https://evil.test/oauth/device/"},
            {"verification_uri_complete": "https://auth.meta.com.evil.test/?code=ABCD-EFGH"},
            {"verification_uri_complete": "https://auth.meta.com/oauth/device/?code=OTHER"},
            {
                "verification_uri_complete": "https://auth.meta.com/oauth/device/?code=ABCD-EFGH&secret=x"
            },
            {"verification_uri": "https://user@auth.meta.com/oauth/device/"},
            {"verification_uri": "https://auth.meta.com:443/oauth/device/"},
            {"verification_uri": "http://auth.meta.com/oauth/device/"},
            {"expires_in": True},
            {"expires_in": 0},
            {"expires_in": 86401},
            {"interval": 0},
            {"interval": 601},
            {"device_code": "bad\r\nsecret"},
            {"user_code": "<script>"},
        ):
            with self.subTest(changes=changes):
                async with self.upstream(httpx.Response(200, json=device_payload(**changes))):
                    with self.assertRaises(muse.MuseOAuthError):
                        await muse.start_device_authorization()

    async def test_token_exchange_does_not_invent_expiry_or_refresh(self):
        async with self.upstream(
            httpx.Response(
                200,
                json={
                    "access_token": "fixture-oauth-secret",
                    "token_type": "Bearer",
                },
            )
        ) as requests:
            result = await muse.exchange_device_token("fixture-device-secret")
        self.assertEqual(result, {"access_token": "fixture-oauth-secret"})
        form = parse_qs(requests[0].content.decode())
        self.assertEqual(form["grant_type"], ["urn:ietf:params:oauth:grant-type:device_code"])
        self.assertEqual(form["device_code"], ["fixture-device-secret"])
        self.assertEqual(form["client_id"], [muse.CLIENT_ID])

    async def test_pending_and_slow_down_have_safe_machine_codes(self):
        for code in ("authorization_pending", "slow_down", "expired_token", "access_denied"):
            async with self.upstream(
                httpx.Response(
                    400,
                    json={
                        "error": code,
                        "error_description": "fixture-secret-must-not-leak",
                    },
                )
            ):
                with self.assertRaises(muse.MuseOAuthError) as raised:
                    await muse.exchange_device_token("fixture-device-secret")
            self.assertEqual(raised.exception.code, code)
            self.assertNotIn("fixture-secret", str(raised.exception))

    async def test_invalid_token_fields_rejected(self):
        for payload in (
            {},
            {"access_token": "bad\nvalue", "token_type": "Bearer"},
            {"access_token": "fixture", "token_type": "MAC"},
            {"access_token": "fixture", "token_type": "Bearer", "expires_in": -1},
        ):
            async with self.upstream(httpx.Response(200, json=payload)):
                with self.assertRaises(muse.MuseOAuthError):
                    await muse.exchange_device_token("fixture-device-secret")

    async def test_mint_separates_account_token_from_inference_key(self):
        async with self.upstream(httpx.Response(200, json=key_payload())) as requests:
            result = await muse.mint_key("fixture-oauth-secret")
        self.assertEqual(str(requests[0].url), muse.KEY_ENDPOINT)
        self.assertEqual(requests[0].headers["authorization"], "Bearer fixture-oauth-secret")
        self.assertEqual(json.loads(requests[0].content), {})
        self.assertEqual(result["api_key"], "fixture-inference-secret")
        self.assertEqual(result["provider"], "muse_code")
        self.assertEqual(result["credential_type"], "oauth")
        self.assertEqual(result["access_token"], "fixture-oauth-secret")
        self.assertEqual(len(result["account_id"]), 64)
        self.assertEqual(result["user_email"], "fixture@example.test")
        self.assertNotIn("user_full_name", result)
        self.assertEqual(result["subscription_usage"]["window"]["used_percent"], 7)

    async def test_mint_rejects_payment_or_unknown_subscription_instead_of_api_fallback(self):
        for changes in (
            {"is_subs_active": False},
            {"is_subs_active": None},
            {"require_payment": True},
            {"require_payment": None},
        ):
            async with self.upstream(httpx.Response(200, json=key_payload(**changes))):
                with self.assertRaises(muse.MuseOAuthError) as raised:
                    await muse.mint_key("fixture-oauth-secret")
            self.assertEqual(raised.exception.code, "subscription_required")

    async def test_mint_cannot_redirect_key_to_another_base(self):
        for base in ("https://evil.test/v1", "https://api.meta.ai/v1?secret=x", None):
            async with self.upstream(httpx.Response(200, json=key_payload(base_url=base))):
                with self.assertRaises(muse.MuseOAuthError):
                    await muse.mint_key("fixture-oauth-secret")

    async def test_quota_is_optional_and_malformed_quota_is_not_zero(self):
        for value in (None, {}, {"window": {"used_percent": -1}}, {"weekly": True}):
            async with self.upstream(httpx.Response(200, json=key_payload(subs_usage=value))):
                result = await muse.mint_key("fixture-oauth-secret")
            self.assertIsNone(result["subscription_usage"])

    async def test_revoked_session_requires_reauthorization(self):
        async with self.upstream(httpx.Response(401, json={"detail": "fixture-secret"})):
            with self.assertRaises(muse.MuseOAuthError) as raised:
                await muse.mint_key("fixture-oauth-secret")
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.code, "reauthorization_required")
        self.assertNotIn("fixture-secret", str(raised.exception))

    async def test_redirect_malformed_and_oversized_responses_rejected(self):
        for response in (
            httpx.Response(302, headers={"Location": "https://evil.test"}),
            httpx.Response(200, content=b"not-json"),
            httpx.Response(200, json=[]),
            httpx.Response(200, content=b" " * 65537),
        ):
            async with self.upstream(response) as requests:
                with self.assertRaises(muse.MuseOAuthError):
                    await muse.mint_key("fixture-oauth-secret")
            self.assertEqual(len(requests), 1)

    async def test_untrusted_endpoints_and_invalid_input_never_reach_network(self):
        with patch.object(muse.http_client, "get_client") as client:
            for endpoint, token in (
                ("https://evil.test", "secret"),
                (muse.DEVICE_ENDPOINT, "secret"),
                (muse.KEY_ENDPOINT, None),
            ):
                with self.assertRaises(muse.MuseOAuthError):
                    await muse._request(endpoint, {}, access_token=token)
            for token in (None, "", "x" * 8193, "abc def", "secret\x00"):
                with self.assertRaises(muse.MuseOAuthError):
                    await muse.mint_key(token)
            client.assert_not_called()

    async def test_transient_network_error_is_sanitized(self):
        @asynccontextmanager
        async def fail(**options):
            raise httpx.ConnectError("fixture-secret-in-proxy-error")
            yield

        with patch.object(muse.http_client, "get_client", fail):
            with self.assertRaises(muse.MuseOAuthError) as raised:
                await muse.mint_key("fixture-oauth-secret")
        self.assertNotIn("fixture-secret", str(raised.exception))
        self.assertEqual(raised.exception.status_code, 502)

    async def test_advertised_oauth_expiry_is_separate_from_key_expiry(self):
        async with self.upstream(
            httpx.Response(
                200,
                json={
                    "access_token": "fixture",
                    "token_type": "Bearer",
                    "expires_in": 600,
                },
            )
        ):
            with patch.object(muse.time, "time", return_value=1800000000):
                result = await muse.exchange_device_token("fixture-device")
        self.assertEqual(result["oauth_expires_at"], 1800000600)
        self.assertNotIn("expiry", result)

    async def test_mint_requires_server_verified_account_and_valid_key(self):
        for updates in (
            {"user_email": ""},
            {"user_email": "a\n@b"},
            {"api_key": ""},
            {"api_key": "invalid\nkey"},
        ):
            async with self.upstream(httpx.Response(200, json=key_payload(**updates))):
                with self.assertRaises(muse.MuseOAuthError):
                    await muse.mint_key("fixture-oauth-secret")

    async def test_vendor_failure_statuses_do_not_expose_body(self):
        for operation in (
            muse.start_device_authorization,
            lambda: muse.exchange_device_token("fixture-device"),
            lambda: muse.mint_key("fixture-token"),
        ):
            async with self.upstream(httpx.Response(503, json={"error": "fixture-secret"})):
                with self.assertRaises(muse.MuseOAuthError) as raised:
                    await operation()
            self.assertNotIn("fixture-secret", str(raised.exception))

    def test_invalid_and_over_limit_quota_is_not_a_fake_zero_observation(self):
        for field, value in (
            ("used_percent", True),
            ("resets_at", 1800000000000),
            ("window_duration_mins", 0),
        ):
            usage = key_payload()["subs_usage"]
            usage["window"][field] = value
            self.assertIsNone(muse.subscription_usage(usage))
        usage = key_payload()["subs_usage"]
        usage["window"]["used_percent"] = 110
        self.assertEqual(muse.subscription_usage(usage)["window"]["used_percent"], 110)


if __name__ == "__main__":
    unittest.main()
