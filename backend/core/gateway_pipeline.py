"""Pre-call guardrails and exact-match response caching for the request path.

This module is the single integration layer between the protocol routers
(which normalize every request into the internal Gemini format) and the
upstream dispatchers in ``core.api.primary``. Both features are disabled by
default and are switched on through config/env:

- ``GUARDRAILS_ENABLED`` — prompt-injection blocking, keyword blocking, and
  PII masking applied to user text before it leaves the gateway.
- ``RESPONSE_CACHE_ENABLED`` — exact-match caching of deterministic
  (temperature == 0) non-streaming responses.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional, Tuple

from core.guardrails import GuardrailsEngine
from core.request_trace_service import trace_decision
from core.response_cache import generate_cache_key, response_cache, response_cache_coordinator
from fastapi import Response
from log import log

# Responses larger than this are not cached (memory protection).
MAX_CACHEABLE_RESPONSE_BYTES = 512 * 1024

CACHE_HIT_HEADER = "x-polaris-cache"


def runtime_admission_response() -> Optional[Response]:
    """Reject inference after the process lifecycle has closed admission."""
    from core.runtime_lifecycle import get_runtime_lifecycle

    lifecycle = get_runtime_lifecycle()
    if lifecycle is None or lifecycle.admission_available:
        return None
    return Response(
        content=json.dumps(
            {
                "error": {
                    "message": "Gateway runtime is temporarily unavailable.",
                    "type": "runtime_unavailable",
                }
            }
        ),
        status_code=503,
        media_type="application/json",
    )


def _iter_text_parts(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collect mutable references to every text part in a Gemini payload."""
    parts: List[Dict[str, Any]] = []
    system_instruction = body.get("system_instruction") or body.get("systemInstruction")
    if isinstance(system_instruction, dict):
        for part in system_instruction.get("parts") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part)
    contents = body.get("contents")
    if isinstance(contents, list):
        for content in contents:
            if not isinstance(content, dict):
                continue
            for part in content.get("parts") or []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part)
    return parts


async def apply_pre_call_guardrails(
    body: Dict[str, Any],
) -> Tuple[Optional[Response], Dict[str, Any]]:
    """Inspect and sanitize the request payload before upstream dispatch.

    Returns ``(blocking_response, body)``. When the request violates a
    blocking rule (prompt injection or blocked keyword) a 400 ``Response`` is
    returned and the request must not be forwarded. When PII masking applies,
    the returned body is a sanitized deep copy; otherwise the original body is
    returned unchanged.
    """
    from config import get_guardrails_config

    try:
        settings = await get_guardrails_config()
    except Exception as exc:
        log.error(
            f"[guardrails] policy resolution failed ({type(exc).__name__}); "
            "blocking the request because enforcement state is unknown."
        )
        trace_decision(
            category="guardrail",
            action="blocked",
            result="failed",
            reason="policy_unavailable",
        )
        return (
            Response(
                content=json.dumps(
                    {
                        "error": {
                            "message": "Gateway guardrails are temporarily unavailable.",
                            "type": "guardrails_unavailable",
                        }
                    }
                ),
                status_code=503,
                media_type="application/json",
            ),
            body,
        )

    if not settings["enabled"]:
        trace_decision(
            category="guardrail",
            action="skipped",
            result="skipped",
            reason="feature_disabled",
        )
        return None, body

    engine = GuardrailsEngine(
        enable_pii_masking=settings["pii_masking_enabled"],
        enable_injection_detection=settings["injection_detection_enabled"],
        custom_blocked_words=settings["blocked_keywords"],
    )

    sanitized_body: Optional[Dict[str, Any]] = None
    text_parts = _iter_text_parts(body)
    for index, part in enumerate(text_parts):
        result = engine.inspect_and_sanitize(part["text"])
        if not result.is_safe:
            log.warning(f"[guardrails] request blocked: {', '.join(result.violations)}")
            reason = (
                "injection_detected"
                if any("injection" in str(item).lower() for item in result.violations)
                else "blocked_keyword"
            )
            trace_decision(
                category="guardrail",
                action="blocked",
                result="denied",
                reason=reason,
            )
            return (
                Response(
                    content=json.dumps(
                        {
                            "error": {
                                "message": "Request blocked by gateway guardrails.",
                                "type": "guardrail_violation",
                                "violations": result.violations,
                            }
                        }
                    ),
                    status_code=400,
                    media_type="application/json",
                ),
                body,
            )
        if result.sanitized_text != part["text"]:
            if sanitized_body is None:
                sanitized_body = copy.deepcopy(body)
            _iter_text_parts(sanitized_body)[index]["text"] = result.sanitized_text
            log.info(f"[guardrails] masked PII in request text ({', '.join(result.violations)})")

    trace_decision(
        category="guardrail",
        action="masked" if sanitized_body is not None else "evaluated",
        result="succeeded" if sanitized_body is not None else "allowed",
        reason="pii_masked" if sanitized_body is not None else "policy_passed",
    )

    return None, sanitized_body if sanitized_body is not None else body


def _is_cacheable_request(body: Dict[str, Any]) -> bool:
    """Only deterministic requests (explicit temperature == 0) are cacheable."""
    request_body = body.get("request")
    if not isinstance(request_body, dict):
        request_body = body
    generation_config = request_body.get("generationConfig")
    if not isinstance(generation_config, dict):
        return False
    temperature = generation_config.get("temperature")
    try:
        return temperature is not None and float(temperature) == 0.0
    except (TypeError, ValueError):
        return False


async def lookup_response_cache(
    body: Dict[str, Any],
) -> Tuple[Optional[str], Optional[Response]]:
    """Return ``(cache_key, cached_response)`` for a non-streaming request.

    ``cache_key`` is ``None`` when caching is disabled or the request is not
    cacheable; ``cached_response`` is ``None`` on cache miss.
    """
    from config import get_response_cache_config
    from core.request_context import is_operation_replay_required

    replay_required = is_operation_replay_required()

    def replay_miss() -> Tuple[None, Response]:
        return None, Response(
            content=json.dumps(
                {
                    "error": {
                        "message": "The prior operation result is temporarily unavailable.",
                        "type": "operation_replay_unavailable",
                    }
                }
            ),
            status_code=503,
            media_type="application/json",
        )

    try:
        settings = await get_response_cache_config()
    except Exception as exc:
        log.error(
            f"[response-cache] policy resolution failed ({type(exc).__name__}); failing open."
        )
        trace_decision(
            category="cache",
            action="skipped",
            result="failed",
            reason="policy_unavailable",
        )
        return replay_miss() if replay_required else (None, None)

    if not settings["enabled"]:
        trace_decision(
            category="cache",
            action="skipped",
            result="skipped",
            reason="feature_disabled",
        )
        return replay_miss() if replay_required else (None, None)
    if not _is_cacheable_request(body):
        trace_decision(
            category="cache",
            action="skipped",
            result="skipped",
            reason="not_eligible",
        )
        return replay_miss() if replay_required else (None, None)

    response_cache.default_ttl_seconds = settings["ttl_seconds"]
    response_cache.max_entries = settings["max_entries"]

    cache_key = generate_cache_key(str(body.get("model") or ""), body, stream=False)
    entry = await response_cache_coordinator.get(cache_key)
    if entry is None:
        trace_decision(
            category="cache",
            action="miss",
            result="miss",
            reason="cache_miss",
        )
        return replay_miss() if replay_required else (cache_key, None)

    content, media_type = entry
    log.info(f"[response-cache] HIT for model={body.get('model')}")
    trace_decision(
        category="cache",
        action="hit",
        result="hit",
        reason="cache_hit",
        model=str(body.get("model") or ""),
    )
    return cache_key, Response(
        content=content,
        status_code=200,
        media_type=media_type,
        headers={CACHE_HIT_HEADER: "hit"},
    )


async def store_response_cache(cache_key: Optional[str], response: Response) -> None:
    """Persist a successful upstream response for future exact-match hits."""
    if not cache_key or response is None or response.status_code != 200:
        return
    body_bytes = response.body
    if not body_bytes or len(body_bytes) > MAX_CACHEABLE_RESPONSE_BYTES:
        return
    stored = await response_cache_coordinator.set(
        cache_key,
        (bytes(body_bytes), response.media_type or "application/octet-stream"),
        response_cache.default_ttl_seconds,
    )
    if not stored:
        trace_decision(
            category="cache",
            action="skipped",
            result="failed",
            reason="coordination_unavailable",
        )
        return
    trace_decision(
        category="cache",
        action="stored",
        result="succeeded",
        reason="cache_stored",
    )
