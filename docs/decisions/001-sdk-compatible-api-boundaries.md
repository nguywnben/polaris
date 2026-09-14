# ADR-001: Preserve SDK-Compatible API Boundaries

## Status

Accepted

## Date

2026-07-12

## Context

Polaris serves clients built for the OpenAI, Anthropic, and Google GenAI SDKs. Product-specific path prefixes force users to override SDK behavior, create duplicated segments, and make otherwise compatible IDE integrations fail. Provider names also change more frequently than the client protocols they implement.

## Decision

Expose inference endpoints at the paths expected by supported SDKs:

- OpenAI-compatible routes under `/v1`.
- Anthropic Messages at `/v1/messages` from the service origin.
- Google GenAI routes under `/v1beta` and `/v1` as requested by the SDK.
- Management operations under `/api`, separate from inference contracts.

Keep provider identity behind capability and routing interfaces rather than embedding it in public inference paths. Keep product branding in the console and documentation. Retain `sk-ogw-` only as the API-key identification prefix.

## Alternatives Considered

### Product-prefixed inference routes

Paths such as `/omni/v1` or `/gateway/v1` make ownership visible but require non-standard client configuration and can produce duplicated SDK paths. Rejected because compatibility is the primary contract.

### One generic request schema

A single custom endpoint would reduce router count but force every client to translate its payload before reaching the gateway. Rejected because translation belongs in the gateway.

## Consequences

- Existing SDKs can use their normal base-URL behavior.
- Route compatibility tests are required before public API changes.
- Management APIs evolve independently from inference protocols, but documented 1.x routes follow Semantic Versioning and cannot be removed without a major release.
- Provider additions should extend registry and adapter boundaries without creating provider-specific public namespaces.
