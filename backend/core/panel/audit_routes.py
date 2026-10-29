"""Authenticated management API for durable redacted audit evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from core.audit import (
    MAX_RETENTION_DAYS,
    MAX_RETENTION_EVENTS,
    MIN_RETENTION_DAYS,
    MIN_RETENTION_EVENTS,
    AuditQuery,
    AuditRetentionPolicy,
)
from core.audit_export import (
    MAX_AUDIT_EXPORT_BYTES,
    MAX_AUDIT_EXPORT_EVENTS,
    AuditExportLimitError,
    build_audit_export,
)
from core.audit_service import get_audit_service
from core.i18n import LocalizedJSONResponse as JSONResponse
from core.management_audit import ManagementMutation
from core.panel.credential_privacy_route import CredentialPrivacyRoute
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from log import log
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(route_class=CredentialPrivacyRoute, prefix="/api/audit", tags=["audit"])


class AuditFilterParams(BaseModel):
    """Bounded exact-match filters shared by list and export routes."""

    model_config = ConfigDict(extra="forbid")

    actor_types: list[str] = Field(default_factory=list, max_length=32)
    actor_fingerprints: list[str] = Field(default_factory=list, max_length=32)
    actions: list[str] = Field(default_factory=list, max_length=32)
    target_types: list[str] = Field(default_factory=list, max_length=32)
    target_fingerprints: list[str] = Field(default_factory=list, max_length=32)
    outcomes: list[str] = Field(default_factory=list, max_length=32)
    request_id: str | None = Field(default=None, max_length=128)
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None

    def to_domain(
        self,
        *,
        page_size: int = 50,
        cursor: str | None = None,
    ) -> AuditQuery:
        return AuditQuery(
            actor_types=tuple(self.actor_types),
            actor_fingerprints=tuple(self.actor_fingerprints),
            actions=tuple(self.actions),
            target_types=tuple(self.target_types),
            target_fingerprints=tuple(self.target_fingerprints),
            outcomes=tuple(self.outcomes),
            request_id=self.request_id,
            occurred_after=self.occurred_after,
            occurred_before=self.occurred_before,
            page_size=page_size,
            cursor=cursor,
        )


class AuditQueryParams(AuditFilterParams):
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, min_length=1, max_length=1024)

    def to_domain(self) -> AuditQuery:
        return super().to_domain(page_size=self.page_size, cursor=self.cursor)


class AuditExportParams(AuditFilterParams):
    format: Literal["jsonl", "csv"] = "jsonl"


class AuditRetentionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retention_days: int = Field(
        ge=MIN_RETENTION_DAYS,
        le=MAX_RETENTION_DAYS,
        strict=True,
    )
    max_events: int = Field(
        ge=MIN_RETENTION_EVENTS,
        le=MAX_RETENTION_EVENTS,
        strict=True,
    )

    def to_domain(self) -> AuditRetentionPolicy:
        return AuditRetentionPolicy(
            retention_days=self.retention_days,
            max_events=self.max_events,
        )


class AuditEventResponse(BaseModel):
    schema_version: int
    event_id: str
    occurred_at: str
    request_id: str
    actor_type: str
    actor_fingerprint: str
    action: str
    target_type: str
    target_fingerprint: str
    outcome: str
    change_codes: list[str]


class AuditPageResponse(BaseModel):
    events: list[AuditEventResponse]
    next_cursor: str | None
    page_size: int = Field(ge=1, le=200)
    has_more: bool


class AuditRetentionPolicyResponse(BaseModel):
    retention_days: int
    max_events: int


class AuditLimitBoundsResponse(BaseModel):
    minimum: int
    maximum: int


class AuditRetentionBoundsResponse(BaseModel):
    retention_days: AuditLimitBoundsResponse
    max_events: AuditLimitBoundsResponse


class AuditRetentionReadResponse(BaseModel):
    policy: AuditRetentionPolicyResponse
    bounds: AuditRetentionBoundsResponse


class AuditRetentionUpdateResponse(BaseModel):
    policy: AuditRetentionPolicyResponse
    removed_events: int = Field(ge=0)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _unavailable(operation: str, exc: Exception) -> JSONResponse:
    log.error(
        f"Audit {operation} failed ({type(exc).__name__}); "
        "the exception detail was withheld from the API response."
    )
    return _error(
        503,
        "audit_unavailable",
        "The audit service is temporarily unavailable.",
    )


def _policy_record(policy: AuditRetentionPolicy) -> dict[str, int]:
    return {
        "retention_days": policy.retention_days,
        "max_events": policy.max_events,
    }


@router.get("/events", response_model=AuditPageResponse)
async def get_audit_events(
    params: Annotated[AuditQueryParams, Query()],
    token: str = Depends(verify_panel_token),
):
    del token
    try:
        page = await get_audit_service().query(params.to_domain())
    except ValueError:
        return _error(
            400,
            "audit_query_invalid",
            "The audit query contains an invalid filter or cursor.",
        )
    except Exception as exc:
        return _unavailable("query", exc)
    return JSONResponse(
        content={
            "events": [event.to_record() for event in page.events],
            "next_cursor": page.next_cursor,
            "page_size": params.page_size,
            "has_more": page.next_cursor is not None,
        }
    )


@router.get("/retention", response_model=AuditRetentionReadResponse)
async def get_audit_retention(token: str = Depends(verify_panel_token)):
    del token
    try:
        policy = get_audit_service().retention_policy
    except Exception as exc:
        return _unavailable("retention read", exc)
    return JSONResponse(
        content={
            "policy": _policy_record(policy),
            "bounds": {
                "retention_days": {
                    "minimum": MIN_RETENTION_DAYS,
                    "maximum": MAX_RETENTION_DAYS,
                },
                "max_events": {
                    "minimum": MIN_RETENTION_EVENTS,
                    "maximum": MAX_RETENTION_EVENTS,
                },
            },
        }
    )


@router.get("/export")
async def export_audit_events(
    request: Request,
    params: Annotated[AuditExportParams, Query()],
    token: str = Depends(verify_panel_token),
):
    del token
    try:
        service = get_audit_service()
        export = await build_audit_export(
            service,
            params.to_domain(),
            export_format=params.format,
        )
        await service.record(
            ManagementMutation(
                action="audit.export",
                target_type="audit_policy",
                change_codes=("exported",),
                target_identifier=f"{params.format}:bounded",
            ),
            request_id=request.state.request_id,
            actor_type="panel_session",
            actor_identifier="panel-owner",
            outcome="succeeded",
        )
    except AuditExportLimitError:
        return _error(
            413,
            "audit_export_limit_exceeded",
            "The filtered audit export exceeds the configured safety limit.",
        )
    except ValueError:
        return _error(
            400,
            "audit_export_invalid",
            "The audit export contains an invalid filter or format.",
        )
    except Exception as exc:
        return _unavailable("export", exc)

    generated_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return StreamingResponse(
        iter(export.chunks),
        media_type=export.media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="polaris-audit-{generated_at}.{export.extension}"'
            ),
            "X-Audit-Event-Count": str(export.event_count),
            "X-Audit-Byte-Count": str(export.byte_count),
            "X-Audit-Max-Events": str(MAX_AUDIT_EXPORT_EVENTS),
            "X-Audit-Max-Bytes": str(MAX_AUDIT_EXPORT_BYTES),
        },
    )


@router.put("/retention", response_model=AuditRetentionUpdateResponse)
async def update_audit_retention(
    request: AuditRetentionUpdateRequest,
    token: str = Depends(verify_panel_token),
):
    del token
    try:
        policy = request.to_domain()
        removed_events = await get_audit_service().update_retention(policy)
    except ValueError:
        return _error(
            400,
            "audit_retention_invalid",
            "The audit retention policy is invalid.",
        )
    except Exception as exc:
        return _unavailable("retention update", exc)
    return JSONResponse(
        content={
            "policy": _policy_record(policy),
            "removed_events": removed_events,
        }
    )
