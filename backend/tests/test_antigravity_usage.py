"""Provider values stay partial and UTC; no inferred zero quota or raw payloads."""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.antigravity_usage import (
    _optional_rpc,
    fetch_account_metadata,
    parse_account_metadata,
    parse_group_quotas,
    parse_model_quotas,
)


class AntigravityUsageTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_quota_api_merges_only_normalized_account_metadata(self):
        from core.api import primary

        with (
            patch.object(
                primary,
                "build_primary_headers",
                AsyncMock(return_value={"Authorization": "Bearer synthetic"}),
            ),
            patch.object(
                primary,
                "get_antigravity_api_url",
                AsyncMock(return_value="https://example.invalid"),
            ),
            patch.object(
                primary,
                "post_async",
                AsyncMock(
                    return_value=httpx.Response(
                        200, json={"models": {"model": {"quotaInfo": {"remainingFraction": 0.8}}}}
                    )
                ),
            ),
            patch(
                "core.antigravity_usage.fetch_account_metadata",
                AsyncMock(
                    return_value={
                        "plan": "pro",
                        "windows": [{"label": "Weekly", "remaining_percentage": 40}],
                    }
                ),
            ) as metadata,
        ):
            result = await primary.fetch_quota_info("synthetic", "project-fixture")
        self.assertTrue(result["success"])
        self.assertEqual(result["models"]["model"]["remaining"], 0.8)
        self.assertEqual(result["plan"], "pro")
        self.assertEqual(result["windows"][0]["remaining_percentage"], 40)
        self.assertEqual(metadata.await_args.args[2], "project-fixture")
        self.assertNotIn("synthetic", str(result))

    async def test_optional_account_failure_keeps_independent_group_quotas(self):
        rpc = AsyncMock(
            side_effect=[
                None,
                {
                    "groups": [
                        {
                            "displayName": "Model group",
                            "buckets": [{"bucketId": "week", "remainingFraction": 0.4}],
                        }
                    ]
                },
            ]
        )
        with patch("core.antigravity_usage._optional_rpc", rpc):
            result = await fetch_account_metadata("https://example.invalid", {}, "test-project")
        self.assertEqual(result["account_metadata_status"], "unavailable")
        self.assertEqual(result["windows"][0]["remaining_percentage"], 40)
        self.assertEqual(
            [call.args[2] for call in rpc.await_args_list],
            ["loadCodeAssist", "retrieveUserQuotaSummary"],
        )
        self.assertEqual(rpc.await_args_list[1].args[3], {"project": "test-project"})
        with patch("core.antigravity_usage._optional_rpc", AsyncMock(return_value={})) as single:
            self.assertEqual(await fetch_account_metadata("https://example.invalid", {}), {})
        single.assert_awaited_once()

    async def test_optional_rpc_is_bounded_and_does_not_follow_redirects(self):
        for response in (
            httpx.Response(302, headers={"location": "https://other.invalid"}),
            httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1)),
            httpx.Response(200, content=b"not-json"),
        ):
            client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response))
            with patch(
                "core.antigravity_usage.http_client.get_client", return_value=client
            ) as factory:
                result = await _optional_rpc("https://example.invalid", {}, "loadCodeAssist", {})
            self.assertIsNone(result)
            self.assertFalse(factory.call_args.kwargs["follow_redirects"])
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"paidTier": {"id": "pro"}})
            )
        )
        with patch("core.antigravity_usage.http_client.get_client", return_value=client):
            self.assertEqual(
                (await _optional_rpc("https://example.invalid", {}, "loadCodeAssist", {}))[
                    "paidTier"
                ]["id"],
                "pro",
            )

    def test_group_windows_do_not_overwrite_model_quota_or_infer_duration(self):
        windows = parse_group_quotas(
            {
                "quotaSummary": {
                    "groups": [
                        {
                            "displayName": "Gemini Models",
                            "buckets": [
                                {
                                    "bucketId": "weekly",
                                    "displayName": "Weekly",
                                    "remainingFraction": 0.25,
                                    "resetTime": "2030-01-01T00:00:00Z",
                                },
                                {"bucketId": "disabled", "remainingFraction": 1, "disabled": True},
                                {"bucketId": "unknown", "displayName": "Other"},
                            ],
                        }
                    ]
                }
            }
        )
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0]["remaining_percentage"], 25)
        self.assertEqual(windows[0]["label"], "Gemini Models · Weekly")
        self.assertIsNone(windows[1]["remaining_percentage"])

    def test_missing_fraction_is_unknown_and_reset_remains_utc(self):
        models = parse_model_quotas(
            {
                "models": {
                    "partial": {"quotaInfo": {"resetTime": "2030-01-01T00:00:00Z"}},
                    "empty": {"quotaInfo": {"remainingFraction": 0}},
                    "bad": {"quotaInfo": {"remainingFraction": True}},
                }
            }
        )
        self.assertIsNone(models["partial"]["remaining"])
        self.assertEqual(models["partial"]["resetTime"], "2030-01-01T00:00:00+00:00")
        self.assertEqual(models["empty"]["remaining"], 0)
        self.assertIsNone(models["bad"]["remaining"])

    def test_preserves_all_credit_types_without_private_account_data(self):
        result = parse_account_metadata(
            {
                "paidTier": {
                    "id": "g1-pro-tier",
                    "availableCredits": [
                        {
                            "creditType": "GOOGLE_ONE_AI",
                            "creditAmount": "125",
                            "minimumCreditAmountForUsage": "2",
                        },
                        {"creditType": "EXTRA", "creditAmount": 4},
                        {"creditType": "MISSING"},
                    ],
                },
                "cloudaicompanionProject": "private-project",
            }
        )
        self.assertEqual(result["plan"], "g1-pro-tier")
        self.assertEqual(len(result["credit_balances"]), 2)
        self.assertEqual(result["credit_balances"][0]["minimum"], 2)
        self.assertNotIn("private-project", str(result))
