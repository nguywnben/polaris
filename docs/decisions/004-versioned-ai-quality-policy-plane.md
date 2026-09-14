# ADR-004: Versioned AI Quality Policy Plane

## Status

Implemented for the Production Self-Hosted R1 core in P2.6. The global console was completed in
P4.1; virtual-key lifecycle presentation remains scheduled for P4.4.

## Context

Polaris currently exposes context optimization, guardrails, response caching, and related
runtime settings as independent global values. Operators cannot select a quality intent, preview
the effective request policy, or explain why content was changed. Per-request controls would also
create a governance bypass if they could weaken deployment safety settings.

## Decision

Introduce a versioned, provider-neutral quality-policy document. The supported profiles are
`quality`, `balanced`, `capacity`, and `custom`. Existing stored values are projected into a
`balanced` or `custom` document without changing runtime behavior; legacy fields remain readable
during the 1.x compatibility window.

Resolve policy in this order:

```text
deployment safety ceiling
  -> stored global policy
    -> virtual-key restriction
      -> allowlisted per-request override
```

Each layer may make behavior stricter but cannot weaken an earlier safety constraint. Invalid or
unavailable enabled security policy fails closed. Compression itself fails safe by leaving the
request unchanged when its invariants cannot be proven.

For R1, the lower-layer allowlist is intentionally small: a virtual key and a request may only
`inherit` compression or disable it. A virtual-key restriction is managed through
`PATCH /api/virtual-keys/{key_id}/quality-policy`; a caller may set `x-polaris-compression: off` for
one request. Neither surface can enable globally disabled compression or change thresholds. Invalid
request values return HTTP 400 instead of being ignored.

The first production compression mode remains structural history-prefix pruning. It preserves
system instructions, tool definitions, recent complete turns, tool-call/result pairs, structured
payloads, and the original request object. Semantic summarization, filler removal, code thinning,
and tool-output rewriting require a separate accepted decision backed by an evaluation corpus.

Token estimation is iterative and bounded. Estimation, copy, or post-compression invariant failure
returns the original payload with a bounded reason (`estimation_failed` or `invariant_failed`). The
same decision runs once before provider translation for Primary providers and Vertex anonymous.

Every request records the policy version, selected and effective profile, applied/skipped reason,
estimated input tokens before and after, guardrail result, cache result, and latency. Prompt,
response, tool payload, and secret content are excluded.

Policy updates use optimistic concurrency through a revision value. Preview evaluates a bounded,
redacted request description and performs no provider call or persistent mutation.

## Migration and Rollback

- On first read, existing context-optimization values are mapped without rewriting storage.
- The first successful policy write persists the new document and retains legacy values for a
  1.x rollback.
- Runtime selection can return to the legacy projection through one feature flag while the new
  document remains stored but inactive.
- Removing the legacy bridge requires a future deprecation ADR and migration guide.

## Consequences

- Quality behavior becomes explainable and testable as one contract instead of unrelated toggles.
- Virtual keys and request overrides cannot bypass deployment governance.
- The policy evaluator becomes a hot path and must remain pure, bounded, and dependency-free.
- Policy telemetry increases trace volume and therefore requires retention and redaction limits.

## Rejected Alternatives

- Independent global switches were rejected because they permit contradictory configurations.
- Request settings with unconditional precedence were rejected because they bypass governance.
- Semantic compression was rejected for the initial release because token savings alone do not
  demonstrate answer-quality preservation.
- Replacing legacy configuration immediately was rejected because it would make rollback unsafe.
