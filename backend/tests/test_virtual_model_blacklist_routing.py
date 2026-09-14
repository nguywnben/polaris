"""Virtual-model fallback behavior after provider-scoped 404 responses."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.api.primary import (
    ProviderRequestContext,
    _non_stream_request_upstream,
    _stream_request_upstream,
    non_stream_request,
    stream_request,
)
from core.api.utils import record_model_route_miss
from core.coordination import CoordinationReconciliationRequiredError
from core.request_trace_service import request_trace_scope
from fastapi import Response


class FakeUpstreamResponse:
    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content
        self.text = content.decode("utf-8")
        self.headers = {"content-type": "application/json"}


class VirtualModelBlacklistRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_stream_coordination_capacity_returns_bounded_503(self):
        record = AsyncMock()
        with (
            patch(
                "core.api.primary.get_antigravity_stream_to_nonstream",
                AsyncMock(return_value=False),
            ),
            patch(
                "core.api.primary.credential_manager.get_valid_model_credential",
                AsyncMock(
                    side_effect=CoordinationReconciliationRequiredError(
                        "secret coordination detail"
                    )
                ),
            ),
            patch("core.api.primary.record_unassigned_api_call_error", record),
        ):
            response = await _non_stream_request_upstream({"model": "model-a"})

        self.assertEqual(response.status_code, 503)
        self.assertIn(b"temporarily unavailable", response.body)
        self.assertNotIn(b"secret coordination detail", response.body)
        record.assert_awaited_once_with(
            status_code=503,
            mode="primary",
            model_name="model-a",
            reason="coordination_unavailable",
        )

    async def test_stream_coordination_capacity_returns_bounded_503(self):
        record = AsyncMock()
        with (
            patch(
                "core.api.primary.credential_manager.get_valid_model_credential",
                AsyncMock(
                    side_effect=CoordinationReconciliationRequiredError(
                        "secret coordination detail"
                    )
                ),
            ),
            patch("core.api.primary.record_unassigned_api_call_error", record),
        ):
            stream = _stream_request_upstream({"model": "model-a"})
            response = await anext(stream)

        self.assertEqual(response.status_code, 503)
        self.assertIn(b"temporarily unavailable", response.body)
        self.assertNotIn(b"secret coordination detail", response.body)
        record.assert_awaited_once_with(
            status_code=503,
            mode="primary",
            model_name="model-a",
            reason="coordination_unavailable",
        )

    async def test_closing_stream_releases_the_active_credential_lease(self):
        credential = {
            "provider": "google_antigravity",
            "token": "example-token",
            "project_id": "example-project",
        }
        context = ProviderRequestContext(
            provider_id="google_antigravity",
            target_url="http://fixture.invalid/api/chat",
            headers={},
            payload={"model": "model-a"},
            request_metrics={},
        )

        def fake_stream_post_async(**_kwargs):
            async def chunks():
                yield b'data: {"response":"partial"}\n\n'

            return chunks()

        release = AsyncMock()
        with (
            request_trace_scope("request-cancelled", "openai_chat") as trace_collector,
            patch(
                "core.api.primary.credential_manager.get_valid_model_credential",
                AsyncMock(return_value=("model-a", "credential.json", credential)),
            ),
            patch("core.api.primary.credential_manager.release_credential", release),
            patch("core.api.primary.prepare_provider_request", AsyncMock(return_value=context)),
            patch(
                "core.api.primary.get_retry_config",
                AsyncMock(
                    return_value={
                        "retry_enabled": False,
                        "max_retries": 0,
                        "retry_interval": 0,
                    }
                ),
            ),
            patch(
                "core.api.primary.get_antigravity_switch_credential_enabled",
                AsyncMock(return_value=False),
            ),
            patch("core.api.primary.get_auto_disable_error_codes", AsyncMock(return_value=[])),
            patch("core.api.primary.get_upstream_timeout_seconds", AsyncMock(return_value=30)),
            patch("core.api.primary.stream_post_async", side_effect=fake_stream_post_async),
        ):
            stream = stream_request(body={"model": "model-a"})
            self.assertEqual(await anext(stream), b'data: {"response":"partial"}\n\n')
            await stream.aclose()

        release.assert_awaited_once_with("credential.json", mode="primary")
        self.assertTrue(
            any(
                decision.category == "upstream" and decision.reason == "cancelled"
                for decision in trace_collector.decisions
            )
        )

    async def test_model_route_miss_sets_a_credential_scoped_cooldown(self):
        manager = AsyncMock()

        with patch("core.api.utils.record_call", AsyncMock(return_value=True)) as record_mock:
            await record_model_route_miss(
                manager,
                "credential.json",
                model_name="gemini-2.5-flash",
                provider="google_ai_studio",
            )

        manager.set_model_cooldown.assert_awaited_once()
        manager.release_credential.assert_awaited_once_with("credential.json", mode="primary")
        record_mock.assert_awaited_once()

    async def test_virtual_route_blacklists_404_and_tries_the_next_model(self):
        first_credential = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "example-key",
        }
        second_credential = {
            "provider": "google_antigravity",
            "token": "example-token",
            "project_id": "example-project",
        }
        first_context = ProviderRequestContext(
            provider_id="google_ai_studio",
            target_url="https://first.invalid",
            headers={},
            payload={"model": "gemini-retired"},
            request_metrics={},
        )
        second_context = ProviderRequestContext(
            provider_id="google_antigravity",
            target_url="https://second.invalid",
            headers={},
            payload={"model": "claude-sonnet-4-6"},
            request_metrics={},
        )

        with (
            patch(
                "core.api.primary.get_antigravity_stream_to_nonstream",
                AsyncMock(return_value=False),
            ),
            patch(
                "core.api.primary.credential_manager.get_valid_model_credential",
                AsyncMock(
                    side_effect=[
                        ("gemini-retired", "first.json", first_credential),
                        ("claude-sonnet-4-6", "second.json", second_credential),
                    ]
                ),
            ) as route_mock,
            patch(
                "core.api.primary.prepare_provider_request",
                AsyncMock(side_effect=[first_context, second_context]),
            ),
            patch(
                "core.api.primary.get_retry_config",
                AsyncMock(
                    return_value={
                        "retry_enabled": True,
                        "max_retries": 1,
                        "retry_interval": 0,
                    }
                ),
            ),
            patch(
                "core.api.primary.get_antigravity_switch_credential_enabled",
                AsyncMock(return_value=False),
            ),
            patch(
                "core.api.primary.get_auto_disable_error_codes",
                AsyncMock(return_value=[]),
            ),
            patch(
                "core.api.primary.get_upstream_timeout_seconds",
                AsyncMock(return_value=30),
            ),
            patch(
                "core.api.primary.post_async",
                AsyncMock(
                    side_effect=[
                        FakeUpstreamResponse(404, b'{"error":"model not found"}'),
                        FakeUpstreamResponse(503, b'{"error":"temporarily unavailable"}'),
                        FakeUpstreamResponse(200, b'{"response":"ok"}'),
                    ]
                ),
            ) as upstream_mock,
            patch(
                "core.api.primary.record_model_not_found",
                AsyncMock(),
            ) as blacklist_mock,
            patch(
                "core.api.primary.record_model_route_miss",
                AsyncMock(),
            ) as route_miss_mock,
            patch(
                "core.api.primary.record_api_call_success",
                AsyncMock(),
            ),
            patch("core.api.primary.record_api_call_error", AsyncMock()),
        ):
            response = await non_stream_request(
                body={"model": "gemini-retired", "request": {}},
                model_candidates=["gemini-retired", "claude-sonnet-4-6"],
                model_routing=True,
            )

        self.assertEqual(response.status_code, 200)
        blacklist_mock.assert_awaited_once_with(
            "google_ai_studio",
            "gemini-retired",
            credential_name="first.json",
        )
        route_miss_mock.assert_awaited_once()
        self.assertEqual(route_mock.await_count, 2)
        self.assertEqual(upstream_mock.await_count, 3)
        for call in route_mock.await_args_list:
            self.assertTrue(call.kwargs["respect_model_blacklist"])
        self.assertEqual(
            route_mock.await_args.kwargs["excluded_provider_models"],
            set(),
        )
        self.assertEqual(
            route_mock.await_args.kwargs["excluded_credential_models"],
            {("first.json", "gemini-retired")},
        )

    async def test_direct_model_404_tries_another_credential_without_persistent_blacklist(self):
        first_credential = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "example-key",
        }
        second_credential = {
            "provider": "google_antigravity",
            "token": "example-token",
            "project_id": "example-project",
        }
        first_context = ProviderRequestContext(
            provider_id="google_ai_studio",
            target_url="https://first.invalid",
            headers={},
            payload={"model": "gemini-2.5-flash"},
            request_metrics={},
        )
        second_context = ProviderRequestContext(
            provider_id="google_antigravity",
            target_url="https://second.invalid",
            headers={},
            payload={"model": "gemini-2.5-flash"},
            request_metrics={},
        )

        with (
            patch(
                "core.api.primary.get_antigravity_stream_to_nonstream",
                AsyncMock(return_value=False),
            ),
            patch(
                "core.api.primary.credential_manager.get_valid_model_credential",
                AsyncMock(
                    side_effect=[
                        ("gemini-2.5-flash", "first.json", first_credential),
                        ("gemini-2.5-flash", "second.json", second_credential),
                    ]
                ),
            ) as route_mock,
            patch(
                "core.api.primary.prepare_provider_request",
                AsyncMock(side_effect=[first_context, second_context]),
            ),
            patch(
                "core.api.primary.get_retry_config",
                AsyncMock(
                    return_value={
                        "retry_enabled": False,
                        "max_retries": 0,
                        "retry_interval": 0,
                    }
                ),
            ),
            patch(
                "core.api.primary.get_antigravity_switch_credential_enabled",
                AsyncMock(return_value=False),
            ),
            patch(
                "core.api.primary.get_auto_disable_error_codes",
                AsyncMock(return_value=[]),
            ),
            patch(
                "core.api.primary.get_upstream_timeout_seconds",
                AsyncMock(return_value=30),
            ),
            patch(
                "core.api.primary.post_async",
                AsyncMock(
                    side_effect=[
                        FakeUpstreamResponse(404, b'{"error":"model not found"}'),
                        FakeUpstreamResponse(200, b'{"response":"ok"}'),
                    ]
                ),
            ),
            patch("core.api.primary.record_model_not_found", AsyncMock()) as blacklist_mock,
            patch("core.api.primary.record_model_route_miss", AsyncMock()) as route_miss_mock,
            patch("core.api.primary.record_api_call_error", AsyncMock()),
        ):
            response = await non_stream_request(
                body={"model": "gemini-2.5-flash", "request": {}},
                model_routing=False,
            )

        self.assertEqual(response.status_code, 200)
        blacklist_mock.assert_not_awaited()
        route_miss_mock.assert_awaited_once()
        self.assertEqual(route_mock.await_count, 2)
        self.assertFalse(route_mock.await_args.kwargs["respect_model_blacklist"])
        self.assertEqual(
            route_mock.await_args.kwargs["excluded_credential_models"],
            {("first.json", "gemini-2.5-flash")},
        )

    async def test_virtual_stream_blacklists_404_and_continues_with_next_model(self):
        credentials = [
            {
                "provider": "google_ai_studio",
                "credential_type": "api_key",
                "api_key": "example-key",
            },
            {
                "provider": "google_antigravity",
                "token": "example-token",
                "project_id": "example-project",
            },
        ]
        contexts = [
            ProviderRequestContext(
                provider_id="google_ai_studio",
                target_url="https://first.invalid",
                headers={},
                payload={"model": "gemini-retired"},
                request_metrics={},
            ),
            ProviderRequestContext(
                provider_id="google_antigravity",
                target_url="https://second.invalid",
                headers={},
                payload={"model": "claude-sonnet-4-6"},
                request_metrics={},
            ),
        ]
        stream_calls = 0

        def fake_stream_post_async(**_kwargs):
            nonlocal stream_calls
            stream_calls += 1

            async def chunks():
                if stream_calls == 1:
                    yield Response(
                        content=b'{"error":"model not found"}',
                        status_code=404,
                        media_type="application/json",
                    )
                else:
                    yield b'data: {"candidates":[{"finishReason":"STOP"}]}\n\n'

            return chunks()

        with (
            patch(
                "core.api.primary.credential_manager.get_valid_model_credential",
                AsyncMock(
                    side_effect=[
                        ("gemini-retired", "first.json", credentials[0]),
                        ("claude-sonnet-4-6", "second.json", credentials[1]),
                    ]
                ),
            ) as route_mock,
            patch(
                "core.api.primary.prepare_provider_request",
                AsyncMock(side_effect=contexts),
            ),
            patch(
                "core.api.primary.get_retry_config",
                AsyncMock(
                    return_value={
                        "retry_enabled": False,
                        "max_retries": 0,
                        "retry_interval": 0,
                    }
                ),
            ),
            patch(
                "core.api.primary.get_antigravity_switch_credential_enabled",
                AsyncMock(return_value=False),
            ),
            patch(
                "core.api.primary.get_auto_disable_error_codes",
                AsyncMock(return_value=[]),
            ),
            patch(
                "core.api.primary.get_upstream_timeout_seconds",
                AsyncMock(return_value=30),
            ),
            patch("core.api.primary.stream_post_async", side_effect=fake_stream_post_async),
            patch("core.api.primary.record_model_not_found", AsyncMock()) as blacklist_mock,
            patch("core.api.primary.record_model_route_miss", AsyncMock()),
            patch("core.api.primary.record_api_call_success", AsyncMock()),
        ):
            chunks = [
                chunk
                async for chunk in stream_request(
                    body={"model": "gemini-retired", "request": {}},
                    model_candidates=["gemini-retired", "claude-sonnet-4-6"],
                    model_routing=True,
                )
            ]

        self.assertEqual(chunks, [b'data: {"candidates":[{"finishReason":"STOP"}]}\n\n'])
        blacklist_mock.assert_awaited_once_with(
            "google_ai_studio",
            "gemini-retired",
            credential_name="first.json",
        )
        self.assertEqual(route_mock.await_count, 2)
        self.assertEqual(
            route_mock.await_args.kwargs["excluded_provider_models"],
            set(),
        )
        self.assertEqual(
            route_mock.await_args.kwargs["excluded_credential_models"],
            {("first.json", "gemini-retired")},
        )

    async def test_direct_stream_404_tries_another_credential_for_the_same_model(self):
        credentials = [
            {
                "provider": "google_ai_studio",
                "credential_type": "api_key",
                "api_key": "example-key",
            },
            {
                "provider": "google_antigravity",
                "token": "example-token",
                "project_id": "example-project",
            },
        ]
        contexts = [
            ProviderRequestContext(
                provider_id="google_ai_studio",
                target_url="https://first.invalid",
                headers={},
                payload={"model": "gemini-2.5-flash"},
                request_metrics={},
            ),
            ProviderRequestContext(
                provider_id="google_antigravity",
                target_url="https://second.invalid",
                headers={},
                payload={"model": "gemini-2.5-flash"},
                request_metrics={},
            ),
        ]
        stream_calls = 0

        def fake_stream_post_async(**_kwargs):
            nonlocal stream_calls
            stream_calls += 1

            async def chunks():
                if stream_calls == 1:
                    yield Response(
                        content=b'{"error":"model not found"}',
                        status_code=404,
                        media_type="application/json",
                    )
                else:
                    yield b'data: {"candidates":[{"finishReason":"STOP"}]}\n\n'

            return chunks()

        with (
            patch(
                "core.api.primary.credential_manager.get_valid_model_credential",
                AsyncMock(
                    side_effect=[
                        ("gemini-2.5-flash", "first.json", credentials[0]),
                        ("gemini-2.5-flash", "second.json", credentials[1]),
                    ]
                ),
            ) as route_mock,
            patch(
                "core.api.primary.prepare_provider_request",
                AsyncMock(side_effect=contexts),
            ),
            patch(
                "core.api.primary.get_retry_config",
                AsyncMock(
                    return_value={
                        "retry_enabled": False,
                        "max_retries": 0,
                        "retry_interval": 0,
                    }
                ),
            ),
            patch(
                "core.api.primary.get_antigravity_switch_credential_enabled",
                AsyncMock(return_value=False),
            ),
            patch(
                "core.api.primary.get_auto_disable_error_codes",
                AsyncMock(return_value=[]),
            ),
            patch(
                "core.api.primary.get_upstream_timeout_seconds",
                AsyncMock(return_value=30),
            ),
            patch("core.api.primary.stream_post_async", side_effect=fake_stream_post_async),
            patch("core.api.primary.record_model_not_found", AsyncMock()) as blacklist_mock,
            patch("core.api.primary.record_model_route_miss", AsyncMock()) as route_miss_mock,
            patch("core.api.primary.record_api_call_success", AsyncMock()),
        ):
            chunks = [
                chunk
                async for chunk in stream_request(
                    body={"model": "gemini-2.5-flash", "request": {}},
                    model_routing=False,
                )
            ]

        self.assertEqual(chunks, [b'data: {"candidates":[{"finishReason":"STOP"}]}\n\n'])
        blacklist_mock.assert_not_awaited()
        route_miss_mock.assert_awaited_once()
        self.assertEqual(route_mock.await_count, 2)
        self.assertEqual(
            route_mock.await_args.kwargs["excluded_credential_models"],
            {("first.json", "gemini-2.5-flash")},
        )


if __name__ == "__main__":
    unittest.main()
