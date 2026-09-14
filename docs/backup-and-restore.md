# Backup and Restore

Polaris R1 provides an authenticated, passphrase-encrypted backup workflow for the supported
standalone SQLite deployment. The workflow is intentionally separate from the credential-pool ZIP
export: a portable `.ogb` archive can restore the complete core state, while a sanitized export is
diagnostic-only and cannot restore access.

## What is protected

The encrypted archive contains a versioned manifest and a consistent SQLite snapshot. That
snapshot includes configuration metadata, credential payloads, routes, virtual keys, local and
optional OIDC identity state, quality policy, audit events, bounded request traces, migration
checkpoints, and the durable usage ledger. Raw log files, legacy `usage_stats`, and existing
pre-restore snapshots are excluded.

The sanitized JSON export contains safe configuration values and aggregate inventory counts. It
excludes provider credential payloads, root and virtual-key material, password hashes, key
previews, and other values that could authenticate a request. It is marked `restorable: false` and
must not be treated as a recovery artifact.

## Security and compatibility contract

- `.ogb` uses AES-256-GCM authenticated encryption and an scrypt-derived key. Its manifest and
  ciphertext metadata are authenticated together.
- A passphrase must contain 12–256 Unicode characters after NFKC normalization. It is accepted only
  in the request body, held for the operation, and never stored or logged. Losing it makes the
  archive unrecoverable.
- The decrypted archive is a closed two-member ZIP: `manifest.json` and
  `state/credentials.db`. Members are read without filesystem extraction.
- The upload is limited to 64 MiB, SQLite state to 45 MiB, and expanded archive to 46 MiB.
  Member count, hashes, duplicate JSON fields, traversal/symlink flags,
  SQLite integrity, foreign keys, table names, schema inventory, and validation time are bounded.
- Archive format, state schema, and the exact core SQLite schema fingerprint must be compatible.
  Known inert compatibility tables may be carried without changing the core fingerprint. R1 fails
  closed rather than attempting an implicit cross-schema migration; update Polaris through
  the supported version path before restoring an older schema.
- Portable restore is unavailable for PostgreSQL and MongoDB. PostgreSQL operators and existing
  MongoDB compatibility deployments must own and verify database-native recovery separately.

Store backup files away from the Polaris data volume and apply the same access controls as
provider credentials. A strong, unique passphrase and an encrypted operator password manager are
recommended.

## Authenticated API workflow

The Settings UI entry point is delivered by P4.6. Until then, authenticated operators use these
management endpoints:

| Operation | Endpoint | Body | Result |
| --- | --- | --- | --- |
| Create recovery archive | `POST /api/backups` | JSON `passphrase` | `.ogb` attachment |
| Validate/dry run | `POST /api/backups/validate` | multipart archive, passphrase, policy | Compatibility and inventory plan |
| Restore | `POST /api/backups/restore` | multipart archive, passphrase, policy | Restore result and snapshot ID |
| Export diagnostics | `POST /api/backups/sanitized-export` | none | Non-restorable JSON attachment |

Use an authenticated console session or the existing management bearer-token mechanism. Do not
place the passphrase in a URL or command-line argument. Prefer an HTTP client that reads it from a
masked prompt and sends it directly as JSON or multipart form data.

Validation is always a dry run and never creates a snapshot or changes state. The default
`abort_if_configured` conflict policy rejects a restore when the destination contains user state.
Select `replace` only after checking the dry-run inventory and confirming that replacement is
intended.

## Restore and rollback behavior

1. Polaris decrypts and validates the complete archive in a private work directory.
2. It checks archive/state versions and the exact live SQLite schema fingerprint.
3. It creates an encrypted pre-restore `.ogb` snapshot under
   `backend/data/creds/backups/` inside the persistent volume.
4. SQLite's backup API transactionally replaces the live database.
5. State-backed services and caches are rebound to the restored keys and records.
6. The response returns the opaque pre-restore snapshot ID and requires console reauthentication.

If replacement or runtime rebinding fails, Polaris restores the previous database and reloads
the prior runtime state. A failure to complete that automatic rollback returns a distinct service
error and retains the encrypted pre-restore snapshot for manual recovery. Never delete that
snapshot until routing, authentication, and usage state have been verified.

After a successful restore, sign in again, verify `/ready`, inspect provider availability and
routing, and make one bounded test request before resuming normal traffic. Every create, restore,
and sanitized-export operation is recorded in the durable management audit log; validation is
side-effect-free and is not recorded as a mutation.

## Recovery checklist

1. Keep the destination at one worker and one replica and stop external client traffic.
2. Make a new backup of the current state and copy it off the data volume.
3. Validate the intended archive with `abort_if_configured`, then repeat validation with `replace`
   to inspect the final plan.
4. Submit restore with `replace`; retain both the returned snapshot ID and source archive.
5. Reauthenticate and verify readiness, credentials, routes, virtual keys, identity roles, quality
   policy, and recent usage totals.
6. If verification fails, validate and restore the matching `pre-restore-<timestamp>-<id>.ogb`
   file with the same passphrase.

After verification succeeds, inspect `backend/data/creds/backups/` and remove recovery snapshots
that are no longer required, retaining at least the newest known-good rollback point outside the
live volume. R1 does not prune snapshots automatically because it cannot know which operator
recovery point is safe to delete; check free space before repeated restore rehearsals.

For release changes, use the [Compose update and rollback workflow](updating.md). It creates this
encrypted recovery artifact before replacing the image and automatically restores it if target
health verification fails.
