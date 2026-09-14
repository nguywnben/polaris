# Wave 4 Continuous Completion Plan

**Goal:** Complete the approved remainder of Wave 4 (W4.16 Tasks 3–9 and W4.17–W4.19) as one
continuous execution stream without pausing for human confirmation between internal slices.

**Authority:** The human explicitly requested completion of all Wave 4 work without task-by-task
pauses on 2026-09-02. This authorizes implementation and normal local verification/commits inside
the accepted Wave 4 specifications. It does not authorize source transfer, live production data
migration, enabling OIDC by default, production deployment, pushing, or changing external systems.

**Execution rule:** Internal slices remain test-first, independently reviewable, and rollback-safe,
but completion reporting occurs at the Wave 4 boundary unless a genuine external blocker requires
new authority. Runtime activation remains disabled until the W4.19 evidence gate is satisfied.

## Non-negotiable constraints

- Preserve the inference API, local-owner recovery, existing virtual-key compatibility, and all
  role/permission bundles.
- Treat Redis, durable backends, configuration, browser input, and provider output as untrusted.
- Never store or emit plaintext bearer tokens, OIDC proofs, client addresses, credentials, or raw
  identity values in keys, logs, metrics, errors, reports, or fixtures.
- Every distributed allow/admission decision requires the exact ready fencing epoch and fails
  closed for unavailable, corrupt, partial, stale, reconciling, capacity, or cleanup-backlog state.
- Keep standalone mode as the default. A coordinated configuration must validate all prerequisites
  before startup and readiness; there is no silent fallback after coordinated mode is selected.
- Keep deployment templates at one replica by default. Production release activation remains Wave
  5 even after the supported coordinated topology is recorded.
- Do not perform live durable migration, publish, push, or send source to another model/service
  without a separate explicit instruction.

## Delivery sequence

### A. Close W4.16 security coordination

1. Add Redis session lifecycle parity with fixed, bounded, cluster-slot-safe Lua using Redis time.
2. Add Redis authentication-attempt and one-time OIDC transaction parity.
3. Adapt management sessions, login/recovery/OIDC-start throttles, and OIDC transaction storage to
   the typed coordination boundary while standalone remains in-memory.
4. Add bounded security coordination metrics, opt-in live Redis parity, operator documentation,
   adversarial review, full repository gates, and a committed-runtime smoke test.

Acceptance:

- Two services sharing one backend observe issue, rotate, revoke, throttle, and consume outcomes.
- Stale authorization, replay, wrong-browser consume, partial indexes, capacity, cancellation, and
  backend outage fail closed without leaking secret material.
- Redis remains unselected by default and `WORKERS=1` remains valid for standalone mode.

### B. W4.17 routing, governance, and cache coordination

1. Inventory every routing-affecting process-local state and define a strict version-one domain for
   credential leases, route cooldowns, runtime quota reservations, exact-cache records, semantic-
   cache metadata, and invalidation generations. Separate durable authority from derived cache.
2. Implement bounded in-memory reference semantics and a shared abuse/concurrency fixture.
3. Implement fixed Redis Lua parity for lease acquire/release, cooldown publish/read, bounded quota
   coordination, cache metadata publication, and monotonic invalidation.
4. Move `SmartCredentialRouter`/credential selection, model cooldowns, virtual-key runtime quota,
   and exact response-cache admission behind injected coordination adapters. A selected coordinated
   path never falls back to process-local state.
5. Keep semantic embeddings/response bodies local-derived unless an authenticated content store is
   explicitly selected; coordinate only safe metadata and invalidation so cross-replica cache hits
   cannot serve stale or cross-policy content.
6. Add fixed-cardinality metrics, opt-in live parity, failure/restart tests, bounded performance
   measurements, operator documentation, and adversarial review.

Acceptance:

- Concurrent replicas cannot select one exclusive credential twice, bypass cooldowns/rate limits,
  overspend a hard budget, or serve cache content after a coordinated invalidation.
- All scans and cleanup loops have measured/documented caps; no user, credential, cache key,
  reservation, model, or request identifier is a metric label.
- Standalone behavior and public response formats remain compatible.

### C. W4.18 HA configuration, readiness, reconciliation, and rollback

1. Define a closed `standalone`/`coordinated` runtime policy with validated durable-backend, Redis,
   namespace, worker, replica, migration, and reconciliation prerequisites. Reject unknown or
   contradictory configuration before serving traffic.
2. Build one lifecycle owner that initializes the selected state store, verifies durable authority,
   confirms persistent epoch/namespace protection, and injects the same fenced services into all
   security/routing/quota/cache consumers.
3. Make readiness dependency-aware and content-free. Coordinated readiness stays false during
   startup, dependency loss, stale epoch, reconciliation, or drain; liveness remains independent.
4. Add explicit drain, epoch advance, reconciliation, mark-ready, and rollback commands. Commands
   are idempotent, bounded, dry-run capable where applicable, and never switch durable authority or
   delete data automatically.
5. Update Compose/Helm/container configuration with safe one-replica defaults, validated opt-in
   coordinated values, secrets references, disruption/termination behavior, probes, and topology
   ceilings. Rendered manifests must contain no credentials.
6. Add low-cardinality metrics and symptom-based alerts for coordination availability, admission
   closure, reconciliation age/backlog, durable dependency health, and readiness. Every alert links
   to an executable runbook.
7. Verify configuration matrices, container/Helm rendering, namespace backup/restore protection,
   drain/reconcile/rollback smoke tests, and unchanged standalone startup.

Acceptance:

- Unsafe topology/configuration cannot start or become ready.
- Redis namespace loss cannot be mistaken for a new deployment after coordinated activation.
- Operators can identify the failed prerequisite and execute a tested rollback to one standalone
  process without losing durable audit, identity, usage, or reservation evidence.

### D. W4.19 failure/load evidence and activation record

1. Add a reproducible local/CI harness for one-replica coordinated baseline and two-replica,
   one-worker-per-replica target topology using isolated namespaces and synthetic non-secret data.
2. Run forced application-replica loss, Redis interruption/restart, stale epoch, partial namespace,
   durable-backend outage, cancellation/unknown-result, migration interruption/resume, drain,
   reconciliation, and rollback scenarios.
3. Measure p50/p95/p99 latency, successful throughput, admission closure/recovery time, duplicate
   durable commits, budget correctness, authorization correctness, and audit/usage completeness.
4. Replace or cap any Redis-thread-blocking O(n) quota/routing/cache algorithm that misses the
   accepted performance target; record before/after measurements and reject neutral complexity.
5. Run full unit/integration/live opt-in, dependency, container, manifest, browser, accessibility,
   i18n, telemetry, security, diff, and secret gates. Missing external infrastructure is recorded as
   unavailable evidence and cannot be represented as a pass.
6. Write the activation ADR only for the exact topology whose evidence passes. The ADR records
   dependency versions, caps, prerequisites, SLO thresholds, alert/runbook links, rollback steps,
   evidence artifacts, and remaining production-release gate. If evidence is incomplete, retain
   ADR-002's single-process ceiling and close Wave 4 as implementation-ready but not activated.
7. Reconcile a final adversarial review, update architecture/operator/API/changelog/task state,
   restart the committed supported runtime, and prove health/readiness and repository cleanliness.

Acceptance targets inherited from the accepted Phase 6 specification:

- Zero unauthorized management successes, duplicate durable commits, hard-budget overshoot, or
  lost successful audit/usage commits in the forced-failure matrix.
- Redis failover keeps admissions closed until reconciliation and restores readiness within 60
  seconds in the supported topology.
- Coordinated mode adds no more than 20% p95 latency and loses no more than 15% successful
  throughput versus the one-replica coordinated baseline at the documented reference load.
- The committed activation record never claims evidence that was skipped or unavailable.

## Verification cadence

- Every behavior change: RED test, minimal GREEN implementation, focused regression, review, and
  atomic commit.
- Every two to three internal slices: affected integration suites plus Ruff/format/compile/diff.
- W4.16 and W4.17 boundaries: complete affected backend suites, opt-in live skips made explicit,
  metrics/cardinality/secret review, and documentation checkpoint.
- W4.18 boundary: standalone and coordinated configuration matrices, rendered deployment assets,
  readiness/reconciliation/rollback smoke, and container checks.
- W4.19 boundary: full repository and runtime/browser gates, final review, committed restart, clean
  worktree, and no push until the human requests it.

## Stop conditions

Continue automatically across internal task boundaries. Stop only when:

- a required live service, credential, production environment, or external network is absent and
  no faithful local substitute can produce the required evidence;
- completing the next action would require source transfer, live data migration, production
  activation, pushing, destructive deletion, or another authority not granted above;
- a correctness or security invariant cannot be satisfied without changing an accepted role,
  recovery, identity, or public compatibility contract.

When stopped, preserve a clean committed checkpoint and record exact completed work, failed
evidence, blocker, and safe next command in `tasks/current.md`.
