# Polaris — Fixed Production Balance Plan R2

## Control Record

- Plan ID: `PROD-BALANCE-R2`
- Scope: one closed workstream with exactly seven tasks; no Waves or Phases.
- Product target: production self-hosting for one person or a trusted team, not a hosted service.
- Baseline: `docs/audits/production-balance-2026-09-12.md`
- R1 history: `tasks/plan.md` and `tasks/todo.md` remain complete and immutable.

The user's 2026-09-12 instruction authorizes analysis plus both simplification and improvement.
This plan does not require a second approval gate. A newly observed defect is resolved inside the
owning task. The task count changes only for a critical/high security issue, data-loss risk, or an
explicit product-boundary change from the user.

## PB1 — Restore a truthful green baseline

**Outcome:** Current HEAD once again satisfies its existing formatting and R1 compatibility
contracts before architectural work begins.

**Acceptance criteria:**

- Fast gate passes without suppressions or relaxed checks.
- R1 compatibility comparison reports zero changes.
- The stricter model-pool input experiment is removed or implemented without changing the frozen
  OpenAPI contract.

**Verification:** focused compatibility suite, model-pool tests, and fast gate.

## PB2 — Retire unreachable Redis/HA/Kubernetes topology

**Outcome:** The shipped product has one honest runtime topology instead of carrying an unusable
enterprise topology through startup, dependencies, tools, tests, and current documentation.

**Acceptance criteria:**

- Standalone in-memory coordination continues to protect sessions, reservations, rate limits,
  batch actions, cache invalidation, and routing inside one process.
- Redis coordinated runtime, HA operator/reconciliation/evidence, Helm assets, experimental suite,
  activation configuration, and the Redis runtime dependency have no active references.
- Existing default Compose data and APIs remain unchanged; no database migration is needed.

**Verification:** lifecycle, security/session, quota, routing, configuration, metrics, application,
and container-focused tests; repository reference scan.

## PB3 — Bound compatibility and optional dependencies

**Outcome:** Advanced features remain useful, compatibility features remain safe, and neither
controls the default architecture.

**Acceptance criteria:**

- PostgreSQL and OIDC stay opt-in and pass their deterministic contracts.
- MongoDB stays compatibility-only but no longer contains or advertises Redis acceleration.
- Optional-driver failures are actionable only when the corresponding backend is selected; default
  SQLite startup has no optional-service I/O.

**Verification:** storage selection, SQLite, MongoDB compatibility, PostgreSQL deterministic,
identity, and default-start tests.

## PB4 — Normalize core correctness debt

**Outcome:** Core models and failure boundaries are consistently maintainable without a global
rewrite.

**Acceptance criteria:**

- Remaining project-owned Pydantic v1 configuration warnings are removed with unchanged public
  schemas and runtime behavior.
- Silent broad catches in authentication, inference settlement, storage initialization, and
  shutdown either have an intentional bounded fallback with observability or a typed failure.
- No new suppression, skipped core test, public schema change, or secret-bearing log is introduced.

**Verification:** warning-sensitive model/schema tests, targeted failure-injection suites,
compatibility guard, and maintainability inventory.

## PB5 — Apply one console and language quality level

**Outcome:** Every active page uses the same layout density, form rhythm, state feedback, naming,
and responsive behavior; compatibility pages do not compete with their canonical destination.

**Acceptance criteria:**

- All 11 primary destinations and their 13 fragments are inspected against shared component and
  content guidelines; page-only fixes reuse existing primitives.
- No horizontal page overflow at 360/768/1024/1440, no isolated one-line notice card, no raw DOM/i18n
  identifier in visible text, and form labels/controls have consistent spacing.
- English and Vietnamese copy is semantically reviewed; community locales retain key fallback but
  receive no new editorial promise.

**Verification:** DOM contracts, all localization audits, full maintained browser route sweep,
keyboard smoke, and clean browser console.

## PB6 — Right-size verification for routine production work

**Outcome:** Quality remains release-blocking without making every iteration pay for enterprise
evidence.

**Acceptance criteria:**

- Fast, task, and release gates stay deterministic and clearly separated.
- The routine release reliability profile is bounded to a small-team signal that completes in at
  most three minutes; the existing ten-minute profile remains an explicitly optional soak for major
  releases, not a hidden blocker.
- Core, optional, compatibility, and retired surfaces are named truthfully in CI and docs.

**Verification:** gate contract tests, dry-run/list output, routine profile, and intentional-failure
proof without weakening latency/error/memory thresholds merely to pass.

## PB7 — Reconcile and prove the production candidate

**Outcome:** Code, product inventory, constraints, docs, and runtime evidence agree on one support
boundary.

**Acceptance criteria:**

- The final diff contains a net reduction in active runtime/tooling complexity and no unexplained
  feature expansion.
- Core suite, compatibility/configuration contracts, dependency audit, localization, browser,
  application, routine reliability, and container smoke pass once on the candidate.
- Current-state and handoff docs report exact retained/removed features, known limitations,
  rollback path, and measured before/after code size.

**Verification:** one complete R2 release gate after all focused failures are resolved.

## Fixed Order and Change Control

`PB1 → PB2 → PB3 → PB4 → PB5 → PB6 → PB7`

Tasks may use multiple small commits, but no internal checklist becomes a new progress denominator.
Historical enterprise ADRs/evidence are records, not active requirements. A desirable improvement
outside these seven outcomes is explicitly deferred and cannot delay PB7.

