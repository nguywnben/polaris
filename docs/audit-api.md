# Audit Management API

The audit API exposes durable, redacted control-plane evidence to an authenticated panel session.
It never returns raw actor identities, credential filenames, provider secrets, plaintext keys, or
prompt content. SQLite, PostgreSQL, and MongoDB use the same repository contract and cursor rules.

## Authentication and errors

All routes require the existing panel session cookie, a legacy bearer session token, or a virtual
key with the required management read/write scope. Virtual keys are accepted only through the
Bearer header; credentials are never accepted in query parameters. Audit-specific handled errors
use the management envelope:

```json
{"error":{"code":"audit_query_invalid","message":"The audit query contains an invalid filter or cursor."}}
```

Invalid Pydantic inputs use the standard management validation response. Storage and internal
errors return `503 audit_unavailable` without exposing exception details.

## Query events

`GET /api/audit/events` returns newest-first evidence and an opaque signed cursor. The cursor is
bound to the repository signing key and fails closed if modified.

| Query parameter | Contract |
| --- | --- |
| `actor_types` | Repeatable exact allowlisted actor type; at most 32 values |
| `actor_fingerprints` | Repeatable exact 20-character lowercase hexadecimal fingerprint |
| `actions` | Repeatable exact allowlisted action; at most 32 values |
| `target_types` | Repeatable exact allowlisted target type; at most 32 values |
| `target_fingerprints` | Repeatable exact 20-character lowercase hexadecimal fingerprint |
| `outcomes` | Repeatable exact allowlisted outcome; at most 32 values |
| `request_id` | Exact request ID, at most 128 safe characters |
| `occurred_after` | Inclusive timezone-aware RFC 3339 lower bound |
| `occurred_before` | Inclusive timezone-aware RFC 3339 upper bound |
| `page_size` | 1–200, default 50 |
| `cursor` | Opaque continuation token returned by the previous page |

The response contains `events`, `next_cursor`, `page_size`, and `has_more`. Event records contain
only the version, event/request IDs, UTC timestamp, allowlisted actor/action/target/outcome values,
HMAC fingerprints, and allowlisted change codes. Total counts are intentionally omitted to avoid
an unbounded count query.

## Retention

`GET /api/audit/retention` returns the active policy and supported bounds. The default is 90 days
and 1,000,000 events. Supported values are 7–3,650 days and 1,000–10,000,000 events.

`PUT /api/audit/retention` requires the complete strict body:

```json
{"retention_days":90,"max_events":1000000}
```

The service persists the new policy before deleting anything, then prunes by the exact age and
count rules and returns `removed_events`. Every subsequent append is serialized with retention
enforcement, so the configured bounds remain active. The retention mutation itself is recorded
after the route response by the common management audit boundary, including failure outcomes.
Corrupted stored policy data fails startup before repository creation or key generation.

## Export

`GET /api/audit/export?format=jsonl` and `format=csv` accept the same filters as the event query,
but not consumer cursors or page sizes. The service follows internal opaque cursors in 200-event
pages and sends the completed bounded payload through a streaming response.

- Maximum 10,000 events and 8 MiB of UTF-8 output.
- A result over either limit returns `413 audit_export_limit_exceeded`; it is never silently
  truncated.
- JSONL uses one deterministic redacted event object per line.
- CSV uses a fixed column order and prefixes spreadsheet-formula cells with an apostrophe, even
  when a dangerous formula marker follows leading whitespace.
- Attachment filenames are generated only from server UTC time and the allowlisted format.
- A successful export records a correlated `audit.export` event before data is released. The
  exported snapshot intentionally does not include that newly appended evidence event.

The response includes `X-Audit-Event-Count`, `X-Audit-Byte-Count`, `X-Audit-Max-Events`, and
`X-Audit-Max-Bytes` headers.

## Audit operations console

The authenticated `/audit` compatibility route opens the **Audit & security** tab in Activity.
Activity owns the common time, outcome, actor type, and public request-ID investigation values;
selecting related trace evidence carries the request ID to the request-trace tab without persisting
it. Audit-specific action, target, fingerprints, paging, retention, and export controls remain next
to the event list.

The browser treats API responses as untrusted: it accepts only the documented event fields, schema
version, vocabularies, identifier formats, page bounds, and retention bounds before rendering
values through `textContent`. Payloads with unknown or missing event fields are rejected, so an
API-shape expansion cannot silently reach the DOM.

Only `actions`, `target_types`, and `page_size` may be remembered locally. Outcomes, actor types,
request IDs, actor/target fingerprints, time bounds, cursors, event records, and export payloads
are never persisted by the console. A newer event query aborts and supersedes an older one to
prevent stale responses from replacing current evidence. Export always uses the last applied
filter snapshot and accepts only the server-generated `polaris-audit-<UTC>.<format>` filename pattern.
Retention updates require an explicit confirmation that records outside either bound may be
removed immediately.
