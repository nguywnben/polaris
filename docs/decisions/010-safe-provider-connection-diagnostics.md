# ADR-010: Normalize Provider Connection Diagnostics at the Management Boundary

## Status

Accepted on 2026-09-09 for the production self-hosted R1 scope.

## Context

Credential model tests previously returned and persisted redacted copies of provider response
bodies. Pattern redaction cannot make arbitrary third-party text safe, provider-specific shapes
made the console unpredictable, and closing the test dialog did not stop provider work. Per-call
adapter timeouts also allowed refresh and follow-up calls to exceed one user-visible deadline.

## Decision

Normalize connection-test failures at the management boundary into a versioned diagnostic with a
stable category, safe message, fixed remediation, retryability, optional provider HTTP status, and
an optional allowlisted provider code. Raw upstream bodies and exception messages are inputs to
classification only and never cross the public or persisted boundary.

Keep the route backward compatible by retaining `error` and `detail` as safe strings and adding
`diagnostic`. HTTP 429 remains a successful connection check with a quota/rate-limit warning. A
single 30-second deadline covers the complete test. Browser AbortController cancellation and ASGI
disconnect detection cancel the same provider coroutine; caller cancellation is never converted
into an ordinary failure.

## Consequences

- Console remediation is consistent across all advertised provider/authentication variants.
- Useful provider status survives without exposing arbitrary provider content.
- Unknown provider codes deliberately lose detail and fall back to status-based classification.
- Cancellation stops this management diagnostic only; it does not define general inference stream
  or retry behavior.
- Future contract changes require a new diagnostic schema version and compatibility review.

## Rejected alternatives

- Expanding secret-pattern redaction was rejected because arbitrary upstream text is not a safe
  public contract.
- Returning each provider's native error schema was rejected because it couples the console to
  untrusted, changing third-party payloads.
- A background test-job system was rejected as unnecessary for a bounded personal/small-team
  self-hosted workflow.
- Implementing global inference timeout and retry policy here was rejected because that belongs to
  fixed task P2.4.
