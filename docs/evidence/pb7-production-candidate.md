# PB7 — Production Candidate Handoff

- Date: 2026-09-12
- Plan: `PROD-BALANCE-R2`
- Target: production self-hosting for one person or a trusted team

## Candidate decision

Polaris is balanced around one supported deployment topology: one application process, one
worker, one replica, with SQLite as the default durable store. The candidate preserves the
complete gateway, provider, routing, AI-quality, access-control, observability, recovery, and web
console journeys while removing inactive distributed-system machinery that was disproportionate
to the product boundary.

The release verdict is owned by one complete `python tools/quality_gate.py release` run on the
candidate commit. The optional ten-minute reliability soak and real-provider/live optional storage
suites provide supplementary evidence; their availability does not change the routine release
verdict.

## Retained product surface

### Core

- Canonical Docker Compose deployment, single-process runtime, SQLite, health/readiness, first-run
  setup, local-owner recovery, encrypted backup/restore, and image update/rollback.
- OpenAI Chat Completions and Responses, Anthropic Messages, Gemini native, and Vertex-compatible
  request surfaces, including streaming, cancellation, normalized errors, retry, and fallback.
- Nine advertised credential variants across Google, Grok/xAI, OpenAI/Codex, Claude, and Ollama;
  model discovery, credential pools, model routes, cooldowns, health, and five routing strategies.
- AI Quality policies, explicit compression control, invariant protection, guardrails, response
  cache controls, and content-free decision telemetry.
- Virtual keys, scopes, model restrictions, expiry, rate limits, hard budgets, usage/cost records,
  dynamic price synchronization with safe fallbacks, Activity, audit, traces, logs, and exports.
- All 11 console destinations, responsive layout, keyboard operation, themes, curated English and
  Vietnamese copy, and complete key fallback for the remaining console locales.

### Advanced, opt-in

- PostgreSQL, OIDC team access and roles, reverse-proxy operation, Prometheus, OpenTelemetry, and
  Langfuse export. None of these services are contacted by a default SQLite startup.

### Compatibility, frozen

- MongoDB durable storage, legacy route/config aliases, platform-specific launchers,
  hosted-platform descriptors, and community console locale catalogs. These receive security and
  correctness fixes, not architectural expansion.

## Removed from the active product

- Redis coordination, Redis quota scripts, coordinated-runtime activation, multi-replica HA
  lifecycle/operator/reconciliation, and their runtime dependency.
- Kubernetes/Helm deployment assets and executable HA evidence/runbook paths.
- MongoDB Redis acceleration and coordinated-only mutation branches.
- Stale community README translations that advertised retired deployment capabilities without
  maintained semantic review. Console translation catalogs remain available.
- Mandatory ten-minute endurance work in routine releases; the unchanged profile remains an
  explicit optional soak.

Historical ADRs, specifications, plans, reviews, and evidence remain in the repository as records.
The principal Redis/HA records are marked superseded or partially superseded so repository search
cannot mistake them for current operating instructions.

## Measured balance

The baseline was measured at commit `8352941` using the categories recorded in
`docs/audits/production-balance-2026-09-12.md`. Candidate measurements use the same source-file
categories and exclude generated caches.

| Surface | Baseline | Candidate | Change |
| --- | ---: | ---: | ---: |
| Backend runtime | 201 files / 74,292 lines | 193 files / 67,467 lines | -8 files / -6,825 lines |
| Backend tests | 229 files / 49,295 lines | 205 files / 40,253 lines | -24 files / -9,042 lines |
| Frontend JavaScript | 51 files / 21,501 lines | 51 files / 21,504 lines | 0 files / +3 lines |
| Frontend CSS/HTML | 32 files / 7,938 lines | 32 files / 7,930 lines | 0 files / -8 lines |
| Tooling | 26 files / 9,199 lines | 13 files / 3,505 lines | -13 files / -5,694 lines |
| Documentation | 143 files / 17,949 lines | 129 files / 10,366 lines | -14 files / -7,583 lines |

The authoritative Git range `8352941..candidate` changes 176 files with 2,043 insertions and
33,085 deletions (-31,042 net lines). New code is limited to restoring compatibility, bounded
failure observability, UI consistency,
right-sized verification, and the reconciliation contracts/evidence required by the seven-task
plan. The large net deletion is the deliberate removal of inactive topology, tests, tooling, and
stale documentation rather than a reduction of the supported Core journey.

## Known limitations

- Exactly one application process, one worker, and one replica are supported. Load balancing or
  active-active operation is outside this release boundary.
- The published container target is `linux/amd64`; other architectures are unverified.
- SQLite is the canonical fully rehearsed storage path. PostgreSQL and OIDC are opt-in Advanced;
  MongoDB is Compatibility and is not promised feature-parity migration tooling.
- Real provider behavior still depends on external accounts, quotas, catalogs, and upstream
  availability. Deterministic provider contracts are release-blocking; live account checks are
  optional operator evidence.
- Playground messages are held only in the active browser tab. Usage, request metadata, and
  content-free diagnostics follow the configured product policies.
- Community locale catalogs retain complete key fallback but do not receive the same editorial
  promise as English and Vietnamese.

## Rollback and recovery

- No database schema migration is required by R2. An existing default Compose volume remains
  compatible with the prior `1.5.0` image.
- Before changing a deployed image, create and validate an encrypted backup using
  `docs/backup-and-restore.md`, then follow `docs/updating.md` with an immutable target image.
- If health verification fails, the update workflow restores the prior image and SQLite recovery
  point. Explicit operator rollback uses `python tools/compose_update.py rollback --record
  <record.json>` as documented; it never truncates usage, audit, identity, or trace history.
- The code rollback point before R2 is commit `8352941`. Reintroducing Redis/HA/Helm is not a normal
  rollback: those surfaces had no supported activation record and would require a separately
  approved product-boundary change.

## Verification record

- PB1 restored the frozen R1 compatibility contract and a green fast gate.
- PB2/PB3 focused runtime, lifecycle, storage, configuration, identity, and compatibility checks
  passed after the unsupported topology and coupling were removed.
- PB4 passed 107 core failure-boundary/model checks plus the fast gate with no public schema drift.
- PB5 passed 112 focused console/localization checks, all 1,268-key locale audits, 9/9 browser
  journeys, 11 routes at 360/768/1024/1440 widths, keyboard navigation, and a clean console.
- PB6 passed 31 gate/reliability contracts and the routine profile: 600/600 requests, all 15
  checks green, p95 76.055 ms, and Dashboard usable in 565.491 ms.
- PB7 reconciliation contracts and the complete release gate must pass on the exact candidate;
  application and container smoke must use disposable state and must not alter an operator volume.

Tagging, pushing, remote CI confirmation, and image publication remain explicit operator actions.
