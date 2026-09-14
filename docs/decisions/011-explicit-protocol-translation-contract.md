# ADR-011: Make Cross-Protocol Translation Explicit and Fail Closed

## Status

Accepted on 2026-09-09 for the production self-hosted R1 scope.

## Context

The public request models previously allowed arbitrary extra fields, while several nested content
converters skipped unknown message parts or serialized unknown Anthropic blocks into text. That
made apparently successful requests capable of losing instructions, images, structured-output
requirements, or reasoning metadata. Usage translation also subtracted cached input from OpenAI
prompt totals and could count provider reasoning inconsistently.

The gateway advertises five ingress families across multiple provider variants. Maintaining
separate informal assumptions for each route is too error-prone for a production self-hosted
release, but a new universal protocol or runtime framework would add unnecessary complexity.

## Decision

Keep the existing canonical Gemini-shaped boundary and add a versioned semantic matrix plus shared
request/response golden fixtures. Public Pydantic models reject unknown typed fields. Supported
fields are translated explicitly; known semantics that cannot be enforced consistently are
rejected with native HTTP 400 errors. Unknown upstream response parts raise one translation error
that the public boundary normalizes to the endpoint's native HTTP 502 envelope.

Treat cached tokens as a detail of the full effective input, and treat reasoning tokens as a
subset of total generated output. Provider adapters subtract the reasoning subset when populating
Gemini candidate tokens so translation back to OpenAI cannot double count it.

## Consequences

- A successful response no longer implies that unknown request or response semantics were ignored.
- Existing clients sending undocumented extra fields now receive an actionable 400. This is an
  intentional fail-closed hardening of behavior that previously made no correctness guarantee; no
  documented R1 operation, route, or accepted field is removed.
- Adding protocol support requires fixture and disposition changes, making scope and compatibility
  review visible.
- Data-URL image input is supported for translated OpenAI surfaces; remote image references remain
  explicitly rejected until a secure fetch/file policy exists.
- Streaming behavior is unchanged and remains owned by P2.4.

## Rejected alternatives

- Continuing `extra=allow` was rejected because accepting and discarding a field is more dangerous
  than returning a clear client error.
- Passing arbitrary unknown blocks through as prompt text was rejected because it changes roles and
  model-visible semantics.
- Building a new protocol-neutral object graph was rejected because the current canonical boundary
  can satisfy R1 with much less code and migration risk.
- Expanding P2.3 into streaming retry/cancellation work was rejected because it would violate the
  fixed task boundary and verification cadence.
