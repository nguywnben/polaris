# Specification: Production Self-Hosted Baseline R1

## Status

Approved and scope-frozen on 2026-09-08, then reconciled with `PROD-BALANCE-R2` on 2026-09-12.
This specification supersedes the target and release criteria in
`docs/specs/enterprise-overhaul.md`; previously delivered compatible work remains valid.

## Product Definition

Polaris is a self-hosted gateway that lets an individual or a small trusted team connect
multiple AI provider accounts, expose stable OpenAI/Anthropic/Google-compatible endpoints, route
requests intelligently, and understand quality, reliability, and cost from one local console.

The product is successful when a technically comfortable user can deploy it on one machine, add a
provider, make a correct request, diagnose failures, protect access, and recover their data without
operating an enterprise platform.

### Primary users

- An individual developer running several provider accounts locally or on a small VPS.
- A trusted team of up to roughly 20 people sharing routes and scoped API keys.
- A maintainer who needs predictable upgrades, backups, logs, and troubleshooting.

### Non-goals

- Commercial multi-tenant service, customer billing, formal SLA, active-active HA, region failover,
  compliance certification, or large organization governance.
- Arbitrary user code/plugins in the request pipeline.
- Guaranteeing semantic quality for model-generated summarization or destructive prompt rewriting.

## Audit Summary and Decisions

The repository already has strong routing, protocol conversion, credential orchestration, virtual
keys, usage accounting, audit/traces, identity, and defensive test coverage. The imbalance is that
distributed coordination and enterprise identity received much deeper treatment than installation,
configuration, recovery, browser verification, and day-to-day workflows.

| Area | Current state | Production disposition |
| --- | --- | --- |
| Runtime | Single worker/replica is the only activated topology and is adequate for the target | Make standalone the explicit production topology |
| HA/Redis | No supported activation or user migration burden | Retired from runtime, dependencies, tools, tests, and active docs |
| Kubernetes | No supported scale-out topology | Retired; Docker Compose is canonical |
| Storage | SQLite, PostgreSQL, and MongoDB parity creates high maintenance cost | SQLite core; PostgreSQL advanced; MongoDB compatibility only |
| Identity | Secure OIDC/RBAC exists but four-role enterprise language dominates the console | Keep as optional Team access; local owner remains the default and recovery root |
| Observability | Audit, request traces, raw logs, Prometheus, OTLP, and Langfuse are capable but fragmented | Consolidate console navigation into Activity; keep exporters opt-in |
| Configuration | One schema covers a bounded default and opt-in controls | Basic/Advanced/Compatibility grouping with validation and generated examples |
| Frontend | Eleven destinations, Playground, shared components, and maintained browser evidence | Keep the no-build architecture and one common interface contract |
| Localization | Fifteen complete catalogs are expensive to curate equally | English/Vietnamese production; other locales community compatibility |
| Documentation | README covers fifteen languages; linked guides retain their document language | Keep provider/configuration coverage and examples aligned across READMEs; console locale policy is separate |

## Capability Map

### 1. Install, configure, recover

Owns first-run setup, configuration validation, health, backup/restore, update, and rollback.

- Canonical `docker compose` install with persistent data and safe container defaults.
- Setup wizard checks writable data, required secrets, port/proxy configuration, and existing state.
- Basic configuration contains only common self-host choices; advanced and compatibility settings
  remain discoverable without cluttering first run.
- A versioned, integrity-checked portable backup contains configuration, credentials, identity,
  routes, keys, and durable ledgers only inside a passphrase-encrypted archive. A separate sanitized
  export excludes restorable secrets. Raw logs are excluded from both by default.
- Restore supports dry-run validation, conflict policy, pre-restore backup, and rollback.

### 2. Providers and credentials

Owns provider onboarding, auth variants, health, quotas, cooldown, and safe fleet operations.

- Every advertised provider declares supported auth variants, operations, discovery behavior,
  protocols, model metadata, and useful remediation messages.
- “Test connection” distinguishes credentials, permission, quota, network, upstream, and unsupported
  model failures without leaking provider secrets.
- Single and batch actions are capability-aware; selected mixed providers show only valid common
  actions and explain disabled actions.
- Provider forms expose required inputs first, validate bounds/types, and collapse transport or
  provider-specific expert settings.

### 3. Models, routing, and protocol compatibility

Owns model discovery, virtual routes, fallback order, health-aware selection, retries, and public
API compatibility.

- A model route maps a stable name to ordered/weighted eligible provider models.
- Routing strategy, exclusions, cooldown, fallback, and retry decisions are deterministic enough to
  explain by request ID.
- Streaming and non-streaming requests preserve protocol-specific content, tools, finish reasons,
  usage, errors, cancellation, and timeout behavior.
- Public endpoints remain compatible with the existing OpenAI Chat Completions/Responses,
  Anthropic Messages, Gemini native, Vertex, model-list, health, and readiness contracts.

### 4. AI Quality

Owns compression, context safety, cache, guardrails, reasoning visibility, and policy explanation.

- Presets are `quality`, `balanced`, `capacity`, and validated `custom`.
- Compression has a clear global switch and an allowlisted per-key/request restriction. Disabling
  it means the gateway does not prune or rewrite prompt context.
- Preview uses synthetic or user-entered text locally and shows estimated before/after tokens,
  protected content, removed turns, threshold, and reason before saving a policy.
- Quality policy preserves system/tool/current-request invariants and falls back to uncompressed
  forwarding when an invariant cannot be established.
- Response cache and guardrails communicate semantic tradeoffs and are disabled by default unless
  explicitly configured.

### 5. Playground

Owns safe interactive verification of the gateway.

- Select protocol, virtual/raw model, streaming mode, system and user content, temperature,
  token limit, and supported reasoning/tool options.
- Display incremental output, latency, provider attempts, usage/cost estimate, compression action,
  request ID, normalized errors, and raw response metadata in separate views.
- Copy equivalent cURL and minimal SDK examples with a placeholder key, never the active secret.
- Keep prompt history in browser memory only and clear it when the tab reloads or closes.
- Enforce bounded input/output rendering and a single cancellable in-flight request per panel.

### 6. Access and small-team identity

Owns local login, virtual keys, optional team login, roles, and recovery.

- Local owner setup/login/recovery is always available and independent of an external IdP.
- Virtual keys support least-privilege scopes, model restrictions, expiry, rate/budget controls,
  one-time reveal, rotation, revocation, last use, and clear unknown-pricing behavior.
- Optional OIDC is labeled Team access. Existing viewer/operator/security-admin/owner roles remain
  but are not required for single-user operation.
- Identity navigation is hidden or summarized when Team access is disabled; security events remain
  visible to the owner in Activity.

### 7. Usage, cost, and activity

Owns operational evidence useful to a self-hosting maintainer.

- Dashboard prioritizes readiness, provider/credential problems, requests/errors, latency,
  current usage/cost, and quick actions.
- One Activity area presents request traces, management/security events, and raw runtime logs as
  distinct tabs with shared time, outcome, provider, actor, and request-ID filters.
- Prompt/response bodies are not retained by default. Exports remain redacted and bounded.
- Pricing freshness and unknown-price behavior are explicit; hard budgets never silently treat an
  unknown price as zero.
- Prometheus, OTLP, and Langfuse remain separate opt-in integrations, not installation requirements.

## Information Architecture

The console uses one flat primary navigation. Advanced or compatibility complexity is disclosed
inside the page that owns it, not hidden behind a separate sidebar section:

1. Overview
2. Playground
3. Providers
4. Credentials
5. Models & Routing
6. AI Quality
7. Access
8. Activity
9. Settings
10. Team access (shown only when enabled or during configuration)
11. About

“Audit events” and “Request traces” cease being competing top-level pages; they become Activity
tabs. Existing URLs/API contracts may remain as compatibility redirects or internal endpoints.

## Configuration Model

One typed server schema is authoritative. Environment variables, Settings inputs, generated
examples, Compose, and documentation derive from or are checked against it.

- Basic: port, data directory, local owner/setup secret, public/base URL, CORS, reverse-proxy trust,
  log level, route strategy, and backup location/schedule.
- Advanced: PostgreSQL, OIDC, exporters, guardrails, cache, detailed limits and timeouts.
- Compatibility: legacy Code Assist controls and hosted keep-alive behavior.
- Unknown keys warn; malformed or unsafe values fail startup with a precise remediation message.
- The UI explains whether a change is live, requires restart, or is environment-owned/read-only.

## Compatibility and Deprecation

- No existing public inference endpoint is removed in R1.
- Existing management endpoints used by the console remain until replacements ship and browser
  migration is verified.
- MongoDB and hosted-platform descriptors remain available but are documented as compatibility
  paths. They receive security/correctness repairs, not feature-parity expansion.
- Coordinated Redis/HA implementation, executable evidence tooling, and Kubernetes assets are
  retired. The runtime remains explicitly limited to one worker and one application replica.
- Enterprise wording is removed from current product copy. Historical ADRs/specs remain as records
  and receive a superseded banner rather than revisionist edits.

## Release Definition

The current production candidate is complete only when all seven tasks in
`tasks/production-balance-r2.md` and the constraints in `CONSTRAINTS.md` pass. Historical R1 work
remains complete. The release does not wait for retired distributed topology, MongoDB parity,
all-locale editorial review, optional soak evidence, or real credentials for every provider.

The final evidence must include:

- clean install and upgrade/rollback on the canonical Compose path;
- required backend, contract, container, browser, security, and configuration gates;
- one 120-second deterministic routine reliability run; the preserved ten-minute profile is an
  optional soak for major releases or memory investigations;
- provider capability matrix and opt-in live-smoke instructions;
- backup/restore round trip with integrity and secret-redaction evidence;
- complete English/Vietnamese copy audit and key completeness for compatibility locales;
- known limitations, supported tiers, and post-R1 backlog.
