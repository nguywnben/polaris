import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config import (
    get_auto_disable_enabled,
    get_auto_disable_error_codes,
    get_retry_429_enabled,
    get_retry_429_interval,
    get_retry_429_max_retries,
)
from core.credential_manager import CredentialManager
from core.quality_decision import normalize_quality_decision
from core.request_context import (
    get_api_key_id,
    get_request_elapsed_ms,
    get_request_id,
    get_virtual_key_reservation_id,
)
from core.request_trace_service import trace_decision
from core.router.stream_passthrough import close_async_iterator
from core.usage_stats import normalize_token_usage, record_call
from core.virtual_keys import virtual_key_manager
from fastapi import Response
from log import log

UNASSIGNED_USAGE_FILENAME = "__gateway_unassigned__.json"
MODEL_NOT_FOUND_COOLDOWN_SECONDS = 2 * 60
RETRYABLE_UPSTREAM_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
MAX_COLLECTED_STREAM_BYTES = 8 * 1024 * 1024


def _generation_trace_metadata(
    *,
    provider: str,
    latency_ms: int,
    tokens: Dict[str, int],
    request_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    decision = normalize_quality_decision(request_metrics)
    return {
        "provider": provider,
        "latency_ms": latency_ms,
        "cached_tokens": tokens["cached_tokens"],
        "reasoning_tokens": tokens["reasoning_tokens"],
        **decision,
    }


def _schedule_trace_export(
    *,
    model_name: str,
    provider: str,
    token_usage: Optional[Dict[str, Any]],
    latency_ms: int,
    request_metrics: Optional[Dict[str, Any]] = None,
) -> None:
    """Export a generation trace to Langfuse without blocking the response.

    Prompt/response bodies are intentionally NOT exported (privacy): only
    model, provider, token counts, and latency leave the gateway.
    """

    async def _export() -> None:
        try:
            from config import get_telemetry_config
            from core.telemetry_exporter import TelemetryExporter

            settings = await get_telemetry_config()
            if not settings["enabled"]:
                return
            exporter = TelemetryExporter(
                langfuse_public_key=settings["langfuse_public_key"],
                langfuse_secret_key=settings["langfuse_secret_key"],
                langfuse_host=settings["langfuse_host"],
            )
            tokens = normalize_token_usage(token_usage)
            await exporter.export_trace_to_langfuse(
                trace_id=get_request_id() or "unknown",
                name="gateway.generation",
                model=model_name,
                input_data=None,
                output_data=None,
                latency_ms=float(latency_ms),
                prompt_tokens=tokens["input_tokens"],
                completion_tokens=tokens["output_tokens"],
                metadata=_generation_trace_metadata(
                    provider=provider,
                    latency_ms=latency_ms,
                    tokens=tokens,
                    request_metrics=request_metrics,
                ),
            )
        except Exception as exc:
            log.debug(f"[telemetry] trace export failed: {exc}")

    try:
        asyncio.get_running_loop()
        asyncio.create_task(_export())
    except RuntimeError:
        # No running loop (synchronous test context) - skip silently.
        pass


async def check_should_auto_disable(status_code: int) -> bool:
    return await get_auto_disable_enabled() and status_code in await get_auto_disable_error_codes()


async def handle_auto_disable(
    credential_manager: CredentialManager,
    status_code: int,
    credential_name: str,
    mode: str = "code_assist",
) -> None:
    if credential_manager and credential_name:
        log.warning(
            f"[{mode.upper()} AUTO_DISABLE] Status {status_code} triggers auto-disable for credential: {credential_name}"
        )
        await credential_manager.set_cred_disabled(credential_name, True, mode=mode)


async def handle_error_with_retry(
    credential_manager: CredentialManager,
    status_code: int,
    credential_name: str,
    retry_enabled: bool,
    attempt: int,
    max_retries: int,
    retry_interval: float,
    mode: str = "code_assist",
) -> bool:

    should_auto_disable = await check_should_auto_disable(status_code)

    if should_auto_disable:
        await handle_auto_disable(credential_manager, status_code, credential_name, mode)

        if retry_enabled and attempt < max_retries:
            log.info(
                f"[{mode.upper()} RETRY] Retrying with next credential after auto-disable "
                f"(status {status_code}, attempt {attempt + 1}/{max_retries})"
            )
            await asyncio.sleep(retry_interval)
            trace_decision(
                category="retry",
                action="scheduled",
                result="succeeded",
                reason="credential_switched",
                attempt=attempt + 1,
                status_code=status_code,
            )
            return True
        return False

    if status_code in RETRYABLE_UPSTREAM_STATUS_CODES and retry_enabled and attempt < max_retries:
        log.info(
            f"[{mode.upper()} RETRY] {status_code} error encountered, retrying "
            f"(attempt {attempt + 1}/{max_retries})"
        )
        await asyncio.sleep(retry_interval)
        trace_decision(
            category="retry",
            action="scheduled",
            result="succeeded",
            reason="retryable_status",
            attempt=attempt + 1,
            status_code=status_code,
        )
        return True

    return False


async def get_retry_config() -> Dict[str, Any]:
    return {
        "retry_enabled": await get_retry_429_enabled(),
        "max_retries": await get_retry_429_max_retries(),
        "retry_interval": await get_retry_429_interval(),
    }


async def _record_success_usage(
    *,
    filename: str,
    model_name: str,
    provider: str,
    status_code: int,
    token_usage: Optional[Dict[str, Any]],
    request_metrics: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Persist one success and atomically replace its quota estimate with actual usage."""
    api_key_id = get_api_key_id()
    reservation_id = get_virtual_key_reservation_id()
    tokens = normalize_token_usage(token_usage)
    metrics = dict(request_metrics or {})
    metrics.setdefault("latency_ms", get_request_elapsed_ms())
    actual_cost_usd = 0.0
    cost_override_usd = None
    durable_cost_recorded = False
    actual_cost_calculated = not bool(api_key_id)
    durable_reservation_id = (
        reservation_id if virtual_key_manager.is_durable_reservation(reservation_id) else ""
    )
    try:
        if api_key_id:
            actual_cost_usd = await virtual_key_manager.calculate_actual_cost(
                api_key_id,
                model=model_name,
                provider=provider,
                token_usage=token_usage,
            )
            cost_override_usd = actual_cost_usd
            actual_cost_calculated = True
        durable_cost_recorded = bool(
            await record_call(
                filename,
                model=model_name,
                provider=provider,
                status_code=status_code,
                success=True,
                token_usage=token_usage,
                request_metrics=metrics,
                request_id=get_request_id(),
                api_key_id=api_key_id,
                cost_override_usd=cost_override_usd,
                durable_reservation_id=durable_reservation_id,
            )
        )
    except Exception as exc:
        log.error(f"Failed to record successful usage (error_type={type(exc).__name__}).")

    if reservation_id and actual_cost_calculated:
        try:
            result = await virtual_key_manager.commit_reservation(
                reservation_id,
                actual_tokens=tokens["total_tokens"],
                actual_cost_usd=actual_cost_usd,
                durable_cost_recorded=durable_cost_recorded,
            )
            if result.overspent:
                log.warning("[virtual-keys] actual usage exceeded reserved capacity")
        except Exception as exc:
            log.error(f"Failed to commit quota reservation (error_type={type(exc).__name__}).")
    trace_decision(
        category="usage",
        action="recorded",
        result="succeeded" if durable_cost_recorded else "failed",
        reason="usage_recorded",
        provider=provider,
        model=model_name,
        latency_ms=min(86_400_000, max(0, int(metrics.get("latency_ms") or 0))),
        input_tokens=tokens["input_tokens"],
        output_tokens=tokens["output_tokens"],
        cached_tokens=tokens["cached_tokens"],
        reasoning_tokens=tokens["reasoning_tokens"],
        cost_usd=actual_cost_usd,
    )
    return metrics


async def record_api_call_success(
    credential_manager: CredentialManager,
    credential_name: str,
    mode: str = "code_assist",
    model_name: Optional[str] = None,
    token_usage: Optional[Dict[str, Any]] = None,
    status_code: int = 200,
    request_metrics: Optional[Dict[str, Any]] = None,
    provider: Optional[str] = None,
) -> None:
    if credential_manager and credential_name:
        request_metrics, _ = await asyncio.gather(
            _record_success_usage(
                filename=credential_name,
                model_name=model_name or "",
                provider=provider or mode,
                status_code=status_code,
                token_usage=token_usage,
                request_metrics=request_metrics,
            ),
            credential_manager.record_api_call_result(
                credential_name, True, mode=mode, model_name=model_name
            ),
        )

        trace_decision(
            category="upstream",
            action="succeeded",
            result="succeeded",
            reason="completed",
            provider=provider or mode,
            model=model_name or "",
            status_code=status_code,
            latency_ms=min(
                86_400_000,
                max(0, int(request_metrics.get("latency_ms") or 0)),
            ),
        )

        _schedule_trace_export(
            model_name=model_name or "",
            provider=provider or mode,
            token_usage=token_usage,
            latency_ms=int(request_metrics.get("latency_ms") or 0),
            request_metrics=request_metrics,
        )


async def record_api_call_error(
    credential_manager: CredentialManager,
    credential_name: str,
    status_code: int,
    cooldown_until: Optional[float] = None,
    mode: str = "code_assist",
    model_name: Optional[str] = None,
    error_message: Optional[str] = None,
    provider: Optional[str] = None,
) -> None:
    if credential_manager and credential_name:
        try:
            await record_call(
                credential_name,
                model=model_name or "",
                provider=provider or mode,
                status_code=status_code,
                success=False,
                token_usage=None,
                request_id=get_request_id(),
                api_key_id=get_api_key_id(),
            )
        except Exception as e:
            log.error(f"Failed to record failed usage for {credential_name}: {e}")

        await credential_manager.record_api_call_result(
            credential_name,
            False,
            status_code,
            cooldown_until=cooldown_until,
            mode=mode,
            model_name=model_name,
            error_message=error_message,
        )
        trace_decision(
            category="upstream",
            action="failed",
            result="failed",
            reason="rate_limited" if status_code == 429 else "provider_error",
            provider=provider or mode,
            model=model_name or "",
            status_code=status_code,
        )


async def record_model_route_miss(
    credential_manager: CredentialManager,
    credential_name: str,
    *,
    model_name: str,
    provider: str,
) -> None:
    """Record and briefly suppress an unsupported credential-model route."""
    try:
        cooldown_until = datetime.now(timezone.utc).timestamp() + MODEL_NOT_FOUND_COOLDOWN_SECONDS
        await credential_manager.set_model_cooldown(
            credential_name,
            model_name,
            cooldown_until,
            mode="primary",
        )
    except Exception as exc:
        log.error(f"Failed to set model cooldown for {credential_name}: {exc}")

    try:
        await record_call(
            credential_name,
            model=model_name,
            provider=provider,
            status_code=404,
            success=False,
            token_usage=None,
            request_id=get_request_id(),
        )
    except Exception as exc:
        log.error(f"Failed to record model route miss for {credential_name}: {exc}")
    finally:
        trace_decision(
            category="cooldown",
            action="applied",
            result="succeeded",
            reason="model_cooldown",
            provider=provider,
            model=model_name,
            status_code=404,
        )
        await credential_manager.release_credential(credential_name, mode="primary")


async def record_unassigned_api_call_error(
    *,
    status_code: int = 500,
    mode: str = "primary",
    model_name: Optional[str] = None,
    reason: str = "no_candidate",
) -> None:
    """Record a gateway-level request failure that cannot be attributed to a credential."""
    try:
        await record_call(
            UNASSIGNED_USAGE_FILENAME,
            model=model_name or "",
            provider=mode,
            status_code=status_code,
            success=False,
            token_usage=None,
            request_id=get_request_id(),
        )
    except Exception as e:
        log.error(f"Failed to record unassigned usage failure: {e}")
    trace_decision(
        category="routing",
        action="unavailable",
        result="failed",
        reason=(
            reason
            if reason in {"no_candidate", "coordination_unavailable"}
            else "coordination_unavailable"
        ),
        model=model_name or "",
        status_code=status_code,
    )


async def record_unassigned_api_call_success(
    *,
    mode: str,
    model_name: str,
    token_usage: Optional[Dict[str, Any]],
    status_code: int = 200,
    request_metrics: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist unattributed success usage and settle any virtual-key reservation."""
    await _record_success_usage(
        filename=UNASSIGNED_USAGE_FILENAME,
        model_name=model_name,
        provider=mode,
        status_code=status_code,
        token_usage=token_usage,
        request_metrics=request_metrics,
    )
    trace_decision(
        category="upstream",
        action="succeeded",
        result="succeeded",
        reason="completed",
        provider=mode,
        model=model_name,
        status_code=status_code,
    )


async def record_response_cache_hit(*, model_name: str, status_code: int = 200) -> None:
    """Persist one non-billable cache success and settle its quota reservation."""

    await _record_success_usage(
        filename=UNASSIGNED_USAGE_FILENAME,
        model_name=model_name,
        provider="response_cache",
        status_code=status_code,
        token_usage=None,
        request_metrics=None,
    )


async def parse_and_log_cooldown(error_text: str, mode: str = "code_assist") -> Optional[float]:
    try:
        error_data = json.loads(error_text)
        cooldown_until = parse_quota_reset_timestamp(error_data)
        if cooldown_until:
            log.info(
                f"[{mode.upper()}] Quota cooldown detected: "
                f"{datetime.fromtimestamp(cooldown_until, timezone.utc).isoformat()}"
            )
            trace_decision(
                category="cooldown",
                action="applied",
                result="succeeded",
                reason="quota_cooldown",
            )
            return cooldown_until
    except (AttributeError, TypeError, ValueError) as parse_err:
        log.debug(f"[{mode.upper()}] failed to parse cooldown time ({type(parse_err).__name__})")
    return None


async def collect_streaming_response(stream_generator) -> Response:

    merged_response = {
        "response": {
            "candidates": [
                {
                    "content": {"parts": [], "role": "model"},
                    "finishReason": None,
                    "safetyRatings": [],
                    "citationMetadata": None,
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 0,
                "candidatesTokenCount": 0,
                "totalTokenCount": 0,
            },
        }
    }

    collected_text = []
    collected_thought_text = []
    collected_other_parts = []
    collected_tool_parts_count = 0
    has_data = False
    line_count = 0
    done_marker_received = False
    collected_bytes = 0

    log.debug("[STREAM COLLECTOR] Starting to collect streaming response")

    try:
        async for line in stream_generator:
            line_count += 1

            if isinstance(line, Response):
                log.debug(
                    f"[STREAM COLLECTOR] Received error response, status code: {line.status_code}"
                )
                return line

            if isinstance(line, bytes):
                line_str = line.decode("utf-8", errors="ignore")
                log.debug(
                    f"[STREAM COLLECTOR] Processing bytes line {line_count}: {line_str[:200] if line_str else 'empty'}"
                )
            elif isinstance(line, str):
                line_str = line
                log.debug(
                    f"[STREAM COLLECTOR] Processing line {line_count}: {line_str[:200] if line_str else 'empty'}"
                )
            else:
                log.debug(f"[STREAM COLLECTOR] Skipping non-string/bytes line: {type(line)}")
                continue

            collected_bytes += len(line_str.encode("utf-8"))
            if collected_bytes > MAX_COLLECTED_STREAM_BYTES:
                trace_decision(
                    category="upstream",
                    action="failed",
                    result="failed",
                    reason="provider_error",
                    status_code=502,
                )
                return Response(
                    content=json.dumps(
                        {"error": "The upstream streaming response exceeded the collection limit."}
                    ),
                    status_code=502,
                    media_type="application/json",
                )

            if not line_str.startswith("data: "):
                log.debug(
                    f"[STREAM COLLECTOR] Skipping line without 'data: ' prefix: {line_str[:100]}"
                )
                continue

            raw = line_str[6:].strip()
            if done_marker_received:
                log.debug("[STREAM COLLECTOR] Ignoring data after the [DONE] marker")
                continue
            if raw == "[DONE]":
                log.debug("[STREAM COLLECTOR] Received [DONE] marker")
                # Drain the upstream generator so its success accounting and
                # credential-lease cleanup run before this response returns.
                done_marker_received = True
                continue

            try:
                log.debug(f"[STREAM COLLECTOR] Parsing JSON: {raw[:200]}")
                chunk = json.loads(raw)
                has_data = True
                log.debug(
                    f"[STREAM COLLECTOR] Chunk keys: {chunk.keys() if isinstance(chunk, dict) else type(chunk)}"
                )

                response_obj = chunk.get("response", {})
                if not response_obj:
                    log.debug("[STREAM COLLECTOR] No 'response' key in chunk, trying direct access")
                    response_obj = chunk

                candidates = response_obj.get("candidates", [])
                log.debug(f"[STREAM COLLECTOR] Found {len(candidates)} candidates")
                if not candidates:
                    log.debug(
                        f"[STREAM COLLECTOR] No candidates in chunk, chunk structure: {list(chunk.keys()) if isinstance(chunk, dict) else type(chunk)}"
                    )
                    continue

                candidate = candidates[0]

                content = candidate.get("content", {})
                parts = content.get("parts", [])
                log.debug(f"[STREAM COLLECTOR] Processing {len(parts)} parts from candidate")

                for part in parts:
                    if not isinstance(part, dict):
                        continue

                    if (
                        "functionCall" in part
                        or "functionResponse" in part
                        or "function_call" in part
                    ):
                        collected_other_parts.append(part)
                        collected_tool_parts_count += 1
                        log.debug(f"[STREAM COLLECTOR] Collected tool part: {list(part.keys())}")
                        continue

                    text = part.get("text", "")
                    if text:
                        if part.get("thought", False):
                            collected_thought_text.append(text)
                            log.debug(f"[STREAM COLLECTOR] Collected thought text: {text[:100]}")
                        else:
                            collected_text.append(text)
                            log.debug(f"[STREAM COLLECTOR] Collected regular text: {text[:100]}")

                    elif (
                        "inlineData" in part
                        or "fileData" in part
                        or "executableCode" in part
                        or "codeExecutionResult" in part
                    ):
                        collected_other_parts.append(part)
                        log.debug(
                            f"[STREAM COLLECTOR] Collected non-text part: {list(part.keys())}"
                        )

                if candidate.get("finishReason"):
                    merged_response["response"]["candidates"][0]["finishReason"] = candidate[
                        "finishReason"
                    ]

                if candidate.get("safetyRatings"):
                    merged_response["response"]["candidates"][0]["safetyRatings"] = candidate[
                        "safetyRatings"
                    ]

                if candidate.get("citationMetadata"):
                    merged_response["response"]["candidates"][0]["citationMetadata"] = candidate[
                        "citationMetadata"
                    ]

                usage = response_obj.get("usageMetadata", {})
                if usage:
                    merged_response["response"]["usageMetadata"].update(usage)

            except json.JSONDecodeError as e:
                log.debug(f"[stream collector] failed to parse JSON chunk: {e}")
                continue
            except Exception as e:
                log.debug(f"[STREAM COLLECTOR] Error processing chunk: {e}")
                continue

    except Exception as e:
        log.error(f"[STREAM COLLECTOR] Error collecting stream after {line_count} lines: {e}")
        trace_decision(
            category="upstream",
            action="failed",
            result="failed",
            reason="provider_error",
            status_code=502,
        )
        return Response(
            content=json.dumps({"error": "Failed to collect the upstream streaming response."}),
            status_code=502,
            media_type="application/json",
        )
    finally:
        await close_async_iterator(stream_generator)

    log.debug(
        f"[STREAM COLLECTOR] Finished iteration, has_data={has_data}, line_count={line_count}"
    )

    if not has_data:
        log.error(f"[STREAM COLLECTOR] No data collected from stream after {line_count} lines")
        return Response(
            content=json.dumps({"error": "No data collected from stream"}),
            status_code=500,
            media_type="application/json",
        )

    final_parts = []

    if collected_thought_text:
        final_parts.append({"text": "".join(collected_thought_text), "thought": True})

    if collected_text:
        final_parts.append({"text": "".join(collected_text)})

    final_parts.extend(collected_other_parts)

    if not final_parts:
        final_parts.append({"text": ""})

    merged_response["response"]["candidates"][0]["content"]["parts"] = final_parts

    log.debug(
        f"[STREAM COLLECTOR] Collected {len(collected_text)} text chunks, "
        f"{len(collected_thought_text)} thought chunks, {len(collected_other_parts)} other parts "
        f"(tool parts: {collected_tool_parts_count})"
    )

    if "response" in merged_response and "candidates" not in merged_response:
        log.debug("[STREAM COLLECTOR] Unwrapping response")
        merged_response = merged_response["response"]

    return Response(
        content=json.dumps(merged_response, ensure_ascii=False).encode("utf-8"),
        status_code=200,
        headers={},
        media_type="application/json",
    )


RESOURCE_EXHAUSTED_COOLDOWN_HOURS = 4


def parse_quota_reset_timestamp(error_response: dict) -> Optional[float]:
    try:
        error_obj = error_response.get("error", {})
        details = error_obj.get("details", [])

        for detail in details:
            if detail.get("@type") == "type.googleapis.com/google.rpc.ErrorInfo":
                reset_timestamp_str = detail.get("metadata", {}).get("quotaResetTimeStamp")

                if reset_timestamp_str:
                    if reset_timestamp_str.endswith("Z"):
                        reset_timestamp_str = reset_timestamp_str.replace("Z", "+00:00")

                    reset_dt = datetime.fromisoformat(reset_timestamp_str)
                    if reset_dt.tzinfo is None:
                        reset_dt = reset_dt.replace(tzinfo=timezone.utc)

                    return reset_dt.astimezone(timezone.utc).timestamp()

        if (
            error_obj.get("status") == "RESOURCE_EXHAUSTED"
            and error_obj.get("message") == "Resource has been exhausted (e.g. check quota)."
        ):
            import time

            cooldown_until = time.time() + RESOURCE_EXHAUSTED_COOLDOWN_HOURS * 3600
            return cooldown_until

        return None

    except (AttributeError, TypeError, ValueError):
        return None
