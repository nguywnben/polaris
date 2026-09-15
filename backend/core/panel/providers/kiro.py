"""Authenticated, session-bound Kiro OAuth onboarding."""

from typing import Literal

from core.device_authorization_coordination import DeviceAuthorizationError
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.kiro import KiroError
from core.kiro_device_login import cancel_login, poll_login, start_login
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["provider-kiro"])


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


async def _response(operation):
    try:
        return JSONResponse(content=await operation, headers={"Cache-Control": "no-store"})
    except KiroError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    except DeviceAuthorizationError:
        raise HTTPException(
            status_code=409, detail="Kiro login expired or is unavailable. Start a new login."
        ) from None


@router.post("/api/providers/kiro/oauth/start")
async def start(request: KiroLoginRequest, token: str = Depends(verify_panel_token)):
    return await _response(start_login(token, **request.model_dump()))


@router.post("/api/providers/kiro/oauth/complete")
async def complete(request: KiroFlowRequest, token: str = Depends(verify_panel_token)):
    return await _response(poll_login(token, request.flow_id))


@router.post("/api/providers/kiro/oauth/cancel")
async def cancel(request: KiroFlowRequest, token: str = Depends(verify_panel_token)):
    return await _response(cancel_login(token, request.flow_id))
