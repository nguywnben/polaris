"""Explicit owner-bound Muse Code device authorization (never background polling)."""

from core.device_authorization_coordination import DeviceAuthorizationError
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.management_audit import ManagementMutation, record_classified_management_response
from core.muse_device_login import cancel_login, complete_login, start_login
from core.muse_oauth import MuseOAuthError
from core.panel.credential_privacy_route import CredentialPrivacyRoute
from core.request_context import get_request_id
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(route_class=CredentialPrivacyRoute, tags=["provider-muse-code"])


class MuseLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential_label: str = Field(default="", max_length=128)


class MuseFlowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flow_id: str = Field(pattern=r"^muse_code_[A-Za-z0-9_-]{43}$")


async def _response(operation):
    try:
        return JSONResponse(content=await operation, headers={"Cache-Control": "no-store"})
    except MuseOAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=str(exc), headers={"Cache-Control": "no-store"}
        ) from None
    except DeviceAuthorizationError:
        raise HTTPException(
            status_code=409,
            detail="Muse Code login expired or is unavailable. Start a new login.",
            headers={"Cache-Control": "no-store"},
        ) from None


@router.post("/api/providers/muse-code/oauth/start")
async def start(request: MuseLoginRequest, token: str = Depends(verify_panel_token)):
    return await _response(start_login(token, **request.model_dump()))


@router.post("/api/providers/muse-code/oauth/complete")
async def complete(
    request: MuseFlowRequest, http_request: Request, token: str = Depends(verify_panel_token)
):
    async def save_and_record():
        result = await complete_login(token, request.flow_id)
        if result.get("credential_saved"):
            await record_classified_management_response(
                ManagementMutation(
                    "credential.create", "credential", ("created",), "muse_code:collection"
                ),
                status_code=200,
                request_id=get_request_id(),
                principal=getattr(http_request.state, "management_principal", None),
            )
        return result

    return await _response(save_and_record())


@router.post("/api/providers/muse-code/oauth/cancel")
async def cancel(request: MuseFlowRequest, token: str = Depends(verify_panel_token)):
    return await _response(cancel_login(token, request.flow_id))
