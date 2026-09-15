"""Claude Code and Claude Platform management console routes."""

import io
import json
import zipfile
from typing import List, Tuple

import config
from core.anthropic import (
    AnthropicError,
    complete_claude_oauth,
    create_claude_oauth_url,
    normalize_anthropic_api_url,
    normalize_claude_oauth_url,
    validate_anthropic_api_key,
)
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.models import ClaudeOAuthCodeRequest, ClaudePlatformCredentialRequest, ConfigSaveRequest
from core.pool_import import PoolImportError, restore_anthropic_credential
from core.provider_import_normalization import normalize_provider_import
from core.provider_registry import ANTHROPIC, CLAUDE_CODE, CLAUDE_PLATFORM, api_key_fingerprint
from core.provider_store import store_claude_platform_credential
from core.storage_adapter import get_storage_adapter
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from log import log

from ..utils import get_env_locked_keys
from .import_utils import (
    MAX_PROVIDER_IMPORT_ENTRIES,
    MAX_PROVIDER_IMPORT_FILE_BYTES,
    MAX_PROVIDER_IMPORT_UNCOMPRESSED_BYTES,
    _safe_import_name,
)

router = APIRouter(tags=["provider-anthropic"])

ANTHROPIC_CONFIG_KEYS = {
    "anthropic_api_url",
    "claude_oauth_authorize_url",
    "claude_oauth_token_url",
    "claude_client_id",
    "claude_user_agent",
}
ANTHROPIC_CONFIG_SCOPES = {
    "shared": {"anthropic_api_url", "claude_user_agent"},
    "platform": set(),
    "code": {
        "claude_oauth_authorize_url",
        "claude_oauth_token_url",
        "claude_client_id",
    },
}


async def _current_anthropic_config() -> dict:
    return {
        "anthropic_api_url": await config.get_anthropic_api_url(),
        "claude_oauth_authorize_url": await config.get_claude_oauth_authorize_url(),
        "claude_oauth_token_url": await config.get_claude_oauth_token_url(),
        "claude_client_id": await config.get_claude_client_id(),
        "claude_user_agent": await config.get_claude_user_agent(),
    }


@router.get("/api/providers/anthropic/config")
async def get_anthropic_config(token: str = Depends(verify_panel_token)):
    env_locked = get_env_locked_keys() & ANTHROPIC_CONFIG_KEYS
    return JSONResponse(
        content={"config": await _current_anthropic_config(), "env_locked": sorted(env_locked)}
    )


@router.post("/api/providers/anthropic/config")
async def save_anthropic_config(
    request: ConfigSaveRequest,
    token: str = Depends(verify_panel_token),
):
    new_config = request.config or {}
    unknown_keys = sorted(set(new_config) - ANTHROPIC_CONFIG_KEYS)
    if unknown_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported Anthropic setting(s): {', '.join(unknown_keys)}.",
        )
    locked = get_env_locked_keys() & ANTHROPIC_CONFIG_KEYS
    normalized = {}
    try:
        for key in new_config.keys() - locked:
            value = str(new_config[key] or "").strip()
            if key == "anthropic_api_url":
                value = normalize_anthropic_api_url(value)
            elif key in {"claude_oauth_authorize_url", "claude_oauth_token_url"}:
                label = (
                    "Claude authorization endpoint"
                    if key == "claude_oauth_authorize_url"
                    else "Claude token endpoint"
                )
                value = normalize_claude_oauth_url(value, label)
            elif not value:
                raise ValueError("Anthropic client settings cannot be empty.")
            normalized[key] = value
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    storage_adapter = await get_storage_adapter()
    for key, value in normalized.items():
        if key in new_config and key not in locked:
            await storage_adapter.set_config(key, value)
    await config.reload_config()
    return JSONResponse(
        content={
            "message": "Anthropic provider settings saved.",
            "config": await _current_anthropic_config(),
            "env_locked": sorted(locked),
        }
    )


@router.post("/api/providers/anthropic/config/reset")
async def reset_anthropic_config(
    scope: str = "",
    token: str = Depends(verify_panel_token),
):
    normalized_scope = str(scope or "").strip().lower()
    if normalized_scope and normalized_scope not in ANTHROPIC_CONFIG_SCOPES:
        raise HTTPException(
            status_code=400,
            detail="Anthropic setting scope must be 'shared', 'platform', or 'code'.",
        )
    locked = get_env_locked_keys() & ANTHROPIC_CONFIG_KEYS
    storage_adapter = await get_storage_adapter()
    for key in ANTHROPIC_CONFIG_SCOPES.get(normalized_scope, ANTHROPIC_CONFIG_KEYS) - locked:
        await storage_adapter.delete_config(key)
    await config.reload_config()
    return JSONResponse(
        content={
            "message": "Anthropic provider settings reset to defaults.",
            "config": await _current_anthropic_config(),
            "env_locked": sorted(locked),
        }
    )


@router.post("/api/providers/anthropic/platform/credentials")
async def add_claude_platform_credential(
    request: ClaudePlatformCredentialRequest,
    token: str = Depends(verify_panel_token),
):
    try:
        validation = await validate_anthropic_api_key(request.api_key)
        saved = await store_claude_platform_credential(request.api_key, validation)
    except AnthropicError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    action = saved["action"]
    return JSONResponse(
        status_code=200 if action == "updated" else 201,
        content={
            "success": True,
            "credential_saved": True,
            "credential_action": action,
            "filename": saved["filename"],
            "provider": ANTHROPIC,
            "provider_variant": CLAUDE_PLATFORM,
            "label": saved["label"],
            "model_count": validation.model_count,
            "message": (
                "Claude Platform API key revalidated and updated in the provider pool."
                if action == "updated"
                else "Claude Platform API key added to the provider pool."
            ),
        },
    )


@router.post("/api/providers/anthropic/claude-code/oauth/start")
async def start_claude_oauth(token: str = Depends(verify_panel_token)):
    try:
        return JSONResponse(content={"success": True, **await create_claude_oauth_url()})
    except (AnthropicError, ValueError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc


@router.post("/api/providers/anthropic/claude-code/oauth/complete")
async def save_claude_oauth_credential(
    request: ClaudeOAuthCodeRequest,
    token: str = Depends(verify_panel_token),
):
    try:
        saved = await complete_claude_oauth(request.code, request.state)
    except AnthropicError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    action = saved["action"]
    return JSONResponse(
        status_code=200 if action == "updated" else 201,
        content={
            "success": True,
            "credential_saved": True,
            "credential_action": action,
            "filename": saved["filename"],
            "provider": ANTHROPIC,
            "provider_variant": CLAUDE_CODE,
            "label": saved["label"],
            "model_count": saved["model_count"],
            "message": (
                "Claude Code credential renewed in the provider pool."
                if action == "updated"
                else "Claude Code credential added to the provider pool."
            ),
        },
    )


def _parse_anthropic_json(content: bytes, source_name: str, credential_type: str) -> List[dict]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{source_name} is not valid UTF-8 JSON.") from exc
    values = payload if isinstance(payload, list) else [payload]
    candidates: List[dict] = []
    for index, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{source_name} must contain credential objects.")
        candidate_name = f"{source_name} #{index}" if len(values) > 1 else source_name
        if credential_type == "api_key":
            item = normalize_provider_import(item, "claude_platform")
            api_key = str(item.get("api_key") or "").strip()
            if not api_key:
                raise ValueError(f"{candidate_name}: API key is missing.")
            candidates.append({"source_filename": candidate_name, "api_key": api_key})
            continue
        normalized = normalize_provider_import(item, "claude_code")
        candidates.append({"source_filename": candidate_name, "payload": normalized})
    return candidates


async def _extract_anthropic_import_file(
    upload: UploadFile, credential_type: str
) -> Tuple[List[dict], List[dict]]:
    upload_name = _safe_import_name(upload.filename or "credential.json")
    content = await upload.read(MAX_PROVIDER_IMPORT_FILE_BYTES + 1)
    if len(content) > MAX_PROVIDER_IMPORT_FILE_BYTES:
        raise ValueError(f"{upload_name} exceeds the 2 MB file limit.")
    if upload_name.lower().endswith(".json"):
        return _parse_anthropic_json(content, upload_name, credential_type), []
    if not upload_name.lower().endswith(".zip"):
        raise ValueError(f"{upload_name} must be a JSON file or ZIP archive.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{upload_name} is not a valid ZIP archive.") from exc
    candidates: List[dict] = []
    errors: List[dict] = []
    with archive:
        entries = [
            entry
            for entry in archive.infolist()
            if not entry.is_dir() and entry.filename.lower().endswith(".json")
        ]
        if not entries:
            raise ValueError(f"{upload_name} does not contain any JSON files.")
        if len(entries) > MAX_PROVIDER_IMPORT_ENTRIES:
            raise ValueError(
                f"{upload_name} contains more than {MAX_PROVIDER_IMPORT_ENTRIES} JSON files."
            )
        if sum(entry.file_size for entry in entries) > MAX_PROVIDER_IMPORT_UNCOMPRESSED_BYTES:
            raise ValueError(f"{upload_name} exceeds the 5 MB uncompressed limit.")
        for entry in entries:
            source_name = f"{upload_name} / {_safe_import_name(entry.filename)}"
            try:
                if entry.flag_bits & 0x1:
                    raise ValueError("Encrypted ZIP entries are not supported.")
                if entry.file_size > MAX_PROVIDER_IMPORT_FILE_BYTES:
                    raise ValueError("Credential JSON exceeds the 2 MB file limit.")
                with archive.open(entry) as entry_file:
                    entry_content = entry_file.read(MAX_PROVIDER_IMPORT_FILE_BYTES + 1)
                candidates.extend(
                    _parse_anthropic_json(entry_content, source_name, credential_type)
                )
            except (RuntimeError, ValueError, zipfile.BadZipFile) as exc:
                errors.append(
                    {"status": "error", "source_filename": source_name, "message": str(exc)}
                )
    return candidates, errors


@router.post("/api/providers/anthropic/credentials/import")
async def import_anthropic_credentials(
    files: List[UploadFile] = File(...),
    credential_type: str = "api_key",
    token: str = Depends(verify_panel_token),
):
    normalized_type = str(credential_type or "").strip().lower()
    if normalized_type not in {"api_key", "oauth"}:
        raise HTTPException(status_code=400, detail="Credential type must be 'api_key' or 'oauth'.")
    if not files or len(files) > 50:
        raise HTTPException(status_code=400, detail="Select between one and 50 import files.")
    candidates: List[dict] = []
    results: List[dict] = []
    for upload in files:
        try:
            extracted, errors = await _extract_anthropic_import_file(upload, normalized_type)
            candidates.extend(extracted)
            results.extend(errors)
        except ValueError as exc:
            results.append(
                {
                    "status": "error",
                    "source_filename": _safe_import_name(upload.filename or "Import file"),
                    "message": str(exc),
                }
            )
    if len(candidates) > MAX_PROVIDER_IMPORT_ENTRIES:
        raise HTTPException(
            status_code=400,
            detail=f"A single import supports up to {MAX_PROVIDER_IMPORT_ENTRIES} credentials.",
        )
    seen = set()
    for candidate in candidates:
        identity = api_key_fingerprint(
            candidate.get("api_key") or json.dumps(candidate.get("payload"), sort_keys=True)
        )
        if identity in seen:
            results.append(
                {
                    "status": "skipped",
                    "source_filename": candidate["source_filename"],
                    "message": "Duplicate credential in this import was skipped.",
                }
            )
            continue
        seen.add(identity)
        try:
            if normalized_type == "api_key":
                validation = await validate_anthropic_api_key(candidate["api_key"])
                stored = await store_claude_platform_credential(candidate["api_key"], validation)
                result = {
                    "status": "success",
                    "action": stored["action"],
                    "filename": stored["filename"],
                    "source_filename": candidate["source_filename"],
                    "model_count": validation.model_count,
                    "message": "Claude Platform API key validated and imported into the pool.",
                }
            else:
                restored = await restore_anthropic_credential(candidate)
                result = {**restored, "source_filename": candidate["source_filename"]}
            results.append(result)
        except (AnthropicError, PoolImportError, ValueError) as exc:
            results.append(
                {
                    "status": "error",
                    "source_filename": candidate["source_filename"],
                    "message": str(exc),
                }
            )
        except Exception as exc:
            log.error("Failed to import Anthropic credential: %s", exc)
            results.append(
                {
                    "status": "error",
                    "source_filename": candidate["source_filename"],
                    "message": "The Anthropic credential could not be stored.",
                }
            )
    created = sum(1 for item in results if item.get("action") == "created")
    updated = sum(1 for item in results if item.get("action") == "updated")
    skipped = sum(1 for item in results if item.get("status") == "skipped")
    failed = sum(1 for item in results if item.get("status") == "error")
    return JSONResponse(
        content={
            "success": failed == 0,
            "uploaded_count": created + updated,
            "created_count": created,
            "updated_count": updated,
            "skipped_count": skipped,
            "error_count": failed,
            "total_count": len(candidates),
            "results": results,
            "message": (
                f"Import completed. Results: {created} added, {updated} updated, "
                f"{skipped} skipped, and {failed} failed."
            ),
        }
    )
