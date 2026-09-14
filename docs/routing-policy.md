# Routing, Fallback, Cooldown, and Health

Polaris R1 uses one canonical credential router for the supported standalone deployment: one
worker and one replica. The router combines model eligibility, credential state, bounded health
penalties, concurrency leases, and the configured strategy before any provider request is sent.

## Eligibility order

A route is considered only when all of these checks pass:

1. the credential exists and is enabled;
2. a model-specific cooldown has expired;
3. preview compatibility matches Code Assist preview requirements;
4. the credential/model and provider/model pairs are not excluded;
5. the provider capability contract supports the requested provider and model;
6. the short-lived route cooldown has expired; and
7. the credential has spare routing capacity.

An explicit model catalog stored with a credential is authoritative. Provider capability inference
is used only when that catalog is absent. A model failure on one credential does not suppress the
same model on another compatible credential.

The standalone router accepts at most 100 candidates per decision. Larger pools fail closed with
an actionable diagnostic rather than performing unbounded work.

## Strategy contract

All strategies run after eligibility and model-support checks. Stronger model-support evidence is
preferred before a strategy tie-breaker.

| Strategy | Selection behavior |
| --- | --- |
| `balanced` | Spreads requests using in-flight count, last selection, historical use, health, configured rotation order, then filename for a stable final tie-break. |
| `priority` | Prefers the configured provider, then uses the balanced signals; it falls back when that provider is ineligible. |
| `weighted` | Samples healthy candidates without replacement using each credential's positive weight. A seeded router produces the same order for deterministic tests. |
| `least_latency` | Prefers the lowest 100 ms latency bucket. An unmeasured credential receives an initial opportunity so it can build history. |
| `lowest_cost` | Prefers local/subscription quota, then free or unknown tiers, then metered API platforms; balanced signals break ties. |

Unknown strategy values normalize to `balanced`. Legacy standalone selectors were removed so the
runtime and scenario tests cannot apply different cost, latency, or weight rules.

## Retry and fallback order

- HTTP `408`, `409`, `429`, `500`, `502`, `503`, and `504` are retryable when the existing bounded
  retry setting is enabled and budget remains.
- Authentication, validation, and other client failures are not retried by default.
- A provider `404` excludes only the failed credential/model route, then tries the next compatible
  credential or ordered virtual-model candidate.
- A transient failure makes the affected route temporarily ineligible, allowing a healthy
  alternate credential to win.
- Streaming output is the retry boundary: after model output starts, no ordinary retry or
  credential switch may replay the prefix.
- Retry and model-candidate loops remain bounded by the configured retry count and the fixed model
  route attempt ceiling.

The `switch_credential_enabled` setting retains its existing behavior. When enabled, an eligible
alternate credential is acquired between transient attempts. When disabled, the current request
may retry the same credential while new requests observe its health state.

## Cooldown and recovery

Transient and rate-limit failures use exponential delays starting at 2 seconds and capped at 30
seconds by default. Authentication failures use 300 seconds; model-unavailable failures use 60
seconds. A valid provider quota reset timestamp takes precedence. These are runtime defaults, not
new R1 configuration controls.

Failure count is retained after a cooldown expires so repeated failures increase the delay. A
successful completion clears the failure state and latency measurements continue in a rolling,
10-sample window. Client-request failures do not penalize route health.

## Operator diagnostics

Authenticated readers with `DASHBOARD_READ` may call:

```text
GET /api/observability/routing?limit=20
```

`limit` is 1–100. The response includes selected/unavailable counts and recent decisions with:

- mode, requested model, required provider, and normalized strategy;
- whether a route was selected and its provider;
- a stable reason, actionable message, and rounded retry delay;
- bounded counts of candidate states and rejection reasons; and
- decision time.

The public response never contains credential filenames, tokens, credential payloads, request IDs,
raw provider errors, or exception text. It reports `no_data` before the process has made a routing
decision and returns a bounded `503 routing_health_unavailable` envelope if diagnostics cannot be
read.

Common unavailable reasons are `no_credentials`, `credentials_disabled`, `cooldown_active`,
`capacity_exhausted`, `candidate_capacity`, `model_unavailable`, and `no_candidate`. Follow the
returned message first; then use provider connection diagnostics and request traces when deeper
evidence is needed.

## Scope boundary

This policy does not activate Redis coordination, multi-replica routing, automatic fleet repair,
or commercial-service traffic controls. Those remain experimental or post-R1. No new dependency,
database migration, background worker, or configuration page is required by this contract.
