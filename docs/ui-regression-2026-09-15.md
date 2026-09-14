# Polaris UI regression — 2026-09-15

## Scope and result

All 14 reviewed page surfaces have a passing regression path: setup, login, dashboard,
providers, pool, models, ai-quality, playground, access, identity, activity, config, about,
and OAuth callback. Activity includes trace, audit/security, and runtime-log tabs.

This is a bounded UI regression result, not a production-release or every-provider certification.
The verified work is recorded in local commits on `develop` at the owner's request.
No push or release is included in this pass.

## Corrections

- Runtime coordination now anchors timestamps to Unix time at process start and advances
  using monotonic elapsed time. Identity session dates no longer render as 1970. A regression
  first reproduced the failure, then verified timestamps and expiration across forward and
  backward wall-clock jumps. A separate read-only review found no actionable issue.
- Activity tabs wrap on small screens. The existing no-horizontal-scroller contract remains
  intact, with a browser assertion for the tab strip itself.

## Verification

- 186 tests passed across the changed backend/UI contract modules and the new form-validation
  and password-checklist modules.
- Additional identity/session, in-memory coordination, routing, primary-session,
  provider/device authorization, and credential-batch suites passed.
- All 17 browser scripts passed: 14 page/form scripts plus identity navigation, shared form
  interaction, and the critical-journey suite. The Activity script passed again after its CSS fix.
- Critical journeys: 9/9 passed; the shared responsive/accessibility sweep covered 11 routes
  at four widths. Page-specific scripts additionally exercise English/Vietnamese, light/dark,
  narrow layouts, and applicable empty/error/pending/success, dialog, and keyboard states.
- Changed JavaScript syntax checks, focused Ruff checks, and `git diff --check` passed.
- Browser tests used disposable local data and synthetic provider responses, not real user
  API keys, provider accounts, or billable requests.

## Limits

Real upstream OAuth/provider behavior, all browser engines, every locale, production load,
and the complete release gate were not certified in this pass. Later system-clock corrections
are reflected in calendar timestamps at the next process start; expiration continues to use
elapsed time. Restarting the process can require signing in again because sessions are local.
