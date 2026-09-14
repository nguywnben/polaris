"""Security policy for first-run control-panel setup."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass

from config import trust_proxy_headers_enabled
from fastapi import HTTPException, Request

SETUP_TOKEN_ENV = "SETUP_TOKEN"
SETUP_TOKEN_HEADER = "x-setup-token"
SETUP_TOKEN_MIN_LENGTH = 24
OWNER_PASSWORD_MIN_LENGTH = 12
OWNER_PASSWORD_MAX_LENGTH = 256
_COMMON_OWNER_PASSWORDS = frozenset(
    {
        "administrator",
        "letmein123456",
        "omni-gateway",
        "polaris",
        "password1234",
        "qwerty123456",
    }
)


@dataclass(frozen=True)
class SetupAccessPolicy:
    token_required: bool
    local_request: bool
    token_configured: bool
    token_strong: bool


def _request_client_host(request: Request) -> str:
    if trust_proxy_headers_enabled():
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


def _is_loopback_address(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def is_local_setup_request(request: Request) -> bool:
    """Return whether setup is being performed directly through a loopback origin."""
    hostname = (request.url.hostname or "").strip().lower()
    local_hostname = hostname in {"localhost", "127.0.0.1", "::1"}
    return local_hostname and _is_loopback_address(_request_client_host(request))


def get_setup_access_policy(request: Request) -> SetupAccessPolicy:
    local_request = is_local_setup_request(request)
    configured_token = os.getenv(SETUP_TOKEN_ENV, "").strip()
    explicitly_configured = bool(configured_token)
    return SetupAccessPolicy(
        token_required=explicitly_configured or not local_request,
        local_request=local_request,
        token_configured=explicitly_configured,
        token_strong=(
            len(configured_token) >= SETUP_TOKEN_MIN_LENGTH and len(set(configured_token)) >= 8
        ),
    )


def validate_owner_password(password: str) -> None:
    """Enforce a bounded policy that still permits memorable passphrases."""
    if len(password) < OWNER_PASSWORD_MIN_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {OWNER_PASSWORD_MIN_LENGTH} characters.",
        )
    if len(password) > OWNER_PASSWORD_MAX_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at most {OWNER_PASSWORD_MAX_LENGTH} characters.",
        )
    if password.casefold() in _COMMON_OWNER_PASSWORDS or len(set(password)) < 4:
        raise HTTPException(
            status_code=400,
            detail="Choose a less common password or a longer unique passphrase.",
        )


def verify_setup_access(request: Request, supplied_token: str | None) -> None:
    policy = get_setup_access_policy(request)
    if not policy.token_required:
        return

    if not policy.token_configured or not policy.token_strong:
        raise HTTPException(
            status_code=503,
            detail=(
                "Remote setup requires a strong SETUP_TOKEN configured in the service "
                "environment. Restart the service after changing it."
            ),
        )

    import secrets

    expected_token = os.getenv(SETUP_TOKEN_ENV, "").strip()
    candidate = (supplied_token or request.headers.get(SETUP_TOKEN_HEADER, "")).strip()
    if not candidate or not secrets.compare_digest(candidate, expected_token):
        raise HTTPException(
            status_code=403,
            detail=(
                "A valid setup token is required for remote initial setup. "
                "Use the SETUP_TOKEN configured by the service operator."
            ),
        )
