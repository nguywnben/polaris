"""Synthetic end-to-end transport, quota and localization checks; no live inference."""

import json
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import muse_code
from core.i18n import SUPPORTED_LOCALES, locale_context, translate_text
from core.meta_responses_models import MetaResponsesRequest
from core.muse_provider_i18n import MESSAGES, SOURCE_KEYS
from core.panel import credentials
from core.router.primary.meta_responses import create_meta_response

ACCOUNT = {
    "provider": "muse_code",
    "credential_type": "oauth",
    "account_id": "a" * 64,
    "access_token": "synthetic-oauth",
    "api_key": "synthetic-inference",
}
MODEL = "muse-code/muse-spark-1.3"


class MuseIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_tool_history_survives_converter_and_muse_preparation(self):
        from core.converter.openai_to_gemini import convert_openai_to_gemini_request
        from core.converter.thought_signature import SKIP_THOUGHT_SIGNATURE_VALIDATOR

        canonical = await convert_openai_to_gemini_request(
            {
                "model": MODEL,
                "messages": [
                    {"role": "user", "content": "What is the weather in Hanoi?"},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_weather_1",
                                "type": "function",
                                "function": {
                                    "name": "lookup_weather",
                                    "arguments": '{"city":"Hanoi"}',
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call_weather_1",
                        "content": '{"temperature":29,"unit":"C"}',
                    },
                ],
            }
        )
        self.assertEqual(
            canonical["contents"][1]["parts"][0]["thoughtSignature"],
            SKIP_THOUGHT_SIGNATURE_VALIDATOR,
        )
        for streaming in (False, True):
            with self.subTest(streaming=streaming):
                _, _, payload = muse_code.prepare_request(ACCOUNT, canonical, MODEL, streaming)
                call, result = payload["input"][1:]
                self.assertEqual(call["type"], "function_call")
                self.assertEqual(call["call_id"], "call_weather_1")
                self.assertEqual(call["name"], "lookup_weather")
                self.assertEqual(json.loads(call["arguments"]), {"city": "Hanoi"})
                self.assertEqual(result["type"], "function_call_output")
                self.assertEqual(result["call_id"], "call_weather_1")
                self.assertEqual(json.loads(result["output"]), {"temperature": 29, "unit": "C"})
                self.assertNotIn("thoughtSignature", json.dumps(payload))

    async def test_real_signed_reasoning_remains_rejected_by_muse_preparation(self):
        from core.meta_model_api import MetaModelAPIError

        for streaming in (False, True):
            with self.subTest(streaming=streaming), self.assertRaises(MetaModelAPIError):
                muse_code.prepare_request(
                    ACCOUNT,
                    {
                        "contents": [
                            {
                                "role": "model",
                                "parts": [
                                    {
                                        "functionCall": {
                                            "id": "call_1",
                                            "name": "search",
                                            "args": {},
                                        },
                                        "thoughtSignature": "real-opaque-reasoning-signature",
                                    }
                                ],
                            }
                        ]
                    },
                    MODEL,
                    streaming,
                )

    async def test_client_preparation_errors_release_lease_without_penalizing_muse(self):
        from core.api import primary
        from core.meta_model_api import MetaModelAPIError
        from core.muse_oauth import MuseOAuthError

        from backend.tests.test_extended_provider_runtime import PrimaryExtendedIntegrationTests

        real_prepare = primary.prepare_provider_request
        cases = (
            (
                MetaModelAPIError,
                {
                    "contents": [
                        {
                            "role": "model",
                            "parts": [{"text": "private", "thoughtSignature": "real-signature"}],
                        }
                    ]
                },
            ),
            (
                MuseOAuthError,
                {
                    "contents": [{"role": "user", "parts": [{"text": "hello"}]}],
                    "tools": [{"functionDeclarations": [{"name": "lookup_weather"}]}],
                    "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
                },
            ),
        )
        for error_type, canonical in cases:
            # Use the real adapter so the test covers its typed validation errors,
            # not only an artificial exception injected at the runtime boundary.
            with self.assertRaises(error_type) as raised:
                muse_code.prepare_request(ACCOUNT, canonical, MODEL, True)
            self.assertEqual(raised.exception.status_code, 400)
            for streaming in (False, True):
                stack, release = PrimaryExtendedIntegrationTests().fixtures(
                    [(MODEL, "muse.json", ACCOUNT)]
                )
                with (
                    stack,
                    patch.object(primary, "prepare_provider_request", real_prepare),
                    patch.object(
                        primary, "get_token_compression_config", AsyncMock(return_value={})
                    ),
                    patch.object(primary, "post_async", AsyncMock()) as post,
                    patch.object(primary, "stream_extended_request") as transport,
                ):
                    request = {"model": MODEL, **canonical}
                    if streaming:
                        results = [item async for item in primary._stream_request_upstream(request)]
                        response = results[-1]
                    else:
                        response = await primary._non_stream_request_upstream(request)
                    with self.subTest(
                        error=error_type.__name__, streaming=streaming, check="status"
                    ):
                        self.assertEqual(response.status_code, 400, response.body)
                    with self.subTest(
                        error=error_type.__name__, streaming=streaming, check="lease"
                    ):
                        release.assert_awaited_once_with("muse.json", mode="primary")
                    with self.subTest(
                        error=error_type.__name__, streaming=streaming, check="health"
                    ):
                        primary.record_api_call_error.assert_not_awaited()
                    primary.record_api_call_success.assert_not_awaited()
                    post.assert_not_awaited()
                    transport.assert_not_called()

    async def test_untyped_preparation_failure_still_counts_as_provider_failure(self):
        from core.api import primary

        from backend.tests.test_extended_provider_runtime import PrimaryExtendedIntegrationTests

        for streaming in (False, True):
            stack, _ = PrimaryExtendedIntegrationTests().fixtures([(MODEL, "muse.json", ACCOUNT)])
            with (
                self.subTest(streaming=streaming),
                stack,
                patch.object(
                    primary,
                    "prepare_provider_request",
                    AsyncMock(side_effect=ValueError("Missing provider configuration")),
                ),
            ):
                if streaming:
                    responses = [
                        item async for item in primary._stream_request_upstream({"model": MODEL})
                    ]
                    response = responses[-1]
                else:
                    response = await primary._non_stream_request_upstream({"model": MODEL})
                self.assertEqual(response.status_code, 500)
                primary.record_api_call_error.assert_awaited_once()
                self.assertEqual(
                    primary.record_api_call_error.await_args.args[1:3], ("muse.json", 500)
                )

    async def test_muse_canonical_requests_do_not_receive_google_defaults(self):
        from core.converter.gemini_fix import normalize_gemini_request

        request = {
            "model": MODEL,
            "contents": [{"role": "user", "parts": [{"text": "hello"}]}],
            "generationConfig": {"maxOutputTokens": 128},
        }
        self.assertEqual(await normalize_gemini_request(request, mode="primary"), request)

    async def test_messages_ingress_uses_meta_compatibility_boundary_for_muse(self):
        from core.meta_model_api import MetaModelAPIError
        from core.models import ClaudeRequest
        from core.router.primary import anthropic
        from fastapi import HTTPException

        request = ClaudeRequest(
            model=MODEL, max_tokens=128, messages=[{"role": "user", "content": "hello"}]
        )
        resolution = SimpleNamespace(candidates=[MODEL], response_model=MODEL, is_virtual=False)
        with (
            patch.object(anthropic, "resolve_model_request", AsyncMock(return_value=resolution)),
            patch(
                "core.meta_model_api.anthropic_request_to_meta_canonical",
                AsyncMock(side_effect=MetaModelAPIError("Unsupported option")),
            ) as converter,
            patch(
                "core.converter.anthropic_to_gemini.anthropic_to_gemini_request",
                AsyncMock(side_effect=AssertionError("Used Google defaults")),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await anthropic.messages(request, "fixture")
        self.assertEqual(raised.exception.status_code, 400)
        converter.assert_awaited_once()

    async def test_catalog_management_mints_once_and_stores_the_key_used_for_discovery(self):
        storage = SimpleNamespace(
            get_credential=AsyncMock(return_value=ACCOUNT),
            store_credential=AsyncMock(return_value=True),
        )
        fresh = {**ACCOUNT, "api_key": "new-inference-key"}
        with (
            patch.object(credentials, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(muse_code, "refresh_credential", AsyncMock(return_value=fresh)) as refresh,
            patch.object(
                muse_code, "discover_minted_models", AsyncMock(return_value=[MODEL])
            ) as discover,
        ):
            response = await credentials.get_credential_models(
                "muse.json", "fixture", mode="primary"
            )
        self.assertEqual(response.status_code, 200)
        refresh.assert_awaited_once()
        self.assertEqual(discover.await_args.args[0]["api_key"], "new-inference-key")
        self.assertEqual(
            storage.store_credential.await_args.args[1]["api_key"], "new-inference-key"
        )

    async def test_expired_account_error_during_edit_is_actionable_not_an_unhandled_500(self):
        from core.models import CredentialUpdateRequest
        from core.muse_oauth import MuseOAuthError
        from fastapi import HTTPException

        storage = SimpleNamespace(get_credential=AsyncMock(return_value=ACCOUNT))
        with (
            patch.object(credentials, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(
                muse_code,
                "refresh_credential",
                AsyncMock(
                    side_effect=MuseOAuthError(
                        "Muse Code session is no longer valid. Sign in again.", 401
                    )
                ),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await credentials.update_credential_configuration(
                    "muse.json",
                    CredentialUpdateRequest(credential_label="Work"),
                    "fixture",
                    mode="primary",
                )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("Sign in again", raised.exception.detail)

    async def test_native_prepare_stream_preserves_history_and_usage_but_not_subscription_events(
        self,
    ):
        from core.api import primary
        from core.extended_provider_runtime import http_client

        from backend.tests.test_extended_provider_runtime import PrimaryExtendedIntegrationTests

        real_prepare = primary.prepare_provider_request
        stack, _ = PrimaryExtendedIntegrationTests().fixtures([(MODEL, "muse.json", ACCOUNT)])
        history = [
            {"type": "reasoning", "summary": [], "encrypted_content": "synthetic-opaque"},
            {"type": "function_call", "call_id": "call_1", "name": "add", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "call_1", "output": "5"},
        ]
        output = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "5"}],
        }
        events = [
            {"type": "response.subscription_usage", "private": "quota-not-for-clients"},
            {"type": "response.output_item.done", "item": output},
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_fixture",
                    "status": "completed",
                    "model": "muse-spark-1.3",
                    "output": [output],
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                },
            },
        ]
        from backend.tests.test_muse_quota_stream import USAGE

        events.append({"type": "response.subscription_usage", "subscription": USAGE})
        observer = AsyncMock()
        sent = []

        def handler(request):
            self.assertEqual(str(request.url), "https://api.meta.ai/v1/responses")
            self.assertEqual(request.headers["Authorization"], "Bearer synthetic-inference")
            self.assertNotIn("synthetic-oauth", str(request.headers))
            sent.append(json.loads(request.content))
            return httpx.Response(
                200, content="".join("data: " + json.dumps(e) + "\n\n" for e in events).encode()
            )

        @asynccontextmanager
        async def client(**kwargs):
            self.assertFalse(kwargs["follow_redirects"])
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
                yield session

        async def policy(body):
            return None, body

        with (
            stack,
            patch.object(primary, "prepare_provider_request", real_prepare),
            patch.object(primary, "get_token_compression_config", AsyncMock(return_value={})),
            patch.object(primary, "runtime_admission_response", return_value=None),
            patch.object(primary, "apply_pre_call_guardrails", AsyncMock(side_effect=policy)),
            patch.object(http_client, "get_streaming_client", client),
            patch.object(
                primary, "subscription_observer", return_value=observer, create=True
            ) as bind,
        ):
            response = await create_meta_response(
                MetaResponsesRequest(model=MODEL, input=history, tool_choice="auto"),
                "fixture",
                resolution=SimpleNamespace(
                    candidates=[MODEL], response_model=MODEL, is_virtual=False
                ),
            )
            self.assertEqual(response.status_code, 200, response.body)
            result = json.loads(response.body)
            self.assertEqual(result["output"], [output])
            self.assertEqual(result["model"], MODEL)
            self.assertNotIn("quota-not-for-clients", str(result))
            primary.record_api_call_success.assert_awaited_once()
            self.assertEqual(
                primary.record_api_call_success.await_args.kwargs["token_usage"]["output_tokens"], 2
            )
        self.assertEqual(sent[0]["input"], history)
        self.assertEqual(sent[0]["model"], "muse-spark-1.3")
        self.assertFalse(sent[0]["store"])
        bind.assert_called_once_with("muse.json", ACCOUNT)
        observer.assert_awaited_once()
        self.assertEqual(observer.await_args.args[0]["window"]["used_percent"], 7)

    async def test_native_mixed_billing_routes_and_forced_tools_are_rejected_before_dispatch(self):
        from core.api import primary

        with patch.object(primary, "stream_request") as dispatch:
            for models, choice in (
                ([MODEL, "muse-spark-1.3"], "auto"),
                ([MODEL], "required"),
                ([MODEL], "none"),
            ):
                response = await create_meta_response(
                    MetaResponsesRequest(model="alias", input="hello", tool_choice=choice),
                    "fixture",
                    resolution=SimpleNamespace(
                        candidates=models, response_model="alias", is_virtual=True
                    ),
                )
                self.assertEqual(response.status_code, 400)
        dispatch.assert_not_called()

    async def test_quota_rechecks_eligibility_and_exposes_no_secrets(self):
        fresh = {
            **ACCOUNT,
            "user_email": "fixture@example.test",
            "subscription_usage": {
                "window": {
                    "used_percent": 35,
                    "window_duration_mins": 300,
                    "resets_at": 1789547671,
                },
                "weekly": {"used_percent": 10, "resets_at": 1789948800},
                "tier": "opaque-tier",
                "observed_at": 1789534990,
            },
        }
        storage = SimpleNamespace(
            get_credential=AsyncMock(return_value=ACCOUNT),
            store_credential=AsyncMock(return_value=True),
        )
        with (
            patch.object(credentials, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(muse_code, "refresh_credential", AsyncMock(return_value=fresh)) as refresh,
        ):
            response = await credentials.get_credential_quota(
                "muse.json", "fixture", mode="primary"
            )
        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(response.headers["cache-control"], "no-store")
        result = json.loads(response.body)
        self.assertEqual(result["windows"][0]["remaining_percentage"], 65)
        self.assertNotIn("synthetic", str(result))
        self.assertNotIn("user_email", result)
        self.assertEqual(result["subscription_tier"], "opaque-tier")
        self.assertNotIn("plan", result)
        refresh.assert_awaited_once_with(ACCOUNT)
        storage.store_credential.assert_awaited_once()
        stored = storage.store_credential.await_args.args[1]
        self.assertEqual(stored["user_email"], "fixture@example.test")
        from core.credential_fleet_query import enrich_credential_summary

        card = enrich_credential_summary(
            {"filename": "muse.json", "user_email": None},
            stored,
            backend_type="sqlite",
            mode="primary",
        )
        self.assertEqual(card["user_email"], "fixture@example.test")

    def test_console_errors_have_all_locales_and_protocol_text_stays_unchanged(self):
        for values in MESSAGES.values():
            self.assertEqual(set(values), set(SUPPORTED_LOCALES))
            self.assertTrue(all(values.values()))
        for source in SOURCE_KEYS:
            with locale_context("vi"):
                self.assertNotEqual(translate_text(source), source)
            with locale_context("vi", enabled=False):
                self.assertEqual(translate_text(source), source)

    async def test_verification_does_not_report_success_when_rotated_key_cannot_be_saved(self):
        from core.panel import credential_operations as operations

        storage = SimpleNamespace(
            get_credential=AsyncMock(return_value=ACCOUNT),
            store_credential=AsyncMock(return_value=False),
        )
        with (
            patch.object(operations, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(muse_code, "refresh_credential", AsyncMock(return_value=ACCOUNT)),
            patch.object(muse_code, "discover_minted_models", AsyncMock(return_value=[MODEL])),
        ):
            response = await operations.verify_credential_common("muse.json", mode="primary")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(json.loads(response.body)["success"])
