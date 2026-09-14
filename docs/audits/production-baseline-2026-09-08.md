# Polaris Production Baseline Audit — 2026-09-08

## Purpose

This audit records why `PROD-SELFHOST-R1` replaced the enterprise roadmap. It is evidence for the
fixed plan, not another source of tasks. Findings must map to an existing P0–P5 task or the post-R1
backlog.

## Repository Snapshot

- Approximately 598 repository files: 369 backend, 86 frontend, 80 documentation, 30 deployment,
  19 tooling, and 3 task-control files in the initial inventory.
- Approximately 74,657 lines across 179 backend/core Python files.
- Approximately 30,229 lines across 74 frontend HTML/CSS/JavaScript files.
- 174 `test_*.py` files and approximately 44,037 test lines; the latest recorded full discovery
  before the scope reset was 1,320 passing tests with 30 opt-in live-backend skips.
- 159 router-decorated API operations and 11 current top-level console pages.
- 54 test files mention HA, identity, OIDC, Redis, coordination, or migration—roughly 31% of test
  files—showing where assurance effort became disproportionate to the new target.
- `.env.example` exposes roughly 140 uppercase configuration identifiers by inventory heuristic.
- Frontend code has no package manifest/test runner; CI syntax-checks JavaScript but does not yet
  exercise complete browser journeys.

These counts are directional baselines, not permanent quality metrics. P0.2/P0.4 will regenerate
authoritative inventories with reproducible commands.

## Existing Capability Inventory

### Public gateway protocols

- OpenAI-compatible Chat Completions, Responses, and model listing.
- Anthropic-compatible Messages.
- Google Gemini native routes and Vertex-compatible routes.
- Streaming and non-streaming conversion, tool calls, usage mapping, errors, retries, and request IDs.

### Providers and credentials

- Google Antigravity and Google AI Studio.
- Claude Code and Anthropic/Claude Platform.
- Codex and OpenAI Platform.
- Grok Build and SpaceXAI Console.
- Ollama.
- Credential discovery/import, health, quota, cooldown, capability-aware actions, filters, batch
  preview/execution, and per-provider forms.

### Routing and AI quality

- Model catalog and virtual model pools/routes.
- Balanced, priority, weighted, least-latency, and lowest-cost strategies.
- Health-aware selection, cooldown, retry, fallback, and preferred-provider behavior.
- Quality profiles, token/context pruning, guardrails, response cache, reasoning-related metadata,
  policy precedence, and redacted decision traces.

### Access, usage, and operations

- Local owner setup/login/recovery and revocable sessions.
- Virtual keys with scopes, model restrictions, expiry, rate limits, monetary/token accounting,
  rotation, revocation, and one-time reveal.
- Optional OIDC with PKCE, strict ID-token verification, explicit role binding, four roles, audit,
  and local recovery independence.
- Append-only management/security audit events, request traces, raw runtime logs, usage/cost ledger,
  health/SLO projections, Prometheus, OTLP, and Langfuse integration.

### Console and deployment

- Dashboard, AI Quality, Identity, Access, Credentials Pool, Models, Providers, Settings, Audit,
  Request Traces/Logs, About, and light/dark/system themes.
- Fifteen translation catalogs with a previously recorded 1,116 referenced keys.
- Docker image and Compose, platform install scripts, Render/Zeabur descriptors, Helm chart,
  ServiceMonitor/PrometheusRule, CI, image publishing, and release publishing.
- SQLite, PostgreSQL, and MongoDB repositories plus Redis/in-memory coordination implementations.

## Balance Assessment

### Overbuilt for the current target

1. **HA activation and distributed coordination.** Two-replica delivery matrices, Redis failover,
   fencing epochs, reconciliation, standby promotion, and exact cross-replica accounting are much
   deeper than a one-machine self-hosted release requires. They remain useful engineering assets,
   but must be experimental and non-blocking.
2. **Three-backend parity.** Exact SQLite/PostgreSQL/MongoDB parity multiplies every identity,
   ledger, audit, trace, and migration change. SQLite plus optional PostgreSQL covers the target;
   MongoDB should receive compatibility/security fixes only.
3. **Kubernetes surface.** Helm, ServiceMonitor, and PrometheusRule imply an operational promise the
   one-replica chart cannot fulfill. Retain as experimental/community, not the primary install.
4. **Governance-first information architecture.** Identity and separate audit/trace destinations
   occupy primary navigation even when one owner uses the product. Team identity should appear on
   demand; operational evidence should be one Activity workflow.
5. **Equal editorial promise across 15 locales.** Key completeness is feasible, but equal semantic
   review across all locales is not proportionate. English and Vietnamese become curated; existing
   others keep fallback and completeness guarantees.
6. **Configuration exposure.** Compose and `.env.example` present coordination, storage, security,
   telemetry, routing, cache, and guardrail details together, making safe first use harder.

### Below production quality

1. **No complete backup/restore/update rollback journey.** A self-hosted product must make recovery
   more reliable than hand-copying data directories.
2. **No Playground.** Users cannot prove routes, streaming, compression, metadata, and errors from
   the console before configuring an external client.
3. **Frontend assurance gap.** JavaScript syntax checking does not prove navigation, accessibility,
   loading/error states, XSS safety, or critical journeys.
4. **Configuration drift risk.** Runtime parsing, Compose, `.env`, docs, and Settings do not yet have
   one authoritative schema and parity test.
5. **Fragmented operational workflow.** Dashboard, audit, trace, and raw logs are individually rich
   but require too much navigation and terminology for incident diagnosis.
6. **Provider completeness is hard to prove.** Provider-specific forms and operations exist, but an
   authoritative add/test/discover/infer/remove capability matrix must govern API and UI together.
7. **Documentation truth.** Current README language says stable/enterprise while production support
   tiers, experimental HA, upgrade, backup, rollback, and architecture limits are not equally clear.
8. **Maintainability hotspots.** Several core modules exceed 1,500 lines and frontend locale/page
   catalogs are very large. Changes should extract coherent ownership where useful, not trigger a
   risky rewrite.

## Largest Maintainability Hotspots

| File/area | Approximate lines | R1 treatment |
| --- | ---: | --- |
| `backend/core/redis_state_store.py` | 4,159 | Freeze expansion with HA; security/correctness only |
| `backend/core/state_store.py` | 2,493 | Assess boundaries in P0.4; modify only for core tasks |
| `backend/core/api/primary.py` | 1,979 | Protect with P2.3/P2.4 protocol fixtures before edits |
| `backend/core/panel/credentials.py` | 1,651 | Capability-driven cleanup in P2.1/P3.5 |
| `backend/core/identity/sessions.py` | 1,576 | Security closure in P5.2; no redesign |
| Storage managers | 1,230–1,568 each | Tier/freeze decisions in P5.1 |
| Major converters | 1,108–1,510 each | Golden corpus in P2.3 before corrections |
| `frontend/js/core/i18n.js` | 5,468 | English/Vietnamese curation and fallback policy in P4.6 |
| `frontend/js/core/page-locales.js` | 2,265 | Same as above; avoid manual all-locale expansion |
| Credential/dashboard/identity JS | 908–1,174 each | Workflow-focused changes in P3/P4, not wholesale rewrite |

## Risk-to-Plan Mapping

| Risk | Severity for target | Fixed owner |
| --- | --- | --- |
| Enterprise scope keeps expanding | Critical delivery risk | Constraints + P0.3/P0.5 |
| Unrecoverable/corrupt self-host data | High | P1.4/P1.5/P5.1 |
| Secret leakage through UI/export/log | High | P1.4/P4.2–P4.5/P5.2 |
| Protocol transformation damages output | High | P2.3/P2.4/P2.6 |
| Wrong provider action on mixed selection | High | P2.1/P3.4/P3.5 |
| Installation/configuration drift | High | P1.1–P1.3 |
| Frontend workflows regress silently | Medium-high | P3.2/P5.4 |
| Identity complexity blocks single user | Medium | P3.1/P4.6/P5.2 |
| Accounting/unknown pricing is misleading | Medium-high | P4.4/P5.3 |
| Oversized modules increase change risk | Medium | P0.4 and task-local extraction only |
| Community locale copy is semantically weak | Medium | P4.6; non-blocking beyond EN/VI |
| HA/Helm state is mistaken for supported | Medium-high | P0.1/P0.3/P5.6 |

## Explicit Preserve/Simplify/Add Decisions

### Preserve and finish

- Existing public protocols, provider families, credential operations, routing strategies, quality
  controls, virtual keys, usage/cost, audit/traces, local auth, optional OIDC, themes, and SQLite.
- Existing security work that remains beneficial in standalone mode.

### Simplify or demote

- Redis coordination, multi-replica activation, and Kubernetes to Experimental.
- PostgreSQL to Advanced, MongoDB to Compatibility.
- Identity to optional Team access and audit/traces/logs to one Activity navigation destination.
- Configuration into Basic/Advanced/Experimental sections.
- Translation promise to curated English/Vietnamese plus community compatibility locales.

### Add because production needs them

- Playground, versioned backup/restore, update/rollback, first-run preflight, typed configuration
  registry, support-tier registry, browser journey tests, deterministic protocol corpus, and fixed
  small-team reliability/performance evidence.

### Do not add in R1

- Commercial tenancy/billing, organization hierarchy, SAML/SCIM, arbitrary plugins, new storage or
  telemetry backends, more providers, frontend framework migration, active-active HA, or longer and
  broader load matrices.

## Repository State Caution

At audit time the branch was ahead of its remote and two `.superpowers` implementer reports were
already deleted in the working tree. Those deletions are treated as unrelated user-owned changes
and are not part of the plan rewrite. Planning files remain uncommitted pending review.
