# Polaris — Current State

## Publication authorized — 2026-09-18

The owner approved merge, `v1.0.0` tagging and publication after refreshing README
previews. Replace the outdated shared image with actual Dashboard/Credentials captures
in light/dark themes, using a new offline synthetic database. Verify and commit this
documentation-only update, run exact-SHA CI, then publish through the existing guarded
workflow and verify the published digest in an isolated container. Never reuse operator
data or bypass a failed release gate. Earlier checkpoints below retain their original
authorization boundaries.

## Candidate prepared and verified — 2026-09-18

The owner authorized committing the reviewed repairs, pushing only
`codex/release-1.0.0-readiness`, and running CI. No main merge, stable tag, registry
publication or GitHub release publication is authorized. RR5/RR6 evidence is in
[the existing release plan](release-readiness-2026-09-18.md#authorized-candidate-closure--2026-09-18).
Target image names are available in both registries; beta rollback digests are recorded.
Candidate `bafe7b6` passed the complete local release gate and all required GitHub CI
jobs, with both publication jobs skipped. See the [readiness record](../docs/releases/1.0.0-readiness.md)
for exact evidence, scope and publication steps. The documentation-only handoff commit
must also have green CI and an exact-commit reliability confirmation before delivery.
The sections below preserve earlier checkpoints, not the current release verdict.

## Local release preparation completed — 2026-09-18

The owner requested a whole-product audit and preparation of the new Polaris `1.0.0`
line. See [the scoped plan](release-readiness-2026-09-18.md) and
[current evidence](../docs/audits/release-readiness-2026-09-18.md).
The final local release gate, nine browser journeys and isolated Docker rehearsal passed.
The working tree remains uncommitted; registry-image collisions and immutable-commit
CI/sign-off still block publication. This is not a ready-to-tag declaration.
The owner separately authorized a historical tag/release migration on 2026-09-18:
14 Omni Gateway tags now use `omni-gateway/`; Polaris beta is `v0.1.0-beta` at its
original commit. [Migration evidence](../docs/releases/tag-migration-2026-09-18.md)
records the preserved releases and backup. No code commit, branch push, new `v1.0.0`
tag or image publication was performed or authorized by that migration. R1/R2 remain completed
historical work; their candidates and test results do not certify the current tree.

## Completed Production Balance Workstream

- Completed plan: `PROD-BALANCE-R2` in `tasks/production-balance-r2.md`.
- Fixed progress: **7/7**; one workstream, no Waves or Phases.
- Baseline audit: `docs/audits/production-balance-2026-09-12.md`.
- Candidate handoff: `docs/evidence/pb7-production-candidate.md`.
- No implementation task remains. Tagging, pushing, publishing, and remote CI are operator release
  actions and were not performed.
- R1 below remains completed historical state; it is not reopened or added to the new denominator.

## Resume Here

- Updated: 2026-09-12 (Asia/Saigon)
- Active plan: `PROD-SELFHOST-R1`
- Target: production-quality self-hosting for one person or a trusted team, not enterprise service
  operation.
- Progress: **36/36 implementation tasks**; all six phases are complete.
- Completed: **P5.6 — Release candidate, documentation, and handoff** for release `1.5.0`.
- Validated release candidate `7ffefd8` passed the complete release gate: 50/50
  configuration/inventory/compatibility contracts, all 1,284-key locale audits, dependency
  compatibility and vulnerability checks, 1,727 Core tests with 22 optional/live skips, 9/9
  critical browser journeys, and the 15-check fixed reliability profile.
- The final 600-second profile completed 6,000/6,000 requests with zero errors or exhaustion, p95
  85.401 ms, 24.555 ms maximum schedule lag, bounded memory, Dashboard usable in 332.294 ms,
  graceful shutdown in 0.488 seconds, and restart readiness in 2.462 seconds.
- Release documentation, version/changelog, current image, capability tiers, limitations, clean
  install, recovery/rollback, troubleshooting, and the 36 evidence records are reconciled in
  `docs/evidence/p5.6-release-candidate-handoff.md`.
- The exact candidate also passed fresh setup, authenticated smoke, force-recreate persistence, and
  graceful stop/start through the canonical Compose profile. The regenerated production lock
  changed no package version or hash.
- No planned implementation task remains. Tagging, pushing, remote CI confirmation, and image
  publication are operator release actions and were not performed.
- Supported runtime today: standalone, one worker, one replica.
- Redis coordination, multi-replica HA, and Helm were retired from the active product in PB2.
- MongoDB now operates directly without Redis acceleration or coordinated-only mutation branches;
  SQLite remains the no-service default and optional backends still fail closed when selected.
- Project-owned Pydantic deprecations are zero; critical lifecycle, storage, parser, cache, and
  stream-cleanup failures now retain bounded observability without logging raw exception details.
- All 11 console routes now share the no-overflow, compact advisory-copy, label-spacing, keyboard,
  and localized-feedback contract. Empty support tiers are hidden; only semantically maintained
  English and Vietnamese README files remain, while all 15 console locales retain complete keys.
- The release reliability gate now uses a 120-second/600-request routine profile with unchanged
  quality thresholds. The original 10-minute/6,000-request profile remains an explicitly optional
  soak; obsolete executable HA runbook guidance is removed.

## Why the Plan Was Reset

The prior enterprise plan delivered substantial credential, audit, access, identity, storage, and
coordination work, but its Wave 4 HA closure expanded repeatedly and over-weighted distributed
failure evidence relative to the needs of a personal/small-team self-hosted product. Completed code
is preserved. Unfinished enterprise activation is frozen rather than allowed to keep changing the
release denominator.

## Authoritative Reading Order

1. `CONSTRAINTS.md`
2. `docs/audits/production-baseline-2026-09-08.md`
3. `docs/specs/production-self-hosted.md`
4. `tasks/plan.md`
5. `tasks/todo.md`
6. `git status` and recent commits

Historical enterprise specs, ADRs, evidence, and git history remain useful context but cannot
override the current product boundary or completion rules.

## Working Tree Caution

Before starting the next task, inspect the working tree and preserve unrelated user-owned changes.
Do not push unless the user requests it.

## Fixed Verification Cadence

- Task: focused tests only.
- Phase: affected integration/browser gate once.
- Release candidate: full required gate once; rerun failed slices before another full pass.
- No HA topology matrix in R1.
- No cross-model review except one security pass for backup/restore or final auth/security closure,
  unless the user explicitly requests another.

## Latest Evidence

- `docs/evidence/pb7-production-candidate.md`
- The R2 candidate reconciles code, support tiers, constraints, changelog, historical architecture
  records, measured size, limitations, rollback, and the one required final verification path.
- `docs/evidence/pb6-right-sized-verification.md`
- The routine signal passed 600/600 requests at p95 76.055 ms with dashboard usable in 565.491 ms
  and all 15 checks green. The release dry-run selects routine; the preserved ten-minute soak is
  listed separately as optional.
- `docs/evidence/pb5-console-language.md`
- All 112 focused console/localization contracts and 1,268-key audits passed. Browser evidence
  covered 9/9 journeys, 11 routes at four widths, keyboard navigation, and a clean console. PB5
  removed 7,447 net lines, chiefly stale community README copies that advertised retired runtime
  paths without maintainer semantic review.
- `docs/evidence/p5.6-release-candidate-handoff.md`
- Polaris 1.5.0 is prepared for single-worker/single-replica production self-hosting. The
  release evidence records all local gate results, clean-install rehearsal, rollback command,
  support tiers and known limitations without an enterprise, HA, Kubernetes, or ARM64 claim.
- `docs/evidence/p5.4-browser-harness-ci.md`
- Required frontend evidence now uses a maintained Playwright/Chromium harness instead of syntax
  checks and manual sessions alone. It covers fresh setup, provider/model routing, AI Quality,
  Playground, virtual-key lifecycle, Activity correlation, operations guidance, and local recovery
  with deterministic fixtures and disposable state.
- `docs/evidence/p5.1-storage-tiers-migrations.md`
- SQLite is the documented Core authority, PostgreSQL is Advanced, and MongoDB is Compatibility.
  R1 exposes no production cross-backend migration command and experimental durable/HA parity does
  not block the release.
- The affected gate passed 157 tests with two optional live skips; 31 MongoDB compatibility/tier
  tests passed, while all 12 PostgreSQL live cases plus three SQLite migration cases passed against
  a disposable PostgreSQL 17 instance.
- `docs/evidence/p4.6-settings-team-about-localization.md`
- Settings now maps all 20 controls to authoritative typed metadata, never returns the reusable
  Code Assist secret, preserves blank secrets and environment locks, and explains live/restart
  state. About reports validated build/support facts and permanent recovery/update entry points;
  optional Team access keeps local-owner recovery visible when OIDC is disabled.
- The Phase 4 exit trace covers all nine required journeys. The focused gate passed 101 tests, the
  candidate compatibility projection passed all five tests, all 1,285 locale keys resolved, and
  authenticated browser smoke had no overflow or browser-console entries.
- `docs/evidence/p4.5-unified-activity.md`
- Activity now applies one session-only correlation filter across request traces, audit/security
  events, and bounded runtime logs. Dashboard and both detail views pivot by request ID; `/logs`
  correctly opens runtime evidence, and raw-log downloads are redacted and capped at 16 MiB.
- The fixed task gate passed 83 affected tests and all static checks. An authenticated 520 px
  browser flow retained correlation across views, selected the correct compatibility route, had no
  horizontal overflow, and produced no browser-console entries.
- `docs/evidence/p4.3-playground-interface.md`
- Playground is now a complete core console page for all four supported request shapes, with a
  bounded memory-only editor, native response/stream/error rendering, cancellation, route and AI
  Quality metadata, and placeholder-only cURL/Python SDK examples.
- The final task gate passed 68 affected tests and all static checks. Authenticated deterministic
  Chrome flows passed success, stream, error, cancel, XSS, live locale switching, and 1440/360 px
  responsive checks with no runtime exception or horizontal overflow.
- `docs/evidence/p4.2-playground-backend-boundary.md`
- The authenticated, 1 MiB/20-per-minute/1–120-second bounded Playground API now reuses all four
  real public protocol handlers, preserves native success/error/stream semantics, propagates
  cancellation, and returns content-free route/quality/usage metadata without accepting provider
  credentials or adding raw-content persistence.
- Explicit audit, structured completion logs, and fixed-cardinality RED metrics cover final run
  outcomes. The fixed task gate passed 72 affected tests and all static checks.
- `docs/evidence/p4.1-ai-quality-console.md`
- AI Quality now explains live/no-restart application, environment-to-request precedence,
  unambiguous compression disable behavior, thresholds, protected structures, and cache/guardrail
  tradeoffs. Synthetic preview reports transform scope and estimated removed messages without
  receiving prompt content, persisting data, or calling a provider.
- Five stable warnings identify risky custom combinations. The fixed task gate passed 87 affected
  tests, all 1,209-key localization audits, and an authenticated 535 px browser flow without
  horizontal overflow.
- `docs/evidence/p3.6-models-routing-workflow.md`
- Models now supports create/validate/edit/delete, fallback ordering, global credential strategy,
  revision conflicts, unavailable-model explanations, unsaved-change guards, and a secret-free
  handoff into the completed Playground workflow.
- The final 52-test task gate and 48-case responsive/theme matrix passed. The affected Phase 3 slice
  passed 141 tests; all localization audits passed. Phase exit also repaired P3.3 usage API
  compatibility and P3.4 pagination localization. Candidate compatibility/inventory passed 14 tests
  with the committed models schema loaded in memory; the unrelated user edit remains untouched.
- `docs/evidence/p3.5-credential-fleet-operations.md`
- Credentials now exposes four common filters first and progressively discloses six diagnostic
  filters, with immediate active-count/reset behavior and bounded URL/session persistence. Refresh
  retains valid page context and page-scoped selection.
- Mixed-provider selection offers only the capability intersection; both explicit and all-matching
  batches stop at 100 targets. All-matching confirmation names the exact filter query, server
  fingerprint, and eligible/skipped/total impact before the existing preview-bound idempotent
  execution. The fixed 105-test task gate and authenticated responsive browser smoke passed.
- `docs/evidence/p3.4-provider-onboarding.md`
- Providers now consumes the versioned capability catalog for all nine advertised connection
  variants, keeps the primary add path visible, and progressively discloses import and advanced
  settings. Provider-family settings load only when opened instead of all five families loading on
  page entry; failures retain the built-in catalog and offer retry plus bounded remediation.
- The 68-test task gate and authenticated browser smoke passed. Both catalog pages, every provider
  workspace, keyboard selection, disclosure behavior, lazy request boundary, and a clean browser
  console were verified.
- `docs/evidence/p3.3-production-dashboard.md`
- Dashboard now prioritizes one readiness decision, clear next actions, provider/credential
  incidents, current request health, recent content-free activity, actual recorded cost, latency,
  and usage trends. Low-value per-credential/per-request cards were removed and advanced telemetry
  was demoted to a collapsed disclosure.
- All list reads are bounded and startup is fixed at four API requests. State fixtures, the 52-test
  task gate, and authenticated 360/768/1024/1440 browser evidence passed without overflow or browser
  errors.
- `docs/evidence/p3.2-shared-page-states-accessibility.md`
- Core asynchronous pages now share persistent error/remediation and stale-data states instead of
  becoming blank, while existing content survives refresh failures. Toasts are live-region aware,
  modal focus is contained and restored, tables/pagination expose consistent semantics, and reduced
  motion suppresses nonessential movement.
- A manifest-sensitive asset digest prevents immutable browser caches from retaining a bundle that
  omits newly registered modules. The task gate passed 45 affected tests and a clean authenticated
  browser session reported no errors or warnings.

- `docs/evidence/p3.1-navigation-conditional-complexity.md`
- The console now follows the fixed self-hosted information architecture. Request traces, audit and
  security events, and runtime logs share one accessible Activity destination; `/audit` and `/logs`
  remain compatible.
- Team access is conditional on enabled OIDC state or direct configuration, advanced/compatibility
  settings are collapsed, and mobile drawer plus page-heading focus behavior is explicit. The task
  gate passed 73 affected tests, all translation audits, and authenticated 360/1440 Chrome smoke.
- `docs/evidence/p2.6-compression-quality-hardening.md`
- Compression now fails open to the unchanged request on bounded estimation/copy/invariant failure,
  preserves system/tool/current-request structures, and applies one policy decision across Primary
  and Vertex paths. Virtual keys and requests may only inherit or disable the global policy.
- A fixed adversarial corpus, 96-case deterministic property matrix, safe preset/anti-truncation
  checks, provider/protocol/stream/routing matrices, and one HTTP success per advertised protocol
  passed the P2.6 task and Phase 2 gates.
- `docs/evidence/p2.5-routing-fallback-health.md`
- All five routing strategies now share the production smart router and a deterministic scenario
  matrix; repeated failures grow bounded cooldowns, success resets route health, and unsupported,
  disabled, busy, oversized, and cooling pools produce actionable reasons.
- Authenticated routing diagnostics expose only provider/model context, stable reason/count
  vocabulary, and rounded recovery time. Credential filenames, request IDs, payloads, content, and
  raw upstream errors remain excluded. The fixed task gate passed 125 affected tests and all fixed
  static checks.
- `docs/evidence/p2.4-streaming-lifecycle.md`
- All six public streaming surfaces now close nested provider resources on disconnect, suppress
  retry after model output, require terminal events before success, preserve heartbeat/UTF-8/SSE
  framing, and enforce 1 MiB frame plus 8 MiB aggregation ceilings.
- Cancelled and failed HTTP 200 streams now release quota reservations without fallback commit and
  persist one truthful trace outcome. Focused fault injection covers timeout, partial EOF,
  midstream errors, anti-truncation, and each protocol adapter.
- `docs/evidence/p2.3-cross-protocol-contract-corpus.md`
- Five advertised ingress families now share one versioned feature matrix and request/response
  golden corpora for text, images, system instructions, tools, structured output, reasoning,
  usage, finish reasons, and native errors.
- Unknown or untranslatable request semantics fail with native 400 errors; unknown upstream parts
  fail with native 502 errors. Developer/system intent, signed Anthropic thinking, structured
  output, cached/reasoning usage, and incomplete/safety finishes survive translation.
- The task gate passed lint/format for 421 files, compilation, the 179-Core/13-experimental
  partition, JavaScript, YAML, six shell checks, whitespace, 103 affected tests, and five immutable
  compatibility tests after runtime validators were made invisible to the frozen OpenAPI schema.
- `docs/evidence/p2.2-provider-connection-diagnostics.md`
- Provider connection tests now expose one safe versioned diagnostic contract across all nine
  advertised variants, with actionable categories, remediation, bounded provider status, and an
  allowlisted provider code instead of raw upstream bodies or exception text.
- A single 30-second deadline covers the complete operation, browser cancellation reaches the
  provider coroutine, and the console renders limited/failure outcomes through complete 15-locale
  labels. The fixed task gate passed its environment-only shell retry and 78 focused tests; the
  final semantic correction passed another 21 affected tests.
- `docs/evidence/p2.1-provider-capability-matrix.md`
- All nine advertised provider/auth variants now share a versioned capability contract covering
  lifecycle operations, discovery, quota, OAuth refresh, and five normalized ingress protocol
  families. The console derives card and mixed-selection actions from that server contract.
- Unsupported operations fail closed with the stable typed 422 envelope before provider I/O or
  mutation. The additive v2 route preserves the immutable `/api/providers` v1 contract. The fixed
  task gate passed its environment-only shell retry and all 85 focused affected tests.
- `docs/evidence/p1.6-supported-install-matrix.md`
- One linear, version-pinned Compose guide now covers Windows Docker Desktop/WSL2, Linux Docker
  Engine, and the remaining macOS manual check; native launchers and hosted descriptors are
  explicitly compatibility-only, while Helm remains experimental.
- The Windows rehearsal completed fresh setup, authenticated runtime smoke, recreate persistence,
  and a no-error/no-overflow browser login on the isolated port 4298. The Phase 1 gate covered all
  fixed steps after two exposed inventory/compatibility debts were corrected without overwriting
  the immutable R1 fixture.
- `docs/evidence/p1.5-compose-update-rollback.md`
- Compose updates now require a version/digest, deploy the resolved immutable ID, preserve a
  checksum-bound encrypted host recovery point, detect `.env`/port drift, and automatically restore
  both state and the previous image after target failure.
- The P1.5 task gate passed all fixed steps and 30 affected tests. Isolated 1.4.0 → 1.5.0 update,
  explicit rollback, and a target-mutates-SQLite-then-fails-health rehearsal all recovered healthy
  authenticated operation; the failed target's marker was absent after rollback.
- `docs/evidence/p1.4-versioned-backup-restore.md`
- `docs/reviews/p1.4-cross-model-review-reconciliation.md`
- Candidate `a38ca74` provides one encrypted SQLite recovery artifact, strict dry-run/conflict/schema
  validation, encrypted pre-restore snapshots, cancellation-safe atomic replacement, complete
  runtime cache/service rebinding, and a separate non-restorable sanitized inventory.
- The fixed task gate passed 51 selected tests. A clean read-only container restored original
  routing and root access after deliberate mutation, rejected the superseded key, emitted no
  secret in sanitized export, and retained its encrypted recovery snapshot before cleanup.
- The independent review returned PASS WITH FINDINGS and no Critical/High issues. Commit `cb4ee10`
  rejects non-table SQLite schema objects, invalidates restored response-cache state, and records
  bounded snapshot/passphrase operations. All 35 affected tests passed after reconciliation.
- `docs/evidence/p1.3-first-run-setup-preflight.md`
- First-run setup now models fresh, resumed, configured, and invalid states with one next action;
  preflight verifies durable writes, address, listener, transport/cookies, token policy, and owner
  state before enabling owner creation.
- Remote setup requires an operator-configured strong token that is never generated or logged;
  resumability persists no secrets, owner creation is serialized, and 12–256 character passphrases
  are enforced across API and console.
- The task gate passed 76 selected tests and all fixed checks. A fresh isolated container completed
  setup and authenticated smoke, passed again after recreate, and the 360/1440 keyboard browser
  flow had no overflow or browser errors.
- `docs/evidence/p1.2-minimal-compose-profile.md`
- Default Compose now needs no external database or Redis, exposes only common production
  controls, and persists all application state in one named volume; advanced controls require an
  explicit override file.
- The canonical CI path performs fresh setup, force-recreate persistence, readiness, and graceful
  shutdown checks through Compose. Local Docker evidence passed both authenticated smoke runs;
  shutdown exited 0 in 0.96 seconds with a read-only root filesystem.
- `docs/evidence/p1.1-authoritative-configuration-schema.md`
- All 124 documented environment variables now have one typed Basic/Advanced/Experimental schema;
  startup validates scalar boundaries before storage initialization and warns on unknown `POLARIS_*`
  controls.
- Settings field ownership, secret-safe metadata, environment locks, restart classification,
  writable/resettable keys, generated documentation, and `.env`/Compose parity derive from or are
  checked against the same contract.
- The focused P1.1 task gate passed without running the complete Core or experimental HA suites.
- `docs/evidence/p0.6-compatibility-deprecation-guard.md`
- The immutable `r1-v1` fixture protects 18 public inference operations, 112 management
  operations, console routes/aliases, config migrations, nine stored schema versions, and seven
  generated client examples.
- A populated pre-R1 SQLite fixture now upgrades without losing credentials or config. The fixture
  exposed and fixed SQLite's rejection of expression defaults during additive column migration.
- The Phase 0 gate passed configuration/inventory contracts, all translation audits (1,116 keys),
  and 71 affected tests. The 168-module Core suite was covered in order after fixes: 1,417 tests
  passed with 22 intentional optional/live skips. No HA topology matrix ran.
- `docs/evidence/p0.5-fixed-quality-gates.md`
- One runner now defines fast, focused task, affected phase, and single release scopes. The fast
  gate passed in seconds without the complete Core suite; the release dry-run lists 16 fixed steps.
- Required CI checks are visibly named, while optional storage/provider tests and experimental HA
  are listed separately and cannot change the production result.
- The focused gate contract passed 8 tests. The checked partition contained 167 Core modules and 13
  experimental-HA modules; no complete Core or HA topology run was added to P0.5.
- `docs/evidence/p0.4-risk-maintainability-baseline.md`
- The reproducible inventory records 9 modules at or above 1,500 lines, 7 parallel persistence
  families, 8 Pydantic v1-style sites, 480 broad exception handlers across 96 runtime files, 11
  conditional skip sites, 7 live/environment-gated modules, and the missing browser harness.
- All 12 bounded risks are owned by existing P0–P5 tasks or the post-R1 backlog. No file-size-only
  refactor, new task, wave, phase, or denominator was authorized.
- The focused baseline contract passed 5 tests and the independent inventory reproduction check
  matched the saved artifact.
- `docs/evidence/p0.3-experimental-ha-isolation.md`
- Default startup is standalone without Redis; coordinated startup is rejected before external I/O,
  and the compiled experimental activation allowlist remains empty.
- The P0.3 checked partition contained 165 core modules and 13 experimental-HA modules. The focused
  P0.3 gate passed 35 tests; the independently runnable experimental suite passed 109 tests and
  skipped 32 existing opt-in live cases.
- CI and the R1 release checklist now require the partition audit and core suite, not external
  two-replica evidence.
- `docs/evidence/p0.2-product-surface-inventory.md`
- Checked inventory: 11 pages/tabs, 134 OpenAPI operations, 24 Settings controls, 124 example
  environment variables, 16 advertised claims, and explicit locale ownership.
- Product copy now presents the fixed Core/Advanced/Compatibility/Experimental self-host boundary in
  both curated languages; Redis coordination and Kubernetes/Helm are explicitly experimental.
- P0.2 focused console/localization gate: 53 tests passed; all four localization audits passed.
- `docs/evidence/p0.1-capability-registry.md`
- Default runtime snapshot: 31 capabilities; only Core entries are active.
- Focused contract/runtime matrix: 45 tests passed.
- Full backend gate: 1,522 tests run; 1,468 passed and 54 existing optional/live-backend cases
  skipped.
- Ruff, compileall, runtime HTTP projection, and whitespace checks passed.
