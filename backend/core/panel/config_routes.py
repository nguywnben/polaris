import asyncio
import os

import config
from core.auth import verify_password
from core.configuration_schema import (
    CONFIGURATION_FIELDS,
    ApplyMode,
    ConfigurationError,
    settings_metadata,
    validate_config_updates,
)
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.identity import get_session_service
from core.keep_alive import keep_alive_service
from core.models import AccessCredentialsUpdateRequest, ConfigSaveRequest
from core.passwords import hash_password
from core.storage_adapter import get_storage_adapter
from core.utils import (
    create_panel_session_token,
    set_panel_session_cookie,
    verify_panel_token,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from log import configure_logging, log

from .utils import get_env_locked_keys, internal_server_error

router = APIRouter(prefix="/api/config", tags=["config"])
_access_credentials_update_lock = asyncio.Lock()

ACCESS_SECRET_KEYS = {
    "api_password",
    "password",
    *(
        field.config_key
        for field in CONFIGURATION_FIELDS
        if field.config_key and field.surface == "access" and field.secret
    ),
}
CONFIGURATION_SECRET_KEYS = {
    "api_password",
    "password",
    *(field.config_key for field in CONFIGURATION_FIELDS if field.config_key and field.secret),
}
RESTART_REQUIRED_CONFIG_KEYS = {
    field.config_key
    for field in CONFIGURATION_FIELDS
    if field.config_key and field.apply is ApplyMode.RESTART
}
PROVIDER_SPECIFIC_CONFIG_KEYS = {
    field.config_key
    for field in CONFIGURATION_FIELDS
    if field.config_key and field.surface == "provider"
}
POLICY_ONLY_CONFIG_KEYS = {
    field.config_key
    for field in CONFIGURATION_FIELDS
    if field.config_key and field.surface == "quality"
}
ALLOWED_CONFIG_KEYS = {
    field.config_key
    for field in CONFIGURATION_FIELDS
    if field.config_key and field.surface == "system"
}
DEFAULT_BACKED_CONFIG_KEYS = {
    "code_assist_client_id",
    "code_assist_client_secret",
}
RESETTABLE_CONFIG_KEYS = set(ALLOWED_CONFIG_KEYS)
PRESERVED_RESET_KEYS = {
    "api_key",
    "panel_password",
}


def _redact_access_secrets(current_config: dict) -> dict:
    """Return control-panel configuration without any reusable secret."""
    public_config = dict(current_config)
    for key in CONFIGURATION_SECRET_KEYS:
        if key in public_config:
            public_config[f"{key}_configured"] = bool(public_config.get(key))
        public_config.pop(key, None)
    return public_config


def _classify_config_updates(keys) -> dict:
    """Separate immediately applied settings from process startup settings."""
    normalized = set(keys)
    return {
        "hot_updated": sorted(normalized - RESTART_REQUIRED_CONFIG_KEYS),
        "restart_required": sorted(normalized & RESTART_REQUIRED_CONFIG_KEYS),
    }


@router.get("/get")
async def get_config(token: str = Depends(verify_panel_token)):
    try:
        current_config = {}

        current_config["code_assist_endpoint"] = await config.get_code_assist_endpoint()
        current_config["credentials_dir"] = await config.get_credentials_dir()
        current_config["proxy"] = await config.get_proxy_config() or ""

        (
            code_assist_client_id,
            code_assist_client_secret,
        ) = await config.get_code_assist_oauth_client_config()
        current_config["code_assist_client_id"] = code_assist_client_id
        current_config["code_assist_client_secret"] = code_assist_client_secret

        current_config["auto_disable_enabled"] = await config.get_auto_disable_enabled()
        current_config["auto_disable_error_codes"] = await config.get_auto_disable_error_codes()

        current_config["retry_429_max_retries"] = await config.get_retry_429_max_retries()
        current_config["retry_429_enabled"] = await config.get_retry_429_enabled()
        current_config["retry_429_interval"] = await config.get_retry_429_interval()

        current_config[
            "anti_truncation_max_attempts"
        ] = await config.get_anti_truncation_max_attempts()

        compression_config = await config.get_token_compression_config()
        current_config["token_compression_enabled"] = compression_config["enabled"]
        current_config["token_compression_threshold"] = compression_config["threshold_tokens"]
        current_config["token_compression_target"] = compression_config["target_tokens"]
        current_config["token_compression_min_recent_turns"] = compression_config[
            "min_recent_turns"
        ]

        routing_policy = await config.get_routing_policy()
        current_config["routing_strategy"] = routing_policy["strategy"]
        current_config["preferred_provider"] = routing_policy["preferred_provider"]
        current_config["upstream_timeout_seconds"] = await config.get_upstream_timeout_seconds()

        log_config = await config.get_log_config()
        current_config["log_level"] = log_config["level"]
        current_config["log_max_mb"] = log_config["max_mb"]
        current_config["log_backup_count"] = log_config["backup_count"]

        current_config["compatibility_mode_enabled"] = await config.get_compatibility_mode_enabled()

        current_config[
            "return_thoughts_to_frontend"
        ] = await config.get_return_thoughts_to_frontend()

        current_config["keepalive_url"] = await config.get_keepalive_url()
        current_config["keepalive_interval"] = await config.get_keepalive_interval()

        current_config["host"] = await config.get_server_host()
        current_config["port"] = await config.get_server_port()
        current_config["panel_password"] = await config.get_panel_password()

        storage_adapter = await get_storage_adapter()
        storage_config = await storage_adapter.get_all_config()

        env_locked_keys = get_env_locked_keys()

        for key, value in storage_config.items():
            if key in DEFAULT_BACKED_CONFIG_KEYS and (
                value is None or (isinstance(value, str) and not value.strip())
            ):
                continue
            if key in ALLOWED_CONFIG_KEYS and key not in env_locked_keys:
                current_config[key] = value

        return JSONResponse(
            content={
                "config": _redact_access_secrets(current_config),
                "env_locked": sorted(env_locked_keys),
                "metadata": settings_metadata(os.environ),
            }
        )

    except Exception as e:
        log.error(f"Failed to retrieve configuration: {e}")
        raise internal_server_error() from e


@router.post("/save")
async def save_config(request: ConfigSaveRequest, token: str = Depends(verify_panel_token)):
    try:
        new_config = request.config

        log.debug(f"Received configuration data: {list(new_config.keys())}")

        if ACCESS_SECRET_KEYS & set(new_config):
            raise HTTPException(
                status_code=400,
                detail="Access passwords must be updated through the dedicated access endpoint.",
            )

        unknown_keys = sorted(set(new_config) - ALLOWED_CONFIG_KEYS)
        if unknown_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported configuration key(s): {', '.join(unknown_keys)}",
            )

        try:
            new_config = validate_config_updates(new_config, surface="system")
        except ConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        env_locked_keys = get_env_locked_keys()

        storage_adapter = await get_storage_adapter()
        saved_config = {}
        for key, value in new_config.items():
            if key not in env_locked_keys:
                await storage_adapter.set_config(key, value)
                saved_config[key] = value

        await config.reload_config()

        keepalive_keys = {"keepalive_url", "keepalive_interval"}
        if keepalive_keys & set(new_config.keys()):
            try:
                await keep_alive_service.restart()
            except Exception as e:
                log.warning(f"Failed to restart keep-alive service: {e}")

        if {"log_level", "log_max_mb", "log_backup_count"} & set(saved_config):
            log_config = await config.get_log_config()
            configure_logging(
                log_config["level"],
                log_config["max_mb"],
                log_config["backup_count"],
            )

        # Build response message
        update_classification = _classify_config_updates(saved_config)
        response_data = {
            "message": "Configuration saved.",
            "saved_config": saved_config,
            **update_classification,
        }
        if update_classification["restart_required"]:
            response_data["restart_notice"] = (
                "Restart the application to apply listener or credential storage changes."
            )

        return JSONResponse(content=response_data)

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to save configuration: {e}")
        raise internal_server_error() from e


@router.post("/access")
async def update_access_credentials(
    payload: AccessCredentialsUpdateRequest,
    request: Request,
    token: str = Depends(verify_panel_token),
):
    """Update the panel password without exposing its current value."""
    async with _access_credentials_update_lock:
        if not await verify_password(payload.current_password):
            raise HTTPException(
                status_code=401, detail="The current console password is incorrect."
            )

        requested_updates = {
            "panel_password": (
                payload.panel_password,
                payload.panel_password_confirm,
                "Panel password",
            ),
        }
        updates = {}
        for key, (value, confirmation, label) in requested_updates.items():
            if value is None or value == "":
                continue
            if value != confirmation:
                raise HTTPException(status_code=400, detail=f"{label} confirmation does not match.")
            if len(value) < 8 or len(value) > 256:
                raise HTTPException(
                    status_code=400,
                    detail=f"{label} must contain between 8 and 256 characters.",
                )
            updates[key] = value

        if not updates:
            raise HTTPException(status_code=400, detail="Enter at least one new password.")

        env_locked_keys = get_env_locked_keys()
        locked_updates = sorted(set(updates) & env_locked_keys)
        if locked_updates:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The requested password is managed by the runtime environment and "
                    "cannot be changed from the console."
                ),
            )

        try:
            if "panel_password" in updates:
                await get_session_service().revoke_local_owner_sessions()
            storage_adapter = await get_storage_adapter()
            for key, value in updates.items():
                await storage_adapter.set_config(key, hash_password(value))
            await config.reload_config()

            response_data = {
                "message": "Console password updated.",
                "updated": sorted(updates),
            }
            response = JSONResponse(content=response_data)
            if "panel_password" in updates:
                set_panel_session_cookie(
                    response,
                    await create_panel_session_token(),
                    request,
                )

            log.info("Control-panel password updated.")
            return response
        except HTTPException:
            raise
        except Exception as exc:
            log.error(f"Failed to update the control-panel password: {exc}")
            raise HTTPException(status_code=500, detail="Failed to update the console password.")


@router.post("/reset")
async def reset_config(token: str = Depends(verify_panel_token)):
    """Reset global configuration overrides while preserving access secrets."""
    try:
        env_locked_keys = get_env_locked_keys()
        resettable_keys = RESETTABLE_CONFIG_KEYS - env_locked_keys

        storage_adapter = await get_storage_adapter()
        deleted_keys = []
        for key in sorted(resettable_keys):
            if await storage_adapter.delete_config(key):
                deleted_keys.append(key)

        await config.reload_config()

        try:
            await keep_alive_service.restart()
        except Exception as e:
            log.warning(f"Failed to restart keep-alive service after configuration reset: {e}")

        log_config = await config.get_log_config()
        configure_logging(
            log_config["level"],
            log_config["max_mb"],
            log_config["backup_count"],
        )

        return JSONResponse(
            content={
                "message": "System configuration reset to defaults. Access passwords and the generated API key were preserved.",
                "reset_config": deleted_keys,
                "env_locked": sorted(env_locked_keys & RESETTABLE_CONFIG_KEYS),
                "preserved": sorted(PRESERVED_RESET_KEYS),
                **_classify_config_updates(deleted_keys),
            }
        )

    except Exception as e:
        log.error(f"Failed to reset configuration: {e}")
        raise internal_server_error() from e
