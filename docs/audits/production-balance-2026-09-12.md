# Production Balance Audit — 2026-09-12

## Decision

Polaris already covers the complete self-hosted gateway journey. The next release must not
expand the product surface. It must make the existing surface consistently production-grade for
one person or a trusted small team and remove unreachable enterprise machinery that still taxes
maintenance, dependencies, documentation, and verification.

This audit is the baseline for `PROD-BALANCE-R2`. Historical R1 evidence remains immutable.

## Measured Baseline

| Surface | Current size/state | Production assessment |
| --- | ---: | --- |
| Backend runtime | 201 files / 74,292 lines | Capable, but distributed-runtime and parallel storage code dominate several hotspots |
| Backend tests | 229 files / 49,295 lines | Strong coverage; experimental topology consumes disproportionate suite surface |
| Frontend JavaScript | 51 files / 21,501 lines | Appropriate no-build architecture; browser/DOM coverage is sufficient for this product size |
| Frontend CSS/HTML | 32 files / 7,938 lines | Shared primitives exist; page-level visual consistency still needs one complete pass |
| Tooling | 26 files / 9,199 lines | Quality runner is useful; HA evidence and a mandatory ten-minute profile are too heavy for routine self-host releases |
| Documentation | 143 files / 17,949 lines | Core guides are complete; historical enterprise material is too prominent in repository search |
| Public inference API | 18 operations | Complete and compatibility-protected |
| Management API | 126 operations | Broad but justified by the console; compatibility protection is currently red |
| Console | 11 primary destinations, 13 fragments | Complete core journey; Team access remains optional and Activity owns audit/log compatibility pages |
| Providers | 6 families / 9 credential variants | Complete for the advertised provider set; do not add another provider in this workstream |
| Configuration | 124 documented environment variables, 24 console controls | Typed and tiered; basic setup remains bounded |
| Localization | English/Vietnamese curated, 13 community locales | Keep compatibility catalogs frozen; new product copy is required only in English and Vietnamese |

The current branch is not a valid production candidate despite the completed R1 record:

- `python tools/quality_gate.py fast` fails because one committed test file is not formatted.
- `backend.tests.test_compatibility_guard` reports two failures because
  `PUT /api/model-pools/polaris` changed its request schema after R1.
- Seven Pydantic v1-style configuration sites still emit deprecation warnings.
- The maintainability inventory records 502 broad exception handlers, including 321 that do not
  re-raise. Many are legitimate process/API boundaries, but the core authentication, inference,
  storage, and shutdown hotspots are not consistently observable.

## Complete Capability Disposition

### Keep as Core production

- Single-instance Docker Compose with SQLite, health/readiness, first-run setup, backup/restore,
  update/rollback, and local-owner recovery.
- Google Antigravity, Google AI Studio, Grok, xAI Console, Codex, OpenAI Platform, Claude Code,
  Claude Platform, and Ollama credential workflows.
- OpenAI Chat Completions and Responses, Anthropic Messages, Gemini native, and Vertex-compatible
  inference including streaming, cancellation, retry, fallback, and normalized errors.
- Credential pool operations, model discovery, virtual model routes, five routing strategies,
  cooldown/health, model blacklist, and Playground handoff.
- AI Quality policy, explicit compression disable, invariant protection, cache/guardrail controls,
  and content-free decision telemetry.
- Virtual keys, scopes, model restrictions, expiry, rate limits, hard budgets, rotation, revocation,
  usage, dynamic pricing, Activity, audit, traces, logs, and exports.
- Dashboard, Providers, Credentials, Models & Routing, AI Quality, Access, Activity, Settings,
  About, themes, responsive layout, English, and Vietnamese.

### Keep as Advanced production

- PostgreSQL, OIDC Team access and roles, reverse-proxy operation, Prometheus, OpenTelemetry, and
  Langfuse export. These capabilities have real small-team value and remain opt-in.

### Keep but freeze as Compatibility

- MongoDB storage, legacy route/config aliases, platform-specific launchers, hosted-platform
  descriptors, and community locales. They receive security and correctness fixes only.
- MongoDB must not retain an optional Redis acceleration path after Redis topology retirement;
  correctness falls back to its durable implementation.

### Remove from the active product

- Redis coordinated runtime, multi-replica HA activation/operator/reconciliation, HA topology
  evidence tooling, Redis quota scripts, Kubernetes/Helm deployment, and their release-suite branch.
- These paths have no accepted activation record, cannot be used in the shipped build, and provide
  no current user migration burden. Historical ADRs remain as records with superseded status.

## Quality Balance Findings

| Area | Current level | R2 action |
| --- | --- | --- |
| Core gateway/protocols | Production | Preserve contracts; no rewrite |
| Provider and credential workflows | Production | Preserve; fix only evidence-backed defects |
| AI Quality and pricing | Production | Preserve safe defaults and dynamic catalog fallback |
| Installation/recovery | Production | Preserve canonical Compose path |
| OIDC/PostgreSQL/exporters | Appropriate advanced | Keep opt-in and isolated |
| MongoDB/community locales | Compatibility burden | Freeze; remove only Redis coupling |
| Redis/HA/Helm | Overbuilt and unusable | Retire completely from active code, config, dependencies, tests, and docs |
| Release verification | Overbuilt for every iteration | Use a bounded routine profile; keep the ten-minute soak optional before major releases |
| API compatibility | Below production on current HEAD | Restore zero-diff R1 contract before other work |
| Pydantic migration | Below production | Complete behavior-preserving v2 migration with schema checks |
| Exception observability | Uneven | Fix only silent catches on core trust/lifecycle boundaries; do not mechanically rewrite all 502 |
| Frontend architecture | Appropriate | Keep no-build JavaScript; do not add a framework or duplicate unit-test stack |
| Frontend visual/copy quality | Uneven | Apply existing shared components and content rules across every active page |

## Non-goals

- No new provider, protocol, database, identity protocol, telemetry vendor, commercial billing,
  organization hierarchy, plugin system, or frontend framework.
- No rewrite motivated only by file size or line-count reduction.
- No attempt to make MongoDB equal to SQLite/PostgreSQL or community translations equal to the
  curated locales.
- No new Wave, Phase, suffix, hidden denominator, or follow-on task discovered during execution.
