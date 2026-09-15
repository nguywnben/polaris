import asyncio
import json
import os
import time
from typing import List

from config import (
    get_antigravity_api_url,
    get_code_assist_endpoint,
    get_google_ai_studio_api_url,
)
from core.anthropic import (
    AnthropicError,
    refresh_claude_oauth_credential,
    validate_anthropic_api_key,
)
from core.anthropic_usage import fetch_anthropic_oauth_usage
from core.api.primary import fetch_quota_info
from core.codex import CodexError, refresh_codex_oauth_credential
from core.codex_usage import fetch_codex_usage
from core.credential_batch_operations import (
    BATCH_ACTION_OPERATIONS,
    BATCH_ITEM_TIMEOUT_SECONDS,
    BATCH_PREVIEW_TTL_SECONDS,
    assert_idempotency_reservation,
    batch_request_fingerprint,
    batch_requires_preview,
    build_batch_plan,
    get_idempotent_response,
    issue_batch_preview,
    preview_matches,
    public_batch_plan,
    release_idempotency_reservation,
    store_idempotent_response,
)
from core.credential_fleet_query import (
    credential_selection_registry,
    load_credential_fleet_items,
    select_credential_filenames,
)
from core.credential_manager import credential_manager
from core.credential_operation_evidence import record_durable_credential_mutation
from core.extended_provider_runtime import (
    discover_extended_models,
    normalize_extended_credential,
    test_extended_credential,
)
from core.google_ai_studio import (
    GoogleAIStudioError,
    build_api_key_headers,
    build_generation_url,
    validate_api_key,
)
from core.google_oauth_api import Credentials, merge_refreshed_credential_data
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.model_pool import ModelPoolError, model_catalog_service, normalize_model_id
from core.models import (
    CredentialBatchOperationResponse,
    CredentialModelTestRequest,
    CredentialUpdateRequest,
    CredFileActionRequest,
    CredFileBatchActionRequest,
)
from core.ollama import OllamaError, normalize_ollama_base_url, validate_ollama_connection
from core.openai_platform import OpenAIPlatformError, validate_openai_api_key
from core.pool_import import PoolImportError, restore_pool_archive
from core.provider_connection_diagnostics import (
    CONNECTION_TEST_TIMEOUT_SECONDS,
    ConnectionTestDisconnected,
    ConnectionTestTimedOut,
    build_connection_test_failure,
    classify_provider_exception,
    classify_provider_response,
    connection_diagnostic,
    run_bounded_connection_test,
)
from core.provider_registry import (
    ANTHROPIC,
    EXTENDED_CONNECTION_FIELDS,
    EXTENDED_PROVIDERS,
    GOOGLE_AI_STUDIO,
    OLLAMA,
    OPENAI,
    XAI,
    api_key_fingerprint,
    credential_supports_operation,
    get_credential_provider,
    get_credential_provider_variant,
    get_declared_credential_models,
    get_static_credential_identity,
    is_api_key_credential,
)
from core.storage_adapter import get_storage_adapter
from core.utils import CODE_ASSIST_USER_AGENT, verify_panel_token
from core.xai import XaiError, refresh_xai_oauth_credential, validate_xai_api_key
from core.xai_billing import fetch_xai_billing_usage
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from log import log

from .credential_operations import (
    _get_download_filename,
    clear_all_model_cooldowns_for_credential,
    deduplicate_credentials_by_email_common,
    download_all_creds_common,
    fetch_user_email_common,
    get_creds_status_common,
    refresh_all_user_emails_common,
    reject_unsupported_credential_operation,
    upload_credentials_common,
    verify_credential_common,
)
from .utils import (
    internal_server_error,
    public_error_detail,
    validate_credential_filename,
    validate_mode,
)

router = APIRouter(tags=["credentials"])


def _extended_configuration_fields(provider: str) -> tuple[str, ...]:
    if provider == "kiro":
        return ("region", "profile_arn")
    if provider not in EXTENDED_PROVIDERS:
        return ()
    extra = {"cloudflare": "account_id", "kilo": "organization_id", "opencode": "plan"}
    return ("base_url", extra[provider]) if provider in extra else ("base_url",)


async def _get_available_credential_models(credential_data: dict) -> list[str]:
    """Return models that can be selected for one credential test."""
    declared_models = get_declared_credential_models(credential_data)
    if declared_models:
        return declared_models

    provider_id = get_credential_provider(credential_data)
    if provider_id in EXTENDED_PROVIDERS:
        return []
    catalog = await model_catalog_service.get_catalog()
    return [entry.model_id for entry in catalog if provider_id in entry.providers]


def _editable_credential_fields(credential_data: dict) -> list[str]:
    if credential_data.get("source") == "environment":
        return []
    fields = ["credential_label"]
    credential_type = str(credential_data.get("credential_type") or "").strip().lower()
    if credential_type == "api_key":
        fields.append("api_key")
    if get_credential_provider(credential_data) == OLLAMA:
        fields.extend(("api_key", "base_url"))
    fields.extend(_extended_configuration_fields(get_credential_provider(credential_data)))
    return list(dict.fromkeys(fields))


def _credential_configuration_payload(filename: str, credential_data: dict) -> dict:
    source = "environment" if credential_data.get("source") == "environment" else "managed"
    provider_id = get_credential_provider(credential_data)
    fields = _editable_credential_fields(credential_data)
    payload = {
        "filename": filename,
        "provider": provider_id,
        "provider_variant": get_credential_provider_variant(credential_data),
        "credential_type": str(credential_data.get("credential_type") or "oauth"),
        "credential_label": credential_data.get("credential_label"),
        "source": source,
        "editable": bool(fields) and credential_supports_operation(credential_data, "edit"),
        "editable_fields": fields,
        "can_reauthenticate": (
            source == "managed" and credential_supports_operation(credential_data, "reauthenticate")
        ),
        "has_api_key": bool(credential_data.get("api_key")),
    }
    if provider_id == OLLAMA:
        payload["base_url"] = str(credential_data.get("base_url") or "")
    for field in _extended_configuration_fields(provider_id):
        payload[field] = str(credential_data.get(field) or "")
        payload[f"has_{field}"] = bool(payload[field])
    return payload


async def _validate_credential_update(candidate: dict, changed_fields: set[str]) -> None:
    provider_id = get_credential_provider(candidate)
    credential_type = str(candidate.get("credential_type") or "").strip().lower()

    if provider_id in EXTENDED_PROVIDERS:
        if changed_fields & {"api_key", *EXTENDED_CONNECTION_FIELDS}:
            # Connection changes invalidate the old catalog, including protocol
            # families which may no longer be supported after an OpenCode plan edit.
            candidate["model_ids"] = []
            if "plan" in changed_fields and "base_url" not in changed_fields:
                candidate["base_url"] = ""
            candidate.update(normalize_extended_credential(candidate))
            candidate["model_ids"] = await discover_extended_models(candidate)
        return

    if provider_id == OLLAMA:
        if changed_fields & {"api_key", "base_url"}:
            validation = await validate_ollama_connection(
                str(candidate.get("base_url") or ""),
                str(candidate.get("api_key") or ""),
            )
            candidate["model_ids"] = validation.model_ids
        return

    if "base_url" in changed_fields:
        raise HTTPException(
            status_code=422,
            detail="The endpoint can only be edited for Ollama connections.",
        )
    if "api_key" not in changed_fields:
        return
    if credential_type != "api_key":
        raise HTTPException(
            status_code=422,
            detail="OAuth secrets cannot be edited. Re-authenticate the account instead.",
        )

    api_key = str(candidate.get("api_key") or "")
    if provider_id == GOOGLE_AI_STUDIO:
        validation = await validate_api_key(api_key)
    elif provider_id == XAI:
        validation = await validate_xai_api_key(api_key)
    elif provider_id == OPENAI:
        validation = await validate_openai_api_key(api_key)
    elif provider_id == ANTHROPIC:
        validation = await validate_anthropic_api_key(api_key)
    else:
        raise HTTPException(status_code=422, detail="This API key type cannot be edited.")
    candidate["model_ids"] = validation.model_ids


@router.get("/configuration/{filename}")
async def get_credential_configuration(
    filename: str,
    token: str = Depends(verify_panel_token),
    mode: str = "provider",
):
    """Return only safe fields needed by the provider-pool edit form."""
    mode = validate_mode(mode)
    if mode != "primary":
        raise HTTPException(status_code=400, detail="Only provider-pool credentials are editable.")
    filename = validate_credential_filename(filename)
    storage_adapter = await get_storage_adapter()
    credential_data = await storage_adapter.get_credential(filename, mode=mode)
    if not credential_data:
        raise HTTPException(status_code=404, detail="Credential does not exist.")
    rejection = reject_unsupported_credential_operation(credential_data, "edit", mode=mode)
    if rejection:
        return rejection
    return JSONResponse(content=_credential_configuration_payload(filename, credential_data))


@router.patch("/configuration/{filename}")
async def update_credential_configuration(
    filename: str,
    request: CredentialUpdateRequest,
    token: str = Depends(verify_panel_token),
    mode: str = "provider",
):
    """Validate and update safe provider-pool credential fields in place."""
    mode = validate_mode(mode)
    if mode != "primary":
        raise HTTPException(status_code=400, detail="Only provider-pool credentials are editable.")
    filename = validate_credential_filename(filename)
    storage_adapter = await get_storage_adapter()
    credential_data = await storage_adapter.get_credential(filename, mode=mode)
    if not credential_data:
        raise HTTPException(status_code=404, detail="Credential does not exist.")
    rejection = reject_unsupported_credential_operation(credential_data, "edit", mode=mode)
    if rejection:
        return rejection
    if credential_data.get("source") == "environment":
        raise HTTPException(
            status_code=409,
            detail="This credential is managed by environment variables and is read-only here.",
        )

    changed_fields = set(request.model_fields_set)
    editable_fields = set(_editable_credential_fields(credential_data))
    unsupported = sorted(changed_fields - editable_fields)
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported credential field(s): {', '.join(unsupported)}.",
        )

    candidate = dict(credential_data)
    if "credential_label" in changed_fields:
        candidate["credential_label"] = str(request.credential_label or "").strip()
    if "api_key" in changed_fields:
        candidate["api_key"] = request.api_key.get_secret_value().strip() if request.api_key else ""
        if not candidate["api_key"] and get_credential_provider(candidate) in EXTENDED_PROVIDERS:
            candidate["api_key"] = credential_data.get("api_key", "")
            changed_fields.discard("api_key")
    if "base_url" in changed_fields:
        try:
            candidate["base_url"] = str(request.base_url or "")
            if get_credential_provider(candidate) == OLLAMA:
                candidate["base_url"] = normalize_ollama_base_url(candidate["base_url"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    for field in set(EXTENDED_CONNECTION_FIELDS) - {"base_url"}:
        if field in changed_fields:
            candidate[field] = str(getattr(request, field) or "").strip()

    try:
        await _validate_credential_update(candidate, changed_fields)
    except (GoogleAIStudioError, XaiError, OpenAIPlatformError, AnthropicError, OllamaError) as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400),
            detail=public_error_detail(exc),
        ) from exc
    except ValueError as exc:
        if get_credential_provider(candidate) not in EXTENDED_PROVIDERS:
            raise
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400),
            detail=public_error_detail(exc)
            if hasattr(exc, "status_code")
            else "Invalid provider credential.",
        ) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Provider model discovery timed out.") from exc

    if changed_fields & {"api_key", *EXTENDED_CONNECTION_FIELDS}:
        if get_credential_provider(candidate) == OLLAMA:
            candidate["connection_fingerprint"] = api_key_fingerprint(
                f"{str(candidate.get('base_url') or '').rstrip('/')}\0"
                f"{str(candidate.get('api_key') or '')}"
            )
        elif is_api_key_credential(candidate):
            candidate["key_fingerprint"] = api_key_fingerprint(str(candidate.get("api_key") or ""))
        candidate_identity = get_static_credential_identity(candidate)
        for other_filename, other_data in (
            await storage_adapter.get_all_credentials(mode=mode)
        ).items():
            if (
                other_filename != filename
                and get_static_credential_identity(other_data) == candidate_identity
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Another provider-pool credential already uses this connection.",
                )

    stored = await storage_adapter.store_credential(filename, candidate, mode=mode)
    if not stored:
        raise HTTPException(status_code=500, detail="The credential update could not be stored.")
    return JSONResponse(
        content={
            **_credential_configuration_payload(filename, candidate),
            "success": True,
            "changed_fields": sorted(changed_fields),
            "model_count": len(get_declared_credential_models(candidate)),
            "message": "Credential settings updated and validated.",
        }
    )


def _credential_test_failure_response(
    diagnostic,
    *,
    status_code: int,
    filename: str,
    provider: str = "",
    credential_type: object = None,
    model: str = "",
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=build_connection_test_failure(
            diagnostic,
            filename=filename,
            provider=provider,
            credential_type=credential_type,
            model=model,
            status_code=status_code,
        ),
    )


@router.post("/upload")
async def upload_credentials(
    files: List[UploadFile] = File(...),
    token: str = Depends(verify_panel_token),
    mode: str = "code_assist",
):
    try:
        mode = validate_mode(mode)
        return await upload_credentials_common(files, mode=mode)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Batch import failed: {e}")
        raise internal_server_error() from e


@router.get("/status")
async def get_creds_status(
    token: str = Depends(verify_panel_token),
    offset: int = 0,
    limit: int = 50,
    status_filter: str = "all",
    error_code_filter: str = "all",
    cooldown_filter: str = "all",
    preview_filter: str = "all",
    tier_filter: str = "all",
    provider_filter: str = "all",
    provider_variant_filter: str = "all",
    credential_kind_filter: str = "all",
    health_filter: str = "all",
    quota_state_filter: str = "all",
    source_filter: str = "all",
    mode: str = "code_assist",
):
    try:
        mode = validate_mode(mode)
        return await get_creds_status_common(
            offset,
            limit,
            status_filter,
            mode=mode,
            error_code_filter=error_code_filter,
            cooldown_filter=cooldown_filter,
            preview_filter=preview_filter,
            tier_filter=tier_filter,
            provider_filter=provider_filter,
            provider_variant_filter=provider_variant_filter,
            credential_kind_filter=credential_kind_filter,
            health_filter=health_filter,
            quota_state_filter=quota_state_filter,
            source_filter=source_filter,
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to retrieve credential status: {e}")
        raise internal_server_error() from e


@router.get("/models/{filename}")
async def get_credential_models(
    filename: str,
    token: str = Depends(verify_panel_token),
    mode: str = "primary",
):
    """Return public model metadata for one credential without exposing secrets."""
    try:
        mode = validate_mode(mode)
        filename = validate_credential_filename(filename)
        storage_adapter = await get_storage_adapter()
        credential_data = await storage_adapter.get_credential(filename, mode=mode)
        if not credential_data:
            raise HTTPException(status_code=404, detail="Credential does not exist.")

        rejection = reject_unsupported_credential_operation(
            credential_data,
            "model_discovery",
            mode=mode,
        )
        if rejection:
            return rejection

        if mode == "primary" and get_credential_provider(credential_data) in EXTENDED_PROVIDERS:
            candidate = dict(credential_data)
            candidate["model_ids"] = []
            candidate.update(normalize_extended_credential(candidate))
            model_ids = await discover_extended_models(candidate)
            candidate["model_ids"] = model_ids
            if not await storage_adapter.store_credential(filename, candidate, mode=mode):
                raise HTTPException(
                    status_code=500, detail="The credential update could not be stored."
                )
        else:
            model_ids = await _get_available_credential_models(credential_data)
        return JSONResponse(
            content={
                "success": True,
                "filename": filename,
                "provider": get_credential_provider(credential_data),
                "model_count": len(model_ids),
                "model_ids": model_ids,
            }
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 400),
            detail=public_error_detail(exc)
            if hasattr(exc, "status_code")
            else "Invalid provider credential.",
        ) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Provider model discovery timed out.") from exc
    except Exception as exc:
        log.error(f"Failed to retrieve credential models: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve credential models.",
        ) from exc


@router.get("/detail/{filename}")
async def get_cred_detail(
    filename: str, token: str = Depends(verify_panel_token), mode: str = "code_assist"
):
    try:
        mode = validate_mode(mode)
        filename = validate_credential_filename(filename)

        storage_adapter = await get_storage_adapter()
        backend_info = await storage_adapter.get_backend_info()
        backend_type = backend_info.get("backend_type", "unknown")

        credential_data = await storage_adapter.get_credential(filename, mode=mode)
        if not credential_data:
            raise HTTPException(status_code=404, detail="Credential does not exist.")

        file_status = await storage_adapter.get_credential_state(filename, mode=mode)
        if not file_status:
            file_status = {
                "error_codes": [],
                "disabled": False,
                "last_success": time.time(),
                "user_email": None,
            }

        result = {
            "status": file_status,
            "content": credential_data,
            "filename": os.path.basename(filename),
            "backend_type": backend_type,
            "user_email": file_status.get("user_email"),
            "model_cooldowns": file_status.get("model_cooldowns", {}),
        }

        if mode == "code_assist":
            result["preview"] = file_status.get("preview", True)
        else:
            result["enable_credit"] = file_status.get("enable_credit", False)

        return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to retrieve credential details {filename}: {e}")
        raise internal_server_error() from e


async def _apply_credential_action(
    storage_adapter,
    filename: str,
    credential_data: dict,
    action: str,
    *,
    mode: str,
) -> JSONResponse:
    operation = BATCH_ACTION_OPERATIONS.get(action)
    if not operation:
        raise HTTPException(status_code=400, detail="Invalid credential action.")

    rejection = reject_unsupported_credential_operation(
        credential_data,
        operation,
        mode=mode,
    )
    if rejection:
        return rejection

    if action in {"enable", "disable"}:
        disabled = action == "disable"
        updated = await credential_manager.set_cred_disabled(filename, disabled, mode=mode)
        if not updated:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to {action} the credential. It may no longer exist.",
            )
        return JSONResponse(content={"message": f"Credential {action}d."})

    if action == "delete":
        deleted = await credential_manager.remove_credential(filename, mode=mode)
        if not deleted:
            raise HTTPException(status_code=500, detail="Failed to delete the credential.")
        return JSONResponse(
            content={
                "success": True,
                "deleted": True,
                "history_retained_anonymously": True,
                "message": "Credential deleted. Historical usage was retained anonymously.",
            }
        )

    if mode != "primary":
        raise HTTPException(
            status_code=400,
            detail="Credit usage is only available for provider-pool credentials.",
        )
    enable_credit = action == "enable_credit"
    updated = await storage_adapter.update_credential_state(
        filename,
        {"enable_credit": enable_credit},
        mode=mode,
    )
    if not updated:
        verb = "enable" if enable_credit else "disable"
        raise HTTPException(
            status_code=500,
            detail=f"Failed to {verb} credit usage. The credential may no longer exist.",
        )
    await clear_all_model_cooldowns_for_credential(storage_adapter, filename, mode)
    state = "enabled" if enable_credit else "disabled"
    return JSONResponse(content={"message": f"Credit usage {state} for this credential."})


async def _execute_credential_action(
    storage_adapter,
    filename: str,
    credential_data: dict,
    action: str,
    *,
    mode: str,
    timeout_seconds: float | None = None,
) -> JSONResponse:
    started_at = time.perf_counter()
    operation = BATCH_ACTION_OPERATIONS.get(action, "unknown")
    variant_id = get_credential_provider_variant(credential_data)
    outcome = "failed"
    summary_code = "operation_failed"
    try:
        operation_coro = _apply_credential_action(
            storage_adapter,
            filename,
            credential_data,
            action,
            mode=mode,
        )
        response = (
            await asyncio.wait_for(operation_coro, timeout=timeout_seconds)
            if timeout_seconds is not None
            else await operation_coro
        )
        if response.status_code == 422:
            outcome = "unsupported"
            summary_code = "credential_operation_unsupported"
        elif response.status_code >= 400:
            outcome = "failed"
            summary_code = "operation_failed"
        else:
            outcome = "succeeded"
            summary_code = "operation_succeeded"
        return response
    except TimeoutError:
        outcome = "timed_out"
        summary_code = "operation_timed_out"
        raise
    except asyncio.CancelledError:
        outcome = "cancelled"
        summary_code = "operation_cancelled"
        raise
    except HTTPException as exc:
        outcome = "failed"
        summary_code = f"http_{exc.status_code}"
        raise
    finally:
        await record_durable_credential_mutation(
            action=action,
            operation=operation,
            mode=mode,
            filename=filename,
            variant_id=variant_id,
            outcome=outcome,
            duration_ms=(time.perf_counter() - started_at) * 1000,
            summary_code=summary_code,
        )


@router.post("/action")
async def creds_action(
    request: CredFileActionRequest,
    token: str = Depends(verify_panel_token),
    mode: str = "code_assist",
):
    started_at = time.perf_counter()
    evidence_emitted = False
    evidence_mode = mode
    try:
        mode = validate_mode(mode)
        evidence_mode = mode
        try:
            filename = validate_credential_filename(request.filename)
        except HTTPException:
            await record_durable_credential_mutation(
                action=request.action,
                operation=BATCH_ACTION_OPERATIONS.get(request.action, "unknown"),
                mode=mode,
                filename=request.filename,
                variant_id="unknown",
                outcome="invalid",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                summary_code="invalid_filename",
            )
            evidence_emitted = True
            raise
        log.info(f"Performing credential action '{request.action}' on {filename} (mode={mode}).")

        storage_adapter = await get_storage_adapter()
        credential_data = await storage_adapter.get_credential(filename, mode=mode)
        if not credential_data:
            await record_durable_credential_mutation(
                action=request.action,
                operation=BATCH_ACTION_OPERATIONS.get(request.action, "unknown"),
                mode=mode,
                filename=filename,
                variant_id="unknown",
                outcome="not_found",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                summary_code="credential_not_found",
            )
            evidence_emitted = True
            raise HTTPException(status_code=404, detail="Credential file does not exist.")
        evidence_emitted = True
        return await _execute_credential_action(
            storage_adapter,
            filename,
            credential_data,
            request.action,
            mode=mode,
        )
    except HTTPException:
        raise
    except Exception as e:
        if not evidence_emitted:
            await record_durable_credential_mutation(
                action=request.action,
                operation=BATCH_ACTION_OPERATIONS.get(request.action, "unknown"),
                mode=evidence_mode,
                filename=request.filename,
                variant_id="unknown",
                outcome="failed",
                duration_ms=(time.perf_counter() - started_at) * 1000,
                summary_code="operation_failed",
            )
        log.error("Credential file operation failed; internal detail was withheld.")
        raise internal_server_error() from e


@router.post(
    "/batch-action",
    response_model=CredentialBatchOperationResponse,
    response_model_exclude_none=True,
)
async def creds_batch_action(
    request: CredFileBatchActionRequest,
    token: str = Depends(verify_panel_token),
    mode: str = "code_assist",
):
    reservation = None
    mutation_started = False
    target_fingerprint = ""
    idempotency_fingerprint = ""
    planning_complete = False
    evidence_mode = mode
    filenames = list(request.filenames)
    storage_adapter = None
    try:
        mode = validate_mode(mode)
        evidence_mode = mode
        action = request.action
        has_explicit_targets = bool(filenames)
        has_selection = bool(request.selection_token)
        if has_explicit_targets == has_selection:
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "code": "credential_batch_target_scope_invalid",
                        "message": (
                            "Provide either explicit credential filenames or one selection token."
                        ),
                    }
                },
            )
        idempotency_targets = (
            filenames if has_explicit_targets else [f"selection:{request.selection_token or ''}"]
        )
        idempotency_fingerprint = batch_request_fingerprint(
            mode,
            action,
            idempotency_targets,
        )
        try:
            cached = await get_idempotent_response(
                request.idempotency_key,
                idempotency_fingerprint,
            )
        except HTTPException as exc:
            return _batch_coordination_error(exc)
        if cached and not request.preview:
            status_code, body = cached
            return JSONResponse(status_code=status_code, content=body)

        if has_selection:
            try:
                filters = credential_selection_registry.resolve(
                    request.selection_token or "",
                    mode=mode,
                )
            except ValueError:
                return JSONResponse(
                    status_code=410,
                    content={
                        "error": {
                            "code": "credential_selection_expired",
                            "message": "Refresh the fleet selection before running this batch.",
                        }
                    },
                )
            storage_adapter = await get_storage_adapter()
            fleet_items = await load_credential_fleet_items(storage_adapter, mode=mode)
            filenames = select_credential_filenames(fleet_items, filters)
            if not filenames:
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": {
                            "code": "credential_selection_empty",
                            "message": "No credentials currently match this selection.",
                        }
                    },
                )
            if len(filenames) > 100:
                return JSONResponse(
                    status_code=422,
                    content={
                        "error": {
                            "code": "credential_selection_limit_exceeded",
                            "message": "Narrow the fleet selection to 100 credentials or fewer.",
                            "matching_count": len(filenames),
                            "maximum_count": 100,
                        }
                    },
                )
        target_fingerprint = batch_request_fingerprint(mode, action, filenames)
        requires_preview = batch_requires_preview(action, len(filenames))

        if not request.preview and requires_preview:
            try:
                preview_is_current = await preview_matches(
                    request.preview_token, target_fingerprint
                )
            except HTTPException as exc:
                return _batch_coordination_error(exc)
            if not preview_is_current:
                return JSONResponse(
                    status_code=428,
                    content={
                        "error": {
                            "code": "credential_batch_preview_required",
                            "message": "Run a fresh matching preview before executing this batch.",
                            "requires_preview": True,
                        }
                    },
                )
            if not request.idempotency_key:
                return JSONResponse(
                    status_code=428,
                    content={
                        "error": {
                            "code": "credential_batch_idempotency_required",
                            "message": "An idempotency key is required for this batch.",
                        }
                    },
                )

        if not request.preview and request.idempotency_key:
            try:
                cached = await get_idempotent_response(
                    request.idempotency_key,
                    idempotency_fingerprint,
                    reserve=True,
                )
            except HTTPException as exc:
                return _batch_coordination_error(exc)
            if isinstance(cached, tuple):
                status_code, body = cached
                return JSONResponse(status_code=status_code, content=body)
            reservation = cached

        log.info(
            f"Planning credential batch action '{action}' for {len(filenames)} targets "
            f"(mode={mode}, preview={request.preview})."
        )
        if storage_adapter is None:
            storage_adapter = await get_storage_adapter()
        results = await build_batch_plan(storage_adapter, action, filenames, mode=mode)
        planning_complete = True

        if request.preview:
            try:
                preview_token = await issue_batch_preview(target_fingerprint)
            except HTTPException as exc:
                return _batch_coordination_error(exc)
            body = _batch_response_body(
                action,
                results,
                preview=True,
                requires_preview=requires_preview,
            )
            body["preview_token"] = preview_token
            body["preview_expires_in_seconds"] = BATCH_PREVIEW_TTL_SECONDS
            return JSONResponse(content=body)

        for item in results:
            if item["status"] != "eligible":
                await record_durable_credential_mutation(
                    action=action,
                    operation=item["operation"],
                    mode=mode,
                    filename=item["filename"] or filenames[item["target_index"]],
                    variant_id=item["variant_id"],
                    outcome=item["status"],
                    duration_ms=0,
                    summary_code=item["code"],
                )
                continue
            try:
                await assert_idempotency_reservation(reservation)
                mutation_started = True
                response = await _execute_credential_action(
                    storage_adapter,
                    item["filename"],
                    item["credential_data"],
                    action,
                    mode=mode,
                    timeout_seconds=BATCH_ITEM_TIMEOUT_SECONDS,
                )
                if response.status_code >= 400:
                    item["status"] = "unsupported" if response.status_code == 422 else "failed"
                    item["code"] = (
                        "credential_operation_unsupported"
                        if response.status_code == 422
                        else "operation_failed"
                    )
                else:
                    item["status"] = "succeeded"
                    item["code"] = "operation_succeeded"
            except TimeoutError:
                item["status"] = "timed_out"
                item["code"] = "operation_timed_out"
            except HTTPException as exc:
                item["status"] = "failed"
                item["code"] = f"http_{exc.status_code}"
            except Exception:
                item["status"] = "failed"
                item["code"] = "operation_failed"

        body = _batch_response_body(
            action,
            results,
            preview=False,
            requires_preview=requires_preview,
        )
        await store_idempotent_response(
            reservation,
            200,
            body,
        )
        reservation = None
        return JSONResponse(content=body)

    except HTTPException:
        raise
    except Exception as e:
        if not request.preview and not planning_complete:
            for filename in filenames:
                await record_durable_credential_mutation(
                    action=request.action,
                    operation=BATCH_ACTION_OPERATIONS.get(request.action, "unknown"),
                    mode=evidence_mode,
                    filename=filename,
                    variant_id="unknown",
                    outcome="failed",
                    duration_ms=0,
                    summary_code="operation_failed",
                )
        log.error("Batch credential operation failed; internal detail was withheld.")
        raise internal_server_error() from e
    finally:
        if reservation is not None and not mutation_started:
            try:
                await asyncio.shield(release_idempotency_reservation(reservation))
            except Exception:
                log.error("Credential batch reservation release failed.")


def _batch_coordination_error(exc: HTTPException) -> JSONResponse:
    in_progress = "still in progress" in str(exc.detail)
    overloaded = exc.status_code == 429
    unavailable = exc.status_code == 503
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": (
                    "credential_batch_overloaded"
                    if overloaded
                    else (
                        "credential_batch_coordination_unavailable"
                        if unavailable
                        else (
                            "credential_batch_in_progress"
                            if in_progress
                            else "credential_batch_idempotency_conflict"
                        )
                    )
                ),
                "message": (
                    "Too many credential batches are currently in progress."
                    if overloaded
                    else (
                        "Credential batch coordination is temporarily unavailable."
                        if unavailable
                        else (
                            "A batch with this idempotency key is still in progress."
                            if in_progress
                            else "The idempotency key cannot be used for this batch request."
                        )
                    )
                ),
            }
        },
        headers=exc.headers,
    )


def _batch_response_body(
    action: str,
    results: list[dict],
    *,
    preview: bool,
    requires_preview: bool,
) -> dict:
    public_results = public_batch_plan(results)
    outcome_counts: dict[str, int] = {}
    for item in public_results:
        status = item["status"]
        outcome_counts[status] = outcome_counts.get(status, 0) + 1
    success_count = outcome_counts.get("succeeded", 0)
    errors = [
        f"Target {item['target_index']}: {item['code']}"
        for item in public_results
        if item["status"] not in {"eligible", "succeeded"}
    ]
    body = {
        "success": not errors,
        "preview": preview,
        "action": action,
        "operation": BATCH_ACTION_OPERATIONS[action],
        "requires_preview": requires_preview,
        "requested_count": len(public_results),
        "success_count": success_count,
        "total_count": len(public_results),
        "outcome_counts": outcome_counts,
        "results": public_results,
        "errors": errors,
        "message": (
            "Batch preview completed."
            if preview
            else f"Batch operation completed. Processed {success_count}/{len(public_results)} credential files."
        ),
    }
    if action == "delete" and success_count:
        body["history_retained_anonymously"] = True
    return body


@router.get("/download/{filename}")
async def download_cred_file(
    filename: str, token: str = Depends(verify_panel_token), mode: str = "code_assist"
):
    try:
        mode = validate_mode(mode)
        filename = validate_credential_filename(filename)

        storage_adapter = await get_storage_adapter()

        credential_data = await storage_adapter.get_credential(filename, mode=mode)
        if not credential_data:
            raise HTTPException(status_code=404, detail="Credential file does not exist.")

        rejection = reject_unsupported_credential_operation(
            credential_data,
            "export",
            mode=mode,
        )
        if rejection:
            return rejection

        content = json.dumps(credential_data, ensure_ascii=False, indent=2)
        download_filename = await _get_download_filename(
            storage_adapter,
            filename,
            credential_data,
            mode,
        )

        from fastapi.responses import Response

        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={download_filename}"},
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to download credential file: {e}")
        raise internal_server_error() from e


@router.post("/fetch-email/{filename}")
async def fetch_user_email(
    filename: str, token: str = Depends(verify_panel_token), mode: str = "code_assist"
):
    try:
        mode = validate_mode(mode)
        return await fetch_user_email_common(filename, mode=mode)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to retrieve user email: {e}")
        raise internal_server_error() from e


@router.post("/refresh-all-emails")
async def refresh_all_user_emails(
    token: str = Depends(verify_panel_token), mode: str = "code_assist"
):
    try:
        mode = validate_mode(mode)
        return await refresh_all_user_emails_common(mode=mode)
    except Exception as e:
        log.error(f"Failed to retrieve user emails in batch: {e}")
        raise internal_server_error() from e


@router.post("/deduplicate-by-email")
async def deduplicate_credentials_by_email(
    token: str = Depends(verify_panel_token), mode: str = "code_assist"
):
    try:
        mode = validate_mode(mode)
        return await deduplicate_credentials_by_email_common(mode=mode)
    except Exception as e:
        log.error(f"Failed to deduplicate credentials in batch: {e}")
        raise internal_server_error() from e


@router.get("/download-all")
async def download_all_creds(token: str = Depends(verify_panel_token), mode: str = "code_assist"):
    try:
        mode = validate_mode(mode)
        return await download_all_creds_common(mode=mode)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to download package: {e}")
        raise internal_server_error() from e


@router.post("/import")
async def import_pool_credentials(
    archive: UploadFile = File(...),
    token: str = Depends(verify_panel_token),
):
    """Import a mixed-provider credential pool from one ZIP archive."""
    try:
        return JSONResponse(content=await restore_pool_archive(archive))
    except PoolImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.error(f"Pool import failed: {exc}")
        raise HTTPException(status_code=500, detail="Pool archive could not be imported.") from exc


@router.post("/verify/{filename}")
@router.post("/verify-project/{filename}", include_in_schema=False)
async def verify_credential(
    filename: str, token: str = Depends(verify_panel_token), mode: str = "code_assist"
):
    try:
        mode = validate_mode(mode)
        return await verify_credential_common(filename, mode=mode)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to verify credential {filename}: {e}")
        raise internal_server_error() from e


@router.get("/errors/{filename}")
async def get_credential_errors(
    filename: str, token: str = Depends(verify_panel_token), mode: str = "code_assist"
):
    try:
        mode = validate_mode(mode)
        filename = validate_credential_filename(filename)

        storage_adapter = await get_storage_adapter()

        if not hasattr(storage_adapter._backend, "get_credential_errors"):
            raise HTTPException(
                status_code=501,
                detail="The current storage backend does not support retrieving credential error messages.",
            )

        error_info = await storage_adapter._backend.get_credential_errors(filename, mode=mode)

        return JSONResponse(content=error_info)

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to retrieve credential error information {filename}: {e}")
        raise internal_server_error() from e


@router.get("/quota/{filename}")
async def get_credential_quota(
    filename: str, token: str = Depends(verify_panel_token), mode: str = "provider"
):
    try:
        mode = validate_mode(mode)
        filename = validate_credential_filename(filename)

        storage_adapter = await get_storage_adapter()

        credential_data = await storage_adapter.get_credential(filename, mode=mode)
        if not credential_data:
            raise HTTPException(status_code=404, detail="Credential does not exist.")

        rejection = reject_unsupported_credential_operation(
            credential_data,
            "quota",
            mode=mode,
        )
        if rejection:
            return rejection

        provider_id = get_credential_provider(credential_data)
        if provider_id == GOOGLE_AI_STUDIO:
            return JSONResponse(
                content={
                    "success": True,
                    "supported": False,
                    "filename": filename,
                    "provider": provider_id,
                    "models": {},
                    "message": (
                        "Google AI Studio does not expose per-key quota balances "
                        "through the Generative Language API."
                    ),
                }
            )

        if provider_id == OLLAMA:
            return JSONResponse(
                content={
                    "success": True,
                    "supported": False,
                    "filename": filename,
                    "provider": provider_id,
                    "message": "Ollama does not expose a compatible account quota view for this credential.",
                }
            )

        if provider_id == ANTHROPIC:
            if is_api_key_credential(credential_data):
                return JSONResponse(
                    content={
                        "success": True,
                        "supported": False,
                        "filename": filename,
                        "provider": provider_id,
                        "message": (
                            "Subscription quota is available for Claude Code OAuth "
                            "credentials only. Claude Platform does not expose this "
                            "account usage view for API keys."
                        ),
                    }
                )

            async def refresh_anthropic_credential() -> dict:
                refreshed = await refresh_claude_oauth_credential(credential_data)
                await storage_adapter.store_credential(filename, refreshed, mode=mode)
                log.info(f"Claude Code token automatically refreshed: {filename}")
                return refreshed

            if not (credential_data.get("access_token") or credential_data.get("token")):
                credential_data = await refresh_anthropic_credential()
            access_token = credential_data.get("access_token") or credential_data.get("token")

            try:
                quota_info = await fetch_anthropic_oauth_usage(access_token)
            except AnthropicError as exc:
                if exc.status_code == 401 and credential_data.get("refresh_token"):
                    credential_data = await refresh_anthropic_credential()
                    access_token = credential_data.get("access_token") or credential_data.get(
                        "token"
                    )
                    quota_info = await fetch_anthropic_oauth_usage(access_token)
                else:
                    raise

            return JSONResponse(
                content={
                    "success": True,
                    "supported": True,
                    "filename": filename,
                    "provider": provider_id,
                    "provider_variant": "claude_code",
                    **quota_info,
                }
            )

        if provider_id == OPENAI:
            if is_api_key_credential(credential_data):
                return JSONResponse(
                    content={
                        "success": True,
                        "supported": False,
                        "filename": filename,
                        "provider": provider_id,
                        "message": (
                            "Account quota is available for Codex OAuth credentials only. "
                            "OpenAI Platform does not expose this account rate-limit view "
                            "for API keys."
                        ),
                    }
                )

            async def refresh_codex_credential() -> dict:
                refreshed = await refresh_codex_oauth_credential(credential_data)
                await storage_adapter.store_credential(filename, refreshed, mode=mode)
                log.info(f"Codex token automatically refreshed: {filename}")
                return refreshed

            if not (credential_data.get("access_token") or credential_data.get("token")):
                credential_data = await refresh_codex_credential()
            access_token = credential_data.get("access_token") or credential_data.get("token")
            account_id = str(credential_data.get("account_id") or "").strip()

            try:
                quota_info = await fetch_codex_usage(access_token, account_id)
            except CodexError as exc:
                if exc.status_code == 401 and credential_data.get("refresh_token"):
                    credential_data = await refresh_codex_credential()
                    access_token = credential_data.get("access_token") or credential_data.get(
                        "token"
                    )
                    account_id = str(credential_data.get("account_id") or "").strip()
                    quota_info = await fetch_codex_usage(access_token, account_id)
                else:
                    raise

            return JSONResponse(
                content={
                    "success": True,
                    "supported": True,
                    "filename": filename,
                    "provider": provider_id,
                    **quota_info,
                }
            )

        if provider_id == XAI:
            if is_api_key_credential(credential_data):
                return JSONResponse(
                    content={
                        "success": True,
                        "supported": False,
                        "filename": filename,
                        "provider": provider_id,
                        "message": (
                            "Account quota is available for Grok Build OAuth credentials only. "
                            "SpaceXAI Console does not expose this billing view for API keys."
                        ),
                    }
                )

            async def refresh_oauth_credential() -> dict:
                refreshed = await refresh_xai_oauth_credential(credential_data)
                await storage_adapter.store_credential(filename, refreshed, mode=mode)
                log.info(f"Grok Build token automatically refreshed: {filename}")
                return refreshed

            if not (credential_data.get("access_token") or credential_data.get("token")):
                credential_data = await refresh_oauth_credential()
            access_token = credential_data.get("access_token") or credential_data.get("token")

            try:
                quota_info = await fetch_xai_billing_usage(access_token)
            except XaiError as exc:
                if exc.status_code == 401 and credential_data.get("refresh_token"):
                    credential_data = await refresh_oauth_credential()
                    access_token = credential_data.get("access_token") or credential_data.get(
                        "token"
                    )
                    quota_info = await fetch_xai_billing_usage(access_token)
                else:
                    raise

            return JSONResponse(
                content={
                    "success": True,
                    "supported": True,
                    "filename": filename,
                    "provider": provider_id,
                    **quota_info,
                }
            )

        from core.google_oauth_api import Credentials

        creds = Credentials.from_dict(credential_data)

        await creds.refresh_if_needed()

        updated_data = merge_refreshed_credential_data(credential_data, creds)
        if updated_data != credential_data:
            log.info(f"Token automatically refreshed: {filename}")
            await storage_adapter.store_credential(filename, updated_data, mode=mode)
            credential_data = updated_data

        access_token = credential_data.get("access_token") or credential_data.get("token")
        if not access_token:
            raise HTTPException(
                status_code=400, detail="Credential does not contain an access token."
            )

        quota_info = await fetch_quota_info(access_token)

        if quota_info.get("success"):
            return JSONResponse(
                content={
                    "success": True,
                    "filename": filename,
                    "models": quota_info.get("models", {}),
                }
            )
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "filename": filename,
                    "error": quota_info.get("error", "Unknown error."),
                },
            )

    except (AnthropicError, CodexError, OllamaError, XaiError) as e:
        return JSONResponse(
            status_code=502 if e.status_code >= 500 else 400,
            content={"success": False, "filename": filename, "error": str(e)},
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to retrieve credential quota {filename}: {e}")
        raise internal_server_error() from e


@router.post("/configure-preview/{filename}")
async def configure_preview_channel(
    filename: str, token: str = Depends(verify_panel_token), mode: str = "code_assist"
):
    try:
        mode = validate_mode(mode)

        if mode != "code_assist":
            raise HTTPException(
                status_code=400,
                detail="The Preview channel can only be configured for Code Assist credentials.",
            )

        filename = validate_credential_filename(filename)

        storage_adapter = await get_storage_adapter()

        credential_data = await storage_adapter.get_credential(filename, mode=mode)
        if not credential_data:
            raise HTTPException(status_code=404, detail="Credential does not exist.")

        credentials = Credentials.from_dict(credential_data)
        token_refreshed = await credentials.refresh_if_needed()

        if token_refreshed:
            log.info(f"Token automatically refreshed: {filename}")
            credential_data = merge_refreshed_credential_data(credential_data, credentials)
            await storage_adapter.store_credential(filename, credential_data, mode=mode)

        access_token = credential_data.get("access_token") or credential_data.get("token")
        project_id = credential_data.get("project_id", "")

        if not access_token:
            raise HTTPException(
                status_code=400, detail="Credential does not contain an access token."
            )
        if not project_id:
            raise HTTPException(status_code=400, detail="Credential does not contain a Project ID.")

        import uuid

        from core.httpx_client import get_async, post_async

        setting_id = f"preview-setting-{uuid.uuid4().hex[:8]}"
        binding_id = f"preview-binding-{uuid.uuid4().hex[:8]}"

        base_url = (
            f"https://cloudaicompanion.googleapis.com/v1/projects/{project_id}/locations/global"
        )
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        log.info(f"Starting configuration of preview channel: {filename} (project_id={project_id})")

        setting_url = f"{base_url}/releaseChannelSettings"
        setting_response = await post_async(
            url=setting_url,
            json={"release_channel": "EXPERIMENTAL"},
            headers=headers,
            params={"release_channel_setting_id": setting_id},
            timeout=30.0,
        )

        setting_status = setting_response.status_code

        if setting_status == 200 or setting_status == 201:
            log.info(f"Step 1/2: Release channel setting created (setting_id={setting_id}).")
        elif setting_status == 409:
            log.info(
                "Step 1/2: Release channel setting already exists; retrieving the existing setting ID."
            )
            list_response = await get_async(url=setting_url, headers=headers, timeout=30.0)
            if list_response.status_code == 200:
                try:
                    list_data = list_response.json()
                    settings = list_data.get("releaseChannelSettings", [])
                    if settings:
                        existing_name = settings[0].get("name", "")
                        setting_id = existing_name.split("/")[-1]
                        log.info(f"Step 1/2: Retrieved existing setting_id={setting_id}")
                    else:
                        log.warning(
                            "Step 1/2: the list response was empty; keeping the generated setting ID."
                        )
                except Exception as e:
                    log.warning(
                        f"Step 1/2: failed to parse the list response: {e}. Keeping the generated setting ID."
                    )
            else:
                log.warning(
                    f"Step 1/2: list request failed (status={list_response.status_code}); keeping the generated setting ID."
                )
        else:
            error_text = public_error_detail(
                setting_response.text if hasattr(setting_response, "text") else ""
            )
            log.error(
                f"Step 1/2 failed: {filename} - Status: {setting_status}, Error: {error_text}"
            )

            return JSONResponse(
                status_code=setting_status,
                content={
                    "success": False,
                    "filename": filename,
                    "preview": False,
                    "message": f"Failed to create Release Channel Setting: HTTP {setting_status}",
                    "error": error_text,
                    "step": "create_setting",
                },
            )

        # Step 2: Create Setting Binding (bind to project)
        binding_url = f"{base_url}/releaseChannelSettings/{setting_id}/settingBindings"
        binding_response = await post_async(
            url=binding_url,
            json={"target": f"projects/{project_id}", "product": "GEMINI_CODE_ASSIST"},
            headers=headers,
            params={"setting_binding_id": binding_id},
            timeout=30.0,
        )

        binding_status = binding_response.status_code

        if binding_status == 200 or binding_status == 201:
            await storage_adapter.update_credential_state(filename, {"preview": True}, mode=mode)

            log.info(
                f"Step 2/2: Setting binding created. Preview channel configuration completed for {filename}."
            )

            return JSONResponse(
                content={
                    "success": True,
                    "filename": filename,
                    "preview": True,
                    "message": "Preview channel configured, and Preview mode is now enabled.",
                    "setting_id": setting_id,
                    "binding_id": binding_id,
                }
            )
        elif binding_status == 409:
            # Binding already exists, meaning it was configured already
            await storage_adapter.update_credential_state(filename, {"preview": True}, mode=mode)

            log.info(
                f"Step 2/2: Setting Binding already exists - Preview channel is configured: {filename}"
            )

            return JSONResponse(
                content={
                    "success": True,
                    "filename": filename,
                    "preview": True,
                    "message": "Preview channel configuration already exists, and preview mode is enabled.",
                }
            )
        else:
            # Step 2 failed
            error_text = public_error_detail(
                binding_response.text if hasattr(binding_response, "text") else ""
            )
            log.error(
                f"Step 2/2 failed: {filename} - Status: {binding_status}, Error: {error_text}"
            )

            return JSONResponse(
                status_code=binding_status,
                content={
                    "success": False,
                    "filename": filename,
                    "preview": False,
                    "message": f"Failed to create Setting Binding: HTTP {binding_status}",
                    "error": error_text,
                    "step": "create_binding",
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to configure preview channel {filename}: {e}")
        raise internal_server_error() from e


@router.post("/test/{filename}")
async def test_credential(
    filename: str,
    request: CredentialModelTestRequest,
    mode: str = "code_assist",
    _token: str = Depends(verify_panel_token),
    http_request: Request = None,
):
    """Run one bounded model test and stop provider work after client disconnect."""
    disconnect_check = http_request.is_disconnected if http_request is not None else None
    try:
        return await run_bounded_connection_test(
            _test_credential_unbounded(filename, request, mode=mode),
            is_disconnected=disconnect_check,
            timeout_seconds=CONNECTION_TEST_TIMEOUT_SECONDS,
        )
    except ConnectionTestTimedOut:
        return _credential_test_failure_response(
            connection_diagnostic("timeout"),
            status_code=504,
            filename=filename,
            model=request.model,
        )
    except ConnectionTestDisconnected:
        return _credential_test_failure_response(
            connection_diagnostic("cancelled"),
            status_code=499,
            filename=filename,
            model=request.model,
        )


async def _test_credential_unbounded(
    filename: str,
    request: CredentialModelTestRequest,
    *,
    mode: str,
):
    provider_id = ""
    credential_data: dict = {}
    test_model = request.model
    try:
        mode = validate_mode(mode)

        filename = validate_credential_filename(filename)

        storage_adapter = await get_storage_adapter()

        credential_data = await storage_adapter.get_credential(filename, mode=mode)
        if not credential_data:
            raise HTTPException(status_code=404, detail="Credential does not exist.")

        rejection = reject_unsupported_credential_operation(
            credential_data,
            "test",
            mode=mode,
        )
        if rejection:
            return rejection

        from core.httpx_client import post_async

        provider_id = get_credential_provider(credential_data)
        try:
            test_model = normalize_model_id(request.model)
        except ModelPoolError:
            return _credential_test_failure_response(
                connection_diagnostic("invalid_model"),
                status_code=400,
                filename=filename,
                provider=provider_id,
                credential_type=credential_data.get("credential_type"),
                model=request.model,
            )

        available_models = await _get_available_credential_models(credential_data)
        if not available_models:
            return _credential_test_failure_response(
                connection_diagnostic("invalid_model"),
                status_code=409,
                filename=filename,
                provider=provider_id,
                credential_type=credential_data.get("credential_type"),
                model=test_model,
            )
        if test_model not in available_models:
            return _credential_test_failure_response(
                connection_diagnostic("invalid_model"),
                status_code=400,
                filename=filename,
                provider=provider_id,
                credential_type=credential_data.get("credential_type"),
                model=test_model,
            )

        if mode == "primary" and provider_id in EXTENDED_PROVIDERS:
            response = await test_extended_credential(credential_data, test_model)
            status_code = response.status_code
            if status_code == 200:
                await storage_adapter.update_credential_state(
                    filename, {"error_codes": [], "error_messages": {}}, mode=mode
                )
                return JSONResponse(
                    content={
                        "success": True,
                        "status_code": status_code,
                        "message": "Model test completed successfully.",
                        "filename": filename,
                        "provider": provider_id,
                        "credential_type": credential_data.get("credential_type"),
                        "model": test_model,
                    }
                )
            # Catalog visibility is not inference authorization. Rate limiting is
            # likewise a failed explicit test, never a successful authentication.
            diagnostic = classify_provider_response(status_code)
            await storage_adapter.update_credential_state(
                filename,
                {
                    "error_codes": [status_code],
                    "error_messages": {str(status_code): diagnostic.message},
                },
                mode=mode,
            )
            return _credential_test_failure_response(
                diagnostic,
                status_code=status_code,
                filename=filename,
                provider=provider_id,
                credential_type=credential_data.get("credential_type"),
                model=test_model,
            )

        test_request = {
            "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
            "generationConfig": {"maxOutputTokens": 1},
        }

        if mode == "primary" and provider_id == GOOGLE_AI_STUDIO:
            api_key = str(credential_data.get("api_key") or "").strip()
            headers = build_api_key_headers(api_key)
            request_body = test_request
            request_url = build_generation_url(
                await get_google_ai_studio_api_url(), test_model, streaming=False
            )
            access_token = ""
            project_id = ""
        elif mode == "primary" and provider_id in {XAI, OPENAI, ANTHROPIC, OLLAMA}:
            if provider_id == XAI and not is_api_key_credential(credential_data):
                credential_data = await refresh_xai_oauth_credential(credential_data)
                await storage_adapter.store_credential(filename, credential_data, mode=mode)
            elif (
                provider_id == OPENAI
                and not is_api_key_credential(credential_data)
                and not (credential_data.get("access_token") or credential_data.get("token"))
            ):
                credential_data = await refresh_codex_oauth_credential(credential_data)
                await storage_adapter.store_credential(filename, credential_data, mode=mode)
                log.info(f"Codex token automatically refreshed: {filename}")
            elif provider_id == ANTHROPIC and not is_api_key_credential(credential_data):
                prepared = await credential_manager.prepare_credential(
                    filename, credential_data, mode=mode
                )
                if not prepared:
                    raise AnthropicError("Claude Code credential could not be refreshed.", 401)
                credential_data = prepared
            from core.api.primary import prepare_provider_request

            context = await prepare_provider_request(
                credential_data,
                {"model": test_model, "request": test_request},
                streaming=False,
            )
            headers = context.headers
            request_body = context.payload
            request_url = context.target_url
            access_token = ""
            project_id = ""
        else:
            credentials = Credentials.from_dict(credential_data)
            token_refreshed = await credentials.refresh_if_needed()
            if token_refreshed:
                log.info(f"Token automatically refreshed: {filename} (mode = {mode})")
                credential_data = merge_refreshed_credential_data(credential_data, credentials)
                await storage_adapter.store_credential(filename, credential_data, mode=mode)

            access_token = credential_data.get("access_token") or credential_data.get("token")
            if not access_token:
                raise HTTPException(
                    status_code=400,
                    detail="Credential does not contain an access token.",
                )
            project_id = credential_data.get("project_id", "")
            if not project_id:
                raise HTTPException(
                    status_code=400,
                    detail="Credential does not contain a Project ID.",
                )

        if mode == "primary" and provider_id not in {
            GOOGLE_AI_STUDIO,
            XAI,
            OPENAI,
            ANTHROPIC,
            OLLAMA,
        }:
            api_base_url = await get_antigravity_api_url()
            from core.api.primary import build_primary_headers

            headers = await build_primary_headers(access_token, test_model)
            request_body = {
                "model": test_model,
                "project": project_id,
                "request": test_request,
            }
            request_url = f"{api_base_url}/v1internal:generateContent"
        elif mode != "primary":
            api_base_url = await get_code_assist_endpoint()
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "User-Agent": CODE_ASSIST_USER_AGENT,
            }
            request_body = {
                "model": test_model,
                "project": project_id,
                "request": test_request,
            }
            request_url = f"{api_base_url}/v1internal:generateContent"

        response = await post_async(
            url=request_url, json=request_body, headers=headers, timeout=30.0
        )

        status_code = response.status_code

        if (
            status_code == 401
            and mode == "primary"
            and provider_id == OPENAI
            and not is_api_key_credential(credential_data)
            and credential_data.get("refresh_token")
        ):
            credential_data = await refresh_codex_oauth_credential(credential_data)
            await storage_adapter.store_credential(filename, credential_data, mode=mode)
            log.info(f"Codex token automatically refreshed: {filename}")
            context = await prepare_provider_request(
                credential_data,
                {"model": test_model, "request": test_request},
                streaming=False,
            )
            headers = context.headers
            request_body = context.payload
            request_url = context.target_url
            response = await post_async(
                url=request_url,
                json=request_body,
                headers=headers,
                timeout=30.0,
            )
            status_code = response.status_code

        if (
            status_code == 401
            and mode == "primary"
            and provider_id == ANTHROPIC
            and not is_api_key_credential(credential_data)
            and credential_data.get("refresh_token")
        ):
            credential_data = await refresh_claude_oauth_credential(credential_data)
            await storage_adapter.store_credential(filename, credential_data, mode=mode)
            context = await prepare_provider_request(
                credential_data,
                {"model": test_model, "request": test_request},
                streaming=False,
            )
            response = await post_async(
                url=context.target_url,
                json=context.payload,
                headers=context.headers,
                timeout=30.0,
            )
            status_code = response.status_code

        if status_code == 200 or status_code == 429:
            log.info(
                f"Credential test successful: {filename} (mode={mode}, model={test_model}, status={status_code})"
            )

            if status_code == 200:
                await storage_adapter.update_credential_state(
                    filename, {"error_codes": [], "error_messages": {}}, mode=mode
                )

                if mode == "code_assist":
                    preview_model = "gemini-3-flash-preview"
                    log.info(f"Starting preview model test: {filename} (model={preview_model})")

                    try:
                        preview_response = await post_async(
                            url=f"{api_base_url}/v1internal:generateContent",
                            json={
                                "model": preview_model,
                                "project": project_id,
                                "request": {
                                    "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
                                    "generationConfig": {"maxOutputTokens": 1},
                                },
                            },
                            headers=headers,
                            timeout=30.0,
                        )

                        preview_status = preview_response.status_code

                        if preview_status == 200 or preview_status == 429:
                            log.info(
                                f"Preview model test passed: {filename} (status = {preview_status})."
                            )
                            await storage_adapter.update_credential_state(
                                filename, {"preview": True}, mode=mode
                            )
                        elif preview_status == 404:
                            log.warning(
                                f"Preview model is not supported for {filename} (status = 404)"
                            )
                            await storage_adapter.update_credential_state(
                                filename, {"preview": False}, mode=mode
                            )
                        else:
                            log.warning(
                                f"Preview model test failed: {filename} (status = {preview_status})"
                            )
                    except Exception as e:
                        log.error(f"Preview model test failed for {filename}: {e}")

            diagnostic = (
                classify_provider_response(
                    status_code,
                    response.text if hasattr(response, "text") else None,
                )
                if status_code == 429
                else None
            )
            message = diagnostic.message if diagnostic else "Model test completed successfully."
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "status_code": status_code,
                    "message": message,
                    "filename": filename,
                    "provider": provider_id,
                    "credential_type": credential_data.get("credential_type"),
                    "model": test_model,
                    **({"diagnostic": diagnostic.as_dict()} if diagnostic else {}),
                },
            )
        else:
            log.warning(f"Credential test failed: {filename} (mode={mode}, status={status_code})")
            diagnostic = classify_provider_response(
                status_code,
                response.text if hasattr(response, "text") else None,
            )

            try:
                log.error(
                    "Credential test failed with a normalized provider diagnostic - "
                    f"file: {filename}, mode: {mode}, status code: {status_code}, "
                    f"category: {diagnostic.category}, provider code: "
                    f"{diagnostic.provider_code or 'unavailable'}"
                )

                error_codes = [status_code]
                error_messages = {str(status_code): diagnostic.message}

                await storage_adapter.update_credential_state(
                    filename,
                    {"error_codes": error_codes, "error_messages": error_messages},
                    mode=mode,
                )

                log.info(f"Saved test error info: {filename} - error code {status_code}")
            except Exception as e:
                log.error(f"Failed to save test error message: {e}")

        return _credential_test_failure_response(
            diagnostic,
            status_code=status_code,
            filename=filename,
            provider=provider_id,
            credential_type=credential_data.get("credential_type"),
            model=test_model,
        )

    except HTTPException:
        raise
    except asyncio.CancelledError:
        raise
    except Exception as e:
        diagnostic = classify_provider_exception(e)
        status_code = diagnostic.provider_status or (
            500
            if diagnostic.category == "internal"
            else 504
            if diagnostic.category == "timeout"
            else 502
        )
        log.error(
            "Credential test raised a normalized exception - "
            f"file: {filename}, category: {diagnostic.category}, "
            f"exception: {type(e).__name__}"
        )
        return _credential_test_failure_response(
            diagnostic,
            status_code=status_code,
            filename=filename,
            provider=provider_id,
            credential_type=credential_data.get("credential_type"),
            model=test_model,
        )
