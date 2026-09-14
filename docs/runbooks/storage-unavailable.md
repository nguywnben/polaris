# Durable storage unavailable

## Contain

1. Treat `/health` as process liveness only. Keep traffic blocked while `/ready` returns 503 or
   `polaris_storage_ready` is 0.
2. Confirm the configured tier and that exactly one gateway worker and one replica are running.
3. Do not clear an external URI, create a blank database, delete SQLite WAL/SHM files, or repeatedly
   restart against suspected corruption. Preserve the current database and logs for diagnosis.

## Diagnose SQLite Core

- An `SQLite integrity preflight failed` startup error means the existing database was rejected
  before schema migration. Stop the gateway and preserve the complete credentials directory.
- For `database is locked`, stop other gateway instances and database tools, then allow the sole
  process to retry. The application waits up to five seconds for transient writer overlap.
- Verify the credentials directory is writable, durable, and local to the supported standalone
  deployment. Do not place active SQLite state on an unreliable network filesystem.
- Restore only through the encrypted [backup and restore workflow](../backup-and-restore.md). Keep
  the damaged state until the replacement passes validation and restart verification.

## Diagnose an explicit external backend

- For PostgreSQL, check DNS, TCP/TLS, credentials, role permissions, database capacity, and the
  database service itself. PostgreSQL is Advanced and uses operator-managed native recovery.
- For MongoDB, check the same connectivity and credential boundaries plus transaction capability.
  MongoDB is a Compatibility path and uses operator-managed native recovery.
- Never switch to a different implicit backend during an outage. Explicit external storage failures
  intentionally fail closed so writes cannot split across authorities.

## Recover and verify

1. Restore the exact selected backend or a verified SQLite `.ogb` recovery point, then restart one
   gateway worker only.
2. Confirm `/ready` returns 200 and `polaris_storage_ready` is 1.
3. Perform an authenticated, non-secret management write and confirm audit/trace and usage records
   persist across one controlled restart.
4. Retain the incident's last known-good backup ID, application version, backend tier, and bounded
   error type. Do not copy connection strings, credential payloads, prompts, or responses into the
   incident record.

The support boundary and migration policy are documented in [Storage support and recovery](../storage.md).
