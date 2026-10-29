"""Authenticated query, detail, export, and retention API for request traces."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from core.audit_service import get_audit_service
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.management_audit import ManagementMutation
from core.panel.credential_privacy_route import CredentialPrivacyRoute
from core.request_trace import (
    MAX_TRACE_RETENTION_COUNT,
    MAX_TRACE_RETENTION_DAYS,
    MIN_TRACE_RETENTION_COUNT,
    MIN_TRACE_RETENTION_DAYS,
    RequestTraceQuery,
    RequestTraceRetentionPolicy,
)
from core.request_trace_export import (
    MAX_REQUEST_TRACE_EXPORT_BYTES,
    MAX_REQUEST_TRACE_EXPORT_TRACES,
    RequestTraceExportLimitError,
    build_request_trace_export,
)
from core.request_trace_service import get_request_trace_service
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import StreamingResponse
from log import log
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(
    route_class=CredentialPrivacyRoute, prefix="/api/traces", tags=["request traces"]
)


class TraceFilterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocols: list[str] = Field(default_factory=list, max_length=32)
    outcomes: list[str] = Field(default_factory=list, max_length=32)
    providers: list[str] = Field(default_factory=list, max_length=32)
    models: list[str] = Field(default_factory=list, max_length=32)
    request_id: str | None = Field(default=None, max_length=128)
    started_after: datetime | None = None
    started_before: datetime | None = None

    def to_domain(self, *, page_size: int = 50, cursor: str | None = None) -> RequestTraceQuery:
        return RequestTraceQuery(
            protocols=tuple(self.protocols),
            outcomes=tuple(self.outcomes),
            providers=tuple(self.providers),
            models=tuple(self.models),
            request_id=self.request_id,
            started_after=self.started_after,
            started_before=self.started_before,
            page_size=page_size,
            cursor=cursor,
        )


class TraceQueryParams(TraceFilterParams):
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, min_length=1, max_length=1024)

    def to_domain(self) -> RequestTraceQuery:
        return super().to_domain(page_size=self.page_size, cursor=self.cursor)


class TraceExportParams(TraceFilterParams):
    format: Literal["jsonl", "csv"] = "jsonl"


class TraceRetentionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retention_days: int = Field(
        ge=MIN_TRACE_RETENTION_DAYS,
        le=MAX_TRACE_RETENTION_DAYS,
        strict=True,
    )
    max_traces: int = Field(
        ge=MIN_TRACE_RETENTION_COUNT,
        le=MAX_TRACE_RETENTION_COUNT,
        strict=True,
    )

    def to_domain(self) -> RequestTraceRetentionPolicy:
        return RequestTraceRetentionPolicy(
            retention_days=self.retention_days,
            max_traces=self.max_traces,
        )


class TraceDecisionResponse(BaseModel):
    sequence: int
    elapsed_ms: int
    category: str
    action: str
    result: str
    reason: str
    provider: str
    model: str
    attempt: int
    status_code: int
    latency_ms: int
    candidate_count: int
    original_tokens: int
    final_tokens: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    cost_usd: float


class TraceResponse(BaseModel):
    schema_version: int
    trace_id: str
    request_id: str
    protocol: str
    started_at: str
    completed_at: str
    outcome: str
    status_code: int
    duration_ms: int
    requested_model: str
    selected_provider: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    decisions: list[TraceDecisionResponse]
    decisions_truncated: bool


class TracePageResponse(BaseModel):
    traces: list[TraceResponse]
    next_cursor: str | None
    page_size: int = Field(ge=1, le=200)
    has_more: bool


class TraceRetentionPolicyResponse(BaseModel):
    retention_days: int
    max_traces: int


class TraceLimitBoundsResponse(BaseModel):
    minimum: int
    maximum: int


class TraceRetentionReadResponse(BaseModel):
    policy: TraceRetentionPolicyResponse
    bounds: dict[str, TraceLimitBoundsResponse]


class TraceRetentionUpdateResponse(BaseModel):
    policy: TraceRetentionPolicyResponse
    removed_traces: int = Field(ge=0)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


def _unavailable(operation: str, exc: Exception) -> JSONResponse:
    log.error(
        f"Request trace {operation} failed ({type(exc).__name__}); "
        "the exception detail was withheld from the API response."
    )
    return _error(503, "trace_unavailable", "Request traces are temporarily unavailable.")


def _policy_record(policy: RequestTraceRetentionPolicy) -> dict[str, int]:
    return {"retention_days": policy.retention_days, "max_traces": policy.max_traces}


@router.get("", response_model=TracePageResponse)
async def get_request_traces(
    params: Annotated[TraceQueryParams, Query()],
    token: str = Depends(verify_panel_token),
):
    del token
    try:
        page = await get_request_trace_service().query(params.to_domain())
    except ValueError:
        return _error(
            400, "trace_query_invalid", "The trace query contains an invalid filter or cursor."
        )
    except Exception as exc:
        return _unavailable("query", exc)
    return JSONResponse(
        content={
            "traces": [trace.to_record() for trace in page.traces],
            "next_cursor": page.next_cursor,
            "page_size": params.page_size,
            "has_more": page.next_cursor is not None,
        }
    )


@router.get("/retention", response_model=TraceRetentionReadResponse)
async def get_request_trace_retention(token: str = Depends(verify_panel_token)):
    del token
    try:
        policy = get_request_trace_service().retention_policy
    except Exception as exc:
        return _unavailable("retention read", exc)
    return JSONResponse(
        content={
            "policy": _policy_record(policy),
            "bounds": {
                "retention_days": {
                    "minimum": MIN_TRACE_RETENTION_DAYS,
                    "maximum": MAX_TRACE_RETENTION_DAYS,
                },
                "max_traces": {
                    "minimum": MIN_TRACE_RETENTION_COUNT,
                    "maximum": MAX_TRACE_RETENTION_COUNT,
                },
            },
        }
    )


@router.put("/retention", response_model=TraceRetentionUpdateResponse)
async def update_request_trace_retention(
    request: TraceRetentionUpdateRequest,
    token: str = Depends(verify_panel_token),
):
    del token
    try:
        policy = request.to_domain()
        removed = await get_request_trace_service().update_retention(policy)
    except ValueError:
        return _error(400, "trace_retention_invalid", "The trace retention policy is invalid.")
    except Exception as exc:
        return _unavailable("retention update", exc)
    return JSONResponse(content={"policy": _policy_record(policy), "removed_traces": removed})


@router.get("/export")
async def export_request_traces(
    request: Request,
    params: Annotated[TraceExportParams, Query()],
    token: str = Depends(verify_panel_token),
):
    del token
    try:
        export = await build_request_trace_export(
            get_request_trace_service(),
            params.to_domain(),
            export_format=params.format,
        )
        await get_audit_service().record(
            ManagementMutation(
                action="trace.export",
                target_type="trace_policy",
                change_codes=("exported",),
                target_identifier=f"{params.format}:bounded",
            ),
            request_id=request.state.request_id,
            actor_type="panel_session",
            actor_identifier="panel-owner",
            outcome="succeeded",
        )
    except RequestTraceExportLimitError:
        return _error(
            413,
            "trace_export_limit_exceeded",
            "The filtered trace export exceeds the safety limit.",
        )
    except ValueError:
        return _error(
            400, "trace_export_invalid", "The trace export contains an invalid filter or format."
        )
    except Exception as exc:
        return _unavailable("export", exc)
    generated_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return StreamingResponse(
        iter(export.chunks),
        media_type=export.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="polaris-traces-{generated_at}.{export.extension}"',
            "X-Trace-Count": str(export.trace_count),
            "X-Trace-Byte-Count": str(export.byte_count),
            "X-Trace-Max-Count": str(MAX_REQUEST_TRACE_EXPORT_TRACES),
            "X-Trace-Max-Bytes": str(MAX_REQUEST_TRACE_EXPORT_BYTES),
        },
    )


@router.get("/{trace_id}", response_model=TraceResponse)
async def get_request_trace(
    trace_id: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")],
    token: str = Depends(verify_panel_token),
):
    del token
    try:
        page = await get_request_trace_service().query(
            RequestTraceQuery(trace_ids=(trace_id,), page_size=1)
        )
    except ValueError:
        return _error(400, "trace_id_invalid", "The trace ID is invalid.")
    except Exception as exc:
        return _unavailable("detail", exc)
    if not page.traces:
        return _error(404, "trace_not_found", "The request trace was not found.")
    return JSONResponse(content=page.traces[0].to_record())
