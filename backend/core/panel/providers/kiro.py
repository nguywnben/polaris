"""Authenticated, session-bound Kiro OAuth onboarding."""

from typing import Literal

from core import kiro_browser_login
from core.device_authorization_coordination import (
    DeviceAuthorizationBusyError,
    DeviceAuthorizationError,
)
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.kiro import KiroError
from core.kiro_device_login import cancel_login, poll_login, start_login
from core.management_audit import ManagementMutation, record_classified_management_response
from core.panel.credential_privacy_route import CredentialPrivacyRoute
from core.request_context import get_request_id
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(route_class=CredentialPrivacyRoute, tags=["provider-kiro"])


class KiroLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["google", "github", "builder-id", "identity-center"]
    region: Literal["us-east-1", "eu-central-1"] = "us-east-1"
    token_region: str = Field(default="us-east-1", max_length=32)
    start_url: str = Field(default="", max_length=2048)
    credential_label: str = Field(default="", max_length=128)


class KiroFlowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flow_id: str = Field(pattern=r"^kiro_[A-Za-z0-9_-]{43}$")


class KiroBrowserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callback_origin: str = Field(max_length=256)
    region: Literal["us-east-1", "eu-central-1"] = "us-east-1"


class KiroCallbackRequest(KiroFlowRequest):
    callback_url: str = Field(min_length=1, max_length=6144)


async def _response(operation):
    try:
        return JSONResponse(content=await operation, headers={"Cache-Control": "no-store"})
    except KiroError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    except DeviceAuthorizationBusyError:
        raise HTTPException(
            status_code=503,
            detail="Kiro login expired or is unavailable. Start a new login.",
            headers={"Retry-After": "1"},
        ) from None
    except DeviceAuthorizationError:
        raise HTTPException(
            status_code=409, detail="Kiro login expired or is unavailable. Start a new login."
        ) from None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Kiro callback URL.") from None


@router.post("/api/providers/kiro/oauth/start")
async def start(request: KiroLoginRequest, token: str = Depends(verify_panel_token)):
    return await _response(start_login(token, **request.model_dump()))


@router.post("/api/providers/kiro/oauth/complete")
async def complete(request: KiroFlowRequest, token: str = Depends(verify_panel_token)):
    return await _response(poll_login(token, request.flow_id))


@router.post("/api/providers/kiro/oauth/cancel")
async def cancel(request: KiroFlowRequest, token: str = Depends(verify_panel_token)):
    return await _response(cancel_login(token, request.flow_id))


@router.post("/api/providers/kiro/browser/start")
async def browser_start(request: KiroBrowserRequest, token: str = Depends(verify_panel_token)):
    return await _response(kiro_browser_login.start_login(token, **request.model_dump()))


@router.post("/api/providers/kiro/browser/complete")
async def browser_complete(
    request: KiroFlowRequest, http_request: Request, token: str = Depends(verify_panel_token)
):
    async def complete_and_record():
        result = await kiro_browser_login.complete_login(token, request.flow_id)
        if result.get("credential_saved"):
            await record_classified_management_response(
                ManagementMutation(
                    "credential.create", "credential", ("created",), "kiro:collection"
                ),
                status_code=200,
                request_id=get_request_id(),
                principal=getattr(http_request.state, "management_principal", None),
            )
        return result

    return await _response(complete_and_record())


@router.post("/api/providers/kiro/browser/cancel")
async def browser_cancel(request: KiroFlowRequest, token: str = Depends(verify_panel_token)):
    return await _response(kiro_browser_login.cancel_login(token, request.flow_id))


@router.post("/api/providers/kiro/browser/callback")
async def browser_manual_callback(
    request: KiroCallbackRequest, token: str = Depends(verify_panel_token)
):
    return await _response(
        kiro_browser_login.accept_callback(
            request.callback_url, token=token, flow_id=request.flow_id
        )
    )


@router.get("/oauth/callback", include_in_schema=False)
@router.get("/signin/callback", include_in_schema=False)
async def browser_callback(request: Request):
    # Public landing route captures no tokens and cannot save a credential.
    # Fixed redirect removes authorization parameters before rendering any assets.
    try:
        await kiro_browser_login.accept_callback(str(request.url))
        result = "received"
    except DeviceAuthorizationBusyError:
        # Keep the URL available for manual submission if a concurrent poll owns
        # the short lease. Do not discard its code with a failure redirect.
        from core.i18n import translate
        from core.panel.root import _oauth_callback_page

        return _oauth_callback_page(
            False, "Kiro", translate("oauth.copy_callback"), manual_callback=True
        )
    except (KiroError, DeviceAuthorizationError, ValueError):
        result = "failed"
    return RedirectResponse(
        "/callback?kiro=" + result,
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
