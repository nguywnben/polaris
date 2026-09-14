# ADR-012: Use One Bounded, Output-Aware Stream Lifecycle

## Status

Accepted on 2026-09-09 for the production self-hosted R1 scope.

## Context

The gateway exposed six public streaming surfaces through nested provider, canonical Gemini, and
protocol-conversion iterators. A downstream disconnect did not reliably close every nested source.
Retry handling distinguished attempts by status but not by whether output had already reached the
client, allowing duplicated content after a partial response. Several framing and aggregation
paths also had no explicit memory ceiling, and a transport-split UTF-8 character could be replaced.

Quota fallback settlement used the initial HTTP status, so an interrupted HTTP 200 stream could be
committed as successful. Request traces had the same ambiguity for in-stream failures.

## Decision

Use a shared managed streaming response and explicit cascading ownership for nested iterators.
Treat the first data event as the retry boundary while allowing SSE comment heartbeats before a
safe retry. Require a provider terminal event before recording success. After output begins, map
all timeout, exception, error-response, invalid-frame, and premature-EOF paths to one terminal
in-stream error without retrying or switching credentials.

Bound transport framing at 1 MiB and intentional aggregations at 8 MiB. Preserve split UTF-8 bytes
until a complete sequence is available. Commit a fallback quota estimate only after natural stream
completion with no upstream-failure decision; cancellation and failure release it. Persist one
trace after the body lifecycle ends, allowing an upstream failure decision to override HTTP 200.

## Consequences

- Disconnects promptly close HTTP response contexts and release provider and quota resources.
- A client never receives a replayed prefix from an ordinary retry after visible model output.
- Partial streams are explicit failures rather than apparent successes with incomplete usage.
- Large valid responses remain streamable; only frame-sized buffers and features that inherently
  reconstruct a final response have ceilings.
- The opt-in anti-truncation feature retains clean-EOF continuation but cannot retry an exceptional
  partial attempt.
- No endpoint, dependency, environment setting, storage schema, or deployment topology changes.

## Rejected alternatives

- Retrying after partial output was rejected because neither HTTP nor the provider protocols offer
  a general exactly-once delivery guarantee.
- Relying on garbage collection to close async generators was rejected because lease and
  reservation release must be deterministic.
- Buffering full streams without a ceiling was rejected because a self-hosted process needs a
  predictable memory bound.
- Adding a new heartbeat timer or retry configuration surface was rejected; provider heartbeats and
  the existing timeout/retry controls are sufficient for R1.
