"""Native Responses ingress retains Meta history within the managed pipeline."""

import json
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, Header, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.meta_responses_models import MetaResponsesRequest
from core.router.primary.meta_responses import create_meta_response, native_request_to_gemini
from fastapi.responses import JSONResponse
from pydantic import ValidationError


class MetaResponsesSchemaTests(unittest.TestCase):
    def test_malformed_nested_types_produce_validation_errors_not_exceptions(self):
        for extra in (
            {"reasoning": {"effort": []}},
            {"reasoning": {"summary": {}}},
            {"text": {"format": {"type": []}}},
            {"input": [{"role": [], "content": "hi"}]},
            {"input": [{"role": "assistant", "phase": [], "content": "hi"}]},
            {"input": [{"role": "user", "content": [{"type": [], "text": "hi"}]}]},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                MetaResponsesRequest.model_validate({"model": "alias", "input": "hi", **extra})

    def test_rejects_unsupported_state_and_nested_fields(self):
        for extra in (
            {"store": True},
            {"previous_response_id": "resp_1"},
            {"background": True},
            {"reasoning": {"effort": "none"}},
            {"input": [{"role": "user", "content": "hi", "unknown": 1}]},
            {"max_output_tokens": 15},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                MetaResponsesRequest.model_validate({"model": "alias", "input": "hi", **extra})

    def test_accepts_encrypted_history_phase_and_tool_pairs(self):
        request = MetaResponsesRequest.model_validate(
            {
                "model": "alias",
                "reasoning": {"effort": "high", "summary": "auto"},
                "include": ["reasoning.encrypted_content"],
                "input": [
                    {
                        "type": "reasoning",
                        "id": "rs_1",
                        "summary": [{"type": "summary_text", "text": "Inspect files"}],
                        "encrypted_content": "opaque",
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "phase": "commentary",
                        "content": "Checking",
                    },
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "read",
                        "arguments": "{}",
                    },
                    {"type": "function_call_output", "call_id": "call_1", "output": "contents"},
                ],
            }
        )
        self.assertEqual(request.input[0]["encrypted_content"], "opaque")

    def test_rejects_orphan_tool_output_and_reasoning_without_summary(self):
        for item in (
            {"type": "function_call_output", "call_id": "absent", "output": "x"},
            {"type": "reasoning", "encrypted_content": "opaque"},
        ):
            with self.subTest(item=item), self.assertRaises(ValidationError):
                MetaResponsesRequest(model="alias", input=[item])

    def test_image_understanding_accepts_https_and_inline_but_not_local_fetches(self):
        for url in ("https://example.com/photo.png", "data:image/png;base64,aGVsbG8="):
            request = MetaResponsesRequest(
                model="alias",
                input=[
                    {
                        "role": "user",
                        "content": [{"type": "input_image", "image_url": url, "detail": "auto"}],
                    }
                ],
            )
            self.assertEqual(request.input[0]["content"][0]["image_url"], url)
        for url in ("file:///etc/passwd", "http://127.0.0.1/x", "https://user:pass@example.com/x"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                MetaResponsesRequest(
                    model="alias",
                    input=[
                        {"role": "user", "content": [{"type": "input_image", "image_url": url}]}
                    ],
                )

    def test_max_effort_is_not_permitted_for_contributor_models(self):
        with self.assertRaises(ValidationError):
            MetaResponsesRequest(
                model="muse-spark-1.3-contributor", input="hi", reasoning={"effort": "max"}
            )


class MetaResponsesAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_primary_prepare_transport_and_accounting_complete(self):
        from core.api import primary
        from core.extended_provider_runtime import http_client

        from backend.tests.test_extended_provider_runtime import PrimaryExtendedIntegrationTests

        real_prepare = primary.prepare_provider_request
        stack, _ = PrimaryExtendedIntegrationTests().fixtures(
            [("muse-spark-1.3", "meta.json", {"provider": "meta", "api_key": "fixture-meta-key"})]
        )
        sent = []
        terminal = {
            "type": "response.completed",
            "response": {
                "id": "resp_fixture",
                "status": "completed",
                "model": "muse-spark-1.3",
                "output": [],
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            },
        }

        def handler(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200, content=("data: " + json.dumps(terminal) + "\n\n").encode())

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
            patch.object(
                primary, "apply_pre_call_guardrails", AsyncMock(side_effect=policy)
            ) as guard,
            patch.object(http_client, "get_streaming_client", client),
        ):
            response = await create_meta_response(
                MetaResponsesRequest(model="polaris", input="hi"),
                "fixture",
                resolution=SimpleNamespace(
                    candidates=["muse-spark-1.3"], response_model="polaris", is_virtual=True
                ),
            )
            self.assertEqual(response.status_code, 200, response.body)
            primary.record_api_call_success.assert_awaited_once()
            usage = primary.record_api_call_success.await_args.kwargs["token_usage"]
            self.assertEqual(usage["input_tokens"], 3)
            self.assertEqual(usage["output_tokens"], 2)
            # The fixture stubs the success recorder, which normally releases the
            # credential via record_api_call_result; cancellation is tested separately.
            guard.assert_awaited_once()
        self.assertEqual(sent[0]["input"], "hi")
        self.assertFalse(sent[0]["store"])
        self.assertEqual(json.loads(response.body)["model"], "polaris")

    async def test_mirror_accounts_for_instructions_tools_results_and_summary(self):
        request = MetaResponsesRequest(
            model="alias",
            instructions="Policy",
            input=[
                {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "Thought"}],
                    "encrypted_content": "opaque-secret",
                },
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "read",
                    "arguments": '{"path":"a"}',
                },
                {"type": "function_call_output", "call_id": "call_1", "output": "Result"},
            ],
            tools=[
                {
                    "type": "function",
                    "name": "read",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                }
            ],
        )
        mirror = await native_request_to_gemini(request)
        serialized = json.dumps(mirror)
        for value in ("Policy", "Thought", "Result", "Read a file", "path"):
            self.assertIn(value, serialized)
        self.assertNotIn("opaque-secret", serialized)

    async def test_nonstream_retains_native_output_and_alias_through_managed_stream(self):
        observed = {}
        closed = False
        accounted = False
        terminal = {
            "type": "response.completed",
            "response": {
                "id": "resp_1",
                "status": "completed",
                "model": "muse-spark-1.3",
                "output": [{"type": "reasoning", "encrypted_content": "opaque"}],
                "usage": {"input_tokens": 3, "output_tokens": 2},
            },
        }

        async def upstream(**kwargs):
            nonlocal closed, accounted
            observed.update(kwargs)
            try:
                yield ("data: " + json.dumps({"_polaris_meta_event": terminal}) + "\n\n").encode()
                accounted = True
            finally:
                closed = True

        with patch("core.api.primary.stream_request", upstream):
            response = await create_meta_response(
                MetaResponsesRequest(model="alias", input="hi"),
                "token",
                resolution=SimpleNamespace(
                    candidates=["muse-spark-1.3"], response_model="alias", is_virtual=True
                ),
            )
        payload = json.loads(response.body)
        self.assertEqual(payload["model"], "alias")
        self.assertEqual(payload["output"][0]["encrypted_content"], "opaque")
        self.assertTrue(closed)
        self.assertTrue(accounted)
        self.assertFalse(observed["native"])
        self.assertTrue(observed["model_routing"])
        self.assertIn("_polaris_meta_responses", observed["body"]["request"])
        from core.meta_native_boundary import validate_native_request

        self.assertEqual(
            validate_native_request(observed["body"]["request"], "meta")["input"], "hi"
        )

    async def test_stream_disconnect_closes_upstream_without_reading_ahead(self):
        closed = False
        consumed = 0

        async def upstream(**kwargs):
            nonlocal closed, consumed
            try:
                for index in range(3):
                    consumed += 1
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "_polaris_meta_event": {
                                    "type": "response.output_text.delta",
                                    "delta": str(index),
                                }
                            }
                        )
                        + "\n\n"
                    ).encode()
            finally:
                closed = True

        with patch("core.api.primary.stream_request", upstream):
            response = await create_meta_response(
                MetaResponsesRequest(model="alias", input="hi", stream=True),
                "token",
                resolution=SimpleNamespace(
                    candidates=["muse-spark-1.3"], response_model="alias", is_virtual=False
                ),
            )
            first = await anext(response.body_iterator)
            await response.body_iterator.aclose()
        self.assertIn(b"response.output_text.delta", first)
        self.assertEqual(consumed, 1)
        self.assertTrue(closed)

    async def test_upstream_http_failure_is_sanitized_before_committing_stream(self):
        async def upstream(**kwargs):
            yield JSONResponse({"error": "secret credential material"}, status_code=401)

        with patch("core.api.primary.stream_request", upstream):
            response = await create_meta_response(
                MetaResponsesRequest(model="alias", input="hi", stream=True),
                "token",
                resolution=SimpleNamespace(
                    candidates=["muse-spark-1.3"], response_model="alias", is_virtual=False
                ),
            )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(b"secret credential", response.body)

    async def test_missing_native_marker_fails_closed(self):
        async def upstream(**kwargs):
            yield b'data: {"candidates": [{"text": "not native"}]}\n\n'

        with patch("core.api.primary.stream_request", upstream):
            response = await create_meta_response(
                MetaResponsesRequest(model="alias", input="hi"),
                "token",
                resolution=SimpleNamespace(
                    candidates=["muse-spark-1.3"], response_model="alias", is_virtual=False
                ),
            )
        self.assertEqual(response.status_code, 502)
        self.assertNotIn(b"not native", response.body)


class MetaResponsesHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def _post(self, payload, candidates, *, authenticated=True):
        from core.router.primary.responses import router
        from core.utils import authenticate_bearer

        app = FastAPI()
        app.include_router(router)
        called = []

        async def fixture_auth(authorization: str | None = Header(default=None)):
            if authorization != "Bearer fixture":
                raise HTTPException(status_code=401)
            return "fixture"

        app.dependency_overrides[authenticate_bearer] = fixture_auth

        async def upstream(**kwargs):
            called.append(kwargs)
            for event in (
                {"type": "response.output_text.delta", "delta": "Hello"},
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_fixture",
                        "status": "completed",
                        "model": candidates[0],
                        "output": [],
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    },
                },
            ):
                yield ("data: " + json.dumps({"_polaris_meta_event": event}) + "\n\n").encode()

        resolution = SimpleNamespace(
            candidates=candidates,
            response_model=payload["model"],
            is_virtual=payload["model"] == "polaris",
        )
        with (
            patch("core.router.primary.responses.resolve_model_request", return_value=resolution),
            patch("core.api.primary.stream_request", upstream),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/responses",
                    json=payload,
                    headers={"Authorization": "Bearer fixture"} if authenticated else {},
                )
        return response, called

    async def test_explicit_muse_reasoning_and_tools_stream_native_events(self):
        response, calls = await self._post(
            {
                "model": "muse-spark-1.3",
                "input": "hi",
                "stream": True,
                "reasoning": {"effort": "high", "summary": "auto"},
                "include": ["reasoning.encrypted_content"],
                "tools": [{"type": "function", "name": "read", "parameters": {"type": "object"}}],
            },
            ["muse-spark-1.3"],
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("event: response.output_text.delta", response.text)
        self.assertIn("event: response.completed", response.text)
        self.assertEqual(len(calls), 1)

    async def test_legacy_shaped_muse_first_turn_uses_native_tool_stream(self):
        response, calls = await self._post(
            {
                "model": "muse-spark-1.3",
                "input": "hi",
                "stream": True,
                "tools": [{"type": "function", "name": "read", "parameters": {"type": "object"}}],
            },
            ["muse-spark-1.3"],
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("_polaris_meta_responses", calls[0]["body"]["request"])

    async def test_polaris_alias_with_only_meta_candidates_uses_native(self):
        response, calls = await self._post(
            {"model": "polaris", "input": "hi"}, ["muse-spark-1.3", "muse-spark-1.2"]
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["model"], "polaris")
        self.assertTrue(calls[0]["model_routing"])

    async def test_native_options_fail_for_mixed_and_non_meta_routes(self):
        for candidates in (["muse-spark-1.3", "other"], ["other"]):
            response, calls = await self._post(
                {"model": "polaris", "input": "hi", "reasoning": {"effort": "high"}}, candidates
            )
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(calls, [])

    async def test_authentication_failure_never_starts_upstream(self):
        response, calls = await self._post(
            {"model": "muse-spark-1.3", "input": "hi"}, ["muse-spark-1.3"], authenticated=False
        )
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(calls, [])


class MetaMessagesHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def _post(self, extra=None):
        from core.meta_model_api import prepare_request
        from core.router.primary.anthropic import router
        from core.utils import authenticate_bearer

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[authenticate_bearer] = lambda: "fixture"
        prepared = []

        async def upstream(*, body, **kwargs):
            _, _, native = prepare_request(
                {"provider": "meta", "api_key": "fixture-key"},
                body["request"],
                body["model"],
                False,
            )
            prepared.append(native)
            return JSONResponse(
                {
                    "candidates": [
                        {
                            "content": {"role": "model", "parts": [{"text": "Hello"}]},
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 2,
                        "candidatesTokenCount": 1,
                        "totalTokenCount": 3,
                    },
                }
            )

        payload = {
            "model": "muse-spark-1.3",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": "Hi"}],
            **(extra or {}),
        }
        resolution = SimpleNamespace(
            candidates=[payload["model"]], response_model=payload["model"], is_virtual=False
        )
        with (
            patch("core.router.primary.anthropic.resolve_model_request", return_value=resolution),
            patch("core.api.primary.non_stream_request", side_effect=upstream) as request,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                response = await client.post("/v1/messages", json=payload)
        return response, prepared, request.await_count

    async def test_default_messages_reach_meta_without_synthetic_generation_options(self):
        response, prepared, count = await self._post()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(count, 1)
        self.assertFalse(prepared[0]["store"])
        self.assertNotIn("temperature", prepared[0])
        self.assertNotIn("stop", prepared[0])
        self.assertEqual(prepared[0]["input"][0]["content"][0]["text"], "Hi")

    async def test_messages_tool_history_reaches_meta_without_synthetic_signatures(self):
        response, prepared, count = await self._post(
            {
                "tools": [{"name": "read", "input_schema": {"type": "object", "properties": {}}}],
                "messages": [
                    {"role": "user", "content": "Read"},
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "tool_use", "id": "call_1", "name": "read", "input": {}}
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": "call_1", "content": "File text"}
                        ],
                    },
                ],
            }
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(count, 1)
        self.assertEqual(
            [item["type"] for item in prepared[0]["input"]][-2:],
            ["function_call", "function_call_output"],
        )
        self.assertEqual(prepared[0]["input"][-1]["call_id"], "call_1")

    async def test_unsupported_messages_options_are_safe_400_before_upstream(self):
        for extra in (
            {"thinking": {"type": "enabled", "budget_tokens": 1024}},
            {"stop_sequences": ["private-sentinel"]},
        ):
            with self.subTest(extra=extra):
                response, prepared, count = await self._post(extra)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(count, 0)
                self.assertEqual(prepared, [])
                self.assertNotIn("private-sentinel", response.text)


if __name__ == "__main__":
    unittest.main()
