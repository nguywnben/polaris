"""Fail-closed controls for external observability exporters."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit


class TelemetryConfigurationError(RuntimeError):
    """Raised when an explicitly enabled exporter is unsafe or incomplete."""


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class TelemetryPolicy:
    prometheus_enabled: bool
    metrics_token: str
    otel_enabled: bool
    otel_endpoint: str
    otel_interval_seconds: int
    otel_headers: tuple[tuple[str, str], ...]

    def public_status(self) -> dict[str, object]:
        endpoint = ""
        if self.otel_endpoint:
            parsed = urlsplit(self.otel_endpoint)
            endpoint = f"{parsed.scheme}://{parsed.hostname or ''}"
            if parsed.port:
                endpoint += f":{parsed.port}"
        return {
            "prometheus": {"enabled": self.prometheus_enabled, "authentication": "bearer"},
            "opentelemetry": {
                "enabled": self.otel_enabled,
                "endpoint_origin": endpoint,
                "content_exported": False,
            },
        }


def get_telemetry_policy() -> TelemetryPolicy:
    prometheus_enabled = _enabled("PROMETHEUS_EXPORT_ENABLED")
    token = os.getenv("METRICS_TOKEN", "").strip()
    if prometheus_enabled and len(token.encode("utf-8")) < 32:
        raise TelemetryConfigurationError(
            "Prometheus export requires METRICS_TOKEN with at least 32 UTF-8 bytes."
        )

    otel_enabled = _enabled("OTEL_EXPORT_ENABLED")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip().rstrip("/")
    if otel_enabled:
        protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/json").strip().lower()
        if protocol != "http/json":
            raise TelemetryConfigurationError(
                "This aggregate OpenTelemetry exporter requires OTLP http/json."
            )
        parsed = urlsplit(endpoint)
        try:
            parsed_port = parsed.port
        except ValueError as exc:
            raise TelemetryConfigurationError("OpenTelemetry endpoint port is invalid.") from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed_port is not None
            and not 1 <= parsed_port <= 65535
        ):
            raise TelemetryConfigurationError(
                "OpenTelemetry export requires an HTTPS OTLP endpoint without embedded credentials."
            )

    interval = 60
    headers: list[tuple[str, str]] = []
    if otel_enabled:
        raw_interval = os.getenv("OTEL_EXPORT_INTERVAL_SECONDS", "60").strip()
        try:
            interval = int(raw_interval)
        except ValueError as exc:
            raise TelemetryConfigurationError("OpenTelemetry export interval is invalid.") from exc
        if not 15 <= interval <= 300:
            raise TelemetryConfigurationError(
                "OpenTelemetry export interval must be 15–300 seconds."
            )

        raw_headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "").strip()
        for item in raw_headers.split(",") if raw_headers else ():
            name, separator, value = item.partition("=")
            normalized = name.strip().lower()
            value = value.strip()
            if (
                not separator
                or normalized not in {"authorization", "api-key", "x-api-key"}
                or not re.fullmatch(r"[a-z0-9-]{1,64}", normalized)
                or not 1 <= len(value) <= 1024
                or "\r" in value
                or "\n" in value
                or len(headers) >= 8
            ):
                raise TelemetryConfigurationError("OpenTelemetry exporter headers are invalid.")
            headers.append((normalized, value))

    return TelemetryPolicy(
        prometheus_enabled, token, otel_enabled, endpoint, interval, tuple(headers)
    )
