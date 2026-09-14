# Redis Quota State v2 Design

**Status:** Implemented and locally verified on 2026-09-05; HA activation remains denied

**Date:** 2026-09-04

**Scope:** W4-C coordination-store scalability blocker

## 1. Context

The current Redis quota scripts retain lifecycle records for idempotent reserve, commit, and release operations. Admission aggregates those records with `HGETALL` and per-record lookups. With the documented capacity of 100,000 records per quota key, the hot path is O(n) and can monopolize Redis long enough to affect unrelated tenants.

This prevents high-availability activation even though the functional quota tests pass. The redesign must remove work proportional to retained record count without weakening rate enforcement, idempotency, fencing, or fail-closed behavior.

## 2. Decisions

### 2.1 Split quota authority by time horizon

Redis coordination owns only short-window request and token admission:

- requests per minute (RPM);
- tokens per minute (TPM);
- reservation lifecycle and replay protection needed to enforce those limits.

The durable usage ledger is the sole authority for daily and monthly monetary budgets, including reservation, settlement, reconciliation, and crash recovery. Redis must not reconstruct long-horizon spend from retained lifecycle records.

Existing coordination request fields related to cost and budget remain temporarily for source compatibility. They are validated and included where required for replay identity, but they do not participate in Redis admission decisions. Runtime callers must send neutral budget values. Removing those fields is a separate interface migration.

### 2.2 Use 61 fixed second buckets

Each quota key receives a rate-bucket hash containing exactly 61 circular slots. A slot is addressed by `unix_second % 61` and stores:

- schema version;
- the absolute Unix second represented by the slot;
- accepted request count;
- accepted token count.

The authoritative time source is Redis `TIME`. A decision at second `S` aggregates slots whose absolute second is in `[S-60, S]`. This includes the complete boundary second and is therefore conservative by less than one second compared with an exact millisecond window: it may deny slightly early, but it must never admit traffic that the exact window would deny.

Slots outside the window contribute zero. A stale slot may be overwritten only after its absolute second has left the window. Values use exact integer arithmetic and existing signed-63-bit safety checks.

The bounded aggregation may use `HMGET` for all 61 known fields or an equivalent fixed-size operation. It must never enumerate lifecycle records.

### 2.3 Preserve reservation semantics

Reserve, commit, and release update buckets atomically in Lua with the corresponding lifecycle record:

- **Reserve:** add one request and the estimated token amount to the bucket for the current second.
- **Commit:** if the reservation bucket is still in the retained window, subtract its estimated contribution; add one request and the actual token amount to the current bucket.
- **Release:** if the reservation bucket is still in the retained window, subtract its contribution and do not add a replacement event.

The lifecycle record stores enough information to locate and reverse the accepted contribution, including accepted time and estimated tokens. If the original slot has aged out, commit or release performs no subtraction because that contribution is already outside the enforced window.

To ensure an active reservation record cannot expire while its accepted-second slot is still inside the conservative window, Quota State v2 requires reservation TTL to be at least 61 seconds. The production TTL remains 15 minutes. Tests and internal callers using shorter synthetic TTLs must be migrated without changing the production default.

Commit-time overspend reporting remains available for TPM: it is calculated from the fixed bucket aggregate after replacing estimated tokens with actual tokens. Monetary budget overspend is reported by the durable usage ledger, not Redis.

### 2.4 Keep lifecycle records, but remove global scans

The existing per-key lifecycle record and expiry indexes remain for:

- idempotent reserve, commit, and release;
- replay result retention;
- direct validation of the record being mutated;
- bounded expiry cleanup.

Each operation may:

- perform O(1) cardinality checks;
- read the target record directly;
- inspect the fixed 61 rate buckets;
- clean at most the existing bounded batch of 256 due records or replay entries.

It must not scan or validate every retained lifecycle record. The documented capacity of 100,000 records remains unchanged, but it no longer controls per-request work.

Global hash/ZSET integrity becomes a lifecycle reconciliation responsibility. A reconciliation procedure pages through records in bounded batches, validates record/index parity, and records progress. Readiness and HA activation remain denied until that procedure completes. During normal traffic, malformed schema metadata, a malformed touched record, invalid bucket data, counter underflow, or an inconsistent directly touched index entry fails closed.

## 3. Redis key and schema contract

Quota State v2 adds a per-quota-key bucket structure and an explicit schema marker. Exact key names will follow the existing hash-tag and tenant scoping rules so all keys used by one Lua operation remain in the same Redis Cluster slot.

The schema marker contains at least:

- `quota_state_version = 2`;
- the current coordination epoch/fencing generation;
- initialization or reconciliation state.

Every mutation script checks the marker before changing state. Missing, malformed, future, or v1 metadata returns a stable fail-closed result requiring reconciliation. Scripts must not silently initialize v2 over existing v1 data.

Bucket invariants are:

1. at most 61 slot fields exist;
2. a slot's absolute second must match its circular position;
3. request and token counters are non-negative safe integers;
4. subtraction must not underflow;
5. a slot cannot represent a time later than the Redis clock used by the operation.

## 4. Migration and rollback

There is no in-place online conversion of v1 lifecycle aggregates to v2 buckets. Coordinated HA has not been activated, so migration favors determinism over dual-write complexity.

The implemented activation workflow is:

1. keep coordinated mode denied and drain quota mutations;
2. reconcile the durable usage ledger;
3. advance exactly one coordination epoch into `reconciling` and update the configured epoch;
4. run bounded durable binding and quota reconciliation repeatedly;
5. dispose of terminal ephemeral v1 state, block on active/corrupt state, and initialize empty v2
   bucket state plus its non-expiring `2|epoch|ready` marker;
6. require a fresh complete reconciliation confirmation before marking that exact epoch ready;
7. only then permit a later HA activation decision.

Rollback to standalone mode may discard ephemeral Redis rate state. Durable budget reservations and settlements remain in the usage ledger and must not be deleted. Returning from standalone to coordinated mode requires a fresh drain and reconciliation; no rate state is inferred from the standalone process.

## 5. Failure and concurrency behavior

All lifecycle and bucket changes for one quota key occur in one atomic Lua execution. Existing ownership, replay fingerprint, and fencing checks remain authoritative.

The system fails closed when:

- schema version or epoch is invalid;
- a target lifecycle record is malformed;
- a live bucket is malformed or cannot be decoded exactly;
- a transition would make a bucket counter negative;
- cardinality or directly touched index invariants fail;
- Redis is unavailable while coordinated enforcement is required;
- durable budget authority is unavailable when a monetary budget is configured.

A denied reservation creates no rate contribution. Replaying the same accepted, denied, committed, or released operation returns the recorded result and must not mutate buckets again. Conflicting replays remain rejected.

## 6. Performance contract

For each reserve, commit, or release, work is bounded by constants independent of the number of retained lifecycle records:

- at most 61 rate slots inspected;
- at most one target lifecycle record read directly;
- at most 256 due lifecycle/replay entries cleaned;
- a fixed number of cardinality, schema, epoch, and ownership checks.

No hot-path script may call `HGETALL` on the lifecycle-record hash or perform a per-record `ZSCORE` loop. Adding records up to the 100,000-record capacity must not increase the number of records inspected by an admission operation.

This design removes the algorithmic activation blocker. It does not itself provide production latency evidence: HA remains denied until live Redis measurements and the required two-replica shared-database topology evidence satisfy the existing activation contract.

## 7. Verification strategy

Implementation will be test-driven and must cover:

### Functional parity

- RPM and TPM allow/deny boundaries;
- conservative boundary-second behavior;
- reserve-to-commit replacement of estimated with actual tokens;
- release reversal;
- commit or release after the accepted bucket ages out;
- idempotent replay and conflicting replay;
- ownership and fencing failures;
- minimum 61-second reservation TTL.

### Safety and corruption

- malformed/missing/v1/future schema marker fails closed;
- malformed bucket, wrong slot timestamp, integer overflow, and underflow fail closed;
- malformed target record and directly touched index mismatch fail closed;
- durable daily/monthly budget enforcement remains fail closed and is not duplicated in Redis.

### Bounded-work evidence

- static assertions prevent lifecycle-hash `HGETALL` and unbounded record loops in mutation scripts;
- a synthetic target with 100,000 retained records exercises the same fixed record-inspection count as a small target;
- cleanup remains capped at 256 items per operation;
- live Redis latency evidence is collected when an approved Redis environment is available.

### Regression gates

- in-memory and Redis-backed quota stores expose the same v2 behavior;
- all coordination, virtual-key, usage-ledger, API, frontend, and documentation gates pass;
- existing standalone behavior remains supported;
- HA activation records remain empty until topology and live-evidence gates pass.

## 8. Documentation updates required with implementation

The implementation change must update:

- `docs/specs/coordination-store.md` with v2 ownership, schema, and bounded-work rules;
- the W4 adversarial review disposition for the O(n) blocker;
- the HA activation disposition and evidence index;
- operator reconciliation and rollback instructions;
- roadmap/progress records without claiming HA readiness prematurely.

## 9. Rejected alternatives

### Lower the retained-record cap

Reducing 100,000 to a smaller number limits the worst case but leaves admission O(n), couples correctness latency to replay retention, and does not establish an enterprise capacity model.

### Depend on a Redis module or probabilistic counter

Modules complicate portability and deployment certification. Probabilistic counters are unsuitable for fail-closed quota decisions and exact lifecycle reversal.

### Maintain rolling totals without fixed buckets

A single rolling total cannot expire contributions exactly without an event structure that reintroduces work proportional to traffic. Fixed second buckets provide deterministic bounded state and a documented, conservative error bound.

### Convert v1 state online with dual writes

Dual-writing two quota algorithms introduces transition races and reconciliation complexity before coordinated HA has ever been activated. A drained, fenced initialization is simpler and safer.

## 10. Acceptance criteria

Quota State v2 is implementation-complete only when:

1. Redis mutation scripts contain no lifecycle-record full scan;
2. RPM/TPM semantics, replay, ownership, fencing, and fail-closed behavior pass their test matrix;
3. durable usage ledger is the only daily/monthly budget authority;
4. v1 or unreconciled state cannot silently enter v2 coordinated operation;
5. bounded-work evidence covers the 100,000-record retained-state case;
6. all repository quality gates pass;
7. documentation and evidence accurately preserve the separate remaining HA topology/live-environment blocker.

Completion of these criteria closes the Redis O(n) design blocker only. It does not authorize HA activation by itself.

## 11. Implementation and evidence

Quota State v2 was implemented in reviewable checkpoints from `343762c` through `69616a2`.
The production mutation scripts use a fixed 61-field `HMGET`, one direct lifecycle lookup, and a
257-item due preflight capped to 256 mutations; the former v1 quota Lua bodies were removed from
the runtime module. The operator exposes a closed `--quota-page-size 1..256` and persists only an
opaque cursor. `mark-ready` re-runs a one-entry authoritative reconciliation check rather than
trusting a stored completion flag.

The final deterministic evidence on 2026-09-05 is:

- 164 focused quota/HA tests passed; seven live Redis tests skipped because
  `POLARIS_TEST_REDIS_URI` was not configured;
- 1,320 backend tests passed; 30 opt-in live-backend tests skipped;
- the 100,000-retained-record synthetic case and the small case both inspected exactly one record
  and 61 buckets;
- Ruff lint/format, compileall, dependency consistency/audit, strict YAML, Compose configuration,
  45 JavaScript syntax checks, four i18n audits, and whitespace checks passed;
- Docker Desktop was installed but its Linux daemon remained unavailable, so live Redis latency
  and the required Redis plus shared-database two-replica matrix were not run.

Acceptance criteria 1-7 above are satisfied for the algorithmic checkpoint. The independent HA
topology/rollback acceptance gate remains open, `SUPPORTED_HA_ACTIVATION_RECORDS` remains empty,
and every deployment surface remains fixed to one worker and one replica.
