# Storage Support and Recovery

Polaris supports one application worker and one replica. Choosing an external database
does not enable horizontal scaling. The selected backend owns credentials, configuration,
identities, audit events, request traces, usage/cost records, and budget reservations.

## Support tiers

| Backend | Tier | Select it with | Operating contract |
| --- | --- | --- | --- |
| SQLite | **Core** | Leave both external database URIs empty | Default and recommended for personal or trusted-team self-hosting. Covered by the complete install, encrypted backup, restore, update, and rollback path. |
| PostgreSQL | **Advanced** | `POSTGRESQL_URI` | Optional for operators who already manage PostgreSQL. Repository contracts are qualified independently, but database-native backup, TLS, capacity, and upgrades remain operator responsibilities. |
| MongoDB | **Compatibility** | `MONGODB_URI` and optional `MONGODB_DATABASE` | Existing deployments remain usable and receive correctness/security fixes. MongoDB is accessed directly without a Redis cache; live MongoDB evidence is not a release blocker. Transaction-capable deployment is required by the durable usage ledger. |

Configure at most one external URI. If the selected PostgreSQL or MongoDB instance is unavailable,
startup fails closed; Polaris never silently writes to a new SQLite database. Redis is not a
storage backend or cache dependency of the supported runtime.

## Core SQLite behavior

The canonical Compose profile persists `credentials.db` and its SQLite sidecar files in the
`polaris-data` volume. Direct deployments must persist the complete credentials directory,
not copy a live database file by itself.

At startup Polaris performs a bounded, read-only `quick_check` on an existing database before
running schema changes. Corrupt or unreadable state stops startup with recovery guidance. Additive
schema compatibility changes, table creation, and credential filename repair then run in one
writer transaction; a later failure rolls the entire startup migration back. Every application
SQLite connection enables foreign-key enforcement and a five-second busy timeout. WAL mode allows
readers during a write, while SQLite still serializes writers.

The timeout absorbs short writer overlap; it is not a substitute for the supported one-worker,
one-replica topology. Repeated `database is locked` failures usually mean a second gateway process,
an operator tool holding a transaction, a stalled filesystem, or a database directory that is not
local durable storage. Do not delete `credentials.db-wal` or `credentials.db-shm` while a process is
running.

## Upgrade, rollback, and backend migration

- Before an application update, create and validate an encrypted `.ogb` archive and copy it outside
  the application data volume. The [update workflow](updating.md) binds that recovery point to the
  previous image.
- Supported SQLite upgrades are additive. The versioned pre-R1 fixture proves credentials and
  configuration survive forward migration; a forced mid-migration failure proves no partial schema
  is committed.
- Supported rollback restores the previous image and its encrypted pre-update SQLite recovery
  point. Portable restore is intentionally exact-schema and SQLite-only.
- PostgreSQL and MongoDB require database-native, point-in-time-consistent backups tested by the
  operator. The `.ogb` workflow cannot restore those backends.
- There is no supported live SQLite/PostgreSQL/MongoDB conversion command. Durable-family migration
  components retained from HA research are experimental evidence, not an operator workflow. Do not
  switch `POSTGRESQL_URI` or `MONGODB_URI` expecting existing data to move automatically.

## Failure response

| Symptom | Required response |
| --- | --- |
| SQLite integrity preflight fails | Stop retry loops, preserve the whole credentials directory, and restore a verified encrypted backup. Never initialize a blank replacement over the affected volume. |
| SQLite remains locked beyond five seconds | Confirm exactly one worker/replica, stop other writers, and verify the volume is healthy. Preserve WAL/SHM files with the database until all processes are stopped. |
| Explicit PostgreSQL or MongoDB cannot initialize | Restore that exact backend and restart. Do not remove its URI to force an implicit SQLite fallback. |
| `/ready` remains 503 after recovery | Keep traffic blocked; inspect the selected backend and verify an authenticated write survives one controlled restart. |

Operational steps are in [Durable storage unavailable](runbooks/storage-unavailable.md). SQLite
archive details and commands are in [Backup and Restore](backup-and-restore.md).

## Verification commands

The required SQLite and compatibility tests run without external services:

```powershell
python -m unittest backend.tests.test_sqlite_production_storage backend.tests.test_compatibility_guard.PreR1SQLiteUpgradeTests backend.tests.test_portable_backup
python -m unittest backend.tests.test_audit_mongodb_repository backend.tests.test_identity_mongodb_repository backend.tests.test_usage_ledger_mongodb backend.tests.test_mongodb_driver
```

PostgreSQL qualification is optional and requires a disposable database named only through the
test environment variable:

```powershell
$env:OMNI_TEST_POSTGRESQL_URI = "postgresql://user:password@127.0.0.1:5432/omni_test"
python -m unittest backend.tests.test_durable_family_migration backend.tests.test_identity_repository_live backend.tests.test_usage_ledger_live
```

The live suite creates isolated schemas and cleans them up. Never point it at a database where the
test role is not allowed to create and drop disposable schemas.
