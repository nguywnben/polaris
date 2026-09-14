# Virtual-Key Management API

Virtual keys provide independently revocable, hashed-at-rest credentials for inference clients and
explicitly authorized management automation. The plaintext credential is returned only when a key
is created or rotated. List, update, revoke, usage, and delete responses never expose it, and the
plaintext is never persisted.

## Authentication and scope model

Inference routes accept a virtual key through the same SDK-compatible credential locations as the
root integration key. Management routes accept either the browser panel session, the legacy signed
Bearer session, or a virtual key in the `Authorization: Bearer <virtual-key>` header. Virtual keys
are not accepted from management query parameters or cookies.

Supported scopes are closed and versioned by the server:

| Scope | Permission |
| --- | --- |
| `inference:openai` | OpenAI-compatible inference and model routes |
| `inference:anthropic` | Anthropic-compatible inference routes |
| `inference:gemini` | Gemini-compatible inference routes |
| `management:read` | Safe management methods: `GET`, `HEAD`, and `OPTIONS` |
| `management:write` | Management mutation methods; requires `management:read` |
| `management:permission:<permission>` | One additive allowlisted management permission |

New keys default to the three inference scopes and no management access. This is least privilege
for the existing inference-key purpose while preserving the create API's prior behavior. Callers
must explicitly request management scopes. An unknown, empty, malformed, or internally inconsistent
scope set is rejected; authorization never treats an unknown scope as a wildcard.

Management authorization is route-based rather than inferred from the raw URL or client UI state.
The broad read/write scopes retain their pre-Wave-4 behavior only for the existing route manifest;
they do not automatically receive later identity, owner-assignment, recovery, or HA permissions.
Granular scopes use values from the closed server permission catalog. Root-key disclosure uses
`management:permission:root_key.read`, separately from `root_key.rotate`; broad legacy read keys
retain the former only for compatibility with the existing root-key GET route.

Successful inference and management authentication updates `last_used_at` at most once per minute.
Management mutations performed by a virtual key are attributed to its stable key ID before the
audit service converts that identifier to a non-reversible fingerprint.

## Record contract and migration

Stored records use `schema_version: 2`. Existing unversioned keys migrate to version 2 with all
three inference scopes, preserving their previous inference access and adding no management access.
The migration writes only when every stored record is valid; a malformed record or unknown future
schema version fails closed and prevents a partial rewrite that could discard data.

Public records contain:

- `schema_version`, stable `id`, `name`, and masked `key_preview`;
- `enabled`, derived `status` (`active`, `disabled`, `expired`, or terminal `revoked`),
  `created_at`, `expires_at`, `last_used_at`, and `revoked_at`;
- monotonic `revision` for optimistic lifecycle concurrency;
- daily/monthly USD budgets and RPM/TPM limits;
- bounded `allowed_models` patterns and ordered `scopes`;
- `unknown_pricing_policy` and optional `fallback_price_usd_per_million`.

Model patterns use a bounded safe glob subset: letters, digits, `.`, `_`, `:`, `/`, `+`, `*`, `?`,
and `-`. Each pattern is at most 128 characters, at most 64 patterns are accepted, and bracket
classes or other regex-like syntax are rejected. Matching is case-insensitive.

## Unknown-pricing policy

Every key declares one of these policies:

| Policy | Contract |
| --- | --- |
| `deny` | With a hard budget, fail closed when any eligible model has no enforceable price; default for new and migrated keys |
| `warn` | With a hard budget, emit bounded warning telemetry and fail closed when any eligible model is unpriced |
| `fallback` | Reserve unknown models at the positive configured price per one million estimated tokens |

Fallback prices are valid only with `fallback`, must be positive, and cannot exceed 100,000 USD per
one million tokens. A key without a daily or monthly hard budget does not invent a monetary cost
for unknown models. The durable ledger stores the fallback cost used by a budgeted request so a
restart cannot erase that spend.

The resolver checks the hot-reloaded operator override first, then the last valid synchronized
LiteLLM catalog entry for the selected provider, and finally the bundled reviewed snapshot.
Synchronization runs at startup and periodically without blocking inference; an invalid or failed
download leaves the prior snapshot active. The `pricing` object in `GET /api/usage/aggregated`
exposes the sync state, bounded error code, source, model count, fetch time, bundled review date,
and override-file freshness without returning local paths. The bundled snapshot was reviewed on
2026-08-21. Provider billing remains authoritative, so use `model_pricing.json` whenever a contract
or private endpoint differs from public list pricing.

## Reservation and settlement semantics

The supported single-worker runtime reserves constrained capacity atomically after authentication
and before provider selection. One reservation covers every credential retry and model fallback in
the request; retries never consume another RPM slot. For a virtual model, budget estimation uses the
highest calculated cost across its eligible concrete candidates. TPM reserves estimated prompt
tokens plus the requested maximum output; when no output maximum is supplied, the bounded default
is 4,096 tokens. Local count-token operations reserve RPM only.

Requests with a daily or monthly hard budget first write an active reservation to the usage ledger
owned by the selected storage backend. The reserve transaction serializes decisions per virtual key
and evaluates committed spend plus every active estimate in integer nano-USD. A ledger outage or an
unknown transaction result fails authentication with HTTP 503; no cached snapshot can admit a
hard-budget request.

Successful provider calls atomically replace the durable estimate with normalized actual tokens
and policy cost. This prevents a crash window between recording usage and settling its reservation.
Provider errors, response errors, disconnects, cancelled streams, and later RPM/TPM rejection
release the durable estimate. Commit and release are idempotent, and terminal reservations cannot
become active again. Active reservations expire after 15 minutes. Actual usage above the estimate
is committed and emits overspend telemetry so later requests observe the exceeded limit.

If the provider succeeded but ledger settlement is unavailable or uncertain, cleanup retains the
durable reservation instead of releasing it. Once expired, its estimate is conservatively included
in hard-budget enforcement for the rest of the applicable rolling window. Actual usage reports do
not present that estimate as measured spend. This fail-closed posture can temporarily reduce
available budget during an outage, but prevents a successful request from becoming unaccounted
zero spend after restart. Local pending-settlement tracking expires with the reservation and is
hard-capped; capacity exhaustion rejects new hard-budget requests with HTTP 503 rather than growing
process memory without bound.

RPM and TPM still use the in-process state-store boundary and completed rate usage remains in its
rolling 60-second window. W4.14 therefore does not relax the documented `WORKERS=1` and
single-replica restriction. Prometheus exposes only bounded event labels in
`polaris_virtual_key_quota_events_total` and `polaris_usage_ledger_operations_total`; key IDs, request
contents, amounts, and attribution never become labels.

## Management routes

| Method and route | Required virtual-key scope | Behavior |
| --- | --- | --- |
| `GET /api/virtual-keys` | `management:read` | List public records |
| `POST /api/virtual-keys` | `management:write` | Create and reveal plaintext once |
| `PATCH /api/virtual-keys/{key_id}` | `management:write` | Update supplied fields |
| `DELETE /api/virtual-keys/{key_id}` | `management:write` | Delete the record |
| `GET /api/virtual-keys/{key_id}/usage` | `management:read` | Read key-attributed usage |
| `POST /api/virtual-keys/{key_id}/rotate` | `management:write` | Atomically replace and reveal plaintext once |
| `POST /api/virtual-keys/{key_id}/revoke` | `management:write` | Permanently revoke while retaining stable identity |

Create accepts all public policy fields except server-owned identity, status, timestamps, preview,
revision, and usage metadata. Update is partial and remains backward-compatible when
`expected_revision` is omitted. Rotate and revoke require the current positive
`expected_revision`; update may supply it. A stale mutation returns HTTP 409 without changing the
record. Domain validation failures return HTTP 400 and a missing key returns HTTP 404. Rotation
preserves the stable key ID, invalidates the previous secret atomically, and returns the new secret
only in that successful response. Revocation is terminal: a revoked key cannot be re-enabled or
rotated. Create, update, rotate, revoke, and legacy delete operations use the bounded management
audit vocabulary without recording secret material.

## Access console contract

The Access page preserves the existing root integration key and SDK examples while adding a
separate virtual-key governance workspace. Operators can search and filter public records, create
or edit policy, inspect usage, rotate, and terminally revoke. The form exposes scope, model, rate,
budget, expiry, and unknown-pricing controls; selecting management write also selects management
read, and fallback price is editable only when fallback pricing is selected.

Create and rotate display plaintext in a modal exactly once. Closing or copying clears the secret
from JavaScript state and the DOM, and the feature does not write it to browser persistence. A
concurrent mutation returns the revision conflict without silently overwriting newer policy; the
console reloads the current record before another attempt. All statuses and lifecycle actions are
localized across the 15 supported console locales.
