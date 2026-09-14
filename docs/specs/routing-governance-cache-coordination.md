# Routing, Governance, and Cache Coordination Contract

## Status

Accepted implementation specification for Wave 4 slice W4.17. It implements the runtime-state
boundary accepted by ADR-006 and ADR-008 without activating coordinated deployment mode.

## Objectives

W4.17 makes every admission decision that can change provider load, quota correctness, or cache
freshness depend on an injected, fenced coordination boundary. The same semantic adapter must work
against the in-process reference and Redis-backed state store. Selecting a coordinated adapter must
never fall back to process-local state after an outage, corrupt reply, stale epoch, retry conflict,
or cancellation.

Public gateway response shapes, standalone defaults, and the one-worker/one-replica ceiling remain
unchanged until W4.18 and W4.19 finish their activation gates.

## State Inventory and Ownership

| State | Current owner | W4.17 authority | Local data allowed in coordinated mode |
| --- | --- | --- | --- |
| Credential in-flight leases | `SmartCredentialRouter._leases` | fenced CAS record per HMAC credential ID | lease handles owned by the current request only |
| Route failure/cooldown | `SmartCredentialRouter._failures` plus durable model cooldown fields | fenced CAS record per HMAC credential/model route | decoded snapshot for one selection attempt |
| Last selection and latency rank | router dictionaries | fenced bounded route record | bounded diagnostic copy |
| Credential/provider state cache | router dictionaries and durable credential storage | durable storage plus coordinated governance generation | discardable snapshot valid only for observed generation |
| Virtual-key rate/budget reservation | `VirtualKeyManager` state store | existing fenced quota lifecycle | request-local durable settlement handles |
| Virtual-key metadata cache | `VirtualKeyManager._keys_by_hash` | durable configuration plus coordinated governance generation | discardable snapshot valid only for observed generation |
| Exact response body | `ResponseCache` | local derived content only | allowed, bounded, and TTL-limited |
| Exact-cache metadata | local cache tuple | fenced CAS record containing HMAC entry ID, content digest, policy generation, and expiry | local body may be served only after metadata resolution |
| Semantic prompt/embedding/body | unused `SemanticCache` prototype | remains inactive and local-only | allowed only as discardable derived data; never sent to Redis |
| Semantic-cache metadata | none | reserved typed metadata kind and invalidation scope | no runtime activation in W4.17 |
| Model catalog cache | `ModelCatalogCache` | durable/provider source plus governance generation | discardable snapshot valid only for observed generation |
| Model blacklist | durable configuration with a process-only write lock | durable source; coordinated generation invalidates readers | no process-local authority; lost-update CAS is deferred to the durable repository revision contract |
| Fleet preview tokens | process-local bounded query service | unchanged, fail-closed UX token | allowed: a cross-replica miss cannot grant access or bypass routing/billing |
| Recent routing decisions | process-local bounded deque | local diagnostics | allowed: redacted and non-authoritative |

## Identifiers and Content Boundary

- The adapter receives a deployment-persistent secret key and derives domain-separated HMAC-SHA256
  identifiers. Raw credential filenames, virtual-key IDs, model IDs, request IDs, cache keys,
  prompts, embeddings, responses, and provider errors never enter coordination keys or payloads.
- Store-facing identifiers are lowercase hexadecimal digests or fixed allowlisted scopes. Metrics
  use only fixed backend, operation, outcome, and cache-kind labels.
- Exact response bytes stay in the bounded local `ResponseCache`. Coordinated metadata contains
  only a content SHA-256 digest, policy/invalidation generation, media-type category, and expiry.
- Semantic cache remains inactive. A future authenticated content store requires a separate
  decision and must not reuse Redis as a prompt/response body store.

## Version-One Semantic Adapter

The adapter composes the versioned `read_cas`, `compare_and_set`, `invalidate`, and
`read_invalidation_generation` primitives. All mutations carry the active fencing epoch and a
unique replay operation ID.

### Credential leases

Each opaque credential record contains a revision, a bounded ordered set of lease ID/expiry pairs,
the last-selection timestamp, and a bounded latency summary. Acquire performs read, server-backed
expiry pruning, capacity validation, and CAS. A conflict restarts from a fresh read up to the fixed
retry limit. Release removes exactly the supplied lease ID; expiry makes abandoned leases
recoverable. The adapter supports an explicit `max_concurrency`; `1` proves exclusive admission.

The router snapshots all eligible candidates, ranks using shared in-flight/last-selection/latency
evidence, and CAS-acquires the winner. A conflict reranks from fresh snapshots. It never records a
local lease before the coordinated acquire succeeds.

### Route outcomes and cooldowns

A route record is keyed by opaque credential plus opaque model scope. It contains bounded failure
count, fixed failure kind, retry-after timestamp, and latency summary. Client-request failures do
not penalize a route. Success clears the matching failure and records bounded latency. Failure
publishes the resulting retry deadline through CAS; readers reject the route until it expires.

Existing durable model cooldown fields remain readable for standalone compatibility. Coordinated
mode requires both durable and coordinated checks and treats the later deadline as authoritative;
an unavailable coordination read closes admission.

### Runtime quota

W4.17 reuses the W4.15 quota reserve/commit/release lifecycle. `VirtualKeyManager` receives the
selected store and fencing epoch explicitly, validates the epoch at construction, and forwards it
on every transition. A false-valued but valid injected store is preserved. Reset helpers may select
the in-memory store only when explicitly invoked by tests or standalone lifecycle code.

### Cache metadata and invalidation

Publishing an exact-cache body first stores the bounded local bytes, then CAS-publishes metadata
whose digest matches those bytes and whose generation matches the current exact-cache invalidation
scope. Lookup obtains the current generation and metadata before reading the local body. Any
missing, expired, stale-generation, corrupt, or digest-mismatched evidence is a miss and evicts the
local copy. Coordination failure in a selected coordinated adapter is a miss, never a local hit.

An invalidation monotonically increments the cache scope. Local caches observe it before serving.
Governance mutations similarly increment fixed scopes consumed by configuration, virtual-key,
credential, blacklist, and model-catalog caches.

Virtual-key reads use the bounded generation poll during ordinary hits. A token missing from the
local snapshot forces one current-generation read before authentication is rejected. If a
completed cross-replica mutation advanced the generation, the reader discards its snapshot and
reloads the durable key set first; an unchanged generation never triggers a durable reload. This
keeps the normal hit path bounded while ensuring a key returned by a completed management
mutation is immediately usable through another replica.

## Bounds and Failure Posture

- Maximum credential candidates per coordinated selection: 100.
- Maximum active leases in one credential record: 128.
- Maximum route latency samples: 10.
- Maximum CAS retry attempts per semantic mutation: 8.
- CAS payloads remain below the existing 16 KiB transport limit.
- Every loop and cleanup path has a fixed bound. Exhaustion returns a typed conflict/capacity
  decision; it never scans an unbounded namespace.
- Stale/reconciling epoch, backend unavailability, corrupt payload, capacity exhaustion, and retry
  exhaustion close credential/quota admission. Cache lookup fails as a miss because serving stale
  content is unsafe but forwarding the request is safe.
- Cancellation may leave only an expiring admitted lease. Commit/release operations are
  idempotent, and unknown mutation results are retried with the same operation ID.

## Compatibility and Deferred Activation

Standalone construction continues to inject `InMemoryStateStore`, preserves public formats, and
does not require Redis. W4.17 provides injection points and parity evidence only. W4.18 owns mode
validation, persistent namespace/epoch lifecycle, dependency-aware readiness, drain/reconcile,
deployment assets, and rollback. W4.19 owns forced-failure/load evidence and any activation record.

## Acceptance Evidence

- Shared in-memory and Redis contract tests cover exclusive acquisition, expiry, release,
  cooldown propagation, stale epochs, replay conflicts, cache publication, digest mismatch, and
  monotonic invalidation.
- Two independently constructed routers sharing one store cannot both acquire an exclusive
  credential or bypass a shared cooldown.
- Two virtual-key managers sharing one store cannot exceed RPM/TPM/hard-budget admission and every
  transition preserves the configured fencing epoch.
- Two cache coordinators cannot serve a local body after another replica invalidates its scope.
- Redis live parity is opt-in and reported as unavailable—not passed—when no test URI is supplied.
