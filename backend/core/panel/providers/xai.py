"""Grok Build OAuth and SpaceXAI Console provider routes."""

import io
import json
import zipfile
from typing import Any, Dict, List, Tuple

import config
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.models import ConfigSaveRequest, XaiCredentialRequest, XaiOAuthCodeRequest
from core.panel.credential_privacy_route import CredentialPrivacyRoute
from core.pool_import import PoolImportError, classify_pool_credential, restore_xai_credential
from core.provider_import_normalization import normalize_provider_import
from core.provider_registry import XAI, api_key_fingerprint
from core.provider_store import store_xai_api_key_credential
from core.storage_adapter import get_storage_adapter
from core.utils import verify_panel_token
from core.xai import (
    XaiError,
    complete_xai_oauth,
    create_xai_oauth_url,
    normalize_xai_api_url,
    normalize_xai_issuer,
    validate_xai_api_key,
)
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from log import log

from ..utils import get_env_locked_keys
from .import_utils import (
    MAX_PROVIDER_IMPORT_ENTRIES,
    MAX_PROVIDER_IMPORT_FILE_BYTES,
    MAX_PROVIDER_IMPORT_UNCOMPRESSED_BYTES,
    _safe_import_name,
)

router = APIRouter(route_class=CredentialPrivacyRoute, tags=["provider-xai"])

XAI_CONFIG_KEYS = {
    "xai_api_url",
    "xai_oauth_api_url",
    "xai_oauth_issuer",
    "xai_client_id",
    "xai_user_agent",
}
XAI_CONFIG_SCOPES = {
    "oauth": {"xai_oauth_issuer", "xai_client_id", "xai_oauth_api_url"},
    "api": {"xai_api_url"},
    "shared": {"xai_user_agent"},
}


async def _current_xai_config() -> dict:
    return {
        "xai_api_url": await config.get_xai_api_url(),
        "xai_oauth_api_url": await config.get_xai_oauth_api_url(),
        "xai_oauth_issuer": await config.get_xai_oauth_issuer(),
        "xai_client_id": await config.get_xai_client_id(),
        "xai_user_agent": await config.get_xai_user_agent(),
    }


@router.get("/api/providers/xai/config")
async def get_xai_config(token: str = Depends(verify_panel_token)):
    env_locked = get_env_locked_keys() & XAI_CONFIG_KEYS
    return JSONResponse(
        content={"config": await _current_xai_config(), "env_locked": sorted(env_locked)}
    )


@router.post("/api/providers/xai/config")
async def save_xai_config(
    request: ConfigSaveRequest,
    token: str = Depends(verify_panel_token),
):
    new_config = request.config or {}
    unknown_keys = sorted(set(new_config) - XAI_CONFIG_KEYS)
    if unknown_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported Grok Build or SpaceXAI Console setting(s): {', '.join(unknown_keys)}.",
        )
    env_locked = get_env_locked_keys() & XAI_CONFIG_KEYS
    current_config = await _current_xai_config()
    candidate_config = {
        key: current_config[key] if key in env_locked else new_config.get(key, current_config[key])
        for key in XAI_CONFIG_KEYS
    }
    try:
        normalized = {
            "xai_api_url": normalize_xai_api_url(str(candidate_config["xai_api_url"] or "")),
            "xai_oauth_api_url": normalize_xai_api_url(
                str(candidate_config["xai_oauth_api_url"] or "")
            ),
            "xai_oauth_issuer": normalize_xai_issuer(
                str(candidate_config["xai_oauth_issuer"] or "")
            ),
            "xai_client_id": str(candidate_config["xai_client_id"] or "").strip(),
            "xai_user_agent": str(candidate_config["xai_user_agent"] or "").strip(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not normalized["xai_client_id"] or not normalized["xai_user_agent"]:
        raise HTTPException(
            status_code=400,
            detail="Grok Build OAuth client ID and the shared HTTP User-Agent cannot be empty.",
        )
    storage_adapter = await get_storage_adapter()
    for key, value in normalized.items():
        if key not in env_locked and key in new_config:
            await storage_adapter.set_config(key, value)
    await config.reload_config()
    return JSONResponse(
        content={
            "message": "Grok Build and SpaceXAI Console settings saved.",
            "config": await _current_xai_config(),
            "env_locked": sorted(env_locked),
        }
    )


@router.post("/api/providers/xai/config/reset")
async def reset_xai_config(
    scope: str = "",
    token: str = Depends(verify_panel_token),
):
    normalized_scope = str(scope or "").strip().lower()
    if normalized_scope and normalized_scope not in XAI_CONFIG_SCOPES:
        raise HTTPException(
            status_code=400,
            detail="Grok Build and SpaceXAI Console setting scope must be 'oauth', 'api', or 'shared'.",
        )

    env_locked = get_env_locked_keys() & XAI_CONFIG_KEYS
    storage_adapter = await get_storage_adapter()
    reset_keys = XAI_CONFIG_SCOPES.get(normalized_scope, XAI_CONFIG_KEYS)
    for key in reset_keys - env_locked:
        await storage_adapter.delete_config(key)
    await config.reload_config()
    scope_label = {
        "oauth": "Grok Build settings",
        "api": "SpaceXAI Console settings",
        "shared": "Grok Build and SpaceXAI Console shared settings",
    }.get(normalized_scope, "Grok Build and SpaceXAI Console settings")
    return JSONResponse(
        content={
            "message": f"{scope_label} reset to defaults.",
            "config": await _current_xai_config(),
            "env_locked": sorted(env_locked),
        }
    )


@router.post("/api/providers/xai/credentials")
async def add_xai_api_key_credential(
    request: XaiCredentialRequest,
    token: str = Depends(verify_panel_token),
):
    try:
        validation = await validate_xai_api_key(request.api_key)
        saved = await store_xai_api_key_credential(request.api_key, validation)
    except XaiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    action = saved["action"]
    return JSONResponse(
        status_code=200 if action == "updated" else 201,
        content={
            "success": True,
            "credential_saved": True,
            "credential_action": action,
            "filename": saved["filename"],
            "provider": XAI,
            "label": saved["label"],
            "model_count": validation.model_count,
            "message": (
                "SpaceXAI Console API key revalidated and updated in the provider pool."
                if action == "updated"
                else "SpaceXAI Console API key added to the provider pool."
            ),
        },
    )


@router.post("/api/providers/xai/oauth/start")
async def start_xai_oauth(token: str = Depends(verify_panel_token)):
    try:
        result = await create_xai_oauth_url()
        return JSONResponse(content={"success": True, **result})
    except XaiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/api/providers/xai/oauth/complete")
async def save_xai_oauth_credential(
    request: XaiOAuthCodeRequest,
    token: str = Depends(verify_panel_token),
):
    try:
        result = await complete_xai_oauth(request.code, request.state)
    except XaiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return JSONResponse(
        status_code=200 if result["action"] == "updated" else 201,
        content={
            "success": True,
            "credential_saved": True,
            "credential_action": result["action"],
            "provider": XAI,
            **result,
            "message": (
                "Grok Build OAuth credential renewed in the provider pool."
                if result["action"] == "updated"
                else "Grok Build OAuth credential added to the provider pool."
            ),
        },
    )


def _parse_xai_import_document(content: bytes, source_name: str) -> Dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{source_name} is not valid UTF-8 JSON.") from exc

    try:
        payload = normalize_provider_import(payload)
        provider_id = classify_pool_credential(payload)
    except PoolImportError as exc:
        raise ValueError(f"{source_name}: {exc}") from exc
    if provider_id != XAI:
        raise ValueError(
            f"{source_name} does not contain a Grok Build or SpaceXAI Console credential."
        )

    return {
        "source_filename": source_name,
        "filename": _safe_import_name(source_name),
        "provider": XAI,
        "payload": payload,
    }


async def _extract_xai_import_file(
    upload: UploadFile,
) -> Tuple[List[Dict[str, Any]], List[dict]]:
    upload_name = _safe_import_name(upload.filename or "credential.json")
    content = await upload.read(MAX_PROVIDER_IMPORT_FILE_BYTES + 1)
    if len(content) > MAX_PROVIDER_IMPORT_FILE_BYTES:
        raise ValueError(f"{upload_name} exceeds the 2 MB file limit.")

    lower_name = upload_name.lower()
    if lower_name.endswith(".json"):
        return [_parse_xai_import_document(content, upload_name)], []
    if not lower_name.endswith(".zip"):
        raise ValueError(f"{upload_name} must be a JSON file or ZIP archive.")

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{upload_name} is not a valid ZIP archive.") from exc

    candidates: List[Dict[str, Any]] = []
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
                with archive.open(entry) as entry_stream:
                    entry_content = entry_stream.read(MAX_PROVIDER_IMPORT_FILE_BYTES + 1)
                if len(entry_content) > MAX_PROVIDER_IMPORT_FILE_BYTES:
                    raise ValueError(f"{source_name} exceeds the 2 MB entry limit.")
                candidates.append(_parse_xai_import_document(entry_content, source_name))
            except (RuntimeError, ValueError, zipfile.BadZipFile) as exc:
                errors.append(
                    {
                        "status": "error",
                        "source_filename": source_name,
                        "message": str(exc),
                    }
                )
    return candidates, errors


def _xai_import_identity(candidate: Dict[str, Any]) -> str:
    payload = candidate["payload"]
    credential_type = str(payload.get("credential_type") or "").strip().lower()
    if credential_type == "api_key":
        identity = str(payload.get("api_key") or "").strip()
    else:
        identity = str(
            payload.get("account_fingerprint")
            or payload.get("user_email")
            or payload.get("refresh_token")
            or payload.get("access_token")
            or payload.get("credential_label")
            or ""
        ).strip()
    return f"{credential_type}:{api_key_fingerprint(identity)}"


@router.post("/api/providers/xai/credentials/import")
async def import_xai_credentials(
    files: List[UploadFile] = File(...),
    credential_type: str = "",
    token: str = Depends(verify_panel_token),
):
    """Import bounded Grok Build OAuth or SpaceXAI Console API key credentials."""
    normalized_type = str(credential_type or "").strip().lower()
    if normalized_type not in {"", "oauth", "api_key"}:
        raise HTTPException(
            status_code=400,
            detail="Credential type must be 'oauth' or 'api_key'.",
        )
    if not files:
        raise HTTPException(status_code=400, detail="Select at least one import file.")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="A single import supports up to 50 files.")

    candidates: List[Dict[str, Any]] = []
    results: List[dict] = []
    for upload in files:
        try:
            extracted, extraction_errors = await _extract_xai_import_file(upload)
            results.extend(extraction_errors)
            for candidate in extracted:
                candidate_type = (
                    str(candidate["payload"].get("credential_type") or "").strip().lower()
                )
                if normalized_type and candidate_type != normalized_type:
                    expected_label = (
                        "Grok Build OAuth credential"
                        if normalized_type == "oauth"
                        else "SpaceXAI Console API key"
                    )
                    results.append(
                        {
                            "status": "error",
                            "source_filename": candidate["source_filename"],
                            "message": (
                                f"{candidate['source_filename']} is not a {expected_label}."
                            ),
                        }
                    )
                    continue
                candidates.append(candidate)
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

    counts = {"created": 0, "updated": 0, "replaced": 0, "skipped": 0}
    seen_identities = set()
    for candidate in candidates:
        identity = _xai_import_identity(candidate)
        if identity in seen_identities:
            counts["skipped"] += 1
            results.append(
                {
                    "status": "skipped",
                    "action": "skipped",
                    "source_filename": candidate["source_filename"],
                    "message": "A duplicate provider credential in this import was skipped.",
                }
            )
            continue
        seen_identities.add(identity)

        try:
            restored = await restore_xai_credential(candidate)
            action = str(restored.get("action") or "created")
            status = str(restored.get("status") or "success")
            counter = action if action in {"created", "updated", "replaced"} else "skipped"
            if status == "skipped":
                counter = "skipped"
            counts[counter] += 1
            results.append(
                {
                    "status": status,
                    "action": action,
                    "filename": restored.get("filename", candidate["filename"]),
                    "source_filename": candidate["source_filename"],
                    "model_count": restored.get("model_count"),
                    "validation_status": restored.get("validation_status"),
                    "message": restored.get("message") or "Provider credential imported.",
                }
            )
        except XaiError as exc:
            results.append(
                {
                    "status": "error",
                    "source_filename": candidate["source_filename"],
                    "message": str(exc),
                }
            )
        except Exception as exc:
            log.error(f"Failed to import a Grok Build or SpaceXAI Console credential: {exc}")
            results.append(
                {
                    "status": "error",
                    "source_filename": candidate["source_filename"],
                    "message": "The provider credential could not be stored.",
                }
            )

    error_count = sum(1 for item in results if item.get("status") == "error")
    uploaded_count = counts["created"] + counts["updated"] + counts["replaced"]
    message = (
        f"Import completed. Results: {counts['created']} added, {counts['updated']} updated, "
        f"{counts['replaced']} renewed, {counts['skipped']} skipped, and {error_count} failed."
    )
    return JSONResponse(
        content={
            "success": True,
            "uploaded_count": uploaded_count,
            "created_count": counts["created"],
            "updated_count": counts["updated"],
            "replaced_count": counts["replaced"],
            "skipped_count": counts["skipped"],
            "error_count": error_count,
            "total_count": len(candidates),
            "credential_type": normalized_type or "all",
            "results": results,
            "message": message,
        }
    )
