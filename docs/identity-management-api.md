# Identity and Session Management API

The closed, typed control-plane API under `/api/identity` supports the localized Identity console
and human administrators. Legacy broad management API keys receive none of the identity
permissions, and enabling these routes does not enable OIDC or weaken local-owner recovery.

## Resource and permission matrix

| Method and resource | Permission | Purpose |
| --- | --- | --- |
| `GET /api/identity/session` | `identity.read` | Current typed principal, effective permissions, and current session status |
| `GET /api/identity/identities` | `identity.read` | Bounded durable identity and role-binding inventory |
| `POST /api/identity/identities` | `identity.manage` | Create an exact issuer/subject direct binding |
| `PATCH /api/identity/identities/{identity_id}` | `identity.manage` | Enable or disable an identity with identity revision CAS |
| `PUT /api/identity/identities/{identity_id}/role-binding` | `identity.manage` | Replace the direct role binding with binding revision CAS |
| `GET /api/identity/sessions` | `sessions.manage` | Bounded active-session inventory |
| `POST /api/identity/sessions/{reference}/revoke` | `sessions.manage` | Revoke one session through a non-secret reference |
| `GET /api/identity/oidc-policy` | `identity.read` | Safe OIDC readiness/configuration projection |
| `POST /api/identity/oidc-policy/advance` | `oidc.manage` | Advance the policy authorization epoch and invalidate OIDC sessions |
| `GET /api/identity/recovery` | `recovery.manage` | Verify local-owner, password, and effective ingress-policy readiness |

Assigning the `owner` role, changing an existing owner, or attempting to disable an owner also
requires `owners.manage`. The immutable local owner cannot be disabled or have its role changed.
Claim-mapped identities can never be assigned owner through OIDC claims.

## Pagination and concurrency

Identity and session list requests use `page_size` from 1 through 100 and return `next_cursor` plus
`has_more`. Identity cursors contain only the already-visible creation timestamp and opaque durable
identity ID. Session cursors are independently HMAC-derived revocation references. Invalid cursors
fail with a generic client error.

Identity enablement requires `expected_revision`; role updates require the independent binding
revision; OIDC policy advancement requires its policy revision. Concurrent writers therefore have
one winner and stale requests receive HTTP 409 without storage details. Identity and policy
authorization epochs remain the fail-safe even if eager in-memory session cleanup encounters an
operational failure.

## Secret and privacy boundary

No endpoint returns or exports a bearer session token, internal session digest, OIDC token, client
secret, email, display name, group claim, or arbitrary provider claim. A session `reference` is an
HMAC-derived, one-way revocation handle with its own domain separation; it cannot authenticate a
request. OIDC policy output contains only safe configuration and secret-presence markers. The
client secret remains environment/file-secret only.

Identity resources expose only authorization keys needed for exact administration: the opaque
identity ID and the exact case-sensitive OIDC issuer/subject pair. Session resources map sessions
back to the opaque durable identity ID and do not repeat issuer/subject values.

## Audit and denial evidence

Audit actors use the closed vocabulary `local_owner`, `oidc_user`, `virtual_key`, or `system`.
Verified principals are attached to request state before permission evaluation, so authenticated
denials retain the correct typed actor. Exact OIDC issuer/subject pairs are joined only as input to
the audit HMAC and never enter an event record.

Every identity, role-binding, session-revocation, and OIDC-policy mutation is classified in the
management audit matrix. Denied protected reads also produce a `management.access_denied` event
whose target is the trusted route template. Concrete identity IDs and route parameters are HMAC
fingerprinted; session references are replaced by the constant session target before audit.

## Error contract

Request validation uses HTTP 400/422, unauthenticated requests use 401, permission denials use 403,
missing identities or sessions use 404, stale revisions and owner-policy conflicts use 409, and an
unavailable identity/session dependency uses 503. Responses never include database messages,
provider exceptions, raw identifiers from failed lookups, or secret material.

Recovery status reports `direct_loopback_only` only when `PANEL_RECOVERY_LOCAL_ONLY` is effectively
enabled; otherwise it reports `network_reachable` so operators and the W4.12 UI cannot infer a
stronger break-glass network boundary than the server actually enforces.
