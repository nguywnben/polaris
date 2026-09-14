# Spec: Enterprise Identity and High Availability

## Status

Accepted for Wave 4 on 2026-08-26. W4.2–W4.6 now provide the principal/permission domain, complete
existing-route authorization coverage, versioned identity repositories with SQLite, PostgreSQL,
and MongoDB parity, and opaque standalone sessions with local-owner recovery. OIDC activation,
shared session coordination, worker-count, and replica-count changes remain gated by their later
slices and acceptance evidence.

## Objective

Complete Phase 6 without weakening the supported standalone deployment. Polaris will gain
explicit management principals, four server-enforced roles, standards-based OIDC, revocable
sessions, durable governance data, Redis-backed runtime coordination, and a tested HA activation
path. Success means authorization and hard limits remain correct during concurrency and failover;
it does not merely mean that multiple processes can start.

Wave 4 governs one organization per deployment. Tenant creation, tenant-scoped data isolation,
SCIM provisioning, SAML, social login, and production release activation remain out of scope.

## Current Baseline

- Browser management authentication issues an HTTP-only opaque `panel_session` backed by a
  revocable in-process store and the durable local-owner authorization epoch. Existing signed JWTs
  are accepted only for the shorter of their original expiry or a bounded migration window.
- Every valid browser session is effectively an owner. Management virtual keys distinguish only
  `management:read` and `management:write`.
- Audit evidence attributes browser mutations to a generic redacted `panel-owner` actor.
- SQLite, PostgreSQL, and MongoDB implement durable audit and trace repositories; usage/state
  parity is not yet complete.
- Rate/budget reservations are atomic only in the supported single process. Other reservations,
  cooldowns, login/recovery throttles, opaque sessions, and cache invalidation still include
  process-local state.
- `WORKERS=1` and one application replica remain enforced.

## Trust Boundaries and Assets

External boundaries are the browser, reverse proxy, OIDC issuer metadata/JWKS/token endpoints,
management API clients, Redis, and the selected durable database. Assets are provider credentials,
virtual keys, identity/role bindings, owner recovery, sessions, audit/trace history, usage and hard
budget state, and configuration mutations.

The design addresses spoofing with verified principals, tampering with signed OIDC tokens and
atomic state operations, repudiation with actor-aware audit events, disclosure with opaque sessions
and redaction, denial of service with bounded discovery/JWKS/session stores, and elevation of
privilege with a complete route-permission coverage gate.

## Management Principal Contract

Every protected management request resolves exactly one typed principal before route execution:

| Principal | Stable identity | Authorization source |
| --- | --- | --- |
| Local owner | Deployment-local owner ID | Local password plus server-side session |
| OIDC user | Exact `(issuer, subject)` pair | Durable role binding or explicit claim mapping |
| Virtual key | Existing stable virtual-key ID | Existing management scopes |
| System | Fixed internal identifier | Internal lifecycle only; never accepted from a request |

Email, display name, and group labels are presentation data, not stable identifiers. OIDC Core only
guarantees the `(iss, sub)` pair as stable. Principal and target identifiers are HMAC-fingerprinted
before durable audit storage.

## Roles and Permissions

Roles are named permission bundles, not client-side visibility flags. The server checks one
allowlisted permission for every management route and WebSocket handshake.

| Role | Exact permission bundle |
| --- | --- |
| `viewer` | `dashboard.read`, `configuration.read`, `credentials.read`, `providers.read`, `quality.read`, `access.read`, `audit.read`, `traces.read`, `logs.read`, `identity.read` |
| `operator` | All viewer permissions plus `credentials.operate`, `routing.manage`, `quality.manage`, `logs.manage` |
| `security_admin` | All viewer permissions plus `credentials.operate`, `credentials.manage`, `credentials.export`, `providers.manage`, `access.manage`, `audit.manage`, `audit.export`, `traces.manage`, `traces.export`, `identity.manage`, `sessions.manage`, `oidc.manage`, `backup.export` |
| `owner` | Union of operator and security-admin permissions plus `configuration.manage`, `root_key.read`, `root_key.rotate`, `backup.restore`, `owners.manage`, `recovery.manage`, `ha.activate` |

The bundles are explicit and are not inferred from role name ordering. An owner-only permission
cannot be delegated through an OIDC claim. At least one working owner/recovery path must remain.
Existing virtual keys retain their current read/write behavior for existing routes; they receive no
new identity, owner, recovery, or HA permissions implicitly. Because broad `management:write` is
more powerful than the new human roles, Wave 4 inventories it as a legacy automation scope, exposes
a migration warning, and adds granular permission scopes for newly created keys before any later
removal proposal; existing keys are not silently narrowed.

Root-key disclosure and rotation are deliberately separate owner permissions. Existing broad
`management:read` keys retain access to the pre-Wave-4 root-key GET route for compatibility, but a
viewer or other human role cannot inherit that secret through `access.read`.

## OIDC Contract

- Use the confidential Authorization Code flow with PKCE `S256`, one-time `state`, and one-time
  `nonce`; implicit and password grants are unsupported.
- Discover metadata from an explicitly configured HTTPS issuer. Require exact issuer equality,
  exact registered redirect URI, bounded no-redirect fetches, TLS validation, endpoint-host policy,
  timeouts, and bounded responses. By default, authorization/token/JWKS/UserInfo origins must equal
  the issuer origin; additional origins or private-network IdPs require an environment allowlist.
  Resolve and validate every address immediately before a pinned connection, rejecting loopback,
  link-local, private, reserved, and mixed public/private answers unless explicitly allowlisted.
- Validate the ID Token signature and allowlisted asymmetric algorithm, exact `iss`, `aud`, `exp`,
  bounded `iat`/clock skew, and exact `nonce` before creating a session. If `aud` contains multiple
  values, require `azp`; whenever `azp` is present, require it to equal the configured client ID.
- Refresh JWKS once for an unknown key ID, then fail closed. Never accept `alg=none`, symmetric
  provider tokens, an attacker-selected JWKS URI, or unverified UserInfo.
- Identify a user only by `(iss, sub)`. If UserInfo is enabled, its `sub` must exactly match the ID
  Token before any values are used.
- Treat role/group claim names and values as provider-specific configuration. Missing, malformed,
  oversized, or unmapped values deny login by default. Direct subject bindings take precedence.
- Do not persist provider access, refresh, or ID tokens after the internal session is established.
  The initial Wave 4 client secret is environment/file-secret only; management APIs expose only a
  configured-state marker and can never create, read, update, or export its value.
- Accept a query-delivered authorization code only at the exact callback, mark the response
  `no-store`, exchange it once, and immediately return a 303 redirect to a clean same-origin path so
  the code is not retained in the application URL or rendered into the page.

Supporting normal enterprise RS256/PS256/ES256 verification requires the optional cryptographic
backend for PyJWT. Wave 4 approves changing the runtime requirement from `PyJWT` to
`PyJWT[crypto]` in W4.7; the dependency must be pinned and audited before use.

## Session and Recovery Contract

- Replace new browser JWT sessions with at least 256-bit opaque random values. Store only an HMAC
  digest plus principal, issued/last-seen time, idle/absolute expiry, authentication method, and
  authorization epoch in the session store.
- Keep the cookie HTTP-only, same-site, path-scoped, and secure whenever HTTPS is authoritative.
  Never put a session, OIDC code, token, or PKCE verifier in browser storage or a query string after
  callback processing.
- Rotate the session on authentication and privilege change. Revoke it on logout, identity disable,
  role downgrade, owner-password rotation, or OIDC configuration revision.
- Existing sessions may survive an OIDC outage until their local expiry. New OIDC login fails
  closed when validation dependencies are unavailable.
- The local owner remains the break-glass path by default. It is separately rate-limited, fully
  audited, and can be restricted to loopback/trusted administrative ingress. It cannot be disabled
  unless another tested recovery mechanism and an active owner binding exist.

W4.6 implements this contract for the standalone topology. New setup, login, and recovery flows
issue 256-bit opaque values; the store retains only an HMAC index and bounded metadata. Logout,
password rotation, expiry, and authorization-epoch change revoke or invalidate sessions. Provider
OAuth state receives only an ephemeral HMAC reference, never the bearer session. Active sessions
are deliberately lost on process restart until W4.16 supplies shared coordination. The maintained
operator contract is [Management Sessions and Local-Owner Recovery](../management-sessions.md).

## Management API Principles

New APIs live under `/api/identity` and remain additive. Typed request/response schemas, bounded
pagination, optimistic revisions, generic error details, and one common authorization dependency
are required. The proposed resource families are session status, OIDC configuration, identities,
role bindings, active sessions, and recovery verification.

All protected OpenAPI routes must appear in a declarative permission manifest. All write routes
must also appear in the management audit matrix or have an explicit side-effect-free exclusion.
Frontend navigation and controls consume server-returned permissions but never constitute the
authorization boundary.

## Durable and Coordinated State

Coordinated mode requires a shared PostgreSQL or MongoDB durable backend and Redis. SQLite remains
the default standalone backend and is rejected for HA activation.

- Durable: configuration revisions, encrypted credentials, virtual keys, identities, role
  bindings and authorization epochs, append-only audit, bounded traces, usage/cost ledger, hard-
  budget reservation journal, and migration checkpoints.
- Coordinated runtime: management sessions, login throttles, replay/nonce state, credential
  reservations/cooldowns, rate/budget reservations, cache metadata/invalidation, and fencing epoch.
- Local derived: immutable snapshots and caches that can be discarded and rebuilt without changing
  an authorization, limit, routing, or billing decision.

In coordinated mode, every replica derives the opaque management-session HMAC key from the shared
coordination key with a dedicated domain separator. It must not race through a last-writer-wins
durable config bootstrap. Standalone mode retains its persisted random session master key so local
sessions survive a process restart. Rotating the coordinated key intentionally invalidates all
sessions tied to the previous coordination trust domain.

The W4.4–W4.5 durable identity contract uses exact case-sensitive issuer/subject identity, separate
optimistic revisions for identity and binding resources, authorization epochs, and a fixed additive
migration checkpoint. SQLite, PostgreSQL, and MongoDB bootstrap an immutable enabled local owner and
validate all stored records before completing initialization. PostgreSQL uses transactional
multi-table mutations; MongoDB embeds each identity/binding pair for single-document atomicity.
All backends provide no destructive rollback or delete path and are selected through the existing
storage adapter. The maintained implementation contract is `docs/identity-repository.md`.

Callers depend on typed compare-and-set, reserve/commit/release, expiry, idempotency, and
invalidation semantics—not Redis commands. New admissions and security mutations fail closed when
required coordination is unavailable. After a Redis topology loss, an epoch/reconciliation barrier
must complete before admissions resume.

CAS record lifetime and CAS replay-evidence lifetime are separate contract values. Durable routing
and outcome records may outlive the short uncertainty window in which retrying an operation must
return its exact prior result. High-churn routing, release, outcome, and cache mutations therefore
retain replay evidence for a bounded window; credential admissions retain it for at least the lease
lifetime so an admitted request can still present a valid settlement proof. Exhausted or unavailable
coordination is reported as a sanitized HTTP 503 and never leaks a storage exception as HTTP 500.
Expired high-churn CAS replay evidence is validated and removed in fixed batches of at most 256 per
mutation. A larger expiry backlog therefore converges incrementally without unbounded Lua work or a
permanent reconciliation loop; the global replay-capacity check remains enforced after each batch.

Redis is not the sole source of truth for an accepted hard-budget reservation: the reservation is
written through to a durable idempotent journal before provider work starts. Reconciliation rebuilds
coordination state from that journal and the committed usage ledger, avoiding an overspend window
when asynchronous Redis replication loses a recently acknowledged key.

## Activation and Rollback

1. Keep standalone mode active while additive schemas and repositories are installed.
2. Copy and verify durable records with counts, checksums, and resumable migration checkpoints.
3. Enable Redis coordination with one replica and run parity/shadow evidence.
4. Pass failure and load gates, then canary two replicas with one worker each.
5. Expand worker/replica limits only after the same invariants pass at the target topology.

Rollback first drains to one worker/replica, blocks new admissions, reconciles reservations and the
durable ledger, and only then returns to the in-process state implementation. Audit, usage, and
identity records are never destructively rolled back.

## Multi-Replica Acceptance Targets

- Correctness: zero unauthorized management successes, duplicate durable commits, hard-budget
  overshoot, or lost successful audit/usage commits in the forced-failure matrix.
- Recovery: loss of one application replica causes no manual recovery; Redis failover keeps new
  admissions closed until reconciliation and restores readiness within 60 seconds in the supported
  topology.
- Availability objective: 99.9% monthly end-to-end for a correctly provisioned coordinated
  deployment, including required database and Redis dependency failures but excluding scheduled
  maintenance; correctness takes precedence over availability.
- Performance: at the documented reference load, coordinated mode adds no more than 20% to gateway
  p95 latency and does not reduce successful throughput by more than 15% versus the one-replica
  coordinated baseline.
- Operability: readiness identifies the unavailable dependency without secrets, alerts link to
  recovery runbooks, and rollback is exercised rather than documented only.

## Tech Stack

- Python 3.12/3.14, FastAPI 0.x, Pydantic 2, Hypercorn, httpx.
- PyJWT 2 with proposed `crypto` extra for asymmetric OIDC verification.
- SQLite standalone; PostgreSQL or MongoDB for HA durable state; Redis 8 client for coordination.
- Server-assembled HTML, plain JavaScript, layered CSS, and keyed 15-locale catalogs.

## Commands

```powershell
.\.venv\Scripts\python.exe -m backend.tests
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m ruff format --check backend
.\.venv\Scripts\python.exe -m compileall -q backend
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit --local --progress-spinner off
Get-ChildItem frontend/js -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
```

Live PostgreSQL, MongoDB, Redis, multi-process failure, load, container, and browser matrices are
checkpoint gates and must run in CI or an explicitly configured local environment.

## Project Structure

```text
backend/core/identity/          Principals, permissions, OIDC, sessions, recovery
backend/core/panel/             Additive identity management routes
backend/core/storage/           Durable identity/ledger repositories and migrations
backend/core/state_store.py     Standalone and Redis semantic coordination boundary
backend/tests/                  Unit, contract, integration, failure, and migration tests
frontend/fragments/pages/       Identity console page
frontend/js/features/           Identity/session/role workflows
frontend/js/core/               Navigation, permissions, localization
deploy/                         Redis/HA configuration, probes, alerts, rollback tooling
docs/runbooks/                  Identity, dependency, failover, and rollback procedures
```

## Testing Strategy

- TDD for every behavior change, beginning with denial and abuse cases.
- A generated permission matrix covers every management route, method, principal, and role.
- OIDC fixtures cover metadata/JWKS poisoning, issuer/audience/algorithm/nonce/state failures, key
  rotation, replay, claim bounds, timeout, and provider outage without real secrets.
- Session tests cover fixation, revocation, expiry, privilege change, concurrent logout, recovery,
  CSRF, and cross-origin requests.
- Repository parity covers SQLite standalone plus live PostgreSQL/MongoDB; coordinated tests cover
  live Redis, restart, expiry, idempotency, failover, and reconciliation.
- Browser checks cover 360/768/1024/1440, all themes, 15 locales, keyboard/focus, permission-driven
  navigation, recovery warnings, clean console/network, and secret/token absence.

## Boundaries

### Always

- Preserve inference API and existing virtual-key compatibility.
- Deny unknown principals, claims, roles, permissions, algorithms, issuers, and coordination state.
- Audit authentication, authorization denial, identity/role/session/recovery, migration, and HA
  activation events using bounded redacted fields.
- Keep `WORKERS=1` and one replica until the full activation gate passes.

### Ask first

- Enable OIDC as a default login path, disable local owner access, change role bundles, run a live
  data migration, or enable coordinated/multi-replica mode.

### Never

- Infer identity from email alone or assign a default role to an unmapped OIDC user.
- Trust UI visibility, an unsigned token, provider text, forwarded headers, or Redis availability
  as an authorization decision.
- Store plaintext sessions, PKCE verifiers, OIDC tokens, virtual keys, or provider secrets.
- Continue hard-budget admission through unknown or partitioned coordination state.

## Success Criteria

1. All management surfaces resolve a typed principal and a server-enforced permission.
2. The four roles pass the complete allow/deny matrix; UI exposure matches server capabilities.
3. Local owner, OIDC, session revocation, and recovery work without lockout or secret leakage.
4. OIDC validation and metadata/JWKS fetching pass adversarial protocol and SSRF-oriented tests.
5. Existing standalone password login and management virtual keys remain compatible by default.
6. Durable identity, audit, trace, and usage data pass backend parity and migration rollback tests.
7. Redis coordination covers every decision that cannot safely remain process-local.
8. The forced failure/load matrix meets the stated correctness, recovery, and performance targets.
9. Multi-worker/multi-replica configuration remains impossible before those gates and explicit
   human activation approval.
10. Full repository, dependency, container, browser, documentation, and runbook gates pass.

## Authoritative Sources

- OpenID Connect Core 1.0 incorporating errata set 2:
  https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Security Best Current Practice, RFC 9700:
  https://www.rfc-editor.org/rfc/rfc9700.html
- OAuth 2.0 Authorization Server Metadata, RFC 8414:
  https://www.rfc-editor.org/rfc/rfc8414.html
- OAuth 2.0 Token Revocation, RFC 7009:
  https://www.rfc-editor.org/rfc/rfc7009.html
- OWASP Session Management Cheat Sheet:
  https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

## Open Questions

No implementation question is silently defaulted. Human acceptance is required for the permission
bundles, the always-available local recovery posture, the new cryptographic dependency, the
99.9%/60-second/20%-latency HA targets, and the decision to keep SCIM and multi-tenancy out of Wave
4. Any requested change updates this spec and the applicable ADR before code begins.
