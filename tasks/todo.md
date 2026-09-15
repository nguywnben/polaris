# Polaris Production Self-Hosted R1 — Fixed Checklist

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
