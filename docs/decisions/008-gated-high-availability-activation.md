# ADR-008: Gate High Availability on Coordinated State and Failure Evidence

## Status

Superseded on 2026-09-12 by `PROD-BALANCE-R2` PB2. Redis coordination, HA activation/evidence, and
Kubernetes deployment were retired from the active product. The content below is a historical
decision record and is not an executable runbook or current support claim.

## Context

ADR-002 deliberately enforces one worker and ADR-006 separates durable data from coordinated
runtime state. Wave 3 added durable audit/traces and atomic in-process budget reservations, but
configuration of a shared database or Redis still does not make sessions, login throttles,
credential reservations, cooldowns, cache invalidation, and every usage decision safe across
processes. Starting multiple replicas today could permit authorization drift, duplicate provider
selection, stale cache decisions, and hard-budget overshoot.

Phase 6 must define what evidence earns an HA claim, which dependency failures fail closed, how a
deployment activates the mode, and how it returns safely to standalone operation.

## Decision

Expose two explicit deployment modes:

- `standalone` remains the default, supports SQLite/PostgreSQL/MongoDB durable storage, uses the
  in-process state implementation, and enforces one worker and one replica.
- `coordinated` requires Redis plus a shared PostgreSQL or MongoDB durable backend. SQLite, missing
  migrations, partial coordination capability, or unhealthy reconciliation make readiness fail
  and prevent extra workers/replicas.

The durable boundary contains configuration revisions, credentials, virtual keys, identities,
role bindings and authorization epochs, append-only audit, bounded traces, usage/cost ledger,
hard-budget reservation journal, and migration checkpoints.
The Redis-capable runtime boundary contains sessions, login throttles, replay/nonce state,
credential reservations/cooldowns, rate/budget reservations, cache metadata/invalidation, and a
coordination fencing epoch. Only disposable, reconstructable data may remain process-local.

Callers use typed semantic operations—compare-and-set, reserve/commit/release, expire, idempotent
replay, and invalidation. Correctness does not depend on a best-effort distributed lock. Each atomic
operation is bounded, namespaced by deployment, versioned, and testable against both the in-process
and Redis implementations.

Redis unavailability or an unknown topology/fencing epoch closes new management sessions, security
mutations, credential admission, and rate/budget admission. A process may finish an already
admitted request only through idempotent commit/release. After reconnect or failover, all replicas
remain unready until a new epoch is observed and the durable usage ledger, outstanding
reservations, session policy, and invalidation state pass a reconciliation barrier. Correctness
takes precedence over degraded availability.

An accepted hard-budget reservation is written through to a durable idempotent journal before
provider execution; Redis coordinates the hot path but is not the only recovery source. This makes
recent reservation loss during asynchronous Redis replication reconstructable before admissions
resume. Durable identity authorization epochs likewise prevent a stale Redis session record from
resurrecting revoked privilege after failover.

Coordinated activation is staged and reversible:

1. Install additive durable schemas and copy records under standalone mode using resumable
   checkpoints, counts, and checksums.
2. Run all Redis semantics with one application replica and compare decision evidence.
3. Pass restart, partition, dependency-loss, stale-epoch, duplicate-delivery, and load tests.
4. Canary two replicas with one worker each, then expand only to the topology proven by the same
   matrix. Configuration rejects values above the tested ceiling.
5. Supersede ADR-002's deployment limit only in a later accepted activation record containing the
   exact tested versions, topology, results, dashboards, runbooks, and rollback command.

The initial service objectives for the supported coordinated topology are:

- 99.9% monthly end-to-end availability including required database and Redis dependency failures,
  excluding scheduled maintenance;
- recovery to ready within 60 seconds after loss of one application replica or supported Redis
  failover;
- zero unauthorized management success, duplicate durable commit, hard-budget overshoot, or lost
  successful audit/usage commit in the forced-failure acceptance matrix;
- no more than 20% additional gateway p95 latency and 15% throughput reduction versus a one-replica
  coordinated baseline at the documented reference load.

Rollback drains to a single worker/replica, blocks new admission, completes or expires outstanding
reservations, reconciles the durable ledger, verifies no active coordinated session depends on a
newer policy, and only then selects the in-process implementation. Durable records are retained;
rollback never truncates audit, trace, identity, or usage history.

## Configuration and Operability Boundary

HA configuration is environment/deployment controlled, not a general control-panel toggle. Secret
Redis/database values never enter status responses. `/ready` exposes only bounded dependency
categories. Low-cardinality metrics and alerts cover coordination availability, reconciliation
duration/failure, stale epoch, reservation imbalance, durable lag, and rollback state with linked
runbooks.

Deployment templates keep one replica unless coordinated mode and its prerequisites are explicit.
An operator cannot bypass the gate by setting `WORKERS` alone.

## Migration and Rollback

- All schema changes are additive and versioned. A migration checkpoint records source, target,
  revision, counts, checksum, and status without secret or prompt content.
- Dual-write is not accepted as an indefinite state. A bounded migration may use compare evidence,
  but one authoritative writer is declared at every step.
- Failed copy/verification leaves standalone authoritative and can resume idempotently.
- Failed coordinated activation returns to the drain/reconcile/single-replica procedure.
- No automated rollback performs destructive data deletion.

## Consequences

- HA becomes an earned capability with a reproducible evidence record instead of a replica count.
- Redis and a shared durable database become mandatory operational dependencies in coordinated
  mode; their outages intentionally affect readiness and admission.
- Reconciliation and fencing increase implementation complexity but bound split-brain behavior.
- Standalone users keep the current simple and safe deployment without mandatory Redis.
- A later activation record can narrow or raise the topology ceiling without weakening this ADR.

## Rejected Alternatives

- Enabling multiple workers when Redis merely responds to `PING` was rejected because capability
  and state migration must be complete, not just connectivity.
- Using shared SQL/MongoDB alone for every hot-path coordination decision was rejected by ADR-006.
- Continuing from process-local state during a Redis partition was rejected because it can violate
  sessions, routing reservations, and hard budgets.
- Treating Redis as the only durable source was rejected because identity, audit, trace, and usage
  require independent backup and repository semantics.
- Best-effort locks without fencing/idempotency were rejected because pauses and failover can allow
  stale holders to mutate state.

## Relationship to Existing Decisions

This ADR refines ADR-006 and does not supersede ADR-002 by itself. ADR-002 remains active until a
separate activation record proves the target topology and explicitly changes the supported limit.
