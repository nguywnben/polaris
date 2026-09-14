# Credential batch coordination contract

## Status

Accepted W4-C blocker-closure implementation. This contract moves preview and idempotency authority
behind the lifecycle-selected coordination store and restores bounded per-domain admission. It does
not activate coordinated mode.

## Security and correctness boundary

- Preview and idempotency keys are HMAC-addressed; raw tokens, idempotency keys, filenames, and
  response bodies never appear in coordination keys, logs, or metric labels.
- CAS payloads are AES-GCM encrypted with a lifecycle-derived, domain-separated key.
- Reservations are bound to the exact request fingerprint and fencing epoch. A conflicting key,
  stale epoch, corrupt record, or unavailable backend fails closed.
- An active reservation is never automatically stolen. The route verifies exact ownership before
  every credential mutation.
- Cancellation before the first mutation releases the reservation. Once any mutation may have
  started, a completion failure retains the pending marker so a retry cannot repeat unknown work.
- Completed responses remain available for 24 hours. A response up to 256 KiB is compressed,
  divided into bounded encrypted CAS chunks, verified by digest, and made visible only by one final
  atomic root transition.
- Preview tokens expire after five minutes. Batch input remains capped at 100 targets and per-item
  execution remains bounded to five seconds.
- Preview and idempotency admissions use separate AES-GCM-encrypted CAS registries. Each registry
  holds at most 256 live full-length HMAC digests and backend-time expiries; its maximum plaintext
  size is 10,243 bytes and remains below the generic 16 KiB coordination limit.
- Expired entries are pruned during admission. Completed idempotency results retain their slot for
  the replay lifetime, explicit pre-mutation release returns the slot, and capacity exhaustion is a
  retryable HTTP 429 with `Retry-After` rather than an ambiguous availability failure.

## Failure semantics

Chunk writes that precede a failed root commit are invisible and expire. A missing/corrupt chunk,
digest mismatch, decompression overflow, duplicate JSON field in a control record, owner mismatch,
or dependency failure never returns a cached success and never grants mutation authority.

Registry transitions use bounded CAS retries and authoritative coordination time. A failed token
root publication conservatively retains its short-lived admission rather than removing a slot that
could belong to an already-published colliding token. Unknown release outcomes may temporarily
retain capacity but cannot undercount live work or grant duplicate mutation authority.

## Verification

Focused tests cover cross-client preview and replay, concurrent single-owner reservation,
conflicting key reuse, safe release, ownership fencing, large multi-chunk response reconstruction,
exact 256-entry capacity, expiry pruning, concurrent cross-client admission, completion retention,
HTTP 429/503 envelopes, stale epochs, dependency loss, cancellation, and route compatibility.
