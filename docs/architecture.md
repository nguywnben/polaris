# Architecture

This document describes the current Polaris architecture, dependency rules, runtime state, completed module boundaries, and release constraints. It documents boundaries rather than duplicating implementation details.

## System Context

```text
OpenAI SDK     Anthropic SDK     Google GenAI SDK     IDE and CLI clients
     \               |                  |                    /
      +--------------+------------------+-------------------+
                             |
                    SDK-compatible routers
                             |
                normalization and translation
                             |
             model policy and credential selection
                             |
             provider adapters and fallback execution
                             |
                  provider APIs and account pools
```

The public transport surface is namespace-neutral. Product branding appears in the management experience and documentation. Generated API keys retain the `sk-polaris-` prefix as an intentional token-identification rule.

## Repository Boundaries

```text
backend/
  main.py                 Application composition and process startup
  config.py               Environment, stored configuration, and defaults
  core/
    router/               HTTP contracts and SDK-specific request handling
    api/                  Provider request orchestration and retry lifecycle
    converter/            Pure request/response format translation
    storage/              Concrete persistence backends
    identity/             Management principals, RBAC decisions, and route permission manifest
    panel/                Authenticated management API and setup policy
    antigravity.py        Google Antigravity headers and per-credential model discovery
    anthropic.py          Claude Code OAuth, Claude Platform keys, and Messages translation
    codex.py              Codex device OAuth, model discovery, and Responses translation
    openai_platform.py    OpenAI Platform API-key validation and Chat Completions transport
    ollama.py             Ollama connection validation, model discovery, and chat translation
    xai.py               Grok Build OAuth, SpaceXAI Console model discovery, and transport translation
    xai_billing.py       Grok Build OAuth account quota retrieval and normalization
    provider_registry.py  Provider identity and capability metadata
    credential_operation_evidence.py Redacted credential mutation events and bounded metrics
    smart_routing.py      Provider and credential selection policy
    storage_adapter.py    Persistence boundary used by the application
  tests/                   Regression and contract tests
frontend/
  index.html              Console shell and ordered asset manifest
  fragments/              Auth, layout, and page-level HTML fragments
  css/                    Cascade-ordered style layers
  js/core/                Shared state, navigation, and manager factories
  js/ui/                  Reusable UI primitives and credential views
  js/features/            Page and workflow modules
  assets/                 Brand and provider assets
deploy/                   Container and hosting definitions
docs/                     Architecture and maintained project assets
```

Dependencies should flow inward from HTTP adapters to orchestration and domain policy. Conversion code must not perform network or storage operations. Routes must use the storage adapter rather than importing database drivers directly.

## Request Lifecycle

1. A router authenticates the client and validates its SDK-specific payload.
2. The request is normalized into the provider-neutral working representation.
3. Context optimization removes only oversized, safe-to-drop history prefixes.
4. Model-pool policy resolves virtual models to ordered provider model candidates.
5. Smart routing reserves a compatible, healthy credential and applies cooldown and concurrency signals.
6. The provider adapter translates and sends the upstream request.
7. Recoverable failures trigger bounded credential or model fallback.
8. The response is translated to the originating SDK format and streamed or returned.
9. Usage, latency, token, retry, and credential-health results are recorded asynchronously.

Model eligibility is evaluated before a request is sent. A declared model catalog on a credential is authoritative; provider-prefix inference is used only when no catalog has been stored. A provider model-not-found response creates a credential-scoped negative route cache, so a missing entitlement on one account does not disable the same model for other accounts.

The maintained eligibility, strategy, fallback, cooldown, recovery, and secret-free diagnostics
contract is documented in [Routing, Fallback, Cooldown, and Health](routing-policy.md).

## State and Scaling

The default single-instance mode stores credentials, configuration, and usage data under `backend/data/creds`, with logs under `backend/data/logs`. Both locations must be persisted in containers.

Control-plane mutations emit versioned evidence into the selected durable audit repository.
Actor and target identifiers become stable HMAC fingerprints before storage; stored records use
allowlisted actions, outcomes, and change codes. Authenticated management routes provide bounded
exact filters, signed opaque cursor pagination, policy-driven age/count retention, and formula-safe
size-bounded JSONL/CSV export. Retention is persisted before pruning and is enforced after each
append. The Observability audit console revalidates this redacted response boundary before using
text-only DOM rendering. It persists only category filters and page size; request IDs,
fingerprints, time bounds, cursors, and event records remain session-only. Retention changes
require explicit confirmation, and exports use the applied filter snapshot rather than draft form
values. The [audit API contract](audit-api.md) defines the public surface and safety limits.
Credential operation counters and latency histograms continue to use only fixed capability
dimensions.

Supported inference requests also emit a separate versioned decision trace after the response or
stream lifecycle ends. Its allowlisted steps explain routing/fallback, retry/cooldown, compression,
guardrails, cache, quota, upstream, usage, and outcome without prompt/response bodies, secrets,
credential filenames, arbitrary metadata, or exception text. SQLite, PostgreSQL, and MongoDB own
additive trace repositories with signed pagination and a dedicated 7-day/100,000-record default
retention policy; audit and raw-log policies do not prune traces. The maintained privacy, storage,
and lifecycle boundary is documented in [Request Decision Trace Contract](request-traces.md).

The operational-health plane derives a cached, bounded 15-minute RED snapshot from those traces.
It exposes at most 5,000 sampled requests and 50 provider/model routes to the authenticated
console, while Prometheus receives only fixed quantile/status/exhaustion vocabularies and a finite
provider label set. Caller and policy rejections remain visible but do not degrade the service
error SLO. External Prometheus and OTLP/HTTP JSON export are both explicit opt-ins; unsafe tokens,
non-HTTPS OTLP endpoints, embedded credentials, arbitrary exporter headers, and unsupported OTLP
transports fail closed. The design follows the official
[OTLP/HTTP contract](https://opentelemetry.io/docs/specs/otlp/) and
[symptom-based Prometheus alerting guidance](https://prometheus.io/docs/practices/alerting/).
Alert rules link directly to the maintained [operational runbooks](observability.md).

Virtual keys use a versioned, fail-closed record contract with hashed-at-rest secrets. Protocol-
specific inference scopes are separate from management read/write scopes; existing unversioned
keys migrate with their prior inference access and no management permission. Bounded model globs,
expiry/status, throttled last-used metadata, and explicit unknown-pricing policy are part of the
record boundary. Request-scoped key attribution prevents management automation from being audited
as the browser owner. The [virtual-key API contract](virtual-key-api.md) defines the supported
scope matrix, migration behavior, and the reservation-enforcement boundary.

Constrained inference authenticates once and creates one atomic in-process reservation spanning
all credential retries and model fallbacks. RPM, estimated TPM, and worst-case eligible-model cost
are admitted together; success replaces the estimate with actual ledger-backed usage, while errors,
disconnects, and cancellations release it. Cached spend is reconciled against unreconciled commits
without double counting, and a budget-ledger outage fails closed. The same process-local
state-store semantics cover primary and Vertex surfaces.

`WORKERS=1` and one application replica are the supported process model for the 1.x series. SQLite is the Core authority, PostgreSQL is an Advanced option, and MongoDB is retained for Compatibility. Shared storage alone does not coordinate reservations, cooldowns, sessions, or usage aggregation across workers. The service rejects `WORKERS` values other than `1` instead of presenting an unsafe scale-out configuration as supported.

The optional identity boundary is governed by
[ADR-007](decisions/007-explicit-rbac-and-oidc-identity.md). Every protected management operation
and WebSocket has an exact server-side permission; missing policy fails closed. Local-owner login
and recovery remain available in every supported deployment. OIDC team login is an Advanced,
disabled-by-default option using Authorization Code with PKCE, state, nonce, strict discovery and
ID Token verification, exact issuer/subject identities, bounded non-owner group mapping, and
revocable sessions. The [Identity console](identity-console.md) exposes identities, role bindings,
sessions, and typed audit records without exposing reusable secrets. In the supported standalone
topology, opaque sessions are process-local and a restart signs users out; this is expected and
does not affect durable configuration or the local owner account.

The Render Blueprint deliberately uses a paid persistent disk. Free Render services have ephemeral filesystems and are not suitable for durable credential storage.

## Security Boundaries

- Public inference requests use the generated API key; browser management routes use HttpOnly session cookies.
- First-run preflight checks durable writes, address, transport/cookie safety, and installation state before owner creation. Direct loopback setup remains token-free; remote setup requires an operator-configured strong `SETUP_TOKEN` that is never generated or logged.
- Runtime-log WebSockets require a matching console origin and authenticate only through the HttpOnly session cookie; credentials are never accepted in their URLs.
- Forwarded client and protocol headers are ignored unless `TRUST_PROXY_HEADERS=true`.
- Imported archives and credentials are validated by provider-specific paths before persistence.
- Fixed-length and chunked HTTP bodies are bounded before application parsers allocate request data.
- Credential values must never appear in logs, issue reports, filenames, or UI summaries.
- Provider tokens remain retrievable for upstream calls, so the deployment boundary must protect storage with least-privilege access and platform-level encryption at rest.
- Cross-origin browser access is disabled unless explicit origins are configured.

## Module Decomposition

The management console is assembled server-side from repository-owned fragments. The browser still receives one complete DOM, so route behavior and accessibility relationships do not depend on client-side template loading.

CSS and JavaScript remain split into reviewable source modules. The panel router concatenates each ordered manifest into one versioned, immutable browser bundle, which preserves module ownership without multiplying production network requests.

```text
frontend/
  index.html
  fragments/
    auth/                  Login and first-run setup
    layout/                Sidebar, mobile header, and footer
    pages/                 One fragment per console route
  css/
    foundation.css         Tokens, reset, typography, and base elements
    shell.css              Authentication and application layout
    providers-and-models.css
    forms-and-data.css
    components.css
    audit.css              Audit filters, event stream, detail dialog, and retention layout
    observability.css      Request trace search/detail and separated raw-log diagnostics
    dialogs.css
    responsive.css         Breakpoint overrides loaded last
  js/
    core/                  Localization, navigation, state, and managers
    ui/                    Notifications, dialogs, API-key UI, and credential views
    features/              Authentication, audit, traces, pool, models, providers, settings, logs

backend/core/panel/
  credentials.py          Credential HTTP routes
  credential_operations.py Reusable import, dedupe, download, and verification logic
  auth.py                 Login, setup, OAuth, and API-key routes
  auth_support.py         Login throttling and response shaping
  environment_credentials.py Environment credential import routes
  setup_security.py       Remote first-run bootstrap policy
  trace_routes.py         Authenticated trace query, detail, retention, and bounded export
  observability_routes.py Authenticated RED, route-health, exhaustion, and exporter status
  providers/
    catalog.py            Provider capability discovery
    antigravity.py        Google Antigravity settings
    google_ai_studio.py   Google AI Studio settings and imports
    anthropic.py          Claude Code and Claude Platform settings and imports
    openai.py             Codex and OpenAI Platform settings and imports
    ollama.py             Ollama connection settings and imports
    xai.py                Grok Build OAuth and SpaceXAI Console settings and imports
    import_utils.py        Shared bounded-import policy
```

Module size is a review signal, not a target. A file is split when it owns independent workflows, provider contracts, or UI layers. Cohesive translation algorithms and storage adapters remain intact even when long because arbitrary slicing would increase coupling without creating a stable boundary.

Further converter decomposition should happen only when request, response, tool, and streaming contracts can be separated with behavior-preserving tests:

```text
backend/core/converter/{openai,anthropic}_to_gemini.py
  -> request.py, response.py, tools.py, streaming.py per format package
```

The storage drivers interpolate only table and column identifiers selected from internal allowlists; all credential values remain parameterized. Future storage work should consolidate those safe identifier builders, replace repeated broad exception handling with typed boundary errors, and add live integration suites for PostgreSQL and MongoDB.

### Standalone coordination boundary

Routing, quota, governance invalidation, exact-cache metadata, management sessions, security
attempts, OIDC/provider/device authorization, and credential-batch idempotency have a fenced
semantic coordination interface. The runtime creates one in-memory adapter per process and keeps
exact response bytes in its bounded local cache. This protects concurrent work inside the supported
one-worker, one-replica topology; it is not a distributed-state or scale-out contract. Startup
rejects coordinated mode, multiple workers, multiple replicas, and retired coordination settings.
ADR-002 remains the release authority for this boundary.

Production dependencies are compiled into `requirements.lock` with hashes. `requirements.txt` remains the human-maintained input, and CI rejects stale lock output.

Credential inventory includes an opaque `quota_cache_scope` for display caches. It is a
process-keyed digest of provider/account identity and connection scope, not a credential or
authorization token. Browser plan snapshots and quota previews are isolated by this scope;
replacement accounts and late responses cannot reuse another account's cached display. Unknown
identities do not restore persisted plans. A server restart invalidates these optional snapshots
until fresh quota metadata arrives; it does not change stored credentials or subscriptions.

## Change Policy

Public SDK routes and payload contracts require compatibility tests. Storage schema changes require forward migration and rollback notes. Provider-specific changes must remain behind provider capability boundaries. Architectural decisions that are expensive to reverse should be recorded under `docs/decisions/` as ADRs.

Current decisions:

- [ADR-001: Preserve SDK-Compatible API Boundaries](decisions/001-sdk-compatible-api-boundaries.md)
- [ADR-002: Secure First Run and Enforce Single-Worker Operation](decisions/002-secure-first-run-and-single-worker.md)
- [ADR-003: Deployment-Scoped Model Eligibility and Negative Route Cache](decisions/003-deployment-scoped-model-eligibility.md)
- [ADR-004: Versioned AI Quality Policy Plane](decisions/004-versioned-ai-quality-policy-plane.md)
- [ADR-005: Provider-Declared Credential Operation Capabilities](decisions/005-provider-operation-capabilities.md)
- [ADR-006: Separate Durable Data from Coordinated Runtime State](decisions/006-durable-and-coordinated-enterprise-state.md)
- [ADR-007: Use Explicit Management Principals, RBAC, and OIDC](decisions/007-explicit-rbac-and-oidc-identity.md)
- [ADR-008: historical gated-HA decision, superseded by topology retirement](decisions/008-gated-high-availability-activation.md)
- [ADR-009: Use One Encrypted SQLite Artifact for Portable Recovery](decisions/009-encrypted-portable-sqlite-recovery.md)
- [ADR-010: Return One Safe Provider Connection Diagnostic](decisions/010-safe-provider-connection-diagnostics.md)
- [ADR-011: Use One Explicit Cross-Protocol Translation Contract](decisions/011-explicit-protocol-translation-contract.md)
- [ADR-012: Use One Bounded, Output-Aware Stream Lifecycle](decisions/012-bounded-stream-lifecycle.md)
- [ADR-013: Use One Canonical Standalone Routing Policy](decisions/013-canonical-standalone-routing.md)
