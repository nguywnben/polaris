"""Fault handling for the opt-in anti-truncation continuation stream."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from starlette.responses import StreamingResponse

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.converter.anti_truncation import AntiTruncationStreamProcessor


class AntiTruncationStreamLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_failure_after_output_is_not_retried(self):
        calls = 0

        async def request(_payload):
            nonlocal calls
            calls += 1

            async def body():
                yield b'data: {"candidates":[{"content":{"parts":[{"text":"partial"}]}}]}\n\n'
                raise TimeoutError("upstream stalled")

            return StreamingResponse(body())

        processor = AntiTruncationStreamProcessor(
            request,
            {"model": "gemini-test", "request": {"contents": []}},
            max_attempts=3,
        )
        chunks = [chunk async for chunk in processor.process_stream()]

        self.assertEqual(calls, 1)
        self.assertIn(b'"code": 504', b"".join(chunks))


if __name__ == "__main__":
    unittest.main()
