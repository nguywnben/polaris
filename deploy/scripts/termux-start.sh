#!/usr/bin/env bash
# Compatibility path for Termux. Canonical production: docs/installation.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

if [ ! -d ".venv" ]; then
    echo "[INFO] Creating Python virtual environment..."
    python -m venv .venv
fi

echo "[INFO] Installing Python dependencies..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --require-hashes -r requirements.lock

if command -v pm2 >/dev/null 2>&1; then
    echo "[INFO] Starting Polaris with PM2..."
    pm2 start .venv/bin/python --name polaris -- backend/main.py
else
    echo "[INFO] PM2 is not installed. Starting Polaris in the foreground..."
    exec .venv/bin/python backend/main.py
fi
