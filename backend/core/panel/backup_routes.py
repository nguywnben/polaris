"""Authenticated API for portable backup, dry-run validation, and restore."""

from __future__ import annotations

from datetime import datetime, timezone

from core.i18n import LocalizedJSONResponse as JSONResponse
from core.portable_backup import (
    BACKUP_ARCHIVE_VERSION,
    MAX_BACKUP_UPLOAD_BYTES,
    BackupArchiveError,
    BackupBackendError,
    BackupConflictError,
    BackupRestoreError,
    BackupSizeError,
    PortableBackupService,
    RestoreConflictPolicy,
)
from core.storage_adapter import get_storage_adapter
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from log import log
from pydantic import BaseModel, ConfigDict, Field, SecretStr

router = APIRouter(prefix="/api/backups", tags=["backups"])
_BACKUP_MEDIA_TYPE = "application/vnd.omni-gateway.backup+json"


class BackupCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passphrase: SecretStr = Field(min_length=12, max_length=256)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _download(content: bytes, *, filename: str, media_type: str, headers=None) -> Response:
    safe_headers = {
        "Cache-Control": "no-store",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
        **(headers or {}),
    }
    return Response(content=content, media_type=media_type, headers=safe_headers)


async def _reload_restored_runtime(storage) -> None:
    """Rebind every singleton that owns state-derived keys or cached records."""

    import config
    from core.audit_service import close_audit_service, initialize_audit_service
    from core.credential_manager import credential_manager
    from core.identity import (
        close_oidc_login_service,
        close_session_service,
        initialize_session_service,
    )
    from core.model_pool import model_catalog_service
    from core.request_trace_service import (
        close_request_trace_service,
        initialize_request_trace_service,
    )
    from core.response_cache import response_cache_coordinator
    from core.runtime_lifecycle import get_runtime_session_kwargs
    from core.usage_ledger_service import (
        close_usage_ledger_service,
        initialize_usage_ledger_service,
    )
    from core.virtual_keys import virtual_key_manager

    await close_oidc_login_service()
    await close_usage_ledger_service()
    await close_request_trace_service()
    await close_session_service()
    await close_audit_service()
    await credential_manager.close()

    await storage.reload_config_cache()
    await config.reload_config()
    virtual_key_manager.reset_runtime_state()
    virtual_key_manager.invalidate()
    await model_catalog_service.invalidate()
    await response_cache_coordinator.invalidate()

    await credential_manager.initialize()
    await initialize_audit_service(storage)
    await initialize_session_service(storage, **get_runtime_session_kwargs())
    await initialize_request_trace_service(storage)
    await initialize_usage_ledger_service(storage)


async def get_portable_backup_service() -> PortableBackupService:
    storage = await get_storage_adapter()
    if storage.get_backend_type() != "sqlite":
        raise BackupBackendError(
            "Portable backup and restore is available for the SQLite backend only."
        )
    info = await storage.get_backend_info()
    database_path = info.get("database_path")
    credentials_dir = info.get("credentials_dir")
    if not isinstance(database_path, str) or not isinstance(credentials_dir, str):
        raise BackupBackendError("SQLite backup paths are unavailable.")

    async def reload_callback() -> None:
        await _reload_restored_runtime(storage)

    return PortableBackupService(
        database_path,
        credentials_dir=credentials_dir,
        reload_callback=reload_callback,
    )


async def _read_archive(upload: UploadFile) -> bytes:
    content = bytearray()
    try:
        while True:
            chunk = await upload.read(min(1024 * 1024, MAX_BACKUP_UPLOAD_BYTES + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > MAX_BACKUP_UPLOAD_BYTES:
                raise BackupSizeError("Encrypted backup upload exceeds the size limit.")
    finally:
        await upload.close()
    if not content:
        raise BackupArchiveError("Encrypted backup upload is empty.")
    return bytes(content)


def _workflow_error(operation: str, exc: Exception) -> JSONResponse:
    log.error(f"Backup {operation} failed (error_type={type(exc).__name__}).")
    if isinstance(exc, BackupBackendError):
        return _error(
            409,
            "backup_backend_unsupported",
            "Portable backup and restore is available for the SQLite backend only.",
        )
    if isinstance(exc, BackupConflictError):
        return _error(
            409,
            "backup_restore_conflict",
            "The current instance contains state; choose the replace policy to overwrite it.",
        )
    if isinstance(exc, BackupSizeError):
        return _error(
            413,
            "backup_archive_too_large",
            "The backup archive exceeds a supported resource limit.",
        )
    if isinstance(exc, BackupArchiveError):
        return _error(
            400,
            "backup_archive_invalid",
            "The backup archive, passphrase, or compatibility metadata is invalid.",
        )
    if isinstance(exc, BackupRestoreError):
        return _error(
            503,
            "backup_restore_failed",
            "Restore failed and Polaris kept or recovered the previous state.",
        )
    return _error(
        503,
        "backup_unavailable",
        "The backup service is temporarily unavailable.",
    )


@router.post("")
async def create_backup(
    payload: BackupCreateRequest,
    token: str = Depends(verify_panel_token),
):
    del token
    try:
        service = await get_portable_backup_service()
        artifact = await service.create_backup(payload.passphrase.get_secret_value())
        return _download(
            artifact.content,
            filename=artifact.filename,
            media_type=_BACKUP_MEDIA_TYPE,
            headers={"X-Backup-Archive-Version": str(BACKUP_ARCHIVE_VERSION)},
        )
    except Exception as exc:
        return _workflow_error("creation", exc)


@router.post("/validate")
async def validate_backup(
    archive: UploadFile = File(...),
    passphrase: SecretStr = Form(..., min_length=12, max_length=256),
    conflict_policy: RestoreConflictPolicy = Form(RestoreConflictPolicy.ABORT_IF_CONFIGURED),
    token: str = Depends(verify_panel_token),
):
    del token
    try:
        content = await _read_archive(archive)
        service = await get_portable_backup_service()
        plan = await service.validate_restore(
            content,
            passphrase.get_secret_value(),
            conflict_policy=conflict_policy,
        )
        return JSONResponse(content={"dry_run": True, "plan": plan.to_dict()})
    except Exception as exc:
        return _workflow_error("validation", exc)


@router.post("/restore")
async def restore_backup(
    archive: UploadFile = File(...),
    passphrase: SecretStr = Form(..., min_length=12, max_length=256),
    conflict_policy: RestoreConflictPolicy = Form(RestoreConflictPolicy.ABORT_IF_CONFIGURED),
    token: str = Depends(verify_panel_token),
):
    del token
    try:
        content = await _read_archive(archive)
        service = await get_portable_backup_service()
        result = await service.restore(
            content,
            passphrase.get_secret_value(),
            conflict_policy=conflict_policy,
        )
        return JSONResponse(
            content={
                **result.to_dict(),
                "session_reauthentication_required": True,
            }
        )
    except Exception as exc:
        return _workflow_error("restore", exc)


@router.post("/sanitized-export")
async def create_sanitized_export(token: str = Depends(verify_panel_token)):
    del token
    try:
        service = await get_portable_backup_service()
        content = await service.create_sanitized_export()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return _download(
            content,
            filename=f"polaris-sanitized-{stamp}.json",
            media_type="application/json",
            headers={"X-Omni-Restorable": "false"},
        )
    except Exception as exc:
        return _workflow_error("sanitized export", exc)
