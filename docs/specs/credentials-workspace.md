# Credentials workspace

## Objective and acceptance

Keep `/credentials` a management workspace, using the current Polaris visual language.
The owner confirmed one full-width section per provider and at most four credential
cards per row on wide screens. Sections grow to additional rows, then the next provider.

- Show an explicit label first; OAuth may show its known email. Otherwise show the
  credential's existing filename identifier, never a missing-email error or a secret.
  Keep this title on one line with ellipsis; preserve the full text in its tooltip
  and management dialog (owner refinement, 2026-09-16).
- Cards show status, authentication method, available model count and supported quota.
  Unknown/unsupported quota must not appear as 100% available.
- Keep enable/disable and model testing as quick actions. Management is one information
  surface: account identity, fresh quota, searchable models, editable configuration
  and diagnostics. Information loads independently; actions and results stay inline.
  Reauthorization navigates to the existing provider workspace. Deletion requires an
  inline confirmation. Sensitive payload is fetched only after explicit reveal and
  cleared on hide, disclosure collapse or close; export remains capability-gated.
- Section batch actions target an immutable list of displayed credentials belonging
  to that provider. State the page scope and retain the server preview/confirmation
  protocol. Do not replace unrelated global selections.
  Enable, Disable and Delete are displayed directly in the section header; no
  intermediate actions modal (owner refinement, 2026-09-16). Mobile wraps the
  action group below the heading. Confirmation remains required.
- Preserve bounded pagination, empty/error states, existing provider behavior and
  light/dark themes. Layout scales down to one column without overflow at 320px.
- All new copy has contextual translations in the 15 supported locales.

## Implementation sequence

1. Test and correct identity presentation; no new provider calls or auth changes.
2. Full-width sections, responsive credential grid and scoped batch controls.
3. Reuse existing renderers, configuration form and API contracts inside one management modal.
4. Browser verification with synthetic old/new OAuth and API-key records, five or
   more records in one section, unsupported capabilities, themes and mobile widths.

## Structure and style

Native JavaScript and existing CSS tokens; no new dependencies. UI lives in
`frontend/js/ui/credential-cards.js`, manager state in `frontend/js/core/credential-manager.js`.
The management surface and action lifecycle are extracted into
`credential-management.js` and `credential-management-actions.js`, avoiding further
growth in the large card renderer. Styles are scoped in `credential-management.css`.
For example, retain `manager.credentialSupportsOperation(credInfo, 'quota')` rather
than inferring capabilities from provider names. Escape all interpolated identity text.

## Commands and testing

- `.venv/Scripts/python.exe -m unittest backend.tests.test_credential_fleet_console`
- `.venv/Scripts/python.exe tools/credentials_ui_smoke.py`
- `.venv/Scripts/python.exe tools/credentials_workspace_smoke.py`
- `.venv/Scripts/python.exe tools/credential_management_smoke.py`
- `node tools/i18n-audit.mjs`
- `.venv/Scripts/python.exe -m backend.tests --suite core`
- `git diff --check`

## Boundaries

Always preserve unrelated working-tree changes, use existing capability contracts and
confirm batch changes. Never fetch raw credential payloads just to render a management
overview, log tokens, mutate real credentials for testing, or call live model inference.
Ask before schema changes, dependency additions, deployment or expanding auth behavior.
No Docker update, commit or push is part of this task.

## Verification record — 2026-09-16

- New identity and scope snapshot regressions failed before implementation, then passed.
- Full core suite: 2,200 tests, no failures, 22 pre-existing optional skips; log at
  `temp/credentials-workspace-core.log` (local artifact).
- `credentials_workspace_smoke.py`: five keys in one section; old and new OAuth;
  no missing-email fallback; escaped hostile labels; unknown/unsupported quota;
  environment-managed edit/reauthorization gating; no raw detail request on modal
  open; focus containment/return; provider-only preview/commit with unrelated
  selection preserved; 320–1920px and 15 locales. Desktop/mobile captures inspected.
- `credentials_ui_smoke.py`: empty/populated, filters/reset, load error/retry,
  selection, ZIP chooser and route behavior passed.
- `extended_providers_smoke.py`: 23-card catalog, 13 forms, 130 responsive/theme
  cases, 39 synthetic JSON/ZIP/rejection imports, OpenCode/Meta editor passed.
- Locale coverage/static/JavaScript audits, Ruff, JavaScript syntax and diff checks passed.
- Native preview on 4284 returns updated credential UI assets. No live inference,
  real credential mutations, Docker changes or commits were performed.

Review: existing bounded pagination and capability contracts are unchanged. Batch
targets are captured before preview and reused at commit. Management overview uses
only allowlisted metadata; raw payload remains behind an explicit Reveal action.
Providers that do not persist an email (including existing Muse Code records) use
the credential identifier or an operator label; no email lookup is invented.

## Muse Code subscription metadata refinement — 2026-09-16

The owner requested subscription display. Muse's existing validated usage observation
contains an opaque `tier`; expose it as `subscription_tier` on the quota response,
not `plan`. The card and quota dialog show its exact value with the existing localized
tier label. Do not strip prefixes, change case, infer a retail name or assign Pro/Max.
Missing, blank or unknown values hide this metadata; a later missing value removes a
previous badge. Preserve existing eligibility checks, observation timestamps and
secret-free response projection. No extra provider requests or schema changes.

Verification for this refinement: 60 focused Muse/integration/console tests passed;
browser smoke passed for refreshed tiers, missing-tier removal, exact case/prefix
preservation, escaped markup, 128-character overflow, responsive themes and locales.
The full core run executed 2,201 tests with 22 existing optional skips and one
WinError 5 during an atomic file replacement in the unrelated Compose rollback
test. Rerunning the entire `test_compose_update` module passed all nine tests;
the full-suite run is not reported as clean. No rollback implementation was changed.
Native preview backend was restarted on 127.0.0.1:4284; `/ready` returned 200.

### Correction after live account verification

The current authenticated key response returns `subs_tier_name` independently of
usage and can omit `subs_usage` entirely. The earlier synthetic tier-only fixtures
did not cover this real shape. Read the bounded display name as `subscription_plan`
and project it as `plan`, preferring it over an opaque tier. Missing usage reports
`quota_status: unavailable` with no windows, not unsupported quota or 100% remaining.
A missing tier also must not discard valid windows. Do not reuse an older quota
as a fresh observation. The card and management dialog retain the plan when quota
is unavailable and show a localized unknown-data state. No live inference is used
to manufacture a quota observation.

Regression coverage includes a named plan without usage, optional/invalid names,
valid windows without a tier, escaped metadata, card rerender and the quota modal.
Verification: the full core suite passed 2,203 tests with 22 existing optional
skips; the additional invalid-name regression passed in the 36-test Muse module
run. Chromium credential-workspace smoke (15 locales, responsive light/dark),
locale audits, Ruff and syntax checks passed. Native preview 4284 was restarted
and `/ready` returned 200. A sanitized live-response projection confirmed the
named plan and unavailable quota state; no live inference or Docker update occurred.

## Muse Code post-completion quota event — 2026-09-16

Follow-up live investigation with a separate one-request allowance established
that `response.subscription_usage` can arrive after `response.completed`. The
stream adapter must consume it as private metadata, not model output, and store
only validated window fields with their actual observation timestamp. Storage is
bound to the account/session used for that request and must preserve concurrent
credential edits. Normal streaming, collected non-streaming and explicit model
tests use the same observer. Metadata write failures must not retry generation.

This does not change refresh semantics: refresh queries the authenticated key
endpoint, never starts inference, and never presents historical usage as a fresh
response when the endpoint omits usage. Plan display remains independent of quota.

## Single-surface management verification — 2026-09-16

`credential_management_smoke.py` covers independent information loads, inline name
editing, rejected saves and reset, model filtering and explicit inference, verification,
enable/disable, fresh quota failure/retry, explicit secret reveal/hide, inline delete
confirmation and exact-target deletion. All requests use synthetic fixtures; opening
the modal never triggers inference or retrieves raw credential content. The browser
checks one dialog, keyboard containment/focus return, 15 locales, environment-managed
restrictions, and 320–1440px light/dark layouts. The initial missing-modal regression
failed before implementation; the completed workflow passes.

The existing credentials-workspace and credentials-page browser suites pass. The
35-test fleet/asset slice, locale coverage (1,350 referenced keys), JavaScript syntax,
Ruff and diff checks pass. Desktop light/dark and mobile captures were visually
checked in a bounded initial-and-confirmation pass. Native preview 4284 serves the
new versioned JavaScript/CSS and returns 200 for readiness and the credentials page.
The full core suite passes: 2,220 tests, with 22 existing optional skips
(`temp/credential-management-core.log`).
No Docker update, commit, live inference or real credential mutation was performed.

Security boundaries remain the existing authenticated, capability-checked endpoints.
Identity/model/error text is escaped; replacement keys are never prepopulated and
are cleared after saving. Revealed payload is removed when hidden, collapsed or
closed. Pending reads are aborted on close; a pending configuration save prevents
closing and duplicate submission. No dependencies, API contracts or schema changed.
