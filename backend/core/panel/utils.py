import os
import time
from collections import deque
from typing import Set

import config
from core.credential_validation import validate_credential_filename as _validate_credential_filename
from fastapi import HTTPException, WebSocket
from log import log, redact_text
from starlette.websockets import WebSocketState

INTERNAL_SERVER_ERROR_DETAIL = (
    "The request could not be completed because of an internal service error."
)
MAX_PUBLIC_ERROR_DETAIL_LENGTH = 8192


def internal_server_error() -> HTTPException:
    """Return a stable 500 response without exposing implementation details."""
    return HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_DETAIL)


def public_error_detail(value: object, fallback: str = "The provider request failed.") -> str:
    """Return bounded provider diagnostics with credentials removed."""
    detail = redact_text(value).strip()
    if not detail:
        return fallback
    if len(detail) > MAX_PUBLIC_ERROR_DETAIL_LENGTH:
        return f"{detail[:MAX_PUBLIC_ERROR_DETAIL_LENGTH]}..."
    return detail


# =============================================================================

# =============================================================================


class ConnectionManager:
    def __init__(self, max_connections: int = 3):

        self.active_connections: deque = deque(maxlen=max_connections)
        self.max_connections = max_connections
        self._last_cleanup = 0
        self._cleanup_interval = 120

    async def connect(self, websocket: WebSocket):

        self._auto_cleanup()

        if len(self.active_connections) >= self.max_connections:
            await websocket.close(code=1008, reason="Too many connections")
            return False

        await websocket.accept()
        self.active_connections.append(websocket)
        log.debug(
            f"WebSocket connection established, current connections: {len(self.active_connections)}"
        )
        return True

    def disconnect(self, websocket: WebSocket):

        try:
            self.active_connections.remove(websocket)
        except ValueError:
            pass
        log.debug(
            f"WebSocket disconnected, number of current connections: {len(self.active_connections)}"
        )

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception:
            self.disconnect(websocket)

    async def broadcast(self, message: str):

        dead_connections = []
        for conn in self.active_connections:
            try:
                await conn.send_text(message)
            except Exception:
                dead_connections.append(conn)

        for dead_conn in dead_connections:
            self.disconnect(dead_conn)

    def _auto_cleanup(self):
        current_time = time.time()
        if current_time - self._last_cleanup > self._cleanup_interval:
            self.cleanup_dead_connections()
            self._last_cleanup = current_time

    def cleanup_dead_connections(self):
        original_count = len(self.active_connections)

        alive_connections = deque(
            [
                conn
                for conn in self.active_connections
                if hasattr(conn, "client_state")
                and conn.client_state != WebSocketState.DISCONNECTED
            ],
            maxlen=self.max_connections,
        )

        self.active_connections = alive_connections
        cleaned = original_count - len(self.active_connections)
        if cleaned > 0:
            log.debug(
                f"Cleaned up {cleaned} dead connections, remaining connections: {len(self.active_connections)}"
            )


# =============================================================================

# =============================================================================


def is_mobile_user_agent(user_agent: str) -> bool:
    if not user_agent:
        return False

    user_agent_lower = user_agent.lower()
    mobile_keywords = [
        "mobile",
        "android",
        "iphone",
        "ipad",
        "ipod",
        "blackberry",
        "windows phone",
        "samsung",
        "htc",
        "motorola",
        "nokia",
        "palm",
        "webos",
        "opera mini",
        "opera mobi",
        "fennec",
        "minimo",
        "symbian",
        "psp",
        "nintendo",
        "tablet",
    ]

    return any(keyword in user_agent_lower for keyword in mobile_keywords)


def validate_mode(mode: str = "code_assist") -> str:
    """Normalize public credential mode names to storage mode names."""
    normalized = (mode or "code_assist").strip().lower()
    if normalized == "provider":
        return "primary"
    if normalized not in ["code_assist", "primary"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode parameter: '{mode}'. Only 'code_assist' or 'provider' are supported.",
        )
    return normalized


def validate_credential_filename(filename: str) -> str:
    """Compatibility export for existing panel modules."""
    return _validate_credential_filename(filename)


def public_mode_name(mode: str = "code_assist") -> str:
    """Return the API-facing credential mode name."""
    return "provider" if validate_mode(mode) == "primary" else "code_assist"


def get_env_locked_keys() -> Set:
    env_locked_keys = set()

    for env_key, config_key in config.ENV_MAPPINGS.items():
        if os.getenv(env_key):
            env_locked_keys.add(config_key)

    return env_locked_keys
