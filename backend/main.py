import asyncio
import os
import re
import sys
import uuid
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app_version import get_application_version
from config import get_server_host, get_server_port, trust_proxy_headers_enabled

# Import managers and utilities
from core.audit_service import close_audit_service, get_audit_service, initialize_audit_service
from core.credential_manager import credential_manager
from core.dynamic_pricing import (
    dynamic_pricing_service,
    pricing_sync_enabled,
    run_dynamic_pricing_sync_loop,
)
from core.health import router as health_router
from core.http_server import configure_hypercorn
from core.httpx_client import http_client
from core.i18n import LocalizedJSONResponse, locale_context, resolve_locale
from core.identity import (
    close_oidc_login_service,
    close_session_service,
    initialize_session_service,
)
from core.keep_alive import keep_alive_service
from core.management_audit import (
    classify_management_denial,
    classify_management_mutation,
    record_classified_management_response,
)
from core.metrics import router as metrics_router
from core.model_pool import model_catalog_service
from core.otel_exporter import run_otel_export_loop
from core.panel import router as panel_router
from core.panel.playground import PLAYGROUND_MAX_BODY_BYTES
from core.protocol_contract import ProtocolTranslationError
from core.request_context import request_scope
from core.request_limits import RequestBodyLimitMiddleware, get_max_request_body_bytes
from core.request_trace import classify_request_protocol
from core.request_trace_service import (
    bind_request_trace_collector,
    close_request_trace_service,
    get_request_trace_service,
    initialize_request_trace_service,
    request_trace_scope,
)
from core.router.primary.anthropic import router as primary_anthropic_router
from core.router.primary.gemini import router as primary_gemini_router
from core.router.primary.model_list import router as primary_model_list_router

# Import all routers
from core.router.primary.openai import router as primary_openai_router
from core.router.primary.responses import router as primary_responses_router
from core.router.protocol_errors import protocol_error_response, protocol_for_path
from core.router.stream_passthrough import close_async_iterator
from core.router.vertex.gemini import router as vertex_gemini_router
from core.router.vertex.model_list import router as vertex_model_list_router
from core.router.vertex.openai import router as vertex_openai_router
from core.runtime_lifecycle import (
    close_runtime,
    get_runtime_session_kwargs,
    initialize_runtime,
)
from core.storage_adapter import close_storage_adapter
from core.task_manager import create_managed_task, shutdown_all_tasks
from core.telemetry_policy import get_telemetry_policy
from core.usage_ledger_service import (
    close_usage_ledger_service,
    initialize_usage_ledger_service,
)
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from log import configure_logging, log
from paths import FRONTEND_DIR
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


async def _prewarm_model_catalog() -> None:
    """Refresh provider models without delaying readiness or first traffic."""
    try:
        await model_catalog_service.get_catalog()
        log.info("Model catalog prewarm completed.")
    except Exception as exc:
        # Discovery is best-effort at startup; the request path still has the
        # normal retry/fallback behavior if an upstream is temporarily down.
        log.warning(f"Model catalog prewarm failed ({type(exc).__name__}).")


def _parse_csv_env(name: str) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _get_worker_count() -> int:
    raw_value = os.getenv("WORKERS", "1").strip()
    try:
        workers = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("WORKERS must be the integer 1.") from exc
    if workers != 1:
        raise RuntimeError(
            "Polaris supports WORKERS=1 only. "
            "Credential reservations, cooldowns, and usage aggregation are not yet coordinated "
            "across multiple worker processes."
        )
    return workers


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting the Polaris service.")

    try:
        import config

        await config.init_config()
        log_config = await config.get_log_config()
        configure_logging(
            log_config["level"],
            log_config["max_mb"],
            log_config["backup_count"],
        )
        log.info("Configuration cache initialized.")
    except Exception as e:
        log.critical(f"Configuration cache initialization failed ({type(e).__name__}).")
        raise RuntimeError("Configuration initialization failed.") from e

    try:
        await initialize_runtime()
        log.info("Process-local runtime lifecycle initialized.")
    except Exception as e:
        log.critical(f"Runtime coordination initialization failed: {type(e).__name__}")
        await close_storage_adapter()
        raise RuntimeError("Runtime coordination initialization failed.") from e

    try:
        await credential_manager._get_or_create()
        log.info("Credential manager initialized.")
    except Exception as e:
        log.critical(f"Credential manager initialization failed ({type(e).__name__}).")
        await close_runtime()
        await close_storage_adapter()
        raise RuntimeError("Credential storage initialization failed.") from e

    try:
        await initialize_audit_service()
        log.info("Durable audit service initialized.")
    except Exception as e:
        log.critical(f"Audit service initialization failed: {type(e).__name__}")
        await credential_manager.close()
        await close_runtime()
        await close_storage_adapter()
        raise RuntimeError("Audit service initialization failed.") from e

    try:
        await initialize_session_service(**get_runtime_session_kwargs())
        log.info("Revocable management session service initialized.")
    except Exception as e:
        log.critical(f"Session service initialization failed: {type(e).__name__}")
        await close_audit_service()
        await credential_manager.close()
        await close_runtime()
        await close_storage_adapter()
        raise RuntimeError("Session service initialization failed.") from e

    try:
        await initialize_request_trace_service()
        log.info("Durable request trace service initialized.")
    except Exception as e:
        log.critical(f"Request trace service initialization failed: {type(e).__name__}")
        await close_session_service()
        await close_audit_service()
        await credential_manager.close()
        await close_runtime()
        await close_storage_adapter()
        raise RuntimeError("Request trace service initialization failed.") from e

    try:
        await initialize_usage_ledger_service()
        log.info("Durable usage ledger service initialized.")
    except Exception as e:
        log.critical(f"Usage ledger service initialization failed: {type(e).__name__}")
        await close_request_trace_service()
        await close_session_service()
        await close_audit_service()
        await credential_manager.close()
        await close_runtime()
        await close_storage_adapter()
        raise RuntimeError("Usage ledger service initialization failed.") from e

    dynamic_pricing_service.load_cache()
    if pricing_sync_enabled():
        create_managed_task(run_dynamic_pricing_sync_loop(), name="dynamic-pricing-sync")
        log.info("Dynamic model pricing synchronization enabled.")

    try:
        telemetry_policy = get_telemetry_policy()
        if telemetry_policy.otel_enabled:
            create_managed_task(
                run_otel_export_loop(telemetry_policy), name="otel-aggregate-export"
            )
            log.info("Content-free OpenTelemetry aggregate export enabled.")
    except Exception as e:
        log.critical(f"External telemetry configuration failed: {type(e).__name__}")
        await close_usage_ledger_service()
        await close_request_trace_service()
        await close_session_service()
        await close_audit_service()
        await credential_manager.close()
        await close_runtime()
        await close_storage_adapter()
        raise RuntimeError("External telemetry configuration failed.") from e

    try:
        await keep_alive_service.start()
    except Exception as e:
        log.error(f"Keep-alive service startup failed ({type(e).__name__}).")

    create_managed_task(_prewarm_model_catalog(), name="model-catalog-prewarm")
    log.info("Model catalog prewarm scheduled.")

    try:
        yield
    finally:
        log.info("Starting Polaris shutdown.")

        try:
            await keep_alive_service.stop()
        except Exception as e:
            log.error(f"Keep-alive service shutdown failed ({type(e).__name__}).")

        try:
            await shutdown_all_tasks(timeout=10.0)
            log.info("All asynchronous tasks have been shut down.")
        except Exception as e:
            log.error(f"Asynchronous task shutdown failed ({type(e).__name__}).")

        try:
            await close_usage_ledger_service()
            log.info("Usage ledger service closed.")
        except Exception as e:
            log.error(f"Usage ledger shutdown failed ({type(e).__name__}).")

        try:
            await close_request_trace_service()
            log.info("Request trace service closed.")
        except Exception as e:
            log.error(f"Request trace shutdown failed ({type(e).__name__}).")

        try:
            await close_oidc_login_service()
            log.info("OIDC login service closed.")
        except Exception as e:
            log.error(f"OIDC login shutdown failed ({type(e).__name__}).")

        try:
            await close_session_service()
            log.info("Management session service closed.")
        except Exception as e:
            log.error(f"Session service shutdown failed ({type(e).__name__}).")

        try:
            await close_audit_service()
            log.info("Audit service closed.")
        except Exception as e:
            log.error(f"Audit service shutdown failed ({type(e).__name__}).")

        try:
            await credential_manager.close()
            log.info("Credential manager closed.")
        except Exception as e:
            log.error(f"Credential manager shutdown failed ({type(e).__name__}).")

        try:
            await close_runtime()
            log.info("Process-local runtime lifecycle closed.")
        except Exception as e:
            log.error(f"Process-local runtime shutdown failed ({type(e).__name__}).")

        try:
            await http_client.close()
            log.info("Outbound HTTP clients closed.")
        except Exception as e:
            log.error(f"Outbound HTTP client shutdown failed ({type(e).__name__}).")

        try:
            await close_storage_adapter()
            log.info("Storage adapter closed.")
        except Exception as e:
            log.error(f"Storage adapter shutdown failed ({type(e).__name__}).")

        log.info("Polaris stopped.")


app = FastAPI(
    title="Polaris",
    description="Universal AI router with smart auto-fallback, token-aware request cleanup, usage visibility, and seamless format translation.",
    version=get_application_version(),
    lifespan=lifespan,
    default_response_class=LocalizedJSONResponse,
)


def _validation_error_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "The request payload is invalid."
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    message = str(first.get("msg") or "The value is invalid.").strip()
    if message and not message.endswith((".", "!", "?")):
        message += "."
    if location:
        return f"Invalid request field '{location}': {message}"
    return f"Invalid request: {message}"


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    protocol = protocol_for_path(request.url.path)
    if protocol:
        detail = (
            exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        )
        return protocol_error_response(
            protocol,
            exc.status_code,
            detail,
            headers=exc.headers,
        )
    return LocalizedJSONResponse(
        {"detail": exc.detail},
        status_code=exc.status_code,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_exception(request: Request, exc: RequestValidationError):
    protocol = protocol_for_path(request.url.path)
    message = _validation_error_message(exc)
    if protocol:
        return protocol_error_response(protocol, 400, message)
    return LocalizedJSONResponse({"detail": message}, status_code=422)


@app.exception_handler(ProtocolTranslationError)
async def handle_protocol_translation_exception(request: Request, exc: ProtocolTranslationError):
    protocol = protocol_for_path(request.url.path)
    if protocol:
        return protocol_error_response(protocol, 502, str(exc))
    return LocalizedJSONResponse({"detail": str(exc)}, status_code=502)


cors_origins = _parse_csv_env("CORS_ORIGINS")
cors_origin_regex = os.getenv("CORS_ORIGIN_REGEX", "").strip() or None
cors_allow_credentials = bool((cors_origins and "*" not in cors_origins) or cors_origin_regex)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Accept-Language",
        "Content-Type",
        "x-api-key",
        "x-goog-api-key",
        "x-anthropic-auth-token",
        "anthropic-auth-token",
        "access_token",
        "x-polaris-compression",
    ],
    expose_headers=["X-Request-ID", "Retry-After"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_body_bytes=get_max_request_body_bytes(),
    path_limits={"/api/playground/runs": PLAYGROUND_MAX_BODY_BYTES},
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    supplied_request_id = request.headers.get("x-request-id", "").strip()
    request_id = (
        supplied_request_id
        if _REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
        else uuid.uuid4().hex
    )
    request.state.request_id = request_id
    management_mutation = classify_management_mutation(
        request.method,
        request.scope.get("path", request.url.path),
    )
    localize_console = request.url.path.startswith("/api/") or request.url.path == "/callback"
    locale = resolve_locale(request.headers.get("accept-language"))
    protocol = classify_request_protocol(
        request.method,
        request.scope.get("path", request.url.path),
    )
    trace_context = request_trace_scope(request_id, protocol) if protocol else nullcontext(None)
    with (
        request_scope(request_id),
        locale_context(locale, enabled=localize_console),
        trace_context as trace_collector,
    ):
        try:
            response = await call_next(request)
        except BaseException as request_error:
            reservation_id = getattr(request.state, "virtual_key_reservation_id", "")
            if reservation_id:
                request.state.virtual_key_reservation_id = ""
                from core.virtual_keys import virtual_key_manager

                try:
                    await virtual_key_manager.release_reservation(reservation_id)
                except Exception as exc:
                    log.error(
                        "Failed to release virtual-key reservation after request error "
                        f"(request_id={request_id}, error_type={type(exc).__name__})."
                    )
            if trace_collector is not None:
                try:
                    await get_request_trace_service().record(
                        trace_collector.complete(
                            status_code=500,
                            cancelled=isinstance(
                                request_error, (asyncio.CancelledError, GeneratorExit)
                            ),
                        )
                    )
                except Exception as exc:
                    log.error(
                        "Failed to persist request trace after request error "
                        f"(request_id={request_id}, error_type={type(exc).__name__})."
                    )
            raise
        try:
            if management_mutation is not None:
                await record_classified_management_response(
                    management_mutation,
                    status_code=response.status_code,
                    request_id=request_id,
                    principal=getattr(request.state, "management_principal", None),
                )
            elif response.status_code in {401, 403}:
                management_denial = classify_management_denial(
                    request.method,
                    request.scope.get("path", request.url.path),
                )
                if management_denial is not None:
                    await record_classified_management_response(
                        management_denial,
                        status_code=response.status_code,
                        request_id=request_id,
                        principal=getattr(request.state, "management_principal", None),
                    )
        except Exception as exc:
            log.critical(
                "Durable management audit append failed "
                f"(request_id={request_id}, error_type={type(exc).__name__})."
            )
    trace_recorded = False
    audit_recorded = False

    async def persist_request_trace(*, cancelled: bool = False) -> None:
        nonlocal trace_recorded
        if trace_recorded or trace_collector is None:
            return
        trace_recorded = True
        try:
            await get_request_trace_service().record(
                trace_collector.complete(
                    status_code=response.status_code,
                    cancelled=cancelled,
                )
            )
        except Exception as exc:
            log.error(
                "Failed to persist bounded request trace "
                f"(request_id={request_id}, error_type={type(exc).__name__})."
            )

    async def persist_inference_audit() -> None:
        nonlocal audit_recorded
        if audit_recorded or protocol is None:
            return
        audit_recorded = True
        try:
            await get_audit_service().record_inference(
                request_id=request_id,
                protocol=protocol,
                status_code=response.status_code,
            )
        except Exception as exc:
            log.critical(
                "Durable inference audit append failed "
                f"(request_id={request_id}, error_type={type(exc).__name__})."
            )

    async def persist_inference_observability(*, cancelled: bool = False) -> None:
        await asyncio.gather(
            persist_request_trace(cancelled=cancelled),
            persist_inference_audit(),
        )

    reservation_id = getattr(request.state, "virtual_key_reservation_id", "")
    if reservation_id:
        released = False

        async def finalize_reservation(*, successful: bool) -> None:
            nonlocal released
            if released:
                return
            released = True
            request.state.virtual_key_reservation_id = ""
            from core.virtual_keys import virtual_key_manager

            try:
                upstream_failed = trace_collector is not None and any(
                    decision.category == "upstream" and decision.result == "failed"
                    for decision in trace_collector.decisions
                )
                if successful and response.status_code < 400 and not upstream_failed:
                    await virtual_key_manager.commit_reservation(
                        reservation_id,
                        actual_tokens=None,
                        actual_cost_usd=None,
                        durable_cost_recorded=False,
                    )
            except Exception as exc:
                log.error(
                    "Failed to finalize virtual-key reservation "
                    f"(request_id={request_id}, error_type={type(exc).__name__})."
                )
            try:
                await virtual_key_manager.release_reservation(reservation_id)
            except Exception as exc:
                log.error(
                    "Failed to release virtual-key reservation "
                    f"(request_id={request_id}, error_type={type(exc).__name__})."
                )

        body_iterator = getattr(response, "body_iterator", None)
        if body_iterator is not None:

            async def releasing_body_iterator():
                completed = False
                try:
                    async for chunk in body_iterator:
                        yield chunk
                    completed = True
                finally:
                    try:
                        await close_async_iterator(body_iterator)
                    except Exception as exc:
                        log.error(
                            "Failed to close streaming response during quota cleanup "
                            f"(request_id={request_id}, error_type={type(exc).__name__})."
                        )
                    await finalize_reservation(successful=completed)

            response.body_iterator = releasing_body_iterator()
        else:
            existing_background = response.background

            async def finalize_response() -> None:
                try:
                    if existing_background is not None:
                        await existing_background()
                finally:
                    await finalize_reservation(successful=True)

            response.background = BackgroundTask(finalize_response)

    trace_body_iterator = getattr(response, "body_iterator", None)
    if trace_collector is not None and trace_body_iterator is not None:
        stream_cancelled = False

        async def tracing_body_iterator():
            nonlocal stream_cancelled
            try:
                with bind_request_trace_collector(trace_collector):
                    async for chunk in trace_body_iterator:
                        yield chunk
            except (asyncio.CancelledError, GeneratorExit):
                stream_cancelled = True
                await persist_inference_observability(cancelled=True)
                raise
            except BaseException:
                with bind_request_trace_collector(trace_collector):
                    trace_collector.record(
                        category="upstream",
                        action="failed",
                        result="failed",
                        reason="provider_error",
                        status_code=500,
                    )
                await persist_inference_observability()
                raise
            finally:
                try:
                    await close_async_iterator(trace_body_iterator)
                except Exception as exc:
                    log.error(
                        "Failed to close streaming response during trace cleanup "
                        f"(request_id={request_id}, error_type={type(exc).__name__})."
                    )

        response.body_iterator = tracing_body_iterator()
        existing_background = response.background

        async def finalize_inference_observability() -> None:
            try:
                if existing_background is not None:
                    await existing_background()
            finally:
                await persist_inference_observability(cancelled=stream_cancelled)

        response.background = BackgroundTask(finalize_inference_observability)
    elif trace_collector is not None:
        await persist_inference_observability()
    response.headers["X-Request-ID"] = request_id
    if localize_console:
        response.headers["Content-Language"] = locale
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Origin-Agent-Cluster"] = "?1"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "script-src-attr 'none'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self' ws: wss:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "worker-src 'self'; "
        "manifest-src 'self'"
    )
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    is_https = request.url.scheme == "https" or (
        trust_proxy_headers_enabled()
        and forwarded_proto.split(",", 1)[0].strip().lower() == "https"
    )
    if is_https:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/frontend/"):
        response.headers.setdefault("Cache-Control", "public, max-age=86400")
    else:
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.include_router(primary_openai_router, prefix="", tags=["OpenAI-compatible API"])


app.include_router(primary_responses_router, prefix="", tags=["OpenAI Responses API"])


app.include_router(primary_gemini_router, prefix="", tags=["Gemini-compatible API"])


app.include_router(primary_model_list_router, prefix="", tags=["Model Catalog"])


app.include_router(primary_anthropic_router, prefix="", tags=["Anthropic-compatible Messages"])


app.include_router(health_router, prefix="")


app.include_router(metrics_router, prefix="")


app.include_router(panel_router, prefix="", tags=["Panel Interface"])


app.include_router(vertex_gemini_router, prefix="", tags=["Vertex Gemini API"])


app.include_router(vertex_openai_router, prefix="", tags=["Vertex OpenAI API"])


app.include_router(vertex_model_list_router, prefix="", tags=["Vertex Model List"])


app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


@app.head("/keepalive")
async def keepalive() -> Response:
    return Response(status_code=200)


def main():
    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    _get_worker_count()

    async def _run():
        port = await get_server_port()
        host = await get_server_host()

        log.info("=" * 60)
        log.info("Starting Polaris.")
        log.info("=" * 60)
        log.info(f"Control panel: http://127.0.0.1:{port}")
        log.info("=" * 60)

        config = Config()
        config.bind = [f"{host}:{port}"]
        config.accesslog = "-"
        config.errorlog = "-"
        config.loglevel = "INFO"
        configure_hypercorn(config)

        await serve(app, config)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
