@echo off
REM Compatibility path for native Python installs. Canonical production: docs/installation.md.
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

where uv >nul 2>nul
if errorlevel 1 (
    echo [ERROR] uv is required. Install it from https://docs.astral.sh/uv/ and run this script again.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creating virtual environment...
    uv venv
)

echo [INFO] Installing Python dependencies...
uv pip install --require-hashes -r requirements.lock
if errorlevel 1 exit /b 1

echo [INFO] Starting Polaris...
".venv\Scripts\python.exe" backend\main.py
