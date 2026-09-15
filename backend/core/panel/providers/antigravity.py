"""Google Antigravity provider configuration routes."""

import config
from core.google_endpoint_validation import (
    normalize_google_api_base_url,
    normalize_google_oauth_base_url,
)
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
    "antigravity_user_agent",
    "antigravity_payload_user_agent",
}

GOOGLE_SHARED_CONFIG_KEYS = {
    "oauth_url",
    "google_apis_url",
}

GOOGLE_COMPATIBILITY_CONFIG_KEYS = {
    "resource_manager_url",
    "service_usage_url",
    "code_assist_client_id",
    "code_assist_client_secret",
    "code_assist_endpoint",
}

GOOGLE_CONFIG_KEYS = GOOGLE_SHARED_CONFIG_KEYS | GOOGLE_COMPATIBILITY_CONFIG_KEYS

ANTIGRAVITY_SECRET_CONFIG_KEYS = {"antigravity_client_secret"}
GOOGLE_SECRET_CONFIG_KEYS = {"code_assist_client_secret"}


def redact_antigravity_config(config_values: dict) -> dict:
    """Return provider settings without reflecting stored secrets to the browser."""
    return _redact_config(config_values, ANTIGRAVITY_SECRET_CONFIG_KEYS)


def redact_google_config(config_values: dict) -> dict:
    """Return shared Google settings without reflecting stored secrets."""
    return _redact_config(config_values, GOOGLE_SECRET_CONFIG_KEYS)


def _redact_config(config_values: dict, secret_keys: set[str]) -> dict:
    safe_config = dict(config_values)
    configured_secrets = sorted(key for key in secret_keys if bool(safe_config.get(key)))
    for key in secret_keys:
        if key in safe_config:
            safe_config[key] = ""
    return {"config": safe_config, "configured_secrets": configured_secrets}


async def _current_antigravity_config() -> dict:
    client_id, client_secret = await config.get_antigravity_oauth_client_config()
    return {
        "antigravity_client_id": client_id,
        "antigravity_client_secret": client_secret,
        "antigravity_api_url": await config.get_antigravity_api_url(),
        "antigravity_user_agent": await config.get_antigravity_user_agent(),
        "antigravity_payload_user_agent": await config.get_antigravity_payload_user_agent(),
    }


async def _current_google_config() -> dict:
    client_id, client_secret = await config.get_code_assist_oauth_client_config()
    return {
        "oauth_url": await config.get_oauth_proxy_url(),
        "google_apis_url": await config.get_googleapis_proxy_url(),
        "resource_manager_url": await config.get_resource_manager_api_url(),
        "service_usage_url": await config.get_service_usage_api_url(),
        "code_assist_client_id": client_id,
        "code_assist_client_secret": client_secret,
        "code_assist_endpoint": await config.get_code_assist_endpoint(),
    }


def _validated_updates(
    new_config: dict,
    *,
    allowed_keys: set[str],
    secret_keys: set[str],
    scope_label: str,
) -> dict:
    unknown_keys = sorted(set(new_config) - allowed_keys)
    if unknown_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported {scope_label} setting(s): {', '.join(unknown_keys)}.",
        )

    validated = {}
    for key, value in new_config.items():
        if not isinstance(value, str):
            raise HTTPException(
                status_code=400, detail=f"{scope_label} setting '{key}' must be a string."
            )
        if key in secret_keys and not value.strip():
            continue
        try:
            if key in {"oauth_url", "google_apis_url"}:
                value = normalize_google_oauth_base_url(value, setting_name=key)
            elif key in {
                "antigravity_api_url",
                "resource_manager_url",
                "service_usage_url",
                "code_assist_endpoint",
            }:
                value = normalize_google_api_base_url(value, setting_name=key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        validated[key] = value
    return validated


async def _save_config_values(
    new_config: dict,
    *,
    allowed_keys: set[str],
    secret_keys: set[str],
    scope_label: str,
) -> tuple[dict, list[str]]:
    validated = _validated_updates(
        new_config,
        allowed_keys=allowed_keys,
        secret_keys=secret_keys,
        scope_label=scope_label,
    )
    env_locked = get_env_locked_keys() & allowed_keys
    storage_adapter = await get_storage_adapter()
    saved_config = {}
    for key, value in validated.items():
        if key in env_locked:
            continue
        await storage_adapter.set_config(key, value)
        saved_config[key] = value
    if saved_config:
        await config.reload_config()
    return saved_config, sorted(env_locked)


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
        saved_config, env_locked = await _save_config_values(
            request.config or {},
            allowed_keys=ANTIGRAVITY_CONFIG_KEYS,
            secret_keys=ANTIGRAVITY_SECRET_CONFIG_KEYS,
            scope_label="Google Antigravity",
        )

        content = redact_antigravity_config(saved_config)
        content.update(
            {
                "message": "Google Antigravity settings saved.",
                "saved_config": content.pop("config"),
                "env_locked": env_locked,
            }
        )
        return JSONResponse(content=content)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to save Google Antigravity configuration: {e}")
        raise internal_server_error() from e


@router.get("/api/providers/google/config")
async def get_google_config(token: str = Depends(verify_panel_token)):
    """Return shared Google OAuth and legacy Code Assist compatibility settings."""
    try:
        env_locked = get_env_locked_keys() & GOOGLE_CONFIG_KEYS
        content = redact_google_config(await _current_google_config())
        content["env_locked"] = sorted(env_locked)
        return JSONResponse(content=content)
    except Exception as e:
        log.error(f"Failed to retrieve shared Google configuration: {e}")
        raise internal_server_error() from e


@router.post("/api/providers/google/config")
async def save_google_config(request: ConfigSaveRequest, token: str = Depends(verify_panel_token)):
    """Save shared Google OAuth and legacy Code Assist compatibility settings."""
    try:
        saved_config, env_locked = await _save_config_values(
            request.config or {},
            allowed_keys=GOOGLE_CONFIG_KEYS,
            secret_keys=GOOGLE_SECRET_CONFIG_KEYS,
            scope_label="Google",
        )
        content = redact_google_config(saved_config)
        content.update(
            {
                "message": "Google settings saved.",
                "saved_config": content.pop("config"),
                "env_locked": env_locked,
            }
        )
        return JSONResponse(content=content)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to save shared Google configuration: {e}")
        raise internal_server_error() from e


@router.post("/api/providers/google/config/reset")
async def reset_google_config(scope: str, token: str = Depends(verify_panel_token)):
    """Reset one Google configuration scope without clearing the other scope."""
    try:
        reset_keys_by_scope = {
            "shared": GOOGLE_SHARED_CONFIG_KEYS,
            "compatibility": GOOGLE_COMPATIBILITY_CONFIG_KEYS,
        }
        reset_keys = reset_keys_by_scope.get(scope)
        if reset_keys is None:
            raise HTTPException(
                status_code=400,
                detail="Google reset scope must be 'shared' or 'compatibility'.",
            )

        all_env_locked = get_env_locked_keys() & GOOGLE_CONFIG_KEYS
        resettable_keys = reset_keys - all_env_locked
        storage_adapter = await get_storage_adapter()
        deleted_keys = []
        for key in sorted(resettable_keys):
            if await storage_adapter.delete_config(key):
                deleted_keys.append(key)
        if resettable_keys:
            await config.reload_config()

        content = redact_google_config(await _current_google_config())
        content.update(
            {
                "message": f"Google {scope} settings reset to defaults.",
                "reset_config": deleted_keys,
                "env_locked": sorted(all_env_locked),
            }
        )
        return JSONResponse(content=content)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to reset shared Google configuration: {e}")
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
