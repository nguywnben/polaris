# OIDC Foundation and Security Boundary

The optional OIDC boundary includes validated configuration, a hardened discovery transport, a
bounded JWKS cache, strict ID Token verification, one-time Authorization Code + PKCE/state/nonce,
deny-by-default identity resolution, and revision-bound sessions. The browser flow is exposed only
when `OIDC_ENABLED=true` and the complete trust configuration is valid. Identity/session APIs and
the localized console are active, but they do not enable OIDC on their own.

The local-owner login and recovery path remain available and independent of the identity provider.
`WORKERS=1` and one application replica remain the only supported topology.

## Configuration Contract

OIDC is disabled when `OIDC_ENABLED` is absent or false. A disabled snapshot carries no active
issuer, client, endpoint, algorithm, mapping, or secret configuration. An enabled snapshot fails
closed unless every required value is valid.

| Variable | Default | Contract |
| --- | --- | --- |
| `OIDC_ENABLED` | `false` | Boolean browser-login gate; disabled mode performs no provider discovery. |
| `OIDC_ISSUER` | required when enabled | Exact HTTPS issuer URL; no credentials, query, fragment, wildcard, or trailing-dot host. |
| `OIDC_CLIENT_ID` | required when enabled | Non-empty client identifier, at most 256 characters. |
| `OIDC_CLIENT_SECRET` | none | Client secret supplied directly; configure exactly one secret source. |
| `OIDC_CLIENT_SECRET_FILE` | none | Absolute regular-file path; symlinks, replacement races, invalid UTF-8, and files over 4 KiB are rejected. |
| `OIDC_REDIRECT_URI` | required when enabled | Exact HTTPS URL whose path is `/api/identity/oidc/callback`, with no query or fragment. |
| `OIDC_SCOPES` | `openid profile email` | Space-separated, unique scopes; `openid` is mandatory; maximum 16. |
| `OIDC_ID_TOKEN_SIGNING_ALGORITHMS` | `RS256` | Comma-separated subset of `RS256`, `PS256`, and `ES256`; symmetric and `none` algorithms are impossible. |
| `OIDC_SUBJECT_CLAIM` | `sub` | Fixed to `sub`; it cannot be remapped. |
| `OIDC_USERNAME_CLAIM` | `preferred_username` | Bounded claim name for future profile display. |
| `OIDC_DISPLAY_NAME_CLAIM` | `name` | Bounded claim name for future profile display. |
| `OIDC_EMAIL_CLAIM` | `email` | Bounded profile claim only; email is never an identity key. |
| `OIDC_GROUPS_CLAIM` | `groups` | Bounded claim name used only by explicit role mapping. |
| `OIDC_ROLE_MAPPINGS` | `{}` | JSON object with at most 64 exact group-to-role entries. Values are `viewer`, `operator`, or `security_admin`; `owner` and default roles are forbidden. |
| `OIDC_ALLOWED_ENDPOINT_ORIGINS` | issuer origin only | Comma-separated additional exact HTTPS origins, maximum 16 including the issuer origin. |
| `OIDC_ALLOWED_PRIVATE_HOSTS` | none | Comma-separated exact internal hostnames/IPs, maximum 32; no wildcards or CIDRs. |
| `OIDC_CONNECT_TIMEOUT_SECONDS` | `5` | Integer from 1 through 30. |
| `OIDC_READ_TIMEOUT_SECONDS` | `10` | Integer from 1 through 60. |
| `OIDC_MAX_RESPONSE_BYTES` | `262144` | Discovery/JWKS response cap from 4 KiB through 1 MiB. |
| `OIDC_JWKS_TTL_SECONDS` | `300` | Successful JWKS snapshot lifetime from 30 through 3,600 seconds. |
| `OIDC_CLOCK_SKEW_SECONDS` | `60` | Symmetric clock tolerance from 0 through 300 seconds for `exp`, `nbf`, and future `iat`. |
| `OIDC_MAX_ID_TOKEN_AGE_SECONDS` | `300` | Maximum accepted age from 60 through 3,600 seconds, before the configured skew. |
| `OIDC_START_WINDOW_SECONDS` | `300` | Per-client browser-start accounting window, 30–3,600 seconds. |
| `OIDC_START_MAX_ATTEMPTS` | `20` | Starts allowed per client/window, 3–100. |
| `OIDC_START_MAX_TRACKED_CLIENTS` | `10000` | Process-local throttle memory bound, 100–100,000 clients. |

Secrets are excluded from the public immutable policy and its string representation. Configuration
uses the durable OIDC policy revision and authorization epoch already provided by the identity
repository. W4.11 owns mutation APIs, optimistic concurrency, readiness projection, and revision
advancement. The API reports only a secret-configured marker and cannot read or write the client
secret. Environment changes require a controlled restart. See
[Identity and Session Management API](identity-management-api.md).

## Discovery and Network Safety

The client derives `/.well-known/openid-configuration` from the configured issuer and requires the
returned `issuer` to match exactly. Metadata must advertise Authorization Code flow, PKCE `S256`, a
supported subject type, an allowed asymmetric ID Token algorithm, compatible client authentication,
and all configured scopes and claims. Authorization, token, JWKS, and optional UserInfo endpoints
are revalidated against the endpoint policy. Issuer, redirect, and discovered endpoint URLs are
ASCII-only to prevent visually confusable trust-boundary values.

Outbound OIDC requests:

- use HTTPS with the original hostname as TLS SNI and certificate-verification target;
- resolve every address before connecting and connect only to an address from that approved set;
- reject private, loopback, link-local, reserved, unspecified, multicast, or mixed public/private
  DNS answers unless the exact host is explicitly allowlisted;
- ignore environment proxies and reject redirects, response compression, duplicate JSON keys,
  invalid UTF-8, non-finite JSON numbers, oversized headers/bodies, and unsupported media types;
- return content-free internal errors so provider responses and network details cannot reach APIs or
  audit records.

Additional endpoint origins and private hosts expand the IdP trust boundary. Operators should keep
both lists empty unless the provider architecture requires them and should use exact values rather
than broad infrastructure domains.

## JWKS Validation and Rotation

JWKS documents contain at most 64 unique-key-ID public signing keys. The parser accepts only RSA
and P-256 EC public keys compatible with the configured/discovered algorithm intersection. It
rejects symmetric keys, private key fields, malformed or non-canonical base64url values, weak or
oversized RSA moduli, invalid exponents, invalid EC points, duplicate key IDs, and a JWKS URI that
does not exactly match validated discovery metadata.

Successful snapshots replace the cache atomically and expire after the configured TTL. Cold loads,
expired refreshes, and unknown-key refreshes are single-flight. An unknown key ID causes at most one
refresh per lookup. Invalid refresh data never replaces the last valid snapshot, and a bounded
failure cooldown prevents concurrent provider failures from creating a refresh storm.

## ID Token Verification

The W4.8 verifier accepts only compact signed JWTs using the configured and discovered intersection
of `RS256`, `PS256`, and `ES256`. It rejects symmetric or unsigned algorithms, embedded or remote
header-selected keys, critical/unknown JOSE extensions, duplicate JSON fields, invalid UTF-8 or
base64url, and oversized headers, payloads, signatures, claims, audiences, or profile data before
using them.

Signature verification uses only a key from the exact policy/discovery-bound JWKS cache. An unknown
key ID may trigger one bounded rotation attempt; repeated unknown IDs share a short cooldown, while
a failed rotation never replaces the last valid snapshot or blocks a still-fresh known key.

After signature verification, the verifier requires exact `iss`, a bounded ASCII `sub`, an `aud`
containing the configured client ID, `azp` for multiple audiences, and exact client ID whenever
`azp` is present. It also requires transaction-bound `nonce`, integer `exp` and `iat`, optional
integer `nbf`, bounded clock skew, bounded token age, and a consistent issue/not-before/expiry
timeline. Optional UserInfo is usable only after its bounded `sub` exactly matches the ID Token.

Only issuer, subject, audiences, authorized party, verified timestamps/nonce, configured bounded
profile fields, policy revision, and JWKS generation leave the verifier. Unknown provider claims,
raw tokens, key material, and provider exception text have no output field. Every rejection uses
the same content-free error and suppresses the internal exception chain; asynchronous cancellation
continues to propagate.

## Authorization Transaction and Code Exchange

W4.9 creates an in-process, capacity-bounded authorization transaction service. Each transaction
uses independent high-entropy `state`, browser binding, PKCE verifier, and nonce values. The store
retains only HMAC-indexed state/browser values and derives the verifier and nonce from keyed input;
it never stores plaintext provider tokens. Each record binds the exact issuer, client, redirect,
authorization endpoint, token endpoint, authentication method, and durable policy revision. A
monotonic TTL, atomic consume operation, bounded capacity, and explicit cancellation prevent replay
and unbounded memory growth.

Authorization requests always use `response_type=code`, PKCE `S256`, and transaction-bound state and
nonce. Callback parsing starts from bounded raw ASCII query bytes, rejects malformed percent
encoding, duplicates, unknown fields, query-carried tokens, mixed issuers, and code/error ambiguity,
then consumes the matching transaction exactly once. Invalid query structure is rejected before
consumption so unrelated malformed traffic cannot burn a valid state; a matching provider error,
mix-up attempt, exchange outage, verification failure, or cancellation consumes it so it cannot be
replayed.

The token client posts a bounded form directly to the pinned discovered token endpoint, using only
the single discovered `client_secret_basic` or `client_secret_post` method. Credentials never enter
the URL. The response requires a Bearer access token and ID Token with strict type/size bounds;
access and refresh tokens are discarded, and only the verified allowlisted ID Token projection
leaves the protocol core. Provider-controlled errors remain behind one content-free boundary.

## Identity Resolution, Browser Routes, and Sessions

W4.10 resolves only the exact, case-sensitive `(issuer, subject)` pair. A durable direct binding
wins over provider claims. Otherwise the bounded configured group claim must match one or more
allowlist entries that all resolve to the same non-owner role. Missing, malformed, oversized,
unmapped, or conflicting claims deny login. Claim-derived bindings are re-evaluated on every login,
so a mapping downgrade updates the durable binding before session issuance. Email, username, and
display name never participate in identity lookup or authorization.

`GET /api/identity/oidc/start` allocates a browser-bound transaction and returns a 303 to the
validated provider authorization endpoint. Its separate `oidc_login` cookie is HttpOnly,
SameSite=Lax, callback-path scoped, short lived, and Secure on authoritative HTTPS. Start attempts
and pending transactions have independent process-local capacity bounds. Lazy discovery also has a
bounded admission queue; one provider failure is shared through a short negative-cache backoff so
an IdP outage cannot create serialized retry storms or consume unbounded request waiters.

`GET /api/identity/oidc/callback` consumes bounded raw query bytes, the exact browser binding, the
authorization code, and the transaction exactly once. Success issues an opaque `panel_session` and
returns a 303 to `/`; failure returns a generic 303 to `/login`. Both paths remove the binding
cookie, set no-store/no-referrer headers, and remove every provider-controlled parameter from the
browser URL. Provider access/refresh/ID tokens never enter cookies, storage, logs, or redirects.

An OIDC session stores separate identity and OIDC-policy authorization epochs and the resolved
typed principal. Every request reloads the exact durable identity and policy snapshot; identity
disablement, role/source change, or policy revision makes the session stale and revokes it. The
authorization layer requires the session verifier's typed principal and never synthesizes
local-owner authority. If a claim-derived identity can no longer resolve to exactly one allowed
role, the denied login advances its authorization epoch, making every older session stale.

## Activation and Rollback

Keep `OIDC_ENABLED=false` or unset until the IdP registration, exact callback, group mapping, and
local recovery path have been reviewed. Rollback sets `OIDC_ENABLED=false` and restarts the single
process; local-owner login/recovery remains available and durable identity records are retained.
Active in-process sessions are cleared by the restart.

Enterprise activation is not complete until W4-B protocol, abuse, recovery, API, audit, i18n,
accessibility, and browser gates pass. Provider discovery is lazy: an IdP outage blocks only new
OIDC login and never application startup or the local-owner recovery path.
