# ADR-006: Separate Durable Data from Coordinated Runtime State

## Status

Partially superseded on 2026-09-12 by `PROD-BALANCE-R2` PB2. Durable storage decisions remain
applicable; Redis coordination and multi-replica work below are historical and not supported
product surfaces.

Accepted as the prerequisite for multi-worker and multi-replica support.

## Context

Polaris supports durable credential/configuration backends, but reservations, cooldowns,
sessions, rate windows, response-cache coordination, and parts of usage aggregation still assume a
single process. Shared SQL or MongoDB storage alone does not make those runtime decisions atomic.
Advertising horizontal scale before coordinating them would allow overspend, duplicate selection,
stale invalidation, and inconsistent sessions.

## Decision

Keep `WORKERS=1` and one application replica as the enforced 1.x default until the enterprise
state contract passes failure and load tests. Divide state by semantics:

- Durable records: configuration revisions, encrypted credential records, virtual-key metadata,
  append-only audit events, bounded request traces, and the usage/cost ledger.
- Coordinated runtime state: credential reservations, cooldowns, rate/budget reservations,
  sessions, replay protection, cache metadata/invalidation, and distributed locks.
- Process-local derived state: immutable snapshots and bounded caches that are safe to discard and
  reconstruct.

Existing storage-adapter interfaces remain the durable boundary and gain typed repositories as
features land. The runtime state-store boundary gains atomic operations with an in-process
implementation for the supported single-worker mode and a Redis-capable implementation before HA
is enabled. Callers depend on semantics such as reserve/commit/release, compare-and-set, expiry,
and idempotency rather than Redis commands.

Hard budgets reserve estimated cost before provider execution, then commit actual usage or release
the reservation. Unknown pricing follows the key policy and is never silently treated as zero for
a hard limit. Audit writes are append-only and redact secrets and prompt content before crossing
the repository boundary.

HA activation requires durable-ledger parity, atomic coordination tests, failover tests, load
tests, documented operational dependencies, and a rollback path. Merely configuring PostgreSQL,
MongoDB, or Redis does not change the supported worker count.

## Migration and Rollback

- New durable records are additive and versioned; schema changes include forward migration and
  rollback notes.
- The in-process state implementation remains the rollback target for one worker.
- A deployment may disable distributed coordination only after returning to one worker/replica.
- Usage/audit data is never rolled back by destructive truncation during application rollback.

## Consequences

- Single-instance behavior remains simple and safe while enterprise state evolves behind stable
  interfaces.
- HA becomes a verified capability rather than a configuration claim.
- Redis is an optional operational dependency until HA is explicitly activated.
- Reservation semantics add complexity but prevent knowingly exceeding concurrent limits.

## Implementation Status

W3.7 implements the reserve/commit/release portion of this decision for the supported single-worker
runtime. The in-process state store atomically coordinates RPM, estimated TPM, rolling hard budgets,
expiry, and durable-ledger reconciliation. Request success commits actual usage; errors and
cancellation release capacity. Redis methods remain deliberately fail-closed, so this milestone does
not activate HA or change the one-worker/one-replica support boundary.

## Rejected Alternatives

- Enabling multiple workers with process-local state was rejected as unsafe.
- Using a SQL database for every hot-path coordination operation was rejected as the default because
  latency and locking behavior differ across supported backends.
- Storing all state in Redis was rejected because credentials, audit history, and usage ledgers need
  durable repository semantics and independent backup policy.
