"""Kiro quota contract from cockpit-tools runtime getUsageLimits snapshots."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.kiro import KiroError
from core.kiro_usage import fetch_kiro_usage, parse_kiro_usage


class KiroUsageTests(unittest.IsolatedAsyncioTestCase):
    def test_legacy_allocation_is_used_when_precision_fields_are_null(self):
        result = parse_kiro_usage(
            {
                "usageBreakdownList": [
                    {
                        "resourceType": "CREDITS",
                        "currentUsageWithPrecision": None,
                        "usageLimitWithPrecision": None,
                        "currentUsage": 5,
                        "usageLimit": 100,
                    }
                ]
            }
        )
        self.assertEqual(result["summary_remaining_percentage"], 95)
        self.assertEqual(result["windows"][0]["remaining_percentage"], 95)

    async def test_usage_fetch_is_bounded_and_sanitizes_malformed_payloads(self):
        for response in (
            httpx.Response(302),
            httpx.Response(503, text="private-body"),
            httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1)),
            httpx.Response(200, content=b"not-json"),
        ):
            client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response))
            with patch("core.kiro_usage.http_client.get_client", return_value=client) as factory:
                with self.assertRaises(KiroError) as caught:
                    await fetch_kiro_usage({"provider": "kiro", "api_key": "synthetic-key"})
            self.assertEqual(caught.exception.status_code, 502)
            self.assertNotIn("private-body", str(caught.exception))
            self.assertFalse(factory.call_args.kwargs["follow_redirects"])

    def test_summary_combines_active_credit_balances_not_minimum_trial_percentage(self):
        result = parse_kiro_usage(
            {
                "usageBreakdownList": [
                    {
                        "resourceType": "CREDITS",
                        "usageLimit": 100,
                        "currentUsage": 20,
                        "freeTrialInfo": {
                            "usageLimit": 50,
                            "currentUsage": 50,
                            "freeTrialStatus": "EXPIRED",
                        },
                        "bonuses": [{"usageLimit": 100, "currentUsage": 0, "status": "ACTIVE"}],
                    }
                ]
            }
        )
        self.assertEqual(result["summary_remaining_percentage"], 90)
        self.assertEqual(len(result["windows"]), 3)
        unknown = parse_kiro_usage(
            {
                "usageBreakdownList": [
                    {
                        "resourceType": "CREDITS",
                        "usageLimit": 100,
                        "currentUsage": 20,
                        "freeTrialInfo": {"usageLimit": 50},
                    }
                ]
            }
        )
        self.assertIsNone(unknown["summary_remaining_percentage"])

    def test_resource_trial_and_bonus_remain_separate(self):
        result = parse_kiro_usage(
            {
                "subscriptionInfo": {"subscriptionTitle": "Kiro Pro"},
                "overageConfiguration": {"overageStatus": "ENABLED"},
                "nextDateReset": 2000000000,
                "usageBreakdownList": [
                    {
                        "resourceType": "AGENTIC_REQUEST",
                        "displayName": "Credits",
                        "usageLimitWithPrecision": 100,
                        "currentUsageWithPrecision": 120,
                        "freeTrialInfo": {
                            "usageLimit": 10,
                            "currentUsage": 2,
                            "freeTrialStatus": "ACTIVE",
                        },
                        "bonuses": [{"bonusCode": "WELCOME", "usageLimit": 5, "currentUsage": 1}],
                    }
                ],
                "accessToken": "never-return-this",
            }
        )
        self.assertEqual(result["plan"], "Kiro Pro")
        self.assertTrue(result["overage_enabled"])
        self.assertEqual([w["remaining_percentage"] for w in result["windows"]], [0, 80, 80])
        self.assertEqual(result["windows"][0]["used"], 120)
        self.assertEqual(result["windows"][1]["status"], "ACTIVE")
        self.assertNotIn("never-return-this", str(result))

    def test_missing_or_invalid_numbers_are_unknown_not_full(self):
        for value in (None, True, "", "NaN", -1):
            result = parse_kiro_usage(
                {
                    "usageBreakdownList": [
                        {"resourceType": "AGENTIC_REQUEST", "usageLimit": 50, "currentUsage": value}
                    ]
                }
            )
            self.assertIsNone(result["windows"][0]["remaining_percentage"])
        self.assertEqual(parse_kiro_usage({})["quota_status"], "unavailable")
        with self.assertRaises(KiroError):
            parse_kiro_usage([])

    async def test_fetch_uses_fixed_regional_host_and_safe_auth_errors(self):
        requests = []

        async def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"usageBreakdownList": []})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("core.kiro_usage.http_client.get_client", return_value=client):
            result = await fetch_kiro_usage(
                {"provider": "kiro", "api_key": "synthetic-key", "region": "eu-central-1"}
            )
        self.assertEqual(result["quota_status"], "unavailable")
        self.assertEqual(requests[0].url.host, "q.eu-central-1.amazonaws.com")
        self.assertEqual(requests[0].url.path, "/getUsageLimits")
        self.assertEqual(requests[0].headers["tokentype"], "API_KEY")
        self.assertNotIn("isEmailRequired", requests[0].url.params)

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(401, text="private-body"))
        )
        with patch("core.kiro_usage.http_client.get_client", return_value=client):
            with self.assertRaises(KiroError) as caught:
                await fetch_kiro_usage({"provider": "kiro", "api_key": "synthetic-key"})
        self.assertEqual(caught.exception.status_code, 401)
        self.assertNotIn("private-body", str(caught.exception))
