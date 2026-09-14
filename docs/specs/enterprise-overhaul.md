# Spec: Polaris Enterprise Overhaul

## Status

Superseded on 2026-09-08 by `docs/specs/production-self-hosted.md` for current product scope and
release criteria. This document remains a historical record of delivered work; unfinished
enterprise/HA objectives no longer block the production self-hosted baseline.

## Objective

Turn Polaris from a capable single-instance AI router into an enterprise-ready gateway
whose behavior is safe to operate, easy to explain, and measurable. The primary users are AI
platform administrators, developers integrating SDK clients, security teams, and operators
responsible for provider capacity and cost.

The overhaul must improve the existing product without breaking the stable 1.x OpenAI,
Anthropic, Google GenAI, Vertex, health, and management contracts. New capability is delivered
as independently releasable vertical slices rather than a single rewrite.

### Reference-project findings

| Project | Capability worth adopting | Constraint for Polaris |
| --- | --- | --- |
| 9Router | Tiered fallback, quota-aware multi-account routing, usage and reset visibility | Avoid provider-count growth without a stable adapter contract |
| CLIProxyAPI | Credential conductor, cooldown-aware selection, provider-specific auth lifecycle | Actions must be capability-aware instead of assuming every credential is Google-shaped |
| Portkey Gateway | Pipeline hooks, guardrail checks, cache/retry composition | Start with typed built-in stages; do not expose arbitrary executable plugins |
| Langfuse | Request traces, sessions, scores, evaluations, project/member governance | Embed operational traces first; keep full prompt/eval lifecycle as an integration boundary |
| LiteLLM | Virtual keys, budgets, teams, guardrails, router settings, caching, audit logs | Preserve Polaris's smaller and safer management surface |
| OmniRoute | Compression profiles, per-request policy, task-fit routing, scoped keys, health autopilot | Do not adopt semantic compression claims without an evaluation gate |

### Product principles

1. Quality is a policy, not a collection of unrelated switches.
2. Global policy is the upper safety bound; a key or request may choose a stricter policy but
   cannot silently weaken governance.
3. Every routing, compression, retry, cache, and guardrail decision is explainable by request ID.
4. Provider operations are derived from declared capabilities.
5. Secrets are shown once, redacted everywhere else, and never accepted in query strings.
6. Accessibility, responsive behavior, and complete localization are release gates.
7. Multi-replica support is not advertised until all mutable runtime state is coordinated.

## Scope

### A. Console information architecture

- Keep Overview focused on health, SLOs, traffic, cost, and incidents.
- Move secret creation and API-key administration out of Overview.
- Add **AI Quality** for compression, reasoning visibility, anti-truncation, guardrails, response
  cache, and policy preview.
- Add **Access** for the root integration key, virtual keys, scopes, budgets, rate limits,
  expiration, and usage.
- Evolve Logs into **Observability**, separating request traces from raw runtime logs.
- Keep Providers for onboarding and provider-specific settings; keep Credentials for fleet
  operations; keep Models for virtual routes and fallback ordering.
- Add light, dark, and system theme modes without a flash of the wrong theme.

### B. AI quality policy

Introduce a versioned policy document with these profiles:

| Profile | Compression | Guardrails/cache default | Intended use |
| --- | --- | --- | --- |
| `quality` | Off unless the request would exceed a configured safe context budget | Guardrails on when configured; cache deterministic calls only | Safety-critical and evaluation traffic |
| `balanced` | Safe history-prefix pruning above the threshold | Same deterministic-cache rule | Default coding traffic |
| `capacity` | Earlier safe pruning while preserving more than the configured minimum | Same deterministic-cache rule | Long-running tool sessions |
| `custom` | Explicit validated values | Explicit validated values | Advanced operators |

The current token-pruning algorithm remains the only production compression engine in the first
release. It must always preserve system instructions, tool definitions, recent complete turns,
tool-call/result integrity, structured payloads, and the original request object. Semantic filler
removal, model-generated summaries, code thinning, and tool-output rewriting are prohibited until
an evaluation corpus proves their quality impact.

Policy precedence is:

```text
enterprise safety ceiling
  -> stored global policy
    -> virtual-key restriction
      -> allowlisted per-request override
```

Each request records profile, applied mode, reason, original/final estimated tokens, saved tokens,
guardrail outcome, cache outcome, and latency without recording prompt content.

### C. Provider and credential operations

Extend provider metadata with credential variants and supported operations such as `verify`,
`test`, `quota`, `refresh_identity`, `toggle`, `delete`, `export`, `credit_mode`, and
`preview_channel`. The server rejects unsupported operations even if a client crafts the request.

The Credentials page must:

- filter by provider variant, credential kind, health, cooldown, quota state, tier, and source;
- show only actions supported by every selected credential, with an explanation when unavailable;
- preserve filters and pagination across refreshes;
- support select-page and select-all-results as distinct actions;
- show an operation preview before destructive or high-volume work;
- make provider, account identity, model entitlement, quota/reset, last success, error, and source
  visible without opening every record.

Provider forms must use the correct input type, required state, bounds, autocomplete behavior,
secret masking, help text, validation, and provider-specific defaults. Advanced transport fields
are collapsed by default.

### D. Access governance and audit

- Build a complete console flow over the existing virtual-key API.
- Add key scopes for inference protocols and management read/write operations.
- Make rate-limit and budget enforcement reservation-aware so concurrent requests cannot
  knowingly exceed the configured ceiling.
- Treat unknown model pricing according to an explicit policy: deny, warn, or configured fallback
  price; never silently count it as zero for a hard budget.
- Add an append-only audit stream for login, configuration, provider, credential, key, policy,
  backup, and destructive actions. Each event includes timestamp, request ID, actor, action,
  target, outcome, and redacted change summary.
- Add OIDC and role-based access only after the audit and scope model is stable. Initial roles are
  `viewer`, `operator`, `security_admin`, and `owner`.

### E. Observability and reliability

- Add request-trace summaries with provider attempts, routing reason, retries, cooldowns,
  compression, guardrails, cache, tokens, cost, and outcome.
- Add health views for provider/model routes and budget/quota exhaustion.
- Export bounded metrics with low-cardinality labels; keep request IDs in logs/traces, not metric
  labels.
- Add alert-ready status for error-rate, p95 latency, credential exhaustion, budget exhaustion,
  storage failure, and unknown pricing.
- Move sessions, rate windows, reservations, cooldowns, response cache, and invalidation to the
  existing state-store boundary before allowing multiple workers or replicas.
- Make the usage ledger use the selected durable storage backend before declaring HA support.

### F. Localization and content quality

- Replace positional translation arrays with keyed catalogs incrementally.
- Add a static gate for hard-coded user-facing strings in HTML and JavaScript.
- Require parity for all 15 supported locales, including placeholders, accessible names, errors,
  empty states, dialogs, and dynamically generated content.
- Maintain a terminology glossary. Vietnamese uses “thông tin xác thực” for credential,
  “nhà cung cấp” for provider, “định tuyến dự phòng” for fallback, and keeps protocol/product
  names unchanged. `token`, `OAuth`, `API`, SDK names, and provider brands remain technical terms.
- Runtime fallback to English is allowed only as a measured safety net and must be visible in the
  localization audit.

## Tech Stack

- Python 3.12/3.14, FastAPI, Pydantic 2, Hypercorn, httpx.
- SQLite by default; PostgreSQL or MongoDB for durable configuration/credentials; Redis for
  coordinated runtime state.
- Server-assembled HTML fragments, plain JavaScript, and layered CSS with no frontend build step.
- `unittest`-based repository test runner, Ruff, Node syntax checks, yamllint, pip-audit.
- No new runtime dependency in phases 1-4 unless an accepted ADR documents the need and rollback.

## Commands

```powershell
# Run all backend and contract tests
.\.venv\Scripts\python.exe -m backend.tests

# Run focused test modules
.\.venv\Scripts\python.exe -m unittest backend.tests.test_token_compression

# Backend quality
.\.venv\Scripts\ruff.exe check backend
.\.venv\Scripts\ruff.exe format --check backend
.\.venv\Scripts\python.exe -m compileall -q backend

# Frontend syntax
Get-ChildItem frontend\js -Recurse -Filter *.js | Sort-Object FullName |
  ForEach-Object { node --check $_.FullName }

# Supply-chain and configuration checks
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit --local --progress-spinner off
.\.venv\Scripts\yamllint.exe --strict .github deploy .yamllint.yml

# Runtime
$env:CREDENTIALS_DIR = "$env:TEMP\omni-gateway-enterprise-smoke\credentials"
.\.venv\Scripts\python.exe backend\main.py
```

## Project Structure

```text
backend/core/policy/             Versioned AI-quality and access policy domain
backend/core/panel/              Authenticated management APIs
backend/core/provider_registry.py Provider/credential capability contract
backend/core/state_store.py      Single-process and Redis coordination boundary
backend/core/usage_stats.py      Request/cost ledger
backend/tests/                    Unit, contract, and runtime regression tests
frontend/fragments/pages/        One fragment per console page
frontend/js/core/                Navigation, state, localization, theme
frontend/js/features/            Page workflows
frontend/css/                    Tokens, layout, components, responsive behavior
docs/decisions/                  Accepted architecture decisions
docs/specs/                      Product and engineering specifications
tasks/                           Current implementation plan and checklist
```

New directories are introduced only when their first cohesive vertical slice lands.

## Code Style

Use typed domain values and pure validation before I/O. Routes translate HTTP to domain calls and
do not contain policy logic.

```python
@dataclass(frozen=True)
class QualityPolicy:
    profile: QualityProfile
    compression: CompressionPolicy

    def validate(self) -> None:
        if self.compression.target_tokens >= self.compression.threshold_tokens:
            raise ValueError("Compression target must be lower than its threshold.")
```

- Python: 100 columns, Ruff imports/formatting, snake_case functions, explicit bounded validation.
- JavaScript: plain functions/modules consistent with the current bundle manifest; no inline event
  handlers and no user-visible literal outside the English keyed catalog.
- HTML: semantic landmarks, one active `h1`, explicit labels and descriptions, no inline styles in
  new markup.
- CSS: design tokens first, mobile-safe layout, visible focus, reduced-motion support.

## Testing Strategy

- Test-driven development for every behavior change.
- Unit tests for policy precedence, validation, compression invariants, capability resolution,
  scope enforcement, rate/budget reservations, and translation coverage.
- API contract tests for success and error envelopes, authentication, optimistic concurrency,
  audit events, and backward compatibility.
- Integration tests for SQLite plus opt-in live PostgreSQL, MongoDB, and Redis jobs.
- Browser verification at 360, 768, 1024, and 1440 CSS pixels; zero console warnings/errors,
  keyboard-complete workflows, correct accessibility tree, no horizontal page overflow.
- Load tests for routing and governance hot paths before enabling multiple replicas.
- An evaluation fixture set must cover long coding conversations, tool calls/results, structured
  outputs, multilingual prompts, and cache-aware traffic before any semantic compressor ships.

## Boundaries

### Always

- Preserve stable SDK routes and stored 1.x configuration through forward-compatible migration.
- Redact secrets and prompt content from logs, traces, audit summaries, and screenshots.
- Add a test before changing behavior and run the full quality gate at each checkpoint.
- Keep every phase deployable and reversible.
- Update the spec and ADR before changing a decision.

### Ask first

- Add a runtime dependency, introduce a destructive schema migration, or remove a documented route.
- Enable multi-worker/multi-replica mode.
- Change default auth semantics, enable external telemetry by default, or transmit prompt content.
- Ship semantic compression or automatic configuration changes (“autopilot”) that can affect
  request content or provider spend.

### Never

- Persist plaintext virtual keys or provider secrets outside the provider credential store.
- Use query-string credentials.
- Claim HA while mutable state or usage accounting remains process-local.
- Fail open when an enabled security policy cannot be loaded.
- silently treat an unknown-priced model as free under a hard budget.
- Copy reference-project code or claims without validating license, fit, tests, and failure modes.

## Success Criteria

1. All existing 1.x route-contract tests pass; no stored configuration is lost during upgrade or
   rollback.
2. Operators can configure, preview, enable, and disable an AI-quality profile and see why each
   request was or was not compressed.
3. Compression never breaks tool-call/result pairs or removes protected content; `quality` mode
   is the explicit escape hatch for unmodified context.
4. Credential bulk actions are capability-correct on mixed-provider selections, and crafted
   unsupported actions are rejected server-side.
5. Root and virtual API keys are managed outside Overview; plaintext new keys appear once only.
6. Every management mutation emits a redacted audit event correlated by request ID.
7. Observability exposes request outcome, routing, retry, compression, cache, guardrail, token,
   cost, and latency summaries without prompt/secret leakage.
8. Every visible string and accessible name is covered in all 15 locales; no known English leakage
   remains in Vietnamese mode.
9. Light, dark, and system themes pass WCAG 2.2 AA contrast and keyboard/focus checks across all
   console pages and supported widths.
10. Budget/rate enforcement is concurrency-safe for the supported process model; unknown pricing
    follows the selected deny/warn/fallback policy.
11. Multi-replica deployment is enabled only after distributed-state, durable-ledger, failover,
    and load tests pass.
12. Full tests, lint, format, syntax, dependency, container smoke, and browser checks pass with no
    new high-severity security finding.

## Open Questions

No question blocks phases 1-4. Proposed defaults are `balanced` AI quality, `system` theme,
unknown-price policy `warn` for unrestricted traffic and `deny` for hard-budget keys, and English
fallback with an audit-visible localization counter. OIDC/RBAC and multi-replica activation each
require a dedicated accepted ADR when their implementation phase begins.
