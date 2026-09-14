# Identity and Session Governance Console

The Advanced `/identity` destination manages the optional team-access boundary separately from
virtual API keys. It uses the closed identity API, does not enable OIDC by itself, and cannot
remove or replace local-owner recovery. OIDC remains disabled until the complete operator trust
configuration is valid.

## Operator surfaces

The page presents five bounded surfaces:

1. **Current principal** — the durable identity ID, principal type, role, role source,
   authentication context, and exact effective permissions for the current console request.
2. **OIDC readiness** — a secret-free projection of readiness, issuer, redirect URI, scopes, role
   mapping count, policy revision, authorization epoch, and client-credential presence.
3. **Recovery readiness** — local-owner enablement, password presence, and the effective ingress
   policy. `direct_loopback_only` is shown only when the server enforces that boundary.
4. **Direct identities** — cursor-paginated issuer/subject bindings with independent identity and
   role-binding revisions.
5. **Active sessions** — cursor-paginated, non-authenticating session references with current-session
   marking and bounded timestamps.

Protocol values such as `owner`, `security_admin`, `oidc_user`, `direct_binding`,
`direct_loopback_only`, and authentication-method codes remain exact. Surrounding explanatory copy
is curated for every supported locale.

## Permission-derived controls

The browser treats the permissions returned by `GET /api/identity/session` as presentation input;
the server remains the authorization boundary.

| Control | Required effective permission |
| --- | --- |
| Read principal, identities, and OIDC projection | `identity.read` |
| Create, enable, disable, or rebind a direct identity | `identity.manage` |
| Create or modify an owner binding | `owners.manage` in addition to `identity.manage` |
| Read or revoke active sessions | `sessions.manage` |
| Advance the OIDC authorization epoch | `oidc.manage` |
| Read local recovery readiness | `recovery.manage` |

Unknown permissions are displayed in the effective-permission summary but never enable a control.
Legacy broad management scopes receive none of the new identity permissions.

## Mutation safety

- Owner creation, role changes, identity enablement/disablement, session revocation, and OIDC policy
  advancement use native modal confirmation before the request is sent.
- Identity enablement, role binding, and OIDC policy advancement send the matching server revision.
  An HTTP 409 causes a bounded refetch; a pending role choice is reapplied over the fresh revision so
  the operator can review and submit again.
- Mutation controls are disabled while a request is in flight. Successful list replacement restores
  focus to the corresponding refreshed control or to a status boundary when the target was removed.
- Identity and session pagination are independently single-flight. A consumed next cursor is cleared
  before dispatch so rapid triggers cannot duplicate a cursor or desynchronize the page backstack.
- Creating an existing exact issuer/subject binding reports a collision; stale-revision guidance is
  reserved for mutations that actually send a CAS revision.
- Revoking the current session signs the browser out immediately. Advancing the OIDC authorization
  epoch also signs out a current OIDC principal because durable invalidation applies to that session.
- Incomplete eager session cleanup is surfaced as a warning; the durable authorization epoch remains
  authoritative.

## Browser trust boundary

The console revalidates and bounds external response collections before rendering them. It uses DOM
creation and `textContent`, never `innerHTML`, for identity, issuer, subject, permission, session, or
policy values. Cursor values remain memory-only and are bounded before reuse.

No bearer token, session digest, OIDC token, client secret, password, profile claim, or group claim is
represented by a DOM field or persisted to `localStorage` or `sessionStorage`. Session references are
one-way revocation handles and cannot authenticate a request. The OIDC client secret stays in its
environment/file-secret boundary.

## Operational expectations

- Lists request 25 records per page even though the API supports a maximum of 100.
- Refresh reads the current principal first, then loads only resources allowed by its effective
  permissions.
- The console is designed for 360, 768, 1024, and 1440 pixel widths and inherits the existing
  light, dark, and system theme contract.
- Native dialogs provide focus containment; localized Close/Cancel controls and Escape all use the
  same cleanup path and return focus deliberately.
- OIDC remains disabled by default, and local-owner recovery remains available under its existing
  ingress policy.

The resource and error contract is maintained in
[Identity and Session Management API](identity-management-api.md). The underlying session and OIDC
security boundaries are documented in [Management Sessions](management-sessions.md) and
[OIDC Foundation](oidc-foundation.md). The closed internal review cycles are recorded in
[W4.12 Adversarial Review Record](w4.12-adversarial-review.md).
