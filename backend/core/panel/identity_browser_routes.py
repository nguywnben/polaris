"""Public browser endpoints for enterprise OIDC sign-in."""

from __future__ import annotations

import asyncio
import time

from core.identity import (
    OIDC_CALLBACK_PATH,
    OidcLoginDisabled,
    OidcLoginError,
    get_or_initialize_oidc_login_service,
)
from core.utils import _panel_cookie_is_secure, set_panel_session_cookie
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import RedirectResponse

from .auth_support import _assert_and_record_oidc_start, _client_identity

OIDC_BROWSER_COOKIE = "oidc_login"

router = APIRouter(prefix="/api/identity", tags=["identity"])


def _secure_no_store(response: RedirectResponse) -> RedirectResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _set_browser_binding(
    response: RedirectResponse,
    *,
    browser_token: str,
    max_age: int,
    request: Request,
) -> None:
    response.set_cookie(
        key=OIDC_BROWSER_COOKIE,
        value=browser_token,
        max_age=max_age,
        httponly=True,
        secure=_panel_cookie_is_secure(request),
        samesite="lax",
        path=OIDC_CALLBACK_PATH,
    )


def _clear_browser_binding(response: RedirectResponse, request: Request) -> None:
    response.delete_cookie(
        key=OIDC_BROWSER_COOKIE,
        path=OIDC_CALLBACK_PATH,
        httponly=True,
        secure=_panel_cookie_is_secure(request),
        samesite="lax",
    )


@router.get("/oidc/start")
async def start_oidc_login(request: Request):
    """Begin one browser-bound Authorization Code + PKCE transaction."""
    await _assert_and_record_oidc_start(_client_identity(request))
    try:
        service = await get_or_initialize_oidc_login_service()
        authorization = await service.begin()
        response = _secure_no_store(
            RedirectResponse(authorization.authorization_url, status_code=303)
        )
        _set_browser_binding(
            response,
            browser_token=authorization.browser_token,
            max_age=authorization.expires_in_seconds,
            request=request,
        )
        return response
    except asyncio.CancelledError:
        raise
    except OidcLoginDisabled:
        raise HTTPException(status_code=404, detail="OIDC login is unavailable.") from None
    except OidcLoginError:
        raise HTTPException(status_code=503, detail="OIDC login is unavailable.") from None
    except Exception:
        raise HTTPException(status_code=503, detail="OIDC login is unavailable.") from None


@router.get("/oidc/callback")
async def complete_oidc_login(request: Request):
    """Consume one callback, issue a local session, and remove every provider parameter."""
    browser_token = request.cookies.get(OIDC_BROWSER_COOKIE, "")
    try:
        if not browser_token:
            raise OidcLoginError
        service = await get_or_initialize_oidc_login_service()
        issued = await service.complete(
            request.scope.get("query_string", b""),
            browser_token=browser_token,
            now=time.time(),
        )
        response = _secure_no_store(RedirectResponse("/", status_code=303))
        set_panel_session_cookie(response, issued.token, request)
    except asyncio.CancelledError:
        raise
    except Exception:
        response = _secure_no_store(RedirectResponse("/login", status_code=303))
    _clear_browser_binding(response, request)
    return response
