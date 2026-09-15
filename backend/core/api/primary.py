import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from config import (
    get_antigravity_api_url,
    get_antigravity_payload_user_agent,
    get_antigravity_stream_to_nonstream,
    get_antigravity_switch_credential_enabled,
    get_auto_disable_error_codes,
    get_codex_api_url,
    get_codex_user_agent,
    get_google_ai_studio_api_url,
    get_openai_api_url,
    get_token_compression_config,
    get_upstream_timeout_seconds,
    get_xai_api_url,
    get_xai_oauth_api_url,
    get_xai_user_agent,
)
from core.anthropic import (
    anthropic_response_to_gemini,
    anthropic_stream_line_to_gemini,
    build_anthropic_headers,
    fetch_anthropic_model_ids,
    gemini_request_to_anthropic,
    get_anthropic_connection,
)
from core.antigravity import (
    build_antigravity_headers,
    fetch_antigravity_model_ids,
)
from core.api.utils import (
    RETRYABLE_UPSTREAM_STATUS_CODES,
    collect_streaming_response,
    get_retry_config,
    handle_error_with_retry,
    parse_and_log_cooldown,
    record_api_call_error,
    record_api_call_success,
    record_model_route_miss,
    record_response_cache_hit,
    record_unassigned_api_call_error,
)
from core.codex import (
    build_codex_headers,
    codex_response_to_gemini,
    codex_stream_line_to_gemini,
    fetch_codex_model_ids,
    gemini_request_to_codex,
)
from core.coordination import CoordinationUnavailableError
from core.credential_manager import credential_manager
from core.gateway_pipeline import (
    apply_pre_call_guardrails,
    lookup_response_cache,
    runtime_admission_response,
    store_response_cache,
)
from core.google_ai_studio import (
    build_api_key_headers,
    build_generation_url,
    build_models_url,
    parse_model_ids,
)
from core.httpx_client import get_async, post_async, stream_post_async
from core.model_blacklist import record_model_not_found
from core.ollama import (
    build_ollama_headers,
    fetch_ollama_model_ids,
    gemini_request_to_ollama,
    normalize_ollama_base_url,
    ollama_response_to_gemini,
    ollama_stream_line_to_gemini,
)
from core.openai_platform import (
    build_openai_headers,
    fetch_openai_model_ids,
    gemini_request_to_openai,
    openai_response_to_gemini,
    openai_stream_line_to_gemini,
)
from core.primary_session_coordination import (
    PrimarySessionState,
    get_primary_session_coordinator,
)
from core.provider_registry import (
    ANTHROPIC,
    CLAUDE_CODE,
    CLAUDE_PLATFORM,
    CODEX,
    GOOGLE_AI_STUDIO,
    GOOGLE_ANTIGRAVITY,
    GROK,
    OLLAMA,
    OPENAI,
    OPENAI_PLATFORM,
    XAI,
    XAI_CONSOLE,
    get_credential_provider,
    get_credential_provider_variant,
    get_provider_routing_id,
)
from core.request_trace_service import trace_decision
from core.storage_adapter import get_storage_adapter
from core.token_compression import (
    CompressionResult,
    CompressionSettings,
    compress_gemini_request,
    compression_trace_reason,
)
from core.usage_stats import (
    extract_token_usage_from_response,
    extract_token_usage_from_stream_chunk,
    merge_token_usage,
)
from core.xai import (
    build_xai_headers,
    fetch_xai_model_ids,
    fetch_xai_oauth_model_ids,
    gemini_request_to_xai,
    xai_response_to_gemini,
    xai_stream_line_to_gemini,
)
from fastapi import Response
from log import log

MAX_MODEL_ROUTE_ATTEMPTS = 128
MAX_MODEL_DISCOVERY_CONCURRENCY = 8
MAX_MODEL_DISCOVERY_COHORTS = 32
MAX_MODEL_DISCOVERY_FAILOVER_ATTEMPTS = 3
MODEL_DISCOVERY_ROTATION_SECONDS = 5 * 60


@dataclass(frozen=True)
class CredentialModelDiscovery:
    model_ids: frozenset[str]
    refreshed: bool


@dataclass(frozen=True)
class ProviderRequestContext:
    provider_id: str
    target_url: str
    headers: Dict[str, str]
    payload: Dict[str, Any]
    request_metrics: Dict[str, Any]


def _extract_first_user_text(request_payload: Dict[str, Any]) -> str:
    contents = request_payload.get("contents", [])
    if not isinstance(contents, list):
        return ""
    for content in contents:
        if not isinstance(content, dict) or content.get("role") != "user":
            continue
        parts = content.get("parts", [])
        if not isinstance(parts, list):
            continue
        for part in parts:
            if isinstance(part, dict) and part.get("text"):
                return str(part["text"])
    return ""


def _session_key(request_payload: Dict[str, Any], model: str = "") -> str:
    session_id = request_payload.get("sessionId")
    if session_id:
        return f"session:{session_id}"
    model_prefix = f"model:{model}:" if model else ""
    first_user_text = _extract_first_user_text(request_payload)
    if first_user_text:
        digest = hashlib.sha256(first_user_text.encode("utf-8")).hexdigest()[:32]
        return f"{model_prefix}text:{digest}"
    return f"{model_prefix}default"


async def _get_session_state(
    request_payload: Dict[str, Any], model: str = ""
) -> PrimarySessionState:
    key = _session_key(request_payload, model)
    first_user_text = _extract_first_user_text(request_payload)
    return await get_primary_session_coordinator().next_state(key, first_user_text)


def _generate_request_id(conversation_id: str, trajectory_id: str, step: int) -> str:
    unix_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return f"agent/{conversation_id}/{unix_ms}/{trajectory_id}/{step}"


def _build_labels(model: str, trajectory_id: str, step: int) -> Dict[str, str]:
    used_claude = "claude" in model.lower()
    return {
        "last_step_index": str(step),
        "model_enum": model,
        "trajectory_id": trajectory_id,
        "used_claude": str(used_claude).lower(),
        "used_claude_conservative": str(used_claude).lower(),
    }


def _apply_credit_mode(payload: Dict[str, Any], enabled: bool) -> None:
    if enabled:
        payload["enabledCreditTypes"] = ["GOOGLE_ONE_AI"]
    else:
        payload.pop("enabledCreditTypes", None)


async def wrap_cli_request(
    gemini_request: Dict[str, Any],
    model: str,
    project_id: str,
    enable_credit: bool = False,
    compression_result: CompressionResult | None = None,
) -> Tuple[Dict[str, Any], str, CompressionResult]:
    original_inner = dict(gemini_request)
    state = await _get_session_state(original_inner, model)
    if compression_result is None:
        compression_result = compress_gemini_request(
            original_inner,
            CompressionSettings(**await get_token_compression_config()),
        )
    inner = dict(compression_result.request)

    if compression_result.applied:
        log.info(
            f"Compressed request history for model={model}: "
            f"removed_contents={compression_result.removed_contents}, "
            f"estimated_tokens={compression_result.original_estimated_tokens}"
            f"->{compression_result.final_estimated_tokens}, "
            f"reason={compression_result.reason}."
        )

    inner.pop("safetySettings", None)

    if not inner.get("sessionId"):
        inner["sessionId"] = state.session_id

    inner["labels"] = _build_labels(model, state.trajectory_id, state.step_index)

    tool_config = inner.get("toolConfig") or {}
    func_config = tool_config.get("functionCallingConfig") or {}
    if "mode" not in func_config:
        func_config["mode"] = "VALIDATED"
    tool_config["functionCallingConfig"] = func_config
    inner["toolConfig"] = tool_config

    request_id = _generate_request_id(state.conversation_id, state.trajectory_id, state.step_index)

    payload = {
        "project": project_id,
        "requestId": request_id,
        "request": inner,
        "model": model,
        "userAgent": await get_antigravity_payload_user_agent(),
        "requestType": "agent",
    }
    _apply_credit_mode(payload, enable_credit)
    return payload, request_id, compression_result


async def build_primary_headers(access_token: str, model: str = "") -> Dict[str, str]:
    return await build_antigravity_headers(access_token)


async def prepare_provider_request(
    credential_data: Dict[str, Any],
    body: Dict[str, Any],
    *,
    streaming: bool,
    extra_headers: Optional[Dict[str, str]] = None,
) -> ProviderRequestContext:
    """Build the provider-specific URL, authentication, and request payload."""
    provider_id = get_credential_provider(credential_data)
    model_name = str(body.get("model") or "").strip()
    inner_request = body.get("request", body)
    compression_result = compress_gemini_request(
        dict(inner_request),
        CompressionSettings(**await get_token_compression_config()),
    )
    compressed_request = dict(compression_result.request)

    if provider_id == GOOGLE_AI_STUDIO:
        api_key = str(credential_data.get("api_key") or "").strip()
        payload = dict(compressed_request)
        for internal_key in ("model", "sessionId", "labels", "enabledCreditTypes"):
            payload.pop(internal_key, None)
        target_url = build_generation_url(
            await get_google_ai_studio_api_url(), model_name, streaming
        )
        auth_headers = build_api_key_headers(api_key)
    elif provider_id == XAI:
        access_token = (
            credential_data.get("api_key")
            or credential_data.get("access_token")
            or credential_data.get("token")
        )
        if not access_token:
            raise ValueError("Provider credential does not contain an access token or API key.")
        payload = gemini_request_to_xai(dict(compressed_request), model_name, streaming)
        is_oauth = (
            get_credential_provider_variant(credential_data) == GROK
            or str(credential_data.get("credential_type") or "").strip().lower() == "oauth"
        )
        base_url = await get_xai_oauth_api_url() if is_oauth else await get_xai_api_url()
        target_url = f"{base_url.rstrip('/')}/chat/completions"
        auth_headers = build_xai_headers(
            str(access_token),
            await get_xai_user_agent(),
            oauth=is_oauth,
        )
        if is_oauth and model_name:
            auth_headers["x-grok-model-override"] = model_name
    elif provider_id == OPENAI:
        credential_variant = get_credential_provider_variant(credential_data)
        access_token = (
            credential_data.get("api_key")
            if credential_variant == OPENAI_PLATFORM
            else credential_data.get("access_token") or credential_data.get("token")
        )
        if not access_token:
            raise ValueError("OpenAI credential does not contain an API key or access token.")
        if credential_variant == OPENAI_PLATFORM:
            payload = gemini_request_to_openai(dict(compressed_request), model_name, streaming)
            target_url = f"{(await get_openai_api_url()).rstrip('/')}/chat/completions"
            auth_headers = build_openai_headers(str(access_token))
        else:
            payload = gemini_request_to_codex(dict(compressed_request), model_name, streaming)
            target_url = f"{(await get_codex_api_url()).rstrip('/')}/responses"
            auth_headers = build_codex_headers(
                str(access_token),
                str(credential_data.get("account_id") or ""),
                session_id=str(
                    inner_request.get("sessionId") or _session_key(inner_request, model_name)
                ),
                user_agent=await get_codex_user_agent(),
            )
    elif provider_id == ANTHROPIC:
        payload = gemini_request_to_anthropic(dict(compressed_request), model_name, streaming)
        anthropic_base_url, anthropic_user_agent = await get_anthropic_connection(credential_data)
        target_url = f"{anthropic_base_url}/messages"
        auth_headers = build_anthropic_headers(
            credential_data,
            user_agent=anthropic_user_agent,
        )
    elif provider_id == OLLAMA:
        payload = gemini_request_to_ollama(dict(compressed_request), model_name, streaming)
        base_url = normalize_ollama_base_url(str(credential_data.get("base_url") or ""))
        target_url = f"{base_url}/api/chat"
        auth_headers = build_ollama_headers(str(credential_data.get("api_key") or ""))
    else:
        access_token = credential_data.get("access_token") or credential_data.get("token")
        if not access_token:
            raise ValueError("Credential does not contain an access token.")
        project_id = str(credential_data.get("project_id") or "").strip()
        if not project_id:
            raise ValueError("Credential does not contain a Project ID.")
        primary_url = await get_antigravity_api_url()
        operation = (
            "v1internal:streamGenerateContent?alt=sse"
            if streaming
            else "v1internal:generateContent"
        )
        target_url = f"{primary_url.rstrip('/')}/{operation}"
        auth_headers = await build_primary_headers(str(access_token))
        payload, _, compression_result = await wrap_cli_request(
            compressed_request,
            model_name,
            project_id,
            enable_credit=bool(credential_data.get("enable_credit", False)),
            compression_result=compression_result,
        )

    if extra_headers:
        auth_headers.update(extra_headers)
        if provider_id == GOOGLE_AI_STUDIO:
            auth_headers.pop("Authorization", None)
            auth_headers["x-goog-api-key"] = str(credential_data.get("api_key") or "")
        elif provider_id == XAI:
            auth_headers.pop("x-goog-api-key", None)
            access_token = (
                credential_data.get("api_key")
                or credential_data.get("access_token")
                or credential_data.get("token")
            )
            auth_headers["Authorization"] = f"Bearer {access_token}"
        elif provider_id == OPENAI:
            auth_headers.pop("x-goog-api-key", None)
            credential_variant = get_credential_provider_variant(credential_data)
            access_token = (
                credential_data.get("api_key")
                if credential_variant == OPENAI_PLATFORM
                else credential_data.get("access_token") or credential_data.get("token")
            )
            auth_headers["Authorization"] = f"Bearer {access_token}"
            if credential_variant == CODEX:
                account_id = str(credential_data.get("account_id") or "").strip()
                if account_id:
                    auth_headers["ChatGPT-Account-Id"] = account_id
        elif provider_id == ANTHROPIC:
            for header in ("Authorization", "x-api-key", "anthropic-version", "anthropic-beta"):
                auth_headers.pop(header, None)
            auth_headers.update(
                build_anthropic_headers(
                    credential_data,
                    user_agent=anthropic_user_agent,
                )
            )
        elif provider_id == OLLAMA:
            auth_headers.pop("x-goog-api-key", None)
            auth_headers.pop("Authorization", None)
            auth_headers.update(build_ollama_headers(str(credential_data.get("api_key") or "")))
        else:
            auth_headers.pop("x-goog-api-key", None)
            access_token = credential_data.get("access_token") or credential_data.get("token")
            auth_headers["Authorization"] = f"Bearer {access_token}"

    trace_decision(
        category="compression",
        action="applied" if compression_result.applied else "skipped",
        result="succeeded" if compression_result.applied else "skipped",
        reason=compression_trace_reason(compression_result),
        provider=provider_id,
        model=model_name,
        original_tokens=compression_result.original_estimated_tokens,
        final_tokens=compression_result.final_estimated_tokens,
    )
    trace_decision(
        category="upstream",
        action="attempted",
        result="succeeded",
        reason="healthy_candidate",
        provider=provider_id,
        model=model_name,
    )

    return ProviderRequestContext(
        provider_id=provider_id,
        target_url=target_url,
        headers=auth_headers,
        payload=payload,
        request_metrics=compression_result.as_metrics(),
    )


def _is_retryable_status(status_code: int, disable_error_codes: List[int]) -> bool:
    return status_code in RETRYABLE_UPSTREAM_STATUS_CODES or status_code in disable_error_codes


def _stream_event_is_terminal(chunk: Any) -> bool:
    """Return whether a canonical Gemini SSE chunk closes model generation."""
    if not isinstance(chunk, (str, bytes)):
        return False
    text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
    payload_text = text.strip()
    if payload_text.startswith("data:"):
        payload_text = payload_text[5:].strip()
    if payload_text == "[DONE]":
        return True
    try:
        payload = json.loads(payload_text)
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if isinstance(payload.get("response"), dict):
        payload = payload["response"]
    prompt_feedback = payload.get("promptFeedback")
    if isinstance(prompt_feedback, dict) and prompt_feedback.get("blockReason"):
        return True
    candidates = payload.get("candidates")
    return isinstance(candidates, list) and any(
        isinstance(candidate, dict) and bool(candidate.get("finishReason"))
        for candidate in candidates
    )


def _stream_event_is_heartbeat(chunk: Any) -> bool:
    if not isinstance(chunk, (str, bytes)):
        return False
    text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
    return text.lstrip().startswith(":")


def _normalize_sse_frame(chunk: Any) -> Any:
    if not isinstance(chunk, (str, bytes)):
        return chunk
    marker = chunk.lstrip()
    prefixes = (b"data:", b":") if isinstance(chunk, bytes) else ("data:", ":")
    if not marker.startswith(prefixes):
        return chunk
    newline = b"\n\n" if isinstance(chunk, bytes) else "\n\n"
    return chunk.rstrip() + newline


def _normalize_model_candidates(
    body: Dict[str, Any],
    model_candidates: Optional[List[str]],
) -> List[str]:
    values = model_candidates or [str(body.get("model") or "")]
    candidates: List[str] = []
    seen = set()
    for value in values:
        model_name = str(value or "").strip()
        if model_name and model_name not in seen:
            seen.add(model_name)
            candidates.append(model_name)
    return candidates


def _no_credential_error_message(model_name: str) -> str:
    normalized_model = str(model_name or "").strip()
    if normalized_model:
        return (
            f"No route is currently available for model '{normalized_model}'. "
            "Check enabled credentials, model support, cooldowns, and routing settings."
        )
    return (
        "No credential route is currently available. Check credential health and routing settings."
    )


async def _coordination_unavailable_response(
    *, log_prefix: str, model_name: str, error: CoordinationUnavailableError
) -> Response:
    log.error(
        f"{log_prefix} Credential routing coordination is unavailable "
        f"(error_type={type(error).__name__})."
    )
    await record_unassigned_api_call_error(
        status_code=503,
        mode="primary",
        model_name=model_name,
        reason="coordination_unavailable",
    )
    return Response(
        content=json.dumps({"error": "Credential routing is temporarily unavailable."}),
        status_code=503,
        media_type="application/json",
    )


async def _switch_credential_for_retry(
    *,
    refresh_credential_fast,
    log_prefix: str,
) -> bool:
    """Acquire a new credential after the current attempt has been recorded."""
    if await refresh_credential_fast():
        return True

    log.warning(f"{log_prefix} No alternate credential is currently available.")
    return False


async def _exclude_missing_model_route(
    *,
    credential_route_exclusions: set[tuple[str, str]],
    credential_name: str,
    provider_id: str,
    model_name: str,
) -> None:
    """Exclude one failed credential-model route and persist it when possible."""
    credential_route_exclusions.add((credential_name, model_name))
    try:
        await record_model_not_found(
            provider_id,
            model_name,
            credential_name=credential_name,
        )
    except Exception as exc:
        log.error(
            "Model route blacklist persistence failed "
            f"(provider={provider_id}, credential={credential_name}, model={model_name}): {exc}"
        )


async def stream_request(
    body: Dict[str, Any],
    native: bool = False,
    headers: Optional[Dict[str, str]] = None,
    model_candidates: Optional[List[str]] = None,
    model_routing: bool = False,
):
    """Public streaming entry point: guardrails first, then upstream dispatch."""
    admission_response = runtime_admission_response()
    if admission_response is not None:
        yield admission_response
        return
    guard_response, body = await apply_pre_call_guardrails(body)
    if guard_response is not None:
        yield guard_response
        return

    upstream = _stream_request_upstream(
        body,
        native=native,
        headers=headers,
        model_candidates=model_candidates,
        model_routing=model_routing,
    )
    try:
        async for item in upstream:
            yield item
    finally:
        await upstream.aclose()


async def _stream_request_upstream(
    body: Dict[str, Any],
    native: bool = False,
    headers: Optional[Dict[str, str]] = None,
    model_candidates: Optional[List[str]] = None,
    model_routing: bool = False,
):
    request_started_at = time.perf_counter()
    requested_model = str(body.get("model") or "")
    candidates = _normalize_model_candidates(body, model_candidates)
    route_exclusions: set[tuple[str, str]] = set()
    credential_route_exclusions: set[tuple[str, str]] = set()

    try:
        route_result = await credential_manager.get_valid_model_credential(
            candidates,
            mode="primary",
            respect_model_blacklist=model_routing,
            excluded_provider_models=route_exclusions,
            excluded_credential_models=credential_route_exclusions,
        )
    except CoordinationUnavailableError as exc:
        yield await _coordination_unavailable_response(
            log_prefix="[provider stream]",
            model_name=requested_model,
            error=exc,
        )
        return

    if not route_result:
        log.error("[provider stream] No credentials currently available")
        await record_unassigned_api_call_error(
            status_code=503, mode="primary", model_name=requested_model
        )
        yield Response(
            content=json.dumps({"error": _no_credential_error_message(requested_model)}),
            status_code=503,
            media_type="application/json",
        )
        return

    model_name, current_file, credential_data = route_result
    request_body = {**body, "model": model_name}
    try:
        context = await prepare_provider_request(
            credential_data,
            request_body,
            streaming=True,
            extra_headers=headers,
        )
    except ValueError as exc:
        provider_id = get_credential_provider(credential_data)
        await record_api_call_error(
            credential_manager,
            current_file,
            500,
            None,
            mode="primary",
            model_name=model_name,
            error_message=str(exc),
            provider=provider_id,
        )
        yield Response(
            content=json.dumps({"error": str(exc)}),
            status_code=500,
            media_type="application/json",
        )
        return

    provider_id = context.provider_id
    target_url = context.target_url
    auth_headers = context.headers
    final_payload = context.payload
    request_metrics = context.request_metrics

    retry_config = await get_retry_config()
    max_retries = retry_config["max_retries"]
    retry_interval = retry_config["retry_interval"]
    switch_credential_enabled = await get_antigravity_switch_credential_enabled()

    DISABLE_ERROR_CODES = await get_auto_disable_error_codes()
    last_error_response = None
    retry_attempt = 0

    async def refresh_credential_fast():
        nonlocal model_name, current_file, credential_data, provider_id, request_body
        nonlocal target_url, auth_headers, final_payload, request_metrics
        route_result = await credential_manager.get_valid_model_credential(
            candidates,
            mode="primary",
            respect_model_blacklist=model_routing,
            excluded_provider_models=route_exclusions,
            excluded_credential_models=credential_route_exclusions,
        )
        if not route_result:
            return None
        model_name, current_file, credential_data = route_result
        request_body = {**body, "model": model_name}
        try:
            new_context = await prepare_provider_request(
                credential_data,
                request_body,
                streaming=True,
                extra_headers=headers,
            )
        except ValueError:
            await credential_manager.release_credential(current_file, mode="primary")
            return None
        provider_id = new_context.provider_id
        target_url = new_context.target_url
        auth_headers = new_context.headers
        final_payload = new_context.payload
        request_metrics = new_context.request_metrics
        return True

    attempt_limit = max_retries + MAX_MODEL_ROUTE_ATTEMPTS
    for attempt in range(attempt_limit + 1):
        received_content = False
        terminal_received = False
        stream_token_usage: Dict[str, Any] = {}
        need_retry = False
        model_route_retry = False

        try:
            async for chunk in stream_post_async(
                url=target_url,
                body=final_payload,
                native=native,
                headers=auth_headers,
                timeout=await get_upstream_timeout_seconds(),
            ):
                if isinstance(chunk, Response):
                    status_code = chunk.status_code
                    last_error_response = chunk

                    error_body = None
                    try:
                        error_body = (
                            chunk.body.decode("utf-8")
                            if isinstance(chunk.body, bytes)
                            else str(chunk.body)
                        )
                    except Exception as exc:
                        log.debug(
                            "[provider stream] could not decode an upstream error body "
                            f"({type(exc).__name__})."
                        )
                        error_body = ""

                    if received_content:
                        await record_api_call_error(
                            credential_manager,
                            current_file,
                            status_code,
                            None,
                            mode="primary",
                            model_name=model_name,
                            error_message=error_body,
                            provider=provider_id,
                        )
                        trace_decision(
                            category="retry",
                            action="skipped",
                            result="skipped",
                            reason="not_eligible",
                            attempt=attempt + 1,
                            status_code=status_code,
                        )
                        yield chunk
                        return

                    if status_code == 404:
                        credential_route_exclusions.add((current_file, model_name))
                        if model_routing:
                            log.warning(
                                "[provider stream] model route not found; blacklisting "
                                f"credential={current_file}, provider={provider_id}, model={model_name}."
                            )
                            await _exclude_missing_model_route(
                                credential_route_exclusions=credential_route_exclusions,
                                credential_name=current_file,
                                provider_id=provider_id,
                                model_name=model_name,
                            )
                        else:
                            log.warning(
                                "[provider stream] credential could not serve the requested model; "
                                f"trying another route (credential={current_file}, model={model_name})."
                            )
                        await record_model_route_miss(
                            credential_manager,
                            current_file,
                            model_name=model_name,
                            provider=provider_id,
                        )
                        if attempt < attempt_limit:
                            need_retry = True
                            model_route_retry = True
                            break
                        yield chunk
                        return
                    elif _is_retryable_status(status_code, DISABLE_ERROR_CODES):
                        log.warning(
                            f"[provider stream] streaming request failed (status={status_code}), credential={current_file}, response={error_body[:500] if error_body else 'None'}"
                        )

                        cooldown_until = None
                        if (status_code == 429 or status_code == 503) and error_body:
                            cooldown_until = await parse_and_log_cooldown(
                                error_body, mode="primary"
                            )

                        await record_api_call_error(
                            credential_manager,
                            current_file,
                            status_code,
                            cooldown_until,
                            mode="primary",
                            model_name=model_name,
                            error_message=error_body,
                            provider=provider_id,
                        )

                        should_retry = await handle_error_with_retry(
                            credential_manager,
                            status_code,
                            current_file,
                            retry_config["retry_enabled"],
                            retry_attempt,
                            max_retries,
                            retry_interval,
                            mode="primary",
                        )

                        if should_retry:
                            retry_attempt += 1
                            need_retry = True
                            break
                        else:
                            log.error(
                                "[provider stream] Maximum number of retries reached or should not be retried, returning original error"
                            )
                            yield chunk
                            return
                    else:
                        log.error(
                            f"[provider stream] streaming request failed with a non-retryable status (status={status_code}), credential={current_file}, response={error_body[:500] if error_body else 'None'}"
                        )
                        await record_api_call_error(
                            credential_manager,
                            current_file,
                            status_code,
                            None,
                            mode="primary",
                            model_name=model_name,
                            error_message=error_body,
                            provider=provider_id,
                        )
                        yield chunk
                        return
                else:
                    if _stream_event_is_heartbeat(chunk):
                        yield _normalize_sse_frame(chunk)
                        continue
                    if isinstance(chunk, (str, bytes)) and not chunk.strip():
                        continue
                    if provider_id == XAI:
                        chunk = xai_stream_line_to_gemini(chunk)
                        if not chunk:
                            continue
                    elif provider_id == OPENAI:
                        if get_credential_provider_variant(credential_data) == OPENAI_PLATFORM:
                            chunk = openai_stream_line_to_gemini(chunk)
                        else:
                            chunk = codex_stream_line_to_gemini(chunk)
                        if not chunk:
                            continue
                    elif provider_id == ANTHROPIC:
                        chunk = anthropic_stream_line_to_gemini(
                            chunk, stream_id=f"{current_file}:{model_name}"
                        )
                        if not chunk:
                            continue
                    elif provider_id == OLLAMA:
                        chunk = ollama_stream_line_to_gemini(chunk)
                        if not chunk:
                            continue

                    chunk = _normalize_sse_frame(chunk)

                    if not received_content:
                        received_content = True
                        log.debug(
                            f"[provider stream] started receiving streaming responses, model: {model_name}"
                        )

                    terminal_received = terminal_received or _stream_event_is_terminal(chunk)

                    chunk_token_usage = extract_token_usage_from_stream_chunk(chunk)
                    stream_token_usage = merge_token_usage(stream_token_usage, chunk_token_usage)

                    if isinstance(chunk, bytes):
                        log.debug(f"[provider stream raw] chunk(bytes): {chunk}")
                    else:
                        log.debug(f"[provider stream raw] chunk(str): {chunk}")

                    yield chunk

            if received_content and terminal_received:
                await record_api_call_success(
                    credential_manager,
                    current_file,
                    mode="primary",
                    model_name=model_name,
                    token_usage=stream_token_usage,
                    request_metrics={
                        **request_metrics,
                        "latency_ms": round((time.perf_counter() - request_started_at) * 1000),
                        "retry_count": attempt,
                    },
                    provider=provider_id,
                )
                log.debug(f"[provider stream] Streaming response completed, model: {model_name}")
                return
            elif received_content:
                log.warning(
                    "[provider stream] upstream closed before a terminal stream event "
                    f"(credential={current_file}, model={model_name})"
                )
                await record_api_call_error(
                    credential_manager,
                    current_file,
                    502,
                    None,
                    mode="primary",
                    model_name=model_name,
                    error_message="Upstream stream ended before a terminal event",
                    provider=provider_id,
                )
                yield Response(
                    content=json.dumps(
                        {"error": "The upstream streaming response ended unexpectedly."}
                    ),
                    status_code=502,
                    media_type="application/json",
                )
                return
            elif not need_retry:
                log.warning(
                    f"[provider stream] received an empty reply with no content, voucher: {current_file}"
                )
                await record_api_call_error(
                    credential_manager,
                    current_file,
                    200,
                    None,
                    mode="primary",
                    model_name=model_name,
                    error_message="Empty response from API",
                    provider=provider_id,
                )

                if retry_config["retry_enabled"] and retry_attempt < max_retries:
                    retry_attempt += 1
                    need_retry = True
                else:
                    log.error("[provider stream] Empty response reaches maximum number of retries")
                    yield Response(
                        content=json.dumps({"error": "Empty response returned by service"}),
                        status_code=500,
                        media_type="application/json",
                    )
                    return

            if need_retry:
                if model_route_retry:
                    log.info("[provider stream] Trying the next compatible model route.")
                else:
                    log.info(
                        "[provider stream] retrying request "
                        f"(attempt {retry_attempt + 1}/{max_retries + 1})."
                    )

                if model_route_retry or switch_credential_enabled:
                    switched = await _switch_credential_for_retry(
                        refresh_credential_fast=refresh_credential_fast,
                        log_prefix="[provider stream]",
                    )
                    if not switched:
                        log.error(
                            "[provider stream] No credentials or tokens available when retrying"
                        )
                        if model_route_retry and last_error_response is not None:
                            yield last_error_response
                            return
                        yield Response(
                            content=json.dumps({"error": "No credentials are available."}),
                            status_code=503,
                            media_type="application/json",
                        )
                        return
                continue

        except (asyncio.CancelledError, GeneratorExit):
            # A disconnected client closes this async generator at its current
            # yield point. Release the active distributed lease explicitly;
            # normal success/error accounting may not get a chance to run.
            trace_decision(
                category="upstream",
                action="failed",
                result="failed",
                reason="cancelled",
                provider=provider_id,
                model=model_name,
                status_code=499,
            )
            await credential_manager.release_credential(current_file, mode="primary")
            raise
        except CoordinationUnavailableError as exc:
            yield await _coordination_unavailable_response(
                log_prefix="[provider stream]",
                model_name=requested_model,
                error=exc,
            )
            return
        except Exception as e:
            is_timeout = isinstance(e, (TimeoutError, httpx.TimeoutException))
            exception_status = int(getattr(e, "status_code", 0) or (504 if is_timeout else 502))
            log.error(
                f"[provider stream] Streaming Request Exception: {e}, Credentials: {current_file}"
            )
            if received_content:
                await record_api_call_error(
                    credential_manager,
                    current_file,
                    exception_status,
                    None,
                    mode="primary",
                    model_name=model_name,
                    error_message=str(e),
                    provider=provider_id,
                )
                trace_decision(
                    category="retry",
                    action="skipped",
                    result="skipped",
                    reason="not_eligible",
                    attempt=attempt + 1,
                    status_code=exception_status,
                )
                yield Response(
                    content=json.dumps(
                        {
                            "error": (
                                "The upstream streaming request timed out after output began."
                                if is_timeout
                                else "The upstream streaming request failed after output began."
                            )
                        }
                    ),
                    status_code=exception_status,
                    media_type="application/json",
                )
                return
            if exception_status == 404:
                credential_route_exclusions.add((current_file, model_name))
                if model_routing:
                    await _exclude_missing_model_route(
                        credential_route_exclusions=credential_route_exclusions,
                        credential_name=current_file,
                        provider_id=provider_id,
                        model_name=model_name,
                    )
                await record_model_route_miss(
                    credential_manager,
                    current_file,
                    model_name=model_name,
                    provider=provider_id,
                )
                if attempt < attempt_limit:
                    switched = await _switch_credential_for_retry(
                        refresh_credential_fast=refresh_credential_fast,
                        log_prefix="[provider stream]",
                    )
                    if switched:
                        continue
                yield Response(
                    content=json.dumps(
                        {"error": "No compatible credential could serve the requested model."}
                    ),
                    status_code=404,
                    media_type="application/json",
                )
                return
            await record_api_call_error(
                credential_manager,
                current_file,
                exception_status,
                None,
                mode="primary",
                model_name=model_name,
                error_message=str(e),
                provider=provider_id,
            )
            if retry_config["retry_enabled"] and retry_attempt < max_retries:
                retry_attempt += 1
                log.info(
                    "[provider stream] retry after abnormality "
                    f"(attempt {retry_attempt + 1}/{max_retries + 1})..."
                )
                await asyncio.sleep(retry_interval)
                if switch_credential_enabled:
                    switched = await _switch_credential_for_retry(
                        refresh_credential_fast=refresh_credential_fast,
                        log_prefix="[provider stream]",
                    )
                    if not switched:
                        yield Response(
                            content=json.dumps({"error": "No credentials are available."}),
                            status_code=503,
                            media_type="application/json",
                        )
                        return
                continue
            else:
                log.error(f"[provider stream] all retries failed. Last exception: {e}")
                if last_error_response:
                    yield last_error_response
                else:
                    yield Response(
                        content=json.dumps(
                            {"error": "The upstream streaming request failed unexpectedly."}
                        ),
                        status_code=500,
                        media_type="application/json",
                    )
                return

    log.error("[provider stream] all retries failed.")
    if last_error_response:
        yield last_error_response
    else:
        yield Response(
            content=json.dumps({"error": "Request failed after all retries were exhausted."}),
            status_code=429,
            media_type="application/json",
        )


async def non_stream_request(
    body: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    model_candidates: Optional[List[str]] = None,
    model_routing: bool = False,
) -> Response:
    """Public non-streaming entry point: guardrails, cache, then upstream."""
    admission_response = runtime_admission_response()
    if admission_response is not None:
        return admission_response
    guard_response, body = await apply_pre_call_guardrails(body)
    if guard_response is not None:
        return guard_response

    cache_key, cached_response = await lookup_response_cache(body)
    if cached_response is not None:
        await record_response_cache_hit(
            model_name=str(body.get("model") or ""),
            status_code=cached_response.status_code,
        )
        return cached_response

    response = await _non_stream_request_upstream(
        body,
        headers=headers,
        model_candidates=model_candidates,
        model_routing=model_routing,
    )

    if cache_key:
        try:
            await store_response_cache(cache_key, response)
        except Exception as exc:
            log.debug(f"[response-cache] response store failed ({type(exc).__name__}).")
    return response


async def _non_stream_request_upstream(
    body: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    model_candidates: Optional[List[str]] = None,
    model_routing: bool = False,
) -> Response:
    request_started_at = time.perf_counter()

    if await get_antigravity_stream_to_nonstream():
        log.debug("[provider] Streaming collection mode for non-streaming requests")

        stream = _stream_request_upstream(
            body=body,
            native=False,
            headers=headers,
            model_candidates=model_candidates,
            model_routing=model_routing,
        )

        return await collect_streaming_response(stream)

    log.debug("[provider] Direct non-streaming mode enabled")

    requested_model = str(body.get("model") or "")
    candidates = _normalize_model_candidates(body, model_candidates)
    route_exclusions: set[tuple[str, str]] = set()
    credential_route_exclusions: set[tuple[str, str]] = set()

    try:
        route_result = await credential_manager.get_valid_model_credential(
            candidates,
            mode="primary",
            respect_model_blacklist=model_routing,
            excluded_provider_models=route_exclusions,
            excluded_credential_models=credential_route_exclusions,
        )
    except CoordinationUnavailableError as exc:
        return await _coordination_unavailable_response(
            log_prefix="[provider]",
            model_name=requested_model,
            error=exc,
        )

    if not route_result:
        log.error("[provider] No credentials currently available")
        await record_unassigned_api_call_error(
            status_code=503, mode="primary", model_name=requested_model
        )
        return Response(
            content=json.dumps({"error": _no_credential_error_message(requested_model)}),
            status_code=503,
            media_type="application/json",
        )

    model_name, current_file, credential_data = route_result
    if (
        get_credential_provider(credential_data) == OPENAI
        and get_credential_provider_variant(credential_data) == CODEX
    ):
        # ChatGPT's Codex endpoint is stream-only. Re-enter through the streaming
        # path so downstream non-stream clients still receive one collected response.
        await credential_manager.release_credential(current_file, mode="primary")
        return await collect_streaming_response(
            _stream_request_upstream(
                body=body,
                native=False,
                headers=headers,
                model_candidates=model_candidates,
                model_routing=model_routing,
            )
        )

    request_body = {**body, "model": model_name}
    try:
        context = await prepare_provider_request(
            credential_data,
            request_body,
            streaming=False,
            extra_headers=headers,
        )
    except ValueError as exc:
        provider_id = get_credential_provider(credential_data)
        await record_api_call_error(
            credential_manager,
            current_file,
            500,
            None,
            mode="primary",
            model_name=model_name,
            error_message=str(exc),
            provider=provider_id,
        )
        return Response(
            content=json.dumps({"error": str(exc)}),
            status_code=500,
            media_type="application/json",
        )

    provider_id = context.provider_id
    target_url = context.target_url
    auth_headers = context.headers
    final_payload = context.payload
    request_metrics = context.request_metrics

    retry_config = await get_retry_config()
    max_retries = retry_config["max_retries"]
    retry_interval = retry_config["retry_interval"]
    switch_credential_enabled = await get_antigravity_switch_credential_enabled()

    DISABLE_ERROR_CODES = await get_auto_disable_error_codes()
    last_error_response = None
    retry_attempt = 0

    async def refresh_credential_fast():
        nonlocal model_name, current_file, credential_data, provider_id, request_body
        nonlocal target_url, auth_headers, final_payload, request_metrics
        route_result = await credential_manager.get_valid_model_credential(
            candidates,
            mode="primary",
            respect_model_blacklist=model_routing,
            excluded_provider_models=route_exclusions,
            excluded_credential_models=credential_route_exclusions,
        )
        if not route_result:
            return None
        model_name, current_file, credential_data = route_result
        request_body = {**body, "model": model_name}
        try:
            new_context = await prepare_provider_request(
                credential_data,
                request_body,
                streaming=False,
                extra_headers=headers,
            )
        except ValueError:
            await credential_manager.release_credential(current_file, mode="primary")
            return None
        provider_id = new_context.provider_id
        target_url = new_context.target_url
        auth_headers = new_context.headers
        final_payload = new_context.payload
        request_metrics = new_context.request_metrics
        return True

    attempt_limit = max_retries + MAX_MODEL_ROUTE_ATTEMPTS
    for attempt in range(attempt_limit + 1):
        need_retry = False

        try:
            response = await post_async(
                url=target_url,
                json=final_payload,
                headers=auth_headers,
                timeout=await get_upstream_timeout_seconds(),
            )

            status_code = response.status_code

            if status_code == 200:
                if not response.content or len(response.content) == 0:
                    log.warning(
                        f"[provider] Received 200 response but the content is empty, voucher: {current_file}"
                    )

                    await record_api_call_error(
                        credential_manager,
                        current_file,
                        200,
                        None,
                        mode="primary",
                        model_name=model_name,
                        error_message="Empty response from API",
                        provider=provider_id,
                    )

                    if retry_config["retry_enabled"] and retry_attempt < max_retries:
                        retry_attempt += 1
                        need_retry = True
                    else:
                        log.error("[provider] Empty response reaches maximum number of retries")
                        return Response(
                            content=json.dumps({"error": "Empty response returned by service"}),
                            status_code=503,
                            media_type="application/json",
                        )
                else:
                    response_content = response.content
                    if provider_id == XAI:
                        try:
                            response_content = json.dumps(
                                xai_response_to_gemini(response.json())
                            ).encode("utf-8")
                        except (ValueError, TypeError) as exc:
                            await record_api_call_error(
                                credential_manager,
                                current_file,
                                502,
                                None,
                                mode="primary",
                                model_name=model_name,
                                error_message=str(exc),
                                provider=provider_id,
                            )
                            return Response(
                                content=json.dumps(
                                    {"error": "Grok Build returned an invalid response."}
                                ),
                                status_code=502,
                                media_type="application/json",
                            )
                    elif provider_id == OPENAI:
                        try:
                            if get_credential_provider_variant(credential_data) == OPENAI_PLATFORM:
                                translated = openai_response_to_gemini(response.json())
                            else:
                                translated = codex_response_to_gemini(response.json())
                            response_content = json.dumps(translated).encode("utf-8")
                        except (ValueError, TypeError) as exc:
                            await record_api_call_error(
                                credential_manager,
                                current_file,
                                502,
                                None,
                                mode="primary",
                                model_name=model_name,
                                error_message=str(exc),
                                provider=provider_id,
                            )
                            return Response(
                                content=json.dumps(
                                    {"error": "OpenAI returned an invalid response."}
                                ),
                                status_code=502,
                                media_type="application/json",
                            )
                    elif provider_id == ANTHROPIC:
                        try:
                            response_content = json.dumps(
                                anthropic_response_to_gemini(response.json())
                            ).encode("utf-8")
                        except (ValueError, TypeError) as exc:
                            await record_api_call_error(
                                credential_manager,
                                current_file,
                                502,
                                None,
                                mode="primary",
                                model_name=model_name,
                                error_message=str(exc),
                                provider=provider_id,
                            )
                            return Response(
                                content=json.dumps(
                                    {"error": "Anthropic returned an invalid response."}
                                ),
                                status_code=502,
                                media_type="application/json",
                            )
                    elif provider_id == OLLAMA:
                        try:
                            response_content = json.dumps(
                                ollama_response_to_gemini(response.json())
                            ).encode("utf-8")
                        except (ValueError, TypeError) as exc:
                            await record_api_call_error(
                                credential_manager,
                                current_file,
                                502,
                                None,
                                mode="primary",
                                model_name=model_name,
                                error_message=str(exc),
                                provider=provider_id,
                            )
                            return Response(
                                content=json.dumps(
                                    {"error": "Ollama returned an invalid response."}
                                ),
                                status_code=502,
                                media_type="application/json",
                            )
                    token_usage = extract_token_usage_from_response(response_content)
                    await record_api_call_success(
                        credential_manager,
                        current_file,
                        mode="primary",
                        model_name=model_name,
                        token_usage=token_usage,
                        status_code=status_code,
                        request_metrics={
                            **request_metrics,
                            "latency_ms": round((time.perf_counter() - request_started_at) * 1000),
                            "retry_count": attempt,
                        },
                        provider=provider_id,
                    )
                    return Response(
                        content=response_content,
                        status_code=200,
                        media_type="application/json",
                    )

            if status_code != 200:
                last_error_response = Response(
                    content=response.content,
                    status_code=status_code,
                    headers=dict(response.headers),
                )

                error_text = ""
                try:
                    error_text = response.text
                except Exception as exc:
                    log.debug(
                        "[provider] could not decode an upstream error body "
                        f"({type(exc).__name__})."
                    )

                if status_code == 404:
                    credential_route_exclusions.add((current_file, model_name))
                    if model_routing:
                        log.warning(
                            "[provider] model route not found; blacklisting "
                            f"credential={current_file}, provider={provider_id}, model={model_name}."
                        )
                        await _exclude_missing_model_route(
                            credential_route_exclusions=credential_route_exclusions,
                            credential_name=current_file,
                            provider_id=provider_id,
                            model_name=model_name,
                        )
                    else:
                        log.warning(
                            "[provider] credential could not serve the requested model; "
                            f"trying another route (credential={current_file}, model={model_name})."
                        )
                    await record_model_route_miss(
                        credential_manager,
                        current_file,
                        model_name=model_name,
                        provider=provider_id,
                    )
                    if attempt < attempt_limit and await refresh_credential_fast():
                        continue
                    return last_error_response
                elif _is_retryable_status(status_code, DISABLE_ERROR_CODES):
                    log.warning(
                        f"[provider] non-streaming request failed (status={status_code}), credential={current_file}, response={error_text[:500] if error_text else 'None'}"
                    )

                    cooldown_until = None
                    if (status_code == 429 or status_code == 503) and error_text:
                        cooldown_until = await parse_and_log_cooldown(error_text, mode="primary")

                    await record_api_call_error(
                        credential_manager,
                        current_file,
                        status_code,
                        cooldown_until,
                        mode="primary",
                        model_name=model_name,
                        error_message=error_text,
                        provider=provider_id,
                    )

                    should_retry = await handle_error_with_retry(
                        credential_manager,
                        status_code,
                        current_file,
                        retry_config["retry_enabled"],
                        retry_attempt,
                        max_retries,
                        retry_interval,
                        mode="primary",
                    )

                    if should_retry:
                        retry_attempt += 1
                        need_retry = True
                    else:
                        log.error(
                            "[provider] Maximum number of retries reached or should not be retried, returning original error"
                        )
                        return last_error_response
                else:
                    log.error(
                        f"[provider] non-streaming request failed with a non-retryable status (status={status_code}), credential={current_file}, response={error_text[:500] if error_text else 'None'}"
                    )
                    await record_api_call_error(
                        credential_manager,
                        current_file,
                        status_code,
                        None,
                        mode="primary",
                        model_name=model_name,
                        error_message=error_text,
                        provider=provider_id,
                    )
                    return last_error_response

            if need_retry:
                log.info(
                    f"[provider] retrying request (attempt {retry_attempt + 1}/{max_retries + 1})."
                )

                if switch_credential_enabled:
                    switched = await _switch_credential_for_retry(
                        refresh_credential_fast=refresh_credential_fast,
                        log_prefix="[provider]",
                    )
                    if not switched:
                        log.error("[provider] No credentials or tokens available when retrying")
                        return Response(
                            content=json.dumps({"error": "No credentials are available."}),
                            status_code=503,
                            media_type="application/json",
                        )
                continue

        except CoordinationUnavailableError as exc:
            return await _coordination_unavailable_response(
                log_prefix="[provider]",
                model_name=requested_model,
                error=exc,
            )
        except Exception as e:
            log.error(
                f"[provider] non-streaming request raised an exception: {e}; credential={current_file}"
            )
            await record_api_call_error(
                credential_manager,
                current_file,
                500,
                None,
                mode="primary",
                model_name=model_name,
                error_message=str(e),
                provider=provider_id,
            )
            if retry_config["retry_enabled"] and retry_attempt < max_retries:
                retry_attempt += 1
                log.info(
                    "[provider] Retry after exception "
                    f"(attempt {retry_attempt + 1}/{max_retries + 1})..."
                )
                await asyncio.sleep(retry_interval)
                if switch_credential_enabled:
                    switched = await _switch_credential_for_retry(
                        refresh_credential_fast=refresh_credential_fast,
                        log_prefix="[provider]",
                    )
                    if not switched:
                        return Response(
                            content=json.dumps({"error": "No credentials are available."}),
                            status_code=503,
                            media_type="application/json",
                        )
                continue
            else:
                log.error(f"[provider] all retries failed. Last exception: {e}")
                if last_error_response:
                    return last_error_response
                else:
                    return Response(
                        content=json.dumps({"error": "The upstream request failed unexpectedly."}),
                        status_code=500,
                        media_type="application/json",
                    )

    log.error("[provider] all retries failed.")
    if last_error_response:
        return last_error_response
    else:
        return Response(
            content=json.dumps({"error": "Request failed after all retries were exhausted."}),
            status_code=500,
            media_type="application/json",
        )


async def _get_enabled_catalog_credentials() -> List[Tuple[str, str, str, Dict[str, Any]]]:
    """Return enabled credentials with precise product and routing identities."""
    storage_adapter = await get_storage_adapter()
    credentials: List[Tuple[str, str, str, Dict[str, Any]]] = []

    get_all_credentials = getattr(storage_adapter, "get_all_credentials", None)
    get_all_states = getattr(storage_adapter, "get_all_credential_states", None)
    if callable(get_all_credentials) and callable(get_all_states):
        credential_map, state_map = await asyncio.gather(
            get_all_credentials(mode="primary"),
            get_all_states(mode="primary"),
        )
        credential_items = credential_map.items()
    else:
        filenames = await storage_adapter.list_credentials(mode="primary")
        credential_items = []
        state_map = {}
        for filename in filenames:
            state_map[filename] = await storage_adapter.get_credential_state(
                filename, mode="primary"
            )
            credential_data = await storage_adapter.get_credential(filename, mode="primary")
            credential_items.append((filename, credential_data))

    for filename, credential_data in credential_items:
        state = state_map.get(filename) or {}
        if state.get("disabled") or not credential_data:
            continue
        catalog_data = dict(credential_data)
        if state.get("tier") and not catalog_data.get("tier"):
            catalog_data["tier"] = state["tier"]
        credentials.append(
            (
                filename,
                get_credential_provider_variant(catalog_data),
                get_credential_provider(catalog_data),
                catalog_data,
            )
        )
    return credentials


def _stored_model_ids(credential_data: Dict[str, Any]) -> set[str]:
    values = credential_data.get("model_ids")
    if not isinstance(values, list):
        return set()
    return {
        str(model_id).removeprefix("models/").strip()
        for model_id in values
        if str(model_id or "").strip()
    }


async def get_configured_provider_model_ids() -> Dict[str, set[str]]:
    """Return stored model catalogs grouped by precise provider product."""
    provider_models: Dict[str, set[str]] = {}
    for _, provider_variant, _, credential_data in await _get_enabled_catalog_credentials():
        provider_models.setdefault(provider_variant, set()).update(
            _stored_model_ids(credential_data)
        )
    return provider_models


async def get_configured_provider_ids() -> set[str]:
    """Return provider products with at least one enabled credential."""
    return set(await get_configured_provider_model_ids())


def _catalog_request_matches(
    requested_provider: str,
    provider_variant: str,
    routing_provider: str,
) -> bool:
    requested = str(requested_provider or "").strip().lower().replace("-", "_")
    if requested in {CODEX, OPENAI_PLATFORM, GROK, XAI_CONSOLE}:
        return provider_variant == requested
    return routing_provider == get_provider_routing_id(requested)


def _catalog_entitlement_signature(credential_data: Dict[str, Any]) -> str:
    fields = (
        "tier",
        "plan",
        "plan_type",
        "subscription_tier",
        "subscription_plan",
        "account_type",
        "access_tier",
    )
    values = []
    for field in fields:
        value = credential_data.get(field)
        if isinstance(value, (str, int, float)) and str(value).strip():
            values.append(f"{field}:{str(value).strip().lower()}")
    return "|".join(values) or "unknown"


def _stored_catalog_signature(credential_data: Dict[str, Any]) -> str:
    model_ids = sorted(_stored_model_ids(credential_data))
    if not model_ids:
        return "uncataloged"
    payload = "\0".join(model_ids).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _catalog_cohort_key(
    credential: Tuple[str, str, str, Dict[str, Any]],
) -> Tuple[str, str, str]:
    _, provider_variant, _, credential_data = credential
    return (
        provider_variant,
        _catalog_entitlement_signature(credential_data),
        _stored_catalog_signature(credential_data),
    )


def _catalog_rotation_score(*parts: str) -> bytes:
    window = int(time.time() // MODEL_DISCOVERY_ROTATION_SECONDS)
    value = "|".join((str(window), *parts)).encode("utf-8")
    return hashlib.sha256(value).digest()


def _group_catalog_credentials(
    credentials: List[Tuple[str, str, str, Dict[str, Any]]],
) -> Dict[Tuple[str, str, str], List[Tuple[str, str, str, Dict[str, Any]]]]:
    cohorts: Dict[
        Tuple[str, str, str],
        List[Tuple[str, str, str, Dict[str, Any]]],
    ] = {}
    for credential in credentials:
        cohorts.setdefault(_catalog_cohort_key(credential), []).append(credential)
    return cohorts


def _select_catalog_cohorts(
    cohorts: Dict[
        Tuple[str, str, str],
        List[Tuple[str, str, str, Dict[str, Any]]],
    ],
) -> List[
    Tuple[
        Tuple[str, str, str],
        List[Tuple[str, str, str, Dict[str, Any]]],
    ]
]:
    """Select a bounded, provider-fair set of cohorts for live discovery."""
    queues: Dict[
        str,
        List[
            Tuple[
                Tuple[str, str, str],
                List[Tuple[str, str, str, Dict[str, Any]]],
            ]
        ],
    ] = {}
    for key, members in cohorts.items():
        queues.setdefault(key[0], []).append((key, members))
    for provider_id, items in queues.items():
        items.sort(key=lambda item: _catalog_rotation_score(provider_id, *item[0]))

    selected = []
    provider_ids = sorted(queues)
    while len(selected) < MAX_MODEL_DISCOVERY_COHORTS:
        progressed = False
        for provider_id in provider_ids:
            queue = queues[provider_id]
            if not queue:
                continue
            selected.append(queue.pop(0))
            progressed = True
            if len(selected) >= MAX_MODEL_DISCOVERY_COHORTS:
                break
        if not progressed:
            break
    return selected


async def _discover_credential_model_ids(
    filename: str,
    provider_variant: str,
    credential_data: Dict[str, Any],
    storage_adapter,
) -> CredentialModelDiscovery:
    """Refresh and persist the catalog exposed by one credential."""
    stored = _stored_model_ids(credential_data)
    data = credential_data
    try:
        if provider_variant == GOOGLE_ANTIGRAVITY:
            data = await credential_manager.prepare_credential(
                filename, credential_data, mode="primary"
            )
            access_token = (data or {}).get("access_token") or (data or {}).get("token")
            if not access_token:
                return CredentialModelDiscovery(frozenset(stored), False)
            discovered = await fetch_antigravity_model_ids(str(access_token))
        elif provider_variant == GOOGLE_AI_STUDIO:
            api_key = str(data.get("api_key") or "")
            if not api_key:
                return CredentialModelDiscovery(frozenset(stored), False)
            response = await get_async(
                build_models_url(await get_google_ai_studio_api_url()),
                headers=build_api_key_headers(api_key),
                timeout=30.0,
            )
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            discovered = parse_model_ids(response.json())
        elif provider_variant in {GROK, XAI_CONSOLE}:
            if provider_variant == GROK:
                data = await credential_manager.prepare_credential(
                    filename, credential_data, mode="primary"
                )
            access_token = (
                (data or {}).get("api_key")
                or (data or {}).get("access_token")
                or (data or {}).get("token")
            )
            if not access_token:
                return CredentialModelDiscovery(frozenset(stored), False)
            discovered = (
                await fetch_xai_oauth_model_ids(str(access_token))
                if provider_variant == GROK
                else await fetch_xai_model_ids(str(access_token))
            )
        elif provider_variant == CODEX:
            data = await credential_manager.prepare_credential(
                filename, credential_data, mode="primary"
            )
            access_token = (data or {}).get("access_token") or (data or {}).get("token")
            if not access_token:
                return CredentialModelDiscovery(frozenset(stored), False)
            account_id = str((data or {}).get("account_id") or "")
            discovered = await fetch_codex_model_ids(str(access_token), account_id)
        elif provider_variant == OPENAI_PLATFORM:
            api_key = str(data.get("api_key") or "")
            if not api_key:
                return CredentialModelDiscovery(frozenset(stored), False)
            discovered = await fetch_openai_model_ids(api_key)
        elif provider_variant in {CLAUDE_CODE, CLAUDE_PLATFORM}:
            if provider_variant == CLAUDE_CODE:
                data = await credential_manager.prepare_credential(
                    filename, credential_data, mode="primary"
                )
            if not data:
                return CredentialModelDiscovery(frozenset(stored), False)
            discovered = await fetch_anthropic_model_ids(data)
        elif provider_variant == OLLAMA:
            base_url = str(data.get("base_url") or "")
            if not base_url:
                return CredentialModelDiscovery(frozenset(stored), False)
            discovered = await fetch_ollama_model_ids(
                base_url,
                str(data.get("api_key") or ""),
            )
        else:
            return CredentialModelDiscovery(frozenset(stored), False)

        normalized = {
            str(model_id).removeprefix("models/").strip()
            for model_id in discovered
            if str(model_id or "").strip()
        }
        if normalized and normalized != stored:
            updated = dict(data or credential_data)
            updated["model_ids"] = sorted(normalized)
            await storage_adapter.store_credential(filename, updated, mode="primary")
        return CredentialModelDiscovery(frozenset(normalized or stored), True)
    except Exception as exc:
        log.warning(f"{provider_variant} model discovery failed for {filename}: {exc}")
        return CredentialModelDiscovery(frozenset(stored), False)


async def _discover_catalog_models(
    credentials: List[Tuple[str, str, str, Dict[str, Any]]],
    storage_adapter,
) -> Dict[str, set[str]]:
    """Merge all cached catalogs and refresh only bounded cohort representatives."""
    provider_models: Dict[str, set[str]] = {}
    for _, provider_variant, _, credential_data in credentials:
        provider_models.setdefault(provider_variant, set()).update(
            _stored_model_ids(credential_data)
        )

    cohorts = _group_catalog_credentials(credentials)
    selected = _select_catalog_cohorts(cohorts)
    skipped_count = len(cohorts) - len(selected)
    if skipped_count:
        log.info(
            "Model discovery deferred %s cohort(s); cached catalogs remain available.",
            skipped_count,
        )

    semaphore = asyncio.Semaphore(MAX_MODEL_DISCOVERY_CONCURRENCY)

    async def discover_cohort(key, members):
        ordered = sorted(
            members,
            key=lambda item: _catalog_rotation_score(*key, item[0]),
        )
        models: set[str] = set()
        for filename, provider_variant, _, credential_data in ordered[
            :MAX_MODEL_DISCOVERY_FAILOVER_ATTEMPTS
        ]:
            models.update(_stored_model_ids(credential_data))
            async with semaphore:
                result = await _discover_credential_model_ids(
                    filename,
                    provider_variant,
                    credential_data,
                    storage_adapter,
                )
            models.update(result.model_ids)
            if result.refreshed:
                break
        return key[0], models

    results = await asyncio.gather(
        *(discover_cohort(key, members) for key, members in selected),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, Exception):
            log.warning(f"Provider model cohort discovery failed: {result}")
            continue
        provider_variant, model_ids = result
        provider_models.setdefault(provider_variant, set()).update(model_ids)
    return provider_models


async def fetch_provider_model_ids(
    provider_id: str,
    stored_model_ids: Optional[set[str]] = None,
) -> set[str]:
    """Discover model IDs through bounded representatives of matching cohorts."""
    fallback = set(stored_model_ids or ())
    credentials = [
        credential
        for credential in await _get_enabled_catalog_credentials()
        if _catalog_request_matches(provider_id, credential[1], credential[2])
    ]
    if not credentials:
        return fallback

    storage_adapter = await get_storage_adapter()
    provider_models = await _discover_catalog_models(credentials, storage_adapter)
    model_ids = set(fallback)
    for values in provider_models.values():
        model_ids.update(values)
    return model_ids


async def fetch_configured_provider_models() -> Dict[str, List[str]]:
    """Discover bounded provider cohorts while preserving every cached catalog."""
    credentials = await _get_enabled_catalog_credentials()
    storage_adapter = await get_storage_adapter()
    provider_models = await _discover_catalog_models(credentials, storage_adapter)
    return {
        provider_id: sorted(model_ids) for provider_id, model_ids in sorted(provider_models.items())
    }


async def fetch_quota_info(access_token: str) -> Dict[str, Any]:

    headers = await build_primary_headers(access_token)

    try:
        primary_url = await get_antigravity_api_url()

        response = await post_async(
            url=f"{primary_url}/v1internal:fetchAvailableModels",
            json={},
            headers=headers,
            timeout=30.0,
        )

        if response.status_code == 200:
            data = response.json()
            log.debug(
                f"[provider quota] Raw response: {json.dumps(data, ensure_ascii=False)[:500]}"
            )

            quota_info = {}

            if "models" in data and isinstance(data["models"], dict):
                for model_id, model_data in data["models"].items():
                    if isinstance(model_data, dict) and "quotaInfo" in model_data:
                        quota = model_data["quotaInfo"]
                        remaining = quota.get("remainingFraction", 0)
                        reset_time_raw = quota.get("resetTime", "")

                        reset_time_beijing = "N/A"
                        if reset_time_raw:
                            try:
                                utc_date = datetime.fromisoformat(
                                    reset_time_raw.replace("Z", "+00:00")
                                )

                                from datetime import timedelta

                                beijing_date = utc_date + timedelta(hours=8)
                                reset_time_beijing = beijing_date.strftime("%m-%d %H:%M")
                            except Exception as e:
                                log.warning(f"[provider quota] Failed to parse reset time: {e}")

                        quota_info[model_id] = {
                            "remaining": remaining,
                            "resetTime": reset_time_beijing,
                            "resetTimeRaw": reset_time_raw,
                        }

            return {"success": True, "models": quota_info}
        else:
            log.error(
                f"[provider quota] Failed to fetch quota ({response.status_code}): {response.text[:500]}"
            )
            return {"success": False, "error": f"API returned an error: {response.status_code}"}

    except Exception as e:
        import traceback

        log.error(f"[provider quota] Failed to fetch quota: {e}")
        log.error(f"[provider quota] Traceback: {traceback.format_exc()}")
        return {"success": False, "error": "Unable to retrieve provider quota information."}
