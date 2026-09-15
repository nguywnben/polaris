# Changelog

All notable user-facing changes are documented in this file. Polaris follows
[Semantic Versioning](https://semver.org/). Its version line restarted at `0.1.0-beta.1` after the
project-wide rename; earlier product tags remain below for release provenance. Breaking
changes are permitted throughout the Polaris `0.x` beta series.

## [Unreleased]

### Added

- Every provider now offers a JSON credential example beside the import heading,
  with provider-specific OAuth, API-key or Ollama connection fields and no copied secrets.
- Kiro browser sign-in follows the cockpit-tools portal/PKCE flow, with automatic
  callback completion and a manual callback-URL fallback for remote instances.
  AWS device login and API keys remain separate secondary options.
- GroqCloud, DeepSeek Platform, Mistral AI Studio and Cerebras Cloud API-key
  providers, with credential-specific endpoints, JSON/ZIP imports, chat model
  discovery, streaming/tool adapters, PNG logos and descriptions in 15 languages.
- Groq streaming usage/error metadata and Mistral reasoning chunks/tool IDs are
  adapted at the provider boundary. See the API-platform guide for reasoning limits.
- Complete contextual interface catalogs for all 15 supported languages, including exact
  provider authorization/import instructions and localized field hints.
- Regression checks for missing translations, interpolation variables, provider-copy fidelity,
  language switching, and nonblank normal-weight placeholders.
- Live setup-password checklist for length, character variety, blocked common passwords,
  and confirmation, grouped below both password fields and matching the server policy
  without imposing composition rules.

### Fixed

- Provider workspaces use consistent API-key actions, concise placeholders and
  import wording across old and new integrations. JSON examples sit beside the
  import heading instead of adding a competing action footer.
- Kiro device authorization presents a copyable code, sign-in action, expiry and
  localized cancellation. OAuth and API-key settings are grouped in one full-width
  advanced section while remaining bound to their own credential forms.
- Translation checks cover generated provider controls as well as static markup.
- Shared Google configuration saves and resets now emit correlated, redacted
  provider audit events through the same pipeline as other provider settings.
- Settings groups keep-alive with server connections, places inference timeout
  under Storage and Connections, and removes the duplicate routing summary.
  Independent columns stay compact while retention and backups remain full width.
- Light/dark changes apply the palette together instead of letting input and card
  hover transitions lag behind the page background. Normal interaction transitions remain enabled.
- Page-header actions share a consistent height and concise contextual labels.
  Identity refresh reports success or failure through toasts, without inline
  success messages or moving focus into fields; partial failures are not reported as success.
- Provider settings now have one owner: Code Assist and shared Google endpoints are in
  Providers; routing-wide stream conversion and retry credential switching are in Settings.
  Claude and xAI shared fields have a single editor, and Grok's OAuth inference endpoint
  is editable independently from SpaceXAI Console. Saved values and environment locks remain intact.
- Antigravity credit controls moved from Pool to Providers, with bounded account selection
  and confirmation. Offline imports distinguish stored credentials from verified credentials.
- Native Codex, Claude Code and Grok credential files are normalized with bounded,
  provider-specific validation. Foreign OAuth tokens are not sent to Google for email discovery.
- OAuth destination validation is consistent at save/runtime; Claude rate limits and server
  errors remain transient. Explicit NO_PROXY rules apply to shared HTTP and streaming clients.

- Global credential routing policy remains editable before any provider models exist and
  saves independently from virtual routes, with failed drafts retained for retry.
- Activity distinguishes an empty request history from filters with no matches. Connecting
  the runtime log stream no longer incorrectly reports that logs were cleared.
- Identity keeps all effective permissions in a keyboard-accessible disclosure and hides
  pagination when neither a previous nor a next page exists, shortening the mobile view.
- Shared light/dark styling keeps the Polaris logo visible and secondary/status text readable.
  Phone and tablet controls use consistent touch sizing; mobile navigation contains keyboard
  focus and disables background interaction until closed. Native dialog backdrops use the
  shared theme, and the dashboard's recent-activity heading no longer crowds its description.
- Opening a modal no longer automatically focuses its first input, textarea, or select.
  Focus starts on a non-editable surface while Tab, Shift+Tab, Escape, and return focus remain available.
- Toasts stay above native and custom modals without moving focus into form controls;
  validation keeps field error markers and normal keyboard navigation. Identity creation
  uses its Cancel action without a duplicate close icon.
- Late translations now override old English defaults in the live translator. Provider auto-copy
  no longer overwrites explicitly localized labels or caches placeholders in a previous language.
- Text inputs and textareas have contextual placeholders at normal weight; configured OAuth
  secret fields keep an appropriate hint after settings load.
- Session inventory uses Unix-anchored timestamps instead of displaying dates in 1970,
  while session expiration remains based on monotonic elapsed time.
- Activity tabs wrap on narrow screens instead of creating a horizontal scroller.
- OAuth result pages share the console's theme and auth styling, distinguish success/failure,
  and offer localized provider navigation. Manual callback flows keep their URL in the original
  tab; callback responses are not cached and do not send referrers.
- Identity uses a full-width permission list, content-sized readiness panels, flat identity/session
  records, and read-only roles for identities the current principal cannot edit. Empty status rows
  no longer reserve space; responsive controls retain confirmation and permission safeguards.
- Identity translations now reach the live language catalogs and English-source lookup,
  instead of leaving headings in English and exposing raw translation keys.
- Sidebar order follows provider setup, routing and quality, testing, access management,
  and operations; desktop and mobile use the same reading and keyboard order.
- Identity and sessions remains discoverable in the sidebar even when OIDC team access is
  disabled or unavailable, without enabling OIDC or changing management permissions.
- About uses labelled support-state counts and simpler responsive sections, with clear
  documentation/sponsor links and explicit empty support information. Failed loads no
  longer leave the build/support regions marked as busy.
- Provider catalog shows full descriptions with quieter capability labels and keeps
  pagination beside the catalog. Search and paging retain a keyboard entry point.
  Connection/import panels are more compact, provider introductions stay specific,
  and Antigravity settings use distinct English/Vietnamese guidance.
- Playground uses balanced responsive columns, simpler message editors, a contextual
  message counter, and visible output limits. Running requests show a pending submit
  label while keeping cancellation available; stale validation clears when the draft is valid again.
- Overview now uses compact, content-sized sections and contextual first-run guidance.
  Unsampled health metrics no longer imply zero latency or zero errors; unavailable health
  remains distinct from no traffic. Dashboard charts fit small screens and expose keyboard-accessible tooltips.
- Login now shares setup's secret visibility controls and visual rhythm, with concise
  localized guidance, a clear sign-in action, pending feedback, and duplicate-submit protection.
  Failed attempts retain the masked password for correction; successful sign-in clears it.
- Setup password fields stay locked until the current required setup token passes
  server verification. Reloading, editing the token, or a failed check locks them;
  stale responses cannot unlock fields after a token edit.
- Validation borders clear when a field is edited instead of retaining browser-owned
  invalid styling; invalid submissions still receive Polaris feedback.

- Replaced native browser validation popups with localized Polaris error toasts for
  static and dynamically created forms, preserving HTML constraints and invalid-field feedback.
- Form fields now highlight only under the pointer, not when their labels are hovered.
  Text-field labels no longer focus/open controls; accessible names, keyboard navigation,
  and checkbox/radio label activation are preserved. The root-key label no longer
  copies a secret, while direct clicks and Enter on the key still copy it.
- Failed setup checks retain the entered setup token so it can be corrected and retried.
- Setup checks now prompt for an empty setup token before sending a request and announce
  successful checks with a toast without moving focus to the password field. The inline
  guidance stays visible and updates to the current action after verification or token edits.
- Removed synthetic hidden `admin` usernames from console setup, sign-in, and password-change
  forms so password managers receive the actual password-only flow.

### Changed

- Simplified the first-run setup layout with compact installation checks and clearer password
  grouping. Added accessible, independently controlled visibility buttons inside all setup secret
  inputs, visible only while populated, with keyboard support and labels in all supported console
  languages.

## [0.1.0-beta.1] - 2026-09-14

### Added

- Added protocol-aware Node.js SDK examples to Playground alongside cURL and Python.
- Added automatic model-pricing synchronization with a validated last-known-good snapshot and
  manual `model_pricing.json` precedence, so newly priced models do not require a Polaris
  release while inference remains available during catalog outages.
- Added a 120-second release-blocking reliability profile for routine self-hosted releases while
  preserving the original ten-minute profile as an explicit optional soak.

### Changed

- Completed the breaking pre-release cutover to Polaris across the repository, containers,
  console, API keys, virtual model route, environment variables, headers, browser state,
  telemetry, backup formats, and cryptographic domains. No compatibility aliases are retained;
  see the [Polaris identifier contract](docs/migrations/polaris.md).
- Standardized locale-aware console metrics: high-level values at 10,000 and above now use
  compact notation with exact hover and assistive labels, while detailed views retain grouped
  full-precision values and small USD costs keep sub-cent precision.
- Rebalanced the supported product around one worker and one replica: SQLite remains the Core
  default, PostgreSQL and team OIDC remain Advanced opt-ins, and MongoDB remains Compatibility.
- Unified console spacing, advisory copy, empty support-tier rendering, responsive coverage, and
  keyboard smoke across all 11 destinations; only English and Vietnamese documentation is now
  maintainer-curated while all 15 console locale catalogs remain complete.
- Completed the project-owned Pydantic 2 configuration migration and made core lifecycle/storage
  fallback logs observable without exposing raw exception details.

### Removed

- Removed the unreachable Redis coordinated runtime, multi-replica HA lifecycle/operator/evidence,
  Kubernetes/Helm assets, Redis dependency, and their obsolete active runbook.
- Removed Redis acceleration and coordinated-only write branches from the MongoDB Compatibility
  backend, plus 13 stale community README snapshots that advertised retired deployment paths.

### Fixed

- Aligned dashboard usage windows to fixed browser-local clock boundaries and replaced relative
  timeline placeholders with actual localized timestamps. The one-day view now represents today
  from 00:00 through 23:00 instead of a rolling 24-hour interval, and tooltips identify one bucket
  timestamp rather than displaying an interval.
- Corrected production usage accounting across retries and streaming: the dashboard now labels
  provider attempts explicitly, recovered failovers keep the logical request successful, partial
  streams remain failures, cumulative usage chunks are merged, and token totals no longer count
  cache reads twice. Anthropic cache writes now use their distinct price when available, while the
  dashboard exposes incomplete provider-usage coverage instead of presenting missing usage as zero.
- Restored the frozen R1 API compatibility surface and strengthened default SQLite startup so
  optional database drivers and external services are not loaded unless explicitly selected.

## [1.5.0] - 2026-09-12

### Added

- Added a canonical storage support/recovery contract that distinguishes SQLite Core, PostgreSQL
  Advanced, and MongoDB Compatibility operation, including explicit outage and migration limits.
- Added schema-derived Settings state, validated About build/support facts, permanent update and
  recovery entry points, optional Team-access guidance, and complete English/Vietnamese product
  copy with compatibility-locale fallbacks.
- Added selectable cURL, Python SDK, and Node.js SDK quickstarts for every supported Access protocol,
  using visible virtual-key placeholders only.
- Added one shared Activity investigation workflow for request traces, audit/security events, and
  bounded runtime logs, including common filters, request-ID pivots from Dashboard and detail
  views, session-only correlation state, and a 16 MiB redacted raw-log download ceiling.
- Added restrictive per-virtual-key and per-request compression controls. Keys can inherit or
  disable the global policy through an additive revision-checked management endpoint, while
  authenticated requests can use `x-polaris-compression: off`; neither can weaken global policy.
- Added a versioned adversarial AI Quality corpus, deterministic property matrix, and one successful
  HTTP request for every advertised public protocol against bounded deterministic upstreams.
- Added authenticated, bounded routing-health diagnostics with actionable eligibility, capacity,
  cooldown, and recovery reasons while excluding credential filenames and request identifiers.
- Added a versioned cross-protocol contract and shared golden corpora for OpenAI Chat, OpenAI
  Responses, Anthropic Messages, Gemini, and Vertex text, images, system instructions, tools,
  structured output, reasoning, usage, finish reasons, and native errors.
- Added a versioned safe diagnostic contract for credential connection tests with consistent
  categories, remediation, retry guidance, bounded provider status, and deterministic coverage for
  all nine advertised provider/authentication variants.
- Added a versioned provider/auth capability matrix for all nine advertised variants, including
  lifecycle actions, discovery, OAuth refresh, quota, and normalized ingress protocols; the
  credential console now derives valid card and mixed-selection actions from the same contract.
- Added versioned, passphrase-encrypted portable SQLite backup with dry-run validation, explicit
  conflict policy, automatic encrypted pre-restore snapshots, transactional replacement and
  rollback, plus a separate non-restorable sanitized inventory export.
- Added a dry-run-first Compose updater that resolves immutable image IDs, creates an encrypted
  host recovery point, verifies `/ready`, and restores both the previous image and state snapshot
  after a failed update.
- Added one typed configuration schema for startup validation, Settings metadata, environment
  ownership, restart requirements, `.env`/Compose parity checks, and a generated operator reference.
- Added a localized Audit surface under Observability with safe category filters, cursor
  pagination, redacted event details, request-ID pivots, confirmed retention controls, and
  bounded JSONL/CSV export.
- Added optional OIDC team login with Authorization Code + PKCE,
  exact issuer/subject identities, explicit non-owner group-to-role mappings, and revocable
  sessions bound to identity and policy authorization revisions.
- Added selected-backend durable usage and cost repositories for SQLite, PostgreSQL, and
  transaction-capable MongoDB, including idempotent hard-budget reservation journals, restart-safe
  settlement, read-only verified legacy SQLite import, and bounded ledger operation metrics.
- Added Redis coordination semantic primitives, opt-in isolated live parity evidence, and bounded
  coordination operation metrics. The standalone in-memory default and runtime selection remain
  unchanged; this release does not activate HA Redis operation.
- Added fenced, bounded coordination semantics for opaque management sessions, authentication
  attempt admission, and one-time OIDC transactions across the in-memory and Redis state stores.
  Session and OIDC payloads remain authenticated and encrypted; live Redis parity is opt-in.
- Added inactive, fenced coordination for credential leases and cooldowns, quota transitions,
  governance invalidation, and exact-cache metadata, with opaque HMAC identifiers, fixed-cardinality
  telemetry, bounded reference evidence, and opt-in Redis parity. Response content stays local.
- Added a fail-closed HA runtime lifecycle with durable/shared namespace binding, coordinated
  dependency readiness, dry-run-first drain/epoch/reconcile/rollback operations, deployment guards,
  low-cardinality alerts, and an operator runbook. No coordinated topology is activated.
- Added a reproducible synthetic HA semantics harness and an explicit activation-disposition record
  that cannot be used as production or multi-replica evidence.
- Added storage-owned atomic credential-pool mutation plans for SQLite, PostgreSQL, and MongoDB, and
  separate encrypted 256-entry admission domains for credential batch previews and idempotent
  results.
- Added bounded, resumable quota-state reconciliation with dry-run/apply operation, opaque progress
  cursors, v1 disposal checks, and authoritative readiness confirmation.

### Changed

- Standardized every application SQLite connection on foreign-key enforcement and a bounded
  five-second writer wait while keeping the production topology at one worker and one replica.

- System configuration responses now redact every reusable schema secret and report only configured
  state; blank secret fields preserve stored values, environment-owned controls are not submitted,
  and all 20 controls expose their live/restart/read-only behavior.
- Preserved the pre-R1 virtual-key edit contract while retaining optimistic concurrency: the console
  sends `expected_revision`, legacy PATCH clients may omit it, and new rotate/revoke operations
  continue to require it.
- The legacy `/logs` route now opens Runtime logs instead of Request traces, matching its name;
  `/activity` remains the primary request-trace entry and `/audit` remains an audit compatibility
  link.
- Reorganized the self-hosted console around one daily workflow: request traces, audit/security
  events, and runtime logs now share an accessible Activity page; Team access is conditional,
  advanced and compatibility settings are collapsed, legacy `/audit` and `/logs` URLs continue to
  work, and mobile navigation now traps no hidden focus and restores focus on Escape.
- Context compression now estimates deeply nested payloads without recursion, fails open to the
  original request on estimation or invariant failure, preserves protected structures, and records
  bounded before/after estimates and reasons. Primary providers resolve compression once and Vertex
  anonymous now follows the same policy for streaming and non-streaming requests.
- Quality preview and runtime now agree that compression begins only after the configured threshold
  is exceeded, and weak-password guidance is localized across all supported console languages.
- Unified balanced, priority, weighted, least-latency, and lowest-cost selection under the runtime
  smart router; seeded fixtures are reproducible, repeated failures use bounded increasing
  cooldowns, and unused conflicting legacy selectors were removed.
- Public streaming now closes nested provider resources on disconnect, suppresses retries after
  model output begins, requires terminal events before success accounting, preserves heartbeat and
  split UTF-8 framing, bounds frame/aggregation memory, and settles quota and request traces once.
- Public inference request models now reject unknown or untranslatable semantics with native
  protocol errors instead of silently dropping fields; translated responses preserve signed
  reasoning, cached/reasoning token accounting, and incomplete/safety finish states.
- Credential model tests now have one cancelable 30-second operation deadline; raw upstream bodies
  and exception text are no longer returned or persisted, while the console presents actionable
  limited/failure states through labels completed across all 15 locales.
- Simplified the default Docker Compose deployment to common standalone controls and one durable
  named volume; optional storage, identity, routing, guardrail, cache, and telemetry controls now
  require the explicit advanced override, and CI verifies state across container recreation.
- Invalid documented environment values now fail startup with field-specific remediation instead
  of relying on scattered fallback behavior; unknown `POLARIS_*` controls emit spelling warnings.
- System Settings validation and field ownership are schema-derived, removing the duplicated route
  whitelist and per-field validation block while keeping provider, quality, and access ownership
  separate.
- Hard daily and monthly virtual-key budgets now reserve and settle against the selected durable
  ledger before provider admission. RPM and TPM remain single-process until the Redis coordination
  phase, so worker and replica limits are unchanged.
- Successful provider responses with uncertain ledger settlement retain a conservative durable
  estimate instead of being released as zero spend. Readiness now actively probes the selected
  usage ledger, and compatibility reports fail closed at a bounded row ceiling.
- Local-owner login, recovery, and OIDC-start throttles now reserve attempts atomically before
  protected work, while session issue/resolve/rotate/revoke and OIDC proof consumption use one
  typed coordination boundary without changing the standalone default.
- Credential selection now enforces a 100-candidate ceiling and shared lease/cooldown evidence;
  exact-cache hits require matching coordinated generation and digest evidence. Runtime Redis
  selection and multi-replica operation remain gated.
- Runtime coordination consumers now receive one lifecycle-owned service. Primary conversation
  steps use HMAC-addressed fenced CAS state, and coordinated MongoDB deployments cannot reuse the
  coordination Redis namespace for the legacy cache.
- Credential identity admission and deduplication now use one coherent durable snapshot and commit;
  batch capacity exhaustion returns HTTP 429 with retry guidance while coordination outage returns
  a typed HTTP 503 response.
- Redis quota admission now uses 61 fixed second buckets and one directly addressed lifecycle
  record instead of work proportional to as many as 100,000 retained records. Redis owns RPM/TPM
  only; the durable usage ledger is the sole daily/monthly monetary-budget authority.

### Fixed

- Rejected corrupt SQLite state before startup writes and made additive startup migration atomic so
  a later initialization failure cannot leave a partially upgraded database.
- Preserved upgrades from populated pre-R1 SQLite credential stores by adding timestamp columns in
  an SQLite-compatible additive step, backfilling existing rows, and timestamping new writes
  explicitly. A versioned compatibility guard now detects accidental SDK, console, config, or
  stored-schema contract breaks before release. Runtime shutdown also restores a fresh standalone
  response-cache coordination boundary instead of leaving the cache attached to a closed store.

- Hardened OIDC outage handling with bounded shared discovery backoff, removed implicit owner
  fallback from verified-session authorization, and invalidated older sessions after a failed
  claim-role re-evaluation.
- Hardened inactive Redis coordination primitives against partial epoch loss, large-token
  precision loss, expired replay reuse, partial cleanup, malformed quota chronology, and
  cancellation during client shutdown. Coordinated runtime activation remains gated.
- Prevented false-valued injected coordination backends from triggering local OIDC fallback and
  made session/OIDC adapters preserve the exact validated fencing epoch for later HA activation.
- Prevented unknown routing CAS/invalidation outcomes from being replayed with a new operation ID,
  avoiding duplicate leases or duplicate generation increments after a committed transport timeout.
- Closed lifecycle teardown leakage into later credential-routing work and corrected localization
  audits so supplemental catalogs, HTML void elements, protocol values, and backend management
  errors cannot escape coverage.
- Prevented cross-replica duplicate credential identity admission, batch-domain capacity drift,
  stale standalone MongoDB routing cache after a pool mutation, and ambiguous preview coordination
  failures.
- Prevented v1/corrupt/expiring or incompletely reconciled quota state from entering a ready epoch,
  and made quota reconciliation cursors, page bounds, identifiers, and pipeline replies fail closed.
- Corrected the synthetic HA evidence output so it no longer reports provider, batch, pool, or
  quota blockers that the completed semantic checks already resolved. Redis and multi-replica
  operation remain experimental and outside the supported release topology.

## [1.4.0] - 2026-08-21

### Added

- Added virtual API keys with per-key daily and monthly USD budgets, requests-per-minute and tokens-per-minute limits, expiry, and glob model allowlists, managed through the `/api/virtual-keys` panel API. Secrets are stored as SHA-256 hashes and shown exactly once at creation time.
- Added a per-call USD cost ledger computed from a maintained model pricing table, with operator overrides through `model_pricing.json` in the credentials directory and cost aggregates in the dashboard usage API.
- Added an optional pre-call guardrails pipeline that rejects prompt-injection attempts and blocked keywords with HTTP 400 and masks emails, card numbers, and API keys from outbound request text.
- Added an optional exact-match response cache for deterministic (temperature 0) non-streaming requests with configurable TTL and capacity.
- Added `weighted`, `least_latency`, and `lowest_cost` routing strategies alongside the existing `balanced` and `priority` policies, selectable from the settings page in all 15 console languages.
- Added a Prometheus `GET /metrics` endpoint with per-provider request, token, cost, and latency counters plus cache statistics, protected by an optional `METRICS_TOKEN` bearer requirement.
- Added optional Langfuse trace export that emits model, provider, token counts, and latency for successful calls without sending prompt or response bodies.
- Added dashboard analytics: a provider health matrix, token distribution breakdown, hourly traffic timeline, and pagination for the usage tables.
- Added a Helm chart at `deploy/helm/polaris` with persistent storage, probes, secret management, optional Ingress, and an optional Prometheus ServiceMonitor.

### Changed

- Usage records now attribute every call to its originating API key and store the estimated call cost for budget enforcement and FinOps reporting.
- Docker Compose now forwards routing strategy, response cache, guardrails, metrics, and Langfuse configuration from the environment.

## [1.3.2] - 2026-08-21

### Fixed

- Replaced the generic localization fallback that could appear as credential-card provider names and action labels in non-English interfaces.
- Localized credential-card provider labels, concise actions, status badges, and explanatory tooltips across every supported console language.

## [1.3.1] - 2026-08-21

### Added

- Added a conditional update guide in the About page that appears only when a newer Polaris release is available.
- Added a production-oriented update and rollback guide for pinned Docker and Docker Compose deployments.

### Changed

- Completed the management console localization across the supported languages, including API messages and locale-aware initial selection.
- Refined Vietnamese navigation terminology so the credential workspace remains concise and consistent with the rest of the console.

## [1.3.0] - 2026-08-20

### Added

- Added Claude Code OAuth credentials, Claude Platform API-key credentials, and Ollama endpoint credentials with provider-native discovery, validation, routing, and JSON/ZIP portability.
- Added Gemini CLI OAuth credentials with PKCE authorization and Cloud Code-compatible routing for supported Gemini CLI accounts.
- Added provider-specific assets, catalog entries, documentation links, and credential workspaces for the expanded provider catalog.

### Changed

- Strengthened credential-aware routing, failure classification, request correlation, and outbound HTTP client reuse for more predictable fallback behavior under provider failures.
- Improved provider catalog navigation and layout so the growing collection of connection types remains searchable and usable across desktop and mobile views.
- Standardized runtime dependency auditing and CI lockfile validation around immutable, hash-locked production dependencies.

### Fixed

- Kept provider routing and credential diagnostics scoped to each provider implementation instead of applying Google Antigravity assumptions to other credential types.
- Formatted backend modules consistently with the repository Ruff policy to keep local and CI validation aligned.

## [1.2.1] - 2026-07-24

### Changed

- Optimized provider model discovery by sampling representative credential capabilities instead of querying every credential in large pools.
- Preserved a unified model catalog while labeling each model with its specific provider product and deduplicating only within that provider.
- Expanded fixed-model response normalization across OpenAI Chat Completions, Responses, Anthropic Messages, and Google GenAI request surfaces.
- Separated removed credentials from the active 24-hour request breakdown while retaining their historical usage totals.

### Fixed

- Prevented provider selection from routing fixed-model requests through credentials whose discovered catalogs do not support the requested model.
- Kept provider-specific model support independent when different providers expose the same model identifier.
- Removed misleading Grok Build tier badges when upstream account metadata does not represent a subscription plan.

## [1.2.0] - 2026-07-19

### Added

- Added Codex device OAuth, account-scoped model discovery, token refresh, Responses transport translation, and JSON/ZIP credential import.
- Added OpenAI Platform API-key validation, model discovery, Chat Completions routing, and JSON/ZIP credential import.
- Added provider-native quota, plan, and subscription diagnostics for Codex, Grok Build, Google Antigravity, and supported API-key credentials.
- Added provider-specific credential verification and model testing across every supported credential type.

### Changed

- Reorganized the Providers page as a searchable, responsive product catalog with separate credential workspaces and settings for every connection type.
- Renamed xAI Console to SpaceXAI Console and standardized Codex and Grok Build product naming and assets throughout the console.
- Expanded credential cards with truthful authentication, subscription, health, quota, and model-capability information.

### Fixed

- Routed verification and model tests through each credential's native provider implementation instead of the Google Antigravity transport.
- Refreshed expired Codex access tokens once before retrying verification, quota, and model-test requests.
- Kept provider diagnostics and badges aligned with the actual credential payload instead of inferring unsupported account properties.

## [1.1.4] - 2026-07-19

### Added

- Added deployment-aware Google Antigravity model discovery and persisted per-credential model catalogs during verification.
- Added Grok Build OAuth account billing visibility with monthly credits, weekly usage, reset times, and a conservative remaining-quota badge.

### Changed

- Standardized the Grok OAuth product name as Grok Build across provider contracts, imports, usage reporting, documentation, and the management console.

### Fixed

- Restricted fixed and virtual model routing to credentials whose discovered catalog supports the selected model while preserving fallback through other eligible credentials and providers.
- Kept unavailable-model memory scoped to the credential and provider route that actually failed, so one account cannot incorrectly suppress another account's valid model deployment.

## [1.1.3] - 2026-07-17

### Added

- Added consistent skeleton loading feedback for credential, model-catalog, dashboard, and configuration data.

### Changed

- Split the management console and provider-settings backend into focused, independently maintained modules without changing public routes.
- Removed Anime.js and its interface motion so navigation, dialogs, notifications, and mobile controls respond immediately with a smaller frontend payload.

### Fixed

- Reduced page-switching jitter by caching recently loaded tab data, deduplicating concurrent loads, and preserving rendered content during background refreshes.
- Stabilized console layout dimensions and footer placement across desktop and mobile navigation.

## [1.1.2] - 2026-07-16

### Changed

- Distinguished Grok OAuth accounts from SpaceXAI Console API keys throughout credential storage, usage reporting, imports, and the management console.
- Prioritized credentials that explicitly declare support for the requested model before routes whose support can only be inferred.

### Fixed

- Retried fixed-model requests through alternate compatible credentials and providers after an upstream `404` without changing the requested model.
- Kept persistent provider-model blacklisting exclusive to virtual `polaris` fallback while applying short credential-model cooldowns to failed fixed routes.

## [1.1.1] - 2026-07-15

### Changed

- Replaced Grok OAuth callback URL entry with the authorization code shown by xAI while preserving PKCE session validation.

## [1.1.0] - 2026-07-15

### Added

- Added Grok OAuth and SpaceXAI Console API-key credentials with model discovery, token refresh, pool backup restoration, and provider-aware routing.
- Added Grok request and response translation for text, image input, function tools, reasoning content, streaming, and provider-reported token usage.

### Fixed

- Scoped account deduplication by provider so OAuth accounts that share an email address across different providers remain independent.

## [1.0.0] - 2026-07-13

### Added

- Added provider-aware model discovery, credential model testing, virtual `polaris` routing, and a manageable blacklist for unavailable virtual-model routes.
- Added Google AI Studio API-key credentials, JSON/ZIP import, model catalog discovery, credential backup restoration, and provider-specific pool views.
- Added stable OpenAI, Anthropic, and Google GenAI error envelopes across authentication, validation, upstream, and pre-stream failures.
- Added bounded request identifiers through `X-Request-ID` for client-side correlation.
- Added a configurable global request-body ceiling for fixed-length and chunked SDK requests.
- Added release-based update discovery that compares semantic versions against the latest published GitHub Release.
- Added first-class architecture, upgrade, security, contribution, and release-checklist documentation for the stable series.

### Changed

- Declared the SDK-compatible routes and canonical `/api/credentials` management routes as the 1.x compatibility baseline.
- Hardened configuration, credential-manager, and storage initialization so partial failures stop startup instead of exposing a split or misleading runtime state.
- Made explicit MongoDB or PostgreSQL configuration fail closed when unavailable, and rejected simultaneous external database selections.
- Moved default-branch container builds to the `edge` channel; `latest` now advances only for verified stable version tags.
- Pinned the official Python container base image by digest while retaining Dependabot updates.
- Removed inline browser event handlers and tightened the management console content-security policy.
- Improved first-run authentication state, bounded login-rate-limit memory, same-origin session enforcement, provider-error redaction, and shutdown cleanup.

### Removed

- Removed the beta `/api/creds` route aliases; integrations must use `/api/credentials`.
- Removed the ambiguous `PASSWORD`, `CLIENT_ID`, `CLIENT_SECRET`, `API_URL`, and other beta environment aliases in favor of the documented canonical names.

### Fixed

- Standardized "no credentials available" as `503 Service Unavailable` so SDK retry behavior is correct.
- Prevented startup races when initializing configuration, credential managers, and storage adapters.
- Prevented unauthenticated console startup probes from generating expected `401` errors in the browser console.

## [0.2.0-beta] - 2026-07-12

### Added

- Added secure remote first-run setup with an ephemeral or configured bootstrap token.
- Added a hash-locked production dependency set and reusable runtime/container smoke tests.
- Added canonical `/api/credentials` management routes while retaining hidden `/api/creds` aliases for beta migration.

### Changed

- Standardized internal module names, repository tooling, deployment defaults, and contributor documentation.
- Expanded CI across supported Python versions with linting, formatting, dependency auditing, route contracts, and runtime smoke tests.
- Gated Docker Hub and GHCR publication on successful verification and container smoke tests.
- Split the management console, authentication, and credential-management monoliths along behavioral boundaries.
- Migrated MongoDB storage from deprecated Motor to the official PyMongo Async API.
- Limited published container images to the fully verified `linux/amd64` provider stack.
- Declared single-worker operation as the supported runtime model until distributed reservations and usage aggregation are implemented.

### Fixed

- Removed an internal shortcut that intercepted a real `Hi` model prompt as a health check.
- Restricted forwarding-header trust to explicitly configured reverse-proxy deployments.
- Bounded provider credential uploads and ZIP extraction to prevent oversized or compressed archive exhaustion.
- Rejected unsafe credential filenames and expanded log redaction for connection URIs and provider tokens.
- Removed duplicate Preview-channel creation requests.
- Removed query-string authentication from the runtime-log WebSocket and enforced same-origin handshakes.
- Prevented release tags from generating invalid branch-prefixed container tags.
- Gated GitHub Releases on verified container publication and sourced release notes from this changelog.

## [0.1.0-beta] - 2026-07-08

### Added

- SDK-compatible OpenAI, Anthropic, and Google GenAI routes.
- Provider credential pool, virtual model routing, context optimization, usage visibility, and the management console.
- Docker Hub and GitHub Container Registry publishing.

[Unreleased]: https://github.com/nguywnben/polaris/compare/v0.1.0-beta.1...HEAD
[0.1.0-beta.1]: https://github.com/nguywnben/polaris/compare/v1.4.0...v0.1.0-beta.1
[1.5.0]: https://github.com/nguywnben/polaris/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/nguywnben/polaris/compare/v1.3.2...v1.4.0
[1.3.2]: https://github.com/nguywnben/polaris/compare/v1.3.1...v1.3.2
[1.3.1]: https://github.com/nguywnben/polaris/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/nguywnben/polaris/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/nguywnben/polaris/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/nguywnben/polaris/compare/v1.1.4...v1.2.0
[1.1.4]: https://github.com/nguywnben/polaris/compare/v1.1.3...v1.1.4
[1.1.3]: https://github.com/nguywnben/polaris/compare/v1.1.2...v1.1.3
[1.1.2]: https://github.com/nguywnben/polaris/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/nguywnben/polaris/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/nguywnben/polaris/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/nguywnben/polaris/compare/v0.2.0-beta...v1.0.0
[0.2.0-beta]: https://github.com/nguywnben/polaris/compare/v0.1.0-beta...v0.2.0-beta
[0.1.0-beta]: https://github.com/nguywnben/polaris/releases/tag/v0.1.0-beta
