# W4-C External Topology Closure Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to execute this plan task by task. Every production behavior change follows `superpowers:test-driven-development`; every completed task receives specification and code-quality review before the next task starts.

**Goal:** Close Wave 4 only after Polaris enforces the accepted HA safety invariants in production code and an isolated, reproducible two-replica Redis/PostgreSQL topology passes the complete ADR-008 acceptance matrix.

**Architecture:** Keep standalone as the default and the production HA activation allowlist empty while implementation and candidate evidence are developed. Safety belongs in the real coordination, lifecycle, migration, and operator owners; the external evidence system only injects an immutable candidate verifier through existing typed seams, drives the real application, introduces controlled faults, and independently verifies durable outcomes. Evidence may make a candidate eligible for review, but only a separately reviewed activation record can change the production topology ceiling.

**Tech Stack:** Python 3.12, FastAPI/Uvicorn, Redis 8, PostgreSQL 17, asyncpg, Lua Redis scripts, Docker Compose, `unittest`, Ruff, JSON/JSONL evidence artifacts.

**Governing specifications:** `docs/decisions/008-gated-high-availability-activation.md`, `docs/specs/ha-runtime-lifecycle.md`, `docs/specs/coordination-store.md`, `docs/specs/durable-ledger-migration.md`, `docs/superpowers/plans/2026-09-04-w4.19-ha-evidence.md`, and `.superpowers/sdd/2026-09-04-w4.19-ha-evidence/ha-topology-design-review.md`.

## Global constraints

- Preserve `standalone`, one worker, and one replica as production defaults. `SUPPORTED_HA_ACTIVATION_RECORDS` stays empty until the complete matrix passes and a separate activation decision is accepted.
- Do not add an environment bypass, permissive verifier, parser exception, monkeypatch of production globals, or fixture-side safety behavior.
- New Redis scripts must remain cluster-slot-safe: every key is supplied through `KEYS`; scripts never derive a differently slotted key dynamically.
- Drain blocks new admissions atomically at the same Redis decision boundary. Idempotent commit/release/expiry for work admitted before drain remains available.
- Once a selected coordinated dependency becomes unavailable or loses authority, the running replica remains fenced on that epoch. Re-entry requires explicit new epoch, complete reconciliation evidence, mark-ready, and process restart.
- Existing durable bindings forbid implicit Redis epoch bootstrap after namespace loss. Bootstrap is explicit and allowed only for a fresh isolated deployment.
- Migration schemas and manifests are additive and versioned. Never rewrite the meaning of a completed historical checkpoint.
- Use only synthetic data and ephemeral test credentials. Artifacts contain no bearer token, password, DSN, prompt, raw identity, environment dump, or Redis key material.
- The evidence controller has no production route and the production image must not contain `tools/ha_topology_evidence`.
- No source upload, production deployment, live production migration, push, destructive volume pruning, or automatic activation is authorized by this plan.
- Every task ends with focused tests, Ruff format/check, `git diff --check`, a specification review, a quality review, and a local commit. Claims use fresh command output only.

## Task 1: Make drain an atomic admission fence and mark-ready retry-safe

**Files:**

- Modify: `backend/core/state_store.py`
- Modify: `backend/core/redis_state_store.py`
- Modify: `backend/core/ha_operator.py`
- Modify: `backend/tests/coordination_store_contract.py`
- Modify: `backend/tests/test_coordination_in_memory.py`
- Modify: `backend/tests/test_coordination_redis_live.py`
- Modify: `backend/tests/test_ha_operator.py`
- Modify: `docs/specs/coordination-store.md`
- Modify: `docs/specs/ha-runtime-lifecycle.md`

**Interface:** Add a typed coordination admission-fence contract, represented by the existing HA drain record and checked inside every semantic operation that creates new admission: credential reservation, rate/budget reservation, replay/nonce creation, management session/security mutation admission, and any routing admission that can consume exclusive capacity. Settlement methods accepting an already-issued reservation/operation identity remain idempotently callable while fenced. `HaRuntimeOperator.mark_ready()` must clear a matching completed drain even when the target epoch is already ready.

1. Add contract tests that start a drain concurrently with each admission family and assert that no admission linearized after the drain succeeds; assert pre-drain commit/release/expiry still converges idempotently.
2. Add an operator regression test for a crash after epoch-ready write but before drain deletion; retrying the same mark-ready operation must remove the drain without advancing or weakening the epoch.
3. Run the focused tests and preserve the failing output as RED evidence in the task ledger.
4. Implement the smallest typed in-memory and Redis fence mechanism. Pass the drain key explicitly to every affected Lua script and validate the bound deployment/epoch in the script before mutation.
5. Make mark-ready cleanup idempotent and reject a drain belonging to any other binding/epoch.
6. Run the focused in-memory, deterministic Redis, Redis-live, and operator suites until green.
7. Update the two specifications with the admission-versus-settlement rule and the mark-ready retry boundary.
8. Review, run Ruff/diff checks, and commit as `fix(ha): fence admissions during drain`.

## Task 2: Latch dependency loss and defend the epoch namespace

**Files:**

- Modify: `backend/core/ha_runtime.py`
- Modify: `backend/core/redis_state_store.py`
- Modify: `backend/core/ha_coordination_binding.py`
- Modify: `backend/tests/test_ha_runtime_lifecycle.py`
- Modify: `backend/tests/test_ha_coordination_binding.py`
- Modify: `backend/tests/test_coordination_redis_live.py`
- Modify: `docs/specs/ha-runtime-lifecycle.md`
- Modify: `docs/runbooks/high-availability.md`

**Interface:** Introduce an explicit process-local recovery latch with a bounded, non-secret reason category. A coordinated process that has observed Redis/durable authority failure cannot transition back to ready on the same epoch. `read_epoch` must distinguish an uninitialized fresh deployment from missing/corrupt state when a durable binding exists; only explicit bootstrap may create epoch one.

1. Add RED lifecycle tests for healthy → unavailable → same-epoch healthy probes remaining unready and for recovery only after the operator sequence plus restart on the new epoch.
2. Add RED Redis/binding tests deleting epoch plus initialization marker while the durable binding remains; startup/admission must fail closed and must not recreate epoch one.
3. Add tests for partial binding/epoch combinations, stale epoch, and bounded public error categories without secret values.
4. Implement the outage latch and explicit epoch initialization API; remove implicit initialization from ordinary reads.
5. Ensure bootstrap alone can initialize a verified empty namespace and cannot repair an existing durable binding implicitly.
6. Run lifecycle, binding, Redis deterministic/live, health, and policy tests.
7. Align the lifecycle spec and runbook with ADR-008: a successful ping is insufficient recovery.
8. Review, run Ruff/diff checks, and commit as `fix(ha): latch coordinated dependency loss`.

## Task 3: Add real versioned durable-family migration adapters and prerequisites

**Files:**

- Modify: `backend/core/durable_migration.py`
- Modify: `backend/core/durable_migration_runner.py`
- Add: `backend/core/storage/durable_family_sqlite.py`
- Add: `backend/core/storage/durable_family_postgresql.py`
- Add: `backend/core/storage/durable_family_barrier.py`
- Modify: `backend/core/ha_coordination_binding.py`
- Modify: `backend/tests/test_durable_migration_contract.py`
- Modify: `backend/tests/test_durable_migration_runner.py`
- Add: `backend/tests/test_durable_family_migration.py`
- Modify: `backend/tests/test_migration_checkpoint_external_repositories.py`
- Modify: `docs/specs/durable-ledger-migration.md`

**Interface:** Publish a new immutable manifest version that enumerates all durable application families: configuration revisions, credentials, virtual keys, identities, role bindings/auth epochs, audit, traces, usage/cost ledger, hard-budget reservation journal, and migration checkpoints. Provide concrete paginated readers, put-if-absent-or-equal writers, canonical keyed checksums, and a source mutation barrier for SQLite-to-PostgreSQL evidence. Binding bootstrap/readiness requires one exact completed canonical checkpoint with matching source/target revisions, family counts, checksums, declared authority, and manifest checksum.

1. Add RED contract tests proving every manifest family has a concrete adapter and switch-ready declaration; historical version-one checkpoints remain parseable but cannot satisfy the new prerequisite.
2. Add RED tests for bounded pagination, exact replay, conflicting duplicate rejection, checksum/count mismatch, barrier loss, interruption after target write, and interruption during verification.
3. Add PostgreSQL-live tests covering real tables and every family with synthetic records.
4. Implement additive adapters and barrier using existing repository/table semantics; do not create a generic evidence-only shadow table.
5. Implement the new checkpoint prerequisite in the binding owner and make dry-run report missing/mismatched families without secrets.
6. Run migration contract/runner/checkpoint, storage repository, binding, SQLite, and PostgreSQL-live suites.
7. Update the migration spec with manifest-version compatibility and authority transition rules.
8. Review, run Ruff/diff checks, and commit as `feat(ha): require verified durable migration`.

## Task 4: Require complete reconciliation evidence before readiness and rollback

**Files:**

- Modify: `backend/core/ha_operator.py`
- Modify: `backend/core/ha_coordination_binding.py`
- Modify: `backend/core/usage_ledger.py`
- Modify: `backend/core/identity/service.py`
- Modify: `backend/core/cache.py`
- Modify: `backend/tests/test_ha_operator.py`
- Modify: `backend/tests/test_usage_ledger_service.py`
- Modify: `backend/tests/test_identity_sessions.py`
- Modify: `backend/tests/test_response_cache.py`
- Modify: `docs/specs/ha-runtime-lifecycle.md`
- Modify: `docs/runbooks/high-availability.md`

**Interface:** Replace the quota-only completion flag with a versioned reconciliation receipt containing bounded cursors and canonical digests for quota state, durable usage/reservation liability, identity authorization/session policy, and cache invalidation authority. `mark_ready` and rollback validation accept only a complete receipt bound to deployment, prior epoch, target epoch, manifest/checkpoint, and operation identity.

1. Add RED operator tests for each absent, stale, incomplete, tampered, duplicate, wrong-epoch, and wrong-manifest receipt component.
2. Add RED service tests proving outstanding durable liability is conserved, revoked sessions cannot resurrect, and invalidated cache state cannot be accepted after reconciliation.
3. Add pagination interruption/resume tests at every component boundary and prove bounded page/cursor behavior.
4. Implement typed reconciliation component results and one canonical receipt; keep previews side-effect-free and apply operations idempotent.
5. Require the receipt for mark-ready and rollback-ready validation; never infer success from a zero-count unchallenged fixture.
6. Run operator, lifecycle, quota, usage ledger, identity, cache, binding, and Redis/PostgreSQL-live suites.
7. Update spec/runbook with exact receipt fields, recovery clocks, failure behavior, and rollback preconditions.
8. Review, run Ruff/diff checks, and commit as `feat(ha): enforce complete reconciliation barrier`.

## Task 5: Define an isolated candidate evidence contract

**Files:**

- Add: `tools/ha_topology_evidence/__init__.py`
- Add: `tools/ha_topology_evidence/__main__.py`
- Add: `tools/ha_topology_evidence/contract.py`
- Add: `tools/ha_topology_evidence/app.py`
- Add: `tools/ha_topology_evidence/admin.py`
- Add: `backend/tests/test_ha_topology_evidence_contract.py`
- Add: `backend/tests/test_ha_topology_evidence_isolation.py`
- Modify: `deploy/Dockerfile`
- Modify: `docs/specs/ha-runtime-lifecycle.md`

**Interface:** Add strict immutable `CandidateTopology`, `CandidateVerifier`, `ScenarioResult`, `CorrectnessCounters`, and `RunManifest` schemas. The candidate digest yields a syntactically valid `act_<32hex>` identifier but never enters the production allowlist. Closed commands are `preflight`, `run`, `verify`, and `cleanup`; verification recomputes hashes and exits nonzero for failed, skipped, unavailable, interrupted, not-exercised, duplicate, missing, or tampered evidence.

1. Add RED schema/evaluator tests for unknown fields, invalid enums, NaN/Infinity, duplicate/missing scenarios, zero challenged operations, candidate/image/source mismatch, artifact tampering, and interrupted atomic reports.
2. Add RED isolation tests proving the production parser still rejects replica count two, the production verifier rejects the candidate, no bypass environment variable exists, and production image contents exclude the evidence package.
3. Implement deterministic canonical serialization, digests, bounded validators, atomic report completion, and exact-candidate verification.
4. Implement the evidence-only application/lifecycle injection through constructors and the original ASGI lifespan/routes; do not monkeypatch readiness or repository drivers.
5. Validate that configuration initialization and shutdown ownership occur exactly once.
6. Run contract/isolation, policy, lifecycle, app startup, and deployment asset tests.
7. Document candidate-versus-activation semantics.
8. Review, run Ruff/diff checks, and commit as `feat(ha): add isolated candidate evidence contract`.

## Task 6: Build the real external topology, scenarios, oracle, and reports

**Files:**

- Add: `deploy/evidence/compose.ha.yml`
- Add: `deploy/evidence/Dockerfile`
- Add: `deploy/evidence/redis-primary.conf`
- Add: `deploy/evidence/redis-standby.conf`
- Add: `tools/ha_topology_evidence/fixture.py`
- Add: `tools/ha_topology_evidence/scenarios.py`
- Add: `tools/ha_topology_evidence/oracle.py`
- Add: `tools/ha_topology_evidence/report.py`
- Add: `backend/tests/test_ha_topology_evidence_live.py`
- Modify: `backend/tests/test_ha_deployment_assets.py`
- Modify: `docs/runbooks/high-availability.md`

**Interface:** Create an independent Docker Compose project with app-a, app-b, Redis primary, Redis standby, PostgreSQL, and a deterministic upstream/fault proxy. A host controller owns fixed fault actions and talks directly to each app. The oracle reads actual production durable tables/repositories and Redis authority using opaque operation digests; it never trusts only HTTP/container-health results.

1. Add RED asset tests for exact service inventory, pinned versions/digests, one worker per app, no production persistent paths, loopback-only host ports, internal network, resource bounds, read-only app filesystems, and absence of Docker socket access.
2. Add RED scenario inventory tests requiring migration interruption/resume, bootstrap interruption, baseline/target, both app losses, Redis per-app/both-path interruption, restart, true standby promotion, stale epoch, partial namespace, PostgreSQL outage, cancellation/unknown outcome, drain/reconcile/mark-ready, and standalone rollback.
3. Implement a finite deterministic provider fixture and bounded TCP fault controls; arbitrary forwarding, shell, and SQL controls are prohibited.
4. Implement process/network fault milestones, direct-app request scheduling, actual Redis standby promotion with former-primary isolation, and exact recovery timestamps.
5. Implement the independent durable oracle, conservation checks, auth/session checks, cache invalidation checks, artifact inventory, and secret scanner.
6. Implement opt-in live discovery that reports unavailable with nonzero status when mandatory infrastructure cannot execute; discovery skips never count as acceptance.
7. Run asset/unit tests and a small diagnostic Docker topology; fix only production owners when a scenario exposes a safety failure.
8. Update the runbook with preflight, run, verify, bounded cleanup, retained-volume diagnosis, and rollback commands.
9. Review, run Ruff/diff checks, and commit as `feat(ha): add external topology evidence runner`.

## Task 7: Execute the frozen acceptance matrix and decide activation eligibility

**Files:**

- Add only after a real run: `docs/evidence/<run-id>/candidate.json`
- Add only after a real run: `docs/evidence/<run-id>/manifest.json`
- Add only after a real run: `docs/evidence/<run-id>/events.jsonl`
- Add only after a real run: `docs/evidence/<run-id>/samples.jsonl`
- Add only after a real run: `docs/evidence/<run-id>/scenarios.json`
- Add only after a real run: `docs/evidence/<run-id>/summary.json`
- Modify: `docs/evidence/w4.19-ha-activation-disposition.md`
- Conditionally add after every gate passes: `docs/decisions/009-activate-tested-ha-topology.md`
- Conditionally modify after ADR acceptance: `backend/core/ha_activation.py`
- Conditionally modify after ADR acceptance: `backend/core/ha_runtime_policy.py`
- Conditionally modify after ADR acceptance: `backend/tests/test_ha_runtime_policy.py`

**Frozen workload:** 256 warm-up requests; 4,096 measured attempts per phase; concurrency 16; offered arrival rate 32 requests/second; five-second request deadline; 256 attempts per correctness scenario; reconciliation pages at most 256 records and 64 pages; 120-second scenario timeout; 45-minute total timeout; three alternating baseline/target pairs with predeclared seed variations.

**Eligibility thresholds:** zero unauthorized management success, duplicate durable logical commit, hard-budget overshoot, successful operation missing required audit/usage, revoked-session resurrection, invalidated-cache success, or unresolved liability; every required fault is positively exercised; recovery is at most 60 seconds; each pair satisfies target p95 at most 1.20 times baseline and target successful throughput at least 0.85 times baseline; no required gate is skipped, unavailable, interrupted, or not-exercised.

1. Start Docker and run preflight before the isolated project. Resolve and record exact image/server versions and immutable image digests.
2. Create a new candidate and output directory; freeze candidate, workload, caps, seeds, scenario inventory, source revision, and image IDs before running.
3. Execute all correctness/failure scenarios with synthetic data, then run the three alternating performance pairs without tuning a failed candidate.
4. Run independent `verify` from the completed manifest and scan all artifacts for secrets and source/image mismatch.
5. If any scenario/gate fails or is unavailable, keep the allowlist empty, record the exact failed disposition, preserve evidence/volumes, fix the production owner in a new reviewed task, create a new candidate, and rerun the complete invalidated scope.
6. Only if every threshold and repository gate passes, write ADR-009 referencing immutable artifact digests and exact topology. Then compile the one accepted activation record and ceiling of two replicas; never derive acceptance from runtime environment.
7. Against the activated build, rerun the negative production defaults/parser gates, isolation tests, rollback, and the complete external matrix. Any material code/config change invalidates the evidence.
8. Record the 99.9% monthly figure as an operational Wave 5 SLO, not as statistically proven by this bounded run.
9. Review the evidence/decision, run JSON/schema/hash validation and diff checks, and commit as either `docs(ha): record failed topology disposition` or `feat(ha): activate evidenced topology` according to actual results.

## Task 8: Run final Wave 4 gates and close the roadmap honestly

**Files:**

- Modify: `docs/evidence/w4.19-ha-activation-disposition.md`
- Modify: `docs/roadmap/enterprise-transformation.md`
- Modify: `tasks/current.md`
- Modify: `tasks/todo.md`
- Modify: `.superpowers/sdd/2026-09-04-w4.19-ha-evidence/progress.md`

1. Run the full backend test suite, all opt-in Redis/PostgreSQL live suites, Ruff check/format, type/static gates configured by the repository, frontend build/lint/tests, browser smoke/accessibility, i18n audits, telemetry/metrics, dependency audit, manifest/chart rendering, Docker image/startup tests, evidence verification, secret scan, and `git diff --check`.
2. Run the documented standalone rollback from the coordinated topology using the same PostgreSQL durable history; verify one process, `/health`, `/ready`, owner recovery, management policy, synthetic inference, and pre/post counts/checksums.
3. Perform fresh-context adversarial specification and code-quality reviews. Resolve every blocker/high finding and rerun affected/full gates.
4. Restart the committed tree and capture the exact revision, clean-tree status, versions, topology, commands, results, alerts/runbook references, and remaining Wave 5 operational SLO gate.
5. Check W4-C, Wave 4 report, and human acceptance only when mandatory external evidence and every gate truly pass. Otherwise leave them unchecked and state the exact blocker without weakening the criterion.
6. Commit final documentation/task-state reconciliation as `docs(roadmap): close wave 4 evidence` only after the closure condition is met.

## Plan self-review checklist

- [x] Every contradiction identified by the adversarial design review has a production-owner task before the harness can pass it.
- [x] Drain/admission and prior-work settlement semantics are explicit.
- [x] Same-epoch reconnect and partial epoch namespace loss fail closed.
- [x] Migration uses real application families, a new immutable manifest, and an authority checkpoint prerequisite.
- [x] Reconciliation covers quota, durable usage/reservation liability, authorization/session policy, and invalidation state.
- [x] Candidate evidence cannot activate production and the evidence package is excluded from the production image.
- [x] Redis failover requires a standby/promotion mechanism; restart alone is insufficient.
- [x] Performance workload, correctness thresholds, deadlines, pages, and run counts are frozen and finite.
- [x] Failure/unavailable/skipped/not-exercised results deny eligibility.
- [x] Activation and roadmap closure are conditional on fresh, reproducible evidence.
- [x] No `TBD`, `TODO`, placeholder implementation, permissive verifier, or unbounded destructive cleanup is specified.
- [x] File paths, interfaces, RED/GREEN commands, review gates, and commit boundaries are internally consistent.
