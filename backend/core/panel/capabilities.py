"""Authenticated product support-tier summary for the management console."""

from __future__ import annotations

from core.capability_registry import ProductCapabilitySnapshot, get_capability_snapshot
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends

router = APIRouter(tags=["capabilities"])


@router.get("/api/capabilities", response_model=ProductCapabilitySnapshot)
async def get_product_capabilities(token: str = Depends(verify_panel_token)):
    """Return a versioned, secret-free projection of supported product capabilities."""

    del token
    snapshot = get_capability_snapshot()
    return JSONResponse(content=snapshot.model_dump(mode="json"))
