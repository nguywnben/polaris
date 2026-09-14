"""Contract tests for OpenAI Responses API compatibility."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.responses import StreamingResponse

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.httpx_client import UpstreamStreamProtocolError
from core.models import OpenAIResponsesRequest
from core.router.primary.responses import (
    _iter_chat_events,
    _responses_stream,
    chat_to_responses_response,
    create_response,
    responses_to_chat_request,
)


class OpenAIResponsesTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_parser_rejects_an_unbounded_partial_frame(self):
        async def chunks():
            yield b"x" * 17

        with (
            patch("core.router.primary.responses._MAX_SSE_FRAME_BYTES", 16),
            self.assertRaisesRegex(UpstreamStreamProtocolError, "exceeds"),
        ):
            _ = [event async for event in _iter_chat_events(chunks())]

    async def test_responses_stream_forwards_heartbeat_and_closes_chat_body(self):
        closed = False

        async def chunks():
            nonlocal closed
            try:
                yield b": upstream-ping\n\n"
                yield b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
            finally:
                closed = True

        request = OpenAIResponsesRequest(model="gemini-test", input="hello", stream=True)
        stream = _responses_stream(StreamingResponse(chunks()), request)
        emitted = [await anext(stream) for _ in range(4)]
        await stream.aclose()

        self.assertTrue(emitted[-1].startswith(b":"))
        self.assertTrue(closed)

    async def test_responses_stream_emits_error_when_chat_stream_has_no_done(self):
        async def chunks():
            yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'

        request = OpenAIResponsesRequest(model="gemini-test", input="hello", stream=True)
        stream = _responses_stream(StreamingResponse(chunks()), request)
        payload = b"".join([chunk async for chunk in stream])

        self.assertIn(b"event: error", payload)
        self.assertNotIn(b"event: response.completed", payload)

    async def test_responses_stream_caps_accumulated_final_output(self):
        async def chunks():
            yield b'data: {"choices":[{"delta":{"content":"12345"}}]}\n\n'
            yield b'data: {"choices":[{"delta":{"content":"67890"}}]}\n\n'
            yield b"data: [DONE]\n\n"

        request = OpenAIResponsesRequest(model="gemini-test", input="hello", stream=True)
        with patch("core.router.primary.responses._MAX_RESPONSES_OUTPUT_BYTES", 8):
            payload = b"".join(
                [chunk async for chunk in _responses_stream(StreamingResponse(chunks()), request)]
            )

        self.assertIn(b"event: error", payload)
        self.assertNotIn(b"event: response.completed", payload)

    def test_string_input_and_instructions_translate_to_chat_messages(self):
        request = OpenAIResponsesRequest(
            model="gemini-2.5-flash",
            instructions="Be concise.",
            input="Hello",
            max_output_tokens=100,
        )

        chat = responses_to_chat_request(request)

        self.assertEqual(chat.messages[0].role, "system")
        self.assertEqual(chat.messages[1].role, "user")
        self.assertEqual(chat.max_tokens, 100)

    def test_chat_completion_translates_to_response_output_and_usage(self):
        request = OpenAIResponsesRequest(model="gemini-2.5-flash", input="Hello")
        chat = {
            "id": "chatcmpl-123",
            "created": 100,
            "choices": [{"message": {"role": "assistant", "content": "Hi"}}],
            "usage": {
                "prompt_tokens": 4,
                "completion_tokens": 2,
                "total_tokens": 6,
            },
        }

        response = chat_to_responses_response(chat, request)

        self.assertEqual(response["object"], "response")
        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["output"][0]["content"][0]["text"], "Hi")
        self.assertEqual(response["usage"]["input_tokens"], 4)
        self.assertEqual(response["usage"]["output_tokens"], 2)

    async def test_chat_sse_parser_handles_frames_split_across_chunks(self):
        async def chunks():
            yield b'data: {"choices":[{"delta":{"content":"Hel'
            yield b'lo"}}]}\n\ndata: [DONE]\n\n'

        events = [event async for event in _iter_chat_events(chunks())]

        self.assertEqual(events[0]["choices"][0]["delta"]["content"], "Hello")

    def test_non_function_tools_fail_explicitly(self):
        request = OpenAIResponsesRequest(
            model="gemini-2.5-flash",
            input="Search",
            tools=[{"type": "web_search"}],
        )

        with self.assertRaisesRegex(Exception, "Only function tools"):
            responses_to_chat_request(request)

    def test_function_call_history_translates_to_assistant_and_tool_messages(self):
        request = OpenAIResponsesRequest(
            model="gemini-2.5-flash",
            input=[
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "lookup",
                    "arguments": '{"id":1}',
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "found",
                },
            ],
        )

        chat = responses_to_chat_request(request)

        self.assertEqual(chat.messages[0].role, "assistant")
        self.assertEqual(chat.messages[0].tool_calls[0].id, "call_1")
        self.assertEqual(chat.messages[1].role, "tool")

    async def test_store_true_is_rejected_instead_of_claiming_persistence(self):
        request = OpenAIResponsesRequest(
            model="gemini-2.5-flash",
            input="Hello",
            store=True,
        )

        with self.assertRaisesRegex(Exception, "Stored responses"):
            await create_response(request, token="test")


if __name__ == "__main__":
    unittest.main()
