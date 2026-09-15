"""Secure mixed-provider credential pool archive import."""

from __future__ import annotations

import io
import json
import stat
import zipfile
from pathlib import PurePosixPath
from typing import Any, Dict, List, Tuple

from core.anthropic import (
    AnthropicError,
    fetch_anthropic_model_ids,
    refresh_claude_oauth_credential,
    validate_anthropic_api_key,
)
from core.codex import CODEX_DEFAULT_MODEL_IDS, CodexError
from core.credential_manager import credential_manager
from core.extended_provider_runtime import discover_extended_models
from core.google_ai_studio import GoogleAIStudioError, validate_api_key
from core.ollama import OllamaError, normalize_ollama_base_url, validate_ollama_connection
from core.openai_platform import OpenAIPlatformError, validate_openai_api_key
from core.provider_import_normalization import normalize_provider_import
from core.provider_registry import (
    ANTHROPIC,
    CLAUDE_CODE,
    CLAUDE_PLATFORM,
    CODEX,
    EXTENDED_PROVIDERS,
    GOOGLE_AI_STUDIO,
    GOOGLE_ANTIGRAVITY,
    GROK,
    OLLAMA,
    OPENAI,
    OPENAI_PLATFORM,
    XAI,
    XAI_CONSOLE,
    api_key_fingerprint,
    canonicalize_antigravity_credential_filename,
    get_credential_provider_display_name,
    get_credential_provider_variant,
    get_static_credential_identity,
    normalize_provider_id,
)
from core.provider_store import (
    store_claude_platform_credential,
    store_extended_credential,
    store_google_ai_studio_credential,
    store_ollama_credential,
    store_openai_platform_credential,
    store_xai_api_key_credential,
)
from core.xai import XaiError, validate_xai_api_key
from fastapi import UploadFile
from log import log

MAX_POOL_ARCHIVE_BYTES = 10 * 1024 * 1024
MAX_POOL_ARCHIVE_ENTRIES = 500
MAX_POOL_ENTRY_BYTES = 2 * 1024 * 1024
MAX_POOL_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
SUPPORTED_POOL_PROVIDERS = {
    GOOGLE_ANTIGRAVITY,
    GOOGLE_AI_STUDIO,
    XAI,
    OPENAI,
    ANTHROPIC,
    OLLAMA,
    *EXTENDED_PROVIDERS,
}


class PoolImportError(ValueError):
    """Raised when a pool archive or credential cannot be imported safely."""


def _has_text(payload: Dict[str, Any], key: str) -> bool:
    return bool(str(payload.get(key) or "").strip())


def _is_ai_studio_payload(payload: Dict[str, Any]) -> bool:
    credential_type = str(payload.get("credential_type") or "").strip().lower()
    return _has_text(payload, "api_key") and credential_type in {"", "api_key"}


def _is_antigravity_payload(payload: Dict[str, Any]) -> bool:
    return all(_has_text(payload, key) for key in ("client_id", "client_secret", "refresh_token"))


def _is_xai_payload(payload: Dict[str, Any]) -> bool:
    credential_type = str(payload.get("credential_type") or "").strip().lower()
    if credential_type == "api_key":
        return _has_text(payload, "api_key")
    if credential_type == "oauth":
        return _has_text(payload, "refresh_token") or _has_text(payload, "access_token")
    return False


def _is_openai_payload(payload: Dict[str, Any]) -> bool:
    credential_type = str(payload.get("credential_type") or "").strip().lower()
    if credential_type == "api_key":
        return _has_text(payload, "api_key")
    if credential_type == "oauth":
        return _has_text(payload, "refresh_token") or _has_text(payload, "access_token")
    return False


def _is_anthropic_payload(payload: Dict[str, Any]) -> bool:
    credential_type = str(payload.get("credential_type") or "").strip().lower()
    if credential_type == "api_key":
        return _has_text(payload, "api_key")
    if credential_type == "oauth":
        return _has_text(payload, "refresh_token") or _has_text(payload, "access_token")
    return False


def _is_ollama_payload(payload: Dict[str, Any]) -> bool:
    credential_type = str(payload.get("credential_type") or "").strip().lower()
    return credential_type in {"", "connection"} and _has_text(payload, "base_url")


def classify_pool_credential(payload: Any) -> str:
    """Return a supported provider ID only when the credential shape is clear."""
    if not isinstance(payload, dict):
        raise PoolImportError("Credential payload must be a JSON object.")

    explicit_provider = payload.get("provider") or payload.get("provider_id")
    if explicit_provider:
        provider_id = normalize_provider_id(explicit_provider)
        if provider_id not in SUPPORTED_POOL_PROVIDERS:
            raise PoolImportError(f"Provider '{explicit_provider}' is not supported by this pool.")
        if provider_id == GOOGLE_AI_STUDIO and not _is_ai_studio_payload(payload):
            raise PoolImportError("Google AI Studio payload is not a valid API key credential.")
        if provider_id == GOOGLE_ANTIGRAVITY and not _is_antigravity_payload(payload):
            raise PoolImportError("Google Antigravity payload is missing required OAuth fields.")
        if provider_id == XAI and not _is_xai_payload(payload):
            raise PoolImportError(
                "Credential payload is not a valid Grok Build OAuth or SpaceXAI Console API key credential."
            )
        if provider_id == OPENAI and not _is_openai_payload(payload):
            raise PoolImportError(
                "Credential payload is not a valid Codex OAuth or OpenAI Platform API key credential."
            )
        if provider_id == ANTHROPIC and not _is_anthropic_payload(payload):
            raise PoolImportError(
                "Credential payload is not a valid Claude Code OAuth or Claude Platform API key credential."
            )
        if provider_id == OLLAMA and not _is_ollama_payload(payload):
            raise PoolImportError("Ollama payload is missing a valid connection endpoint.")
        if provider_id in EXTENDED_PROVIDERS:
            try:
                normalize_provider_import(payload)
            except ValueError as exc:
                raise PoolImportError(str(exc)) from None
        return provider_id

    if _is_antigravity_payload(payload):
        return GOOGLE_ANTIGRAVITY
    if _is_ollama_payload(payload):
        return OLLAMA
    api_key = str(payload.get("api_key") or "").strip()
    if api_key.startswith("sk-ant-"):
        return ANTHROPIC
    if _is_ai_studio_payload(payload):
        return GOOGLE_AI_STUDIO
    raise PoolImportError("Credential provider could not be identified safely.")


def _safe_archive_entry_name(value: str) -> Tuple[str, str]:
    normalized = str(value or "").replace("\\", "/")
    path = PurePosixPath(normalized)
    has_drive_prefix = bool(path.parts and ":" in path.parts[0])
    if not normalized or normalized.startswith("/") or has_drive_prefix or ".." in path.parts:
        raise PoolImportError("ZIP entry uses an unsafe path.")
    filename = path.name
    if not filename.lower().endswith(".json"):
        raise PoolImportError("ZIP entry must be a JSON file.")
    return normalized, filename


def _is_symlink(entry: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK((entry.external_attr >> 16) & 0xFFFF)


def _parse_archive_payload(content: bytes, source_name: str) -> Dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PoolImportError(f"{source_name} is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise PoolImportError(f"{source_name} must contain one credential object.")
    try:
        return normalize_provider_import(payload)
    except ValueError as exc:
        raise PoolImportError(f"{source_name}: {exc}") from exc


async def extract_pool_archive(
    upload: UploadFile,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Read a bounded ZIP archive in memory and classify each credential."""
    upload_name = PurePosixPath(
        str(upload.filename or "provider_credentials.zip").replace("\\", "/")
    ).name
    if not upload_name.lower().endswith(".zip"):
        raise PoolImportError("Pool import accepts one ZIP archive.")

    content = await upload.read(MAX_POOL_ARCHIVE_BYTES + 1)
    if len(content) > MAX_POOL_ARCHIVE_BYTES:
        raise PoolImportError("Pool archive exceeds the 10 MB import limit.")

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise PoolImportError("Pool archive is not a valid ZIP file.") from exc

    candidates: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    with archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        if len(entries) > MAX_POOL_ARCHIVE_ENTRIES:
            raise PoolImportError(
                f"Pool archive contains more than {MAX_POOL_ARCHIVE_ENTRIES} files."
            )
        json_entries = [entry for entry in entries if entry.filename.lower().endswith(".json")]
        if not json_entries:
            raise PoolImportError("Pool archive does not contain any JSON credential files.")
        if len(json_entries) > MAX_POOL_ARCHIVE_ENTRIES:
            raise PoolImportError(
                f"Pool archive contains more than {MAX_POOL_ARCHIVE_ENTRIES} JSON files."
            )
        if sum(entry.file_size for entry in json_entries) > MAX_POOL_UNCOMPRESSED_BYTES:
            raise PoolImportError("Pool archive exceeds the 25 MB uncompressed limit.")

        for entry in json_entries:
            source_name = entry.filename.replace("\\", "/")
            try:
                safe_source_name, filename = _safe_archive_entry_name(entry.filename)
                source_name = safe_source_name
                if entry.flag_bits & 0x1:
                    raise PoolImportError("Encrypted ZIP entries are not supported.")
                if _is_symlink(entry):
                    raise PoolImportError("Symbolic-link ZIP entries are not supported.")
                if entry.file_size > MAX_POOL_ENTRY_BYTES:
                    raise PoolImportError("Credential file exceeds the 2 MB entry limit.")

                with archive.open(entry) as entry_stream:
                    entry_content = entry_stream.read(MAX_POOL_ENTRY_BYTES + 1)
                if len(entry_content) > MAX_POOL_ENTRY_BYTES:
                    raise PoolImportError("Credential file exceeds the 2 MB entry limit.")

                payload = _parse_archive_payload(entry_content, source_name)
                provider_id = classify_pool_credential(payload)
                candidates.append(
                    {
                        "source_filename": source_name,
                        "filename": filename,
                        "provider": provider_id,
                        "payload": payload,
                    }
                )
            except (PoolImportError, RuntimeError, zipfile.BadZipFile) as exc:
                errors.append(
                    {
                        "status": "error",
                        "source_filename": source_name,
                        "message": str(exc),
                    }
                )

    return candidates, errors


def _empty_provider_result(
    provider_id: str, *, routing_provider: str | None = None
) -> Dict[str, Any]:
    return {
        "provider": provider_id,
        "provider_name": get_credential_provider_display_name({"provider": provider_id}),
        "routing_provider": routing_provider or provider_id,
        "created": 0,
        "updated": 0,
        "replaced": 0,
        "skipped": 0,
        "failed": 0,
    }


async def _restore_antigravity(candidate: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(candidate["payload"])
    payload["provider"] = GOOGLE_ANTIGRAVITY
    filename = canonicalize_antigravity_credential_filename(candidate["filename"], payload)
    result = await credential_manager.add_primary_credential(filename, payload)
    action = str(result.get("action") or "created")
    stored = bool(result.get("stored", action != "skipped"))
    return {
        "status": "success" if stored else "skipped",
        "action": action,
        "filename": result.get("filename", filename),
        "label": result.get("email") or "Google Antigravity account",
        "message": result.get("message")
        or ("Credential imported into the pool." if stored else "Credential was already current."),
    }


async def _restore_ai_studio(candidate: Dict[str, Any]) -> Dict[str, Any]:
    payload = candidate["payload"]
    api_key = str(payload.get("api_key") or "").strip()
    validation = await validate_api_key(api_key)
    stored = await store_google_ai_studio_credential(
        api_key,
        validation,
        created_at=str(payload.get("created_at") or "").strip() or None,
    )
    action = str(stored.get("action") or "created")
    return {
        "status": "success",
        "action": action,
        "filename": stored.get("filename", candidate["filename"]),
        "label": stored.get("label") or "Google AI Studio API key",
        "model_count": validation.model_count,
        "message": (
            "Existing API key was revalidated and updated."
            if action == "updated"
            else "API key was validated and imported into the pool."
        ),
    }


async def restore_xai_credential(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Store Grok OAuth offline or validate a Console API key without returning secrets."""
    payload = dict(candidate["payload"])
    payload["provider"] = XAI
    if str(payload.get("credential_type") or "").lower() == "api_key":
        api_key = str(payload.get("api_key") or "").strip()
        validation = await validate_xai_api_key(api_key)
        stored = await store_xai_api_key_credential(
            api_key,
            validation,
            created_at=str(payload.get("created_at") or "").strip() or None,
        )
        return {
            "status": "success",
            "action": stored.get("action", "created"),
            "filename": stored["filename"],
            "label": stored.get("label") or "SpaceXAI Console API key",
            "model_count": validation.model_count,
            "message": "SpaceXAI Console API key validated and imported into the pool.",
        }

    payload["validation_status"] = "unverified"
    identity = str(
        payload.get("account_fingerprint")
        or payload.get("user_email")
        or payload.get("refresh_token")
        or payload.get("access_token")
        or payload.get("credential_label")
        or ""
    ).strip()
    fingerprint = api_key_fingerprint(identity)
    filename = f"grok-{fingerprint or 'unknown'}.json"
    result = await credential_manager.add_primary_credential(filename, payload)
    action = str(result.get("action") or "created")
    return {
        "status": "success" if result.get("stored", True) else "skipped",
        "action": action,
        "filename": result.get("filename", filename),
        "label": payload.get("credential_label")
        or payload.get("user_email")
        or "Grok Build OAuth account",
        "validation_status": "unverified",
        "message": (
            "Grok Build OAuth credential stored; provider access is not verified. Verify it in the pool before use."
            if result.get("stored", True)
            else "Grok Build OAuth credential was not added; provider access was not verified."
        ),
    }


async def restore_openai_credential(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Store Codex OAuth offline or validate an OpenAI Platform API key."""
    payload = dict(candidate["payload"])
    payload["provider"] = OPENAI
    credential_type = str(payload.get("credential_type") or "").strip().lower()
    if credential_type == "api_key":
        api_key = str(payload.get("api_key") or "").strip()
        validation = await validate_openai_api_key(api_key)
        stored = await store_openai_platform_credential(
            api_key,
            validation,
            created_at=str(payload.get("created_at") or "").strip() or None,
        )
        return {
            "status": "success",
            "action": stored.get("action", "created"),
            "filename": stored["filename"],
            "label": stored.get("label") or "OpenAI Platform API key",
            "model_count": validation.model_count,
            "message": "OpenAI Platform API key validated and imported into the pool.",
        }

    if credential_type != "oauth" or not (
        str(payload.get("refresh_token") or "").strip()
        or str(payload.get("access_token") or "").strip()
    ):
        raise CodexError("Codex credential is missing its OAuth token.")
    if not payload.get("model_ids"):
        payload["model_ids"] = list(CODEX_DEFAULT_MODEL_IDS)
    payload["validation_status"] = "unverified"
    identity = str(
        payload.get("account_fingerprint")
        or payload.get("user_email")
        or payload.get("account_id")
        or payload.get("refresh_token")
        or payload.get("access_token")
        or ""
    ).strip()
    fingerprint = api_key_fingerprint(identity)
    filename = f"openai-codex-{fingerprint or 'unknown'}.json"
    result = await credential_manager.add_primary_credential(filename, payload)
    return {
        "status": "success" if result.get("stored", True) else "skipped",
        "action": result.get("action", "created"),
        "filename": result.get("filename", filename),
        "label": payload.get("credential_label") or payload.get("user_email") or "Codex account",
        "validation_status": "unverified",
        "message": (
            "Codex OAuth credential stored; provider access is not verified. Verify it in the pool before use."
            if result.get("stored", True)
            else "Codex OAuth credential was not added; provider access was not verified."
        ),
    }


async def restore_anthropic_credential(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and import one Claude Code or Claude Platform credential."""
    payload = dict(candidate["payload"])
    payload["provider"] = ANTHROPIC
    credential_type = str(payload.get("credential_type") or "").strip().lower()
    if credential_type == "api_key":
        api_key = str(payload.get("api_key") or "").strip()
        validation = await validate_anthropic_api_key(api_key)
        stored = await store_claude_platform_credential(
            api_key,
            validation,
            created_at=str(payload.get("created_at") or "").strip() or None,
        )
        return {
            "status": "success",
            "action": stored.get("action", "created"),
            "filename": stored["filename"],
            "label": stored.get("label") or "Claude Platform API key",
            "model_count": validation.model_count,
            "message": "Claude Platform API key validated and imported into the pool.",
        }

    if credential_type != "oauth" or not (
        str(payload.get("refresh_token") or "").strip()
        or str(payload.get("access_token") or "").strip()
    ):
        raise AnthropicError("Claude Code credential is missing its OAuth token.")
    if payload.get("refresh_token"):
        payload = await refresh_claude_oauth_credential(payload)
    model_ids = await fetch_anthropic_model_ids(payload)
    payload["model_ids"] = model_ids
    identity = str(
        payload.get("account_fingerprint")
        or payload.get("user_email")
        or payload.get("refresh_token")
        or payload.get("access_token")
        or ""
    ).strip()
    fingerprint = api_key_fingerprint(identity)
    filename = f"claude-code-{fingerprint or 'unknown'}.json"
    result = await credential_manager.add_primary_credential(filename, payload)
    return {
        "status": "success" if result.get("stored", True) else "skipped",
        "action": result.get("action", "created"),
        "filename": result.get("filename", filename),
        "label": payload.get("credential_label")
        or payload.get("user_email")
        or "Claude Code account",
        "model_count": len(model_ids),
        "message": result.get("message") or "Claude Code credential imported into the pool.",
    }


async def restore_ollama_credential(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and import one local, remote, or cloud Ollama connection."""
    payload = dict(candidate["payload"])
    base_url = normalize_ollama_base_url(str(payload.get("base_url") or ""))
    api_key = str(payload.get("api_key") or "").strip()
    validation = await validate_ollama_connection(base_url, api_key)
    stored = await store_ollama_credential(
        base_url,
        api_key,
        validation,
        created_at=str(payload.get("created_at") or "").strip() or None,
    )
    return {
        "status": "success",
        "action": stored.get("action", "created"),
        "filename": stored["filename"],
        "label": stored.get("label") or "Ollama connection",
        "model_count": validation.model_count,
        "message": "Ollama connection validated and imported into the pool.",
    }


async def restore_extended_credential(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Refresh the model catalog and store a bounded, explicitly typed API key.

    Even authenticated catalogs do not establish permission to run inference.
    Never trust validation state or cached model IDs from an imported archive.
    """
    payload = normalize_provider_import(candidate["payload"])
    try:
        model_ids = await discover_extended_models(payload)
    except Exception:
        raise PoolImportError(
            "Provider model discovery failed. Check the credential and connection settings."
        ) from None
    try:
        stored = await store_extended_credential(payload, model_ids)
    except Exception:
        raise PoolImportError("Provider credential could not be stored.") from None
    return {
        "status": "skipped" if stored.get("action") == "skipped" else "success",
        "action": stored.get("action", "created"),
        "filename": stored["filename"],
        "label": stored.get("label") or EXTENDED_PROVIDERS[payload["provider"]],
        "model_count": len(model_ids),
        "validation_status": "unverified",
        "message": "Credential imported and model catalog loaded. Inference access is not verified.",
    }


async def restore_pool_archive(upload: UploadFile) -> Dict[str, Any]:
    """Import supported credentials and return a secret-free per-file report."""
    candidates, results = await extract_pool_archive(upload)
    providers = {
        GOOGLE_ANTIGRAVITY: _empty_provider_result(GOOGLE_ANTIGRAVITY),
        GOOGLE_AI_STUDIO: _empty_provider_result(GOOGLE_AI_STUDIO),
        GROK: _empty_provider_result(GROK, routing_provider=XAI),
        XAI_CONSOLE: _empty_provider_result(XAI_CONSOLE, routing_provider=XAI),
        CODEX: _empty_provider_result(CODEX, routing_provider=OPENAI),
        OPENAI_PLATFORM: _empty_provider_result(OPENAI_PLATFORM, routing_provider=OPENAI),
        CLAUDE_CODE: _empty_provider_result(CLAUDE_CODE, routing_provider=ANTHROPIC),
        CLAUDE_PLATFORM: _empty_provider_result(CLAUDE_PLATFORM, routing_provider=ANTHROPIC),
        OLLAMA: _empty_provider_result(OLLAMA),
        **{provider: _empty_provider_result(provider) for provider in EXTENDED_PROVIDERS},
    }
    seen_api_key_fingerprints: Dict[str, set[str]] = {
        GOOGLE_AI_STUDIO: set(),
        XAI: set(),
        OPENAI: set(),
        ANTHROPIC: set(),
        OLLAMA: set(),
        **{provider: set() for provider in EXTENDED_PROVIDERS},
    }

    for candidate in candidates:
        provider_id = candidate["provider"]
        report_provider_id = get_credential_provider_variant(candidate["payload"])
        provider_result = providers[report_provider_id]
        is_api_key = (
            provider_id == GOOGLE_AI_STUDIO
            or (
                provider_id == XAI
                and str(candidate["payload"].get("credential_type") or "").lower() == "api_key"
            )
            or (
                provider_id == OPENAI
                and str(candidate["payload"].get("credential_type") or "").lower() == "api_key"
            )
            or (
                provider_id == ANTHROPIC
                and str(candidate["payload"].get("credential_type") or "").lower() == "api_key"
            )
            or provider_id == OLLAMA
            or provider_id in EXTENDED_PROVIDERS
        )
        if is_api_key:
            fingerprint_source = str(candidate["payload"].get("api_key") or "").strip()
            if provider_id == OLLAMA:
                fingerprint_source = (
                    f"{str(candidate['payload'].get('base_url') or '').strip().rstrip('/')}"
                    f"\0{fingerprint_source}"
                )
            fingerprint = api_key_fingerprint(fingerprint_source)
            if provider_id in EXTENDED_PROVIDERS:
                fingerprint = get_static_credential_identity(candidate["payload"])
            provider_fingerprints = seen_api_key_fingerprints[provider_id]
            if fingerprint in provider_fingerprints:
                provider_result["skipped"] += 1
                results.append(
                    {
                        "status": "skipped",
                        "action": "skipped",
                        "source_filename": candidate["source_filename"],
                        "provider": report_provider_id,
                        "routing_provider": provider_id,
                        "provider_name": provider_result["provider_name"],
                        "message": "Duplicate API key in this archive was skipped.",
                    }
                )
                continue
            provider_fingerprints.add(fingerprint)
        try:
            if provider_id == GOOGLE_AI_STUDIO:
                restored = await _restore_ai_studio(candidate)
            elif provider_id == XAI:
                restored = await restore_xai_credential(candidate)
            elif provider_id == OPENAI:
                restored = await restore_openai_credential(candidate)
            elif provider_id == ANTHROPIC:
                restored = await restore_anthropic_credential(candidate)
            elif provider_id == OLLAMA:
                restored = await restore_ollama_credential(candidate)
            elif provider_id in EXTENDED_PROVIDERS:
                restored = await restore_extended_credential(candidate)
            else:
                restored = await _restore_antigravity(candidate)
            action = restored["action"]
            counter = action if action in {"created", "updated", "replaced"} else "skipped"
            provider_result[counter] += 1
            results.append(
                {
                    **restored,
                    "source_filename": candidate["source_filename"],
                    "provider": report_provider_id,
                    "routing_provider": provider_id,
                    "provider_name": provider_result["provider_name"],
                }
            )
        except (
            AnthropicError,
            CodexError,
            GoogleAIStudioError,
            OllamaError,
            OpenAIPlatformError,
            PoolImportError,
            XaiError,
        ) as exc:
            provider_result["failed"] += 1
            results.append(
                {
                    "status": "error",
                    "source_filename": candidate["source_filename"],
                    "provider": report_provider_id,
                    "routing_provider": provider_id,
                    "provider_name": provider_result["provider_name"],
                    "message": str(exc),
                }
            )
        except Exception as exc:
            provider_result["failed"] += 1
            log.error(
                "Failed to import pool credential %s for provider %s: %s",
                candidate["source_filename"],
                provider_id,
                exc,
            )
            results.append(
                {
                    "status": "error",
                    "source_filename": candidate["source_filename"],
                    "provider": report_provider_id,
                    "routing_provider": provider_id,
                    "provider_name": provider_result["provider_name"],
                    "message": "Credential could not be imported.",
                }
            )

    extraction_errors = [item for item in results if not item.get("provider")]
    uploaded_count = sum(
        provider[action]
        for provider in providers.values()
        for action in ("created", "updated", "replaced")
    )
    skipped_count = sum(provider["skipped"] for provider in providers.values())
    error_count = sum(provider["failed"] for provider in providers.values()) + len(
        extraction_errors
    )
    total_count = len(candidates) + len(extraction_errors)
    credential_label = "credential file" if total_count == 1 else "credential files"
    message = (
        f"Pool import completed: imported {uploaded_count}, skipped {skipped_count}, "
        f"and failed {error_count} across {total_count} {credential_label}."
    )
    return {
        "success": error_count == 0,
        "completed": True,
        "total_count": total_count,
        "uploaded_count": uploaded_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "providers": providers,
        "results": results,
        "message": message,
    }
