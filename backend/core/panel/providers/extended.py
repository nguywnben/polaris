"""Authenticated onboarding for additional hosted/API-key providers."""

from typing import Literal

from core.extended_provider_runtime import discover_extended_models, normalize_extended_credential
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.panel.credential_privacy_route import CredentialPrivacyRoute
from core.pool_import import PoolImportError
from core.provider_registry import EXTENDED_PROVIDERS
from core.provider_scoped_import import import_provider_files
from core.provider_store import store_extended_credential
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, SecretStr

router = APIRouter(route_class=CredentialPrivacyRoute, tags=["provider-extended"])


@router.post("/api/providers/extended/{provider_id}/credentials/import")
async def import_extended_credentials(
    provider_id: str,
    files: list[UploadFile] = File(...),
    token: str = Depends(verify_panel_token),
):
    if provider_id not in EXTENDED_PROVIDERS:
        raise HTTPException(
            status_code=404,
            detail="This operation is not supported for the selected provider or credential type.",
        )
    try:
        return JSONResponse(content=await import_provider_files(provider_id, files))
    except PoolImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


class ExtendedCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr = Field(min_length=1, max_length=4096)
    credential_label: str = Field(default="", max_length=128)
    base_url: str = Field(default="", max_length=2048)
    account_id: str = Field(default="", max_length=64)
    organization_id: str = Field(default="", max_length=128)
    plan: Literal["zen", "go"] = "zen"
    region: str = Field(default="us-east-1", max_length=32)
    profile_arn: str = Field(default="", max_length=512)


@router.post("/api/providers/extended/{provider_id}/credentials")
async def add_extended_credential(
    provider_id: str,
    request: ExtendedCredentialRequest,
    token: str = Depends(verify_panel_token),
):
    if provider_id not in EXTENDED_PROVIDERS or provider_id == "muse_code":
        raise HTTPException(
            status_code=404,
            detail="This operation is not supported for the selected provider or credential type.",
        )
    data = {
        **request.model_dump(exclude_unset=True),
        "provider": provider_id,
        "api_key": request.api_key.get_secret_value(),
    }
    try:
        normalized = normalize_extended_credential(data)
        model_ids = await discover_extended_models(normalized)
        saved = await store_extended_credential(
            {**normalized, "credential_label": request.credential_label}, model_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    return JSONResponse(
        status_code=200 if saved["action"] == "updated" else 201,
        content={
            "success": True,
            "credential_saved": True,
            "provider": provider_id,
            "provider_variant": provider_id,
            "credential_action": saved["action"],
            "filename": saved["filename"],
            "model_count": len(model_ids),
            # Catalogs may be public; do not claim inference authorization.
            "connection_test_required": True,
            "message": "Credential saved. Open the credential pool and test a model to check inference access.",
        },
    )
