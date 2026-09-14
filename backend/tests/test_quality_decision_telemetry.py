"""Tests for bounded, prompt-free AI quality decision telemetry."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from core.api.utils import _generation_trace_metadata, _schedule_trace_export
from core.quality_decision import normalize_quality_decision


class QualityDecisionTelemetryTests(unittest.TestCase):
    def test_unknown_values_are_rejected_instead_of_persisting_untrusted_text(self):
        decision = normalize_quality_decision(
            {
                "quality_profile": "secret-profile-name",
                "quality_policy_revision": "not-an-integer",
                "compression_reason": "prompt-content-must-not-be-stored",
            }
        )

        self.assertEqual(
            decision,
            {
                "quality_profile": "unavailable",
                "quality_policy_revision": 0,
                "compression_reason": "unknown",
            },
        )

    def test_unhashable_values_are_safely_normalized(self):
        decision = normalize_quality_decision(
            {
                "quality_profile": ["balanced"],
                "compression_reason": {"reason": "disabled"},
            }
        )

        self.assertEqual(decision["quality_profile"], "unavailable")
        self.assertEqual(decision["compression_reason"], "unknown")

    def test_fail_open_compression_reasons_are_allowlisted(self):
        for reason in ("estimation_failed", "invariant_failed"):
            with self.subTest(reason=reason):
                decision = normalize_quality_decision(
                    {
                        "quality_profile": "balanced",
                        "compression_reason": reason,
                    }
                )

                self.assertEqual(decision["compression_reason"], reason)

    def test_generation_trace_metadata_is_allowlisted_and_prompt_free(self):
        metadata = _generation_trace_metadata(
            provider="google_ai_studio",
            latency_ms=125,
            tokens={"cached_tokens": 4, "reasoning_tokens": 7},
            request_metrics={
                "quality_profile": "balanced",
                "quality_policy_revision": 3,
                "compression_reason": "below_threshold",
                "prompt": "do not export me",
                "secret": "do not export me either",
            },
        )

        self.assertEqual(
            metadata,
            {
                "provider": "google_ai_studio",
                "latency_ms": 125,
                "cached_tokens": 4,
                "reasoning_tokens": 7,
                "quality_profile": "balanced",
                "quality_policy_revision": 3,
                "compression_reason": "below_threshold",
            },
        )


class QualityDecisionTraceWiringTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_langfuse_export_never_constructs_exporter(self):
        with (
            patch(
                "config.get_telemetry_config",
                new=AsyncMock(
                    return_value={
                        "enabled": False,
                        "langfuse_public_key": "",
                        "langfuse_secret_key": "",
                        "langfuse_host": "https://cloud.langfuse.com",
                    }
                ),
            ),
            patch("core.telemetry_exporter.TelemetryExporter") as exporter,
        ):
            _schedule_trace_export(
                model_name="model-a",
                provider="google_ai_studio",
                token_usage={"input_tokens": 10, "output_tokens": 5},
                latency_ms=80,
            )
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        exporter.assert_not_called()

    async def test_scheduled_export_uses_prompt_free_quality_metadata(self):
        export = AsyncMock(return_value=True)
        exporter = Mock(export_trace_to_langfuse=export)
        with (
            patch(
                "config.get_telemetry_config",
                new=AsyncMock(
                    return_value={
                        "enabled": True,
                        "langfuse_public_key": "public",
                        "langfuse_secret_key": "secret",
                        "langfuse_host": "https://langfuse.invalid",
                    }
                ),
            ),
            patch("core.telemetry_exporter.TelemetryExporter", return_value=exporter),
            patch("core.api.utils.get_request_id", return_value="request-123"),
        ):
            _schedule_trace_export(
                model_name="model-a",
                provider="google_ai_studio",
                token_usage={"input_tokens": 10, "output_tokens": 5},
                latency_ms=80,
                request_metrics={
                    "quality_profile": "balanced",
                    "quality_policy_revision": 4,
                    "compression_reason": "target_reached",
                    "prompt": "must never leave the gateway",
                },
            )
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        metadata = export.await_args.kwargs["metadata"]
        self.assertEqual(metadata["quality_profile"], "balanced")
        self.assertEqual(metadata["quality_policy_revision"], 4)
        self.assertEqual(metadata["compression_reason"], "target_reached")
        self.assertNotIn("prompt", metadata)
        self.assertIsNone(export.await_args.kwargs["input_data"])
        self.assertIsNone(export.await_args.kwargs["output_data"])


if __name__ == "__main__":
    unittest.main()
