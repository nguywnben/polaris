# Polaris 1.0.0 release-readiness audit

## Baseline (before changes)

- Date: 2026-09-18. Source: `develop` / `1596650`. No initial tracked changes.
- Runtime/Compose/install release: `0.1.0-beta.1`; changelog records a version restart
  after the product rename. Legacy tags `v1.0.0` through `v1.4.0` still exist.
- Owner confirmed preparation of the new version line for `1.0.0`, not publication.
  Existing tag collision needs an explicit owner decision; no tag is changed here.
- Earlier R1/R2 evidence references older commits and nine provider variants; current
  catalog documentation has 23 workspaces and six OAuth families. September 17 review
  explicitly left container, Linux CI and final-source reliability evidence outstanding.
- Existing maintained inventory: `product-surface-inventory.json` (13 page fragments,
  11 navigation destinations, 20 route groups); auth/setup/callback are additional surfaces.
  Usage belongs to Dashboard, audit/runtime logs to Activity, backup/restore to Settings.
- Initial fast gate: backend/tool lint passed; format failed in
  `test_control_panel_assets.py`, `test_credential_fleet_query.py`,
  `tools/design_consistency_smoke.py`. No threshold or assertion change is needed.
- Git reports inaccessible old `pytest-cache-files-*` directories during untracked
  traversal. These are not inspected, deleted or treated as source changes.

## Capability map and dispositions

| Group | Preserve / authority | Finding or verification still required | Class |
| --- | --- | --- | --- |
| release-versioning | `backend/app_version.py`, Compose, immutable tag history | beta defaults versus 1.0.0 target; legacy tag collision; stale resume metadata | Release risk / confusing |
| console-ux | no-build fragments/bundles; 32px controls, 36px navigation, 4 credential columns when space permits | rerun current populated/empty/auth/modal/state/theme/keyboard matrices after recent changes | Verification pending, not assumed defect |
| core-business-logic | request lifecycle, one reservation across retries, output-aware retry boundary | full current tests for settlement/cancel/expiry/idempotency | Preserve, verification pending |
| api-contracts | frozen compatibility fixture; native error envelopes, bounded request IDs | current OpenAPI/permission inventory and protocol corpus | Preserve, verification pending |
| providers-and-credentials | 23 workspaces; registry capabilities intersect permissions; provider-specific quota facts | reference comparison and deterministic failure-coverage gaps; no live certification | Preserve / evidence limits |
| routing-and-models | authoritative credential catalogs; five strategies; credential-scoped negative routes | strategy/fallback/cooldown/disabled/unknown-model tests | Preserve, verification pending |
| storage-and-recovery | SQLite Core, PG Advanced, Mongo Compatibility; encrypted SQLite backups | fresh/restart/restore/rollback and optional-boundary checks | Release evidence pending |
| security-and-identity | remote setup token is operator-configured and never printed; least privilege | `SECURITY.md` incorrectly says printed bootstrap token; browser harness inherits host env | Confirmed docs bug / isolation risk to inspect |
| observability-and-operations | bounded content-free traces/audit, opt-in exporters, unavailable distinct from zero | usage/cost/missing usage/cancellation/exporter-off checks | Preserve, verification pending |
| localization-and-documentation | 15 README languages and UI catalogs; EN/VI semantic review | active spec still calls all-locale work deferred; content guidelines still use old product name | Confusing / docs bug |
| testing-and-release | existing unchanged gates and routine thresholds | three formatting failures; release command only labels app/container CI evidence; benchmark archives HEAD, not dirty source | Confirmed gate failure / evidence risk |

No missing product feature is inferred from another project's feature list. Cosmetic changes
require measured readability/workflow benefit. Multi-replica/enterprise/new protocol scope,
live account certification and native-speaker certification remain outside this task.

## Reference evidence and license boundary

Root: `C:/Users/nben6/Downloads/repo`; read-only, untrusted source evidence.

- 9router 0.5.35, CLIProxyAPI 7.2.137, OmniRoute 3.8.49 and Portkey gateway 1.15.2
  have MIT root licenses. LiteLLM 1.97.0 and Langfuse 4.15.0 have separately restricted
  enterprise subtrees; only non-enterprise source comparison is in scope.
- cockpit-tools has no root `LICENSE` found in the initial inventory; no copying authorized.
- Existing detailed comparison: `../providers/conformance-audit-2026-09-16.md` and
  `../providers/credential-fidelity-audit-2026-09-16.md` (historical evidence only).
- Current spot check: 9router Codex registry uses ChatGPT Responses plus `wham/usage`,
  distinct from Platform keys; Portkey DeepSeek uses Bearer plus `/v1/chat/completions`.
  These match Polaris' transport separation. Reference model lists are not entitlement
  evidence and reset-credit actions are not authorization to add purchases/redemptions.
- No reference code or dependency copied.

## Execution and evidence

Tracked plan: `../../tasks/release-readiness-2026-09-18.md`. Results below will be recorded
after execution, including failures and limits. This baseline is **not** a release sign-off.

## 1. Current release status

The working tree prepares **Polaris 1.0.0, unpublished**, not a retroactive approval of
the old release. `HEAD` remains `1596650` on `develop`; all audit repairs are uncommitted.
No push, tag, release, registry publication, operator database migration or real
provider call was authorized or performed. **The final local release gate passed**,
with separate application and Docker evidence below. Publication remains blocked by
uncommitted source, legacy artifact collisions and outstanding immutable-commit CI/sign-off.

## 2. Findings and 3. Repairs

| Finding | Classification | Disposition / evidence |
| --- | --- | --- |
| Raw inference failure bodies could enter warning/error logs and persisted credential error messages; debug logging included state values | Security/privacy | Omit raw bodies/values and persist existing classified, content-free diagnostics; regression covers stream/non-stream and retryable/non-retryable errors |
| Update-check exception text could disclose remote response details in debug logs | Security/privacy | Fixed safe message; secret-bearing exception regression |
| Extended-provider failures dropped `Retry-After`; simply forwarding upstream headers would leak untrusted metadata | API correctness | Validate numeric/HTTP-date values only, preserve through protocol adaptation, reject arbitrary/oversized values; no cookies or other upstream headers copied |
| Browser smoke inherited operator application environment | Verification safety | OS launch allowlist, fresh credentials path, no `.env`, no operator provider/DB/OIDC/proxy settings, pricing sync off |
| Reliability measured archived HEAD, not the uncommitted candidate | Release evidence | Explicit `--working-tree` snapshot with per-file and aggregate SHA-256; normal immutable-commit gate unchanged; benchmark pricing sync disabled |
| Plan/credit tooltip could not be dismissed with Escape or traversed across its visual gap | Accessibility | Escape dismissal retains focus; pointer bridge; reopen on fresh hover/focus; DOM and real Chromium regressions |
| Two Activity native date/time controls carried unsupported hardcoded placeholders | Localization/semantics | Retain native picker and translated persistent labels; remove ineffective attributes, not translation-audit rules. Text fields/textareas keep meaningful placeholders |
| Three formatter failures and a stale credit-badge text assertion | Verification | Format only; assert current icon badge's accessible label and translated tooltip, not obsolete visual text |
| Beta metadata, nine-provider documentation, obsolete locale claims and inaccurate setup/import/catalog prose | Documentation/release | Prepare 1.0.0 consistently, document 23 variants and offline/unverified imports, correct operator-configured setup token and all 15 README targets; distinguish SpaceXAI API catalog from Grok Build OAuth catalog in all READMEs |
| Legacy `v1.0.0` exists; image job could publish before release-note validation | Release blocker | Preserve history; dated/unique version-matched preflight before image publication; undated candidate intentionally fails publication check |

Each behavior repair was preceded by a failing focused regression. No test was removed,
no quality threshold was reduced, and no lint/security suppression was added to pass gates.
Security repairs prevent new raw error writes; they do **not** rewrite historical user data.
The final diagnostic regression also ensures inference errors do not claim the connection
test's 30-second deadline: generic upstream/timeouts retain a safe HTTP status, while
credential/permission/quota categories keep the applicable classified explanation.
Impeccable's audit/craft guidance informed measured spacing, hierarchy, responsive and
accessibility review; it led to the tooltip interaction repair, not a replacement visual style.

## 4. Deliberately unchanged

- Preserve existing route/model semantics, accounting, compression, storage schema,
  provider entitlements and capability/permission ownership. No new product feature was
  inferred from another gateway's feature list.
- Preserve the compact console, 32px controls, 36px navigation, responsive four-column
  credential grid, one-line identities, provider-specific modal sections and unknown quota
  states. No speculative visual redesign or made-up provider plan/credit data.
- Do not rename/move/delete legacy tags or images. The owner's choice of the same names
  requires a separately authorized, provenance-preserving publication procedure.
- Do not modify `.agents/content-guidelines.md`: this protected instruction file still
  uses the old brand/Pool terminology. Current product constraints and runtime/docs are
  authoritative; updating that protected file needs the appropriate write permission.
- Retired Redis/HA/Kubernetes designs remain historical, not release requirements.
- Large touched incumbent files (primary request lifecycle, credential cards, reliability
  runner) were assessed for extraction. New header validation and runtime isolation have
  small owners; splitting unrelated stable lifecycle/UI code would broaden this audit.

## 5. Product and workflow coverage

Current inventory: **149 OpenAPI paths / 165 operations**, including **143 management
operations**; 13 page fragments, 11 navigation destinations, 20 route groups, 86 JS and
16 CSS files. Setup/login/callback are additional public surfaces. There are 23 credential
variants, with six OAuth families and provider-scoped API-key/local-server workflows.

| Area | Current verification and preserved boundaries |
| --- | --- |
| UI/UX | Empty/populated pages, all provider workspaces and credential modals, key/identity/route/quality/settings workflows, confirmation/focus, loading/error/retry, mobile sidebar, two themes; measured overflow/contrast/names/overlaps |
| Business logic | Reservation/release, quota/budget windows, idempotent batches, eligibility, route priorities/strategies, cooldown/fallback, stream cancellation, usage/missing-usage settlement; existing contract suites retained |
| API | Frozen compatibility fixture, OpenAI Chat/Responses, Anthropic Messages, Gemini/Vertex boundaries, request IDs, protocol-native error adaptation and output-aware retry tests |
| Providers | Registry capabilities intersect permissions; offline import is not a verification claim; catalogs and model eligibility remain credential-scoped; plan/quota/credits remain provider facts |
| Security | Setup/owner recovery, session expiry/rate limits, OAuth ownership/PKCE/callbacks, SSRF and credential import boundaries, least-privilege actions, content-free diagnostics, dependency audit |
| Storage | SQLite is Core; migration/backup validation/encrypted restore/conflict/rollback contracts, fresh Docker setup and persistence; PG/Mongo/OIDC live services explicitly separate |
| Operations | Health/readiness/shutdown, content-free audit/traces/logs, unavailable distinct from zero, bounded pagination; exporters remain opt-in |
| Localization | All 15 README targets/import descriptions; 1,356 referenced frontend keys, interpolation and management-message audits; EN/VI editorial review and browser locale checks, not native-speaker certification |
| Docs/release | Metadata parity, support policy, Compose/install/update/rollback, collision checklist, guarded release-note extraction; no schema migration introduced |

### Provider inventory and deterministic evidence

Variants reviewed: `cerebras`, `claude_code`, `claude_platform`, `cloudflare`, `codex`,
`deepseek`, `google_ai_studio`, `google_antigravity`, `grok`, `groq`, `kilo`, `kimchi`,
`kimi`, `kiro`, `meta`, `mistral`, `muse_code`, `nvidia`, `ollama`, `openai_platform`,
`opencode`, `poolside`, `xai_console`. See [capabilities](../provider-capabilities.md)
for auth/settings ownership, not just card presence.

The current run re-executes the existing provider-specific corpus. This task additionally
tests **14 extended variants × seven failure statuses**, safe retry metadata, malformed
metadata and diagnostic privacy. Coverage is layered; it is **not** a claim of 23 × 14
independent vendor-native/live certifications.

| Requested state | Deterministic coverage owners (in `backend/tests`) |
| --- | --- |
| Success / credential validation / invalid credential | `test_hosted_providers`, `test_api_platform_providers`, `test_provider_onboarding`, `test_extended_provider_onboarding`, `test_extended_provider_runtime` |
| Expired credential / renewal / callback cancellation | `test_muse_oauth`, `test_kiro_oauth`, `test_claude_oauth_hardening`, `test_oauth_callback`, `test_provider_oauth_session_isolation` |
| Missing model / ineligible credential | `test_model_routing_workflow`, `test_virtual_model_blacklist_routing`, `test_routing_scenario_matrix` |
| Quota exhausted / rate limited | `test_credential_quota`, `test_quota_lifecycle`, `test_quota_reservations`, `test_quota_rate_window`, provider-specific usage tests |
| Upstream error / timeout | `test_provider_connection_diagnostics`, `test_extended_provider_runtime`, `test_protocol_errors` |
| Partial metadata / unavailable quota | `test_antigravity_usage`, `test_codex_usage`, `test_anthropic_usage`, `test_kiro_usage`, `test_muse_quota_stream` and credential-console contracts |
| Malformed response / interrupted stream | `test_meta_native_stream`, `test_muse_quota_stream`, `test_extended_provider_runtime`, `test_public_streaming_lifecycle`, `test_anti_truncation_stream_lifecycle` |
| Retryable / non-retryable failure | `test_routing_coordination`, `test_public_streaming_lifecycle`, `test_extended_provider_runtime`; no transparent replay after emitted output |

Reference comparison also inspected CLIProxyAPI Responses stream-error normalization,
OmniRoute bounded retry-delay parsing, and LiteLLM stream-close/fallback metadata. These
inform checks, not copied implementations or a promise of native-client feature parity.

## 6. Verification evidence

All new runtime tests use synthetic data in isolated directories/projects. Existing preview
databases and real credentials are not test fixtures. Evidence under `temp/` is local and
ignored by Git; the summary here is the durable record.

| Check | Result / evidence |
| --- | --- |
| Focused behavior tests | RED then GREEN for safety, retry headers, tooltip and date control regressions; final harness suite 23 passed |
| Runtime changed-line check | Standard-library line tracer over 49 focused tests: 35/37 executable changed runtime lines hit (94.59%); `temp/release-runtime-changed-lines.json`. This is line coverage, not branch coverage or coverage of all tooling/JS |
| Fast / full release gate | Passed, exit 0; `temp/release-final-source-20260918.log`. Application/container steps in this runner are CI-evidence markers, not silently executed tests; their actual independent results are below |
| Final-source core | 2,308 tests in 186.839s: 2,286 passed, 22 explicitly optional live-storage skips, no failure/error |
| Configuration/inventory/compatibility | 56 passed in final gate |
| Four localization audits | Passed; 1,356 referenced keys in every locale, JS/HTML/API-message coverage |
| Dependency compatibility / vulnerability audit | `pip check` passed; `pip_audit --local` reported no known vulnerabilities in the installed environment |
| Populated browser matrix | 384 cases, zero measured UI findings or page errors; `temp/populated-instance/release-20260918-before/report.json` |
| Expected error states in populated matrix | Eight 400/502 responses from deliberately invalid quota fixtures matched the existing exact allowlist; zero unexpected API errors |
| Empty browser matrix | 152 cases, zero findings/page errors, zero writes; `temp/empty-instance/release-20260918-before/report.json` |
| Populated business workflows | Nine passed; `temp/populated-workflows/release-20260918/report.json` |
| Locale browser matrix | 15 locales, 14 surfaces, 360/1440px and light/dark; no page errors; callback no-store and language checked |
| Interface-state browser tests | Loading/error cleanup, refresh retention, nested dialog focus/scroll/Escape at 320/844/1440 passed |
| Credential browser confirmation | 1440/768/360/844, no horizontal/nested modal overflow; badge keyboard/hover/Escape/reopen passed; `temp/prerelease-credentials/report.json` |
| Application smoke | Fresh setup plus authenticated restart/login passes; `temp/release-application-20260918.log` |
| Critical-journey Chromium smoke | Nine of nine passed; 11 routes × four widths, keyboard sidebar/provider selection; `temp/release-browser-final.log` |
| Docker Linux/amd64 Compose | Build/config/start/setup/recreate/persistent-login/stop/restart/relogin/final-stop passed on final runtime source; final graceful stop 0.661s |
| Routine reliability | Passed all 15 checks: 600/600 in 120.060s, 5 RPS / concurrency limit 8, p95 74.657ms (<100ms), error rate 0%; warm dashboard 513.434ms (<2,500ms); memory peak 158.145MiB, post-warmup growth 0.898MiB, slope 0.684MiB/min; restart ready 1.799s, persisted request HTTP 200 |

Final reliability snapshot: **966 source files**, aggregate SHA-256
`3249eb14daa01e86366ad3fcf7698e0b05b7182fff9d2fae8779d65fc86374cb`.
`temp/release-reliability-working-tree.json` contains every source-file hash and gate
observation. A post-run hash comparison found no runtime, UI, test or tooling drift;
only this report had changed. Subsequent edits close out this report and task-status
documents only. This is stronger provenance than referring to the unchanged old HEAD,
but is not a substitute for CI on a reviewed immutable release commit.

Final Docker rehearsal uses project `polaris-release-audit-d105e30a7d6e`, image
`polaris-release-audit-d105e30a7d6e:local`, volume
`polaris-release-audit-d105e30a7d6e-data`, and local image ID
`sha256:6e65aa6d73e8c0b317efe83fe6a4cbca6855c9577b1a6c24a65d679a26236255`.
The container is stopped; its synthetic volume/image are retained, not deleted. Earlier
successful rehearsal projects (`bc69ac43b502`, `48c6a25ca3b1`, `01c425101a4f`, with the same
prefix) are also stopped and retained. This is a local rehearsal, not a published image digest.

Earlier failed attempts remain part of the record: formatter/static-i18n failures repaired;
stale badge/version assertions repaired; the accidental system Python 3.12 test attempt
lacked dependencies and is invalid evidence. Current local gates use `.venv` Python 3.14.6;
Docker supplies the maintained Python 3.12 runtime. Windows sandbox temp-directory/named-pipe
failures required execution permission for isolated test processes, not application changes.
The first complete final core attempt ran 2,306 tests with 22 existing optional skips and
one `WinError 5` during atomic replacement of a temporary Compose update record. All nine
Compose-update tests then passed in isolation without changing or suppressing that test;
the confirmation gate then passed (2,307 tests; 22 optional skips), including 600/600
reliability requests. This intermittent Windows failure is retained as evidence, not
relabeled a passing run. The final-source gate after the diagnostic-copy correction also
passed, with 2,308 tests (22 optional skips), nine browser journeys and the metrics above.

## 7. Limits and 8. Publication risks

- No real OAuth, paid inference, account/region/plan renewal or vendor quota certification.
  Internal provider services can change independently; retain the limits in
  [provider conformance](../providers/conformance-audit-2026-09-16.md).
- PostgreSQL/MongoDB live suites and external OIDC are optional integrations, not silently
  covered by SQLite tests. The 22 existing skips are two PostgreSQL migration tests,
  14 PG/Mongo identity tests and six PG/Mongo usage-ledger tests, due to absent
  `POLARIS_TEST_POSTGRESQL_URI` / `POLARIS_TEST_MONGODB_URI`.
- No GitHub-hosted CI, remote registry/tag inventory, Linux-native host matrix, ARM64,
  Firefox/WebKit, full assistive-technology certification or ten-minute optional soak was run.
- Automated responsive/contrast checks and selected screenshot inspection are not proof of
  every possible content permutation. Native date/time affordances follow the browser locale.
- Runtime changed executable lines measure 94.59% in the focused tracer run. A combined
  numerical coverage report for frontend JavaScript and developer/release tooling was not
  generated; do not extrapolate the runtime number to the entire repository.
- Existing Python 3.14 SQLite fixture `ResourceWarning` output is recorded, not suppressed.
  Final pass/fail status depends on the suite result, not the absence of warning text.
- Current `HEAD` does not contain these fixes; undated release notes and legacy artifact
  collisions deliberately prevent a ready-to-publish claim.

## 9. Important changed owners

- Runtime safety: `backend/core/api/primary.py`, `credential_manager.py`,
  `provider_connection_diagnostics` integration, `panel/version.py`.
- HTTP metadata: new `backend/core/http_headers.py`, `extended_provider_runtime.py`,
  `router/protocol_errors.py` and matching provider/protocol regressions.
- UI: `frontend/js/ui/credential-cards.js`, `features/navigation.js`,
  `frontend/css/components.css`, Activity fragment and accessibility/placeholder tests.
- Verification: new `tools/runtime_isolation.py`, browser/reliability/quality-gate runners,
  source-snapshot/harness tests and credential browser smoke.
- Release: new `tools/release_preflight.py`, CI/image workflows, app version, Compose,
  changelog, SECURITY, README plus 14 locale READMEs, provider/spec/quality-gate docs and
  [publication preparation](../releases/1.0.0-preparation.md).

## 10. Final release checklist and 11. Tag verdict

- [x] Baseline, bounded plan, current inventory and reference/license checks recorded.
- [x] Confirmed repairs have focused regressions; no weakened thresholds or operator-data reset.
- [x] UI empty/populated, states, themes, responsive, keyboard and locale matrices executed.
- [x] Local application and isolated Docker install/restart/persistence/shutdown rehearsed.
- [x] Complete final local release/core/browser/reliability verdict and review residual failures.
- [ ] Owner reviews/authorizes an immutable commit containing the audited repairs.
- [ ] Required CI/gates pass on that exact commit; optional/live limitations accepted explicitly.
- [ ] Owner inventories and authorizes resolution of old `v1.0.0` / `1.0.0` artifacts.
- [ ] Approved publication date, correct latest-release behavior, image provenance and rollback digest.
- [ ] Explicit authorization to push/tag/publish.

**Current HEAD is not ready to tag `v1.0.0`.** Do not confuse a passing local working-tree
audit with an immutable release candidate or permission to overwrite the existing tag.

## Subsequent owner-authorized tag migration — 2026-09-18

After this audit, the owner separately authorized archiving all 14 Omni Gateway tags
under `omni-gateway/` and renaming the existing Polaris prerelease to `v0.1.0-beta`.
The [migration record](../releases/tag-migration-2026-09-18.md) documents verified
local/remote refs, preserved release IDs/notes/dates, workflow restoration and recovery.
This resolves the Git/GitHub name collision only: no new `v1.0.0`, code commit, branch
push or Docker image publication occurred. Registry provenance/collisions and current
immutable-commit release checks remain outstanding. Earlier statements describe the
audit-time state; its recorded source snapshot predates these documentation updates.

## Subsequent committed candidate verification — 2026-09-18

The owner then authorized committing, pushing the preparation branch and running CI,
but not merging main, tagging or publishing. Runtime candidate
`bafe7b67d31f99b31d8639aa83beda4d5d18ca70` passed the canonical local release gate
(2,311 tests, 22 existing optional storage skips; 9/9 browser journeys; 600/600
routine load requests). GitHub CI [35312546089](https://github.com/nguywnben/polaris/actions/runs/35312546089)
passed Python 3.12/3.14, dependency, application, browser and container gates on that
same SHA; both publication jobs were skipped. Registry inventory confirms that the
target version names are available and records beta rollback digests. Dated release
notes and verification-only manual CI resolve the remaining preparation defects.

The [readiness record](../releases/1.0.0-readiness.md) supersedes the earlier
uncommitted-source, missing-CI and collision verdicts. Optional/live scope exclusions
remain; no test result certifies actual vendor accounts or an untested operator
deployment. Final documentation-only changes require their own green CI before handoff.
