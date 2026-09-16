import asyncio
import io
import json
import os
import stat
import zipfile
from typing import Any, List

from config import (
    get_antigravity_api_url,
    get_antigravity_user_agent,
)
from core.anthropic import AnthropicError, fetch_anthropic_model_ids
from core.antigravity import AntigravityError, fetch_antigravity_model_ids
from core.codex import CodexError, fetch_codex_model_ids, refresh_codex_oauth_credential
from core.credential_fleet_query import (
    CredentialFleetFilters,
    build_credential_fleet_page,
    load_credential_fleet_items,
)
from core.credential_manager import credential_manager
from core.credential_pool import (
    deduplicate_credentials_by_account_email,
    get_known_credential_email,
    parse_credential_expiry,
    resolve_credential_email,
)
from core.google_ai_studio import (
    GoogleAIStudioError,
    validate_api_key,
)
from core.google_oauth_api import (
    Credentials,
    enable_required_apis,
    fetch_project_id_and_tier,
    get_user_projects,
    merge_refreshed_credential_data,
    select_default_project,
)
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.ollama import OllamaError, fetch_ollama_model_ids
from core.openai_platform import OpenAIPlatformError, fetch_openai_model_ids
from core.pool_import import (
    MAX_POOL_ARCHIVE_BYTES,
    MAX_POOL_ARCHIVE_ENTRIES,
    MAX_POOL_ENTRY_BYTES,
    MAX_POOL_UNCOMPRESSED_BYTES,
)
from core.provider_connection_diagnostics import connection_diagnostic
from core.provider_registry import (
    ANTHROPIC,
    CLAUDE_CODE,
    CODEX,
    EXTENDED_PROVIDERS,
    GOOGLE_AI_STUDIO,
    GOOGLE_ANTIGRAVITY,
    OLLAMA,
    OPENAI,
    OPENAI_PLATFORM,
    XAI,
    canonicalize_antigravity_credential_filename,
    credential_supports_operation,
    get_credential_provider,
    get_credential_provider_variant,
    get_credential_variant_capabilities,
    list_credential_variant_capabilities,
    normalize_provider_id,
)
from core.storage_adapter import get_storage_adapter
from core.xai import (
    XaiError,
    fetch_xai_model_ids,
    fetch_xai_oauth_model_ids,
    refresh_xai_oauth_credential,
)
from fastapi import HTTPException, Response, UploadFile
from log import log

from .utils import INTERNAL_SERVER_ERROR_DETAIL, validate_credential_filename, validate_mode


def reject_unsupported_credential_operation(
    credential_data: dict,
    operation: str,
    *,
    mode: str,
) -> JSONResponse | None:
    """Return a stable, secret-free rejection for an unsupported pool operation.

    Code Assist keeps its legacy operation contract. The shared provider pool is
    fail-closed so an unknown or mismatched credential variant cannot reach an
    operation merely by crafting an API request.
    """
    if mode != "primary" or credential_supports_operation(credential_data, operation):
        return None

    inferred_variant = get_credential_provider_variant(credential_data)
    capabilities = get_credential_variant_capabilities(inferred_variant)
    variant_id = capabilities.variant_id if capabilities else "unknown"
    diagnostic = connection_diagnostic("unsupported_operation")
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "credential_operation_unsupported",
                "message": "This operation is not supported for the credential variant.",
                "operation": operation,
                "variant_id": variant_id,
            },
            "diagnostic": diagnostic.as_dict(),
        },
    )


def _count_label(count: int, singular: str, plural: str | None = None) -> str:
    label = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {label}"


def _zip_entry_is_symlink(entry: zipfile.ZipInfo) -> bool:
    file_mode = (entry.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(file_mode)


async def extract_json_files_from_zip(zip_file: UploadFile) -> List[dict]:
    try:
        zip_content = await zip_file.read(MAX_POOL_ARCHIVE_BYTES + 1)
        if len(zip_content) > MAX_POOL_ARCHIVE_BYTES:
            raise HTTPException(status_code=400, detail="ZIP archive exceeds the 10 MB limit.")

        files_data = []
        extracted_bytes = 0

        with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zip_ref:
            entries = [entry for entry in zip_ref.infolist() if not entry.is_dir()]
            if len(entries) > MAX_POOL_ARCHIVE_ENTRIES:
                raise HTTPException(
                    status_code=400,
                    detail=f"ZIP archive contains more than {MAX_POOL_ARCHIVE_ENTRIES} files.",
                )
            json_files = [
                entry
                for entry in entries
                if entry.filename.lower().endswith(".json")
                and not entry.filename.startswith("__MACOSX/")
            ]

            if not json_files:
                raise HTTPException(
                    status_code=400, detail="No JSON files were found in the ZIP archive."
                )

            declared_size = sum(entry.file_size for entry in json_files)
            if declared_size > MAX_POOL_UNCOMPRESSED_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail="ZIP archive exceeds the 25 MB uncompressed limit.",
                )

            log.info(
                f"Found {_count_label(len(json_files), 'JSON file')} in an imported ZIP archive."
            )

            for entry in json_files:
                json_filename = entry.filename
                try:
                    if entry.flag_bits & 0x1:
                        raise HTTPException(
                            status_code=400,
                            detail="Encrypted ZIP entries are not supported.",
                        )
                    if _zip_entry_is_symlink(entry):
                        raise HTTPException(
                            status_code=400,
                            detail="Symbolic-link ZIP entries are not supported.",
                        )
                    if entry.file_size > MAX_POOL_ENTRY_BYTES:
                        raise HTTPException(
                            status_code=400,
                            detail="Credential file exceeds the 2 MB limit.",
                        )

                    with zip_ref.open(entry) as json_file:
                        content = json_file.read(MAX_POOL_ENTRY_BYTES + 1)
                    if len(content) > MAX_POOL_ENTRY_BYTES:
                        raise HTTPException(
                            status_code=400,
                            detail="Credential file exceeds the 2 MB limit.",
                        )
                    extracted_bytes += len(content)
                    if extracted_bytes > MAX_POOL_UNCOMPRESSED_BYTES:
                        raise HTTPException(
                            status_code=400,
                            detail="ZIP archive exceeds the 25 MB uncompressed limit.",
                        )

                    try:
                        content_str = content.decode("utf-8")
                    except UnicodeDecodeError:
                        log.warning(f"Skipping ZIP entry with invalid UTF-8: {json_filename}")
                        continue

                    filename = os.path.basename(json_filename.replace("\\", "/"))
                    files_data.append({"filename": filename, "content": content_str})

                except HTTPException:
                    raise
                except Exception as e:
                    log.warning(f"Error processing file {json_filename} in ZIP: {e}")
                    continue

        log.info(
            f"Extracted {_count_label(len(files_data), 'valid JSON file')} from the ZIP archive."
        )
        return files_data

    except HTTPException:
        raise
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Invalid ZIP file format.") from exc
    except Exception as e:
        log.error(f"Failed to process ZIP file: {e}")
        raise HTTPException(status_code=500, detail="Failed to process ZIP archive.") from e


async def clear_all_model_cooldowns_for_credential(
    storage_adapter: Any,
    filename: str,
    mode: str,
) -> None:
    try:
        cleared = await storage_adapter._backend.clear_all_model_cooldowns(filename, mode=mode)
        if not cleared:
            log.warning(
                f"Failed to clear model cooldowns or credential does not exist: {filename} (mode={mode})"
            )
    except Exception as e:
        log.warning(f"Failed to clear model cooldowns for {filename} (mode={mode}): {e}")


def _incoming_credential_is_better(candidate: dict, current: dict) -> bool:
    candidate_expiry = candidate.get("expiry")
    current_expiry = current.get("expiry")
    if candidate_expiry is None:
        return False
    if current_expiry is None:
        return True
    return candidate_expiry > current_expiry


async def _prepare_upload_candidates(files_data: List[dict]) -> tuple[List[dict], List[dict]]:
    candidates = []
    immediate_results = []
    best_by_email = {}

    for file_data in files_data:
        try:
            filename = validate_credential_filename(os.path.basename(file_data["filename"]))
        except HTTPException as exc:
            immediate_results.append(
                {
                    "filename": "Invalid credential file",
                    "status": "error",
                    "message": f"{exc.detail}",
                }
            )
            continue
        try:
            credential_data = json.loads(file_data["content"])
        except json.JSONDecodeError as e:
            immediate_results.append(
                {
                    "filename": file_data["filename"],
                    "status": "error",
                    "message": f"JSON format error: {str(e)}.",
                }
            )
            continue

        email = await resolve_credential_email(credential_data)
        if email:
            credential_data["user_email"] = email

        candidate = {
            "filename": filename,
            "source_filename": filename,
            "credential_data": credential_data,
            "email": email,
            "expiry": parse_credential_expiry(credential_data),
        }

        if not candidate["email"]:
            candidates.append(candidate)
            continue

        current = best_by_email.get(candidate["email"])
        if current is None:
            best_by_email[candidate["email"]] = candidate
            continue

        if _incoming_credential_is_better(candidate, current):
            immediate_results.append(
                {
                    "filename": current["filename"],
                    "source_filename": current["source_filename"],
                    "status": "skipped",
                    "action": "skipped",
                    "email": current["email"],
                    "message": "Skipped because another imported credential has the same email with a later expiry.",
                }
            )
            best_by_email[candidate["email"]] = candidate
        else:
            immediate_results.append(
                {
                    "filename": candidate["filename"],
                    "source_filename": candidate["source_filename"],
                    "status": "skipped",
                    "action": "skipped",
                    "email": candidate["email"],
                    "message": "Skipped because another imported credential has the same email with an equal or later expiry.",
                }
            )

    candidates.extend(best_by_email.values())
    return candidates, immediate_results


async def upload_credentials_common(
    files: List[UploadFile], mode: str = "code_assist"
) -> JSONResponse:
    mode = validate_mode(mode)

    if not files:
        raise HTTPException(
            status_code=400, detail="Select at least one credential file to import."
        )

    if len(files) > 100:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. A maximum of 100 files is supported; current count: {len(files)}.",
        )

    files_data = []
    uploaded_bytes = 0
    for file in files:
        upload_name = os.path.basename(str(file.filename or "").replace("\\", "/"))
        normalized_name = upload_name.lower()
        if normalized_name.endswith(".zip"):
            zip_files_data = await extract_json_files_from_zip(file)
            uploaded_bytes += sum(len(item["content"].encode("utf-8")) for item in zip_files_data)
            files_data.extend(zip_files_data)
            log.info(
                f"Extracted {_count_label(len(zip_files_data), 'JSON file')} from an imported ZIP archive."
            )

        elif normalized_name.endswith(".json"):
            content = await file.read(MAX_POOL_ENTRY_BYTES + 1)
            if len(content) > MAX_POOL_ENTRY_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Credential file '{upload_name}' exceeds the 2 MB limit.",
                )
            try:
                content_str = content.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Credential file '{upload_name}' must use UTF-8 encoding.",
                )

            uploaded_bytes += len(content)
            files_data.append({"filename": upload_name, "content": content_str})
        else:
            raise HTTPException(
                status_code=400,
                detail=f"File format '{upload_name}' is not supported. Use a JSON file or ZIP archive.",
            )

        if len(files_data) > MAX_POOL_ARCHIVE_ENTRIES:
            raise HTTPException(
                status_code=400,
                detail=f"Import contains more than {MAX_POOL_ARCHIVE_ENTRIES} credential files.",
            )
        if uploaded_bytes > MAX_POOL_UNCOMPRESSED_BYTES:
            raise HTTPException(
                status_code=400,
                detail="Import exceeds the 25 MB uncompressed limit.",
            )

    upload_candidates, preprocessed_results = await _prepare_upload_candidates(files_data)

    mode_label = "provider" if mode == "primary" else "Code Assist"
    batch_size = 1000
    all_results = list(preprocessed_results)
    total_success = 0

    for i in range(0, len(upload_candidates), batch_size):
        batch_files = upload_candidates[i : i + batch_size]

        async def process_single_file(file_data):
            try:
                filename = file_data["filename"]

                filename = os.path.basename(filename)
                credential_data = file_data["credential_data"]

                if mode == "primary":
                    write_result = await credential_manager.add_primary_credential(
                        filename, credential_data
                    )
                else:
                    write_result = await credential_manager.add_credential(
                        filename, credential_data
                    )

                stored = write_result.get("stored", False)
                action = write_result.get("action", "created")
                status = "success" if stored else "skipped"
                saved_filename = write_result.get("filename", filename)
                log.debug(f"Credential import result: {action} ({saved_filename}, mode={mode}).")
                return {
                    "filename": saved_filename,
                    "source_filename": filename,
                    "status": status,
                    "action": action,
                    "email": write_result.get("email"),
                    "message": write_result.get("message")
                    or ("Credential imported." if stored else "Credential skipped."),
                }

            except Exception:
                return {
                    "filename": file_data["filename"],
                    "status": "error",
                    "message": "Credential processing failed.",
                }

        log.info(
            f"Starting concurrent import for {_count_label(len(batch_files), f'{mode} file')}."
        )
        concurrent_tasks = [process_single_file(file_data) for file_data in batch_files]
        batch_results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)

        processed_results = []
        batch_uploaded_count = 0
        batch_skipped_count = 0
        for result in batch_results:
            if isinstance(result, Exception):
                processed_results.append(
                    {
                        "filename": "unknown",
                        "status": "error",
                        "message": "Credential processing failed.",
                    }
                )
            else:
                processed_results.append(result)
                if result["status"] == "success":
                    batch_uploaded_count += 1
                elif result["status"] == "skipped":
                    batch_skipped_count += 1

        all_results.extend(processed_results)
        total_success += batch_uploaded_count
        total_skipped = sum(1 for result in all_results if result.get("status") == "skipped")

        batch_num = (i // batch_size) + 1
        total_batches = (len(upload_candidates) + batch_size - 1) // batch_size
        credential_label = "credential" if len(batch_files) == 1 else "credentials"
        log.info(
            f"Import batch {batch_num}/{total_batches} completed. Saved or renewed "
            f"{batch_uploaded_count}/{len(batch_files)} {mode_label} {credential_label}; "
            f"skipped {_count_label(batch_skipped_count, 'duplicate credential')}."
        )

    total_skipped = sum(1 for result in all_results if result.get("status") == "skipped")
    if total_success > 0 or total_skipped > 0:
        credential_label = "credential" if len(files_data) == 1 else "credentials"
        message = (
            f"Import completed. Saved or renewed {total_success}/{len(files_data)} "
            f"{mode_label} {credential_label}; skipped "
            f"{_count_label(total_skipped, 'duplicate credential')} with an equal or shorter expiry."
        )
        return JSONResponse(
            content={
                "uploaded_count": total_success,
                "skipped_count": total_skipped,
                "total_count": len(files_data),
                "results": all_results,
                "message": message,
            }
        )
    else:
        raise HTTPException(
            status_code=400, detail=f"No {mode_label} credential files were imported."
        )


async def get_creds_status_common(
    offset: int,
    limit: int,
    status_filter: str,
    mode: str = "code_assist",
    error_code_filter: str = None,
    cooldown_filter: str = None,
    preview_filter: str = None,
    tier_filter: str = None,
    provider_filter: str = None,
    provider_variant_filter: str = None,
    credential_kind_filter: str = None,
    health_filter: str = None,
    quota_state_filter: str = None,
    source_filter: str = None,
) -> JSONResponse:
    mode = validate_mode(mode)

    if offset < 0:
        raise HTTPException(status_code=400, detail="Offset must be greater than or equal to 0.")
    if limit not in [20, 50, 100, 200, 500, 1000]:
        raise HTTPException(status_code=400, detail="Limit must be 20, 50, 100, 200, 500, or 1000.")
    if status_filter not in ["all", "enabled", "disabled"]:
        raise HTTPException(
            status_code=400, detail="Status filter must be all, enabled, or disabled."
        )
    if cooldown_filter and cooldown_filter not in ["all", "in_cooldown", "no_cooldown"]:
        raise HTTPException(
            status_code=400, detail="Cooldown filter must be all, in_cooldown, or no_cooldown."
        )
    if preview_filter and preview_filter not in ["all", "preview", "no_preview"]:
        raise HTTPException(
            status_code=400, detail="Preview filter must be all, preview, or no_preview."
        )
    if tier_filter and tier_filter not in ["all", "free", "pro", "ultra", "not_applicable"]:
        raise HTTPException(
            status_code=400,
            detail="Tier filter must be all, free, pro, ultra, or not_applicable.",
        )
    if credential_kind_filter and credential_kind_filter not in [
        "all",
        "oauth",
        "api_key",
        "connection",
    ]:
        raise HTTPException(
            status_code=400,
            detail="Credential kind filter must be all, oauth, api_key, or connection.",
        )
    if health_filter and health_filter not in [
        "all",
        "healthy",
        "degraded",
        "unhealthy",
        "disabled",
    ]:
        raise HTTPException(
            status_code=400,
            detail="Health filter must be all, healthy, degraded, unhealthy, or disabled.",
        )
    if quota_state_filter and quota_state_filter not in [
        "all",
        "available",
        "limited",
        "exhausted",
        "unsupported",
    ]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Quota state filter must be all, available, limited, exhausted, or unsupported."
            ),
        )
    if source_filter and source_filter not in ["all", "managed", "environment"]:
        raise HTTPException(
            status_code=400,
            detail="Source filter must be all, managed, or environment.",
        )
    if error_code_filter and error_code_filter not in {"all", "none"}:
        normalized_error_code = str(error_code_filter).strip()
        if not (normalized_error_code.isdigit() and len(normalized_error_code) == 3):
            raise HTTPException(
                status_code=400,
                detail="Error code filter must be all, none, or a three-digit status code.",
            )

    supported_variants = {item["variant_id"] for item in list_credential_variant_capabilities()}
    normalized_provider_filter = "all"
    normalized_variant_filter = str(provider_variant_filter or "all").strip().lower()
    if normalized_variant_filter != "all" and normalized_variant_filter not in supported_variants:
        raise HTTPException(
            status_code=400,
            detail="Provider variant filter must identify a supported credential variant.",
        )

    raw_provider_filter = str(provider_filter or "all").strip().lower()
    legacy_variant_filter = "all"
    if raw_provider_filter != "all":
        if raw_provider_filter in {"grok", "xai_oauth"}:
            legacy_variant_filter = "grok"
        elif raw_provider_filter in {"xai_console", "xai_api_key"}:
            legacy_variant_filter = "xai_console"
        elif raw_provider_filter in {"codex", "openai_codex"}:
            legacy_variant_filter = "codex"
        elif raw_provider_filter in {"openai_platform", "openai_api_key"}:
            legacy_variant_filter = "openai_platform"
        elif raw_provider_filter in {"claude_code", "claude"}:
            legacy_variant_filter = "claude_code"
        elif raw_provider_filter == "claude_platform":
            legacy_variant_filter = "claude_platform"
        elif raw_provider_filter in supported_variants:
            legacy_variant_filter = raw_provider_filter
        else:
            normalized_provider_filter = normalize_provider_id(provider_filter)
        if mode != "primary" or normalized_provider_filter not in {
            "all",
            GOOGLE_ANTIGRAVITY,
            GOOGLE_AI_STUDIO,
            XAI,
            OPENAI,
            ANTHROPIC,
            OLLAMA,
        }:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Provider filter must identify a supported provider or credential product."
                ),
            )
        if legacy_variant_filter != "all":
            if (
                normalized_variant_filter != "all"
                and normalized_variant_filter != legacy_variant_filter
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Provider and provider variant filters conflict.",
                )
            normalized_variant_filter = legacy_variant_filter

    dedupe_result = await deduplicate_credentials_by_account_email(mode=mode)

    storage_adapter = await get_storage_adapter()
    all_creds = await load_credential_fleet_items(storage_adapter, mode=mode)
    filters = CredentialFleetFilters(
        provider=normalized_provider_filter,
        provider_variant=normalized_variant_filter,
        credential_kind=str(credential_kind_filter or "all"),
        health=str(health_filter or "all"),
        cooldown=str(cooldown_filter or "all"),
        quota_state=str(quota_state_filter or "all"),
        tier=str(tier_filter or "all"),
        source=str(source_filter or "all"),
        status=status_filter,
        error_code=str(error_code_filter or "all"),
        preview=str(preview_filter or "all"),
    )
    payload = build_credential_fleet_page(
        all_creds,
        filters,
        offset=offset,
        limit=limit,
        mode=mode,
    )
    payload["provider_filter"] = raw_provider_filter
    payload["deduplicated_count"] = dedupe_result.get("deleted_count", 0)

    return JSONResponse(content=payload)


async def _get_download_filename(
    storage_adapter,
    filename: str,
    credential_data: dict,
    mode: str,
) -> str:
    download_filename = os.path.basename(filename)
    if mode != "primary" or get_credential_provider(credential_data) != GOOGLE_ANTIGRAVITY:
        return download_filename

    email = get_known_credential_email(credential_data)
    if not email:
        try:
            state = await storage_adapter.get_credential_state(filename, mode=mode)
            email = str(state.get("user_email") or "").strip().lower()
        except Exception:
            email = ""
    return canonicalize_antigravity_credential_filename(
        download_filename,
        credential_data,
        email=email,
    )


async def download_all_creds_common(mode: str = "code_assist") -> Response:
    mode = validate_mode(mode)
    zip_filename = "provider_credentials.zip" if mode == "primary" else "credentials.zip"

    await deduplicate_credentials_by_account_email(mode=mode)

    storage_adapter = await get_storage_adapter()
    credential_filenames = await storage_adapter.list_credentials(mode=mode)

    if not credential_filenames:
        raise HTTPException(
            status_code=404, detail="No credential files are available to download."
        )

    log.info(f"Packaging {_count_label(len(credential_filenames), f'{mode} credential')}.")

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        success_count = 0
        archive_names = set()
        for idx, filename in enumerate(credential_filenames, 1):
            try:
                credential_data = await storage_adapter.get_credential(filename, mode=mode)
                if credential_data:
                    content = json.dumps(credential_data, ensure_ascii=False, indent=2)
                    download_filename = await _get_download_filename(
                        storage_adapter,
                        filename,
                        credential_data,
                        mode,
                    )
                    candidate_name = download_filename
                    stem, extension = os.path.splitext(candidate_name)
                    suffix = 2
                    while download_filename in archive_names:
                        download_filename = f"{stem}-{suffix}{extension}"
                        suffix += 1
                    archive_names.add(download_filename)
                    zip_file.writestr(download_filename, content)
                    success_count += 1

                    if idx % 10 == 0:
                        log.debug(f"Packaging progress: {idx}/{len(credential_filenames)}")

            except Exception as e:
                log.warning(f"Error processing {mode} credential file {filename}: {e}")
                continue

    file_label = "file" if len(credential_filenames) == 1 else "files"
    log.info(
        f"Credential package created with {success_count}/{len(credential_filenames)} {file_label}."
    )

    zip_buffer.seek(0)
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"},
    )


async def fetch_user_email_common(filename: str, mode: str = "code_assist") -> JSONResponse:
    mode = validate_mode(mode)

    filename_only = validate_credential_filename(filename)

    storage_adapter = await get_storage_adapter()
    credential_data = await storage_adapter.get_credential(filename_only, mode=mode)
    if not credential_data:
        raise HTTPException(status_code=404, detail="Credential file does not exist.")

    email = await credential_manager.get_or_fetch_user_email(filename_only, mode=mode)

    if email:
        return JSONResponse(
            content={
                "filename": filename_only,
                "user_email": email,
                "message": "Retrieved user email.",
            }
        )
    else:
        return JSONResponse(
            content={
                "filename": filename_only,
                "user_email": None,
                "message": "Unable to retrieve user email. The credential may be expired or missing required permissions.",
            },
            status_code=400,
        )


async def refresh_all_user_emails_common(mode: str = "code_assist") -> JSONResponse:
    """Refreshes user emails for all credentials where they are missing."""
    mode = validate_mode(mode)

    storage_adapter = await get_storage_adapter()

    # Bulk fetch states for all credentials
    all_states = await storage_adapter.get_all_credential_states(mode=mode)

    results = []
    success_count = 0
    skipped_count = 0

    # Filter in memory for credentials that need emails
    for filename, state in all_states.items():
        try:
            cached_email = state.get("user_email")

            if cached_email:
                skipped_count += 1
                results.append(
                    {
                        "filename": os.path.basename(filename),
                        "user_email": cached_email,
                        "success": True,
                        "skipped": True,
                    }
                )
                continue

            email = await credential_manager.get_or_fetch_user_email(filename, mode=mode)
            if email:
                success_count += 1
                results.append(
                    {
                        "filename": os.path.basename(filename),
                        "user_email": email,
                        "success": True,
                    }
                )
            else:
                results.append(
                    {
                        "filename": os.path.basename(filename),
                        "user_email": None,
                        "success": False,
                        "error": "Unable to retrieve email.",
                    }
                )
        except Exception:
            results.append(
                {
                    "filename": os.path.basename(filename),
                    "user_email": None,
                    "success": False,
                    "error": "Unable to retrieve email.",
                }
            )

    total_count = len(all_states)
    address_label = "email address" if success_count == 1 else "email addresses"
    return JSONResponse(
        content={
            "success_count": success_count,
            "total_count": total_count,
            "skipped_count": skipped_count,
            "results": results,
            "message": (
                f"Retrieved {success_count}/{total_count} {address_label}; skipped "
                f"{_count_label(skipped_count, 'credential')} with an existing email address."
            ),
        }
    )


async def deduplicate_credentials_by_email_common(mode: str = "code_assist") -> JSONResponse:
    """Batch deduplicate credential files by email, keeping the latest expiry."""
    mode = validate_mode(mode)

    try:
        dedupe_result = await deduplicate_credentials_by_account_email(mode=mode)
        duplicate_groups = dedupe_result.get("duplicate_groups", [])
        total_count = dedupe_result.get("total_count", 0)

        if not duplicate_groups:
            return JSONResponse(
                content={
                    "deleted_count": 0,
                    "kept_count": total_count,
                    "total_count": total_count,
                    "unique_emails_count": dedupe_result.get("unique_emails_count", 0),
                    "no_email_count": dedupe_result.get("no_email_count", 0),
                    "duplicate_groups": [],
                    "delete_errors": [],
                    "message": "No duplicate credentials with the same email were found.",
                }
            )

        deleted_count = dedupe_result.get("deleted_count", 0)
        kept_count = dedupe_result.get("kept_count", total_count - deleted_count)
        unique_email_count = dedupe_result.get("unique_emails_count", 0)
        result_duplicate_groups = [
            {
                "email": group["email"],
                "kept_file": os.path.basename(group["kept_file"]),
                "deleted_files": [
                    os.path.basename(filename) for filename in group.get("deleted_files", [])
                ],
                "duplicate_count": group.get(
                    "duplicate_count", len(group.get("deleted_files", []))
                ),
            }
            for group in duplicate_groups
        ]

        return JSONResponse(
            content={
                "deleted_count": deleted_count,
                "kept_count": kept_count,
                "total_count": total_count,
                "unique_emails_count": unique_email_count,
                "no_email_count": dedupe_result.get("no_email_count", 0),
                "duplicate_groups": result_duplicate_groups,
                "delete_errors": [],
                "message": (
                    "Deduplication completed. Deleted "
                    f"{_count_label(deleted_count, 'duplicate credential')} and kept "
                    f"{_count_label(kept_count, 'credential')} "
                    f"({_count_label(unique_email_count, 'unique email address')})."
                ),
            }
        )

    except Exception as e:
        log.error(f"Error occurred while deduplicating credentials in batch: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "deleted_count": 0,
                "kept_count": 0,
                "total_count": 0,
                "message": INTERNAL_SERVER_ERROR_DETAIL,
            },
        )


async def verify_credential_common(filename: str, mode: str = "code_assist") -> JSONResponse:
    mode = validate_mode(mode)
    filename = validate_credential_filename(filename)

    storage_adapter = await get_storage_adapter()

    credential_data = await storage_adapter.get_credential(filename, mode=mode)
    if not credential_data:
        raise HTTPException(status_code=404, detail="Credential does not exist.")

    rejection = reject_unsupported_credential_operation(
        credential_data,
        "verify",
        mode=mode,
    )
    if rejection:
        return rejection

    provider_id = get_credential_provider(credential_data)
    if mode == "primary" and provider_id in EXTENDED_PROVIDERS:
        from core.extended_provider_runtime import discover_extended_models

        try:
            if provider_id == "muse_code":
                from core.muse_code import discover_minted_models, refresh_credential

                credential_data = await refresh_credential(credential_data)
                models = await discover_minted_models(credential_data)
            else:
                models = await discover_extended_models(credential_data)
        except ValueError as exc:
            return JSONResponse(
                status_code=getattr(exc, "status_code", 400),
                content={
                    "success": False,
                    "filename": filename,
                    "provider": provider_id,
                    "message": str(exc),
                },
            )
        credential_data["model_ids"] = models
        stored = await storage_adapter.store_credential(filename, credential_data, mode=mode)
        if provider_id == "muse_code" and not stored:
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "filename": filename,
                    "provider": provider_id,
                    "message": "Unable to save Muse Code credentials.",
                },
            )
        # Do not clear prior inference errors based on a possibly public catalog.
        return JSONResponse(
            content={
                "success": True,
                "filename": filename,
                "provider": provider_id,
                "model_count": len(models),
                "connection_test_required": True,
                "message": "Model catalog refreshed. Test a model to check inference access.",
            }
        )
    if mode == "primary" and provider_id == GOOGLE_AI_STUDIO:
        try:
            validation = await validate_api_key(str(credential_data.get("api_key") or ""))
        except GoogleAIStudioError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "success": False,
                    "filename": filename,
                    "provider": provider_id,
                    "message": str(exc),
                },
            )

        credential_data["model_ids"] = validation.model_ids
        await storage_adapter.store_credential(filename, credential_data, mode=mode)
        await storage_adapter.update_credential_state(
            filename,
            {"error_codes": [], "error_messages": {}},
            mode=mode,
        )
        return JSONResponse(
            content={
                "success": True,
                "filename": filename,
                "provider": provider_id,
                "credential_type": "api_key",
                "model_count": validation.model_count,
                "message": (
                    "Google AI Studio API key verified. Provider metadata was "
                    "refreshed, the enabled state was preserved, and recorded errors were cleared."
                ),
            }
        )

    if mode == "primary" and provider_id == XAI:
        credential_type = str(credential_data.get("credential_type") or "").lower()
        try:
            if credential_type == "oauth":
                credential_data = await refresh_xai_oauth_credential(credential_data)
            access_token = (
                credential_data.get("api_key")
                or credential_data.get("access_token")
                or credential_data.get("token")
            )
            model_ids = (
                await fetch_xai_oauth_model_ids(str(access_token or ""))
                if credential_type == "oauth"
                else await fetch_xai_model_ids(str(access_token or ""))
            )
        except XaiError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "success": False,
                    "filename": filename,
                    "provider": provider_id,
                    "message": str(exc),
                },
            )
        credential_data["model_ids"] = model_ids
        await storage_adapter.store_credential(filename, credential_data, mode=mode)
        await storage_adapter.update_credential_state(
            filename,
            {"error_codes": [], "error_messages": {}},
            mode=mode,
        )
        return JSONResponse(
            content={
                "success": True,
                "filename": filename,
                "provider": provider_id,
                "credential_type": credential_type,
                "model_count": len(model_ids),
                "message": (
                    f"{'Grok Build OAuth credential' if credential_type == 'oauth' else 'SpaceXAI Console API key'} "
                    "verified. Available models were refreshed, the enabled state was preserved, "
                    "and recorded errors were cleared."
                ),
            }
        )

    if mode == "primary" and provider_id == OPENAI:
        credential_variant = get_credential_provider_variant(credential_data)
        credential_type = "api_key" if credential_variant == OPENAI_PLATFORM else "oauth"

        async def refresh_codex_credential() -> dict:
            refreshed = await refresh_codex_oauth_credential(credential_data)
            await storage_adapter.store_credential(filename, refreshed, mode=mode)
            log.info(f"Codex token automatically refreshed: {filename}")
            return refreshed

        try:
            if credential_variant == CODEX:
                if not (credential_data.get("access_token") or credential_data.get("token")):
                    credential_data = await refresh_codex_credential()

                access_token = str(
                    credential_data.get("access_token") or credential_data.get("token") or ""
                )
                account_id = str(credential_data.get("account_id") or "").strip()
                try:
                    model_ids = await fetch_codex_model_ids(access_token, account_id)
                except CodexError as exc:
                    if exc.status_code != 401 or not credential_data.get("refresh_token"):
                        raise
                    credential_data = await refresh_codex_credential()
                    access_token = str(
                        credential_data.get("access_token") or credential_data.get("token") or ""
                    )
                    account_id = str(credential_data.get("account_id") or "").strip()
                    model_ids = await fetch_codex_model_ids(access_token, account_id)
            else:
                model_ids = await fetch_openai_model_ids(str(credential_data.get("api_key") or ""))
        except (CodexError, OpenAIPlatformError, ValueError) as exc:
            return JSONResponse(
                status_code=getattr(exc, "status_code", 400),
                content={
                    "success": False,
                    "filename": filename,
                    "provider": provider_id,
                    "credential_type": credential_type,
                    "message": str(exc),
                },
            )

        credential_data["model_ids"] = model_ids
        await storage_adapter.store_credential(filename, credential_data, mode=mode)
        await storage_adapter.update_credential_state(
            filename,
            {"error_codes": [], "error_messages": {}},
            mode=mode,
        )
        credential_name = (
            "Codex OAuth credential" if credential_variant == CODEX else "OpenAI Platform API key"
        )
        return JSONResponse(
            content={
                "success": True,
                "filename": filename,
                "provider": provider_id,
                "credential_type": credential_type,
                "model_count": len(model_ids),
                "message": (
                    f"{credential_name} verified. Available models were refreshed, "
                    "the enabled state was preserved, and recorded errors were cleared."
                ),
            }
        )

    if mode == "primary" and provider_id == ANTHROPIC:
        credential_type = str(credential_data.get("credential_type") or "").strip().lower()
        try:
            if get_credential_provider_variant(credential_data) == CLAUDE_CODE:
                prepared = await credential_manager.prepare_credential(
                    filename, credential_data, mode=mode
                )
                if not prepared:
                    raise AnthropicError("Claude Code credential could not be refreshed.", 401)
                credential_data = prepared
            model_ids = await fetch_anthropic_model_ids(credential_data)
        except AnthropicError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "success": False,
                    "filename": filename,
                    "provider": provider_id,
                    "credential_type": credential_type,
                    "message": str(exc),
                },
            )
        credential_data["model_ids"] = model_ids
        await storage_adapter.store_credential(filename, credential_data, mode=mode)
        await storage_adapter.update_credential_state(
            filename,
            {"error_codes": [], "error_messages": {}},
            mode=mode,
        )
        credential_name = (
            "Claude Code OAuth credential"
            if credential_type == "oauth"
            else "Claude Platform API key"
        )
        return JSONResponse(
            content={
                "success": True,
                "filename": filename,
                "provider": provider_id,
                "credential_type": credential_type,
                "model_count": len(model_ids),
                "message": (
                    f"{credential_name} verified. Available models were refreshed, "
                    "the enabled state was preserved, and recorded errors were cleared."
                ),
            }
        )

    if mode == "primary" and provider_id == OLLAMA:
        try:
            model_ids = await fetch_ollama_model_ids(
                str(credential_data.get("base_url") or ""),
                str(credential_data.get("api_key") or ""),
            )
        except (OllamaError, ValueError) as exc:
            return JSONResponse(
                status_code=getattr(exc, "status_code", 400),
                content={
                    "success": False,
                    "filename": filename,
                    "provider": provider_id,
                    "credential_type": "connection",
                    "message": str(exc),
                },
            )
        credential_data["model_ids"] = model_ids
        await storage_adapter.store_credential(filename, credential_data, mode=mode)
        await storage_adapter.update_credential_state(
            filename,
            {"error_codes": [], "error_messages": {}},
            mode=mode,
        )
        return JSONResponse(
            content={
                "success": True,
                "filename": filename,
                "provider": provider_id,
                "credential_type": "connection",
                "model_count": len(model_ids),
                "message": (
                    "Ollama connection verified. Available models were refreshed, "
                    "the enabled state was preserved, and recorded errors were cleared."
                ),
            }
        )

    credentials = Credentials.from_dict(credential_data)

    token_refreshed = await credentials.refresh_if_needed()

    if token_refreshed:
        log.info(f"Token automatically refreshed: {filename} (mode = {mode})")
        credential_data = merge_refreshed_credential_data(credential_data, credentials)
        await storage_adapter.store_credential(filename, credential_data, mode=mode)

    if mode == "primary":
        api_base_url = await get_antigravity_api_url()
        user_agent = await get_antigravity_user_agent()
        project_id, subscription_tier, credit_amount = await fetch_project_id_and_tier(
            access_token=credentials.access_token,
            user_agent=user_agent,
            api_base_url=api_base_url,
            include_credits=True,
        )
        try:
            model_ids = await fetch_antigravity_model_ids(
                credentials.access_token,
                api_base_url=api_base_url,
                user_agent=user_agent,
            )
        except AntigravityError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "success": False,
                    "filename": filename,
                    "provider": provider_id,
                    "message": str(exc),
                },
            )
        credential_data["model_ids"] = model_ids
    else:
        credit_amount = None
        subscription_tier = None
        user_projects = await get_user_projects(credentials)
        if user_projects:
            if len(user_projects) == 1:
                project_id = user_projects[0].get("projectId")
            else:
                project_id = await select_default_project(user_projects)
        else:
            project_id = None

        if project_id:
            log.info(f"Enabling required API services for project {project_id}.")
            try:
                await enable_required_apis(credentials, project_id)
            except Exception as e:
                log.warning(f"Failed to enable API service: {e}")

    if project_id:
        credential_data["project_id"] = project_id

    if project_id or subscription_tier:
        await storage_adapter.store_credential(filename, credential_data, mode=mode)

        state_update = {"error_codes": []}

        state_update["tier"] = subscription_tier

        if mode == "code_assist":
            state_update["preview"] = True

        await storage_adapter.update_credential_state(filename, state_update, mode=mode)

        log.info(
            f"Verified {mode} credential: {filename}. Project ID: {project_id}. Tier: {subscription_tier}. Enabled state preserved and error codes cleared."
        )

        response_data = {
            "success": True,
            "filename": filename,
            "project_id": project_id,
            "subscription_tier": subscription_tier,
            "message": "Verification complete. Project ID was updated, the enabled state was preserved, and recorded error codes were cleared.",
        }

        if mode == "primary" and credit_amount is not None:
            response_data["credit_amount"] = credit_amount
        if mode == "primary":
            response_data["model_count"] = len(credential_data.get("model_ids") or [])

        return JSONResponse(content=response_data)
    else:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "filename": filename,
                "message": "Verification failed. Unable to retrieve a Project ID. Check whether the credential is still valid.",
            },
        )


# =============================================================================

# =============================================================================
