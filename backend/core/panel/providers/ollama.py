"""Ollama connection management console routes."""

import io
import json
import zipfile
from typing import List, Tuple

from core.i18n import LocalizedJSONResponse as JSONResponse
from core.models import OllamaCredentialRequest
from core.ollama import OllamaError, normalize_ollama_base_url, validate_ollama_connection
from core.panel.credential_privacy_route import CredentialPrivacyRoute
from core.pool_import import restore_ollama_credential
from core.provider_registry import OLLAMA, api_key_fingerprint
from core.provider_store import store_ollama_credential
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from log import log

from .import_utils import (
    MAX_PROVIDER_IMPORT_ENTRIES,
    MAX_PROVIDER_IMPORT_FILE_BYTES,
    MAX_PROVIDER_IMPORT_UNCOMPRESSED_BYTES,
    _safe_import_name,
)

router = APIRouter(route_class=CredentialPrivacyRoute, tags=["provider-ollama"])


@router.post("/api/providers/ollama/credentials")
async def add_ollama_credential(
    request: OllamaCredentialRequest,
    token: str = Depends(verify_panel_token),
):
    try:
        base_url = normalize_ollama_base_url(request.base_url)
        validation = await validate_ollama_connection(base_url, request.api_key)
        saved = await store_ollama_credential(base_url, request.api_key, validation)
    except (OllamaError, ValueError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
    action = saved["action"]
    return JSONResponse(
        status_code=200 if action == "updated" else 201,
        content={
            "success": True,
            "credential_saved": True,
            "credential_action": action,
            "filename": saved["filename"],
            "provider": OLLAMA,
            "provider_variant": OLLAMA,
            "label": saved["label"],
            "model_count": validation.model_count,
            "message": (
                "Ollama connection revalidated and updated in the provider pool."
                if action == "updated"
                else "Ollama connection added to the provider pool."
            ),
        },
    )


def _parse_ollama_json(content: bytes, source_name: str) -> List[dict]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{source_name} is not valid UTF-8 JSON.") from exc
    values = payload if isinstance(payload, list) else [payload]
    candidates: List[dict] = []
    for index, item in enumerate(values, start=1):
        candidate_name = f"{source_name} #{index}" if len(values) > 1 else source_name
        if not isinstance(item, dict):
            raise ValueError(f"{candidate_name} must contain a credential object.")
        base_url = str(item.get("base_url") or item.get("endpoint") or "").strip()
        if not base_url:
            raise ValueError(f"{candidate_name}: Ollama endpoint is missing.")
        payload_item = dict(item)
        payload_item.update(
            {
                "provider": OLLAMA,
                "credential_type": "connection",
                "base_url": base_url,
                "api_key": str(item.get("api_key") or "").strip(),
            }
        )
        candidates.append(
            {
                "source_filename": candidate_name,
                "filename": candidate_name.rsplit(" / ", 1)[-1],
                "provider": OLLAMA,
                "payload": payload_item,
            }
        )
    return candidates


async def _extract_ollama_import_file(upload: UploadFile) -> Tuple[List[dict], List[dict]]:
    upload_name = _safe_import_name(upload.filename or "ollama.json")
    content = await upload.read(MAX_PROVIDER_IMPORT_FILE_BYTES + 1)
    if len(content) > MAX_PROVIDER_IMPORT_FILE_BYTES:
        raise ValueError(f"{upload_name} exceeds the 2 MB file limit.")
    if upload_name.lower().endswith(".json"):
        return _parse_ollama_json(content, upload_name), []
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
                candidates.extend(_parse_ollama_json(entry_content, source_name))
            except (RuntimeError, ValueError, zipfile.BadZipFile) as exc:
                errors.append(
                    {"status": "error", "source_filename": source_name, "message": str(exc)}
                )
    return candidates, errors


@router.post("/api/providers/ollama/credentials/import")
async def import_ollama_credentials(
    files: List[UploadFile] = File(...),
    token: str = Depends(verify_panel_token),
):
    if not files or len(files) > 50:
        raise HTTPException(status_code=400, detail="Select between one and 50 import files.")
    candidates: List[dict] = []
    results: List[dict] = []
    for upload in files:
        try:
            extracted, errors = await _extract_ollama_import_file(upload)
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
        payload = candidate["payload"]
        identity = api_key_fingerprint(
            f"{str(payload.get('base_url') or '').strip().rstrip('/')}"
            f"\0{str(payload.get('api_key') or '').strip()}"
        )
        if identity in seen:
            results.append(
                {
                    "status": "skipped",
                    "source_filename": candidate["source_filename"],
                    "message": "Duplicate Ollama connection in this import was skipped.",
                }
            )
            continue
        seen.add(identity)
        try:
            restored = await restore_ollama_credential(candidate)
            results.append({**restored, "source_filename": candidate["source_filename"]})
        except (OllamaError, ValueError) as exc:
            results.append(
                {
                    "status": "error",
                    "source_filename": candidate["source_filename"],
                    "message": str(exc),
                }
            )
        except Exception as exc:
            log.error("Failed to import Ollama connection: %s", exc)
            results.append(
                {
                    "status": "error",
                    "source_filename": candidate["source_filename"],
                    "message": "The Ollama connection could not be stored.",
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
