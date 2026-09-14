# ADR-013: Use One Canonical Standalone Routing Policy

## Status

Accepted on 2026-09-09 for the production self-hosted R1 scope.

## Context

Credential eligibility, strategy selection, cooldown, retry fallback, and diagnostic explanations
had grown across the smart router, three unused legacy selection helpers, provider request loops,
and request traces. The legacy helpers disagreed with the runtime cost and latency policy. Weighted
selection could not be reproduced through an injected random source. Cooldown reads also discarded
failure count at expiry, preventing repeated failures from increasing exponential backoff.

When no route was eligible, the public inference error claimed the model was unsupported even when
credentials were merely disabled, busy, or cooling down. Operators had historical trace summaries
but no recent, direct routing explanation.

## Decision

Keep `SmartCredentialRouter` as the only credential-selection authority. Remove the unused legacy
selectors and verify all five strategies through one seeded scenario matrix. Preserve the existing
provider request API, retry controls, model fallback order, and single-replica deployment boundary.

Retain failure count until a success resets route health; expire only the retry deadline. Return a
typed internal decision with a stable reason and recovery delay. Project that decision through a
separate public serializer that exposes only aggregate candidate states/reasons and never credential
or request identifiers.

Expose the bounded projection at authenticated `GET /api/observability/routing` under
`DASHBOARD_READ`. Keep public inference failures generic enough to be truthful for unsupported,
disabled, busy, and cooldown states while still naming the requested model and operator actions.

## Consequences

- Runtime selection and verification use the same strategy implementation.
- Seeded fixtures reproduce weighted decisions without making production selection deterministic.
- Repeated unhealthy outcomes produce bounded increasing delays and a success resets recovery.
- Operators can distinguish configuration, eligibility, capacity, and cooldown failures without
  access to credential filenames or request IDs.
- Recent decision storage remains process-local and capped at 100 records, appropriate for the R1
  standalone runtime; it is not durable monitoring or HA evidence.
- No dependency, migration, background service, or new user-facing setting is introduced.

## Rejected alternatives

- Keeping parallel selector helpers was rejected because their cost tiers and unknown-latency
  handling already differed from the runtime router.
- Returning raw candidate decisions was rejected because filenames may contain account identity and
  request IDs are unnecessary for this operational summary.
- Resetting failures when time passes was rejected because it collapses exponential recovery to the
  base delay during a sustained outage.
- Adding circuit-breaker, fleet-healing, or multi-replica controls was rejected as enterprise scope
  beyond production self-hosted R1.
