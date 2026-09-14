#!/usr/bin/env bash
# Compatibility path for Termux. Canonical production: docs/installation.md.
set -euo pipefail

log() {
    echo "[INFO] $1"
}

fail() {
    echo "[ERROR] $1" >&2
    exit 1
}

if [ "$(id -u)" = "0" ]; then
    fail "Do not run this script as root in Termux."
fi

if [ -z "${PREFIX:-}" ]; then
    fail "This installer is intended for Termux."
fi

export DEBIAN_FRONTEND=noninteractive

log "Updating Termux packages..."
pkg update -y

log "Installing required packages..."
pkg install -y python git nodejs-lts

if ! command -v pm2 >/dev/null 2>&1; then
    log "Installing PM2..."
    npm install -g pm2
fi

PROJECT_DIR="${PROJECT_DIR:-polaris}"
REPOSITORY_URL="${REPOSITORY_URL:-}"

if [ -f "./backend/main.py" ]; then
    log "Using current project checkout."
elif [ -f "./${PROJECT_DIR}/backend/main.py" ]; then
    cd "./${PROJECT_DIR}"
else
    if [ -z "$REPOSITORY_URL" ]; then
        fail "Set REPOSITORY_URL or run this script from the project root."
    fi
    log "Cloning repository..."
    git clone "$REPOSITORY_URL" "$PROJECT_DIR"
    cd "./${PROJECT_DIR}"
fi

if [ ! -d ".venv" ]; then
    log "Creating Python virtual environment..."
    python -m venv .venv
fi

log "Installing Python dependencies..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --require-hashes -r requirements.lock

log "Starting Polaris with PM2..."
pm2 start .venv/bin/python --name polaris -- backend/main.py
pm2 save
