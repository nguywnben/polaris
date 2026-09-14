# Management Identity Repository

## Status and Scope

The versioned storage-agnostic identity contract has implementations for SQLite, PostgreSQL, and
MongoDB selected through the existing storage adapter. Repository selection does not activate OIDC
login or change the supported single-worker/single-replica topology. SQLite is Core, PostgreSQL is
Advanced, and MongoDB is Compatibility.

## Durable Records

The repository owns four schema-version-1 record families:

- management identities: local owner or OIDC user, enabled state, resource revision, and
  authorization epoch;
- one role binding per identity, with its own revision and an explicit `local_bootstrap`,
  `direct_binding`, or `claim_mapping` source;
- one OIDC policy revision/authorization epoch checkpoint;
- the fixed `management_identity_v1` additive migration checkpoint.

OIDC identity is the exact, case-sensitive `(issuer, subject)` pair. Email, display name, group
labels, secrets, tokens, and presentation profile data have no field in the durable contract.
Opaque generated `idn_…` and `rbd_…` identifiers prevent raw identity attributes from entering
resource URLs, errors, or normal record representations.

All records have a closed shape, strict primitive and enum types, bounded identifiers and
timestamps, UTC timestamps, and a supported schema version. Stored rows are reconstructed through
the same validators used for new records; unknown, malformed, incomplete, or contradictory rows
fail closed as store corruption.

## Concurrency and Owner Safety

Identity state, role bindings, and OIDC policy are separate optimistic-concurrency resources.
Callers must provide the current revision for the resource being changed. SQLite uses an immediate
write transaction, PostgreSQL uses parameterized conditional updates and transactions for
multi-table mutations, and MongoDB stores each identity/binding pair in one document so the pair
can change atomically. Concurrent writes with the same revision produce exactly one winner.
Authorization-affecting identity or role changes also advance the identity authorization epoch;
OIDC policy changes advance the policy authorization epoch.

The backward-compatible `local-owner` identity and `binding-local-owner` owner binding are created
idempotently. The bootstrap identity remains enabled and its binding is immutable. Claim mapping
cannot assign `owner`. The contract intentionally exposes no delete operation, so rollback leaves
identity and migration evidence intact.

## Backend Storage and Migration

All three implementations create only missing schema objects and bootstrap records. Initialization
does not remove legacy credential/configuration data and validates the complete identity store
before the repository becomes available. The storage adapter exposes one
`create_identity_repository()` boundary and delegates to the already-selected backend; creating a
repository does not change backend selection or activate authentication.

### SQLite

`SQLiteIdentityRepository.initialize()` opens the selected `credentials.db`, enables WAL and
foreign-key enforcement, begins one immediate transaction, and creates only additive tables and
indexes:

- `management_identities`;
- `management_role_bindings`;
- `oidc_policy_revision`;
- `identity_migrations`.

It inserts missing bootstrap records without overwriting existing rows, validates every
identity/binding pair plus the singleton checkpoints, and commits only if the complete store is
consistent. Failure rolls the transaction back and leaves pre-existing credential/configuration
tables untouched. Foreign keys are enabled on every repository connection, and dynamic values are
always passed as SQL parameters.

### PostgreSQL

PostgreSQL uses four additive tables matching the logical record families plus indexes for exact
OIDC lookup and stable `(created_at, identity_id)` ordering. Issuer and subject columns use the
deterministic `C` collation. Bootstrap and identity/binding mutations use transactions; revision
updates include the expected revision in the `WHERE` predicate. Dynamic values use asyncpg
parameters, domain timestamp strings are converted to UTC `datetime` values at the driver boundary,
and uniqueness errors become the same generic repository error as SQLite.

### MongoDB

MongoDB uses a dedicated `management_identity_state` collection. Each managed identity embeds its
binding in the same closed document so authorization mutations do not require a replica-set
transaction. Policy and migration checkpoints are separate reserved documents. A simple-collation
compound unique index applies only to OIDC identity documents, avoiding null-key collisions with
the local owner and metadata documents; a separate index provides stable list ordering. No TTL or
individual delete path exists.

## Verification Contract

The shared contract tests cover exact issuer/subject matching, duplicate rejection without
attribute leakage, closed record shapes, page bounds, additive/idempotent initialization, restart
persistence, sequential and concurrent revision conflicts, independent identity/binding revisions,
atomic role updates, policy revisions, local-owner lockout prevention, claim-to-owner rejection,
rollback, and corrupted-row failure during reads and restart.

PostgreSQL and MongoDB add driver-boundary/index/CAS tests. Fourteen opt-in live parity cases run
when `POLARIS_TEST_POSTGRESQL_URI` and/or `POLARIS_TEST_MONGODB_URI` are configured; otherwise they are
reported as skipped rather than silently using a fake service. W4.5 closed with 46 focused tests
executed, 14 live cases skipped on the local machine, and all 801 backend tests passing.

The repository is not yet a runtime authentication source. W4.6 must add opaque revocable sessions
and local-owner recovery before later OIDC slices consume durable identities.

## Implementation References

- SQLite transaction semantics: <https://sqlite.org/lang_transaction.html>
- SQLite foreign-key activation and indexing: <https://www.sqlite.org/foreignkeys.html>
- SQLite table constraints: <https://www.sqlite.org/lang_createtable.html>
- aiosqlite connection and transaction API: <https://aiosqlite.polarislib.dev/en/stable/api.html>
- asyncpg connection pool and transaction API:
  <https://magicstack.github.io/asyncpg/current/usage.html>
- PostgreSQL transaction isolation and conditional updates:
  <https://www.postgresql.org/docs/current/transaction-iso.html>
- PyMongo asynchronous API:
  <https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/>
- MongoDB unique and partial indexes:
  <https://www.mongodb.com/docs/manual/tutorial/unique-indexes-schema-validation/>
