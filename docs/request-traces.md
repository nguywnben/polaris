# Request Decision Trace Contract

Polaris persists one bounded, redacted decision trace for each supported inference request.
The trace is operational evidence, not a prompt-observability store: request content, response
content, authorization values, API keys, credential filenames, arbitrary metadata, and exception
text are outside the schema and fail strict record validation.

## Versioned summary

Schema version 1 records a generated trace ID, the public `X-Request-ID`, a closed protocol and
outcome, UTC start/completion timestamps, status and duration, bounded model/provider dimensions,
normalized token/cost totals, a truncation flag, and at most 64 ordered decisions. Supported
decision categories cover request admission, routing/fallback, retry, cooldown, compression,
guardrails, cache, quota, upstream execution, usage, and final outcome. Actions, results, and
reason codes are closed vocabularies; free-text detail cannot enter durable storage.

Supported request surfaces are OpenAI Chat Completions and Responses, Anthropic Messages and token
counting, Gemini generate/stream/count-token, and their Vertex equivalents. Management requests and
raw runtime logs are deliberately excluded.

## Lifecycle and storage

The request middleware creates the collector after validating or generating `X-Request-ID`.
Non-streaming traces are finalized with the response; streaming traces finalize after the body is
consumed or cancelled so deferred provider decisions and cleanup are included. Trace persistence
is best-effort and cannot alter the inference response, while a configured trace repository that
cannot initialize still fails application startup rather than silently disabling evidence.

SQLite, PostgreSQL, and MongoDB use additive `request_traces` storage with request, protocol/outcome,
route, and stable-order indexes. Records are revalidated on every read. Signed opaque cursors and
strict query types form the repository boundary used by the management API in W3.11.

## Management API

All trace-management routes require the authenticated panel session and return sanitized errors:

- `GET /api/traces` lists newest-first traces with signed cursor pagination. Filters are exact and
  allowlisted: protocol, outcome, provider, model, public request ID, and UTC start bounds.
- `GET /api/traces/{trace_id}` returns one strictly revalidated trace or `404`.
- `GET /api/traces/retention` returns the active independent policy and supported bounds.
- `PUT /api/traces/retention` validates and applies both limits, immediately prunes records outside
  either limit, and emits correlated management-audit evidence.
- `GET /api/traces/export?format=jsonl|csv` exports the applied filter snapshot. Export fails rather
  than silently truncating above 10,000 traces or 16 MiB; CSV cells are formula-safe, filenames are
  allowlisted by the client, and successful exports emit an audit event.

Query and export responses contain only the versioned trace contract. Raw logs, prompts, responses,
credential names, arbitrary metadata, and exception strings cannot be requested through these
routes.

## Operations console

The **Activity** destination combines request traces, audit/security events, and bounded runtime
logs as three accessible tabs. Its shared investigation form applies time, canonical outcome, and
public request-ID filters across all three views; provider narrows request traces and runtime text,
while actor type narrows audit events and runtime text. A trace detail can open related audit
evidence without re-entering the request ID, and the Dashboard's recent-request action opens the
same correlated trace workflow.

Trace-specific protocol, model, paging, retention, and export controls remain next to the trace
list. Only protocol and page-size preferences may persist in browser storage; model and every
shared investigation value remain session-only. Untrusted API records are checked against the
closed schema before text-only DOM rendering.

The stable `/logs` deep link now opens the **Runtime logs** Activity tab, while `/activity` opens
request traces. The raw-log WebSocket viewer remains a visually and semantically separate
**Diagnostic only** surface with server-side redaction, authentication, same-origin enforcement,
clear, and retention controls. Downloads contain only the newest complete redacted lines, are
bounded to 16 MiB, and report byte-limit and truncation headers. Raw logs are a low-level fallback;
request traces are the primary source for routing and failure investigation.

Trace retention is independent from audit and raw-log retention. Its separate persisted default is
7 days or 100,000 traces, whichever limit is reached first; supported policy bounds are 1–90 days
and 1,000–1,000,000 traces. Age pruning runs before oldest-first count pruning after each append and
on policy update. No database TTL index bypasses this explicit policy.
