"""Authenticated, ephemeral boundary around the public inference handlers."""

from __future__ import annotations

import asyncio
import base64
import json
import math
import threading
import time
from collections import OrderedDict, deque
from typing import Any, Literal

import config
from core.management_audit import ManagementMutation, record_classified_management_response
from core.models import (
    ClaudeRequest,
    GeminiRequest,
    OpenAIChatCompletionRequest,
    OpenAIResponsesRequest,
)
from core.playground_metrics import (
    bounded_playground_outcome,
    bounded_playground_protocol,
    record_playground_result,
    reset_playground_metrics_for_testing,
)
from core.protocol_contract import ProtocolTranslationError
from core.quality_decision import normalize_quality_decision
from core.request_trace_service import (
    RequestTraceCollector,
    bind_request_trace_collector,
)
from core.router.protocol_errors import ProtocolName, protocol_error_response
from core.router.stream_passthrough import close_async_iterator
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from log import log
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

router = APIRouter(prefix="/api/playground", tags=["playground"])

PLAYGROUND_REQUEST_SCHEMA_VERSION = "playground-request.v1"
PLAYGROUND_METADATA_SCHEMA_VERSION = "playground-metadata.v1"
PLAYGROUND_MAX_BODY_BYTES = 1024 * 1024
PLAYGROUND_MAX_RUNS = 20
PLAYGROUND_RATE_WINDOW_SECONDS = 60
PLAYGROUND_MAX_TRACKED_PRINCIPALS = 10_000
PLAYGROUND_DEFAULT_TIMEOUT_SECONDS = 60
PLAYGROUND_MAX_TIMEOUT_SECONDS = 120

PlaygroundProtocol = Literal[
    "openai_chat",
    "openai_responses",
    "anthropic_messages",
    "gemini",
]

_AUDIT_MUTATION = ManagementMutation(
    "inference.execute",
    "inference_route",
    ("no_change",),
    target_identifier="playground",
)


class PlaygroundRunRequest(BaseModel):
    """Closed wrapper around one native public-protocol request body."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["playground-request.v1"] = PLAYGROUND_REQUEST_SCHEMA_VERSION
    protocol: PlaygroundProtocol
    model: str = Field(min_length=1, max_length=256)
    stream: bool = False
    timeout_seconds: int = Field(
        default=PLAYGROUND_DEFAULT_TIMEOUT_SECONDS,
        ge=1,
        le=PLAYGROUND_MAX_TIMEOUT_SECONDS,
    )
    request: dict[str, Any]

    @model_validator(mode="after")
    def validate_boundary(self) -> "PlaygroundRunRequest":
        if self.model != self.model.strip() or any(ord(char) < 32 for char in self.model):
            raise ValueError("Playground model must be a trimmed printable identifier.")
        if "model" in self.request or "stream" in self.request:
            raise ValueError("Playground model and stream controls belong at the request boundary.")
        forbidden_request_fields = {"api_key", "authorization", "credential", "headers"}
        supplied_request_fields = {field.strip().casefold() for field in self.request}
        if forbidden_request_fields.intersection(supplied_request_fields):
            raise ValueError("Playground requests cannot supply credentials or transport headers.")
        encoded = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > PLAYGROUND_MAX_BODY_BYTES:
            raise ValueError("Playground request exceeds the 1 MiB limit.")
        return self


class PlaygroundRateLimiter:
    """Bounded process-local admission for the supported single-worker topology."""

    def __init__(self, *, max_runs: int, window_seconds: int, max_principals: int) -> None:
        if min(max_runs, window_seconds, max_principals) < 1:
            raise ValueError("Playground rate-limit settings must be positive.")
        self.max_runs = max_runs
        self.window_seconds = window_seconds
        self.max_principals = max_principals
        self._attempts: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def tracked_principals(self) -> int:
        with self._lock:
            return len(self._attempts)

    def admit(self, principal_reference: str, *, now: float | None = None) -> int:
        """Return zero when admitted, otherwise a bounded Retry-After value."""
        if not isinstance(principal_reference, str) or not principal_reference:
            raise ValueError("Playground principal reference is unavailable.")
        current = time.monotonic() if now is None else float(now)
        cutoff = current - self.window_seconds
        with self._lock:
            while self._attempts:
                key, attempts = next(iter(self._attempts.items()))
                while attempts and attempts[0] <= cutoff:
                    attempts.popleft()
                if attempts:
                    break
                self._attempts.popitem(last=False)

            attempts = self._attempts.get(principal_reference)
            if attempts is not None:
                while attempts and attempts[0] <= cutoff:
                    attempts.popleft()
                if not attempts:
                    del self._attempts[principal_reference]
                    attempts = None
            if attempts is None:
                if len(self._attempts) >= self.max_principals:
                    self._attempts.popitem(last=False)
                attempts = deque()
                self._attempts[principal_reference] = attempts
            else:
                self._attempts.move_to_end(principal_reference)

            if len(attempts) >= self.max_runs:
                return max(1, math.ceil(attempts[0] + self.window_seconds - current))
            attempts.append(current)
            return 0


_playground_limiter = PlaygroundRateLimiter(
    max_runs=PLAYGROUND_MAX_RUNS,
    window_seconds=PLAYGROUND_RATE_WINDOW_SECONDS,
    max_principals=PLAYGROUND_MAX_TRACKED_PRINCIPALS,
)


def reset_playground_runtime_for_testing() -> None:
    global _playground_limiter
    _playground_limiter = PlaygroundRateLimiter(
        max_runs=PLAYGROUND_MAX_RUNS,
        window_seconds=PLAYGROUND_RATE_WINDOW_SECONDS,
        max_principals=PLAYGROUND_MAX_TRACKED_PRINCIPALS,
    )
    reset_playground_metrics_for_testing()


def _public_protocol(protocol: PlaygroundProtocol) -> ProtocolName:
    if protocol == "anthropic_messages":
        return "anthropic"
    if protocol == "gemini":
        return "gemini"
    return "openai"


def _trace_protocol(run: PlaygroundRunRequest) -> str:
    if run.protocol == "gemini":
        return "gemini_stream" if run.stream else "gemini_generate"
    return run.protocol


def _validation_message(exc: ValidationError) -> str:
    error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in error.get("loc", ()))
    message = str(error.get("msg") or "The value is invalid.").strip()
    if message and not message.endswith((".", "!", "?")):
        message += "."
    return f"Invalid request field '{location}': {message}" if location else message


async def _dispatch_public_request(run: PlaygroundRunRequest) -> Response:
    payload = {**run.request, "model": run.model, "stream": run.stream}
    if run.protocol == "openai_chat":
        from core.router.primary.openai import chat_completions

        return await chat_completions(OpenAIChatCompletionRequest.model_validate(payload), "")
    if run.protocol == "openai_responses":
        from core.router.primary.responses import create_response

        return await create_response(OpenAIResponsesRequest.model_validate(payload), "")
    if run.protocol == "anthropic_messages":
        from core.router.primary.anthropic import messages

        return await messages(ClaudeRequest.model_validate(payload), "")

    payload.pop("model")
    payload.pop("stream")
    request = GeminiRequest.model_validate(payload)
    if run.stream:
        from core.router.primary.gemini import stream_generate_content

        return await stream_generate_content(request, run.model, "")
    from core.router.primary.gemini import generate_content

    return await generate_content(request, run.model, "")


async def _quality_snapshot() -> dict[str, str | int]:
    try:
        settings = await config.get_token_compression_config()
    except Exception:
        settings = None
    return normalize_quality_decision(settings)


def _metadata(
    run: PlaygroundRunRequest,
    collector: RequestTraceCollector,
    quality: dict[str, str | int],
    *,
    status_code: int,
    cancelled: bool = False,
) -> dict[str, Any]:
    trace = collector.complete(status_code=status_code, cancelled=cancelled)
    compression = next(
        (item for item in trace.decisions if item.category == "compression"),
        None,
    )
    attempts = sum(
        item.category == "upstream" and item.action == "attempted" for item in trace.decisions
    )
    fallbacks = sum(item.category == "fallback" for item in trace.decisions)
    selected_model = next(
        (item.model for item in reversed(trace.decisions) if item.provider and item.model),
        "",
    )
    return {
        "schema_version": PLAYGROUND_METADATA_SCHEMA_VERSION,
        "request_id": trace.request_id,
        "protocol": run.protocol,
        "requested_model": run.model,
        "outcome": trace.outcome,
        "status_code": status_code,
        "duration_ms": trace.duration_ms,
        "route": {
            "selected_provider": trace.selected_provider,
            "selected_model": selected_model,
            "attempts": attempts,
            "fallbacks": fallbacks,
        },
        "usage": {
            "input_tokens": trace.input_tokens,
            "output_tokens": trace.output_tokens,
            "total_tokens": trace.total_tokens,
            "cost_usd": trace.cost_usd,
        },
        "quality": {
            "profile": quality["quality_profile"],
            "policy_revision": quality["quality_policy_revision"],
            "compression_action": compression.action if compression else "unavailable",
            "compression_reason": compression.reason if compression else "unknown",
            "estimated_tokens_before": compression.original_tokens if compression else 0,
            "estimated_tokens_after": compression.final_tokens if compression else 0,
        },
    }


def _encode_metadata(metadata: dict[str, Any]) -> str:
    raw = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_playground_metadata(value: str) -> dict[str, Any]:
    """Decode the documented response header contract (also used by tests/tooling)."""
    padded = value + "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))


async def _record_audit(request: Request, status_code: int) -> None:
    try:
        await record_classified_management_response(
            _AUDIT_MUTATION,
            status_code=status_code,
            request_id=request.state.request_id,
            principal=getattr(request.state, "management_principal", None),
        )
    except Exception as exc:
        log.critical(
            "Playground audit append failed "
            f"(request_id={request.state.request_id}, error_type={type(exc).__name__})."
        )


def _log_result(
    *, request_id: str, protocol: str, outcome: str, status_code: int, duration_ms: int
) -> None:
    log.info(
        json.dumps(
            {
                "event": "playground_run_completed",
                "request_id": request_id,
                "entry_point": "management_playground",
                "protocol": bounded_playground_protocol(protocol),
                "outcome": bounded_playground_outcome(outcome),
                "status_code": status_code,
                "duration_ms": max(0, min(int(duration_ms), 120_000)),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _outcome(status_code: int) -> str:
    if status_code == 499:
        return "cancelled"
    if status_code in {408, 504}:
        return "timed_out"
    if status_code == 429:
        return "rate_limited"
    if status_code in {400, 413, 422}:
        return "invalid"
    if 200 <= status_code < 400:
        return "succeeded"
    return "failed"


async def _finalize(
    request: Request, run: PlaygroundRunRequest, status_code: int, started: float
) -> None:
    duration_ms = max(0, round((time.perf_counter() - started) * 1000))
    outcome = _outcome(status_code)
    record_playground_result(run.protocol, outcome, duration_ms)
    _log_result(
        request_id=request.state.request_id,
        protocol=run.protocol,
        outcome=outcome,
        status_code=status_code,
        duration_ms=duration_ms,
    )
    await _record_audit(request, status_code)


def _stream_error(protocol: ProtocolName, status_code: int, message: str) -> bytes:
    response = protocol_error_response(protocol, status_code, message)
    payload = json.loads(response.body)
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode("utf-8")


@router.post("/runs")
async def create_playground_run(
    run: PlaygroundRunRequest,
    request: Request,
    token: str = Depends(verify_panel_token),
) -> Response:
    """Execute a bounded request through the same handler used by public clients."""
    del token
    started = time.perf_counter()
    request_id = str(getattr(request.state, "request_id", "") or "playground")
    protocol = _public_protocol(run.protocol)
    try:
        retry_after = _playground_limiter.admit(
            str(getattr(request.state, "management_auth_reference", "") or "")
        )
    except ValueError:
        response = protocol_error_response(
            protocol, 503, "Playground admission is temporarily unavailable."
        )
        await _finalize(request, run, 503, started)
        return response
    if retry_after:
        response = protocol_error_response(
            protocol,
            429,
            "The Playground request rate limit was exceeded.",
            headers={"Retry-After": str(retry_after)},
        )
        await _finalize(request, run, 429, started)
        return response

    collector = RequestTraceCollector(request_id, _trace_protocol(run))
    quality: dict[str, str | int] = {
        "quality_profile": "unavailable",
        "quality_policy_revision": 0,
        "compression_reason": "unknown",
    }
    deadline = asyncio.get_running_loop().time() + run.timeout_seconds
    try:
        with bind_request_trace_collector(collector):
            quality, response = await asyncio.wait_for(
                _initial_dispatch(run), timeout=run.timeout_seconds
            )
    except ValidationError as exc:
        response = protocol_error_response(protocol, 400, _validation_message(exc))
        metadata = _metadata(run, collector, quality, status_code=400)
        response.headers["X-Polaris-Playground-Metadata"] = _encode_metadata(metadata)
        await _finalize(request, run, 400, started)
        return response
    except TimeoutError:
        response = protocol_error_response(protocol, 504, "The Playground request timed out.")
        metadata = _metadata(run, collector, quality, status_code=504)
        response.headers["X-Polaris-Playground-Metadata"] = _encode_metadata(metadata)
        await _finalize(request, run, 504, started)
        return response
    except asyncio.CancelledError:
        await _finalize(request, run, 499, started)
        raise
    except HTTPException as exc:
        detail = (
            exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        )
        response = protocol_error_response(
            protocol,
            exc.status_code,
            detail,
            headers=exc.headers,
        )
        metadata = _metadata(run, collector, quality, status_code=exc.status_code)
        response.headers["X-Polaris-Playground-Metadata"] = _encode_metadata(metadata)
        await _finalize(request, run, exc.status_code, started)
        return response
    except ProtocolTranslationError as exc:
        response = protocol_error_response(protocol, 502, str(exc))
        metadata = _metadata(run, collector, quality, status_code=502)
        response.headers["X-Polaris-Playground-Metadata"] = _encode_metadata(metadata)
        await _finalize(request, run, 502, started)
        return response
    except Exception as exc:
        log.error(
            "Playground dispatch failed with details withheld "
            f"(request_id={request_id}, error_type={type(exc).__name__})."
        )
        response = protocol_error_response(
            protocol, 500, "The Playground request could not be completed."
        )
        metadata = _metadata(run, collector, quality, status_code=500)
        response.headers["X-Polaris-Playground-Metadata"] = _encode_metadata(metadata)
        await _finalize(request, run, 500, started)
        return response

    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is None:
        metadata = _metadata(run, collector, quality, status_code=response.status_code)
        response.headers["X-Polaris-Playground-Metadata"] = _encode_metadata(metadata)
        await _finalize(request, run, response.status_code, started)
        return response

    async def bounded_stream():
        status_code = response.status_code
        cancelled = False
        try:
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError
                try:
                    with bind_request_trace_collector(collector):
                        chunk = await asyncio.wait_for(body_iterator.__anext__(), remaining)
                except StopAsyncIteration:
                    break
                yield chunk
            if any(
                decision.category == "upstream" and decision.result == "failed"
                for decision in collector.decisions
            ):
                status_code = 502
        except TimeoutError:
            status_code = 504
            with bind_request_trace_collector(collector):
                collector.record(
                    category="upstream",
                    action="failed",
                    result="failed",
                    reason="provider_error",
                    status_code=504,
                )
            yield _stream_error(protocol, 504, "The Playground request timed out.")
        except (asyncio.CancelledError, GeneratorExit):
            status_code = 499
            cancelled = True
            raise
        except Exception as exc:
            status_code = 502
            log.error(
                "Playground stream failed with details withheld "
                f"(request_id={request_id}, error_type={type(exc).__name__})."
            )
            yield _stream_error(protocol, 502, "The upstream stream could not be completed.")
        finally:
            try:
                await close_async_iterator(body_iterator)
            except (Exception, asyncio.CancelledError) as exc:
                log.warning(
                    "Playground stream cleanup failed "
                    f"(request_id={request_id}, error_type={type(exc).__name__})."
                )
            metadata = _metadata(
                run,
                collector,
                quality,
                status_code=status_code,
                cancelled=cancelled,
            )
            if not cancelled:
                yield (
                    "event: polaris.playground.metadata\n"
                    f"data: {json.dumps(metadata, ensure_ascii=False, separators=(',', ':'))}\n\n"
                ).encode("utf-8")
            await _finalize(request, run, status_code, started)

    response.body_iterator = bounded_stream()
    if "content-length" in response.headers:
        del response.headers["content-length"]
    response.headers["X-Polaris-Playground-Request-ID"] = request_id
    return response


async def _initial_dispatch(
    run: PlaygroundRunRequest,
) -> tuple[dict[str, str | int], Response]:
    quality = await _quality_snapshot()
    response = await _dispatch_public_request(run)
    return quality, response
