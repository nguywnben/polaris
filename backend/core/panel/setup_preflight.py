"""Secret-free first-run diagnostics and resumable setup checkpoints."""

from __future__ import annotations

import os
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit

import config
from core.utils import _panel_cookie_is_secure, _request_origin
from fastapi import Request

from .setup_security import get_setup_access_policy, verify_setup_access

SETUP_CHECKPOINT_KEY = "setup_preflight_checkpoint"
SETUP_CHECKPOINT = {"version": 1, "preflight": "passed"}


def _check(status: str, code: str) -> dict[str, str]:
    return {"status": status, "code": code}


def _origin_is_loopback(origin: str) -> bool:
    """Recognize host-loopback URLs even when Docker obscures the client address."""
    try:
        hostname = urlsplit(origin).hostname
        return hostname == "localhost" or bool(hostname and ip_address(hostname).is_loopback)
    except ValueError:
        return False


async def build_setup_status(
    request: Request,
    storage: Any,
    *,
    setup_required: bool,
    authenticated: bool,
) -> dict[str, Any]:
    """Describe one installation state and one operator action without secrets."""
    origin = _request_origin(request)
    policy = get_setup_access_policy(request)
    local_origin = _origin_is_loopback(origin)
    host = await config.get_server_host()
    port = await config.get_server_port()
    checks = {
        "data": _check("pending", "data_check_required"),
        "address": _check(
            "pass" if origin else "fail", "address_valid" if origin else "address_invalid"
        ),
        "transport": _check(
            "pass",
            "transport_local" if policy.local_request or local_origin else "transport_secure",
        ),
        "setup_token": _check("pass", "setup_token_not_required"),
        "owner": _check("pending", "owner_not_created"),
    }

    if not setup_required:
        checks["data"] = _check("pass", "data_available")
        checks["owner"] = _check("pass", "owner_configured")
        return {
            "state": "configured",
            "next_action": "open_dashboard" if authenticated else "sign_in",
            "setup_required": False,
            "setup_token_required": False,
            "authenticated": authenticated,
            "base_url": origin,
            "listener": f"{host}:{port}",
            "checks": checks,
            "password_policy": {"min_length": 12, "max_length": 256},
        }

    failures: list[str] = []
    if not origin:
        failures.append("fix_base_url")

    if policy.token_required:
        if not policy.token_configured or not policy.token_strong:
            checks["setup_token"] = _check("fail", "setup_token_configuration_invalid")
            failures.insert(0, "configure_setup_token")
        else:
            checks["setup_token"] = _check("pending", "setup_token_entry_required")

    secure_cookie_setting = os.getenv("PANEL_COOKIE_SECURE", "").strip().lower()
    if not policy.local_request and not local_origin and not origin.startswith("https://"):
        checks["transport"] = _check("fail", "https_required")
        failures.append("use_https")
    elif origin.startswith("https://") and not _panel_cookie_is_secure(request):
        checks["transport"] = _check("fail", "secure_cookie_required")
        failures.append("enable_secure_cookie")
    elif origin.startswith("http://") and secure_cookie_setting in {"1", "true", "yes", "on"}:
        checks["transport"] = _check("fail", "secure_cookie_requires_https")
        failures.append("use_https_or_auto_cookie")

    checkpoint = None
    try:
        checkpoint = await storage.get_config(SETUP_CHECKPOINT_KEY)
    except Exception:
        checks["data"] = _check("fail", "data_unavailable")
        failures.append("fix_data_permissions")

    resumed = checkpoint == SETUP_CHECKPOINT
    if resumed:
        checks["data"] = _check("pass", "data_writable")
        checks["owner"] = _check("pending", "owner_creation_ready")

    if failures:
        return {
            "state": "invalid",
            "next_action": failures[0],
            "setup_required": True,
            "setup_token_required": policy.token_required,
            "authenticated": False,
            "base_url": origin,
            "listener": f"{host}:{port}",
            "checks": checks,
            "password_policy": {"min_length": 12, "max_length": 256},
        }

    return {
        "state": "resumed" if resumed else "fresh",
        "next_action": "create_owner"
        if resumed
        else ("enter_setup_token" if policy.token_required else "run_preflight"),
        "setup_required": True,
        "setup_token_required": policy.token_required,
        "authenticated": False,
        "base_url": origin,
        "listener": f"{host}:{port}",
        "checks": checks,
        "password_policy": {"min_length": 12, "max_length": 256},
    }


async def run_setup_preflight(
    request: Request,
    storage: Any,
    *,
    supplied_token: str | None,
) -> dict[str, Any]:
    """Validate setup ingress and prove durable configuration writes."""
    verify_setup_access(request, supplied_token)
    status = await build_setup_status(
        request,
        storage,
        setup_required=True,
        authenticated=False,
    )
    if status["state"] == "invalid":
        return status

    try:
        written = await storage.set_config(SETUP_CHECKPOINT_KEY, SETUP_CHECKPOINT)
        checkpoint = await storage.get_config(SETUP_CHECKPOINT_KEY) if written else None
    except Exception:
        written = False
        checkpoint = None
    if not written or checkpoint != SETUP_CHECKPOINT:
        status["state"] = "invalid"
        status["next_action"] = "fix_data_permissions"
        status["checks"]["data"] = _check("fail", "data_not_writable")
        return status

    status["state"] = "resumed"
    status["next_action"] = "create_owner"
    status["checks"]["data"] = _check("pass", "data_writable")
    status["checks"]["owner"] = _check("pending", "owner_creation_ready")
    if status["setup_token_required"]:
        status["checks"]["setup_token"] = _check("pass", "setup_token_verified")
    return status
