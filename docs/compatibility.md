# Compatibility and Deprecation Policy

Polaris R1 preserves the interfaces already used by self-hosted clients and the management
console. The machine-readable baseline is
`docs/compatibility/r1-compatibility-v1.json`; verify it with:

```text
python tools/compatibility_snapshot.py --check
```

## Protected R1 Surface

The version-one fixture records:

- 18 public OpenAI, Anthropic, Gemini, and Vertex inference operations;
- 112 management operations exposed under `/api/`;
- each operation's method, path, and semantic OpenAPI fingerprint after local schema references are
  resolved and documentation-only fields are removed;
- 18 server-side console entry paths, 11 canonical tabs, and the `/provider`, `/oauth`, and
  `/upload` compatibility aliases;
- removed environment names with their remediation, stored-key migrations, and removed stored
  keys;
- nine durable record schema versions; and
- seven Python/Node client examples with their base path, operation, and checked documentation or
  console source marker.

Additive routes, aliases, and examples are allowed. Removing a protected route, changing its
request/response contract, retargeting a compatibility URL, removing a config migration, changing a
record version without a migration, or letting an SDK example drift fails the guard.

## Change Rule

Do not overwrite `r1-v1` to make a breaking test pass. A protected interface may change only when
all of the following are part of the same accepted change:

1. A working replacement covers the current self-hosted use case.
2. Existing callers retain an adapter, redirect, or other compatibility path for the documented
   window.
3. Stored data/config has an automated forward migration and a tested rollback or recovery path.
4. `CHANGELOG.md` contains a user-facing deprecation notice, replacement, and removal policy.
5. A newly named fixture captures the new contract while the old fixture remains as upgrade input.

R1 defaults to advisory deprecation. Immediate removal requires a documented security or data-loss
reason and explicit approval. Historical enterprise documents remain records; this policy applies
to active product behavior and documentation.

## Upgrade Fixture

`backend/tests/fixtures/pre-r1-sqlite-v1.json` represents an old credential/config installation.
The compatibility test creates that old SQLite layout, starts the current storage manager, migrates
stored configuration names, adds missing columns, repairs legacy filename paths, and confirms the
credential and canonical values remain readable.

The fixture exposed a real SQLite limitation: a non-constant `unixepoch()` default cannot be added
to a populated table with `ALTER TABLE`. The R1 upgrade now adds timestamp columns without an
expression default, backfills existing rows, and supplies timestamps explicitly on new writes.

## Intentional Baseline Review

`python tools/compatibility_snapshot.py --print` prints the current candidate for review but does
not modify the checked fixture. A reviewer must distinguish additive change from replacement,
confirm the migration/deprecation requirements above, and create a new versioned fixture when the
contract genuinely advances.
