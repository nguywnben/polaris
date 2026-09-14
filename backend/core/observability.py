"""LLM Observability and OpenTelemetry Tracing Module.

Captures TTFT (Time To First Token), token throughput (tokens/sec),
lifecycle spans, and provides OpenTelemetry standard export compatibility.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class LLMRequestMetrics:
    request_id: str
    model: str
    provider: str
    credential_file: str
    start_time: float = field(default_factory=time.time)
    first_token_time: Optional[float] = None
    end_time: Optional[float] = None
    input_tokens: int = 0
    output_tokens: int = 0
    status_code: int = 200
    error_message: Optional[str] = None

    def record_first_token(self) -> None:
        """Mark the arrival time of the first stream chunk."""
        if self.first_token_time is None:
            self.first_token_time = time.time()

    def complete(
        self, output_tokens: int = 0, status_code: int = 200, error: Optional[str] = None
    ) -> None:
        """Finalize the request execution metrics."""
        self.end_time = time.time()
        self.output_tokens = max(0, output_tokens)
        self.status_code = status_code
        self.error_message = error

    @property
    def total_latency_ms(self) -> float:
        end = self.end_time or time.time()
        return max(0.0, (end - self.start_time) * 1000.0)

    @property
    def ttft_ms(self) -> Optional[float]:
        """Time to First Token in milliseconds."""
        if self.first_token_time is None:
            return None
        return max(0.0, (self.first_token_time - self.start_time) * 1000.0)

    @property
    def tokens_per_second(self) -> float:
        """Output token generation throughput."""
        if self.output_tokens <= 0 or self.end_time is None:
            return 0.0
        duration = max(0.001, self.end_time - (self.first_token_time or self.start_time))
        return round(self.output_tokens / duration, 2)

    def to_otel_span(self) -> Dict[str, Any]:
        """Convert metrics to OpenTelemetry GenAI semantic convention dictionary."""
        return {
            "name": "gen_ai.chat",
            "attributes": {
                "gen_ai.system": self.provider,
                "gen_ai.request.model": self.model,
                "gen_ai.response.status_code": self.status_code,
                "gen_ai.usage.input_tokens": self.input_tokens,
                "gen_ai.usage.output_tokens": self.output_tokens,
                "polaris.ttft_ms": self.ttft_ms,
                "polaris.tokens_per_sec": self.tokens_per_second,
                "polaris.credential": self.credential_file,
                "polaris.latency_ms": self.total_latency_ms,
            },
            "status": "ERROR" if self.status_code >= 400 else "OK",
            "error_description": self.error_message,
        }
