# W4-C coordination blocker review

## Scope and result

This review covers the post-W4.19 provider authorization, Codex device-flow, credential-batch,
credential-pool, and Quota State v2 coordination changes through hardening commit `69616a2`. The
implementation removes the identified process-local identity-admission authorities, restores exact
bounded batch domains, closes the quota O(n) design blocker, keeps HA activation closed, and passes
the 1,320-test backend suite with 30 opt-in live tests skipped.

## Findings resolved

| Severity | Finding | Resolution |
| --- | --- | --- |
| Critical | Claude/xAI PKCE verifiers and callback state were process-local and unavailable to another replica. | Replaced with encrypted, provider-bound, one-time OIDC coordination using domain-separated HMAC indexes and atomic consume. |
| Critical | Codex polling could not move between replicas and concurrent pollers could exchange the same device authorization. | Added an absolute-lifetime encrypted CAS state machine with bounded leases, exact revision ownership, release-on-pending, and terminal secret erasure before token exchange. |
| Critical | Credential batch reservations and completed responses were process-local, allowing duplicate mutation across replicas. | Added fenced shared reservation ownership, ownership checks before each mutation, encrypted/chunked response publication, and retained pending state after unknown post-mutation failure. |
| Important | A 100-target response can exceed the generic 16 KiB CAS payload limit. | Responses up to 256 KiB are compressed into 12 KiB encrypted chunks; a digest-bound root CAS publishes them atomically. |
| Important | Cancellation could release an idempotency reservation after a mutation had an unknown result. | The route releases only before the first mutation; after that point failure leaves the request in progress and prevents an unsafe retry. |
| Important | The Helm replica guard text and its test diverged in the W4.19 workspace. | Restored the exact tested guard while retaining the enforced one-replica ceiling. |
| Critical | Pool admission and deduplication composed multiple storage calls behind a process-local lock, so two replicas could admit the same identity. | Moved the complete snapshot-plan-write sequence into a storage-owned mutation transaction: SQLite `BEGIN IMMEDIATE`, PostgreSQL transactional table lock, and a MongoDB transaction-conflict gate. |
| Important | Preview and idempotency state used the generic coordination capacity without the historical 256-entry domain bounds. | Added separate encrypted CAS registries capped at exactly 256 live full-HMAC entries, pruned with backend time and covered by concurrent, expiry, completion, and release tests. |
| Important | Preview capacity/outage failures could surface as an ambiguous internal error. | Capacity now returns a typed HTTP 429 with `Retry-After`; dependency failure returns a typed 503 batch envelope. |
| Important | A MongoDB pool transaction could leave the optional standalone Redis routing cache stale. | Rebuild the mode cache after the durable mutation commits; coordinated mode continues to prohibit this legacy cache. |
| Critical | Quota reserve/commit/release enumerated up to 100,000 retained records on the Redis thread. | Replaced aggregation with exactly 61 circular second buckets, one direct lifecycle lookup, and a 256-item cleanup cap. A 100,000-record synthetic target preserves the `(1 record, 61 buckets)` inspection count. |
| Critical | A persisted drain record could claim quota reconciliation complete and let `mark-ready` trust stale or forged evidence. | `mark-ready` now performs an authoritative bounded reconciliation confirmation and denies ready while any marker/lifecycle/replay evidence remains. |
| Important | A valid committed v1 record could retain beyond its active expiry, while the reconciler rejected that chronology. | The v1 parser now accepts the committed lifecycle ordering that the old scripts produced and still rejects impossible state. |
| Important | An expiring schema marker could be overwritten before its TTL was validated. | Marker existence and non-expiring TTL are validated before any disposal or initialization mutation. |
| Important | Cursor/count/identifier and fake-pipeline edges admitted ambiguous administrative results. | Reconciliation now enforces canonical opaque cursors, closed page/count/time bounds, valid identifiers, unique scan candidates, exact pipeline result counts, and fail-closed completion-marker TTL. |
| Minor | Unreferenced quota v1 Lua strings left a misleading full-scan implementation beside the v2 runtime. | Removed 658 lines of dead quota scripts and retained only the imported v2 mutation sources. |

## Retained blockers

- Live Redis plus shared database, two-replica partition/restart, completeness, and rollback tests
  remain unavailable on this host.

`SUPPORTED_HA_ACTIVATION_RECORDS` therefore remains empty and both application deployment surfaces
remain fixed at one replica.

## Verification evidence

- Full backend suite: 1,320 passed, 30 opt-in live-backend tests skipped.
- Focused Quota State v2/HA matrix: 164 passed, seven live Redis tests skipped.
- The 100,000-record and small-target quota fixtures both inspect one lifecycle record and 61
  fixed buckets; mutation scripts contain no lifecycle-hash `HGETALL` or per-record `ZSCORE` loop.
- Affected pool/import/provider/MongoDB/batch matrix: 63 passed.
- Repository-wide backend Ruff lint and format, `compileall`, `pip check`, PyPI vulnerability
  audit, strict YAML, Compose config, 45 JavaScript syntax checks, four i18n audits, and
  `git diff --check` pass.
- SQLite rollback and two-client identity admission execute against a real temporary database.
  PostgreSQL and MongoDB transaction boundaries are driver-contract tests; live shared-backend
  parity remains unavailable and is not counted as a pass.
