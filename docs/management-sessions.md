# Management Sessions and Local-Owner Recovery

## Scope and Status

New browser authentication uses revocable opaque sessions, an independently throttled local-owner
recovery path, and deny-by-default OIDC sessions. This contract applies to the supported
single-worker, single-replica standalone topology. Shared session coordination and HA are not
activated in the production profile; process restart therefore invalidates active sessions.

The bounded identity/session inventory, revocation API, and localized console are active. The API
exposes no bearer token or internal digest, and the console keeps local-owner recovery visible.

## Session Contract

- A successful setup, login, or recovery request creates a fresh `ogs_` opaque token with 32 random
  bytes (256 bits) of entropy.
- Only an HMAC-SHA-256 index and bounded metadata are retained by the session store. Plaintext
  bearer tokens are never stored in configuration, identity records, audit records, logs, metrics,
  OAuth state, or provider authorization URLs.
- The metadata binds a session to its real typed principal, authentication method, issue and
  last-seen times, idle and absolute expiry, and the durable identity authorization epoch. OIDC
  sessions additionally bind the independent OIDC-policy authorization epoch.
- Resolution is atomic. Expired, revoked, unknown, or stale-epoch sessions fail closed. A successful
  resolution advances last-seen time without extending the absolute lifetime.
- Logout revokes the server-side record before clearing the cookie. Owner-password rotation revokes
  all current local-owner sessions before the new password is persisted and then issues one
  replacement session.
- Provider OAuth flows receive only an ephemeral HMAC reference to the authenticated request. The
  session token itself never enters the OAuth transaction or externally visible `state` value.
- OIDC session resolution reloads the exact issuer/subject identity and current policy. Disabled
  identities, role/source changes, and policy revisions revoke stale sessions before permission
  evaluation. A failed claim-role re-evaluation advances the identity epoch, and request
  authorization requires the verifier's typed principal; OIDC principals are never promoted to
  local owner or replaced with an implicit owner fallback.
- W4.11 exposes only independently domain-separated `ssr_` revocation references. These references
  cannot authenticate requests, are never stored in audit events, and support bounded pagination
  and single-session revocation. Durable identity/policy epochs remain authoritative if eager
  removal fails. See [Identity and Session Management API](identity-management-api.md).

The browser cookie remains named `panel_session` and uses `HttpOnly`, `SameSite=Lax`, and `Path=/`.
It is `Secure` when the request is authoritatively HTTPS or when a trusted proxy reports HTTPS.
Existing same-origin and CSRF checks continue to protect authenticated mutations.

## Lifetimes and Compatibility

| Environment setting | Default | Enforced range | Purpose |
| --- | ---: | ---: | --- |
| `PANEL_SESSION_TTL_SECONDS` | 86400 | 301–2592000 | Absolute session lifetime |
| `PANEL_SESSION_IDLE_TTL_SECONDS` | 1800 | 300 to absolute lifetime minus 1 | Maximum idle interval |
| `PANEL_SESSION_MAX_ACTIVE` | 10000 | 1–100000 | Process-local active-session capacity |
| `PANEL_LEGACY_SESSION_MIGRATION_SECONDS` | 3600 | 300–86400 | Temporary acceptance window for an existing local-owner JWT |

Legacy JWTs are never issued after W4.6. During upgrade, a legacy token is accepted only when its
signature, audience, subject, issued-at, and expiry claims are valid and the migration window has
not elapsed. The effective lifetime is therefore the shorter of the JWT's original expiry and the
configured migration window. Legacy tokens can resolve only to the local owner; they cannot create
an OIDC identity.

The initial W4.6 store is process-local. A controlled restart revokes all opaque sessions and users
must sign in again. The HMAC master key is durably generated and validated at startup so corrupted
or unavailable security state fails closed, but persisting that key does not persist active bearer
sessions. Operators must not increase `WORKERS` or run multiple replicas until coordinated session
semantics and the HA gates are complete.

Before issuing a session, the store removes expired records. At the configured capacity it revokes
the least recently used session before admitting a new one, keeping memory bounded without
retaining bearer values. Operators can lower the capacity for constrained deployments; reaching it
can sign out the least recently active browser.

## Local-Owner Recovery

`POST /api/auth/recovery` is the break-glass local-owner authentication path. It accepts only the
configured local password, returns generic failures, issues a fresh opaque session after success,
and emits the dedicated `auth.recovery` audit action. It does not depend on OIDC availability.

Recovery has a separate bounded, process-local throttle so normal login attempts cannot consume or
reset its budget:

| Environment setting | Default | Enforced range | Purpose |
| --- | ---: | ---: | --- |
| `PANEL_RECOVERY_WINDOW_SECONDS` | 900 | 60–7200 | Failure-accounting window |
| `PANEL_RECOVERY_MAX_ATTEMPTS` | 5 | 3–20 | Failures allowed per client and window |
| `PANEL_RECOVERY_MAX_TRACKED_CLIENTS` | 10000 | 100–100000 | Memory bound for tracked clients |
| `PANEL_RECOVERY_LOCAL_ONLY` | disabled | boolean | Require both a loopback URL host and direct loopback peer |

When `PANEL_RECOVERY_LOCAL_ONLY=true`, forwarded headers are deliberately ignored for this check.
Use a direct loopback connection; a reverse proxy cannot assert that it is local. The default keeps
recovery reachable for existing remote standalone deployments, so production operators should
restrict network ingress or enable the loopback-only control according to their topology.

## Operations and Evidence

Prometheus output includes only the fixed-cardinality counter
`polaris_management_session_operations_total{action,outcome}`. Actions are session lifecycle
operations such as issue, resolve, revoke, and principal revocation; outcomes are bounded states
such as succeeded, not found, expired, stale, or failed. Principal IDs, session IDs, tokens, client
addresses, and exception messages are never metric labels.

Expected operational behavior:

1. After upgrade, existing legacy browser sessions work only inside the bounded migration window;
   new authentication receives an opaque cookie.
2. After restart, opaque sessions return HTTP 401 and users sign in again. Health/readiness can
   still be green because this is the documented standalone security posture.
3. A missing, disabled, or corrupt durable local-owner identity prevents session issuance and
   validation. Startup/session service errors are surfaced without exposing stored values.
4. If session initialization is unavailable, authentication fails closed instead of falling back to
   a self-contained token.
5. Rolling back to a pre-W4.6 build cannot read opaque cookies, so users sign in again. The additive
   identity data and internal session/transaction master keys may remain; no destructive rollback
   is required.

## Verification Boundary

The maintained regression suite covers entropy, plaintext exclusion, capacity/LRU behavior,
concurrent rotation,
logout revocation, idle/absolute expiry, authorization-epoch invalidation, password-change
revocation, bounded legacy migration, cookie/origin behavior, OAuth-state isolation, recovery
throttling and loopback restriction, corrupted master-key startup, generic errors, audit coverage,
fixed-cardinality metrics, exact OIDC principals, typed-principal fail-closed behavior, independent
identity/policy revision invalidation after accepted or rejected claim re-evaluation, and
role-downgrade denial. W4-A closed the local session foundation; W4-B remains responsible for the
complete OIDC/API/UI activation evidence.
