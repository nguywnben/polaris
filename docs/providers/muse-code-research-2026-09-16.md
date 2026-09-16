# Muse Code integration research — 2026-09-16

Status: direct OAuth implementation and offline verification, following the user's
explicit approval of a direct adapter rather than a CLI bridge. Existing Meta Model
API remains an independent API-key provider. This is not vendor certification.

## Scope and handling

The user authorized installation and investigation on their fresh Ubuntu VPS,
approved the official device login, and authorized three bounded inference
attempts. All three attempts were used; this continuation made no further model
calls. The CLI runs under a dedicated unprivileged account. VPS credentials were
not copied into Polaris or source control. A separate user-approved Windows login
was exchanged in memory to verify the direct protocol; its credentials were not
persisted in the local credential pool or this document. No public bridge, firewall
change, Docker deployment, subscription change, or payment action was performed.

## Official sources read

The rendered browser pages are publicly readable without signing in, although the
web-text fetch returned a login-only shell. Read the rendered content rather than
concluding that documentation requires login.

- [Muse Code overview](https://dev.meta.ai/docs/muse-code): the published installer
  installs native binaries on macOS and Linux. Windows-native compatibility was
  not established for the CLI. Direct HTTP OAuth was subsequently verified on
  Windows without the CLI; WSL compatibility was not tested.
- [Authentication and billing](https://dev.meta.ai/docs/muse-code/auth): browser
  sign-in and explicit API keys are separate authentication choices. Managed Meta
  accounts require API keys. Environment/API-key precedence must not accidentally
  hide the intended subscription login.
- [Subscriptions](https://dev.meta.ai/docs/muse-code/subscriptions): the subscription
  attaches to the credential created during CLI onboarding. The page says that
  credential is for Muse Code only and subscription usage works through its CLI.
  Additional account API keys use pay-as-you-go billing. A successful HTTP call
  does not establish supported use outside the CLI or prove billing attribution.
- [Extending and automating](https://dev.meta.ai/docs/muse-code/extending): the CLI
  offers headless execution and JSONL output. It is an agent runtime, not a raw
  model proxy. Background observers can make additional model calls; subprocess
  step limits alone do not demonstrate a complete cost bound.
- [Official release article](https://research.meta.ai/blog/introducing-muse-code-and-muse-spark-1-2)
  links the installer at `https://dev.meta.ai/install.sh`.

These are product-documentation observations, not a legal interpretation or a
claim that a future CLI bridge is vendor-approved for every gateway use case.

## Observed official CLI behavior

Installed version: `1.3.0 (1.3.0-R3057.1)`, Linux x86_64. The official launcher
checks release artifact size and SHA-256. Auto-update was disabled for repeatable
research after installation.

- Browser device approval completed and the CLI reported verified Model API access.
- The saved `providers.meta` record contains `mechanism: oauth`,
  `obtained_via: device_code`, an OAuth access token, and a different inference key.
  The record inspected had no refresh token or expiry value. Absence from this
  record does not prove that the account token never expires.
- The inference key authenticated `GET /v1/models`; the OAuth access token did not
  authenticate that same catalog endpoint. Secrets were read only in memory and
  sent to their intended official host.
- Catalog discovery returned Muse Spark Standard and Contributor text models,
  plus image and speech models. Discovery is not permission to route incompatible
  modalities or silently select Contributor models.
- Offline `muse schema generate-json-schema` exposed MSP stdio methods including
  `model/list` and `usage/read`. The latter returns last-observed subscription
  windows, not necessarily a live quota fetch. Unknown usage must remain unknown.
- The launcher identifies public client ID `1031625952748946`, device endpoint
  `https://auth.meta.com/oidc/device/authorization/` and token endpoint
  `https://auth.meta.com/oidc/device/token/`. Both accept URL-encoded forms.
- Direct Windows device approval and token exchange returned HTTP 200. The token
  response contained only `access_token` and `token_type: Bearer`: no refresh token
  and no expiry. This does not establish unlimited token lifetime.
- `POST https://api.meta.ai/muse-code/key` with the OAuth Bearer token and JSON `{}`
  returned HTTP 200 on both Linux and Windows. Anonymous access returned 401.
  The response contained `api_key`, `base_url: https://api.meta.ai/v1`, subscription
  eligibility and quota. The generated key authenticated the model catalog.
  No inference-key expiry was advertised. Repeated minting returned the same key
  in this observation; the adapter does not depend on that remaining true.
- Eligibility was `is_subs_active: true`, `require_payment: false`. The adapter
  requires these exact values before using the minted key. It neither buys a plan
  nor falls back to ordinary account API keys.
- `subs_usage.window` contained `used_percent`, `window_duration_mins: 300` and
  `resets_at`; `weekly` contained `used_percent` and `resets_at`. Reset values are
  Unix seconds, not milliseconds. The `tier` value is opaque, not a display name.
  Invalid or missing observations remain unknown rather than reporting zero.

Follow-up quota investigation on the same day: the current authenticated key
response omitted `subs_usage`, while returning `subs_tier_id` and the display field
`subs_tier_name`. Eligibility remained active. Plan display must therefore be
independent of quota-window availability. The adapter now validates the display
name without treating it as an opaque tier or inventing a remaining percentage.
Only allowlisted metadata was inspected; no additional inference was performed.

## Bounded live inference evidence

All calls used the generated inference key, `muse-spark-1.3` Standard,
`store: false`, synthetic content, and a 256 output-token ceiling. No repository
content or user conversations were sent. No CLI identity headers were forged.

1. A named forced function choice received HTTP 400. The upstream error stated
   that only automatic tool choice is supported.
2. Automatic tool choice produced a valid `add_numbers` call for 2 and 3, together
   with reasoning/message output. Usage: 593 input and 94 output tokens.
3. Replaying the full output and matching function result produced streamed text
   `5` and a completed response. Usage: 711 input (497 cached) and 24 output tokens.

The stream included a `response.subscription_usage` event. Only its event type
was inspected. Quota was subsequently verified through the key-mint response,
not inferred from that event; the adapter suppresses this private event on client
streams. Total successful reported usage was 1,304 input and 118 output tokens.
This is not an invoice or proof that the calls were covered by a subscription.

These tests establish narrow transport feasibility and direct Windows login, not
vendor support, long-term renewal behavior or a billing guarantee.

## Implemented boundary and remaining limits

The approved adapter exposes a separate OAuth-only `muse_code` provider. Every
login check/save requires a user click. Flow state is encrypted, owner-bound,
time-limited and leased against concurrent exchange. There is no background login
polling, CLI subprocess, callback listener or VPS service.

Account tokens authenticate only the mint endpoint. Model requests use only the
minted inference key. Eligibility is rechecked before dispatch; no undocumented
OAuth refresh grant or local token-expiry guess is introduced. A rejected session
requires reauthorization. This conservative check adds a bounded upstream request
per credential preparation; caching eligibility is deliberately not assumed safe.

Public model IDs use `muse-code/` (for example `muse-code/muse-spark-1.3`), preventing
automatic selection of pay-as-you-go Meta credentials for the same upstream model.
Native replay is sealed to its provider family and rejects mixed-family routes.
Contributor models require explicit selection; image/speech generation is excluded.
Only automatic tool choice is accepted, matching the authorized live observation.

Offline tests cover transport, replay, quota, imports, failure states and the UI.
They do not establish long-lived subscription behavior, upstream availability or
successful real inference through the finished gateway. Further model calls require
a fresh allowance. No Docker deployment or commit is authorized by this task.

## Meta API behavior, intentionally unchanged

The existing Meta Responses boundary permits forced/required/disabled tool choices,
whereas this live Muse-backed key accepted only automatic choice. The Muse adapter
therefore rejects other choices; Meta API-key behavior was not changed based on an
observation from a different authentication/subscription context.

## Quota follow-up: post-completion event — 2026-09-16

A separate one-call allowance was granted and consumed for this investigation.
Before the call, fresh authenticated key responses on both Linux and Windows
returned the active `Muse Code Power Usage` plan but omitted `subs_usage`.
The official CLI's `usage/read` schema describes last-observed usage, not an
independent live quota endpoint; that command also had no observation to return.

The single bounded request used Standard `muse-spark-1.3`, input `Reply only OK.`,
`max_output_tokens: 256`, `stream: true`, `store: false`, no tools and no retries.
It returned HTTP 200, reporting 11 input and 245 output tokens. The private event
arrived **after** `response.completed`, with this allowlisted structure:

```json
{
  "type": "response.subscription_usage",
  "subscription": {
    "tier": "<opaque tier>",
    "window": {"used_percent": 0, "window_duration_mins": 300, "resets_at": 1789568145},
    "weekly": {"used_percent": 0, "resets_at": 1789948800}
  }
}
```

Fresh key responses subsequently included both windows again. This establishes
that the earlier 100% observation was not necessarily fabricated, and that a
missing key-response field alone does not establish lack of quota support.
It does not establish an upstream guarantee about when observations are returned.

Polaris now consumes and validates this event before finalizing Muse streams,
including events after completion. It never forwards private subscription events
to API clients. Both normal dispatch paths and explicit model tests bind storage
to the selected credential's account/session. A narrow atomic patch updates only
subscription usage, preserving concurrent credential edits and refusing deleted,
replaced or reauthorized records and older observations. Storage failure is bounded
and cannot trigger a retry of a completed generation; cancellation still propagates.

Refreshing quota still performs a fresh key request, not inference. If that response
omits usage, the UI reports unavailable rather than substituting a saved percentage.
No further live inference is authorized or needed for the synthetic regressions.
