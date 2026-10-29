"""Minimal environment for fresh, local smoke-test runtimes (never production)."""

from __future__ import annotations

import os
from pathlib import Path


def isolated_runtime_environment(runtime: Path, port: int) -> dict[str, str]:
    """Keep OS launch requirements, not operator credentials or application settings."""
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATHEXT", "LANG"}
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    environment.update(
        PYTHON_DOTENV_DISABLED="1",
        CREDENTIALS_DIR=str(runtime.resolve() / "credentials"),
        LOG_FILE=str(runtime.resolve() / "runtime.log"),
        POSTGRESQL_URI="",
        MONGODB_URI="",
        HOST="127.0.0.1",
        PORT=str(port),
        WORKERS="1",
        PANEL_PASSWORD="",
        SETUP_TOKEN="",
        POLARIS_RUNTIME_MODE="standalone",
        POLARIS_REPLICA_COUNT="1",
        PRICING_SYNC_ENABLED="false",
        ENABLE_LOG="0",
    )
    return environment
