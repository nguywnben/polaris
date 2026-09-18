# ADR-014: Preserve Meta Responses replay inside the managed pipeline

## Status

Accepted on 2026-09-15 for the approved Meta Model API integration.

## Context

The legacy Responses-to-Chat-to-Gemini path cannot preserve encrypted reasoning,
assistant phase or streamed function events. Blind passthrough would bypass
Polaris routing, guardrails and usage accounting; relaxing the legacy schema would
advertise unsupported behavior for unrelated providers.

## Decision

Use a separate bounded Meta Responses schema and native event adapter. Construct
a canonical policy-visible mirror, sealed together with the validated native
payload using a process-local identity and content fingerprint. Verify this
boundary before every provider dispatch and again inside Meta transport.
Reject forged JSON markers, mirror/native mutation and cross-provider replay.

Use the existing primary pipeline for both streaming and non-streaming calls.
Only Meta-native consumers receive native events; canonical consumers retain their
existing response shape. Hold terminal events until upstream validation and primary
usage accounting finish. Never log native Meta response bodies. Retain vendor HTTP
status, but sanitize vendor error bodies.

## Consequences

- Native replay remains stateless upstream (`store: false`) and client-managed.
- Canonical history pruning is skipped for opaque native history; changed policy
  mirrors fail closed rather than bypassing masking.
- Native virtual routes must contain only supported Meta models.
- No new dependency, persistent schema or background service is required.
- Full Anthropic reasoning/tool-search compatibility remains unsupported and is
  documented in the [provider guide](../providers/meta-model-api.md).

## Rejected alternatives

- Direct HTTP from the public router bypasses shared policy and accounting.
- Routing opaque Meta history through another provider changes its meaning.
- Expanding the legacy schema globally misrepresents other providers' capabilities.
