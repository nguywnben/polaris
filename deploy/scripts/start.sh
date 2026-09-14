#!/usr/bin/env bash
# Compatibility path for native Python installs. Canonical production: docs/installation.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

if ! command -v uv >/dev/null 2>&1; then
    echo "[ERROR] uv is required. Install it from https://docs.astral.sh/uv/ and run this script again." >&2
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "[INFO] Creating virtual environment..."
    uv venv
fi

echo "[INFO] Installing Python dependencies..."
uv pip install --require-hashes -r requirements.lock

echo "[INFO] Starting Polaris..."
exec .venv/bin/python backend/main.py
