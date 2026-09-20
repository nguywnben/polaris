"""Reasoning controls preserve intent across routing, caching and provider transport."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.api.primary import (
    PrimarySessionState,
    _request_preparation_error,
    prepare_provider_request,
)
from core.converter.openai_to_gemini import convert_openai_to_gemini_request
from core.reasoning_control import ReasoningControlError, prepare_reasoning_request
from core.request_trace_service import request_trace_scope
from core.response_cache import generate_cache_key

INTENT = "_polaris_reasoning_effort"


def request(effort=None):
    result = {"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]}
    if effort is not None:
        result[INTENT] = effort
    return result


class ReasoningMappingTests(unittest.TestCase):
    def test_gemini_mappings_preserve_original_and_remove_internal_intent(self):
        cases = (
            ("gemini-3.8-flash-tiered", "low", {"thinkingLevel": "low"}),
            ("gemini-3.8-flash-tiered", "high", {"thinkingLevel": "high"}),
            ("gemini-3.1-pro-preview", "minimal", {"thinkingLevel": "low"}),
            ("gemini-3-flash-preview", "minimal", {"thinkingLevel": "minimal"}),
            ("gemini-2.5-flash", "none", {"thinkingBudget": 0}),
            ("gemini-2.5-flash-lite", "none", {"thinkingBudget": 0}),
            ("gemini-2.5-pro", "minimal", {"thinkingBudget": 1024}),
            ("gemini-2.5-flash", "low", {"thinkingBudget": 1024}),
            ("gemini-2.5-flash", "medium", {"thinkingBudget": 8192}),
            ("gemini-2.5-pro", "high", {"thinkingBudget": 24576}),
        )
        for provider in ("google_antigravity", "google_ai_studio", "vertex"):
            for model, effort, expected in cases:
                with self.subTest(provider=provider, model=model, effort=effort):
                    original = request(effort)
                    before = copy.deepcopy(original)
                    payload, options = prepare_reasoning_request(original, model, provider, "")
                    self.assertEqual(payload["generationConfig"]["thinkingConfig"], expected)
                    self.assertEqual(options, {})
                    self.assertNotIn(INTENT, payload)
                    self.assertEqual(original, before)

    def test_none_is_never_replaced_with_low_on_always_thinking_models(self):
        for model in ("gemini-3.8-flash-tiered", "gemini-3-pro-preview", "gemini-2.5-pro"):
            with (
                self.subTest(model=model),
                self.assertRaisesRegex(
                    ReasoningControlError, "does not support disabling reasoning"
                ),
            ):
                prepare_reasoning_request(request("none"), model, "google_antigravity", "")

    def test_unsupported_levels_models_and_adapters_fail_closed(self):
        cases = (
            ("gemini-3.8-flash-tiered", "minimal", "google_antigravity"),
            ("gemini-3-pro-preview", "medium", "google_antigravity"),
            ("gemini-3.8-flash-tiered", "xhigh", "google_antigravity"),
            ("gemini-2.5-flash", "max", "google_ai_studio"),
            ("gemini-2.5-flash-image", "low", "google_ai_studio"),
            ("gemini-2.0-flash", "low", "google_ai_studio"),
            ("unknown-model", "low", "google_antigravity"),
            ("claude-sonnet", "high", "google_antigravity"),
            ("muse-spark-1.3-contributor", "high", "muse_code"),
            ("claude-sonnet", "high", "anthropic"),
        )
        for model, effort, provider in cases:
            with self.subTest(model=model, effort=effort, provider=provider):
                with self.assertRaisesRegex(ReasoningControlError, "reasoning_effort"):
                    prepare_reasoning_request(request(effort), model, provider, "")

    def test_openai_wire_options_keep_effort_exactly(self):
        for effort in ("none", "minimal", "low", "medium", "high", "xhigh", "max"):
            for variant in ("openai_platform", "codex"):
                with self.subTest(effort=effort, variant=variant):
                    inner, options = prepare_reasoning_request(
                        request(effort), "selected-model", "openai", variant
                    )
                    expected = (
                        {"reasoning_effort": effort}
                        if variant == "openai_platform"
                        else {"reasoning": {"effort": effort}}
                    )
                    self.assertEqual(options, expected)
                    self.assertNotIn(INTENT, inner)

    def test_omitted_effort_preserves_existing_defaults(self):
        original = request()
        original["generationConfig"] = {"thinkingConfig": {"thinkingBudget": -1}}
        for provider in ("google_antigravity", "muse_code", "openai", "anthropic"):
            with self.subTest(provider=provider):
                inner, options = prepare_reasoning_request(original, "unknown", provider, "")
                self.assertEqual(inner, original)
                self.assertEqual(options, {})

    def test_selected_model_controls_mapping_on_each_attempt(self):
        original = request("high")
        first, _ = prepare_reasoning_request(original, "gemini-2.5-pro", "google_ai_studio", "")
        second, _ = prepare_reasoning_request(
            original, "gemini-3.8-flash-tiered", "google_antigravity", ""
        )
        self.assertEqual(first["generationConfig"]["thinkingConfig"], {"thinkingBudget": 24576})
        self.assertEqual(second["generationConfig"]["thinkingConfig"], {"thinkingLevel": "high"})
        self.assertEqual(original, request("high"))

    def test_explicit_effort_replaces_defaults_without_conflicting_controls(self):
        original = request("none")
        original["generationConfig"] = {
            "maxOutputTokens": 100,
            "thinkingConfig": {
                "thinkingLevel": "high",
                "thinkingBudget": -1,
                "includeThoughts": True,
            },
        }
        before = copy.deepcopy(original)
        inner, _ = prepare_reasoning_request(original, "gemini-2.5-flash", "vertex", "")
        self.assertEqual(
            inner["generationConfig"],
            {
                "maxOutputTokens": 100,
                "thinkingConfig": {"thinkingBudget": 0, "includeThoughts": False},
            },
        )
        self.assertEqual(original, before)

    def test_effort_partitions_response_cache(self):
        keys = {
            generate_cache_key("gemini-3.8-flash-tiered", {"request": request(effort)})
            for effort in (None, "none", "low", "high")
        }
        self.assertEqual(len(keys), 4)

    def test_translation_is_visible_in_content_free_trace(self):
        with request_trace_scope("reasoning-test", "openai_chat") as collector:
            prepare_reasoning_request(request("high"), "gemini-3.8-flash", "google_ai_studio", "")
        self.assertTrue(any(d.reason == "reasoning_effort_high" for d in collector.decisions))


class ReasoningTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_converter_retains_intent_without_premature_model_mapping(self):
        result = await convert_openai_to_gemini_request(
            {
                "model": "gemini-2.5-pro",
                "messages": [{"role": "user", "content": "Hello"}],
                "reasoning_effort": "high",
            }
        )
        self.assertEqual(result[INTENT], "high")
        self.assertNotIn("thinkingConfig", result["generationConfig"])

    async def test_ai_studio_final_payload_contains_native_control_not_internal_marker(self):
        with patch("core.api.primary.get_token_compression_config", AsyncMock(return_value={})):
            context = await prepare_provider_request(
                {"provider": "google_ai_studio", "api_key": "test-key"},
                {"model": "gemini-3.8-flash-tiered", "request": request("low")},
                streaming=True,
            )
        self.assertEqual(
            context.payload["generationConfig"]["thinkingConfig"], {"thinkingLevel": "low"}
        )
        self.assertNotIn(INTENT, json.dumps(context.payload))

    async def test_client_error_releases_credential_without_health_penalty(self):
        with (
            patch(
                "core.api.primary.credential_manager.release_credential", new=AsyncMock()
            ) as release,
            patch("core.api.primary.record_api_call_error", new=AsyncMock()) as record,
        ):
            response = await _request_preparation_error(
                ReasoningControlError("reasoning_effort=none is unsupported"),
                "fixture.json",
                {"provider": "google_antigravity"},
                "gemini-3.8-flash-tiered",
            )
        self.assertEqual(response.status_code, 400)
        release.assert_awaited_once()
        record.assert_not_awaited()

    async def test_final_transport_payloads_preserve_effort_for_both_stream_modes(self):
        credentials = (
            {
                "provider": "google_antigravity",
                "access_token": "test-token",
                "project_id": "test-project",
            },
            {"provider": "openai", "credential_type": "api_key", "api_key": "test-key"},
            {"provider": "openai", "credential_type": "oauth", "access_token": "test-token"},
        )
        for credential in credentials:
            for streaming in (False, True):
                with self.subTest(
                    credential_type=credential.get("credential_type"), streaming=streaming
                ):
                    with (
                        patch(
                            "core.api.primary.get_token_compression_config",
                            AsyncMock(return_value={}),
                        ),
                        patch(
                            "core.api.primary._get_session_state",
                            AsyncMock(
                                return_value=PrimarySessionState(
                                    conversation_id="conversation",
                                    trajectory_id="trajectory",
                                    session_id="session",
                                    step_index=1,
                                    created_at=1.0,
                                    last_used_at=1.0,
                                )
                            ),
                        ),
                    ):
                        context = await prepare_provider_request(
                            credential,
                            {
                                "model": "gemini-3.8-flash-tiered"
                                if credential["provider"] == "google_antigravity"
                                else "gpt-5.4",
                                "request": request("high"),
                            },
                            streaming=streaming,
                        )
                    payload = context.payload
                    self.assertNotIn(INTENT, json.dumps(payload))
                    if credential["provider"] == "google_antigravity":
                        self.assertEqual(
                            payload["request"]["generationConfig"]["thinkingConfig"],
                            {"thinkingLevel": "high"},
                        )
                    elif credential["credential_type"] == "api_key":
                        self.assertEqual(payload["reasoning_effort"], "high")
                    else:
                        self.assertEqual(payload["reasoning"], {"effort": "high"})


if __name__ == "__main__":
    unittest.main()
