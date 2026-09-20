from core.model_pool import get_public_virtual_models, model_catalog_service
from core.models import model_to_dict
from core.router.base_router import create_gemini_model_list, create_openai_model_list
from core.utils import authenticate_flexible, get_base_model_from_feature_model
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from log import log

router = APIRouter()


async def get_primary_models_with_features():
    """Advertise provider models and configured aliases, not synthetic feature IDs.

    Feature prefixes remain accepted by inference routes for explicit opt-in use.
    """

    catalog_entries = await model_catalog_service.get_catalog()
    if not catalog_entries:
        log.warning("[provider model list] No concrete provider models are currently available.")
    models = list(dict.fromkeys(entry.model_id for entry in catalog_entries))

    for virtual_model in await get_public_virtual_models():
        if virtual_model not in models:
            models.append(virtual_model)

    route_label = "route" if len(models) == 1 else "routes"
    log.info(
        f"[provider model list] Generated {len(models)} provider model {route_label}, "
        "including configured aliases."
    )
    return models


@router.get("/v1beta/models")
async def list_gemini_models(token: str = Depends(authenticate_flexible)):
    models = await get_primary_models_with_features()
    log.info("[provider model list] Returning the model list in Gemini format.")
    return JSONResponse(
        content=create_gemini_model_list(
            models, base_name_extractor=get_base_model_from_feature_model
        )
    )


@router.get("/v1/models")
async def list_openai_models(token: str = Depends(authenticate_flexible)):
    models = await get_primary_models_with_features()
    log.info("[provider model list] Returning the model list in OpenAI format.")
    model_list = create_openai_model_list(models, owned_by="provider")
    return JSONResponse(
        content={"object": "list", "data": [model_to_dict(model) for model in model_list.data]}
    )
