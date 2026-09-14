#!/usr/bin/env bash
# Compatibility path for native Python installs. Canonical production: docs/installation.md.
set -euo pipefail

log() {
    echo "[INFO] $1"
}

fail() {
    echo "[ERROR] $1" >&2
    exit 1
}

if [[ "${OSTYPE:-}" != darwin* ]]; then
    fail "This installer is intended for macOS."
fi

if ! command -v brew >/dev/null 2>&1; then
    log "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [ -x "/opt/homebrew/bin/brew" ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -x "/usr/local/bin/brew" ]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
fi

log "Installing required tools..."
brew update
brew install git uv

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
    log "Creating virtual environment..."
    uv venv
fi

log "Installing Python dependencies..."
uv pip install --require-hashes -r requirements.lock

log "Starting Polaris..."
exec .venv/bin/python backend/main.py
