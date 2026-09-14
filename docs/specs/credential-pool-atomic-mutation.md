# Credential pool atomic mutation contract

## Status

Accepted W4-C blocker-closure design under ADR-008. The operator already approved the Wave 4
roadmap and instructed continuous execution. This contract refines that accepted plan; it does not
activate coordinated mode.

## Problem

Credential admission and deduplication currently compose list, read, write, state-update, and
delete calls behind a process-local `asyncio.Lock`. Two replicas can therefore observe the same
snapshot and create or retain duplicate identities. Replacing that lock with an expiring Redis
lease is unsafe: a paused holder can resume after lease expiry and mutate durable storage after a
new holder has started.

## Decision

Move the complete read-plan-write sequence behind one storage-adapter operation named
`mutate_credential_pool`. The caller supplies a synchronous, side-effect-free planner. The selected
durable backend obtains one mode-scoped transactional write gate, reads a closed snapshot, validates
the returned plan, applies every write and delete, and commits before releasing the gate.

- SQLite uses `BEGIN IMMEDIATE`. SQLite remains standalone-only, but the same contract prevents
  multi-process writer races and gives deterministic tests.
- PostgreSQL uses `LOCK TABLE <pool> IN SHARE ROW EXCLUSIVE MODE` inside one transaction. The lock
  conflicts with ordinary inserts, updates, and deletes, including existing credential refresh and
  state-update paths.
- MongoDB coordinated mode uses a transaction that increments the mode document in
  `credential_pool_write_gates` before reading or writing credential documents. Every identity
  admission and deduplication path uses this gate; ordinary refreshes are not identity-admission
  authorities and retain their existing per-document update behavior. Standalone MongoDB uses a
  manager-owned process lock because transactions may be unavailable on a non-replica-set
  deployment and horizontal scale is prohibited there. Its optional legacy Redis routing cache is
  rebuilt after a committed pool mutation.

The transaction snapshot exposes only filename, credential payload, normalized stored email, and
rotation order. The planner returns a frozen mutation envelope with copied writes/deletes plus the
existing response contract.
Filenames are basename-normalized, payloads must be dictionaries, mutation targets must be unique,
and a filename cannot be both written and deleted. Invalid stored JSON, an invalid plan, transaction
failure, or missing coordinated transaction capability fails closed.

Email discovery that can call an external provider happens before acquiring the durable gate.
Identity comparison, expiry selection, filename allocation, and duplicate deletion happen entirely
from the locked snapshot. Successful commits publish one credential invalidation wave; failed
transactions publish none.

## Failure and concurrency semantics

- A process pause holds an open database transaction; another pool mutation cannot pass the same
  durable gate.
- A process crash aborts or times out the transaction and cannot leave a transferable lease token.
- PostgreSQL and SQLite release their lock only on commit or rollback.
- MongoDB transaction conflicts are handled by the driver's bounded `with_transaction` retry. A
  deployment that cannot provide transactions cannot enter coordinated mode.
- No secret, email address, access token, or credential payload is written to a lock key, log label,
  metric label, or coordination record.
- Existing result shapes and provider-separated identity semantics remain backward compatible.

## Verification

Tests must prove a planner receives one coherent snapshot, invalid plans roll back, concurrent
clients produce one identity, failed mutations preserve the old snapshot, and each shared backend
uses its storage-bound gate. Live PostgreSQL/MongoDB parity tests remain opt-in when test URIs are
not configured; unavailable live topology evidence is not counted as a pass.
