"""Machine-readable support tiers for the production self-hosted profile."""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Literal, Mapping

from core.provider_registry import list_provider_capabilities
from pydantic import BaseModel, ConfigDict, Field


class SupportTier(StrEnum):
    CORE = "core"
    ADVANCED = "advanced"
    COMPATIBILITY = "compatibility"
    EXPERIMENTAL = "experimental"


class CapabilityState(StrEnum):
    ACTIVE = "active"
    AVAILABLE = "available"
    DISABLED = "disabled"
    BLOCKED = "blocked"


class ProductCapability(BaseModel):
    """Safe public projection for one build or runtime capability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[._][a-z0-9]+)*$", max_length=96)
    name: str = Field(min_length=1, max_length=80)
    tier: SupportTier
    state: CapabilityState
    summary: str = Field(min_length=1, max_length=240)


class ProductCapabilitySnapshot(BaseModel):
    """Versioned capability response shared by the API and console."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    profile: Literal["self_hosted"] = "self_hosted"
    capabilities: tuple[ProductCapability, ...]


def _enabled(environment: Mapping[str, str], name: str) -> bool:
    value = environment.get(name, "")
    return isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "on"}


def _configured(environment: Mapping[str, str], name: str) -> bool:
    value = environment.get(name, "")
    return isinstance(value, str) and bool(value.strip())


def _capability(
    identifier: str,
    name: str,
    tier: SupportTier,
    state: CapabilityState,
    summary: str,
) -> ProductCapability:
    return ProductCapability(
        id=identifier,
        name=name,
        tier=tier,
        state=state,
        summary=summary,
    )


def _storage_state(*, selected: bool, conflict: bool) -> CapabilityState:
    if conflict:
        return CapabilityState.BLOCKED
    return CapabilityState.ACTIVE if selected else CapabilityState.AVAILABLE


def get_capability_snapshot(
    environment: Mapping[str, str] | None = None,
) -> ProductCapabilitySnapshot:
    """Return a deterministic secret-free view of supported product boundaries."""

    selected = os.environ if environment is None else environment
    postgresql_configured = _configured(selected, "POSTGRESQL_URI")
    mongodb_configured = _configured(selected, "MONGODB_URI")
    storage_conflict = postgresql_configured and mongodb_configured
    postgresql_selected = postgresql_configured and not storage_conflict
    mongodb_selected = mongodb_configured and not storage_conflict
    sqlite_selected = not postgresql_configured and not mongodb_configured

    capabilities = [
        _capability(
            "access.virtual_keys",
            "Virtual API keys",
            SupportTier.CORE,
            CapabilityState.ACTIVE,
            "Scoped client keys, limits, budgets, rotation, and revocation.",
        ),
        _capability(
            "deployment.docker_compose",
            "Docker Compose",
            SupportTier.CORE,
            CapabilityState.AVAILABLE,
            "Canonical single-machine production deployment.",
        ),
        _capability(
            "deployment.platform_scripts",
            "Platform install scripts",
            SupportTier.COMPATIBILITY,
            CapabilityState.AVAILABLE,
            "Existing platform-specific installation paths retained for compatibility.",
        ),
        _capability(
            "deployment.reverse_proxy",
            "Reverse proxy operation",
            SupportTier.ADVANCED,
            CapabilityState.ACTIVE
            if _enabled(selected, "TRUST_PROXY_HEADERS")
            else CapabilityState.AVAILABLE,
            "Optional operation behind a trusted TLS reverse proxy.",
        ),
        _capability(
            "identity.local_owner",
            "Local owner access",
            SupportTier.CORE,
            CapabilityState.ACTIVE,
            "Local setup, login, session revocation, and recovery.",
        ),
        _capability(
            "identity.oidc",
            "OIDC team access",
            SupportTier.ADVANCED,
            CapabilityState.ACTIVE
            if _enabled(selected, "OIDC_ENABLED")
            else CapabilityState.DISABLED,
            "Optional OIDC login and role assignment for a trusted team.",
        ),
        _capability(
            "locale.community",
            "Community locales",
            SupportTier.COMPATIBILITY,
            CapabilityState.AVAILABLE,
            "Existing locales beyond curated English and Vietnamese with fallback coverage.",
        ),
        _capability(
            "operations.activity",
            "Operational activity",
            SupportTier.CORE,
            CapabilityState.ACTIVE,
            "Redacted usage, request traces, audit events, and runtime diagnostics.",
        ),
        _capability(
            "protocol.anthropic_messages",
            "Anthropic Messages API",
            SupportTier.CORE,
            CapabilityState.ACTIVE,
            "Anthropic-compatible message requests and streaming.",
        ),
        _capability(
            "protocol.gemini_native",
            "Gemini native API",
            SupportTier.CORE,
            CapabilityState.ACTIVE,
            "Google Gemini-compatible generation and model routes.",
        ),
        _capability(
            "protocol.openai_chat_completions",
            "OpenAI Chat Completions API",
            SupportTier.CORE,
            CapabilityState.ACTIVE,
            "OpenAI-compatible chat completion requests and streaming.",
        ),
        _capability(
            "protocol.openai_responses",
            "OpenAI Responses API",
            SupportTier.CORE,
            CapabilityState.ACTIVE,
            "OpenAI-compatible Responses requests and streaming.",
        ),
        _capability(
            "protocol.vertex",
            "Vertex-compatible APIs",
            SupportTier.CORE,
            CapabilityState.ACTIVE,
            "Vertex Gemini and OpenAI-compatible request routes.",
        ),
        _capability(
            "quality.policy",
            "AI Quality policy",
            SupportTier.CORE,
            CapabilityState.ACTIVE,
            "Compression, guardrail, cache, and output-quality controls.",
        ),
        _capability(
            "routing.multi_provider",
            "Multi-provider routing",
            SupportTier.CORE,
            CapabilityState.ACTIVE,
            "Health-aware model routes, strategies, retry, and fallback.",
        ),
        _capability(
            "runtime.standalone",
            "Standalone runtime",
            SupportTier.CORE,
            CapabilityState.ACTIVE,
            "Supported single-worker and single-replica production runtime.",
        ),
        _capability(
            "storage.mongodb",
            "MongoDB storage",
            SupportTier.COMPATIBILITY,
            _storage_state(selected=mongodb_selected, conflict=storage_conflict),
            "Existing direct MongoDB storage path retained without Redis or parity expansion.",
        ),
        _capability(
            "storage.postgresql",
            "PostgreSQL storage",
            SupportTier.ADVANCED,
            _storage_state(selected=postgresql_selected, conflict=storage_conflict),
            "Optional durable storage for advanced self-hosted deployments.",
        ),
        _capability(
            "storage.sqlite",
            "SQLite storage",
            SupportTier.CORE,
            _storage_state(selected=sqlite_selected, conflict=storage_conflict),
            "Default durable storage for the production self-hosted profile.",
        ),
        _capability(
            "telemetry.langfuse",
            "Langfuse export",
            SupportTier.ADVANCED,
            CapabilityState.ACTIVE
            if _configured(selected, "LANGFUSE_PUBLIC_KEY")
            and _configured(selected, "LANGFUSE_SECRET_KEY")
            else CapabilityState.DISABLED,
            "Optional external trace integration with content export disabled by default.",
        ),
        _capability(
            "telemetry.opentelemetry",
            "OpenTelemetry export",
            SupportTier.ADVANCED,
            CapabilityState.ACTIVE
            if _enabled(selected, "OTEL_EXPORT_ENABLED")
            else CapabilityState.DISABLED,
            "Optional aggregate OTLP telemetry export.",
        ),
        _capability(
            "telemetry.prometheus",
            "Prometheus metrics",
            SupportTier.ADVANCED,
            CapabilityState.ACTIVE
            if _enabled(selected, "PROMETHEUS_EXPORT_ENABLED")
            else CapabilityState.DISABLED,
            "Optional authenticated Prometheus metrics export.",
        ),
    ]

    for provider in list_provider_capabilities():
        capabilities.append(
            _capability(
                f"provider.{provider['provider_id']}",
                str(provider["display_name"]),
                SupportTier.CORE,
                CapabilityState.AVAILABLE,
                "Built-in provider adapter; active use requires a configured credential.",
            )
        )

    return ProductCapabilitySnapshot(
        capabilities=tuple(sorted(capabilities, key=lambda item: item.id))
    )
