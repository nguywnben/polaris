"""Production boundary tests for ephemeral Playground inference runs."""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.requests import Request

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main
from core.identity import (
    AuthorizationDenied,
    ManagementPermission,
    ManagementPrincipal,
    ManagementRole,
    ManagementRouteTransport,
    management_route_manifest,
    require_management_route,
)
from core.panel import playground as playground_module
from core.panel.playground import (
    PLAYGROUND_MAX_BODY_BYTES,
    PlaygroundRateLimiter,
    PlaygroundRunRequest,
    create_playground_run,
    decode_playground_metadata,
    reset_playground_runtime_for_testing,
)
from core.playground_metrics import record_playground_result, render_playground_metrics
from core.utils import verify_panel_token


def _request(request_id: str = "playground-request") -> Request:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/playground/runs",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
            "server": ("test", 80),
        }
    )
    request.state.request_id = request_id
    request.state.management_auth_reference = "a" * 64
    return request


def _run_request(**overrides) -> PlaygroundRunRequest:
    payload = {
        "schema_version": "playground-request.v1",
        "protocol": "openai_chat",
        "model": "polaris",
        "stream": False,
        "timeout_seconds": 30,
        "request": {"messages": [{"role": "user", "content": "Hello"}]},
    }
    payload.update(overrides)
    return PlaygroundRunRequest(**payload)


class PlaygroundContractTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_playground_runtime_for_testing()

    def test_contract_is_closed_and_cannot_accept_credentials(self) -> None:
        for forbidden in ("api_key", "authorization", "credential", "headers"):
            with (
                self.subTest(location="boundary", forbidden=forbidden),
                self.assertRaises(ValueError),
            ):
                PlaygroundRunRequest(
                    schema_version="playground-request.v1",
                    protocol="openai_chat",
                    model="polaris",
                    request={"messages": [{"role": "user", "content": "Hello"}]},
                    **{forbidden: "must-not-be-accepted"},
                )
            with (
                self.subTest(location="native request", forbidden=forbidden),
                self.assertRaises(ValueError),
            ):
                _run_request(request={forbidden: "must-not-be-accepted"})
        with self.assertRaises(ValueError):
            _run_request(request={"Authorization": "must-not-be-accepted"})

    def test_contract_bounds_protocol_model_timeout_and_payload(self) -> None:
        invalid = (
            {"protocol": "vertex"},
            {"model": ""},
            {"model": "m" * 257},
            {"timeout_seconds": 0},
            {"timeout_seconds": 121},
            {
                "request": {
                    "messages": [{"role": "user", "content": "x" * PLAYGROUND_MAX_BODY_BYTES}]
                }
            },
        )
        for overrides in invalid:
            with self.subTest(overrides=tuple(overrides)), self.assertRaises(ValueError):
                _run_request(**overrides)

    def test_rate_limiter_is_per_principal_bounded_and_reports_retry(self) -> None:
        limiter = PlaygroundRateLimiter(max_runs=2, window_seconds=60, max_principals=2)

        self.assertEqual(limiter.admit("a" * 64, now=100.0), 0)
        self.assertEqual(limiter.admit("a" * 64, now=101.0), 0)
        self.assertEqual(limiter.admit("a" * 64, now=102.0), 58)
        self.assertEqual(limiter.admit("b" * 64, now=102.0), 0)
        self.assertEqual(limiter.tracked_principals, 2)

        self.assertEqual(limiter.admit("c" * 64, now=200.0), 0)
        self.assertLessEqual(limiter.tracked_principals, 2)

    def test_playground_requires_active_operator_permission(self) -> None:
        policy = next(
            entry
            for entry in management_route_manifest()
            if entry.method == "POST" and entry.path == "/api/playground/runs"
        )
        self.assertEqual(policy.permission, ManagementPermission.CREDENTIALS_OPERATE)
        operator = ManagementPrincipal.oidc_user(
            issuer="https://idp.example",
            subject="operator-1",
            role=ManagementRole.OPERATOR,
        )
        viewer = ManagementPrincipal.oidc_user(
            issuer="https://idp.example",
            subject="viewer-1",
            role=ManagementRole.VIEWER,
        )
        self.assertTrue(
            require_management_route(
                operator,
                transport=ManagementRouteTransport.HTTP,
                method="POST",
                path="/api/playground/runs",
            ).allowed
        )
        with self.assertRaises(AuthorizationDenied):
            require_management_route(
                viewer,
                transport=ManagementRouteTransport.HTTP,
                method="POST",
                path="/api/playground/runs",
            )


class PlaygroundEndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        reset_playground_runtime_for_testing()

    async def test_management_authentication_is_required(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/playground/runs",
                json=json.loads(_run_request().model_dump_json()),
            )

        self.assertEqual(response.status_code, 401)

    async def test_authenticated_http_route_preserves_native_success_contract(self) -> None:
        async def authenticated(request: Request) -> str:
            request.state.management_auth_reference = "a" * 64
            request.state.management_principal = ManagementPrincipal.local_owner()
            return "session"

        main.app.dependency_overrides[verify_panel_token] = authenticated
        try:
            with (
                patch.object(
                    playground_module,
                    "_dispatch_public_request",
                    new=AsyncMock(return_value=JSONResponse({"id": "chatcmpl-http"})),
                ),
                patch.object(
                    playground_module,
                    "record_classified_management_response",
                    new=AsyncMock(),
                ),
            ):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=main.app),
                    base_url="http://test",
                ) as client:
                    response = await client.post(
                        "/api/playground/runs",
                        json=json.loads(_run_request().model_dump_json()),
                    )
        finally:
            main.app.dependency_overrides.pop(verify_panel_token, None)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"id": "chatcmpl-http"})
        metadata = decode_playground_metadata(response.headers["x-polaris-playground-metadata"])
        self.assertEqual(metadata["request_id"], response.headers["x-request-id"])

    async def test_playground_body_limit_is_enforced_before_route_parsing(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/playground/runs",
                content=b"x" * (PLAYGROUND_MAX_BODY_BYTES + 1),
                headers={"content-type": "application/json"},
            )

        self.assertEqual(response.status_code, 413)
        self.assertNotIn("x" * 100, response.text)

    async def test_non_stream_response_preserves_public_body_and_adds_safe_metadata(self) -> None:
        public = JSONResponse(
            {
                "id": "chatcmpl-test",
                "choices": [{"message": {"role": "assistant", "content": "answer"}}],
            }
        )
        audit = AsyncMock()
        with (
            patch.object(
                playground_module,
                "_dispatch_public_request",
                new=AsyncMock(return_value=public),
            ),
            patch.object(playground_module, "record_classified_management_response", audit),
        ):
            response = await create_playground_run(
                _run_request(), _request(), token="session-token"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body), json.loads(public.body))
        metadata = decode_playground_metadata(response.headers["x-polaris-playground-metadata"])
        self.assertEqual(metadata["schema_version"], "playground-metadata.v1")
        self.assertEqual(metadata["request_id"], "playground-request")
        self.assertEqual(metadata["protocol"], "openai_chat")
        self.assertEqual(metadata["requested_model"], "polaris")
        self.assertNotIn("credential", json.dumps(metadata).lower())
        self.assertNotIn("session-token", json.dumps(metadata))
        audit.assert_awaited_once()
        self.assertEqual(audit.await_args.kwargs["status_code"], 200)

    async def test_every_supported_protocol_delegates_to_its_public_handler(self) -> None:
        cases = (
            (
                _run_request(),
                "core.router.primary.openai.chat_completions",
            ),
            (
                _run_request(protocol="openai_responses", request={"input": "Hello"}),
                "core.router.primary.responses.create_response",
            ),
            (
                _run_request(
                    protocol="anthropic_messages",
                    request={
                        "messages": [{"role": "user", "content": "Hello"}],
                        "max_tokens": 16,
                    },
                ),
                "core.router.primary.anthropic.messages",
            ),
            (
                _run_request(
                    protocol="gemini",
                    request={"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]},
                ),
                "core.router.primary.gemini.generate_content",
            ),
            (
                _run_request(
                    protocol="gemini",
                    stream=True,
                    request={"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]},
                ),
                "core.router.primary.gemini.stream_generate_content",
            ),
        )
        for run, target in cases:
            with (
                self.subTest(protocol=run.protocol, stream=run.stream),
                patch(
                    target,
                    new=AsyncMock(return_value=Response(status_code=204)),
                ) as handler,
            ):
                response = await playground_module._dispatch_public_request(run)

                self.assertEqual(response.status_code, 204)
                handler.assert_awaited_once()
                self.assertEqual(
                    handler.await_args.args[0].model_dump().get("model", run.model), run.model
                )

    async def test_invalid_native_request_uses_the_public_protocol_error_shape(self) -> None:
        with patch.object(
            playground_module,
            "record_classified_management_response",
            new=AsyncMock(),
        ):
            response = await create_playground_run(
                _run_request(request={}),
                _request(),
                token="session-token",
            )

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body)
        self.assertEqual(payload["error"]["type"], "invalid_request_error")
        self.assertEqual(payload["error"]["code"], "invalid_request")

    async def test_non_stream_timeout_returns_native_504_and_cancels_dispatch(self) -> None:
        cancelled = asyncio.Event()

        async def blocked(*_args, **_kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with (
            patch.object(playground_module, "_dispatch_public_request", side_effect=blocked),
            patch.object(playground_module, "record_classified_management_response", AsyncMock()),
        ):
            response = await create_playground_run(
                _run_request(timeout_seconds=1),
                _request(),
                token="session-token",
            )

        self.assertEqual(response.status_code, 504)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(json.loads(response.body)["error"]["code"], "service_unavailable")

    async def test_public_http_error_keeps_status_headers_and_native_shape(self) -> None:
        audit = AsyncMock()
        with (
            patch.object(
                playground_module,
                "_dispatch_public_request",
                new=AsyncMock(
                    side_effect=HTTPException(
                        status_code=503,
                        detail="The virtual model has no available provider models.",
                        headers={"Retry-After": "9"},
                    )
                ),
            ),
            patch.object(playground_module, "record_classified_management_response", audit),
        ):
            response = await create_playground_run(
                _run_request(), _request(), token="session-token"
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["Retry-After"], "9")
        self.assertEqual(json.loads(response.body)["error"]["code"], "service_unavailable")
        audit.assert_awaited_once()
        self.assertEqual(audit.await_args.kwargs["status_code"], 503)

    async def test_stream_relays_native_chunks_then_emits_safe_metadata(self) -> None:
        async def chunks():
            yield b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
            yield b"data: [DONE]\n\n"

        public = StreamingResponse(chunks(), media_type="text/event-stream")
        with (
            patch.object(
                playground_module,
                "_dispatch_public_request",
                new=AsyncMock(return_value=public),
            ),
            patch.object(
                playground_module,
                "record_classified_management_response",
                new=AsyncMock(),
            ),
        ):
            response = await create_playground_run(
                _run_request(stream=True), _request(), token="session-token"
            )
            content = b"".join([chunk async for chunk in response.body_iterator])

        self.assertIn(b'data: {"choices"', content)
        self.assertIn(b"data: [DONE]", content)
        self.assertIn(b"event: polaris.playground.metadata", content)
        self.assertNotIn(b"session-token", content)

    async def test_closing_stream_propagates_cancellation_to_public_iterator(self) -> None:
        closed = asyncio.Event()

        async def chunks():
            try:
                yield b'data: {"choices":[{"delta":{"content":"one"}}]}\n\n'
                await asyncio.Event().wait()
            finally:
                closed.set()

        public = StreamingResponse(chunks(), media_type="text/event-stream")
        audit = AsyncMock()
        with (
            patch.object(
                playground_module,
                "_dispatch_public_request",
                new=AsyncMock(return_value=public),
            ),
            patch.object(playground_module, "record_classified_management_response", audit),
        ):
            response = await create_playground_run(
                _run_request(stream=True), _request(), token="session-token"
            )
            iterator = response.body_iterator
            self.assertTrue((await iterator.__anext__()).startswith(b"data:"))
            await iterator.aclose()

        self.assertTrue(closed.is_set())
        audit.assert_awaited_once()
        self.assertEqual(audit.await_args.kwargs["status_code"], 499)

    async def test_stream_timeout_closes_upstream_and_emits_native_error_metadata(self) -> None:
        closed = asyncio.Event()

        async def chunks():
            try:
                yield b'data: {"choices":[{"delta":{"content":"one"}}]}\n\n'
                await asyncio.Event().wait()
            finally:
                closed.set()

        public = StreamingResponse(chunks(), media_type="text/event-stream")
        audit = AsyncMock()
        with (
            patch.object(
                playground_module,
                "_dispatch_public_request",
                new=AsyncMock(return_value=public),
            ),
            patch.object(playground_module, "record_classified_management_response", audit),
        ):
            response = await create_playground_run(
                _run_request(stream=True, timeout_seconds=1),
                _request(),
                token="session-token",
            )
            content = b"".join([chunk async for chunk in response.body_iterator])

        self.assertTrue(closed.is_set())
        self.assertIn(b'"code":"service_unavailable"', content)
        self.assertIn(b'"status_code":504', content)
        audit.assert_awaited_once()
        self.assertEqual(audit.await_args.kwargs["status_code"], 504)

    async def test_prompt_and_output_are_absent_from_logs_audit_and_metadata(self) -> None:
        prompt_secret = "prompt-private-marker"
        output_secret = "output-private-marker"
        response_body = {"choices": [{"message": {"content": output_secret}}]}
        audit = AsyncMock()
        with (
            patch.object(
                playground_module,
                "_dispatch_public_request",
                new=AsyncMock(return_value=JSONResponse(response_body)),
            ),
            patch.object(playground_module, "record_classified_management_response", audit),
            patch.object(playground_module.log, "info") as info,
        ):
            response = await create_playground_run(
                _run_request(request={"messages": [{"role": "user", "content": prompt_secret}]}),
                _request(),
                token="session-token",
            )

        metadata = decode_playground_metadata(response.headers["x-polaris-playground-metadata"])
        side_channels = (
            json.dumps(metadata) + repr(info.call_args_list) + repr(audit.call_args_list)
        )
        self.assertNotIn(prompt_secret, side_channels)
        self.assertNotIn(output_secret, side_channels)
        self.assertIn(output_secret, response.body.decode())

    async def test_rate_limit_returns_retry_after_without_dispatching(self) -> None:
        dispatch = AsyncMock(return_value=Response(status_code=204))
        with (
            patch.object(playground_module, "_dispatch_public_request", dispatch),
            patch.object(
                playground_module,
                "_playground_limiter",
                PlaygroundRateLimiter(max_runs=1, window_seconds=60, max_principals=10),
            ),
            patch.object(playground_module, "record_classified_management_response", AsyncMock()),
        ):
            first = await create_playground_run(
                _run_request(), _request("request-one"), token="session-token"
            )
            second = await create_playground_run(
                _run_request(), _request("request-two"), token="session-token"
            )

        self.assertEqual(first.status_code, 204)
        self.assertEqual(second.status_code, 429)
        self.assertIn("Retry-After", second.headers)
        self.assertEqual(dispatch.await_count, 1)

    def test_metrics_use_only_fixed_protocol_and_outcome_labels(self) -> None:
        record_playground_result("openai_chat", "succeeded", 25)
        record_playground_result("untrusted/model", "secret", 50)

        output = render_playground_metrics()

        self.assertIn(
            'polaris_playground_runs_total{protocol="openai_chat",outcome="succeeded"} 1',
            output,
        )
        self.assertIn('protocol="unknown",outcome="failed"', output)
        self.assertNotIn("untrusted/model", output)
        self.assertNotIn("secret", output)


if __name__ == "__main__":
    unittest.main()
