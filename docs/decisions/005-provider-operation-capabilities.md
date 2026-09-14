# ADR-005: Provider-Declared Credential Operation Capabilities

## Status

Accepted for the credential-fleet overhaul.

## Context

Credential operations vary by provider, authentication flow, and account type. A provider name is
not enough to determine whether a credential can be verified, refreshed, queried for quota,
exported, placed in credit mode, or moved to a preview channel. UI-only checks are unsafe because
a crafted request can invoke an operation that the server did not intend to support.

## Decision

Extend the provider registry with credential variants and an explicit operation capability set.
The initial vocabulary is `verify`, `test`, `quota`, `refresh_identity`, `toggle`, `delete`,
`export`, `credit_mode`, and `preview_channel`. Capabilities describe supported operations only;
authorization, current credential state, and environment locks are evaluated separately.

All management operations resolve the authoritative capability set on the server before executing.
Single-item unsupported requests return a typed validation error. Batch operations compute the
intersection of capabilities for the selected credentials and return a typed per-item outcome;
one unsupported item does not misreport successful items. Destructive or high-volume operations
support a side-effect-free preview before execution.

The console consumes the same catalog contract. It hides inapplicable actions, disables actions
that are temporarily unavailable, and explains the reason. “Select page” and “select all matching
results” remain distinct scopes, and the server re-evaluates the filter at execution time.

Provider-specific fields, validation, and defaults remain owned by provider adapters. The shared
fleet layer owns filtering, selection, preview, authorization, result envelopes, and audit hooks.

The initial conservative inventory is:

| Credential variant | Credential kind | Supported operations |
| --- | --- | --- |
| Google Antigravity | OAuth | verify, test, quota, toggle, delete, export, credit mode |
| Google AI Studio | API key | verify, test, toggle, delete, export |
| Grok Build | OAuth | verify, test, quota, toggle, delete, export |
| SpaceXAI Console | API key | verify, test, toggle, delete, export |
| Codex | OAuth | verify, test, quota, toggle, delete, export |
| OpenAI Platform | API key | verify, test, toggle, delete, export |
| Claude Code | OAuth | verify, test, toggle, delete, export |
| Claude Platform | API key | verify, test, toggle, delete, export |
| Ollama | Connection | verify, test, toggle, delete, export |

### Production R1 normalization (2026-09-09)

P2.1 extends the same registry into the complete production matrix for `add`, `verify`, `test`,
OAuth `refresh`, `quota`, `model_discovery`, normalized inference protocols, `disable`, `export`,
and `delete`. `toggle` remains a v1 compatibility alias for the canonical `disable` capability.
The exact matrix and operation meanings are maintained in `docs/provider-capabilities.md`.

The v1 `GET /api/providers` schema and body remain unchanged. New clients consume the additive,
versioned `GET /api/providers/capabilities` route. The credential console stores each returned
variant contract and derives card actions and mixed-selection eligibility from it; it no longer
uses provider-name checks for quota or credential actions. Missing catalogs, unknown variants, and
undeclared operations fail closed. The server uses the same registry before model discovery,
single-item mutations, export, quota, verification, tests, and batch planning.

`refresh_identity` and `preview_channel` remain in the vocabulary for legacy compatibility but are
not declared for the current shared provider pool. They cannot be invoked through the Wave 2 fleet
service until a variant explicitly earns support through contract and failure-path tests.

### Provider-pool lifecycle normalization (2026-09-13)

The shared Pool now declares `edit` for all nine variants and `reauthenticate` for the four OAuth
variants. Editing is deliberately narrow: every managed entry can change its display name, API-key
entries can rotate a key only after native provider validation, and Ollama can change its endpoint
or optional key only after validating the complete resulting connection. OAuth secrets use the
provider authorization flow instead of an in-place secret editor. Environment-owned entries remain
visible but read-only.

Verification is diagnostic rather than an enable action. A successful verification refreshes model
metadata and clears recorded errors while preserving the prior enabled or disabled state. This
prevents a routine check from silently returning an intentionally disabled credential to routing.

### Wave 2 batch boundary

The initial fleet implementation accepts 1–100 explicit targets. Deletion and batches of 20 or
more targets require a side-effect-free preview issued within the previous five minutes. The
opaque preview token is bound to the normalized mode, action, and ordered target selection, and
the server reloads every credential and re-evaluates capabilities during execution. Each item has
a five-second execution boundary and an independent typed result; duplicate targets are reported
without executing twice.

Guarded execution also requires an 8–128 character idempotency key. Completed responses and
in-flight reservations are bounded to 256 entries, contain no credential content, and prevent
concurrent requests with the same key from executing a mutation twice. This coordination state is
process-local by design while Polaris remains single-worker. It is not permission to enable
multiple workers; Phase 6 must move preview and idempotency coordination behind the accepted
distributed-state boundary first.

### Wave 4 coordination addendum (2026-09-04)

Preview and idempotency authority now use the lifecycle-selected fenced CAS backend. Completed
responses are compressed into encrypted bounded chunks and published by an atomic root transition,
so the 100-target contract does not silently exceed the generic 16 KiB CAS payload limit. The route
checks reservation ownership before each mutation and retains an active marker after an unknown
post-mutation failure. This closes the process-local batch-idempotency defect, but not the separate
credential-pool upsert/deduplication lock or the pending per-domain capacity proof. Coordinated HA
activation therefore remains prohibited.

### Wave 2 evidence foundation

The initial evidence boundary answers four on-call questions: which credential operation is
failing or timing out, which bounded provider variant is affected, which request touched the same
anonymous target, and whether an idempotent retry executed a mutation again. Toggle, deletion, and
credit-mode attempts emit one schema-versioned JSON event per target with request ID, actor class,
action, operation, mode, HMAC target fingerprint, provider variant, bounded outcome, duration, and
summary code. Events never contain filenames, credential content, session values, idempotency
keys, emails, tokens, prompts, or raw exception text.

The single-worker foundation keeps a 1,000-event process-local diagnostic mirror and emits the
same allowlisted event to the existing append-only structured log stream. Prometheus exposes
`polaris_credential_operations_total` and
`polaris_credential_operation_duration_seconds` with only bounded operation, outcome, mode, and
variant labels. Request IDs and fingerprints remain event fields, never metric labels. The mirror
is not the durable, queryable audit repository required by Phase 4; that phase remains open and
must persist this schema behind the durable-state boundary in ADR-006 before claiming full audit
coverage.

## Compatibility and Rollback

- Existing provider metadata is mapped to a conservative default set derived from current server
  routes; an undeclared capability is unsupported.
- Current single-item routes remain available during 1.x and delegate to the capability-aware
  operation service.
- The existing batch route remains available and preserves `success_count`, `total_count`,
  `errors`, and `message` while additively returning preview and per-item result fields. The 1.x
  console now performs the preview/idempotency handshake before execution.
- The console can fall back to current per-card controls while the new batch surface is disabled.

## Consequences

- Mixed-provider fleet operations become predictable and enforceable on both client and server.
- Adding a provider requires declaring its complete credential-operation contract.
- Conservative defaults may initially hide an operation until its provider adapter is updated.
- The operation result envelope and capability vocabulary become compatibility-sensitive APIs.

## Rejected Alternatives

- Provider-name conditionals in the console were rejected because they drift from server behavior.
- A universal operation set was rejected because provider credentials are not interchangeable.
- Fail-fast batches were rejected because they obscure partial progress and complicate recovery.
- Arbitrary provider plugins were rejected because executable extensions widen the trust boundary.
