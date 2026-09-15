# Existing-page completion — 2026-09-15

## Approved scope

The owner approved completing four concrete gaps identified in
[the page-function audit](page-function-coverage-2026-09-15.md), with parallel implementation.
This does not replace the historical R1/R2 plans, add a page, or authorize optional expansion.
The product keeps 14 user-facing pages: 11 main pages plus setup, login and OAuth callback.

## Changes

| Existing page | Completion |
| --- | --- |
| Dashboard | Current and historical usage now request independent bounded server pages, including rows beyond 100. Provider summaries aggregate all current traffic, not only the visible page. |
| Settings | Encrypted backup download, non-restorable sanitized export, dry-run validation, separately confirmed restore, permission checks, transient-secret cleanup and explicit reauthentication. |
| Login / Identity | Optional same-origin OIDC entry without automatic redirects or loss of owner-password login; deployment and access-binding guidance in Identity. |
| Models / Settings | Models owns editing of routing strategy and preferred provider. Settings displays a summary and link; ordinary Save and scoped Reset do not overwrite those values. |

No new runtime dependencies, provider families, auth protocol, storage backend, or release was added.
No user Docker volume, live identity provider or live provider credential was used for verification.

## Additive API contracts

- `GET /api/usage/stats/page`: `offset >= 0`, `group=all|current|historical`,
  `order=calls|name`; existing defaults remain all rows ordered by call count. The response adds
  `offset`, `group`, and full current-traffic `provider_totals`. Page size remains bounded at 200.
  Current/historical UI groups include only rows with traffic. Unassigned attempts remain part of
  global usage, not a fictitious provider. Filename ordering prevents changing counters from
  reshuffling pages; concurrent insertions/deletions are live data, not a snapshot guarantee.
- `POST /api/config/reset?scope=system` preserves routing strategy and preferred provider, in
  addition to existing secret/environment exclusions. Default `scope=all` preserves API behavior.
- `GET /api/auth/setup/status` adds `oidc_enabled`. Local configuration validation only; no
  discovery, public secrets or automatic authentication.

## Verification and review

Focused API and DOM regression tests cover pagination, complete summaries, fetch failure and stale
responses; Settings Save/Reset ownership; OIDC readiness and local-owner access; backup input and
permission validation, dry runs, confirmation, uncertain results, and leave/reentry cleanup.
New backup and OIDC copy is provided in all 15 supported locales. Automated checks and editorial
review do not constitute native-speaker certification.

Browser verification uses disposable SQLite instances and deterministic browser fixtures. It
includes the existing nine critical journeys and 11-route responsive sweep, pagination to row 101,
independent history, complete provider totals, real encrypted backup/download/validation/restore
and reauthentication, plus OIDC entry visibility without contacting a real identity provider.

Independent review identified a pending-request secret retention/reentry defect, fixed with
immediate cleanup and visit-scoped permission refresh. Integration checks also caught a
reauthentication link that returned to Dashboard; it now explicitly ends the current session.
The owner declined an additional cross-model review and accepted the existing verification.

The large existing Dashboard module was assessed: paging state and request orchestration were
extracted into `usage-pagination.js`; new backup behavior and translations are separate modules.

### Final evidence

- Dashboard: 21 API/DOM tests; isolated browser reaches current row 101 and historical row 11,
  keeping the full 120-credential provider total. Empty, populated, idle, failure/recovery,
  keyboard and 320–1440px light/dark checks pass.
- Settings: 17 console tests plus scoped-reset/security tests; existing browser smoke verifies
  secret toggles, validation, save errors/success, environment locks, independent routing and
  five widths in both themes. A read-only-summary Save regression was found and fixed.
- OIDC: six new strings in 15 locales, readiness/DOM tests plus the existing OIDC/setup/Identity
  suites pass. No real external IdP login was performed.
- Backup: three behavior/catalog contracts plus real-navigation leave/reentry regression pass;
  isolated Node V8 coverage reports 98.1% of the backup module's executed lines. The browser
  creates an actual encrypted archive, validates wrong/correct passwords and replacement
  conflicts, cancels confirmation, restores disposable state and signs in again.
- A 45-state locale/layout sweep across Settings, Login and Identity verifies all 15 locales,
  meaningful text placeholders at weight 400, and narrow-screen layout. Long archive names wrap.
- Existing browser smoke: 9/9 critical journeys and 11 main routes × 4 viewport widths pass.
- All 1,314 referenced translation keys resolve in every locale. Static HTML/JS and backend
  message audits, 71 JavaScript syntax checks, Python compilation, Ruff lint and manifest audit
  pass. R1 compatibility passes with only the exact optional-reset fingerprint evolution
  recorded; the frozen fixture remains unchanged and future reset changes still fail the guard.

Evidence is generated under `temp/dashboard-ui/`, `temp/settings-ui/` and `temp/page-completion/`
and is not committed as application data. The browser runtimes clean up their disposable databases.

### Remaining verification limits

The task gate stops at **20 pre-existing Ruff-format files** outside this change. All changed
Python files pass formatting; no lint/test suppression or threshold reduction was introduced.
This is not a claim that the repository-wide release gate is green. A full release, fresh Docker
image deployment, real IdP/provider integration and optional external storage tests were not run.
The user's running Docker installation and its data were not modified.
