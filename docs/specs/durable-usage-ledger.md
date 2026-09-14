# Durable usage ledger and hard-budget journal

## Status and objective

Wave 4 slice W4.14 defines and implements the selected-backend repository for usage/cost records
and the durable hard-budget reservation journal required by ADR-006 and ADR-008. The change is
additive and internal: existing management/inference HTTP response shapes remain unchanged,
standalone remains the only supported deployment mode, and `WORKERS=1` plus one application replica
remain enforced.

W4.14 does not activate the W4.13 migration authority switch, Redis coordination, or HA. W4.15
owns Redis semantic parity and W4.18 owns operator-driven cross-backend migration/activation.

## Trust boundary and threat model

The repository accepts application-created records, but every value is still treated as untrusted
at the storage boundary because legacy databases, driver responses, and restored backups may be
malformed or tampered with.

| Threat | Failure mode | Required control |
| --- | --- | --- |
| Spoofing | Reusing a reservation/event ID for different content | Closed IDs plus exact immutable-field comparison; conflict fails closed. |
| Tampering | Negative/NaN cost, token, timestamp, or malformed stored state | Strict typed reconstruction, integer nano-USD accounting, bounded fields, finite UTC timestamps. |
| Repudiation | A provider call is committed without durable reservation evidence | Hard-budget reservations are durable before admission; commit/release transitions are revisioned and idempotent. |
| Information disclosure | Credentials, prompts, API keys, or arbitrary request bodies enter the ledger/logs | Allowlisted scalar fields only; no request/response body, bearer value, credential payload, or plaintext virtual key. |
| Denial of service | Unbounded query, document, journal, or retry growth | Indexed bounded queries, fixed aggregation shapes, reservation expiry, bounded serialization retries. |
| Elevation/overspend | Concurrent reservations read the same spend and both admit | Per-key atomic transaction/compare-and-set; no correctness dependency on a best-effort lock. |

## Canonical records

All records use schema version 1 and strict exact-field decoding.

### Usage entry

- `event_id`: application-generated `use_` identifier and idempotency key.
- `occurred_at`: finite non-negative UTC epoch seconds.
- bounded attribution: credential filename reference, request ID, model, provider, virtual-key ID.
- outcome: HTTP-like status and success flag.
- non-negative token/compression/latency/retry counters and closed quality-decision fields.
- `cost_nanos`: non-negative integer nano-USD; floating-point values never cross the repository
  boundary or participate in budget comparisons.

An unreserved event is append-only. Replaying exactly the same `event_id` is an idempotent no-op;
same ID with different content is corruption/conflict. A reserved success is stored atomically in
the reservation row/document when that reservation transitions to committed, so a process crash
cannot create a committed cost without its journal evidence or count the same transition twice.

### Hard-budget reservation

- `reservation_id`, virtual-key ID, creation/expiry time, estimated token count and cost.
- optional daily/monthly hard limits represented in nano-USD.
- state: `active`, `committed`, `released`, or `expired`; terminal states never return to active.
- optimistic revision, actual committed usage when committed, and transition timestamp.

Only requests with a hard daily or monthly budget require a durable reservation. RPM/TPM remain in
the W4.15 coordination boundary. The durable reserve operation atomically expires stale entries,
computes committed spend plus active estimates for the same key and window, and either inserts the
active reservation or returns a closed rejection reason. It is never valid to admit on an unknown
repository result or an unavailable ledger.

Commit atomically replaces the estimate with one actual usage entry. Exact replay is idempotent;
a different actual event or amount conflicts. Release is idempotent and cannot release a committed
reservation. Reconciliation expires only active reservations whose deadline passed and reports
bounded counts; it never deletes usage or terminal journal history. If a provider response
succeeded but exact durable settlement could not be confirmed, request cleanup must not release
the durable estimate. After expiry that unresolved estimate remains a conservative enforcement-
only charge for the remainder of its daily/monthly window. It is deliberately absent from actual-
usage reports because provider attribution and exact token/cost evidence were not committed. Local
settlement tracking is pruned at the durable reservation TTL and has a 100,000-entry hard ceiling;
new hard-budget admission fails with 503 at capacity. Durable expired evidence remains in the
selected repository after local tracking is pruned. This may deny later work during an outage, but
it cannot turn a known admitted request into silent zero spend.

## Repository interface

SQLite, PostgreSQL, and MongoDB implement the same async semantic interface:

1. initialize additive schema/indexes, validate required schema, and actively probe availability;
2. append an unreserved usage entry idempotently;
3. reserve hard-budget capacity atomically per virtual key;
4. atomically commit one reservation with its usage entry;
5. release or expire an active reservation idempotently;
6. query spend, credential aggregates, provider aggregates, and bounded time-series data, failing
   closed before more than 100,000 committed rows can be materialized by compatibility reporting;
7. anonymize a retired credential reference without deleting history;
8. enumerate/import W4.13 migration records in stable logical-key order.

MongoDB budget operations require transaction-capable topology. A MongoDB deployment that cannot
provide the required atomic transaction fails the durable-budget capability gate; it does not
degrade to a racy read-then-write decision.

## Runtime compatibility and migration

The existing `core.usage_stats` module remains the internal compatibility facade for normalization
and report shaping, but runtime I/O becomes async and delegates to the repository created by the
selected storage adapter. Call sites no longer run a private `usage_stats.db` connection in worker
threads.

Legacy `usage_stats.db` remains read-only migration input and is never truncated:

- SQLite standalone performs one atomic, additive, idempotent local import into `credentials.db`,
  records an append-only source marker, verifies source/target counts and keyed immutable-content
  checksums, then selects the new repository. Source shrink or prefix mutation fails closed; new
  rows may be appended. Credential/provider attribution is excluded from the immutable checksum so
  later credential retirement can anonymize it without invalidating the import evidence. Failure
  rolls back target rows and leaves the legacy source authoritative and startup unready.
- PostgreSQL/MongoDB do not silently import a host-local file or treat an empty target as zero. If
  legacy records exist without verified migration evidence, initialization reports
  `usage_migration_required`; W4.18 tooling performs the explicit cross-backend copy.
- New deployments with no legacy records begin directly on the selected repository.

## Operability

On-call questions are: is the ledger available, are durable reservations balanced, are commits
idempotent/conflicting, and is reconciliation lag growing? W4.14 emits only bounded event names and
low-cardinality counters by backend/result. It never logs filenames, virtual-key IDs, request IDs,
model text, costs tied to an identity, payloads, or driver/DSN secrets. Readiness performs a bounded
selected-repository probe on every request and must not report success when that repository
relation/collection is missing, unreadable, unavailable, or migration is required. Initialization
validates required column types/nullability, primary and unique constraints, the closed record-kind
check, and required index definitions before the repository can become ready.

## Verification and closure

- Domain abuse tests: malformed/unknown fields, non-finite values, ID conflict, terminal-state
  reversal, empty/oversized values, and exact nano-USD conversion.
- Repository contract: concurrent reserve, duplicate reserve/commit/release, expiry/reconcile,
  restart, outage, reporting, anonymization, and migration count/checksum.
- Real SQLite restart/migration tests plus opt-in live PostgreSQL/MongoDB parity tests. Driver fakes
  may prove query boundaries but do not satisfy the live-backend closure claim.
- Runtime tests prove durable journal write precedes provider admission, a failed journal releases
  in-memory capacity, successful usage commits once, failures/cancellation release once, and a
  ledger outage fails hard-budget admission closed.
- Full repository tests and CI gates pass; the standalone service restarts with health/readiness
  evidence and no activation control changes.

## Boundaries

- Always: additive schemas, parameterized operations, strict stored-record decoding, fail-closed
  unknown state, idempotent transitions, bounded queries, and no secrets in telemetry.
- Ask first: a destructive migration, public API change, external data transfer, dependency change,
  or any activation/multi-worker setting.
- Never: silent zero on ledger outage, indefinite dual-write, mutable committed usage, destructive
  rollback, float-based budget comparison, or an HA claim without live evidence.
