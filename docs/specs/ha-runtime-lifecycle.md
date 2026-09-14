# HA runtime lifecycle contract

## Status

Superseded on 2026-09-12 by `PROD-BALANCE-R2` PB2. The implementation and executable evidence path
described below were removed; this file is retained only as a historical design record.

## Closed runtime policy

`POLARIS_RUNTIME_MODE` accepts only `standalone` (default) or `coordinated`.

Standalone requires `WORKERS=1` and `POLARIS_REPLICA_COUNT=1`. Redis coordination settings are
rejected rather than ignored when the mode is standalone, except the legacy `REDIS_URL` cache
setting while coordinated activation remains unavailable. The lifecycle creates one in-process
state store and injects that same fenced store into authentication admission, sessions, OIDC,
provider/device authorization, credential-batch coordination, credential routing, virtual-key
quota, governance invalidation, and exact-cache
metadata. Provider conversation metadata uses the same lifecycle service with HMAC-derived keys and
fenced compare-and-set updates; it never creates a second Redis client or falls back after a
coordination error.

Coordinated configuration requires all of the following:

- `WORKERS=1`; one worker per process is a permanent v1 semantic constraint.
- `POLARIS_REPLICA_COUNT=1`. W4.19 recorded no tested multi-replica ceiling.
- exactly one external durable backend: `POSTGRESQL_URI` or `MONGODB_URI`, never SQLite or both;
- `REDIS_URL` using `redis`, `rediss`, or `unix` transport;
- a validated lowercase/hyphen `POLARIS_COORDINATION_NAMESPACE` and stable
  `POLARIS_DEPLOYMENT_ID`;
- a base64url `POLARIS_COORDINATION_KEY` decoding to 32-64 bytes;
- positive `POLARIS_COORDINATION_EPOCH` matching the durable binding and Redis ready epoch;
- an exact durable migration manifest/checkpoint and an activation record compiled into a future
  release only after every required external failure/load gate passes. W4.19 produced no record.

Unknown values, empty required fields, contradictory backends, unsafe counts, or a supplied but
incomplete coordinated group reject startup. There is no local fallback after coordinated mode is
selected. MongoDB's legacy Redis acceleration is disabled in coordinated mode: the coordination
URI is reserved for the versioned namespaced adapter and never receives unnamespaced credential or
configuration cache keys.

## Persistent binding and namespace-loss defense

The durable backend is the source of a versioned coordination binding containing only deployment
ID, namespace digest, identifier-key fingerprint, fencing epoch, manifest checksum, and activation
record revision. Redis contains a matching fixed-key fenced marker. Neither side stores the raw
namespace key or Redis URI.

The lifecycle requires both records to exist and match before constructing consumers. Explicit
fresh bootstrap atomically establishes epoch one plus every fixed cache/governance invalidation
authority at generation one. A missing Redis marker, epoch, or fixed-scope generation after that
point is namespace loss/corruption and fails readiness or the first coordinated read; generation
zero is never inferred. Existing durable/shared bindings and partial authority must never initialize
or repair a fresh deployment silently. A missing durable binding requires the explicit bootstrap
command, which is itself blocked until the canonical durable inventory and W4.19 activation record
are ready. Partial bootstrap is resumable from the stable deployment ID and fingerprints, never by
deleting either side.

## Lifecycle states and readiness

States are `starting`, `standalone_ready`, `coordinated_ready`, `draining`, `reconciling`,
`unavailable`, and `closed`. Only the two ready states permit `/ready` HTTP 200. `/health` remains a
content-free process-liveness probe and never touches Redis or durable storage.

Coordinated readiness verifies the durable backend, selected usage ledger, coordination service,
exact epoch state, binding match, and not-draining state. Dependency or authority failure
immediately returns a content-free 503 projection and latches that process unavailable with one
bounded non-secret reason category. A later successful ping or binding probe cannot clear the
latch on the same process or epoch. Recovery requires drain, explicit epoch advance, complete
reconciliation, mark-ready, and a process restart configured for the new epoch; stale or
reconciling epochs never become ready automatically. Standalone retains ordinary successful-probe
recovery because it has no distributed authority to fence.

Both public inference entry points consult the process-local lifecycle admission state before
guardrails, cache lookup, routing, or upstream dispatch. This adds no dependency I/O to the request
hot path, but ensures a process already latched unavailable by readiness cannot continue serving
cached or uncached inference after binding or namespace loss.

## Operator transitions

The lifecycle exposes bounded commands for `status`, `drain`, `advance-epoch`, `reconcile`,
`mark-ready`, and `rollback-plan`.

- Mutating commands require explicit apply mode; dry-run is the default.
- Operation IDs are caller supplied or persisted so retries are idempotent.
- Drain writes the persistent typed admission fence. Each distributed admission checks that record
  under its mutation lock or Redis script, so nothing linearized after the drain write can acquire
  new capacity or admit a new security mutation. A valid fence raises a bounded admission-fenced
  error; corrupt or mismatched records fail closed. Existing CAS revisions alone are not settlement
  proof. CAS settlement remains available only when the retained successful admission declared the
  exact target key and create/update transition before the drain; the store verifies that bounded
  typed capability atomically and never parses opaque payloads or accepts a boolean/callback
  bypass. Routing grants only its lease-record update. Credential batches grant only their exact
  root/registry updates and finite owner-bound chunk creates. Device authorization claims retain
  their accepted request and grant only update of that exact encrypted flow record; release and
  consume revalidate the current owner, lease, expiry, revision, and payload before selecting the
  proof, and matching completed retries converge. Quota settlement, OIDC consume, and these
  verified CAS domain settlements remain available while the same epoch is ready.
  Unknown settlement identities do not allocate new negative replay records while drained;
  expired admission evidence cannot authorize a fresh settlement operation.
  Retained Redis CAS replay schema v1 remains readable with its legacy fingerprint before the
  fence rejects new admission, including during a valid drain. It has no capability encoding and
  therefore cannot authorize a new settlement; schema-v2 proof membership remains mandatory.
- Epoch advance moves exactly `ready(N)` to `reconciling(N+1)`. In the same Redis transaction it
  destroys every prior-epoch revocable management session and advances all exact/semantic cache
  and governance invalidation generations. Corrupt session indexes or generation records abort
  the whole transition; an epoch can never advance while stale authority remains accepted.
- Reconciliation validates bindings and durable authority; it never copies, switches, or deletes
  durable data automatically. The old quota-only completion bit is not readiness evidence. A
  version-one receipt contains the exact deployment and namespace digest, prior/target epoch,
  stable reconciliation operation ID, durable manifest checksum, migration plan/checkpoint
  revision and checksum, four ordered component results, and an HMAC signature derived from the
  coordination key. Unknown, duplicate, missing, reordered, stale, incomplete, or tampered fields
  fail closed. Every persisted intermediate receipt is HMAC-authenticated before it can be resumed;
  the final signature is additionally accepted only when all four components are complete.
- The ordered components are quota state, durable usage/reservation liability, identity
  authorization/session policy, and cache/governance invalidation authority. Each component uses
  a canonical chained digest, bounded record/page counts, opaque resume cursor, positive challenge
  count, and (for usage) active-reservation count plus liability nanos. Empty inventories still
  require a real challenged operation; zero rows alone never prove success. Any page observing a
  nonzero active-reservation count or nonzero active liability is rejected without advancing its
  cursor, including zero-cost reservations, so settlement can complete and the exact page can be
  retried. Pages are at most 256 records and 64 pages.
- Applied reconciliation pages and `mark-ready` share one owner-token coordination lock. A
  concurrent operator fails closed and retries; it cannot regress a completed receipt, recreate a
  cleared drain, or race the readiness boundary.
  Identity evidence binds every durable identity/role revision and OIDC policy epoch and requires
  zero surviving sessions from the prior epoch. Cache evidence binds all seven fixed invalidation
  scopes and requires a post-transition generation for each.
- The signed receipt is stored durably through the lifecycle-only internal configuration boundary;
  ordinary configuration invalidation is deliberately not invoked while the epoch is reconciling.
  The drain stores only the receipt checksum and completion state. Repeated calls must use the same
  operation ID and exact cursor. Component mutation and durable receipt persistence are
  interruption-safe: a retry replays bounded idempotent work before advancing the receipt.
- Mark-ready accepts only the exact reconciling epoch after reconciliation evidence. If a crash
  occurs after marking the epoch ready but before removing the drain, retrying the identical
  mark-ready operation completes removal without advancing/changing the epoch. Removal compares
  the exact completed prior-epoch drain, binding, ready epoch, and successful retained operation
  replay atomically. A different operation or mismatched/replaced drain remains an error. Dry-run
  never removes the drain. A fully completed transition with no remaining drain remains retry-safe.
  Crash completion requires the original mark-ready operation replay to remain retained. Both the
  reconciling and already-ready retry paths revalidate the HMAC receipt and exact drain checksum.
- Rollback emits and validates a plan to one standalone worker/replica only when the same complete
  signed receipt is still bound to the current deployment, epoch, manifest, and migration
  checkpoint. It never changes durable authority, clears Redis, or edits deployment configuration
  automatically.

## Recovery clocks and failure behavior

Quota reconciliation uses Redis server time and its bounded existing cursor semantics. One page
may advance through at most its requested page size of empty Redis `SCAN` windows, so unrelated
keys in a sparse namespace cannot consume the 64-page reconciliation budget one window at a time.
Durable usage liability is a stable application-table scan; identity evidence uses durable creation
order; session invalidation and cache generation advancement linearize with the Redis epoch transition.
Receipt signatures contain no wall-clock assertion, so clock skew cannot convert stale evidence
into valid evidence. Recovery duration is measured externally from the first positively exercised
fault until both direct app readiness and the independent oracle recover.
After a container restart, the evidence controller may retry only the initial read-only epoch
snapshot for up to ten seconds while Redis becomes reachable; it never retries a drain, epoch,
reconciliation, or ready mutation implicitly. Replication verification, promotion, and restoration
controls have separate fixed deadlines, and a deadline expiry leaves the scenario failed.

Any unavailable owner, malformed cursor, page overflow, active quota conflict, surviving session,
missing generation, any active reservation, any nonzero active liability, liability overflow,
signature mismatch, or binding
change leaves the epoch reconciling and admission fenced. No component can be skipped and no
operator error reveals a cursor, identifier key, session payload, DSN, or raw namespace.

## Deployment and evidence boundary

An external evidence candidate is not an activation record. The isolated evidence package freezes
the source revision/tree digest, production and launcher image digests, identical pinned Redis
primary/standby images, pinned PostgreSQL image, durable migration manifest, topology, workload,
and complete scenario inventory. Its content digest yields a syntactically valid `act_<32hex>`
candidate identifier, while the production allowlist remains empty and the production policy
continues to reject replica count two.

Only an evidence-owned `CandidateVerifier` may accept that one identifier, and only when every
independently observed source, image, dependency, worker, replica, and manifest input matches. It
is injected through the existing binding, operator, and lifecycle constructors. An ASGI wrapper
delegates all HTTP/WebSocket traffic to the original application and enters the original lifespan;
it neither patches readiness nor replaces repositories. The production policy parser first
validates a private one-replica mapping, after which the evidence boundary derives only the frozen
experimental replica count. Startup and shutdown retain exactly one lifecycle owner.

After a first matrix is independently verified and ADR-009 accepts its identifier, a newly frozen
candidate may name that identifier as its predecessor activation record. That field changes the
new candidate digest. In this mode neither the evidence policy nor the runtime lifecycle may use
the candidate verifier as activation authority: the exact predecessor must pass the compiled
production allowlist and the production policy parser itself must accept two replicas. The full
matrix is rerun against that activated build; an empty/mismatched allowlist or unchanged
one-replica ceiling fails startup.

Evidence manifests are closed, immutable, canonical JSON. Passing requires every required
scenario/repetition exactly once, a complete-pass state, positive challenged operations, observed
fault milestones where applicable, zero safety-violation counters, exact candidate/source/image
identity, and a recomputed SHA-256 for every regular artifact beneath the run directory. Missing,
duplicate, failed, skipped, unavailable, interrupted, not-exercised, non-finite, path-escaping, or
tampered evidence fails closed. A verified candidate is only `activation_eligible_for_review`; a
separate accepted ADR and subsequent production regression matrix are still required to change the
allowlist or replica ceiling.

The report archives canonical `candidate.json` under the same artifact inventory and verifies it
against an independently supplied candidate. The installed launcher package also recomputes its
own digest at application startup rather than trusting only an image label. The offline verifier
requires exactly 28,704 uniquely identified HTTP deliveries covering 28,703 logical operations
(one operation is deliberately delivered twice), the exact challenged-operation and
fault-milestone count for every frozen scenario, and aggregate sample outcomes equal to scenario
counters;
truncated, padded, contradictory, or relabeled success evidence is ineligible.

Host-side lifecycle administration runs with a dedicated, initially empty temporary credentials
directory for the entire matrix and restores the caller environment after every operation. It must
never discover or gate on a developer workstation's legacy SQLite usage ledger; the migrated
synthetic PostgreSQL inventory remains the only durable evidence authority.

Compose, Helm, and container defaults remain one worker/replica and standalone. Coordinated values
are explicit and secrets use environment/Secret references. Termination grace must allow drain;
probes remain `/health` and `/ready`.

W4.18 tests configuration matrices, lifecycle transitions, namespace-loss/partial-binding defense,
readiness, secret-free metrics, rendered manifests, and unchanged standalone startup. W4.19 owns
forced-failure/load evidence and the only activation record. Without its complete evidence, Polaris
Gateway remains supported only in standalone mode even though the coordinated implementation is
present.
