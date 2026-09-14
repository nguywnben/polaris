# Spec: Coordinated Identity and Security State

## Status

Accepted Wave 4 scope. This document refines W4.16 under the accepted enterprise identity/HA
specification and ADR-008. It does not authorize Redis runtime selection, multiple workers,
multiple replicas, readiness changes, or OIDC-by-default activation.

## Objective

Move management sessions, local-owner login/recovery throttles, OIDC-start throttling, OIDC
authorization transaction state, and session revocation/invalidation behind one typed, fenced,
bounded coordination boundary. The standalone runtime must retain its current behavior through the
in-memory implementation. A Redis implementation must pass the same behavioral contract before
W4.18 may expose a selection control.

Success means that a later coordinated topology cannot authorize a revoked/stale session, bypass a
throttle by switching replicas, or consume one OIDC transaction more than once. W4.16 is semantic
and integration readiness, not HA activation evidence.

## Current-state inventory

| State | Current owner | W4.16 target |
| --- | --- | --- |
| Opaque management sessions and revocation indexes | `InProcessSessionStore` | Fenced security-state protocol implemented by in-memory and Redis backends |
| Password-login failures | Module-local ordered dictionary in `panel/auth_support.py` | Atomic attempt reservation and success clear |
| Local-owner recovery failures | Module-local ordered dictionary in `panel/auth_support.py` | Separately namespaced atomic attempt reservation and success clear |
| OIDC login starts | Module-local ordered dictionary in `panel/auth_support.py` | Separately namespaced atomic attempt reservation |
| OIDC state/browser binding and one-time proof | `OidcAuthorizationTransactionService` dictionary | Atomic create/consume with server-owned expiry |
| Identity/role/OIDC-policy session invalidation | Durable authorization epochs plus process-local session indexes | Durable epoch validation plus coordinated cross-process revocation indexes |

Routing reservations, quota/cache state, deployment selection, readiness, workers, and replicas are
outside W4.16 and remain assigned to W4.17-W4.19.

## Threat model

### Trust boundaries and assets

Untrusted input crosses from browser cookies, client addresses, forwarded headers under the
existing trusted-proxy policy, OIDC callback parameters, and the Redis transport. Protected assets
are opaque session authority, identity/role snapshots, local-owner recovery availability, OIDC
PKCE/nonce proofs, and the attempt counters that prevent online guessing and allocation abuse.

### Abuse cases and controls

| STRIDE concern | Abuse case | Required control |
| --- | --- | --- |
| Spoofing | Forge a session digest/reference or bind an OIDC state to another browser | At least 256-bit bearer entropy; HMAC-derived fixed-format lookup keys; constant-time browser binding |
| Tampering | Modify stored session/transaction payload or expiry/index pairs | Strict schema and closed decoding; authenticated opaque payload envelope at the identity adapter; pair/index validation before mutation |
| Repudiation | Retry an uncertain mutation and create two sessions or consume twice | Bounded operation replay for creates/rotations/throttle reservations; atomic one-time consume; existing actor-aware audit remains authoritative |
| Information disclosure | Recover bearer tokens, PKCE verifier, nonce, client address, issuer/subject, or secret from Redis keys/telemetry | Never store bearer/state/browser/PKCE/nonce plaintext; HMAC client/principal indexes; encrypted/authenticated opaque payloads; fixed-cardinality metrics |
| Denial of service | Fill session, attempt, replay, or transaction indexes; force unbounded prune/scan work | Explicit per-category capacities, TTL indexes, 256-item mutation cleanup ceiling, fail-closed reconciliation-required result, no live-record eviction |
| Elevation of privilege | Use a stale authorization snapshot, stale fencing epoch, partial namespace, or another replica after revocation | Exact ready fencing epoch on every authorization/admission mutation and session resolution; durable epoch comparison; atomic cross-process revocation |

## Architecture

### Canonical boundary

`core/security_coordination.py` owns frozen version-one request/result objects and an
`IdentitySecurityCoordinationStore` protocol that extends the W4.15 coordination surface. The
protocol is implemented structurally by `InMemoryStateStore` and `RedisStateStore`; identity and
panel callers never import redis-py or Redis commands.

The boundary has three operation families:

1. **Session lifecycle** — issue, resolve-and-touch, atomic rotate, revoke by digest/reference,
   revoke by principal/principal type, and stable bounded active-session listing.
2. **Attempt throttle** — atomically reserve one attempt in a named security category and clear
   that exact client bucket after successful local authentication.
3. **OIDC transaction** — create one browser-bound opaque transaction and atomically consume it at
   most once without deleting it for a wrong browser binding.

Every state-changing request carries the exact fencing epoch and a bounded operation ID. Session
resolution also requires the exact ready epoch because it returns an authorization decision and
touches idle expiry. A `reconciling`, stale, absent, partial, corrupt, unavailable, or cleanup-
backlogged store never returns an allow/session/proof result.

### Opaque identity adapters

The security store receives only fixed-format HMAC lookup identifiers and bounded opaque bytes.
Session and OIDC adapters own the domain codec and authenticated encryption envelope. Redis keys,
operation IDs, metrics, and errors contain no plaintext bearer, state, browser token, client
address, issuer, subject, email, group, credential, or provider secret.

The adapter derives independent keys for session lookup, session reference, principal index,
client throttle index, and payload protection from the existing persisted internal master keys.
Key separation uses explicit HMAC domains. Encryption nonces are random and stored only with the
ciphertext; the plaintext bearer, PKCE verifier, and nonce are never persisted.

### Session semantics

- Issue atomically publishes one digest/reference/principal-index record with store-clock issue,
  last-seen, idle-expiry, and absolute-expiry timestamps. A digest or reference collision fails
  closed; capacity never evicts a live session.
- Resolve atomically validates every record/index pair, the exact ready epoch, and expiry. It
  returns opaque payload plus store timestamps and advances last-seen/idle expiry no further than
  the absolute expiry.
- Rotate atomically validates and removes the old session and publishes the replacement. An
  unknown result is safely replayable using the same operation ID; the old bearer can never remain
  valid beside a successfully published replacement.
- Revoke by token/reference/principal/principal type updates all indexes atomically. Exact replay
  returns the original bounded result. Management listing is stable by HMAC reference and never
  exposes a digest or token.
- The identity repository remains durable authorization truth. Each resolve still compares the
  session snapshot with the current identity and OIDC-policy authorization epochs; repository
  outage fails closed. Coordinated revocation makes explicit mutations visible across processes.

### Throttle semantics

Login, recovery, and OIDC-start use separate allowlisted categories. The client address is
normalized by the existing trusted-proxy policy, then HMAC-indexed before it crosses the store
boundary.

An attempt is reserved atomically before password verification or OIDC transaction allocation.
The operation either increments the current store-clock window once or returns a bounded retry
delay without running the protected work. Successful password/recovery authentication clears its
bucket; failures retain the reservation. This intentionally counts all password attempts rather
than relying on a racy distributed check-then-record sequence. OIDC starts are never cleared.

### OIDC transaction semantics

- Begin generates state and browser tokens in the caller, derives nonce/verifier from state as
  today, constructs an encrypted metadata payload, and atomically creates the state-digest/browser-
  digest record with store-clock TTL.
- Consume validates the HMAC browser binding and atomically removes/returns the opaque payload.
  A wrong or malformed browser binding does not burn the transaction. A correct browser with a
  wrong response issuer consumes the transaction before the caller rejects it, preserving the
  current anti-replay posture.
- Cancellation before atomic execution leaves the transaction unchanged. Cancellation or
  transport failure after an uncertain consume fails the login closed; the user starts a new flow
  rather than risking proof reuse.

## Bounds and corruption policy

- Sessions: 100,000 maximum, policy default 10,000.
- OIDC pending transactions: 10,000 maximum, policy default 1,000.
- Tracked throttle clients: 100,000 maximum per category, existing defaults retained.
- Operation replay: 100,000 maximum per category and never longer than the underlying evidence.
- Payload: 8 KiB maximum; identifiers and operation IDs retain the W4.15 ASCII bounds.
- Cleanup: preflight at most 257 current due entries and apply at most 256 per category/mutation.

Unknown fields, malformed numeric/string forms, mismatched hash-slot/index pairs, impossible
chronology, expiring namespace markers, or partial state raise a content-free coordination error
before any mutation. Capacity and cleanup backlog fail closed without deleting live records.

## Runtime selection and lifecycle

W4.16 changes standalone callers to use the typed boundary backed by `InMemoryStateStore`. Redis
implementations remain constructor-injected test/operability artifacts. No new environment switch
or management setting selects Redis. W4.18 must add validated configuration, readiness, migration,
reconciliation, topology constraints, alerts, and rollback before selection is reachable.

All shared waiters observe one initialization/close outcome. Closing rejects new work, shields
underlying cleanup from caller cancellation, and permits retry after a failed close. Startup and
shutdown errors remain secret-free.

## Testing strategy

- Abuse-first domain tests reject bool-as-int, malformed/HMAC identifiers, invalid TTL/limits,
  oversized payloads, impossible result tuples, and secret-bearing representations.
- A reusable behavioral fixture runs against in-memory, the stateful Redis driver, and opt-in live
  Redis with implementation-supplied clock hooks.
- Session tests cover issue/resolve/touch/idle/absolute expiry, collision, rotate, revoke/list,
  cross-instance visibility, stale fencing, authorization epoch change, capacity, corruption,
  cancellation, and unknown-result replay.
- Throttle tests cover concurrent threshold admission, category isolation, success clear, retry
  delay, capacity, expiry, and client-HMAC secrecy.
- OIDC tests cover browser binding, exact one-time consume, wrong-issuer burn, expiry, capacity,
  policy drift, cancellation, and payload secrecy.
- Live Redis remains opt-in through `POLARIS_TEST_REDIS_URI`; absence is an explicit skip, never live
  evidence.

## Commands

```powershell
.\.venv\Scripts\python.exe -m unittest -q <focused W4.16 modules>
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -p 'test_*.py'
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\python.exe -m compileall -q backend
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\pip-audit.exe -r requirements.txt
```

Repository closure also runs all frontend JavaScript syntax, YAML, shell, diff, and staged-secret
gates used by W4.15.

## Boundaries

### Always

- Preserve the HTTP cookie and management API compatibility surface.
- Validate durable authorization epochs on every session resolution.
- Require the exact ready fencing epoch for every security allow/admission decision.
- Keep errors, logs, metrics, keys, and representations free of secrets and raw identities.
- Keep `WORKERS=1`, one replica, and OIDC disabled by default.

### Ask first

- Select Redis in a runtime factory, change readiness, enable OIDC by default, change role bundles,
  disable local-owner recovery, or enable more than one worker/replica.

### Never

- Store plaintext session/state/browser/PKCE/nonce/client-address values.
- Treat Redis availability alone as authorization readiness.
- Fall back to process-local state when a selected coordinated operation fails.
- Evict a live session/transaction/throttle record to admit new work at capacity.

## Success criteria

1. In-memory and Redis implementations pass one closed behavioral contract.
2. Session issue/resolve/rotate/revoke/list semantics remain API-compatible and become cross-process
   capable without plaintext bearer retention.
3. Login/recovery/OIDC-start limits cannot be bypassed by replica selection or concurrent
   check-then-record races.
4. OIDC state/browser proof is one-time, bounded, store-clock-expiring, and never persisted in
   plaintext.
5. Identity/role/password/OIDC-policy mutations revoke or stale every affected session across a
   selected shared store.
6. Standalone runtime remains in-memory with one worker/replica and unchanged health/readiness.
7. Full repository, adversarial review, dependency, secret, and committed-runtime gates pass.
