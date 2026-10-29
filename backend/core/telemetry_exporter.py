"""Live Telemetry Exporter for Langfuse, Datadog, and OpenInference.

Streams Gateway execution spans and generation traces in background tasks
without blocking the client response path.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from core.httpx_client import http_client


class TelemetryExporter:
    """Dispatches traces and metrics to observability platforms."""

    def __init__(
        self,
        langfuse_public_key: Optional[str] = None,
        langfuse_secret_key: Optional[str] = None,
        langfuse_host: str = "https://cloud.langfuse.com",
    ) -> None:
        self.langfuse_public_key = langfuse_public_key
        self.langfuse_secret_key = langfuse_secret_key
        self.langfuse_host = langfuse_host.rstrip("/")

    def is_langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    async def export_trace_to_langfuse(
        self,
        trace_id: str,
        name: str,
        model: str,
        input_data: Any,
        output_data: Any,
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Export a single LLM execution generation event to Langfuse."""
        if not self.is_langfuse_enabled():
            return False

        url = f"{self.langfuse_host}/api/public/ingestion"
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        event_payload = {
            "batch": [
                {
                    "id": f"gen-{trace_id}",
                    "type": "generation-create",
                    "timestamp": now_iso,
                    "body": {
                        "traceId": trace_id,
                        "name": name,
                        "model": model,
                        "input": input_data,
                        "output": output_data,
                        "usage": {
                            "input": prompt_tokens,
                            "output": completion_tokens,
                            "total": prompt_tokens + completion_tokens,
                        },
                        "metadata": metadata or {},
                    },
                }
            ]
        }

        try:
            async with http_client.get_client(timeout=3.0, destination_url=url) as client:
                res = await client.post(
                    url,
                    json=event_payload,
                    auth=(self.langfuse_public_key, self.langfuse_secret_key),
                )
                return res.status_code in {200, 201, 207}
        except Exception:
            return False
