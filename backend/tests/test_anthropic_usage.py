"""Tests for Claude Code OAuth account quota retrieval."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.anthropic import AnthropicError
from core.anthropic_usage import (
    ANTHROPIC_OAUTH_USAGE_URL,
    _reset_anthropic_usage_cache_for_testing,
    fetch_anthropic_oauth_usage,
    parse_anthropic_oauth_usage,
)


class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class AnthropicUsageTests(unittest.IsolatedAsyncioTestCase):
    def test_extra_usage_does_not_disappear_when_subscription_windows_are_missing(self):
        usage = parse_anthropic_oauth_usage(
            {"extra_usage": {"is_enabled": True, "used_credits": 125}}
        )
        self.assertEqual(usage["extra_usage"]["used_credits"], 125)
        self.assertEqual(usage["quota_status"], "unavailable")
        self.assertEqual(usage["windows"], [])

    def test_preserves_extra_usage_without_inventing_a_subscription(self):
        usage = parse_anthropic_oauth_usage(
            {
                "five_hour": {"utilization": 10},
                "extra_usage": {
                    "is_enabled": True,
                    "used_credits": 123,
                    "monthly_limit": 1000,
                    "utilization": 12.3,
                    "secret": "hidden",
                },
            }
        )
        self.assertNotIn("plan", usage)
        self.assertEqual(
            usage["extra_usage"],
            {
                "is_enabled": True,
                "used_credits": 123,
                "monthly_limit": 1000,
                "utilization": 12.3,
            },
        )

    def setUp(self) -> None:
        _reset_anthropic_usage_cache_for_testing()

    def tearDown(self) -> None:
        _reset_anthropic_usage_cache_for_testing()

    def test_parser_normalizes_legacy_usage_windows(self):
        usage = parse_anthropic_oauth_usage(
            {
                "tier": "max_20x",
                "five_hour": {
                    "utilization": 24.6,
                    "resets_at": "2033-05-18T03:33:20Z",
                },
                "seven_day": {
                    "utilization": 70,
                    "resets_at": "2033-05-24T03:33:20Z",
                },
                "seven_day_sonnet": {
                    "utilization": 110,
                    "resets_at": "2033-05-24T03:33:20Z",
                },
            }
        )

        self.assertEqual(usage["quota_type"], "account_rate_limits")
        self.assertEqual(usage["plan"], "max_20x")
        self.assertEqual(
            [window["id"] for window in usage["windows"]],
            ["session", "weekly", "weekly_sonnet"],
        )
        self.assertEqual(usage["windows"][0]["used_percentage"], 25)
        self.assertEqual(usage["windows"][0]["remaining_percentage"], 75)
        self.assertEqual(usage["windows"][2]["used_percentage"], 100)
        self.assertTrue(usage["windows"][0]["reset_time"].endswith("+00:00"))

    def test_parser_normalizes_current_limits_array(self):
        usage = parse_anthropic_oauth_usage(
            {
                "subscription_type": "max",
                "limits": [
                    {
                        "kind": "session",
                        "group": "session",
                        "percent": 5,
                        "is_active": True,
                        "resets_at": "2033-05-18T03:33:20Z",
                    },
                    {
                        "kind": "weekly_all",
                        "group": "weekly",
                        "percent": 14,
                        "resets_at": "2033-05-24T03:33:20Z",
                    },
                    {
                        "kind": "weekly_scoped",
                        "group": "weekly",
                        "percent": 16,
                        "resets_at": "2033-05-24T03:33:20Z",
                        "scope": {"model": {"display_name": "Fable"}},
                    },
                    {"kind": "unknown", "percent": "not-a-number"},
                ],
            }
        )

        self.assertEqual(usage["plan"], "max")
        self.assertEqual(
            [window["id"] for window in usage["windows"]],
            ["session", "weekly", "weekly_fable"],
        )
        self.assertEqual(usage["windows"][1]["label"], "7-Day All Models")
        self.assertEqual(usage["windows"][2]["label"], "7-Day Fable")

    def test_parser_rejects_payload_without_valid_windows(self):
        with self.assertRaisesRegex(AnthropicError, "valid usage windows"):
            parse_anthropic_oauth_usage({"five_hour": {"utilization": True}})

    async def test_fetch_uses_claude_headers_and_caches_the_snapshot(self):
        request = AsyncMock(
            return_value=FakeResponse(
                200,
                {
                    "five_hour": {
                        "utilization": 10,
                        "resets_at": "2033-05-18T03:33:20Z",
                    }
                },
            )
        )
        with (
            patch("core.anthropic_usage.get_async", request),
            patch(
                "core.anthropic_usage.get_claude_user_agent",
                AsyncMock(return_value="claude-cli/test"),
            ),
        ):
            first = await fetch_anthropic_oauth_usage("access-secret")
            second = await fetch_anthropic_oauth_usage("access-secret")

        self.assertEqual(first, second)
        request.assert_awaited_once()
        self.assertEqual(request.await_args.args[0], ANTHROPIC_OAUTH_USAGE_URL)
        headers = request.await_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer access-secret")
        self.assertEqual(headers["anthropic-beta"], "oauth-2025-04-20")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertEqual(headers["User-Agent"], "claude-cli/test")

    async def test_fetch_preserves_authentication_status_for_refresh(self):
        with (
            patch(
                "core.anthropic_usage.get_async",
                AsyncMock(return_value=FakeResponse(401, {"secret": "upstream detail"})),
            ),
            patch(
                "core.anthropic_usage.get_claude_user_agent",
                AsyncMock(return_value="claude-cli/test"),
            ),
        ):
            with self.assertRaises(AnthropicError) as context:
                await fetch_anthropic_oauth_usage("expired-secret")

        self.assertEqual(context.exception.status_code, 401)
        self.assertNotIn("upstream", str(context.exception).lower())

    async def test_fetch_rate_limit_enters_a_bounded_cooldown(self):
        request = AsyncMock(return_value=FakeResponse(429, {"retry_after": 0}))
        with (
            patch("core.anthropic_usage.get_async", request),
            patch(
                "core.anthropic_usage.get_claude_user_agent",
                AsyncMock(return_value="claude-cli/test"),
            ),
        ):
            for _ in range(2):
                with self.assertRaises(AnthropicError) as context:
                    await fetch_anthropic_oauth_usage("rate-limited-secret")

        self.assertEqual(context.exception.status_code, 429)
        request.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
