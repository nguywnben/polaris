# ADR-007: Use Explicit Management Principals, RBAC, and OIDC

## Status

Accepted on 2026-08-26. Delivery remains incremental: W4.2 establishes the pure principal and
permission contract, W4.3 enforces it on existing management routes, and W4.4 adds the versioned
repository plus additive SQLite migration. W4.5 completes PostgreSQL/MongoDB repository parity and
storage-adapter selection. W4.6 activates opaque revocable sessions and local-owner recovery for
the standalone topology. W4.7 completes the disabled-by-default OIDC policy, safe discovery
transport, strict metadata/JWKS validation, and bounded rotation cache. It does not activate login;
ID Token verification, authorization transactions, identity resolution, and management/UI gates
remain in W4.8–W4.12. Shared session coordination remains gated by W4.16.

## Context

The current control panel has one local password and treats every valid browser session as the
same owner. Its signed JWT expires but has no server-side record, so individual revocation, role
changes, session inventory, and logout across replicas are impossible. Management virtual keys
support read/write scopes for automation, but those scopes are not a human RBAC model. Audit events
therefore distinguish automation keys while browser actions remain attributed to a generic owner.

Enterprise identity must add `viewer`, `operator`, `security_admin`, and `owner` without changing
the inference API, breaking existing standalone login, trusting browser visibility, or creating an
IdP-dependent lockout. OIDC role/group claims are provider-specific and email is not a stable user
identifier. The design must also prepare sessions for the coordinated runtime boundary in ADR-006.

## Decision

Introduce one internal `ManagementPrincipal` resolved before protected route execution. Its type is
`local_owner`, `oidc_user`, `virtual_key`, or `system`; request-provided values can never select the
type. OIDC users use the exact `(issuer, subject)` pair as their identity. Virtual keys keep their
existing stable IDs and read/write behavior for existing routes.

Create a declarative permission registry and require every management HTTP route and WebSocket to
name one permission. A generated coverage test fails when a protected route is missing. Role names
map to explicit immutable permission sets:

- `viewer`: `dashboard.read`, `configuration.read`, `credentials.read`, `providers.read`,
  `quality.read`, `access.read`, `audit.read`, `traces.read`, `logs.read`, and `identity.read`.
- `operator`: all viewer permissions plus `credentials.operate`, `routing.manage`,
  `quality.manage`, and `logs.manage`.
- `security_admin`: all viewer permissions plus `credentials.operate`, `credentials.manage`,
  `credentials.export`, `providers.manage`, `access.manage`, `audit.manage`, `audit.export`,
  `traces.manage`, `traces.export`, `identity.manage`, `sessions.manage`, `oidc.manage`, and
  `backup.export`.
- `owner`: the union of operator and security-admin permissions plus `configuration.manage`,
  `root_key.read`, `root_key.rotate`, `backup.restore`, `owners.manage`, `recovery.manage`, and
  `ha.activate`.

Permission sets are not inferred from lexical role order. New owner-only and identity permissions
are not granted to existing management virtual keys. The UI consumes the server-returned principal
and permissions to remove inapplicable controls, but the API remains the only enforcement boundary.

Existing broad `management:write` keys remain compatible on existing routes during Wave 4, which
means they can still perform some actions assigned only to the human owner role. Treat that as an
explicit migration debt: inventory and warn on broad keys, offer granular permission scopes for new
and rotated keys, and require a later deprecation decision before narrowing an existing key. Broad
keys never receive new identity, owner-assignment, recovery, or HA-activation permissions.

Route inventory discovered that the existing root-key GET route cannot share `access.read` without
disclosing the integration secret to viewers. `root_key.read` is therefore a distinct owner
permission. Legacy `management:read` keeps it solely to preserve the route behavior that existed
before Wave 4; root-key rotation remains a separate permission.

Use OIDC Authorization Code flow as a confidential relying party with PKCE `S256`, transaction-
bound one-time `state` and `nonce`, exact HTTPS issuer and redirect validation, and bounded discovery,
JWKS, token, and optional UserInfo requests. Validate allowlisted asymmetric signature algorithms,
signature, exact issuer, audience/authorized party, expiry, clock skew, and nonce before using any
claim. On an unknown key ID, refresh JWKS once and then fail closed. If UserInfo is used, require its
`sub` to exactly match the ID Token.

By default, every discovered endpoint origin must equal the configured issuer origin. Additional
origins and internal IdPs require environment allowlists. Discovery/client requests reject redirects,
credentials/query/fragment in configured origins, disallowed IP ranges, mixed DNS answers, oversized
responses, and timeouts; the connection uses the address that passed validation. The exact callback
is `no-store` and exchanges a query-delivered code once before a 303 redirect to a clean same-origin
path.

Role mapping is explicit and revisioned. A direct `(issuer, subject)` binding wins; otherwise an
allowlisted claim name/value mapping may select a non-owner role. Missing, malformed, oversized, or
unmapped claims deny login. OIDC claims can never create or assign an owner. Client secrets are
environment/file-secret only in the initial Wave 4 implementation; APIs expose only whether one is
configured. Provider tokens are not persisted after the internal session is issued.

Issue new browser sessions as opaque random values with at least 256 bits of entropy. Store only an
HMAC digest and bounded session metadata behind a semantic session-store interface. Enforce idle
and absolute expiry, rotate on authentication and privilege changes, and revoke on logout, identity
disable, role downgrade, password rotation, or identity-policy revision. Session cookies remain
HTTP-only, same-site, path-scoped, and secure under authoritative HTTPS.

Keep the local password owner as the default break-glass route, independently rate-limited and
audited. It may be restricted to loopback or trusted administrative ingress. Disabling it requires
an active owner binding and a separately tested recovery method; normal OIDC enablement does not
silently disable it.

Extend audit actor vocabulary for the typed principal while retaining HMAC fingerprinting. Add
bounded events for authentication, denial, identity/role changes, session revocation, OIDC policy,
and recovery. Audit records never contain names, emails, group values, session IDs, OIDC tokens, or
provider exception text.

Normal enterprise issuers require asymmetric JWT verification. The project will replace the
runtime requirement `PyJWT` with `PyJWT[crypto]` only after this ADR is accepted, then audit and pin
the resulting dependency through the existing supported range.

## API and Compatibility Boundary

Add resource-oriented APIs under `/api/identity` for current session, OIDC configuration,
identities, role bindings, sessions, and recovery checks. Use typed additive schemas, bounded
pagination, optimistic revisions, common errors, permission checks, and audit coverage.

Standalone deployments remain local-owner by default. Existing password configuration, inference
keys, management virtual-key read/write scopes, and provider OAuth flows keep their semantics.
Enabling the identity policy triggers a one-time browser reauthentication; legacy signed browser
sessions are accepted only for a bounded migration window in local-owner mode and are never mapped
to an OIDC user.

## Migration and Rollback

1. Add the principal, permission, identity repository, and session-store contracts while existing
   routes still resolve the local owner or existing virtual key.
2. Add complete allow/deny and audit coverage before enabling any non-owner role.
3. Introduce opaque sessions for new logins; bound legacy-session acceptance to local-owner mode and
   the shorter of its original expiry or the documented migration window.
4. Add OIDC configuration disabled by default, validate it through preview/connectivity checks, and
   require a successful test login before activation.
5. Rollback disables new OIDC login, revokes OIDC sessions, returns to one local owner, and leaves
   identity/audit records intact. It never converts an OIDC identity into a local owner.

## Consequences

- Authorization becomes explicit, testable, attributable, and independent of UI state.
- Server-side sessions add storage and cleanup work but enable immediate revocation and HA.
- OIDC outage does not end already-valid local sessions, while new OIDC login fails closed.
- Keeping local recovery reduces lockout risk but requires strong operational protection.
- The PyJWT cryptographic backend is a new audited runtime dependency.
- Provider-specific claim mapping improves compatibility but must be configured deliberately.
- Identity, role-binding, and OIDC-policy resources now have strict versioned records and
  independent optimistic revisions. SQLite preserves existing tables and keeps the local owner
  enabled and immutable while later recovery/session work remains gated.
- The standalone session implementation retains only HMAC-indexed records in process memory, binds
  them to the durable local-owner authorization epoch, and fails closed when the identity or
  session master key is unavailable. Restart reauthentication is an explicit interim consequence
  until W4.16 introduces coordinated session storage.

## Rejected Alternatives

- Keeping every authenticated user as owner was rejected because it provides no least privilege.
- Treating email as identity was rejected because only `(iss, sub)` is guaranteed stable by OIDC.
- Trusting a generic `groups` or `roles` claim was rejected because OIDC Core standardizes neither
  role semantics nor an authorization policy for those values.
- Self-contained browser JWT sessions were rejected because immediate revocation and role changes
  require server-side state.
- Disabling local recovery as soon as OIDC succeeds once was rejected because IdP/configuration
  outages could irreversibly lock out the deployment.
- Adding SCIM in the same wave was rejected to keep authentication/authorization and provisioning
  independently reversible.

## References

- OpenID Connect Core requires exact issuer/audience validation and identifies `(iss, sub)` as the
  only guaranteed stable End-User identifier:
  https://openid.net/specs/openid-connect-core-1_0.html
- OAuth Security BCP requires CSRF defense, exact redirect matching, and recommends PKCE for
  confidential clients:
  https://www.rfc-editor.org/rfc/rfc9700.html
- Authorization-server metadata contract:
  https://www.rfc-editor.org/rfc/rfc8414.html
- Session expiry, rotation, logout, and reauthentication guidance:
  https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
