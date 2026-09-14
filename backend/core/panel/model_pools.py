"""Management API for the dynamic model catalog and virtual model pool."""

import asyncio

import config
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.model_blacklist import (
    clear_model_blacklist,
    get_model_blacklist,
    remove_model_blacklist_entry,
)
from core.model_pool import (
    DEFAULT_VIRTUAL_MODEL_ALIAS,
    MODEL_ROUTING_SCHEMA_VERSION,
    ModelPoolError,
    assess_virtual_model_pool,
    decorate_virtual_model_pool,
    get_virtual_model_pool,
    model_catalog_service,
    save_virtual_model_pool,
)
from core.models import VirtualModelPoolUpdateRequest
from core.provider_registry import get_provider_display_name, get_provider_routing_id
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from log import log

from .utils import get_env_locked_keys

router = APIRouter(tags=["model-pools"])
_model_pool_write_lock = asyncio.Lock()


def _ensure_decorated_pool(pool: dict) -> dict:
    if pool.get("revision") and "configured" in pool:
        return pool
    return decorate_virtual_model_pool(pool)


def _normalize_if_match(value: str | None) -> str:
    normalized = str(value or "").strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:].strip()
    return normalized.strip('"')


def _require_current_revision(
    pool: dict,
    if_match: str | None,
    *,
    required: bool = False,
) -> None:
    """Reject stale opt-in writes while retaining the legacy unconditional PUT."""
    if if_match is None:
        if required:
            raise HTTPException(
                status_code=428,
                detail={
                    "code": "model_route_precondition_required",
                    "current_revision": pool.get("revision", ""),
                },
            )
        return
    expected = _normalize_if_match(if_match)
    if expected == "*" and pool.get("configured"):
        return
    if not expected or expected != pool.get("revision"):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "model_route_conflict",
                "current_revision": pool.get("revision", ""),
            },
        )


async def _project_catalog() -> tuple[list[dict], list[dict], list[dict]]:
    entries = await model_catalog_service.get_catalog()
    blacklist = await get_model_blacklist()
    blacklisted_pairs = {(entry["provider_id"], entry["model_id"]) for entry in blacklist}

    def is_blacklisted(provider_id: str, model_id: str) -> bool:
        return (get_provider_routing_id(provider_id), model_id) in blacklisted_pairs

    catalog = []
    provider_catalog_map = {}
    for entry in entries:
        value = entry.to_dict()
        value["blacklisted_providers"] = [
            provider_id
            for provider_id in value["providers"]
            if is_blacklisted(provider_id, value["model_id"])
        ]
        value["routable_providers"] = [
            provider_id
            for provider_id in value["providers"]
            if not is_blacklisted(provider_id, value["model_id"])
        ]
        value["available"] = bool(value["routable_providers"])
        catalog.append(value)

        for provider_id in value["providers"]:
            group = provider_catalog_map.setdefault(
                provider_id,
                {
                    "provider_id": provider_id,
                    "provider_name": get_provider_display_name(provider_id),
                    "routing_provider_id": get_provider_routing_id(provider_id),
                    "models": [],
                },
            )
            group["models"].append(
                {
                    "model_id": value["model_id"],
                    "available": not is_blacklisted(provider_id, value["model_id"]),
                    "blacklisted": is_blacklisted(provider_id, value["model_id"]),
                }
            )

    provider_catalogs = sorted(
        (
            {
                **group,
                "models": sorted(group["models"], key=lambda model: model["model_id"]),
                "model_count": len(group["models"]),
            }
            for group in provider_catalog_map.values()
        ),
        key=lambda group: (group["provider_name"], group["provider_id"]),
    )
    return catalog, provider_catalogs, blacklist


async def _validate_route(selected_models: list[str]) -> dict:
    catalog, _provider_catalogs, _blacklist = await _project_catalog()
    # A saved fallback can disappear during discovery outages. Retain it as unavailable;
    # only previously unknown IDs are rejected as manual/unverified input.
    current = await get_virtual_model_pool()
    discovered = {entry["model_id"] for entry in catalog}
    catalog.extend(
        {"model_id": model_id, "available": False, "routable_providers": []}
        for model_id in current["selected_models"]
        if model_id not in discovered
    )
    return assess_virtual_model_pool(selected_models, catalog)


@router.get("/api/model-catalog")
async def get_model_catalog(
    refresh: bool = Query(default=False),
    token: str = Depends(verify_panel_token),
):
    """Return dynamic provider models and the default virtual-model policy."""
    try:
        if refresh:
            await model_catalog_service.get_catalog(force_refresh=True)
        catalog, provider_catalogs, blacklist = await _project_catalog()
        pool = _ensure_decorated_pool(await get_virtual_model_pool())
        catalog_ids = {entry["model_id"] for entry in catalog}
        for model_id in pool["selected_models"]:
            if model_id not in catalog_ids:
                catalog.append(
                    {
                        "model_id": model_id,
                        "providers": [],
                        "routable_providers": [],
                        "blacklisted_providers": [],
                        "available": False,
                    }
                )
        catalog.sort(key=lambda entry: entry["model_id"])
        catalog_by_id = {entry["model_id"]: entry for entry in catalog}
        routing_policy = await config.get_routing_policy()
        env_locked = get_env_locked_keys()
        return JSONResponse(
            content={
                "schema_version": MODEL_ROUTING_SCHEMA_VERSION,
                "catalog": catalog,
                "provider_catalogs": provider_catalogs,
                "pool": pool,
                "validation": assess_virtual_model_pool(pool["selected_models"], catalog),
                "routing_policy": {
                    **routing_policy,
                    "strategy_locked": "routing_strategy" in env_locked,
                    "preferred_provider_locked": "preferred_provider" in env_locked,
                },
                "blacklist": blacklist,
                "summary": {
                    "available_models": sum(bool(entry["available"]) for entry in catalog),
                    "selected_models": len(pool["selected_models"]),
                    "unavailable_selected_models": sum(
                        not catalog_by_id.get(model_id, {}).get("available", False)
                        for model_id in pool["selected_models"]
                    ),
                    "blacklisted_routes": len(blacklist),
                },
            }
        )
    except Exception as exc:
        log.error(f"Failed to load the model catalog: {exc}")
        raise HTTPException(
            status_code=502,
            detail="The provider model catalog could not be loaded.",
        ) from exc


@router.get("/api/model-blacklist")
async def get_model_blacklist_entries(token: str = Depends(verify_panel_token)):
    """Return model routes excluded by observed upstream 404 responses."""
    entries = await get_model_blacklist()
    return JSONResponse(content={"blacklist": entries, "count": len(entries)})


@router.delete("/api/model-blacklist/{provider_id}/models/{model_id:path}")
async def delete_model_blacklist_entry(
    provider_id: str,
    model_id: str = Path(..., description="Provider model ID"),
    credential_name: str = Query(default=""),
    token: str = Depends(verify_panel_token),
):
    """Restore one credential-model route, or every matching provider route."""
    try:
        if credential_name:
            removed = await remove_model_blacklist_entry(
                provider_id,
                model_id,
                credential_name=credential_name,
            )
        else:
            removed = await remove_model_blacklist_entry(provider_id, model_id)
    except (ModelPoolError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(
        content={
            "removed": removed,
            "message": (
                "Model route removed from blacklist."
                if removed
                else "Model route is not blacklisted."
            ),
        }
    )


@router.delete("/api/model-blacklist")
async def delete_model_blacklist(token: str = Depends(verify_panel_token)):
    """Restore every provider-model route currently in the blacklist."""
    removed_count = await clear_model_blacklist()
    return JSONResponse(
        content={
            "removed_count": removed_count,
            "message": (
                "Model blacklist cleared." if removed_count else "Model blacklist is already empty."
            ),
        }
    )


@router.get("/api/model-pools")
async def list_model_pools(token: str = Depends(verify_panel_token)):
    """Return configured virtual model pools."""
    return JSONResponse(content={"model_pools": [await get_virtual_model_pool()]})


@router.post(f"/api/model-routes/{DEFAULT_VIRTUAL_MODEL_ALIAS}/validate")
async def validate_default_model_pool(
    request: VirtualModelPoolUpdateRequest,
    token: str = Depends(verify_panel_token),
):
    """Validate a route draft against current discovery without mutating it."""
    del token
    validation = await _validate_route(request.selected_models)
    return JSONResponse(
        content={
            "schema_version": MODEL_ROUTING_SCHEMA_VERSION,
            "alias": DEFAULT_VIRTUAL_MODEL_ALIAS,
            "validation": validation,
        }
    )


async def _save_validated_route(request: VirtualModelPoolUpdateRequest) -> dict:
    validation = await _validate_route(request.selected_models)
    if not validation["valid"]:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "model_route_invalid",
                "validation": validation,
            },
        )
    return await save_virtual_model_pool(request.selected_models, enabled=request.enabled)


@router.post(f"/api/model-routes/{DEFAULT_VIRTUAL_MODEL_ALIAS}", status_code=201)
async def create_default_model_pool(
    request: VirtualModelPoolUpdateRequest,
    token: str = Depends(verify_panel_token),
):
    """Create the default virtual route when it is not already configured."""
    del token
    async with _model_pool_write_lock:
        current = _ensure_decorated_pool(await get_virtual_model_pool())
        if current["configured"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "model_route_already_exists",
                    "message": "The polaris route already exists. Reload it before editing.",
                    "current_revision": current["revision"],
                },
            )
        pool = await _save_validated_route(request)
    return JSONResponse(
        content={"code": "model_route_created", "pool": pool},
        status_code=201,
    )


@router.put(f"/api/model-pools/{DEFAULT_VIRTUAL_MODEL_ALIAS}")
async def update_default_model_pool(
    request: VirtualModelPoolUpdateRequest,
    token: str = Depends(verify_panel_token),
):
    """Compatibility upsert for the ordered default virtual-model members."""
    try:
        async with _model_pool_write_lock:
            pool = await save_virtual_model_pool(
                request.selected_models,
                enabled=request.enabled,
            )
        return JSONResponse(
            content={
                "message": f'Virtual model "{DEFAULT_VIRTUAL_MODEL_ALIAS}" updated.',
                "pool": pool,
            }
        )
    except ModelPoolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.error(f"Failed to update the virtual model pool: {exc}")
        raise HTTPException(
            status_code=500,
            detail="The virtual model configuration could not be saved.",
        ) from exc


@router.patch(f"/api/model-routes/{DEFAULT_VIRTUAL_MODEL_ALIAS}")
async def patch_default_model_route(
    request: VirtualModelPoolUpdateRequest,
    token: str = Depends(verify_panel_token),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    """Validate and update the route under an optimistic revision guard."""
    del token
    async with _model_pool_write_lock:
        current = _ensure_decorated_pool(await get_virtual_model_pool())
        _require_current_revision(current, if_match, required=True)
        if not current["configured"]:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "model_route_not_found",
                    "message": "The polaris route is not configured.",
                },
            )
        pool = await _save_validated_route(request)
    return JSONResponse(content={"message": 'Virtual model "polaris" updated.', "pool": pool})


@router.delete(f"/api/model-routes/{DEFAULT_VIRTUAL_MODEL_ALIAS}")
async def delete_default_model_pool(
    token: str = Depends(verify_panel_token),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    """Delete the configured route while retaining its stable public alias."""
    del token
    async with _model_pool_write_lock:
        current = _ensure_decorated_pool(await get_virtual_model_pool())
        _require_current_revision(current, if_match, required=True)
        if not current["configured"]:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "model_route_not_found",
                    "message": "The polaris route is not configured.",
                },
            )
        pool = await save_virtual_model_pool([], enabled=False)
    return JSONResponse(content={"code": "model_route_deleted", "pool": pool})
