"""Native Meta event preservation must remain opt-in and fail closed."""

import json
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.extended_provider_runtime import stream_extended_request


class MetaNativeStreamTests(unittest.IsolatedAsyncioTestCase):
    def test_native_history_is_counted_once_and_not_canonically_pruned(self):
        from core.meta_native_boundary import seal_native_request, validate_native_request
        from core.token_compression import CompressionSettings, compress_gemini_request
        from core.token_estimator import estimate_input_tokens

        native = {"model": "muse-spark-1.3", "input": "context " * 200}
        canonical = {"contents": [{"role": "user", "parts": [{"text": native["input"]}]}]}
        sealed = seal_native_request(canonical, native)
        self.assertEqual(estimate_input_tokens(sealed), estimate_input_tokens(native))
        result = compress_gemini_request(
            sealed, CompressionSettings(enabled=True, threshold_tokens=256, target_tokens=128)
        )
        self.assertFalse(result.applied)
        self.assertEqual(result.reason, "native_reasoning_history")
        self.assertEqual(validate_native_request(result.request, "meta"), native)

    async def test_meta_skips_google_only_normalization_defaults(self):
        from core.converter.gemini_fix import normalize_gemini_request

        source = {
            "model": "muse-spark-1.3",
            "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
            "generationConfig": {"maxOutputTokens": 16},
        }
        self.assertEqual(await normalize_gemini_request(source, mode="primary"), source)

    async def run_events(self, events, native=True):
        wire = "".join("data: " + json.dumps(e) + "\n\n" for e in events).encode()

        @asynccontextmanager
        async def client(**kwargs):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _: httpx.Response(200, content=wire))
            ) as value:
                yield value

        with patch("core.extended_provider_runtime.http_client.get_streaming_client", client):
            return [
                json.loads(chunk[6:])
                async for chunk in stream_extended_request(
                    {"provider": "meta", "api_key": "fixture"},
                    "muse-spark-1.3",
                    url="https://api.meta.ai/v1/responses",
                    body={},
                    headers={},
                    timeout=30,
                    native_responses=native,
                )
            ]

    async def test_preserves_reasoning_phase_and_final_usage(self):
        item = {"type": "reasoning", "summary": [], "encrypted_content": "opaque"}
        response = {
            "id": "resp_fixture",
            "status": "completed",
            "output": [item],
            "usage": {"input_tokens": 10, "output_tokens": 3},
        }
        events = [
            {"type": "response.output_item.done", "item": item},
            {"type": "response.completed", "response": response},
        ]
        chunks = await self.run_events(events)
        self.assertEqual(chunks[0]["_polaris_meta_event"], events[0])
        self.assertEqual(chunks[-1]["_polaris_meta_event"], events[-1])
        self.assertEqual(chunks[-1]["usageMetadata"]["totalTokenCount"], 13)
        self.assertEqual(chunks[-1]["candidates"][0]["finishReason"], "STOP")

    async def test_normal_protocol_clients_do_not_receive_native_events(self):
        chunks = await self.run_events(
            [
                {"type": "response.output_text.delta", "delta": "hello"},
                {"type": "response.completed", "response": {"status": "completed"}},
            ],
            native=False,
        )
        self.assertTrue(all("_polaris_meta_event" not in c for c in chunks))

    async def test_malformed_tail_or_raw_reasoning_fails(self):
        for events in (
            [
                {"type": "response.completed", "response": {"status": "completed"}},
                {"type": "response.output_text.delta", "delta": "late"},
            ],
            [{"type": "response.reasoning_text.delta", "delta": "private"}],
            [{"type": "response.unknown", "secret": "untrusted"}],
        ):
            with self.subTest(events=events), self.assertRaises(ValueError):
                await self.run_events(events)

    async def test_output_limit_is_a_valid_incomplete_response(self):
        event = {
            "type": "response.incomplete",
            "response": {
                "status": "incomplete",
                "output": [],
                "incomplete_details": {"reason": "max_output_tokens"},
                "usage": {"input_tokens": 10, "output_tokens": 16},
            },
        }
        chunks = await self.run_events([event])
        self.assertEqual(chunks[-1]["_polaris_meta_event"], event)
        self.assertEqual(chunks[-1]["candidates"][0]["finishReason"], "MAX_TOKENS")
