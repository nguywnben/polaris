# Provider authorization coordination contract

## Status

Accepted W4-C blocker-closure specification. It does not activate coordinated mode or change the
HA activation allowlist.

## Threat boundary

Provider authorization transactions contain PKCE verifiers, discovered token endpoints, device
authorization identifiers, and user codes. They are security state, not disposable cache data.
Another replica must be able to complete a flow created by the first replica, while replay,
cross-provider substitution, stale epochs, dependency loss, corrupt payloads, and concurrent token
exchange fail closed. Redis keys and stored payloads must not expose raw flow identifiers or proof
material.

## One-time OAuth transactions

Claude Code and Grok Build use the existing fenced one-time transaction primitive:

- the service creates a 256-bit opaque state with a provider-specific, syntactically recognizable
  prefix only where callback dispatch needs it;
- state and proof indexes are separate domain-derived HMAC values;
- the payload is a closed JSON object encrypted with AES-GCM under a lifecycle-derived key;
- the backend owns expiry and capacity; no process-local map is authoritative;
- consume is atomic, one-time, provider-bound, and returns a generic error for missing, expired,
  replayed, corrupt, stale-epoch, or unavailable state;
- a failed token exchange does not restore a consumed transaction.

## Polling device transactions

Codex device authorization uses a separate leased CAS state machine because a pending provider
response must preserve the transaction. A replica atomically claims one flow for a bounded lease;
only that revision may release or consume it. Another replica may take over after lease expiry.
Every update retains the original absolute lifetime, terminal consumption erases the secret payload,
and the closed payload remains encrypted. Correctness does not depend on a best-effort lock.

## Activation rule

Both transaction classes now have cross-client, concurrency, expiry/replay, stale-epoch,
dependency-loss, encryption, and lifecycle-injection tests over the same OIDC/CAS primitives whose
in-memory and Redis implementations share a contract. This removes the process-local provider-flow
defect at the implementation layer. It does not supply live Redis/two-replica evidence, populate
`SUPPORTED_HA_ACTIVATION_RECORDS`, or change the one-replica ceiling.
