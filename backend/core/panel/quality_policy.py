"""Authenticated management API for the versioned AI quality policy."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

import config
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.quality_policy import (
    LOCKED_SETTING_PATHS,
    POLICY_STORAGE_KEY,
    QualityPolicyError,
    assess_policy_warnings,
    build_policy_document,
    changed_locked_fields,
    get_profile_defaults,
    load_policy_document,
    preview_policy,
    settings_from_legacy,
)
from core.quality_policy_runtime import (
    apply_environment_overrides,
    read_legacy_quality_settings,
)
from core.storage_adapter import get_storage_adapter
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends
from log import log
from pydantic import BaseModel, ConfigDict, Field

from .utils import get_env_locked_keys

router = APIRouter(prefix="/api/quality-policy", tags=["quality-policy"])
_policy_update_lock = asyncio.Lock()


class QualityPolicyUpdateRequest(BaseModel):
    revision: int = Field(ge=0)
    profile: Literal["quality", "balanced", "capacity", "custom"]
    settings: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class QualityPolicyPreviewRequest(QualityPolicyUpdateRequest):
    estimated_input_tokens: int = Field(ge=0, le=2_000_000)
    message_count: int = Field(ge=0, le=100_000)
    tool_count: int = Field(ge=0, le=10_000)
    has_system_instruction: bool
    has_tool_pairs: bool


def _error(status_code: int, code: str, message: str, **details) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, **details}},
    )


def _unavailable(operation: str, exc: Exception) -> JSONResponse:
    log.error(
        f"Quality policy {operation} failed ({type(exc).__name__}); "
        "the exception detail was withheld from the API response."
    )
    return _error(
        503,
        "quality_policy_unavailable",
        "The quality policy service is temporarily unavailable.",
    )


async def _load_current_policy(storage, legacy: dict[str, Any]) -> dict[str, Any]:
    stored = await storage.get_config(POLICY_STORAGE_KEY, None)
    return load_policy_document(stored, legacy)


def _policy_response(
    policy: dict[str, Any], legacy: dict[str, Any], env_locked: set[str]
) -> dict[str, Any]:
    effective_settings, overrides = apply_environment_overrides(
        policy["settings"], legacy, env_locked
    )
    return {
        "policy": policy,
        "effective_settings": effective_settings,
        "env_locked": sorted(env_locked & set(LOCKED_SETTING_PATHS)),
        "environment_overrides": overrides,
        "profile_defaults": get_profile_defaults(),
        "application": {
            "mode": "live",
            "restart_required": False,
            "precedence": ["environment", "global_policy", "virtual_key", "request"],
            "compression_restrictions": {
                "virtual_key": ["inherit", "disabled"],
                "request": ["inherit", "disabled"],
            },
        },
        "warnings": assess_policy_warnings(effective_settings),
        "runtime_active": True,
        "runtime_source": (
            "versioned_policy" if policy["source"] == "stored" else "legacy_projection"
        ),
    }


@router.get("")
async def get_quality_policy(token: str = Depends(verify_panel_token)):
    del token
    try:
        storage = await get_storage_adapter()
        legacy = await read_legacy_quality_settings()
        policy = await _load_current_policy(storage, legacy)
        return JSONResponse(content=_policy_response(policy, legacy, get_env_locked_keys()))
    except QualityPolicyError as exc:
        return _error(500, exc.code, str(exc))
    except Exception as exc:
        return _unavailable("read", exc)


@router.put("")
async def update_quality_policy(
    request: QualityPolicyUpdateRequest,
    token: str = Depends(verify_panel_token),
):
    del token
    try:
        desired = build_policy_document(
            profile=request.profile,
            revision=request.revision + 1,
            settings=request.settings,
        )
    except QualityPolicyError as exc:
        return _error(400, exc.code, str(exc))

    try:
        async with _policy_update_lock:
            storage = await get_storage_adapter()
            legacy = await read_legacy_quality_settings()
            current = await _load_current_policy(storage, legacy)

            if request.revision != current["revision"]:
                return _error(
                    409,
                    "quality_policy_revision_conflict",
                    "The quality policy changed after it was loaded.",
                    current_revision=current["revision"],
                )

            locked = changed_locked_fields(
                settings_from_legacy(legacy),
                desired["settings"],
                get_env_locked_keys(),
            )
            if locked and request.profile == "custom":
                return _error(
                    423,
                    "quality_policy_environment_locked",
                    "The requested profile changes settings managed by the runtime environment.",
                    fields=locked,
                )

            if not await storage.set_config(POLICY_STORAGE_KEY, desired):
                return _error(
                    500, "quality_policy_write_failed", "The quality policy was not saved."
                )
            config.set_cached_config_value(POLICY_STORAGE_KEY, desired)
    except QualityPolicyError as exc:
        return _error(500, exc.code, str(exc))
    except Exception as exc:
        return _unavailable("update", exc)

    return JSONResponse(content=_policy_response(desired, legacy, get_env_locked_keys()))


@router.post("/preview")
async def preview_quality_policy(
    request: QualityPolicyPreviewRequest,
    token: str = Depends(verify_panel_token),
):
    del token
    try:
        storage = await get_storage_adapter()
        legacy = await read_legacy_quality_settings()
        current = await _load_current_policy(storage, legacy)
        if request.revision != current["revision"]:
            return _error(
                409,
                "quality_policy_revision_conflict",
                "The quality policy changed after it was loaded.",
                current_revision=current["revision"],
            )
        proposed = build_policy_document(
            profile=request.profile,
            revision=request.revision,
            settings=request.settings,
            source="preview",
        )
        env_locked = get_env_locked_keys()
        effective_settings, conflicts = apply_environment_overrides(
            proposed["settings"], legacy, env_locked
        )
        preview = preview_policy(
            {**proposed, "settings": effective_settings},
            {
                "estimated_input_tokens": request.estimated_input_tokens,
                "message_count": request.message_count,
                "tool_count": request.tool_count,
                "has_system_instruction": request.has_system_instruction,
                "has_tool_pairs": request.has_tool_pairs,
            },
        )
    except QualityPolicyError as exc:
        return _error(400, exc.code, str(exc))
    except Exception as exc:
        return _unavailable("preview", exc)

    return JSONResponse(
        content={
            "preview": preview,
            "can_apply": request.profile != "custom" or not conflicts,
            "applies_with_environment_overrides": bool(conflicts),
            "environment_conflicts": conflicts,
            "env_locked": sorted(env_locked & set(LOCKED_SETTING_PATHS)),
        }
    )
