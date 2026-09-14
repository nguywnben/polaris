"""Authenticated operational health and telemetry-control status API."""

from __future__ import annotations

from core.credential_manager import credential_manager
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.operational_health import get_operational_health_snapshot
from core.request_trace_service import get_request_trace_service
from core.telemetry_policy import TelemetryConfigurationError, get_telemetry_policy
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, Query
from log import log

router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/routing")
async def get_routing_health(
    limit: int = Query(default=20, ge=1, le=100),
    token: str = Depends(verify_panel_token),
):
    """Return recent bounded routing explanations without credential identifiers."""
    del token
    try:
        decisions = await credential_manager.get_recent_routing_decisions(limit=limit)
        public_decisions = [decision.to_public_dict() for decision in decisions]
        selected_count = sum(bool(decision["selected"]) for decision in public_decisions)
        return JSONResponse(
            content={
                "status": "no_data" if not public_decisions else "available",
                "count": len(public_decisions),
                "selected_count": selected_count,
                "unavailable_count": len(public_decisions) - selected_count,
                "decisions": public_decisions,
            }
        )
    except Exception as exc:
        log.error(f"Routing health snapshot failed ({type(exc).__name__}).")
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "routing_health_unavailable",
                    "message": "Routing health is temporarily unavailable.",
                }
            },
        )


@router.get("/health")
async def get_operational_health(
    window_seconds: int = Query(default=900, ge=300, le=86_400),
    token: str = Depends(verify_panel_token),
):
    del token
    try:
        snapshot = await get_operational_health_snapshot(
            get_request_trace_service(), window_seconds=window_seconds
        )
        snapshot["telemetry"] = get_telemetry_policy().public_status()
        return JSONResponse(content=snapshot)
    except TelemetryConfigurationError:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "telemetry_configuration_invalid",
                    "message": "External telemetry configuration is invalid.",
                }
            },
        )
    except Exception as exc:
        log.error(f"Operational health snapshot failed ({type(exc).__name__}).")
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "operational_health_unavailable",
                    "message": "Operational health is temporarily unavailable.",
                }
            },
        )
