"""Shared HTTP server policy for production and topology evidence runtimes."""

from __future__ import annotations

from hypercorn.config import Config

# Hypercorn intentionally rotates persistent connections after a bounded number
# of requests. The default (1,000) can expire a connection inside Polaris's
# frozen 4,096-request HA measurement phase, so retain a finite ceiling above it.
HYPERCORN_KEEP_ALIVE_MAX_REQUESTS = 10_000


def configure_hypercorn(config: Config) -> Config:
    """Apply the connection lifecycle policy shared by every Polaris server entrypoint."""

    config.keep_alive_max_requests = HYPERCORN_KEEP_ALIVE_MAX_REQUESTS
    return config
