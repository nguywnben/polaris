"""Regression tests for bounded stream-collector observability."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import Response

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.api.utils import collect_streaming_response


class StreamCollectorLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_collector_closes_source_after_prefetched_error(self) -> None:
        closed = False

        async def stream():
            nonlocal closed
            try:
                yield Response(status_code=502)
            finally:
                closed = True

        response = await collect_streaming_response(stream())

        self.assertEqual(response.status_code, 502)
        self.assertTrue(closed)

    async def test_collector_rejects_output_above_memory_limit(self) -> None:
        async def stream():
            yield 'data: {"candidates":[{"content":{"parts":[{"text":"too large"}]}}]}'

        with patch("core.api.utils.MAX_COLLECTED_STREAM_BYTES", 16):
            response = await collect_streaming_response(stream())

        self.assertEqual(response.status_code, 502)

    async def test_done_marker_still_drains_upstream_cleanup(self) -> None:
        completed = False

        async def stream():
            nonlocal completed
            yield 'data: {"response":{"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}}'
            yield "data: [DONE]"
            completed = True

        response = await collect_streaming_response(stream())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(completed)

    async def test_success_summary_is_debug_not_per_request_info(self) -> None:
        async def stream():
            yield (
                'data: {"response":{"candidates":[{"content":{"parts":'
                '[{"text":"ok"}]},"finishReason":"STOP"}]}}'
            )

        summary = (
            "[STREAM COLLECTOR] Collected 1 text chunks, 0 thought chunks, "
            "0 other parts (tool parts: 0)"
        )
        with (
            patch("core.api.utils.log.debug") as debug,
            patch("core.api.utils.log.info") as info,
        ):
            response = await collect_streaming_response(stream())

        self.assertEqual(response.status_code, 200)
        debug.assert_any_call(summary)
        info.assert_not_called()


if __name__ == "__main__":
    unittest.main()
