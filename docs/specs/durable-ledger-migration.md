# Durable-ledger migration contract

## Status and scope

Wave 4 publishes immutable manifest version 2 and the concrete SQLite-to-PostgreSQL contract used
to move durable records from an authoritative standalone backend to a shared backend. The code
does not migrate production data, activate coordinated mode automatically, or relax the default
one-worker/one-replica limit. Those actions remain gated by a completed checkpoint, reconciliation,
the external topology matrix, and an accepted activation record.

## Durable inventory

The migration manifest is closed, canonical, and versioned. Its checksum covers each semantic
field (family, current owner, readiness, copy requirement, and payload sensitivity), so a caller
cannot omit a family or substitute a private inventory. It covers every durable record named by
ADR-006 and ADR-008, including implementation gaps rather than hiding them:

| Family | Current physical owner | Shared parity | Notes |
| --- | --- | --- | --- |
| Configuration | selected backend `config` record set | Yes | Includes hashed/local secrets and internal signing-key material; values are copied but never written to checkpoint metadata. |
| Provider-pool credentials | selected backend `credentials` records | Yes | Encrypted/token-bearing payload plus mutable routing fields; current complete record is copied until W4.17 separates coordinated fields. |
| Primary credentials | selected backend `primary_credentials` records | Yes | Same confidentiality rule as provider-pool credentials. |
| Virtual keys | `config.virtual_keys` versioned document | Yes, through config | Inventoried separately because it is an authorization and billing boundary. |
| Management identities | identity repository | Yes | Includes identities and authorization epochs. |
| Role bindings | identity repository | Yes | Independent optimistic revisions. |
| OIDC policy revision | identity repository | Yes | Contains policy and authorization epochs, not client secrets. |
| Identity schema evidence | identity repository | Yes | Existing additive `management_identity_v1` record. |
| Audit events | append-only audit repository | Yes | Redacted before storage. |
| Request traces | bounded trace repository | Yes | Prompt/body content is excluded by the trace contract. |
| Usage/cost ledger | selected backend `durable_usage_ledger` usage rows | Yes | Canonical application payload and indexed attribution fields move together. |
| Hard-budget reservation journal | selected backend `durable_usage_ledger` reservation rows | Yes | Active and terminal liabilities are independent from usage rows and are never inferred from aggregates. |
| Migration checkpoints | versioned checkpoint repository | W4.13 | Control-plane metadata, not a copied data family; otherwise the checkpoint would recursively inventory itself. Never contains record payloads, names, prompts, credentials, or identity attributes. |

Every version-2 manifest entry explicitly declares readiness and maps to a concrete existing
application table in both adapters. There is no generic migration shadow table. The manifest
checksum binds the exact family, ownership, copy, readiness, and sensitivity declarations.

## Record and integrity contract

Each source repository exposes records in stable application-key order through a bounded numeric
offset. The offset is derived only from the number of accepted records; repositories cannot inject
an opaque cursor into durable metadata.
A record has a closed family, a stable non-secret hashed logical ID, a private application ordering
key, a positive schema version, and a JSON
payload. The payload may contain sensitive durable data and is passed only from the source reader
to the target writer; it is excluded from checkpoints, logs, exceptions, and representations.

Copy is idempotent by `(family, logical ID)`. The target operation is strictly
`put-if-absent-or-equal`: replaying an identical record is accepted, while a target record with the
same key but different canonical content is corruption and stops the migration.
Canonical JSON rejects unsupported/non-finite values. Counts and content checksums are calculated
independently over a stable full scan of source and target. Checkpoint digests use HMAC-SHA-256 with
an injected deployment secret so low-entropy configuration values cannot be tested offline from
checkpoint data.

## Authority state machine

Exactly one backend is authoritative throughout the contract:

1. `planned` — source is authoritative; immutable plan, canonical manifest, source mutation-barrier
   evidence, and the exact source/target instance identities are recorded.
2. `copying` — source remains authoritative and write-fenced by the recorded barrier; bounded pages
   are written with put-if-absent-or-equal semantics.
3. `verifying` — source remains authoritative; source and target are scanned independently.
4. `ready_to_switch` — source remains authoritative; all requested families have equal non-zero or
   explicitly empty counts and equal keyed checksums, and all manifest entries are switch-ready.
5. `target_authoritative` — the target becomes the sole authority only through an explicit
   compare-and-set transition after all version-2 families verify. The migration runner never
   invokes this transition automatically.
6. `rollback_ready` — target remains authoritative while an operator drains and verifies the
   reverse path.
7. `rolled_back` — source becomes the sole authority after the rollback barrier.

There is no dual-authoritative or indefinite dual-write state. An interruption before
`target_authoritative`, including copy, verification, checksum, corruption, or restart failure,
leaves the source authoritative. Resume repeats at most the last uncheckpointed page and relies on
strict idempotent target writes. The source mutation barrier is revalidated before copy, after
target writes, before verification, after both scans, and immediately before any future activation
transition. Losing the barrier leaves the source authoritative and prevents new verification
evidence from being published.

## Checkpoint contract

Checkpoint records use optimistic compare-and-set revisions and persist plan ID, schema and
manifest versions, manifest checksum, source/target backend categories, instance identities and
independent endpoint revisions,
source barrier ID, phase, sole authority, safe numeric copy offset, copied count, explicit-empty
declarations, verified source/target counts and HMAC digests, timestamps, and a bounded
machine-readable failure code. Stored records are reconstructed through the same closed validators
used for new records. Unknown fields, versions, phases, backends, authority contradictions,
malformed offsets/checksums, a non-one initial revision, a non-monotonic compare-and-set update, or
target-authoritative state without completed verification fail closed as corruption. Historical
manifest-version-1 records remain strictly parseable for audit and diagnosis, but are represented
as ineligible historical checkpoints and can never satisfy coordinated readiness.

Checkpoint creation and updates are additive. No API deletes a checkpoint or copied durable data.
W4.13 defines rollback states and invariants but intentionally provides no boolean or operator-
supplied shortcut that can make the source authoritative. W4.18 must provide evidence-bearing
reverse migration, drain, reconciliation, and barrier verification. Rollback never truncates audit,
trace, identity, usage, configuration, or credential history.

## Binding prerequisite and activation boundary

A coordinated binding uses schema version 2 and includes the migration plan ID, immutable
checkpoint revision, source revision, target revision, manifest checksum, and SHA-256 digest of the
complete canonical checkpoint. Bootstrap is dry-run first. Its prerequisite report contains only a
bounded reason code, manifest/revision metadata, and missing or mismatched family names; it never
contains record payloads or backend exception text. Apply rejects missing, historical, incomplete,
wrong-authority, wrong-backend, changed-revision, or changed-checksum evidence.

Every readiness verification reloads the checkpoint from the selected durable backend and checks
that it is the exact `target_authoritative` SQLite-to-PostgreSQL checkpoint bound at bootstrap. A
checkpoint changed after binding, even if otherwise valid, fences the replica. This prevents a
valid activation record or a surviving Redis marker from bypassing durable migration evidence.

## Verification behavior

Verification is streaming and bounded-memory. A process restart during verification safely rescans
the current family from offset zero; it does not retain payloads or repository-provided cursors in
the checkpoint. W4.13 closes only when contract tests cover interruption, duplicate replay,
conflicting duplicate, checksum mismatch, corrupt persisted checkpoint, optimistic conflict,
restart/resume, invalid transition, endpoint mismatch, barrier loss, explicit-empty proof, and
rollback invariants. Version 2 supplies production SQLite/PostgreSQL record adapters, stable
non-secret instance identities, real-table mutation fencing, and live backend parity for every
family. Later Wave 4 tasks add complete reconciliation receipts, isolated topology evidence, and
the separate activation decision.
