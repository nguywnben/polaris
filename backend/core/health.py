"""Liveness and readiness probes for production runtimes."""

from __future__ import annotations

from core.runtime_lifecycle import get_runtime_lifecycle
from core.storage_adapter import get_storage_adapter
from core.usage_ledger_service import get_usage_ledger_service
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from log import log

router = APIRouter(tags=["Health"])


@router.get("/health", include_in_schema=True)
async def health() -> JSONResponse:
    """Return process liveness without touching external dependencies."""
    return JSONResponse(content={"status": "ok"})


@router.get("/ready", include_in_schema=True)
async def ready() -> JSONResponse:
    """Return whether the configured storage backend is available."""
    lifecycle = get_runtime_lifecycle()
    if lifecycle is None:
        log.warning("Readiness check failed because runtime coordination is unavailable.")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "storage": "unavailable",
                "usage_ledger": "unavailable",
                "coordination": "unavailable",
            },
        )
    coordination_available = await lifecycle.check_ready()
    if not coordination_available:
        log.warning("Readiness check failed because runtime coordination is unavailable.")
    try:
        storage = await get_storage_adapter()
        await storage.get_all_config()
    except Exception:
        log.warning("Readiness check failed because storage is unavailable.")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "storage": "unavailable",
                "usage_ledger": "unavailable",
                "coordination": "available" if coordination_available else "unavailable",
            },
        )
    try:
        service = get_usage_ledger_service()
        await service.check_available()
        ledger = service.health_snapshot()
        if not ledger["available"]:
            raise RuntimeError("Usage ledger is unavailable.")
    except Exception:
        log.warning("Readiness check failed because the usage ledger is unavailable.")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "storage": "available",
                "usage_ledger": "unavailable",
                "coordination": "available" if coordination_available else "unavailable",
            },
        )
    return JSONResponse(
        status_code=200 if coordination_available else 503,
        content={
            "status": "ok" if coordination_available else "unavailable",
            "storage": "available",
            "usage_ledger": "available",
            "coordination": "available" if coordination_available else "unavailable",
        },
    )
