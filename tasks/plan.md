# Populated-instance audit — round 2 (2026-09-16)

Completed: `docs/audits/populated-instance-round-2-2026-09-16.md`. All POP items
verified; preserve the report's synthetic-data and browser coverage limitations.

User authorizes an end-to-end UI/workflow audit and fixes with the full synthetic
dataset. Sequential, no subagents/real provider calls/Docker/commit. Preserve the
32px controls, 36px sidebar, provider-owned capabilities and existing dirty work.
Operate-mode refinement of the existing identity, not a redesign.

1. POP-1: Baseline all 13 pages plus auth/sidebar, six sizes/two themes; expand
   23 provider workspaces and 23 credential management variants at desktop/mobile.
   Bounded discovery pass: <=400 scans, <=18 minutes. Read-only against marked demo.
2. POP-2: Exercise data workflows on disposable synthetic storage: filters/search/
   pagination/selection, credential edit/toggle/batch/import/confirm, virtual-key
   lifecycle, identity permissions, model route/quality/settings, logs/trace/audit,
   backup validation, Playground, skeleton/error/retry/toast/focus. Never call real
   accounts. Add failing regressions for verified defects, then fix one batch.
3. POP-3: Confirm affected layouts/flows once; no open-ended visual polish. Run
   focused contracts, localization and fast checks; document coverage, known
   limits, measurements and remaining findings. Reload the offline preview only.

Acceptance: no known blocking errors in tested populated journeys; no measured
overflow/contrast/control-name defects; provider filters cover the actual registry;
bounded lists, truthful quota/usage and safe credential/secret handling maintained.
Screenshots supplement deterministic checks. External/provider correctness, other
browsers and real assistive devices are explicitly not certified by fake data.

# Full-application synthetic dataset (2026-09-16)

Completed: final data in `temp/round2-full-ready/credentials`; candidate in
`temp/round2-full` preserved with browser evidence. Report:
`docs/audits/round-2-full-synthetic-data.md`. Known UI findings deferred to round 2.

Extend the approved credential demo to every existing Polaris surface, using a
NEW isolated directory `temp/round2-full/credentials`. Keep the earlier demo and
operator data intact. No subagents, production code changes, deployment or commit.

1. DEMO-FULL-1 — Seed linked governance data: virtual keys/lifecycle, model route,
   blacklist, custom AI Quality policy, management identities and safe settings.
   Acceptance: actual stored domain records validate; no external login enabled.
2. DEMO-FULL-2 — Seed 30 days of usage, costs, request decisions and audit events,
   linked to the same credentials, models and key IDs; create a real encrypted
   backup and synthetic runtime log. Acceptance: totals reconcile, joins resolve,
   and the real repositories/API can read every data family.
3. DEMO-FULL-3 — Extend offline preview only where data is runtime-owned (routing,
   sessions and Playground). Acceptance: no outbound IO; authentication remains
   enforced; generated responses are explicitly synthetic, not provider evidence.
4. DEMO-FULL-4 — Verify all 13 page fragments plus login/setup in Chromium, including
   key/credential/trace/audit details, backup validation and a bounded Playground
   request. Desktop light/dark and mobile, not the full round-2 visual audit.

Verification: regression-first focused tests, Ruff, SQLite integrity and consistent
totals, authenticated HTTP checks, bounded browser smoke with no browser API mocks.
Preserve UI code and all earlier uncommitted work. External OIDC/OAuth/telemetry
remain offline; static settings/about/setup screens require no invented records.

# Completed — synthetic database preparation for round 2 (2026-09-16)

Create persisted SQLite records for all 23 console provider variants, with 1–7
fictional credentials each. Preserve live storage and all existing changes.

1. Test non-overwrite protection and seed through the existing SQLite manager.
2. Include distinct OAuth/API-key identities, models, health states and persisted
   synthetic OAuth quota snapshots. Never use a real account or secret.
3. Provide a loopback-only offline preview launcher; keep production paths intact.
4. Verify database integrity, counts, safe authenticated reads and outbound denial.

Acceptance: actual persisted rows, every variant represented, counts in range,
API keys without invented email, no live provider calls, no existing DB overwrite.
No round-2 audit, Docker deployment or commit in this preparation task.

Result: real isolated SQLite database with 87 credentials across 23 variants,
offline preview, nine passing focused tests and authenticated HTTP verification.
See `docs/audits/round-2-synthetic-database.md` for boundaries and local commands.

# Completed — empty-instance audit, round 1 (2026-09-16)

User-approved scope: inspect all Polaris surfaces without domain data, repair
verified usability/functionality defects, and leave populated-account testing to
round 2. Preserve existing uncommitted work and the 32px/36px density decisions.
No subagents, live credentials, production changes, deployment or commits.

1. Inventory routes/disclosures/dialogs and inspect a fresh disposable SQLite
   runtime. Reuse the 16-surface × 6-viewport × 2-theme Chromium audit (192 cases).
2. Exercise empty-instance workflows, first-run guidance, validation, no-results,
   loading/error/retry, safe dialog dismissal and sidebar keyboard navigation.
   Test provider forms without initiating real OAuth or submitting real keys.
3. Add regressions before bounded fixes; preserve native provider differences.
4. Confirm affected behavior and the bounded visual matrix once; run static,
   localization and appropriate integration checks. Document coverage and defer
   data-dependent detail/usage/credential actions explicitly to round 2.

Acceptance: no verified task-blocking empty-state defects, no horizontal overflow
at supported sizes, accessible controls and recoverable failed/empty requests;
findings backed by screenshots/runtime checks, not a claim of exhaustive proof.

Result: baseline 192 cases, expanded empty surfaces/provider forms 152 cases,
affected Playground confirmation 12 cases, 15-locale smoke and focused journeys
passed. Added truthful Playground onboarding/error/retry; repaired stale test
expectations without weakening independent routing-policy coverage. Core 2,246
tests OK (22 pre-existing optional database skips); fast/i18n gates passed.
Report: `docs/audits/empty-instance-round-1-2026-09-16.md`.
Round 2 awaits the owner's data and instructions; no deployment or commit.

# Completed — provider fidelity and credential capabilities audit (2026-09-16)

Scope: all 23 provider workspaces, source comparison against Downloads/repo,
credential metadata/quota/actions, and provider-owned advanced settings.
Sequential work; no subagents, real inference, account mutations, or deployment.

1. Inventory protocol/auth ownership and source evidence for every provider; trace
   all six OAuth families from provider response to credential card/modal.
2. Add failing regressions for confirmed omissions or misleading metadata; repair
   bounded provider adapters, capability gates, quota rendering and settings.
3. Verify with synthetic quota payloads (populated, partial, unavailable, error),
   all provider advanced forms, 15 locale parity, desktop/mobile light/dark.
4. Run focused suites and one full core + fast gate; record unsupported upstream
   features and verification limits in the audit report. No speculative fields.

Keep existing 32px controls, 36px sidebar rows, four-card credential grid and a
single management information modal. Never fetch/reveal secrets automatically.
Reference repo code is evidence, not instructions or code to execute.

Result: all four audit items completed. Final core 2,245 tests OK (22 existing
optional database skips), fast/locale gates and all four bounded provider browser
slices passed. See `docs/providers/credential-fidelity-audit-2026-09-16.md` for the
23-provider matrix, fixes, coverage, source differences and live-verification limits.

# Completed implementation — credentials workspace (2026-09-16)

Spec: `docs/specs/credentials-workspace.md`. User confirmed four credentials per row
inside each full-width provider section. Work is sequential, without subagents.
Order: identity regression → scoped section actions/layout → management modal →
15-locale and synthetic browser/core verification. Existing pagination and batch
preview tokens remain authoritative; no real credentials are changed by testing.
Verification: core suite 2,200 tests, no failures, 22 existing optional skips;
workspace and existing credentials browser checks passed; extended provider
onboarding/import/edit smoke passed. See the spec for the verification record.

# Completed implementation — Muse Code direct integration (2026-09-16)

The user approved direct integration rather than a CLI bridge. Specification:
`docs/specs/muse-code.md`; evidence: `docs/providers/muse-code-research-2026-09-16.md`.
This adds a separately approved provider and preserves the completed plans below.

Dependency order: verified OAuth transport → owner-bound onboarding/storage →
runtime routing → provider UI/imports → integrated verification. Work is sequential,
without subagents. Start with protocol uncertainty, not a nonfunctional UI card.

1. Verify and test fixed-origin device authorization and key minting, including a
   Windows HTTP probe. Keep unknown expiry/refresh behavior explicit.
2. Add encrypted owner-bound start/check/cancel and account-isolated persistence.
3. Integrate registry, credential import/refresh/discovery and sanitized diagnostics.
4. Add runtime transport and subscription observations without implicit billing
   fallback; preserve native replay/tool/cancellation semantics.
5. Add the provider workspace and translations using existing components; test the
   entire add/import/re-auth journey before activating its card.
6. Run focused/core/quality/browser gates and report live limitations. No deployment
   or push; new inference tests require a separate allowance.

Risk gates: stop on an unverified required protocol, fail closed on subscription
eligibility, and do not substitute a CLI bridge or an API-key provider. Each slice
gets focused tests before advancing; full-provider readiness is not inferred from
individual successful requests.

Results and operational limits: `docs/providers/muse-code-verification-2026-09-16.md`.

---

# Completed work — Provider conformance audit (2026-09-16)

User-authorized comparison of the existing 22 provider workspaces against the
repositories in `C:/Users/nben6/Downloads/repo`, with evidence-backed repairs.
This does not reopen or renumber the completed R1 plan below.

1. Inventory every provider's authentication, upstream protocol, discovery,
   import schema, advanced settings and runtime integration. Record reference
   implementation paths and official protocol sources in
   `docs/providers/conformance-audit-2026-09-16.md`.
2. Review OAuth/account adapters, then API-key/local adapters, then the shared
   routing/streaming boundary. For each confirmed defect, add a failing test
   before the smallest focused repair. Do not copy reference-repo code blindly.
3. Check onboarding/import/settings parity and run focused provider tests, the
   core suite and isolated browser smoke. Clearly distinguish deterministic
   checks from live provider verification, which requires authorized accounts.

Acceptance: all 22 providers have an evidence entry; confirmed defects have
regression coverage; unsupported/unverified capabilities are stated accurately;
secrets and existing credential data remain untouched. No new provider, dependency,
automatic OAuth completion, Docker deployment or GitHub push is authorized here.
Work is sequential without subagents. Existing uncommitted work is preserved.

Completed: evidence and verification results are recorded in
`docs/providers/conformance-audit-2026-09-16.md`. Live upstream certification
remains outside this source-and-contract audit.

---

# Polaris — Fixed Production Self-Hosted Plan R1

## Control Record

- Plan ID: `PROD-SELFHOST-R1`
- Frozen: 2026-09-08
- Target: production self-hosting for one person or a trusted team of approximately 1–20 people.
- Structure: exactly 6 phases and 36 implementation tasks.
- Supersedes: the unfinished enterprise Wave 4/5 activation path.
- Quality contract: `CONSTRAINTS.md`
- Product specification: `docs/specs/production-self-hosted.md`

This plan is deliberately finite. Task IDs, phase count, and denominator may not expand. A defect
found during a task is part of that task. A desirable improvement that is not required by an
acceptance criterion goes to the post-R1 backlog.

## Change Rules

The plan changes only under the four conditions in `CONSTRAINTS.md`. An allowed change must be
recorded here as `CR-###`, replace equivalent scope where possible, state evidence and impact, and
receive user approval. No Wave, A/B/C suffix, hidden checklist, or second denominator is permitted.

There are no approved change requests.

## Execution and Verification Rules

1. Work in task-ID order unless a dependency explicitly allows adjacent tasks to be combined.
2. One task is one reviewable commit or a small ordered commit set with the task ID in each message.
3. Prefer at most five hand-edited production files per task. Generated locale/catalog changes and
   directly corresponding tests may exceed that count but do not expand scope.
4. Before editing, record the task's exact affected contracts. After editing, run focused tests.
5. At each phase exit, run only the listed phase gate. Run the complete release gate once in P5.6.
6. Do not rerun a long matrix to investigate a known focused failure.
7. Existing unrelated user changes are never absorbed into a task commit.
8. Cross-model review occurs at most once for P1.4/P5.2 security-critical changes unless requested.

## Phase 0 — Scope Reset and a Truthful Baseline

Goal: stop enterprise scope from controlling delivery and make support tiers mechanically clear.

### P0.1 — Capability registry and support tiers

- Scope: create one machine-readable registry for core, advanced, compatibility, and experimental
  capabilities; expose a read-only authenticated summary to the console.
- Include: standalone, storage backends, team login, exporters, coordination, Kubernetes, provider
  families, and public protocols.
- Acceptance: default runtime reports only core capabilities as active; experimental capabilities
  cannot become active through an accidental environment combination.
- Verification: registry schema/unit tests and startup-mode contract tests.
- Depends on: plan approval.

### P0.2 — Product terminology and navigation inventory

- Scope: enumerate all active pages, routes, settings, environment variables, README claims, and
  translations; map each to its support tier and intended owner journey.
- Remove from active copy: “enterprise-ready”, HA claims, governance-first framing, and duplicate or
  misleading setup instructions.
- Acceptance: one checked inventory has no orphan page or advertised feature without a tier.
- Verification: documentation link check, route/page inventory test, English/Vietnamese term audit.
- Depends on: P0.1.

### P0.3 — Isolate unfinished HA work

- Scope: keep existing coordination code and tests but move them behind explicit experimental
  activation; remove two-replica evidence and W4-C from normal release/resume gates.
- Keep: one-worker/one-replica guards, empty activation allowlist, fail-closed behavior.
- Acceptance: a default install never asks for Redis or HA evidence; experimental tests are clearly
  named and independently runnable; no production claim is made for coordinated mode.
- Verification: default startup without Redis, explicit experimental-start rejection, CI test-list
  audit.
- Depends on: P0.1.

### P0.4 — Risk and maintainability baseline

- Scope: record large modules, duplicated storage implementations, Pydantic deprecations, broad
  exception suppressions, skipped/live tests, and frontend test gaps.
- Acceptance: every high-risk item is assigned to an existing P0–P5 task or the post-R1 backlog; no
  refactor is authorized solely by file size.
- Verification: static inventory commands are reproducible and saved in the task report.
- Depends on: P0.2.

### P0.5 — Fast, phase, and release gates

- Scope: define commands for focused task checks, phase checks, and the single full release gate;
  classify optional provider/backend tests separately.
- Include: backend lint/format, dependency audit, config validation, JS syntax, browser smoke,
  container smoke, translation audit, and whitespace.
- Acceptance: contributors can select a gate without running HA matrices or the entire suite after
  every edit; CI names show what is required versus optional.
- Verification: execute the fast gate and dry-run/list the release suites.
- Depends on: P0.3, P0.4.

### P0.6 — Compatibility and deprecation guard

- Scope: capture current public inference routes, management routes used by the console, config
  aliases, database versions, and generated client examples before simplification.
- Acceptance: a versioned fixture detects accidental removal or semantic break; planned UI merges
  retain redirects/compatibility paths where required.
- Verification: route/schema snapshot tests and upgrade fixture load.
- Depends on: P0.5.

Phase 0 exit gate: focused P0 tests, current full unit suite once, configuration inventory, and
documentation/translation checks. No HA topology run.

## Phase 1 — Predictable Installation, Configuration, and Recovery

Goal: make the canonical single-machine deployment safe to install, understand, back up, and undo.

### P1.1 — Authoritative typed configuration schema

- Scope: consolidate environment parsing and setting metadata into one schema with Basic,
  Advanced, and Experimental groups; identify restart-required/read-only fields.
- Acceptance: invalid values fail with actionable messages; unknown `POLARIS_*` keys warn; generated
  environment reference and Settings metadata cannot drift from runtime defaults.
- Verification: boundary config tests and `.env`/Compose parity test.
- Depends on: P0.6.

### P1.2 — Minimal canonical Docker Compose profile

- Scope: make the default Compose file contain only common production controls while preserving
  read-only filesystem, no-new-privileges intent, healthcheck, log rotation, and durable volumes;
  move optional services/options to profiles or override examples.
- Acceptance: `docker compose up -d` needs no database/Redis; data survives recreate; readiness and
  graceful shutdown work; secrets are not baked into the image.
- Verification: clean container build, fresh-start smoke, restart/recreate persistence test.
- Depends on: P1.1.

### P1.3 — First-run setup and preflight

- Scope: make setup verify data writability, secret strength, port/base URL, secure-cookie/reverse
  proxy expectations, and existing installation state; provide recovery-safe owner creation.
- Acceptance: fresh, resumed, configured, and invalid states give one clear next action; setup
  tokens/passwords never appear in URL/history/logs.
- Verification: setup API tests, container smoke, 360/1440 keyboard browser flow.
- Depends on: P1.2.

### P1.4 — Versioned backup, validation, and restore

- Scope: add a passphrase-encrypted portable backup/restore for core SQLite state, configuration
  metadata, credentials, routes, virtual keys, identity, quality policy, and ledgers; add a separate
  sanitized export that excludes restorable secrets; exclude raw logs by default.
- Include: manifest/version/hash, dry run, conflict policy, pre-restore snapshot, atomic replacement,
  and audit event.
- Acceptance: the passphrase is never stored or logged; corrupted/incompatible archives fail
  closed; a verified encrypted round trip restores functional routing and access without partial
  state; a sanitized export contains no usable credential or key.
- Verification: golden archive, corruption/traversal/oversize tests, container round trip, one
  adversarial security review.
- Depends on: P1.3.

### P1.5 — Update and rollback workflow

- Scope: document and script pull/preflight/backup/update/health-check/rollback for Compose without
  silently using floating state.
- Acceptance: a failed health check restores the previous image and state snapshot; dry-run shows
  actions; operator data remains recoverable.
- Verification: two-version synthetic upgrade and forced-failure rollback rehearsal.
- Depends on: P1.4.

### P1.6 — Supported install matrix

- Scope: verify the canonical Compose path on Windows Docker Desktop/WSL2 and Linux; document macOS
  Docker as equivalent with known differences; classify other scripts/platforms as compatibility.
- Acceptance: prerequisites to first healthy authenticated console form one linear guide; ARM64
  status is stated from evidence, never implied.
- Verification: clean-install evidence for available canonical hosts and commands for the remaining
  documented manual check.
- Depends on: P1.5.

Phase 1 exit gate: clean install, first-run, persistent restart, backup/restore, forced rollback,
secret scan, and targeted browser smoke.

## Phase 2 — Gateway Correctness and AI Output Quality

Goal: make every advertised request path predictable and make transformations safe and explainable.

### P2.1 — Provider capability matrix

- Scope: normalize every current provider/auth variant into one capability contract covering add,
  verify, test, refresh, quota, model discovery, inference protocols, disable, export, and delete.
- Acceptance: API and UI derive valid actions from the same contract; unsupported operations fail
  with a stable typed error.
- Verification: table-driven matrix tests for every advertised provider variant.
- Depends on: P0.6.

### P2.2 — Connection tests and actionable provider errors

- Scope: standardize credential, permission, quota/rate limit, network/proxy/TLS, upstream, invalid
  model, and unsupported-operation outcomes with safe remediation.
- Acceptance: raw secret/upstream bodies are redacted; provider-specific useful status survives;
  test requests are bounded and cancelable.
- Verification: deterministic adapter fixtures and console contract tests.
- Depends on: P2.1.

### P2.3 — Cross-protocol contract corpus

- Scope: create shared fixtures for text, multimodal input, system messages, tools, structured
  output, reasoning metadata, usage, finish reasons, and normalized errors across existing public
  protocols.
- Acceptance: every advertised conversion has an explicit supported/translated/rejected result;
  unknown fields do not silently corrupt requests.
- Verification: round-trip/golden tests for OpenAI Chat/Responses, Anthropic, Gemini, and Vertex.
- Depends on: P0.6.

### P2.4 — Streaming, cancellation, timeout, and retry semantics

- Scope: audit disconnect propagation, partial streams, heartbeat behavior, timeout ownership,
  retry eligibility, duplicate delivery risk, and terminal usage/trace settlement.
- Acceptance: no retry after user-visible output unless explicitly safe; canceled/failed requests
  release reservations and close traces once; streams do not buffer unbounded output.
- Verification: deterministic fault-injection tests for every public streaming family.
- Depends on: P2.3.

### P2.5 — Routing, fallback, cooldown, and health

- Scope: unify eligibility, strategy selection, retry/fallback order, provider cooldown, route
  health, and explanation metadata for standalone runtime.
- Acceptance: no eligible route produces an actionable error; selection is reproducible with a
  seeded fixture; unhealthy credentials recover according to bounded policy.
- Verification: scenario matrix for balanced/priority/weighted/least-latency/lowest-cost.
- Depends on: P2.1, P2.4.

### P2.6 — Compression and quality-policy hardening

- Scope: validate global/key/request precedence, explicit off switch, safe presets, token estimates,
  invariant preservation, anti-truncation, and fail-open-to-uncompressed behavior.
- Acceptance: system/tool/current-request structures are never damaged; each action has before/after
  estimate and reason; quality regressions in a fixed corpus block the task.
- Verification: adversarial conversation corpus, property-style invariants, protocol fixtures.
- Depends on: P2.3.

Phase 2 exit gate: provider matrix, protocol corpus, streaming fault suite, routing scenarios, AI
Quality corpus, and one end-to-end request per public protocol against deterministic upstreams.

## Phase 3 — Coherent Core Console

Goal: turn existing pages into a clear daily workflow without a framework rewrite.

### P3.1 — Navigation and conditional complexity

- Scope: implement the specification's information architecture; create Activity tabs; show Team
  access only when relevant; move advanced/experimental settings out of the primary journey.
- Acceptance: every existing feature has one discoverable home; compatibility URLs continue to
  work; mobile navigation and focus order are correct.
- Verification: route/navigation DOM tests and 360/1440 browser smoke.
- Depends on: P0.2, P0.6.

### P3.2 — Shared page states and accessible interaction

- Scope: standardize loading/skeleton, empty, error/remediation, stale data, success toast, dialogs,
  tables/cards, pagination, destructive confirmation, and reduced-motion behavior.
- Acceptance: no core page uses a blank state or browser-native alert for workflow feedback; common
  components meet keyboard/focus/name/contrast requirements.
- Verification: component DOM tests plus automated accessibility smoke on representative pages.
- Depends on: P3.1.

### P3.3 — Production dashboard

- Scope: prioritize readiness, provider/credential incidents, request/error/latency trends,
  usage/cost, recent activity, and quick actions; demote enterprise SLO jargon.
- Acceptance: first-time, healthy, degraded, and no-provider states each identify the next action;
  all list queries are bounded.
- Verification: state fixtures, responsive browser screenshots, request-count assertion.
- Depends on: P3.2.

### P3.4 — Provider onboarding

- Scope: rebuild provider cards/forms around capability metadata, progressive disclosure, field
  validation, connection test, model discovery, and remediation.
- Acceptance: every advertised provider variant can be added/edited/tested/disabled/removed through
  the UI using only fields it actually supports.
- Verification: table-driven DOM/browser workflows with mocked provider outcomes.
- Depends on: P2.1, P2.2, P3.2.

### P3.5 — Credential fleet operations

- Scope: retain faceted filters, stable pagination/selection, common-action calculation, preview,
  bounded batches, results, quota/reset, cooldown, and per-credential diagnostics; simplify labels.
- Acceptance: mixed-provider selection never offers an invalid action; all-results operations show
  exact query/impact before execution; refresh preserves context.
- Verification: mixed-provider browser matrix and destructive-action safety tests.
- Depends on: P3.4.

### P3.6 — Models and routing workflow

- Scope: unify discovered models, virtual routes, fallback ordering/weights, strategy, health,
  validation, and a “test in Playground” handoff.
- Acceptance: users can create, validate, edit, test, and delete a route without manually copying a
  provider model ID; conflicts and temporarily unavailable models are explained.
- Verification: route lifecycle browser test and routing API contract tests.
- Depends on: P2.5, P3.4.

Phase 3 exit gate: authenticated browser matrix for all Phase 3 journeys at 360/768/1024/1440,
light/dark/system, keyboard-only pass, clean console, and English/Vietnamese copy review.

## Phase 4 — Complete Product Workflows

Goal: fill the important gaps and consolidate operational/security workflows.

### P4.1 — AI Quality console completion

- Scope: present safe presets, explicit compression toggle, thresholds, cache/guardrail tradeoffs,
  precedence, restart/live behavior, synthetic preview, and saved-policy revision conflicts.
- Acceptance: the user can predict whether a request will be transformed; risky combinations show
  a specific warning; disabling compression is unambiguous.
- Verification: preset/preview DOM tests, quality-policy API tests, responsive browser flow.
- Depends on: P2.6, P3.2.

### P4.2 — Playground backend boundary

- Scope: add an authenticated, rate/body/time-bounded Playground request boundary that reuses the
  real gateway path and returns safe request/route/quality metadata.
- Acceptance: no provider credential is returned; cancellation propagates; errors match public API
  semantics; raw request/response content is not persisted by default.
- Verification: auth, bounds, cancellation, streaming, redaction, and audit tests.
- Depends on: P2.4, P2.5, P2.6.

### P4.3 — Playground interface

- Scope: add protocol/model/stream controls, bounded message editor, parameters, output stream,
  cancel, metadata, error view, compression preview link, and sanitized cURL/SDK copy.
- Acceptance: first useful test needs no external client; copied examples use a key placeholder;
  one in-flight request is cancelable; prompt history is memory-only by default.
- Verification: end-to-end browser flow for success/stream/error/cancel and XSS payload fixtures.
- Depends on: P3.6, P4.1, P4.2.

### P4.4 — Access lifecycle completion

- Scope: simplify root/client guidance and retain full virtual-key create/reveal/use/edit/rotate/
  revoke lifecycle, model/scope restrictions, expiry, rate/budget, last use, and pricing policy.
- Acceptance: secrets are shown once; destructive actions and revision conflicts are safe; client
  examples work against the selected protocol without leaking the root key.
- Verification: lifecycle browser test, concurrency/budget tests, DOM secret-retention check.
- Depends on: P2.3, P3.2.

### P4.5 — Unified Activity

- Scope: combine request traces, audit/security events, and runtime logs as tabs with common filters,
  request-ID pivots, bounded detail, retention/export, redaction, and helpful empty/error states.
- Acceptance: the user can move from a dashboard failure to route decision and relevant log/event;
  prompt bodies and secrets remain absent; exports are bounded.
- Verification: correlated fixture/browser flow, redaction tests, export bounds tests.
- Depends on: P3.1, P3.3.

### P4.6 — Settings, Team access, About, and localization

- Scope: render typed config groups, live/restart/read-only state, backup/update entry points, optional
  OIDC/roles/recovery, accurate version/support tiers, and complete English/Vietnamese text.
- Acceptance: disabled Team access does not dominate navigation; local recovery remains visible;
  all settings map to the authoritative schema; compatibility locales have complete fallback keys.
- Verification: config/UI parity, identity browser smoke, locale completeness and semantic review.
- Depends on: P1.1, P1.4, P1.5, P3.1.

Phase 4 exit gate: all nine required user journeys in `CONSTRAINTS.md`, browser accessibility smoke,
secret/redaction scan, and English/Vietnamese semantic audit.

## Phase 5 — Operational Hardening and Release

Goal: close production risks, prove the fixed target once, and ship with honest support boundaries.

### P5.1 — Storage tiers and migrations

- Scope: make SQLite the documented core authority, verify backup/locking/corruption behavior;
  qualify PostgreSQL as optional advanced; freeze MongoDB at compatibility; clean remaining schema
  and Pydantic deprecations encountered in these paths.
- Acceptance: forward upgrade and supported rollback preserve core data; optional backend outage
  posture is explicit; no experimental parity gate blocks SQLite production.
- Verification: migration fixtures, SQLite recovery tests, opt-in PostgreSQL contract suite, MongoDB
  compatibility smoke.
- Depends on: P1.4, P4.4, P4.5.

### P5.2 — Authentication and security closure

- Scope: review local login/setup/recovery, sessions, virtual keys, optional OIDC/roles, CORS/proxy,
  uploads/imports, SSRF, XSS/CSRF, rate limits, secrets, dependencies, and container posture.
- Acceptance: no critical/high unresolved finding; all medium findings have an accepted fix or
  documented bounded risk; local-owner recovery is proven independently of OIDC.
- Verification: targeted adversarial tests, dependency/secret scans, one cross-model review and
  reconciled finding table.
- Depends on: P1.3, P1.4, P4.3, P4.4, P4.6.

### P5.3 — Usage, cost, and observability closure

- Scope: verify settlement across success/error/cancel/cache/retry, pricing freshness/unknown policy,
  bounded metrics, trace/audit retention, and opt-in exporters.
- Acceptance: hard budgets never price unknown use as zero; request IDs correlate decisions without
  prompt storage; disabled exporters make no external connection.
- Verification: accounting scenario matrix, cardinality bounds, exporter-off network assertion.
- Depends on: P2.4, P4.5, P5.1.

### P5.4 — Browser test harness and CI balance

- Scope: add a minimal maintained browser/DOM harness for critical journeys without adopting a
  frontend framework; split required versus optional CI; cache dependencies and preserve container
  smoke.
- Acceptance: every required journey has an automated smoke; JS syntax alone is no longer the only
  frontend gate; CI does not run experimental HA matrices.
- Verification: clean CI-equivalent run and intentional-failure proof for one frontend assertion.
- Depends on: P3.1–P4.6.

### P5.5 — Fixed reliability and performance evidence

- Scope: run the exact 10-minute, 10 RPS, 16-concurrency deterministic profile; measure gateway p95,
  errors, memory trend, queue/bounds, dashboard usable time, and graceful restart behavior.
- Acceptance: meet `CONSTRAINTS.md`; diagnose failures with focused tests only; do not add load
  levels, replicas, databases, or longer soak durations to R1.
- Verification: versioned command/config/result artifact tied to the candidate commit.
- Depends on: P5.3, P5.4.

### P5.6 — Release candidate, documentation, and handoff

- Scope: reconcile README/config/reference/runbooks, install/update/backup/troubleshooting guides,
  capability tiers, known limitations, changelog/version, images, and release artifacts.
- Acceptance: run the complete required gate once on an immutable candidate; publish no unsupported
  enterprise/HA claim; all 36 tasks and required evidence are traceable.
- Verification: full backend/contract/container/browser/security/config/i18n gate, clean-install
  rehearsal, release checklist, rollback command, and final user acceptance.
- Depends on: all preceding tasks.

Phase 5 exit gate: P5.6 is the release gate. Experimental HA/Kubernetes and real-provider breadth
are reported separately and cannot change the R1 result.

## Post-R1 Backlog (Non-blocking)

- Evaluate whether coordinated Redis/HA and Helm have enough real demand to retain or remove.
- Reassess MongoDB support based on actual users and migration needs.
- Editorial review for community locales beyond English/Vietnamese.
- ARM64 image qualification where provider SDK dependencies permit it.
- Semantic compression or model-generated summaries only with a separately approved quality eval.
- Additional providers, protocols, frontend framework, commercial tenancy, or organization features.

These entries are intentionally not tasks and cannot be pulled into R1 without an approved change
request.

## Change Request Log

### Polaris 1.0.0 pre-release review — 2026-09-17

User requested a whole-product review and repair, with particular attention to credential
cards/modals, density, business workflows, accurate information and unnecessary scrolling.
This is a bounded verification/repair pass of existing PB4/PB5/PB7 capabilities, not a new
product phase. Do not publish, tag, push, rewrite history or use live provider accounts.

Execution: preserve the dirty worktree; test writes only in disposable databases. Use the
current monochrome identity, 32px controls and 36px sidebar items. Preserve four credential
cards per wide-screen row, provider sections and the actual provider-specific data contracts.
No empty filler, invented metrics or global scrollbar-hiding workaround.

Acceptance / ordered slices:

1. Inventory and baseline: all 13 console routes/subviews, setup/login/callback, 23 provider
   workspaces, credential variants and shared modal families. Inspect populated and empty
   states, keyboard/focus, names, contrast, scrolling and representative error/loading states.
   Record measured issues and remaining external/CI limits before editing production UI.
2. Repair credential scanning and management: compact purposeful card structure, aligned
   provider actions, content-driven detail layout and one necessary dialog scroll surface.
   Preserve operations and fields; add regressions before behavioral fixes. Likely files:
   credential cards/management JS, credential CSS and focused console tests.
3. Repair shared and workflow defects found in slice 1, in small independent increments:
   shell/dialogs first, then affected page/logic owners. Preserve accessibility and all
   15 locales; no unrelated subsystem rewrite. Each increment has focused tests.
4. Confirm: one batched visual confirmation after fixes, focused workflows, core suite,
   fast/release gates, dependency audit and 120-second routine reliability profile where
   available. Container/live-provider evidence must be reported separately, never inferred.

Visual budget: one baseline and at most one post-fix matrix per surface. Existing bounded
empty (152 cases) and populated (up to 400 cases, 18 minutes) harnesses cover desktop/mobile,
intermediate widths, landscape and both themes; add only previously uncovered states to the
same baseline. No endless screenshot/polish loop. Final handoff includes exact evidence,
unresolved release blockers and the updated local preview, not an unconditional release claim.

### Synthetic database fidelity — 2026-09-17

User requested actual persisted demo-data correction across Polaris; production UI,
real credentials and production storage are out of scope. Preserve the existing demo
login and keep a recoverable database backup. Synthetic amounts/identities are not
live account facts: provider field shapes must have source evidence and pass the
production parsers. Missing metadata stays missing.

1. Credential/catalog/quota slice: replace generic OAuth fields, invented models and
   tiers; store raw, source-indexed provider fixtures and normalize with production
   code. Verify provider variants, normalizers and optional/unknown facts in unit tests.
2. Activity slice: reconcile ledger, traces, credential counters, key lifecycle and
   policy decisions; use real billing/pricing contracts without invented charges.
   Verify relational and temporal invariants against persisted SQLite data.
3. Runtime/data slice: use production management routes with offline provider-boundary
   fixtures, safely update the marked preview database, and verify HTTP data plus
   representative management pages. Record coverage and evidence gaps explicitly.

Checkpoints: focused tests after each slice; final integrity check, existing demo
regressions, one preview listener, real HTTP/browser checks. No outbound model calls.

### CR-002 — Kiro OAuth and provider onboarding consistency (2026-09-15)

User approved the follow-up provider audit plan and explicitly required sequential work without
subagents. This bounded repair supersedes key-only Kiro presentation and online-validation-at-import
behavior; it does not expand the completed 36-task R1 baseline. Existing API keys remain supported.
Contracts, implementation order, user workflow and test boundaries are recorded in
`docs/specs/provider-auth-consistency.md`. No automatic Docker rollout, push or merge is included.

### CR-001 — Provider ownership and authentication corrections (2026-09-15)

Owner approved the provider audit corrections and parallel implementation. This is a bounded
post-R1 repair of existing capabilities, not a new provider family or change to the completed
36-task baseline. Existing credentials and saved configuration values must be preserved.

Implementation order and contracts:

1. Claude token failures retain transient/permanent classification; save and runtime validate
   the same OAuth destinations. Verify with synthetic 429/503 and malformed-URL regressions.
2. Recognize narrowly defined native Codex/Claude/Grok imports and report offline imports as
   unverified. Preserve existing validation paths and bounded upload limits. Verify parser and
   import/storage tests without real credentials or external calls.
3. Provider settings have one truthful owner: existing Code Assist compatibility and shared
   Google settings belong in Providers; shared streaming/retry switches belong in Settings;
   Grok gets its existing OAuth inference endpoint; Anthropic/xAI shared settings have one editor.
   Verify schema, allowlists, reset isolation, frontend contracts, and environment locks.
4. Ollama honors explicit proxy bypass without globally changing other providers. Verify direct
   and inherited proxy selection with fake transports.
5. Move Antigravity credit editing into its provider workspace; keep pool status and generic
   credential lifecycle actions. Verify selection, authorization, failure, and empty states.
6. Integrate localized UI, normal-weight placeholders, documentation, and bounded isolated
   browser checks across mobile/desktop and both themes. Review security-sensitive changes
   independently before committing; no deployment or upstream account mutation.

Checkpoint after each repair: focused unittest/Node checks and a reviewable commit. Final gate:
combined affected tests, strict locale audit, frontend build, and real-browser ownership checks.
Do not weaken tests, introduce a framework, or broaden OAuth trust to arbitrary hosts.
