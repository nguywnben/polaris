# Operational observability

The Overview page derives a 15-minute RED snapshot from bounded, content-free request decision
traces. It shows request rate, error ratio, p50/p95/p99 duration, model-route health, and quota,
budget, rate-limit, cooldown, and capacity pressure. The API reads at most 5,000 traces and exposes
at most 50 routes; the dashboard renders the ten busiest routes and marks a truncated sample.
Caller errors and policy/authentication denials are counted as rejections but excluded from the
service error ratio so invalid traffic cannot create a false availability incident.

## External export controls

Prometheus, OpenTelemetry, and Langfuse are independent opt-in integrations. All are disabled by
default. Prometheus is a local authenticated pull endpoint; OpenTelemetry exports only aggregate
gauges and never sends prompts, responses, request/trace IDs, credential identifiers, exception
text, or model-route dimensions.

Prometheus requires both `PROMETHEUS_EXPORT_ENABLED=true` and a `METRICS_TOKEN` of at least 32
UTF-8 bytes. Scrapes of `GET /metrics` must send `Authorization: Bearer <token>`. The endpoint
returns 404 while disabled, 503 for an unsafe enabled configuration, and compares tokens in
constant time. Provider is the only deployment-derived label on spend counters. Durable-ledger
operation counters use only closed backend, operation, and result labels; RED metrics use only fixed
quantile, category, and status vocabularies. No virtual-key ID, request ID, credential reference,
model, cost, or driver error becomes a metric label.

OpenTelemetry requires `OTEL_EXPORT_ENABLED=true` and an HTTPS
`OTEL_EXPORTER_OTLP_ENDPOINT`. The gateway sends aggregate OTLP/HTTP JSON gauges to `/v1/metrics`
every `OTEL_EXPORT_INTERVAL_SECONDS` (15–300, default 60). Optional
`OTEL_EXPORTER_OTLP_PROTOCOL` is fixed to the standard `http/json` transport. Optional
`OTEL_EXPORTER_OTLP_HEADERS` accepts at most eight comma-separated `authorization`, `api-key`, or
`x-api-key` values. Credentials embedded in the endpoint, plaintext HTTP, arbitrary headers, and
line breaks fail startup. Header values and full endpoint paths are never returned to the console.

Langfuse is enabled only when both `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are configured.
It sends the request ID as a trace correlation ID plus model, provider, token counts, latency, and
allowlisted quality-decision metadata. Prompt and response bodies, credential identifiers, API
keys, and exception text are not sent. With either key absent, the request-completion path returns
before constructing the exporter or an HTTP client.

The reference rules are in `deploy/observability/prometheus-alerts.yml`. Tune thresholds only
after establishing a traffic baseline; the supplied error and latency alerts require a minimum
sample so idle or new installations do not page.

## Process-local coordination evidence

`polaris_coordination_operations_total{backend,operation,result}` records process-local coordination,
quota, and identity-security operations. `backend` is limited to `in_memory` or `unknown`, while
operation and result use closed vocabularies. Logical keys, session identifiers, provider values,
payloads, and exception text never become labels.

`polaris_routing_coordination_events_total{operation,result}` records credential-routing, route
outcomes, governance invalidation, and exact-cache decisions. Use these counters to diagnose quota
rejections, reconciliation pressure, and repeated lifecycle failures inside the supported
standalone process.

`polaris_runtime_ready`, `polaris_runtime_coordination_available`, and
`polaris_runtime_info{mode,state}` describe the one-process lifecycle. `/ready` fails closed when that
lifecycle is starting, unavailable, or closed; `/health` remains a process liveness probe. The
reference alert file contains one sustained runtime-unavailable alert and no distributed-topology
claims.

## Symptom runbooks

- [High error rate](runbooks/high-error-rate.md)
- [High latency](runbooks/high-latency.md)
- [Quota, budget, or capacity exhaustion](runbooks/capacity-exhaustion.md)
- [Storage unavailable](runbooks/storage-unavailable.md)
- [Unknown model pricing](runbooks/unknown-pricing.md)
