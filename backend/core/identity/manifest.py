"""Declarative authorization policy for management HTTP and WebSocket routes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.identity.authorization import (
    AuthorizationDecision,
    ManagementPermission,
    require_permission,
)


class ManagementRouteTransport(StrEnum):
    HTTP = "http"
    WEBSOCKET = "websocket"


@dataclass(frozen=True, slots=True)
class ManagementRoutePolicy:
    transport: ManagementRouteTransport
    method: str
    path: str
    permission: ManagementPermission


class UnclassifiedManagementRoute(LookupError):
    """Raised when a protected route has no exact policy entry."""


def _http(
    permission: ManagementPermission,
    *routes: tuple[str, str],
) -> tuple[ManagementRoutePolicy, ...]:
    return tuple(
        ManagementRoutePolicy(ManagementRouteTransport.HTTP, method, path, permission)
        for method, path in routes
    )


_MANAGEMENT_ROUTE_MANIFEST = (
    *_http(
        ManagementPermission.CREDENTIALS_MANAGE,
        ("POST", "/api/auth/start"),
        ("POST", "/api/auth/callback"),
        ("POST", "/api/auth/callback-url"),
    ),
    *_http(
        ManagementPermission.CREDENTIALS_READ,
        ("GET", "/api/auth/status/{project_id}"),
        ("GET", "/api/auth/status"),
        ("GET", "/api/auth/env-creds-status"),
        ("GET", "/api/credentials/status"),
        ("GET", "/api/credentials/models/{filename}"),
        ("GET", "/api/credentials/detail/{filename}"),
        ("GET", "/api/credentials/configuration/{filename}"),
        ("GET", "/api/credentials/errors/{filename}"),
        ("GET", "/api/credentials/quota/{filename}"),
    ),
    *_http(ManagementPermission.ROOT_KEY_READ, ("GET", "/api/auth/keys")),
    *_http(ManagementPermission.ROOT_KEY_ROTATE, ("POST", "/api/auth/keys/reset")),
    *_http(
        ManagementPermission.CREDENTIALS_MANAGE,
        ("POST", "/api/auth/load-env-creds"),
        ("DELETE", "/api/auth/env-creds"),
        ("POST", "/api/credentials/upload"),
        ("POST", "/api/credentials/deduplicate-by-email"),
        ("POST", "/api/credentials/import"),
        ("PATCH", "/api/credentials/configuration/{filename}"),
    ),
    *_http(
        ManagementPermission.CREDENTIALS_OPERATE,
        ("POST", "/api/credentials/action"),
        ("POST", "/api/credentials/batch-action"),
        ("POST", "/api/credentials/fetch-email/{filename}"),
        ("POST", "/api/credentials/refresh-all-emails"),
        ("POST", "/api/credentials/verify/{filename}"),
        ("POST", "/api/credentials/configure-preview/{filename}"),
        ("POST", "/api/credentials/test/{filename}"),
    ),
    *_http(
        ManagementPermission.CREDENTIALS_EXPORT,
        ("GET", "/api/credentials/download/{filename}"),
        ("GET", "/api/credentials/download-all"),
    ),
    *_http(
        ManagementPermission.CONFIGURATION_READ,
        ("GET", "/api/capabilities"),
        ("GET", "/api/config/get"),
    ),
    *_http(
        ManagementPermission.CONFIGURATION_MANAGE,
        ("POST", "/api/config/save"),
        ("POST", "/api/config/access"),
        ("POST", "/api/config/reset"),
    ),
    *_http(
        ManagementPermission.BACKUP_EXPORT,
        ("POST", "/api/backups"),
        ("POST", "/api/backups/sanitized-export"),
    ),
    *_http(
        ManagementPermission.BACKUP_RESTORE,
        ("POST", "/api/backups/validate"),
        ("POST", "/api/backups/restore"),
    ),
    *_http(ManagementPermission.LOGS_MANAGE, ("POST", "/api/logs/clear")),
    *_http(ManagementPermission.LOGS_READ, ("GET", "/api/logs/download")),
    *_http(
        ManagementPermission.DASHBOARD_READ,
        ("GET", "/api/usage/stats"),
        ("GET", "/api/usage/stats/page"),
        ("GET", "/api/usage/aggregated"),
        ("GET", "/api/observability/health"),
        ("GET", "/api/observability/routing"),
    ),
    *_http(
        ManagementPermission.ACCESS_READ,
        ("GET", "/api/virtual-keys"),
        ("GET", "/api/virtual-keys/{key_id}/usage"),
    ),
    *_http(
        ManagementPermission.ACCESS_MANAGE,
        ("POST", "/api/virtual-keys"),
        ("PATCH", "/api/virtual-keys/{key_id}"),
        ("PATCH", "/api/virtual-keys/{key_id}/quality-policy"),
        ("DELETE", "/api/virtual-keys/{key_id}"),
        ("POST", "/api/virtual-keys/{key_id}/rotate"),
        ("POST", "/api/virtual-keys/{key_id}/revoke"),
    ),
    *_http(
        ManagementPermission.PROVIDERS_READ,
        ("GET", "/api/providers"),
        ("GET", "/api/providers/capabilities"),
        ("GET", "/api/providers/antigravity/config"),
        ("GET", "/api/providers/google/config"),
        ("GET", "/api/providers/google-ai-studio/config"),
        ("GET", "/api/providers/xai/config"),
        ("GET", "/api/providers/openai/config"),
        ("GET", "/api/providers/anthropic/config"),
        ("GET", "/api/model-catalog"),
        ("GET", "/api/model-blacklist"),
        ("GET", "/api/model-pools"),
    ),
    *_http(
        ManagementPermission.PROVIDERS_MANAGE,
        ("POST", "/api/providers/antigravity/config"),
        ("POST", "/api/providers/antigravity/config/reset"),
        ("POST", "/api/providers/google/config"),
        ("POST", "/api/providers/google/config/reset"),
        ("POST", "/api/providers/google-ai-studio/config"),
        ("POST", "/api/providers/google-ai-studio/config/reset"),
        ("POST", "/api/providers/xai/config"),
        ("POST", "/api/providers/xai/config/reset"),
        ("POST", "/api/providers/openai/config"),
        ("POST", "/api/providers/openai/config/reset"),
        ("POST", "/api/providers/anthropic/config"),
        ("POST", "/api/providers/anthropic/config/reset"),
    ),
    *_http(
        ManagementPermission.CREDENTIALS_MANAGE,
        ("POST", "/api/providers/google-ai-studio/credentials"),
        ("POST", "/api/providers/google-ai-studio/credentials/import"),
        ("POST", "/api/providers/xai/credentials"),
        ("POST", "/api/providers/xai/oauth/start"),
        ("POST", "/api/providers/xai/oauth/complete"),
        ("POST", "/api/providers/xai/credentials/import"),
        ("POST", "/api/providers/openai/platform/credentials"),
        ("POST", "/api/providers/openai/codex/oauth/start"),
        ("POST", "/api/providers/openai/codex/oauth/complete"),
        ("POST", "/api/providers/openai/credentials/import"),
        ("POST", "/api/providers/anthropic/platform/credentials"),
        ("POST", "/api/providers/anthropic/claude-code/oauth/start"),
        ("POST", "/api/providers/anthropic/claude-code/oauth/complete"),
        ("POST", "/api/providers/anthropic/credentials/import"),
        ("POST", "/api/providers/ollama/credentials"),
        ("POST", "/api/providers/ollama/credentials/import"),
    ),
    *_http(
        ManagementPermission.ROUTING_MANAGE,
        ("DELETE", "/api/model-blacklist"),
        ("DELETE", "/api/model-blacklist/{provider_id}/models/{model_id}"),
        ("PUT", "/api/model-pools/polaris"),
        ("POST", "/api/model-routes/polaris"),
        ("PATCH", "/api/model-routes/polaris"),
        ("DELETE", "/api/model-routes/polaris"),
        ("POST", "/api/model-routes/polaris/validate"),
    ),
    *_http(
        ManagementPermission.CREDENTIALS_OPERATE,
        ("POST", "/api/playground/runs"),
    ),
    *_http(ManagementPermission.QUALITY_READ, ("GET", "/api/quality-policy")),
    *_http(
        ManagementPermission.QUALITY_MANAGE,
        ("PUT", "/api/quality-policy"),
        ("POST", "/api/quality-policy/preview"),
    ),
    *_http(
        ManagementPermission.AUDIT_READ,
        ("GET", "/api/audit/events"),
        ("GET", "/api/audit/retention"),
    ),
    *_http(ManagementPermission.AUDIT_MANAGE, ("PUT", "/api/audit/retention")),
    *_http(ManagementPermission.AUDIT_EXPORT, ("GET", "/api/audit/export")),
    *_http(
        ManagementPermission.TRACES_READ,
        ("GET", "/api/traces"),
        ("GET", "/api/traces/retention"),
        ("GET", "/api/traces/{trace_id}"),
    ),
    *_http(ManagementPermission.TRACES_MANAGE, ("PUT", "/api/traces/retention")),
    *_http(ManagementPermission.TRACES_EXPORT, ("GET", "/api/traces/export")),
    *_http(
        ManagementPermission.IDENTITY_READ,
        ("GET", "/api/identity/session"),
        ("GET", "/api/identity/identities"),
        ("GET", "/api/identity/oidc-policy"),
    ),
    *_http(
        ManagementPermission.IDENTITY_MANAGE,
        ("POST", "/api/identity/identities"),
        ("PATCH", "/api/identity/identities/{identity_id}"),
        ("PUT", "/api/identity/identities/{identity_id}/role-binding"),
    ),
    *_http(
        ManagementPermission.SESSIONS_MANAGE,
        ("GET", "/api/identity/sessions"),
        ("POST", "/api/identity/sessions/{session_reference}/revoke"),
    ),
    *_http(
        ManagementPermission.OIDC_MANAGE,
        ("POST", "/api/identity/oidc-policy/advance"),
    ),
    *_http(
        ManagementPermission.RECOVERY_MANAGE,
        ("GET", "/api/identity/recovery"),
    ),
    ManagementRoutePolicy(
        ManagementRouteTransport.WEBSOCKET,
        "WEBSOCKET",
        "/api/logs/stream",
        ManagementPermission.LOGS_READ,
    ),
)

_POLICY_BY_ROUTE = {
    (entry.transport, entry.method, entry.path): entry for entry in _MANAGEMENT_ROUTE_MANIFEST
}
if len(_POLICY_BY_ROUTE) != len(_MANAGEMENT_ROUTE_MANIFEST):
    raise RuntimeError("Management route manifest contains duplicate entries.")


def management_route_manifest() -> tuple[ManagementRoutePolicy, ...]:
    """Return the immutable route authorization inventory."""
    return _MANAGEMENT_ROUTE_MANIFEST


def require_management_route(
    principal: object,
    *,
    transport: object,
    method: object,
    path: object,
) -> AuthorizationDecision:
    """Authorize an exact trusted route template or fail closed."""
    if (
        type(transport) is not ManagementRouteTransport
        or type(method) is not str
        or type(path) is not str
    ):
        raise UnclassifiedManagementRoute("Management route is not classified.")
    policy = _POLICY_BY_ROUTE.get((transport, method.upper(), path))
    if policy is None:
        raise UnclassifiedManagementRoute("Management route is not classified.")
    return require_permission(principal, policy.permission)
