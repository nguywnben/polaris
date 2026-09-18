# Muse Code implementation verification — 2026-09-16

## Outcome and use

Muse Code is a separate OAuth provider, bringing the console to 23 workspaces.
No Linux CLI, subprocess bridge or VPS is needed by this adapter.

1. Open **Providers → Muse Code → Get sign-in link**.
2. Open/copy the link and approve its device code with Meta.
3. Return to Polaris and choose **Save credential**. Checks happen only on clicks;
   there is no background polling or automatic navigation/completion.
4. In the credential pool, inspect the discovered `muse-code/` models and explicitly
   test the model you intend to use. A connection test performs inference and may
   consume your allowance. Catalog discovery alone does not verify inference access.

The Windows approval during research was a protocol probe, not an import into the
user's Polaris pool. Sign in through the finished provider workspace to save it.
Native CLI OAuth JSON and Polaris JSON/ZIP imports are supported. Imported catalog
and quota claims are discarded; no real secrets appear in sample files.

## Verification executed

- Direct Windows device authorization, user approval, token exchange, key minting
  and catalog access: successful HTTP responses, no CLI dependency. Probe secrets
  were not persisted in the local pool or committed.
- Core regression: **2,181 tests, OK, 22 skipped**. These skips are exactly 12
  PostgreSQL and 10 MongoDB live tests whose optional connection URIs are unset.
  No core-path skip or new suppression was added.
- Final Muse-specific suite: **56 tests, OK**, including the last fixes made after
  the full run loaded its modules. Final Meta/Muse protocol slice: **52 tests, OK**.
- The 102-test provider/import/management slice passed before the last two protocol
  tests were added; those protocol changes passed the 52-test slice above.
- Fast quality gate: lint, formatting, bytecode, test manifest, JavaScript/YAML/
  shell syntax and whitespace passed. Windows sandbox blocked Bash's signal pipe;
  the same local gate passed with the required process permission.
- Locale audits: all **1,358 referenced frontend keys** covered in all 15 locales;
  static HTML and backend management-message audits passed.
- Isolated Muse Playwright smoke: manual start/check/save/restart, no polling, safe
  authorization URL, offline import, translated results, all 15 locales, widths
  320/360/768/1024/1440 and light/dark themes. No horizontal overflow or page errors.
- Existing provider workspace smoke passed, including all 23 JSON examples.
  Extended-provider smoke passed: 23 catalog cards, 13 API forms, 130 layout/theme
  cases and 39 real isolated JSON/ZIP/rejected imports. External traffic was blocked.
- Four full-page Muse screenshots (desktop/mobile, light/dark) were visually
  inspected. Existing provider components and spacing rules were reused; no new
  visual system, framework or provider settings on unrelated pages were introduced.
- Muse precedes Meta Model API. Its authorization URL reuses the Antigravity/Kiro
  link-card pattern; separate Cancel/Open page buttons and the protocol-separation
  notice are absent. The Contributor onboarding notice is also removed at the user's request;
  model-selection safeguards and upstream data handling are unchanged. The updated smoke
  covers this layout and replacement of a pending flow by requesting a new link.
- Catalog cards contain only their connection method badge, including the static
  fallback. Muse's compact device code and advanced credential-name field are
  covered by the browser smoke, including the actual start-request payload and
  all 15 translations. The endpoints and authentication protocol are unchanged.
- Standard-library `trace` statement coverage on the five new backend modules:
  `muse_oauth` 98.8%, `muse_device_login` 89.7%, `muse_code` 93.2%, panel routes 100%,
  localized messages 100%. This is statement coverage, not branch coverage or a
  claim about total repository coverage. Reports remain under ignored `temp/`.

## Review and fixes

Self-review only, as requested; no subagent or independent-model review claimed.

- Fixed trusted origins, TLS validation, no credential-bearing redirects, bounded
  response sizes/timeouts, encrypted owner-bound flow state and lease deadlines.
- No raw account tokens in browser responses, inference headers or activity logs.
  Native reasoning/prompt-bearing events remain excluded from raw stream logs.
- Re-minting checks subscription eligibility and account identity; a failed save
  fails closed in dispatch and management verification, not a false success.
- Catalog management uses the freshly minted key once rather than minting twice;
  expired-account edits return actionable sanitized errors instead of an unhandled
  server exception. Quota reports unknown data as unknown and uses Unix seconds.
- `muse-code/` isolates subscription credentials from raw Meta API model IDs. Native
  replay is provider-bound, rejects mixed billing families and retains tool history.
- Muse-specific paths now skip Google-only request defaults and use the established
  Meta compatibility adapter at Messages ingress. Explicit unsupported options fail
  rather than being silently removed. Only automatic tool choice is supported.
- The private `response.subscription_usage` event is not forwarded to API clients.
  Quota is independently validated from the authenticated mint response.

Large-file assessment: shared primary routing, credential management/panel and i18n
files already exceed the preferred size. New OAuth transport, flow orchestration,
credential validation and translations live in focused Muse modules. Changes to
the shared files are narrow dispatch, permission, localization or persistence hooks;
a broad unrelated rewrite would expand the approved scope and regression risk.

## Limits and deployment status

No new live model call was made during implementation. Earlier three authorized
probes establish narrow transport feasibility, not full production certification.
The final gateway flow uses synthetic upstream transport tests; live end-to-end
inference through Polaris still requires a fresh user allowance.

Meta's documented CLI/subscription boundary and potential protocol changes remain
important. No vendor approval, billing guarantee, indefinite session lifetime or
undocumented token-refresh support is claimed. Rejected sessions require login.
Eligibility is conservatively checked before credential dispatch, adding an upstream
mint request rather than assuming a safe undocumented caching interval.

No new package, schema, purchase, Docker deployment, git commit or push was made.
Existing Meta API-key behavior is preserved. Container-release and optional external
database verification are not part of this local implementation verdict.

## Local preview startup follow-up

The native preview initially failed closed while verifying a pre-R2 SQLite usage
import. All 821 legacy events matched their stored historical fields, but R2's
added `cache_creation_tokens` and inferred `usage_reported` fields changed the
serialized checksum. This was a compatibility failure, not evidence of missing
usage records.

The importer now recognizes both historical checkpoint encodings and compares
the reporting flag using its legacy representation (the legacy source never had
that flag). Stored usage payloads are not rewritten. Historical token/cost fields,
cache-creation counts, source stability, target contents and atomic checkpoint
updates remain verified. Regression tests cover replay, incremental imports,
credential retirement and rejection of altered source/target data.

Before restarting, both local SQLite databases were backed up with SQLite's online
backup API and passed `quick_check`. The native preview runs on loopback port 4284;
the existing Docker service on 4283 is unchanged. HTTP health and the providers
page return 200, the served console bundle contains the Muse OAuth panel, and all
821 historical usage payloads remain byte-for-byte unchanged after startup.

Verification: the focused SQLite suite passed 23 tests; the full core suite
completed 2,189 tests successfully with 22 existing optional-backend skips.
Ruff lint/format and diff whitespace checks passed for the startup fix.

## Fresh subscription observation follow-up

The separate one-call quota investigation is recorded in the research document.
This implementation makes no additional live inference requests. Regression tests
first failed for missing observation capture and route wiring, then passed after
the fix. The completed generation is not retried for a metadata write failure.

- 80 focused Muse tests pass, including private quota after `response.completed`,
  malformed/no metadata, last-valid event selection, cancellation, sanitized write
  failure, and isolation from Meta API-key credentials.
- The core suite completed 2,215 tests in 330.6 seconds with 22 existing optional
  skips. Five additional edge/storage tests added during that run are included in
  the subsequent passing 80-test focused run, not in the earlier core count.
- Dispatch regressions cover native Responses, collected non-streaming and the
  explicit credential model test. Refresh with omitted quota retains the plan,
  returns unavailable, never falls back to old windows and never calls inference.
- A real temporary SQLite test verifies quota persistence while retaining the
  credential label and disabled state. Planner tests cover account/session changes,
  deletion, concurrent key rotation and observation ordering.
- Standard-library statement tracing on the two integration/regression modules
  measured 95.8% for the new `core.muse_quota` module (not branch or repository
  coverage). Ruff lint/format and diff whitespace checks pass.
- Credentials browser smoke passes synthetic identity, four-column sections,
  provider-scoped operations, capability-aware dialogs, keyboard focus, 15 locales,
  and 320–1920px light/dark layouts.

Self-review covered correctness, architecture, security, cancellation and bounded
I/O. No subagent review is claimed. The already-large primary router and panel
receive only narrow callback hooks; atomic metadata persistence is isolated in
the new focused module instead of extending their storage logic. No dependency,
schema, UI copy, billing, login, Docker, commit or push change is required.

The native preview was restarted on loopback port 4284 after verification;
`/ready` and `/credentials` both returned HTTP 200. Docker 4283 was untouched.
