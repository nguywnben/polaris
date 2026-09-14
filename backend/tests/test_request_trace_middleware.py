"""HTTP lifecycle correlation tests for durable request traces."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.request_trace_service import trace_decision
from main import add_security_headers


def _request(path: str, *, request_id="request-123") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "headers": [(b"x-request-id", request_id.encode())],
            "client": ("127.0.0.1", 50000),
            "server": ("localhost", 4283),
        }
    )


class RequestTraceMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_inference_audit_and_trace_persist_concurrently(self):
        trace_started = asyncio.Event()
        audit_started = asyncio.Event()
        release = asyncio.Event()

        async def record_trace(_trace):
            trace_started.set()
            await release.wait()

        async def record_audit(**_fields):
            audit_started.set()
            await release.wait()

        trace_service = Mock(record=AsyncMock(side_effect=record_trace))
        audit_service = Mock(record_inference=AsyncMock(side_effect=record_audit))

        async def next_handler(_request):
            return JSONResponse({"ok": True})

        with (
            patch("main.get_request_trace_service", return_value=trace_service),
            patch("main.get_audit_service", return_value=audit_service),
        ):
            task = asyncio.create_task(
                add_security_headers(_request("/v1/chat/completions"), next_handler)
            )
            try:
                await asyncio.wait_for(
                    asyncio.gather(trace_started.wait(), audit_started.wait()),
                    timeout=0.25,
                )
            finally:
                release.set()
                await task

    async def test_cancellation_before_response_persists_one_cancelled_trace(self):
        service = Mock(record=AsyncMock())

        async def next_handler(_request):
            raise asyncio.CancelledError()

        with patch("main.get_request_trace_service", return_value=service):
            with self.assertRaises(asyncio.CancelledError):
                await add_security_headers(_request("/v1/chat/completions"), next_handler)

        service.record.assert_awaited_once()
        self.assertEqual(service.record.await_args.args[0].outcome, "cancelled")

    async def test_supported_success_and_failure_share_public_request_id(self):
        for status_code, expected in ((200, "succeeded"), (502, "upstream_error")):
            with self.subTest(status_code=status_code):
                service = Mock(record=AsyncMock())

                async def next_handler(_request):
                    return JSONResponse({"ok": status_code == 200}, status_code=status_code)

                with patch("main.get_request_trace_service", return_value=service):
                    response = await add_security_headers(
                        _request("/v1/chat/completions"), next_handler
                    )

                trace = service.record.await_args.args[0]
                self.assertEqual(trace.request_id, response.headers["x-request-id"])
                self.assertEqual(trace.protocol, "openai_chat")
                self.assertEqual(trace.outcome, expected)
                self.assertEqual(trace.status_code, status_code)

    async def test_stream_trace_is_persisted_only_after_body_finishes(self):
        service = Mock(record=AsyncMock())

        async def body():
            yield b"one"
            yield b"two"

        async def next_handler(_request):
            return StreamingResponse(body(), status_code=200)

        with patch("main.get_request_trace_service", return_value=service):
            response = await add_security_headers(
                _request("/v1beta/models/gemini:streamGenerateContent"), next_handler
            )
            self.assertEqual(service.record.await_count, 0)
            chunks = [chunk async for chunk in response.body_iterator]
            service.record.assert_not_awaited()
            self.assertIsNotNone(response.background)
            await response.background()

        self.assertEqual(chunks, [b"one", b"two"])
        service.record.assert_awaited_once()
        self.assertEqual(service.record.await_args.args[0].protocol, "gemini_stream")

    async def test_cancelled_stream_persists_one_cancelled_trace(self):
        service = Mock(record=AsyncMock())

        async def body():
            yield b"one"
            yield b"two"

        async def next_handler(_request):
            return StreamingResponse(body(), status_code=200)

        with patch("main.get_request_trace_service", return_value=service):
            response = await add_security_headers(_request("/v1/chat/completions"), next_handler)
            self.assertEqual(await anext(response.body_iterator), b"one")
            await response.body_iterator.aclose()

        service.record.assert_awaited_once()
        self.assertEqual(service.record.await_args.args[0].outcome, "cancelled")

    async def test_in_stream_upstream_failure_overrides_http_200_outcome(self):
        service = Mock(record=AsyncMock())

        async def body():
            trace_decision(
                category="upstream",
                action="failed",
                result="failed",
                reason="provider_error",
                status_code=502,
            )
            yield b"error event"

        async def next_handler(_request):
            return StreamingResponse(body(), status_code=200)

        with patch("main.get_request_trace_service", return_value=service):
            response = await add_security_headers(_request("/v1/messages"), next_handler)
            _ = [chunk async for chunk in response.body_iterator]
            service.record.assert_not_awaited()
            self.assertIsNotNone(response.background)
            await response.background()

        service.record.assert_awaited_once()
        self.assertEqual(service.record.await_args.args[0].outcome, "upstream_error")

    async def test_management_requests_are_not_written_to_trace_repository(self):
        service = Mock(record=AsyncMock())

        async def next_handler(_request):
            return JSONResponse({"ok": True})

        with (
            patch("main.get_request_trace_service", return_value=service),
            patch("main.record_classified_management_response", AsyncMock()),
        ):
            await add_security_headers(_request("/api/config/save"), next_handler)

        service.record.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
