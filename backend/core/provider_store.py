"""Shared provider credential persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from core.credential_manager import credential_manager
from core.provider_registry import (
    ANTHROPIC,
    GOOGLE_AI_STUDIO,
    OLLAMA,
    OPENAI,
    XAI,
    api_key_fingerprint,
    get_static_credential_identity,
)


async def store_extended_credential(credential_data: dict, model_ids: list[str]) -> dict:
    """Store normalized key credentials with account/endpoint-isolated identity."""
    from core.extended_provider_runtime import normalize_extended_credential

    payload = normalize_extended_credential(credential_data)
    payload["model_ids"] = list(model_ids)
    # validation_status="unverified" is immutable file-import provenance in
    # the existing console, not an inference test result. The onboarding
    # response explicitly requires an inference test after catalog discovery.
    payload["created_at"] = datetime.now(timezone.utc).isoformat()
    payload["credential_label"] = str(credential_data.get("credential_label") or "").strip()[:128]
    fingerprint = get_static_credential_identity(payload).split(":", 1)[1]
    payload["key_fingerprint"] = api_key_fingerprint(payload["api_key"])
    filename = f"{payload['provider']}-{fingerprint}.json"
    result = await credential_manager.add_primary_credential(filename, payload)
    return {
        "action": result.get("action", "created"),
        "filename": result.get("filename", filename),
        "label": payload["credential_label"],
        "model_count": len(model_ids),
    }


async def store_google_ai_studio_credential(
    api_key: str,
    validation: Any,
    *,
    created_at: Optional[str] = None,
) -> dict:
    """Store one validated Google AI Studio key without exposing it."""
    normalized_key = str(api_key or "").strip()
    fingerprint = api_key_fingerprint(normalized_key)
    credential_label = f"API key ending {normalized_key[-4:]}"
    credential_data = {
        "provider": GOOGLE_AI_STUDIO,
        "credential_type": "api_key",
        "api_key": normalized_key,
        "credential_label": credential_label,
        "key_fingerprint": fingerprint,
        "model_ids": validation.model_ids,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    filename = f"google-ai-studio-{fingerprint}.json"
    result = await credential_manager.add_primary_credential(filename, credential_data)
    return {
        "action": result.get("action", "created"),
        "filename": result.get("filename", filename),
        "label": credential_label,
        "fingerprint": fingerprint,
    }


async def store_xai_api_key_credential(
    api_key: str,
    validation: Any,
    *,
    created_at: Optional[str] = None,
) -> dict:
    """Store one validated SpaceXAI Console API key without exposing it."""
    normalized_key = str(api_key or "").strip()
    fingerprint = api_key_fingerprint(normalized_key)
    credential_label = f"API key ending {normalized_key[-4:]}"
    credential_data = {
        "provider": XAI,
        "credential_type": "api_key",
        "api_key": normalized_key,
        "credential_label": credential_label,
        "key_fingerprint": fingerprint,
        "model_ids": validation.model_ids,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    filename = f"xai-console-{fingerprint}.json"
    result = await credential_manager.add_primary_credential(filename, credential_data)
    return {
        "action": result.get("action", "created"),
        "filename": result.get("filename", filename),
        "label": credential_label,
        "fingerprint": fingerprint,
    }


async def store_openai_platform_credential(
    api_key: str,
    validation: Any,
    *,
    created_at: Optional[str] = None,
) -> dict:
    """Store one validated OpenAI Platform API key without exposing it."""
    normalized_key = str(api_key or "").strip()
    fingerprint = api_key_fingerprint(normalized_key)
    credential_label = f"API key ending {normalized_key[-4:]}"
    credential_data = {
        "provider": OPENAI,
        "credential_type": "api_key",
        "api_key": normalized_key,
        "credential_label": credential_label,
        "key_fingerprint": fingerprint,
        "model_ids": validation.model_ids,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    filename = f"openai-platform-{fingerprint}.json"
    result = await credential_manager.add_primary_credential(filename, credential_data)
    return {
        "action": result.get("action", "created"),
        "filename": result.get("filename", filename),
        "label": credential_label,
        "fingerprint": fingerprint,
    }


async def store_codex_credential(credential_data: dict) -> dict:
    """Store one completed Codex OAuth credential in the primary pool."""
    payload = dict(credential_data)
    payload["provider"] = OPENAI
    payload["credential_type"] = "oauth"
    fingerprint = str(payload.get("account_fingerprint") or "").strip()
    if not fingerprint:
        fingerprint = api_key_fingerprint(
            str(payload.get("user_email") or payload.get("refresh_token") or "")
        )
    filename = f"openai-codex-{fingerprint or 'unknown'}.json"
    result = await credential_manager.add_primary_credential(filename, payload)
    return {
        "action": result.get("action", "created"),
        "filename": result.get("filename", filename),
        "label": payload.get("credential_label") or "Codex account",
        "fingerprint": fingerprint,
    }


async def store_claude_platform_credential(
    api_key: str,
    validation: Any,
    *,
    created_at: Optional[str] = None,
) -> dict:
    """Store one validated Claude Platform key without exposing it."""
    normalized_key = str(api_key or "").strip()
    fingerprint = api_key_fingerprint(normalized_key)
    credential_label = f"API key ending {normalized_key[-4:]}"
    credential_data = {
        "provider": ANTHROPIC,
        "credential_type": "api_key",
        "api_key": normalized_key,
        "credential_label": credential_label,
        "key_fingerprint": fingerprint,
        "model_ids": validation.model_ids,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    filename = f"claude-platform-{fingerprint}.json"
    result = await credential_manager.add_primary_credential(filename, credential_data)
    return {
        "action": result.get("action", "created"),
        "filename": result.get("filename", filename),
        "label": credential_label,
        "fingerprint": fingerprint,
    }


async def store_ollama_credential(
    base_url: str,
    api_key: str,
    validation: Any,
    *,
    created_at: Optional[str] = None,
) -> dict:
    """Store one validated Ollama connection without exposing its optional key."""
    normalized_url = str(base_url or "").strip().rstrip("/")
    normalized_key = str(api_key or "").strip()
    fingerprint = api_key_fingerprint(f"{normalized_url}\0{normalized_key}")
    credential_label = normalized_url.removeprefix("https://").removeprefix("http://")
    credential_data = {
        "provider": OLLAMA,
        "credential_type": "connection",
        "base_url": normalized_url,
        "api_key": normalized_key,
        "credential_label": credential_label,
        "connection_fingerprint": fingerprint,
        "model_ids": validation.model_ids,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    filename = f"ollama-{fingerprint}.json"
    result = await credential_manager.add_primary_credential(filename, credential_data)
    return {
        "action": result.get("action", "created"),
        "filename": result.get("filename", filename),
        "label": credential_label,
        "fingerprint": fingerprint,
    }
