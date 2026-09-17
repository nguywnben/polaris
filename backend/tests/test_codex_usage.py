"""Tests for Codex account rate-limit retrieval and normalization."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.codex import CodexError
from core.codex_usage import fetch_codex_usage, parse_codex_usage


class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class CodexUsageTests(unittest.IsolatedAsyncioTestCase):
    def test_credits_and_plan_remain_visible_without_rate_windows(self):
        usage = parse_codex_usage({"plan_type": "pro", "credits": {"balance": 5}})
        self.assertEqual(usage["plan"], "pro")
        self.assertEqual(usage["credits"]["balance"], 5)
        self.assertEqual(usage["quota_status"], "unavailable")
        self.assertEqual(usage["windows"], [])

    def test_missing_usage_is_not_an_unused_window(self):
        for value in (None, True, "", "bad", float("nan")):
            with self.subTest(value=value), self.assertRaises(CodexError):
                parse_codex_usage({"rate_limit": {"primary_window": {"used_percent": value}}})

    def test_optional_account_facts_are_not_invented(self):
        usage = parse_codex_usage({"rate_limit": {"primary_window": {"used_percent": 0}}})
        self.assertNotIn("reset_credits", usage)
        self.assertNotIn("limit_reached", usage)
        self.assertNotIn("review_limit_reached", usage)
        self.assertNotIn("plan", usage)
        self.assertEqual(usage["windows"][0]["remaining_percentage"], 100)

    def test_preserves_additional_model_windows_and_credit_balance(self):
        usage = parse_codex_usage(
            {
                "rate_limit": {"primary_window": {"used_percent": 10}},
                "additional_rate_limits": [
                    {
                        "limit_name": "codex_other",
                        "metered_feature": "other",
                        "rate_limit": {"primary_window": {"used_percent": 40}},
                    }
                ],
                "credits": {
                    "has_credits": True,
                    "unlimited": False,
                    "balance": "12.5",
                    "secret": "hidden",
                },
            }
        )
        self.assertEqual(len(usage["windows"]), 2)
        self.assertEqual(usage["windows"][1]["remaining_percentage"], 60)
        self.assertIn("codex_other", usage["windows"][1]["label"])
        self.assertEqual(
            usage["credits"], {"has_credits": True, "unlimited": False, "balance": 12.5}
        )

    def test_parser_normalizes_standard_and_review_windows(self):
        usage = parse_codex_usage(
            {
                "plan_type": "plus",
                "rate_limit": {
                    "limit_reached": "false",
                    "primary_window": {
                        "used_percent": 24.6,
                        "reset_at": 2_000_000_000,
                        "limit_window_seconds": 18_000,
                    },
                    "secondary_window": {
                        "percent_used": "75",
                        "resets_at": 2_000_100_000_000,
                        "limit_window_seconds": 604_800,
                    },
                },
                "rate_limits_by_limit_id": {
                    "code_review": {
                        "rate_limit": {
                            "limit_reached": "true",
                            "primary": {
                                "used_percent": 110,
                                "reset_at": "2033-05-18T03:33:20Z",
                            },
                        }
                    }
                },
                "rate_limit_reset_credits": {"available_count": "2"},
            }
        )

        self.assertEqual(usage["quota_type"], "account_rate_limits")
        self.assertEqual(usage["plan"], "plus")
        self.assertFalse(usage["limit_reached"])
        self.assertTrue(usage["review_limit_reached"])
        self.assertEqual(usage["reset_credits"], {"available_count": 2})
        self.assertEqual(
            [window["id"] for window in usage["windows"]],
            [
                "session",
                "weekly",
                "review_session",
            ],
        )
        self.assertEqual(usage["windows"][0]["label"], "5-Hour Limit")
        self.assertEqual(usage["windows"][0]["used_percentage"], 25)
        self.assertEqual(usage["windows"][0]["remaining_percentage"], 75)
        self.assertEqual(usage["windows"][1]["label"], "7-Day Limit")
        self.assertEqual(usage["windows"][2]["used_percentage"], 100)
        self.assertEqual(usage["windows"][2]["remaining_percentage"], 0)
        self.assertTrue(usage["windows"][0]["reset_time"].endswith("+00:00"))

    def test_parser_rejects_payload_without_any_account_facts(self):
        with self.assertRaisesRegex(CodexError, "valid rate-limit windows"):
            parse_codex_usage({"rate_limit": {}})

    async def test_fetch_uses_configured_endpoint_and_account_header(self):
        request = AsyncMock(
            return_value=FakeResponse(
                200,
                {
                    "plan_type": "team",
                    "rate_limit": {
                        "primary_window": {
                            "used_percent": 10,
                            "reset_at": "2033-05-18T03:33:20Z",
                        }
                    },
                },
            )
        )
        with (
            patch("core.codex_usage.get_async", request),
            patch(
                "core.codex_usage.get_codex_usage_url",
                AsyncMock(return_value="https://chatgpt.com/backend-api/wham/usage"),
            ),
            patch(
                "core.codex_usage.get_codex_user_agent",
                AsyncMock(return_value="codex_cli_rs/test"),
            ),
        ):
            usage = await fetch_codex_usage("access-secret", "account-123")

        self.assertEqual(usage["plan"], "team")
        self.assertEqual(
            request.await_args.args[0],
            "https://chatgpt.com/backend-api/wham/usage",
        )
        headers = request.await_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer access-secret")
        self.assertEqual(headers["ChatGPT-Account-Id"], "account-123")
        self.assertEqual(headers["Accept"], "application/json")

    async def test_fetch_preserves_authentication_status_for_token_refresh(self):
        with (
            patch(
                "core.codex_usage.get_async",
                AsyncMock(return_value=FakeResponse(401, {"detail": "expired"})),
            ),
            patch(
                "core.codex_usage.get_codex_usage_url",
                AsyncMock(return_value="https://chatgpt.com/backend-api/wham/usage"),
            ),
            patch(
                "core.codex_usage.get_codex_user_agent",
                AsyncMock(return_value="codex_cli_rs/test"),
            ),
        ):
            with self.assertRaises(CodexError) as context:
                await fetch_codex_usage("expired-token", "account-123")

        self.assertEqual(context.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
