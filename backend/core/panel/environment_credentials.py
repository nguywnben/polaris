import base64
import binascii
import json
import os
import re
from typing import Any, Dict, List

from core.credential_pool import upsert_credential_by_email
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.panel.credential_privacy_route import CredentialPrivacyRoute
from core.storage_adapter import get_storage_adapter
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, HTTPException
from log import log

from .utils import internal_server_error, public_mode_name, validate_mode

router = APIRouter(
    route_class=CredentialPrivacyRoute, prefix="/api/auth", tags=["environment-credentials"]
)

ENV_CREDENTIAL_SOURCE = "environment"
ENV_CREDENTIAL_PATTERN = re.compile(
    r"^(CREDENTIALS|CODE_ASSIST_CREDENTIALS)"
    r"(?:_(JSON|B64))?(?:_\d+)?$"
)


def _safe_filename(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return name[:120] or "credential"


def _credential_mode_from_env_name(env_name: str) -> str:
    return "code_assist" if env_name.startswith("CODE_ASSIST_CREDENTIALS") else "provider"


def _decode_env_credential_payload(env_name: str, raw_value: str) -> Any:
    value = raw_value.strip()
    if not value:
        raise ValueError(f"{env_name} is empty.")

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass

    try:
        padded = value + ("=" * ((4 - len(value) % 4) % 4))
        decoded = base64.b64decode(padded, validate=True).decode("utf-8")
        return json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{env_name} must contain JSON or base64-encoded JSON.") from exc


def _extract_credential_entries(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        credentials = payload.get("credentials")
        if isinstance(credentials, list):
            entries = []
            for item in credentials:
                if isinstance(item, dict) and isinstance(item.get("credential"), dict):
                    entry = dict(item)
                    entry.setdefault("mode", payload.get("mode"))
                    entries.append(entry)
                else:
                    entries.append(
                        {
                            "mode": item.get("mode", payload.get("mode"))
                            if isinstance(item, dict)
                            else payload.get("mode"),
                            "filename": item.get("filename") if isinstance(item, dict) else None,
                            "credential": item,
                        }
                    )
            return entries
        if isinstance(credentials, dict):
            return [
                {
                    "mode": payload.get("mode"),
                    "filename": payload.get("filename"),
                    "credential": credentials,
                }
            ]
        if isinstance(payload.get("credential"), dict):
            return [payload]
        return [payload]

    raise ValueError("Credential payload must be a JSON object or array.")


def _normalize_env_credential(env_name: str, index: int, entry: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError("Credential entry must be an object.")

    default_mode = _credential_mode_from_env_name(env_name)
    requested_mode = entry.get("mode")
    mode = validate_mode(requested_mode or default_mode)

    credential = entry.get("credential") if isinstance(entry.get("credential"), dict) else entry
    credential_data = dict(credential)

    if not (
        credential_data.get("token")
        or credential_data.get("access_token")
        or credential_data.get("refresh_token")
    ):
        raise ValueError("Credential must contain token, access_token, or refresh_token.")

    if credential_data.get("access_token") and not credential_data.get("token"):
        credential_data["token"] = credential_data["access_token"]
    if credential_data.get("token") and not credential_data.get("access_token"):
        credential_data["access_token"] = credential_data["token"]
    if credential_data.get("quota_project_id") and not credential_data.get("project_id"):
        credential_data["project_id"] = credential_data["quota_project_id"]

    credential_data["source"] = ENV_CREDENTIAL_SOURCE
    credential_data["env_var"] = env_name
    credential_data["env_index"] = index

    filename = entry.get("filename") or credential_data.get("filename")
    if not filename:
        project_id = (
            credential_data.get("project_id")
            or credential_data.get("quota_project_id")
            or env_name.lower()
        )
        filename = f"env_{public_mode_name(mode)}_{project_id}_{index}.json"
    filename = _safe_filename(os.path.basename(str(filename)))
    if not filename.endswith(".json"):
        filename = f"{filename}.json"

    credential_data.pop("filename", None)

    return {"mode": mode, "filename": filename, "credential": credential_data}


def _collect_env_credentials() -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    for env_name, raw_value in sorted(os.environ.items()):
        if not ENV_CREDENTIAL_PATTERN.match(env_name):
            continue

        payload = _decode_env_credential_payload(env_name, raw_value)
        entries = _extract_credential_entries(payload)
        for index, entry in enumerate(entries, start=1):
            collected.append(_normalize_env_credential(env_name, index, entry))

    return collected


async def _list_imported_env_credentials() -> List[Dict[str, str]]:

    storage_adapter = await get_storage_adapter()
    imported: List[Dict[str, str]] = []

    for mode in ("code_assist", "primary"):
        for filename in await storage_adapter.list_credentials(mode=mode):
            credential_data = await storage_adapter.get_credential(filename, mode=mode)
            if credential_data and credential_data.get("source") == ENV_CREDENTIAL_SOURCE:
                imported.append(
                    {
                        "mode": public_mode_name(mode),
                        "filename": filename,
                        "env_var": credential_data.get("env_var", ""),
                    }
                )

    return imported


def _build_env_status() -> Dict[str, Any]:
    available_env_vars: Dict[str, Any] = {}
    for env_name, raw_value in sorted(os.environ.items()):
        if not ENV_CREDENTIAL_PATTERN.match(env_name):
            continue

        try:
            payload = _decode_env_credential_payload(env_name, raw_value)
            entries = _extract_credential_entries(payload)
            available_env_vars[env_name] = {
                "mode": _credential_mode_from_env_name(env_name),
                "credential_count": len(entries),
                "valid": True,
            }
        except Exception as exc:
            available_env_vars[env_name] = {
                "mode": _credential_mode_from_env_name(env_name),
                "credential_count": 0,
                "valid": False,
                "error": str(exc),
            }

    return available_env_vars


@router.get("/env-creds-status")
async def get_env_credentials_status(token: str = Depends(verify_panel_token)):
    """Return available environment credential variables and imported env credentials."""
    try:
        imported = await _list_imported_env_credentials()
        return JSONResponse(
            content={
                "available_env_vars": _build_env_status(),
                "auto_load_enabled": False,
                "existing_env_files_count": len(imported),
                "existing_env_files": [f"{item['mode']}:{item['filename']}" for item in imported],
                "existing_env_credentials": imported,
            }
        )
    except Exception as e:
        log.error(f"Failed to inspect environment credentials: {e}")
        raise internal_server_error() from e


@router.post("/load-env-creds")
async def load_env_credentials(token: str = Depends(verify_panel_token)):
    """Import credentials from supported * environment variables."""
    try:
        try:
            env_credentials = _collect_env_credentials()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        if not env_credentials:
            return JSONResponse(
                content={
                    "loaded_count": 0,
                    "total_count": 0,
                    "results": [],
                    "message": "No supported environment credential variables were found.",
                }
            )

        results = []
        loaded_count = 0
        skipped_count = 0

        for item in env_credentials:
            filename = item["filename"]
            mode = item["mode"]
            try:
                write_result = await upsert_credential_by_email(
                    filename, item["credential"], mode=mode
                )
                if write_result.get("stored"):
                    loaded_count += 1
                    results.append(
                        {
                            "filename": write_result.get("filename", filename),
                            "mode": public_mode_name(mode),
                            "env_var": item["credential"].get("env_var", ""),
                            "status": "success",
                            "action": write_result.get("action"),
                            "message": write_result.get("message") or "Imported.",
                        }
                    )
                else:
                    skipped_count += 1
                    results.append(
                        {
                            "filename": write_result.get("filename", filename),
                            "mode": public_mode_name(mode),
                            "env_var": item["credential"].get("env_var", ""),
                            "status": "skipped",
                            "action": write_result.get("action"),
                            "message": write_result.get("message") or "Import skipped.",
                        }
                    )
            except Exception as item_error:
                results.append(
                    {
                        "filename": filename,
                        "mode": public_mode_name(mode),
                        "status": "error",
                        "message": str(item_error),
                    }
                )

        return JSONResponse(
            content={
                "loaded_count": loaded_count,
                "skipped_count": skipped_count,
                "total_count": len(env_credentials),
                "results": results,
                "message": f"Imported {loaded_count}/{len(env_credentials)} environment credentials; skipped {skipped_count} duplicates.",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to import environment credentials: {e}")
        raise internal_server_error() from e


@router.delete("/env-creds")
async def clear_env_credentials(token: str = Depends(verify_panel_token)):
    """Delete credentials that were imported from environment variables."""
    try:
        from core.storage_adapter import get_storage_adapter

        storage_adapter = await get_storage_adapter()
        imported = await _list_imported_env_credentials()
        deleted_count = 0
        results = []

        for item in imported:
            filename = item["filename"]
            mode = validate_mode(item["mode"])
            try:
                success = await storage_adapter.delete_credential(filename, mode=mode)
                if success:
                    deleted_count += 1
                    results.append(
                        {"filename": filename, "mode": public_mode_name(mode), "status": "success"}
                    )
                else:
                    results.append(
                        {
                            "filename": filename,
                            "mode": public_mode_name(mode),
                            "status": "error",
                            "message": "Credential was not deleted.",
                        }
                    )
            except Exception as item_error:
                results.append(
                    {
                        "filename": filename,
                        "mode": public_mode_name(mode),
                        "status": "error",
                        "message": str(item_error),
                    }
                )

        return JSONResponse(
            content={
                "deleted_count": deleted_count,
                "total_count": len(imported),
                "results": results,
                "message": f"Deleted {deleted_count}/{len(imported)} environment credentials.",
            }
        )

    except Exception as e:
        log.error(f"Failed to clear environment credentials: {e}")
        raise internal_server_error() from e
