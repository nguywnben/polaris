# ADR-009: Use One Encrypted SQLite Artifact for Portable Recovery

## Status

Accepted on 2026-09-09 for the production self-hosted R1 scope.

## Context

The supported R1 deployment is one standalone process with SQLite state in one persistent volume.
Filesystem copies taken while SQLite is active can be inconsistent, credential-only ZIP exports do
not capture routing or access state, and multi-file restore would create partial-state failure
modes. Operators also need a diagnostic export that can be shared without granting access.

## Decision

Portable recovery uses one passphrase-encrypted `.ogb` envelope containing exactly a versioned
manifest and a snapshot created with SQLite's online backup API. AES-256-GCM authenticates the
ciphertext and envelope metadata; scrypt derives the key from a 12–256 character passphrase. The
passphrase is never persisted or logged.

Restore validates the complete bounded archive, hashes, SQLite integrity, foreign keys, table
inventory, state version, and exact schema fingerprint before mutation. Configured destinations
require an explicit `replace` policy. A new encrypted pre-restore artifact is persisted before the
SQLite backup transaction replaces live state. Runtime reload failure triggers restoration from
the local snapshot.

Raw logs, prior recovery artifacts, and non-authoritative auxiliary files are excluded. In
particular, model-pricing overrides are not copied: keeping recovery to one authoritative SQLite
file preserves the atomic boundary. A separate JSON projection contains only safe configuration
values and aggregate counts and is explicitly non-restorable.

## Consequences

- Routing, access, identity, quality policy, audit, trace, and ledger state move together.
- Corruption, unsafe ZIP structure, resource abuse, wrong passphrases, and incompatible schemas
  fail before live state changes.
- Exact-schema compatibility is conservative. Cross-version schema migration belongs to the
  versioned update workflow, not archive parsing. Known inert compatibility tables do not alter the
  core fingerprint; unknown tables fail closed.
- The feature supports SQLite only. PostgreSQL and MongoDB remain advanced and use their native
  operational backup mechanisms.
- Operators must retain the archive passphrase independently and verify a restored instance before
  deleting its automatic pre-restore snapshot.

## Rejected alternatives

- Raw copying of an active database was rejected because it does not provide SQLite snapshot
  consistency.
- A ZIP containing independent SQLite and pricing files was rejected because no portable atomic
  commit spans both files.
- Unencrypted or server-key-only recovery was rejected because portable archives contain usable
  provider and gateway secrets.
- Automatic best-effort migration of an unknown schema was rejected because it can silently
  produce partially compatible authorization or routing state.
