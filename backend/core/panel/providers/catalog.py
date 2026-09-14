"""Provider catalog routes for the management console."""

from core.i18n import LocalizedJSONResponse as JSONResponse
from core.provider_registry import (
    CREDENTIAL_OPERATIONS,
    INFERENCE_PROTOCOLS,
    LEGACY_CREDENTIAL_OPERATIONS,
    list_credential_variant_capabilities,
    list_legacy_credential_variant_capabilities,
    list_provider_capabilities,
)
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(tags=["provider-catalog"])


class ProviderCapabilityContract(BaseModel):
    provider_id: str
    display_name: str
    credential_types: list[str]
    model_prefixes: list[str]
    supports_streaming: bool
    supports_tools: bool


class CredentialVariantCapabilityContract(BaseModel):
    variant_id: str
    provider_id: str
    display_name: str
    credential_type: str
    operations: list[str]


class ProviderCatalogContract(BaseModel):
    providers: list[ProviderCapabilityContract]
    credential_variants: list[CredentialVariantCapabilityContract]
    operation_vocabulary: list[str]


class ProviderVariantCapabilityContract(CredentialVariantCapabilityContract):
    inference_protocols: list[str]


class ProviderCapabilityMatrixContract(BaseModel):
    schema_version: int
    providers: list[ProviderCapabilityContract]
    credential_variants: list[ProviderVariantCapabilityContract]
    operation_vocabulary: list[str]
    inference_protocol_vocabulary: list[str]


@router.get("/api/providers", response_model=ProviderCatalogContract)
async def get_provider_catalog(token: str = Depends(verify_panel_token)):
    """Return provider capabilities without exposing stored credentials."""
    return JSONResponse(
        content={
            "providers": list_provider_capabilities(),
            "credential_variants": list_legacy_credential_variant_capabilities(),
            "operation_vocabulary": sorted(LEGACY_CREDENTIAL_OPERATIONS),
        }
    )


@router.get(
    "/api/providers/capabilities",
    response_model=ProviderCapabilityMatrixContract,
)
async def get_provider_capability_matrix(token: str = Depends(verify_panel_token)):
    """Return the versioned provider/auth capability matrix used by API and console."""
    return JSONResponse(
        content={
            "schema_version": 2,
            "providers": list_provider_capabilities(),
            "credential_variants": list_credential_variant_capabilities(),
            "operation_vocabulary": sorted(CREDENTIAL_OPERATIONS),
            "inference_protocol_vocabulary": sorted(INFERENCE_PROTOCOLS),
        }
    )
