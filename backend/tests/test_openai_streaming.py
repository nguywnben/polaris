"""Regression tests for OpenAI-compatible streaming responses."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.converter.openai_to_gemini import convert_gemini_to_openai_stream
from core.model_pool import ModelResolution
from core.models import OpenAIChatCompletionRequest, OpenAIResponsesRequest
from core.router.openai_stream_options import apply_stream_options
from core.router.primary import openai
from core.router.primary.responses import _responses_stream, responses_to_chat_request
from core.router.vertex import openai as vertex_openai

USAGE = {
    "promptTokenCount": 10,
    "candidatesTokenCount": 2,
    "thoughtsTokenCount": 3,
    "totalTokenCount": 15,
    "cachedContentTokenCount": 4,
}


class OpenAIStreamOptionsTests(unittest.IsolatedAsyncioTestCase):
    async def request_stream(
        self,
        options,
        *,
        fake=False,
        metadata_only=False,
        done=True,
        vertex=False,
        tool=False,
        anti=False,
        error=False,
    ):
        model = "fake-streaming/gemini-test" if fake else "gemini-test"
        if anti:
            model = "streaming-anti-truncation/gemini-test"
        body = {"model": model, "messages": [{"role": "user", "content": "hello"}], "stream": True}
        if options != "omitted":
            body["stream_options"] = options
        candidate = {
            "content": {"role": "model", "parts": [{"text": "OK"}]},
            "finishReason": "STOP",
        }
        if anti:
            candidate["content"]["parts"] = [{"text": "OK\n[done]"}]
        if tool:
            candidate["content"]["parts"] = [
                {"functionCall": {"name": "lookup", "args": {"city": "Hanoi"}, "id": "call-test"}}
            ]

        async def upstream(**kwargs):
            self.assertNotIn("stream_options", kwargs["body"]["request"])
            yield b": ping\n\n"
            yield (
                "data: "
                + json.dumps(
                    {
                        "candidates": [candidate],
                        **({} if metadata_only else {"usageMetadata": USAGE}),
                    }
                )
                + "\n\n"
            )
            if metadata_only:
                yield "data: " + json.dumps({"usageMetadata": USAGE}) + "\n\n"
            if error:
                yield b'data: {"error":{"message":"upstream failed","code":502}}\n\n'
            if done:
                yield b"data: [DONE]\n\n"

        resolution = ModelResolution(
            requested_model="gemini-test",
            response_model="gemini-test",
            candidates=("gemini-test",),
            is_virtual=False,
        )
        app = FastAPI()
        app.include_router(vertex_openai.router if vertex else openai.router)
        app.dependency_overrides[openai.authenticate_bearer] = lambda: "test"
        with (
            patch.object(openai, "resolve_model_request", AsyncMock(return_value=resolution)),
            patch("core.api.primary.stream_request", side_effect=upstream),
            patch("core.api.vertex.stream_request", side_effect=upstream),
            patch.object(openai, "get_anti_truncation_max_attempts", AsyncMock(return_value=2)),
            patch(
                "core.api.primary.non_stream_request",
                AsyncMock(
                    return_value=JSONResponse({"candidates": [candidate], "usageMetadata": USAGE})
                ),
            ),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                path = "/vertex/v1/chat/completions" if vertex else "/v1/chat/completions"
                response = await client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        frames = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual(frames[-1], "[DONE]")
        self.assertEqual(frames.count("[DONE]"), 1)
        return [json.loads(frame) for frame in frames[:-1]]

    async def test_include_usage_emits_one_final_empty_choices_chunk(self):
        for fake, metadata_only, done in (
            (False, False, True),
            (False, True, True),
            (False, True, False),
            (True, False, True),
        ):
            with self.subTest(fake=fake, metadata_only=metadata_only, done=done):
                chunks = await self.request_stream(
                    {"include_usage": True}, fake=fake, metadata_only=metadata_only, done=done
                )
                self.assertEqual(chunks[-1]["choices"], [])
                self.assertEqual(
                    chunks[-1]["usage"],
                    {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                        "prompt_tokens_details": {"cached_tokens": 4},
                        "completion_tokens_details": {"reasoning_tokens": 3},
                    },
                )
                self.assertTrue(all(c["usage"] is None for c in chunks[:-1]))
                self.assertEqual(chunks[-1]["id"], chunks[0]["id"])
                self.assertIn("OK", str(chunks[:-1]))

    async def test_usage_not_requested_is_not_emitted(self):
        for options in ("omitted", None, {}, {"include_usage": False}):
            with self.subTest(options=options):
                chunks = await self.request_stream(options, metadata_only=True)
                self.assertTrue(all("usage" not in c for c in chunks))
                self.assertTrue(all(c["choices"] for c in chunks))

    async def test_vertex_and_anti_truncation_honor_usage_options(self):
        for mode in ({"vertex": True}, {"anti": True}):
            with self.subTest(mode=mode):
                chunks = await self.request_stream({"include_usage": True}, **mode)
                self.assertEqual(chunks[-1]["choices"], [])
                self.assertEqual(chunks[-1]["usage"]["total_tokens"], 15)

    async def test_tool_call_is_preserved_before_usage(self):
        chunks = await self.request_stream({"include_usage": True}, tool=True)
        choice = chunks[0]["choices"][0]
        self.assertEqual(choice["finish_reason"], "tool_calls")
        self.assertEqual(choice["delta"]["tool_calls"][0]["function"]["name"], "lookup")
        self.assertEqual(chunks[-1]["choices"], [])

    async def test_route_error_after_usage_does_not_emit_successful_usage(self):
        for mode in ({}, {"vertex": True}, {"anti": True}):
            with self.subTest(mode=mode):
                chunks = await self.request_stream({"include_usage": True}, error=True, **mode)
                self.assertEqual(chunks[-1]["error"]["message"], "upstream failed")
                self.assertFalse(any(c.get("usage") for c in chunks))

    async def test_responses_adapter_consumes_final_usage_chunk(self):
        from fastapi.responses import StreamingResponse

        async def source():
            yield b'data: {"choices":[{"delta":{"content":"OK"}}],"usage":null}\n\n'
            yield b'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}\n\n'
            yield b"data: [DONE]\n\n"

        request = OpenAIResponsesRequest(model="gemini-test", input="Hello", stream=True)
        data = b"".join([c async for c in _responses_stream(StreamingResponse(source()), request)])
        events = [
            json.loads(line[6:])
            for line in data.decode().splitlines()
            if line.startswith("data: {")
        ]
        self.assertEqual(events[-1]["type"], "response.completed")
        self.assertEqual(events[-1]["response"]["usage"]["total_tokens"], 15)

    async def test_anti_truncation_sums_attempts_not_cumulative_chunks(self):
        attempts = 0

        async def upstream(**kwargs):
            nonlocal attempts
            attempts += 1
            for text in ("partial", "[done]" if attempts == 2 else "continue"):
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "candidates": [
                                {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
                            ],
                            "usageMetadata": USAGE,
                        }
                    )
                    + "\n\n"
                )
            yield b"data: [DONE]\n\n"

        resolution = ModelResolution(
            requested_model="gemini-test",
            response_model="gemini-test",
            candidates=("gemini-test",),
            is_virtual=False,
        )
        request = OpenAIChatCompletionRequest(
            model="streaming-anti-truncation/gemini-test",
            messages=[{"role": "user", "content": "Hello"}],
            stream=True,
            stream_options={"include_usage": True},
        )
        with (
            patch.object(openai, "resolve_model_request", AsyncMock(return_value=resolution)),
            patch.object(openai, "get_anti_truncation_max_attempts", AsyncMock(return_value=2)),
            patch("core.api.primary.stream_request", side_effect=upstream),
        ):
            response = await openai.chat_completions(request, token="test")
            data = b"".join([c async for c in response.body_iterator])
        chunks = [
            json.loads(line[6:])
            for line in data.decode().splitlines()
            if line.startswith("data: {")
        ]
        self.assertEqual(attempts, 2)
        self.assertEqual(chunks[-1]["usage"]["total_tokens"], 30)
        self.assertEqual(chunks[-1]["usage"]["completion_tokens_details"]["reasoning_tokens"], 6)

    async def test_usage_wrapper_does_not_fabricate_usage_and_preserves_errors(self):
        for error in (False, True):

            async def source():
                yield b'data: {"id":"x","object":"chat.completion.chunk","created":1,"model":"test","choices":[{"delta":{"content":"OK"},"finish_reason":null}]}\n\n'
                if error:
                    yield b'data: {"error":{"message":"upstream failed"}}\n\n'
                yield b"data: [DONE]\n\n"

            data = b"".join([c async for c in apply_stream_options(source(), include_usage=True)])
            self.assertNotIn(b'"choices": []', data)
            self.assertEqual(b"upstream failed" in data, error)

    async def test_usage_wrapper_closes_on_disconnect(self):
        closed = False

        async def source():
            nonlocal closed
            try:
                yield b": ping\n\n"
                yield b"data: [DONE]\n\n"
            finally:
                closed = True

        stream = apply_stream_options(source(), include_usage=True)
        self.assertEqual(await anext(stream), b": ping\n\n")
        await stream.aclose()
        self.assertTrue(closed)

    async def test_separate_tool_call_and_stop_frames_keep_tool_calls_finish_reason(self):
        async def source():
            for choice in (
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "function": {"name": "lookup", "arguments": "{}"}}
                        ]
                    },
                    "finish_reason": None,
                },
                {"index": 0, "delta": {}, "finish_reason": "stop"},
            ):
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "id": "test",
                            "object": "chat.completion.chunk",
                            "created": 1,
                            "model": "test",
                            "choices": [choice],
                        }
                    )
                    + "\n\n"
                )
            yield b"data: [DONE]\n\n"

        chunks = [c async for c in apply_stream_options(source(), include_usage=True)]
        self.assertEqual(json.loads(chunks[-2][6:])["choices"][0]["finish_reason"], "tool_calls")

    def test_invalid_options_still_fail_closed(self):
        for options in (
            [],
            "yes",
            {"include_usage": "true"},
            {"include_usage": 1},
            {"unknown": True},
        ):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                OpenAIChatCompletionRequest(
                    model="test", messages=[], stream=True, stream_options=options
                )

    def test_non_streaming_rejects_non_null_stream_options(self):
        with self.assertRaises(ValidationError):
            OpenAIChatCompletionRequest(
                model="test", messages=[], stream_options={"include_usage": True}
            )

    def test_responses_adapter_requests_usage_for_streaming(self):
        request = responses_to_chat_request(
            OpenAIResponsesRequest(model="test", input="Hello", stream=True)
        )
        self.assertTrue(request.stream_options.include_usage)


def convert_chunk(candidate: dict) -> dict:
    source = {
        "response": {
            "candidates": [candidate],
        }
    }
    converted = convert_gemini_to_openai_stream(
        f"data: {json.dumps(source)}",
        "gemini-2.5-flash",
        "response-id",
    )
    if converted is None:
        raise AssertionError("Expected an OpenAI stream chunk.")
    return json.loads(converted.removeprefix("data: ").strip())


class OpenAIStreamingTests(unittest.TestCase):
    def test_intermediate_chunk_does_not_end_the_stream(self):
        chunk = convert_chunk(
            {
                "index": 0,
                "content": {
                    "role": "model",
                    "parts": [{"text": "I am"}],
                },
            }
        )

        choice = chunk["choices"][0]
        self.assertEqual(choice["delta"]["content"], "I am")
        self.assertIsNone(choice["finish_reason"])

    def test_stop_reason_is_only_emitted_by_the_final_chunk(self):
        chunk = convert_chunk(
            {
                "index": 0,
                "content": {
                    "role": "model",
                    "parts": [{"text": " complete."}],
                },
                "finishReason": "STOP",
            }
        )

        self.assertEqual(chunk["choices"][0]["finish_reason"], "stop")

    def test_token_limit_maps_to_openai_length_reason(self):
        chunk = convert_chunk(
            {
                "index": 0,
                "content": {"role": "model", "parts": []},
                "finishReason": "MAX_TOKENS",
            }
        )

        self.assertEqual(chunk["choices"][0]["finish_reason"], "length")


if __name__ == "__main__":
    unittest.main()
