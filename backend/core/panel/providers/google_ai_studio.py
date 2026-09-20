"""Google AI Studio provider configuration and credential routes."""

import io
import json
import zipfile
from typing import List, Tuple

import config
from core.google_ai_studio import (
    GoogleAIStudioError,
    normalize_api_base_url,
    parse_api_key_import_payload,
    validate_api_key,
)
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.models import ConfigSaveRequest, GoogleAIStudioCredentialRequest
from core.panel.credential_privacy_route import CredentialPrivacyRoute
from core.provider_registry import GOOGLE_AI_STUDIO, api_key_fingerprint
from core.provider_store import store_google_ai_studio_credential, store_imported_connection
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

router = APIRouter(route_class=CredentialPrivacyRoute, tags=["provider-google-ai-studio"])

GOOGLE_AI_STUDIO_CONFIG_KEYS = {"google_ai_studio_api_url"}


async def _current_google_ai_studio_config() -> dict:
    return {"google_ai_studio_api_url": await config.get_google_ai_studio_api_url()}


@router.get("/api/providers/google-ai-studio/config")
async def get_google_ai_studio_config(token: str = Depends(verify_panel_token)):
    """Return Google AI Studio provider settings."""
    env_locked = get_env_locked_keys() & GOOGLE_AI_STUDIO_CONFIG_KEYS
    return JSONResponse(
        content={
            "config": await _current_google_ai_studio_config(),
            "env_locked": sorted(env_locked),
        }
    )


@router.post("/api/providers/google-ai-studio/config")
async def save_google_ai_studio_config(
    request: ConfigSaveRequest,
    token: str = Depends(verify_panel_token),
):
    """Save the Google AI Studio upstream endpoint."""
    new_config = request.config or {}
    unknown_keys = sorted(set(new_config) - GOOGLE_AI_STUDIO_CONFIG_KEYS)
    if unknown_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported Google AI Studio setting(s): {', '.join(unknown_keys)}.",
        )

    try:
        api_url = normalize_api_base_url(str(new_config.get("google_ai_studio_api_url") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    env_locked = get_env_locked_keys() & GOOGLE_AI_STUDIO_CONFIG_KEYS
    if "google_ai_studio_api_url" not in env_locked:
        storage_adapter = await get_storage_adapter()
        await storage_adapter.set_config("google_ai_studio_api_url", api_url)
        await config.reload_config()

    return JSONResponse(
        content={
            "message": "Google AI Studio settings saved.",
            "config": await _current_google_ai_studio_config(),
            "env_locked": sorted(env_locked),
        }
    )


@router.post("/api/providers/google-ai-studio/config/reset")
async def reset_google_ai_studio_config(token: str = Depends(verify_panel_token)):
    """Reset the Google AI Studio endpoint to its environment or built-in value."""
    env_locked = get_env_locked_keys() & GOOGLE_AI_STUDIO_CONFIG_KEYS
    if "google_ai_studio_api_url" not in env_locked:
        storage_adapter = await get_storage_adapter()
        await storage_adapter.delete_config("google_ai_studio_api_url")
        await config.reload_config()
    return JSONResponse(
        content={
            "message": "Google AI Studio settings reset to defaults.",
            "config": await _current_google_ai_studio_config(),
            "env_locked": sorted(env_locked),
        }
    )


@router.post("/api/providers/google-ai-studio/credentials")
async def add_google_ai_studio_credential(
    request: GoogleAIStudioCredentialRequest,
    token: str = Depends(verify_panel_token),
):
    """Validate and add one Google AI Studio API key to the provider pool."""
    api_key = request.api_key.strip()

    try:
        validation = await validate_api_key(api_key)
    except GoogleAIStudioError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    saved = await _store_google_ai_studio_credential(api_key, validation)
    action = saved["action"]
    message = (
        "Google AI Studio API key revalidated and updated in the provider pool."
        if action == "updated"
        else "Google AI Studio API key added to the provider pool."
    )
    return JSONResponse(
        status_code=200 if action == "updated" else 201,
        content={
            "success": True,
            "credential_saved": True,
            "credential_action": action,
            "filename": saved["filename"],
            "provider": GOOGLE_AI_STUDIO,
            "label": saved["label"],
            "model_count": validation.model_count,
            "message": message,
        },
    )


async def _store_google_ai_studio_credential(api_key: str, validation) -> dict:
    """Store one validated key without exposing it in the result."""
    return await store_google_ai_studio_credential(api_key, validation)


def _parse_import_document(content: bytes, source_name: str) -> List[Tuple[str, str]]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{source_name} is not valid UTF-8 JSON.") from exc

    api_keys = parse_api_key_import_payload(payload)
    return [
        (f"{source_name} #{index}" if len(api_keys) > 1 else source_name, api_key)
        for index, api_key in enumerate(api_keys, start=1)
    ]


async def _extract_ai_studio_import_file(
    upload: UploadFile,
) -> Tuple[List[Tuple[str, str]], List[dict]]:
    upload_name = _safe_import_name(upload.filename or "credential.json")
    content = await upload.read(MAX_PROVIDER_IMPORT_FILE_BYTES + 1)
    if len(content) > MAX_PROVIDER_IMPORT_FILE_BYTES:
        raise ValueError(f"{upload_name} exceeds the 2 MB file limit.")

    lower_name = upload_name.lower()
    if lower_name.endswith(".json"):
        return _parse_import_document(content, upload_name), []
    if not lower_name.endswith(".zip"):
        raise ValueError(f"{upload_name} must be a JSON file or ZIP archive.")

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{upload_name} is not a valid ZIP archive.") from exc

    candidates: List[Tuple[str, str]] = []
    errors: List[dict] = []
    with archive:
        json_entries = [
            entry
            for entry in archive.infolist()
            if not entry.is_dir() and entry.filename.lower().endswith(".json")
        ]
        if not json_entries:
            raise ValueError(f"{upload_name} does not contain any JSON files.")
        if len(json_entries) > MAX_PROVIDER_IMPORT_ENTRIES:
            raise ValueError(
                f"{upload_name} contains more than {MAX_PROVIDER_IMPORT_ENTRIES} JSON files."
            )

        total_uncompressed = sum(entry.file_size for entry in json_entries)
        if total_uncompressed > MAX_PROVIDER_IMPORT_UNCOMPRESSED_BYTES:
            raise ValueError(f"{upload_name} exceeds the 5 MB uncompressed limit.")

        for entry in json_entries:
            entry_name = _safe_import_name(entry.filename)
            source_name = f"{upload_name} / {entry_name}"
            if entry.flag_bits & 0x1:
                errors.append(
                    {
                        "status": "error",
                        "source_filename": source_name,
                        "message": "Encrypted ZIP entries are not supported.",
                    }
                )
                continue
            try:
                entry_content = archive.read(entry)
                candidates.extend(_parse_import_document(entry_content, source_name))
            except (RuntimeError, ValueError, zipfile.BadZipFile) as exc:
                errors.append(
                    {
                        "status": "error",
                        "source_filename": source_name,
                        "message": str(exc),
                    }
                )
    return candidates, errors


@router.post("/api/providers/google-ai-studio/credentials/import")
async def import_google_ai_studio_credentials(
    files: List[UploadFile] = File(...),
    token: str = Depends(verify_panel_token),
):
    """Import unverified Google AI Studio API keys from bounded JSON/ZIP uploads."""
    if not files:
        raise HTTPException(status_code=400, detail="Select at least one import file.")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="A single import supports up to 50 files.")

    candidates: List[Tuple[str, str]] = []
    results: List[dict] = []
    for upload in files:
        try:
            extracted, extraction_errors = await _extract_ai_studio_import_file(upload)
            candidates.extend(extracted)
            results.extend(extraction_errors)
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
            detail=f"A single import supports up to {MAX_PROVIDER_IMPORT_ENTRIES} API keys.",
        )

    seen_fingerprints = set()
    created_count = 0
    updated_count = 0
    skipped_count = 0

    for source_name, api_key in candidates:
        fingerprint = api_key_fingerprint(api_key)
        if fingerprint in seen_fingerprints:
            skipped_count += 1
            results.append(
                {
                    "status": "skipped",
                    "source_filename": source_name,
                    "message": "Duplicate API key in this import was skipped.",
                }
            )
            continue
        seen_fingerprints.add(fingerprint)

        try:
            saved = await store_imported_connection(GOOGLE_AI_STUDIO, api_key)
            action = saved["action"]
            if action == "skipped":
                skipped_count += 1
            elif action == "updated":
                updated_count += 1
            else:
                created_count += 1
            results.append(
                {
                    "status": saved["status"],
                    "action": action,
                    "filename": saved["filename"],
                    "source_filename": source_name,
                    "model_count": 0,
                    "validation_status": "unverified",
                    "message": "Credential imported. Inference access is not verified.",
                }
            )
        except GoogleAIStudioError as exc:
            results.append(
                {
                    "status": "error",
                    "source_filename": source_name,
                    "message": str(exc),
                }
            )
        except Exception:
            log.error("Failed to import a Google AI Studio credential")
            results.append(
                {
                    "status": "error",
                    "source_filename": source_name,
                    "message": "The API key could not be stored.",
                }
            )

    error_count = sum(1 for item in results if item.get("status") == "error")
    uploaded_count = created_count + updated_count
    message = (
        f"Import completed. Results: {created_count} added, {updated_count} updated, "
        f"{skipped_count} skipped, and {error_count} failed."
    )
    return JSONResponse(
        content={
            "success": True,
            "uploaded_count": uploaded_count,
            "created_count": created_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "total_count": len(candidates),
            "results": results,
            "message": message,
        },
    )
