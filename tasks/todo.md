# Polaris Production Self-Hosted R1 — Fixed Checklist

Latest guided-install/mobile verification and publication hold:
`docs/releases/1.0.0-readiness.md`, runtime candidate `fec0388`.
The sections below retain earlier audit history, not exact-source CI for that candidate.

## Polaris 1.0.0 pre-release review (PB4/PB5/PB7)

- [x] Baseline inventory: pages, provider workspaces, modal families, workflows, data and release checks.
- [x] Credential cards/provider sections/management: density and interaction repairs with regressions.
- [x] Shared layout and business defects: scoped fixes, no hidden overflow or invented data.
- [x] Confirmation matrix and release evidence: tests, runtime, security/dependencies, performance and limits.

Evidence: `docs/audits/prerelease-1.0.0-2026-09-17.md`. Core 2,288 tests (22
existing optional/live-backend skips), fast/dependency/i18n gates, 9/9 journeys,
384 populated + 152 empty cases and 15-locale matrix. Two authorization defects
and the retired verify alias fixed with HTTP regressions; permission-aware UI
and credential layout confirmed. Preview 4285 restarted with its existing 89
synthetic credentials. Review complete, **release sign-off pending** Docker/CI,
the exact-candidate routine benchmark and the other evidence limits in the report.

## Populated-instance audit — round 2

- [x] POP-1: Bounded populated-page/provider/credential baseline and findings.
- [x] POP-2: Disposable workflows, regression-first fixes and state coverage.
- [x] POP-3: Affected confirmation, quality/localization checks and report.

Evidence: `docs/audits/populated-instance-round-2-2026-09-16.md`; 384-case final
layout matrix, nine workflow checks, 19 browser suites, 53 focused tests and fast
gate. Three production defects and one synthetic-preset defect fixed. Preview
4285 updated, actual data preserved, no Docker/commit or provider calls.

## Full-application synthetic dataset

- [x] DEMO-FULL-1: Persist linked governance/settings/identity/virtual-key examples.
- [x] DEMO-FULL-2: Persist usage, traces, audits, logs and a validated backup.
- [x] DEMO-FULL-3: Cover runtime-owned preview data without outbound IO.
- [x] DEMO-FULL-4: All-page browser/data checks and coverage documentation.

Evidence: `docs/audits/round-2-full-synthetic-data.md`; final isolated dataset
`temp/round2-full-ready/credentials`, preview 4285. Eleven focused tests, 80 browser
captures and API reconciliation. Known populated UI filter/layout issues recorded
for round 2; no production UI edits in this data-preparation task.

## Synthetic database preparation — round 2

- [x] DEMO-1: Persist 1–7 synthetic credentials for all 23 provider variants safely.
- [x] DEMO-2: Provide isolated offline preview with persisted quota/model facts.
- [x] DEMO-3: Verify integrity, counts, authentication, outbound denial and document use.

Evidence: `docs/audits/round-2-synthetic-database.md`; 87 SQLite credentials,
23 variants, nine focused tests and authenticated runtime reads. No live data touched.

## Empty-instance audit — round 1 (2026-09-16)

- [x] EMPTY-1: Inventory and baseline all routes, themes and responsive sizes.
- [x] EMPTY-2: Exercise first-run/empty/loading/error/dialog flows; record defects.
- [x] EMPTY-3: Regression-first fixes and affected behavior verification.
- [x] EMPTY-4: Bounded confirmation matrix, quality gates and coverage report.

Evidence: `docs/audits/empty-instance-round-1-2026-09-16.md`.
Core 2,246 tests OK (22 existing optional skips); fast and i18n passed.

## Provider fidelity audit (2026-09-16, follow-up)

- [x] AUDIT-1: Source-backed inventory of all 23 providers and six OAuth metadata families.
- [x] AUDIT-2: Regressions and fixes for credential quota/capability/metadata fidelity.
- [x] AUDIT-3: Verify advanced-setting ownership, coverage and persistence.
- [x] AUDIT-4: Synthetic browser matrix, locale/core/fast checks and evidence report.

Evidence: `docs/providers/credential-fidelity-audit-2026-09-16.md`.
Final core: 2,245 tests OK, 22 existing optional database skips; fast, locales and
provider/quota/Muse browser matrices passed. No deployment or live account calls.

## Credentials workspace (2026-09-16)

- [x] CRED-1: Identity fallback distinguishes OAuth/API keys without missing-email errors; regression tests.
- [x] CRED-2: Full-width provider sections, four-column responsive cards, explicitly scoped batch actions.
- [x] CRED-3: Capability-aware management modal and compact quick actions; no automatic secret fetch.
- [x] CRED-4: Fifteen-locale checks, synthetic browser tests, core suite and final review.

## Approved Muse Code direct integration (2026-09-16)

Spec: `docs/specs/muse-code.md`. These tasks do not change completed R1/R2 counts.

- [x] MUSE-1: Verified OAuth boundary and Windows login; synthetic security tests
  in `test_muse_oauth.py`, no real credential persisted by the probe.
- [x] MUSE-2: Owner-bound explicit start/check/cancel, expiry/race protection and
  encrypted account storage; coordinator and route integration tests.
- [x] MUSE-3: Registry/discovery/import/refresh and management operations; identity,
  malformed imports, reauthorization and model-filtering regression tests.
- [x] MUSE-4: Runtime request/stream/cancellation and quota integration; native
  tool/reasoning replay and no implicit pay-as-you-go fallback tests.
- [x] MUSE-5: Provider workspace and 15-locale copy; responsive/theme, manual save,
  import and failure-state browser checks.
- [x] MUSE-6: Core suite, fast quality gate, locale audits and integrated browser
  smoke; report separately verified live behavior and remaining limitations.

Checkpoint after MUSE-1: verify the actual token/key lifecycle before wiring login.
Checkpoint after MUSE-3: validate credential isolation before runtime/UI activation.
No request in this checklist authorizes additional paid inference or deployment.

Verification: `docs/providers/muse-code-verification-2026-09-16.md`. Implementation
is complete; live inference through the finished gateway, deployment and long-term
upstream session behavior are not claimed by these checkmarks.

## Current provider conformance audit (2026-09-16)

- [x] Map all 22 providers to local reference implementations and protocol evidence.
- [x] Audit account/OAuth providers and repair confirmed defects with regression tests.
- [x] Audit API-key/local providers and repair confirmed defects with regression tests.
- [x] Verify shared runtime, import and advanced-settings contracts across providers.
- [x] Run integrated checks and publish results with explicit live-test limitations.

## Approved provider authentication repair (2026-09-15)

Spec: `docs/specs/provider-auth-consistency.md`. Existing completed R1 checklist remains unchanged.

- [x] Kiro OAuth credential normalization, storage identity and refresh; preserve API keys (unit tests).
- [x] Owner-bound device login, cancellation, expiry, replay protection (API/security tests).
- [x] Kiro OAuth-first UI, API-key fallback, localized help/imports (DOM/browser tests).
- [x] Offline import parity and retention of failed files (backend/DOM regression tests).
- [x] Provider-specific terminology, consistent actions/results and advanced scope (22-provider browser check).
- [x] Focused/full core checks, frontend assembly/browser checks, review and local commits; live-test limits recorded in the spec.

Verification: core 2,106 tests (22 existing conditional skips), final focused set 84 tests,
fast quality gate, all locale audits, 22-card/15-locale browser checks and four Kiro device UI methods.
Backend commit: `35b409f`; UI/documentation are the following commit. No Docker update, push or merge.

Progress denominator: **36/36** implementation tasks. Planning artifacts do not count as completed
implementation. The denominator cannot change without an approved `CR-###` in `tasks/plan.md`.

## Approval Gate

- [x] User approved `CONSTRAINTS.md`, `docs/specs/production-self-hosted.md`, and `tasks/plan.md` on
  2026-09-08.

## Phase 0 — Scope Reset and Truthful Baseline (6/6)

- [x] P0.1 Capability registry and support tiers
- [x] P0.2 Product terminology and navigation inventory
- [x] P0.3 Isolate unfinished HA work
- [x] P0.4 Risk and maintainability baseline
- [x] P0.5 Fast, phase, and release gates
- [x] P0.6 Compatibility and deprecation guard

## Phase 1 — Installation, Configuration, Recovery (6/6)

- [x] P1.1 Authoritative typed configuration schema
- [x] P1.2 Minimal canonical Docker Compose profile
- [x] P1.3 First-run setup and preflight
- [x] P1.4 Versioned backup, validation, and restore
- [x] P1.5 Update and rollback workflow
- [x] P1.6 Supported install matrix

## Phase 2 — Gateway Correctness and AI Quality (6/6)

- [x] P2.1 Provider capability matrix
- [x] P2.2 Connection tests and actionable provider errors
- [x] P2.3 Cross-protocol contract corpus
- [x] P2.4 Streaming, cancellation, timeout, and retry semantics
- [x] P2.5 Routing, fallback, cooldown, and health
- [x] P2.6 Compression and quality-policy hardening

## Phase 3 — Coherent Core Console (6/6)

- [x] P3.1 Navigation and conditional complexity
- [x] P3.2 Shared page states and accessible interaction
- [x] P3.3 Production dashboard
- [x] P3.4 Provider onboarding
- [x] P3.5 Credential fleet operations
- [x] P3.6 Models and routing workflow

Phase 3 candidate verification passed. The raw dirty-workspace compatibility check still flags the
unrelated unstaged request-schema edit in `backend/core/models.py`; see the P3.6 evidence before
including that edit in a release candidate.

## Phase 4 — Complete Product Workflows (6/6)

- [x] P4.1 AI Quality console completion
- [x] P4.2 Playground backend boundary
- [x] P4.3 Playground interface
- [x] P4.4 Access lifecycle completion
- [x] P4.5 Unified Activity
- [x] P4.6 Settings, Team access, About, and localization

## Phase 5 — Operational Hardening and Release (6/6)

- [x] P5.1 Storage tiers and migrations
- [x] P5.2 Authentication and security closure
- [x] P5.3 Usage, cost, and observability closure
- [x] P5.4 Browser test harness and CI balance
- [x] P5.5 Fixed reliability and performance evidence
- [x] P5.6 Release candidate, documentation, and handoff

## Scope Controls

### Synthetic database fidelity — 2026-09-17

- [x] Provider-specific stored credentials, source-backed models and raw quota fixtures.
- [x] Coherent usage, traces, counters, identity/access and policy data.
- [x] Back up/update actual marked database; verify production APIs and preview.

Evidence: `docs/audits/synthetic-fidelity-2026-09-17.md`. Port 4285 now serves 89
credentials across 23 variants, 712 ledger calls and 720 traces. Production routing
capacity remains unchanged; actual selection succeeds. Source data, rollback,
production HTTP, browser and encrypted backup validation passed.

- [x] No unapproved `CR-###` exists.
- [x] No new Wave, phase, suffix, hidden checklist, or alternate progress denominator exists.
- [x] Experimental HA/Kubernetes work has not blocked a core-production task.
- [x] Post-R1 backlog work has not entered the release candidate.

## Approved post-R1 repair — CR-001

- [x] Claude transient failures and OAuth destination validation.
- [x] Native provider imports and truthful validation status.
- [x] Provider settings ownership, scoped resets, and server validation.
- [x] Ollama explicit proxy bypass.
- [x] Antigravity credit editor in Providers.
- [x] Locales, documentation, focused integration tests, and isolated browser verification.
