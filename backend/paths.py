"""Shared filesystem paths for the backend service."""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATA_DIR = BACKEND_DIR / "data"
DEFAULT_CREDENTIALS_DIR = DATA_DIR / "creds"
DEFAULT_LOGS_DIR = DATA_DIR / "logs"
DEFAULT_LOG_FILE = DEFAULT_LOGS_DIR / "polaris.log"
