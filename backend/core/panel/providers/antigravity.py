"""Google Antigravity provider configuration routes."""

import config
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.models import ConfigSaveRequest
from core.storage_adapter import get_storage_adapter
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, HTTPException
from log import log

from ..utils import get_env_locked_keys, internal_server_error

router = APIRouter(tags=["provider-antigravity"])

ANTIGRAVITY_CONFIG_KEYS = {
    "antigravity_client_id",
    "antigravity_client_secret",
    "antigravity_api_url",
    "oauth_url",
    "google_apis_url",
    "resource_manager_url",
    "service_usage_url",
    "antigravity_user_agent",
    "antigravity_payload_user_agent",
    "stream_to_nonstream",
    "switch_credential_enabled",
}

STRING_KEYS = {
    "antigravity_client_id",
    "antigravity_client_secret",
    "antigravity_api_url",
    "oauth_url",
    "google_apis_url",
    "resource_manager_url",
    "service_usage_url",
    "antigravity_user_agent",
    "antigravity_payload_user_agent",
}

BOOLEAN_KEYS = {
    "stream_to_nonstream",
    "switch_credential_enabled",
}

SECRET_CONFIG_KEYS = {"antigravity_client_secret"}


def redact_antigravity_config(config_values: dict) -> dict:
    """Return provider settings without reflecting stored secrets to the browser."""
    safe_config = dict(config_values)
    configured_secrets = sorted(key for key in SECRET_CONFIG_KEYS if bool(safe_config.get(key)))
    for key in SECRET_CONFIG_KEYS:
        if key in safe_config:
            safe_config[key] = ""
    return {"config": safe_config, "configured_secrets": configured_secrets}


async def _current_antigravity_config() -> dict:
    client_id, client_secret = await config.get_antigravity_oauth_client_config()
    return {
        "antigravity_client_id": client_id,
        "antigravity_client_secret": client_secret,
        "antigravity_api_url": await config.get_antigravity_api_url(),
        "oauth_url": await config.get_oauth_proxy_url(),
        "google_apis_url": await config.get_googleapis_proxy_url(),
        "resource_manager_url": await config.get_resource_manager_api_url(),
        "service_usage_url": await config.get_service_usage_api_url(),
        "antigravity_user_agent": await config.get_antigravity_user_agent(),
        "antigravity_payload_user_agent": await config.get_antigravity_payload_user_agent(),
        "stream_to_nonstream": await config.get_antigravity_stream_to_nonstream(),
        "switch_credential_enabled": await config.get_antigravity_switch_credential_enabled(),
    }


@router.get("/api/providers/antigravity/config")
async def get_antigravity_config(token: str = Depends(verify_panel_token)):
    """Return Google Antigravity provider settings for the provider setup UI."""
    try:
        env_locked = get_env_locked_keys() & ANTIGRAVITY_CONFIG_KEYS
        content = redact_antigravity_config(await _current_antigravity_config())
        content["env_locked"] = sorted(env_locked)
        return JSONResponse(content=content)
    except Exception as e:
        log.error(f"Failed to retrieve Google Antigravity configuration: {e}")
        raise internal_server_error() from e


@router.post("/api/providers/antigravity/config")
async def save_antigravity_config(
    request: ConfigSaveRequest, token: str = Depends(verify_panel_token)
):
    """Save Google Antigravity provider settings from the provider setup UI."""
    try:
        new_config = request.config or {}
        unknown_keys = sorted(set(new_config) - ANTIGRAVITY_CONFIG_KEYS)
        if unknown_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported Google Antigravity setting(s): {', '.join(unknown_keys)}.",
            )

        for key in STRING_KEYS & set(new_config):
            if not isinstance(new_config[key], str):
                raise HTTPException(
                    status_code=400, detail=f"Google Antigravity setting '{key}' must be a string."
                )

        for key in BOOLEAN_KEYS & set(new_config):
            if not isinstance(new_config[key], bool):
                raise HTTPException(
                    status_code=400, detail=f"Google Antigravity setting '{key}' must be a boolean."
                )

        env_locked = get_env_locked_keys() & ANTIGRAVITY_CONFIG_KEYS
        storage_adapter = await get_storage_adapter()

        saved_config = {}
        for key, value in new_config.items():
            if key in env_locked:
                continue
            await storage_adapter.set_config(key, value)
            saved_config[key] = value

        await config.reload_config()

        content = redact_antigravity_config(saved_config)
        content.update(
            {
                "message": "Google Antigravity settings saved.",
                "saved_config": content.pop("config"),
                "env_locked": sorted(env_locked),
            }
        )
        return JSONResponse(content=content)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to save Google Antigravity configuration: {e}")
        raise internal_server_error() from e


@router.post("/api/providers/antigravity/config/reset")
async def reset_antigravity_config(token: str = Depends(verify_panel_token)):
    """Reset Google Antigravity provider settings to built-in or environment defaults."""
    try:
        env_locked = get_env_locked_keys() & ANTIGRAVITY_CONFIG_KEYS
        storage_adapter = await get_storage_adapter()

        deleted_keys = []
        for key in sorted(ANTIGRAVITY_CONFIG_KEYS - env_locked):
            if await storage_adapter.delete_config(key):
                deleted_keys.append(key)

        await config.reload_config()

        content = redact_antigravity_config(await _current_antigravity_config())
        content.update(
            {
                "message": "Google Antigravity settings reset to defaults.",
                "reset_config": deleted_keys,
                "env_locked": sorted(env_locked),
            }
        )
        return JSONResponse(content=content)
    except Exception as e:
        log.error(f"Failed to reset Google Antigravity configuration: {e}")
        raise internal_server_error() from e
