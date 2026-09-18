# Console navigation, empty models, and provider field layout

## Behavior

- A pristine Models catalog shows onboarding without routing-policy controls.
  Saved routes, selected models, and unavailable-route records keep the management
  workspace and policy accessible, even when discovery returns no models.
- Same-origin links to known console routes use the existing in-document router.
  Query parameters and hashes survive navigation and browser history. Downloads,
  external links, authentication endpoints, fragment-only links, and modified
  clicks retain browser behavior.
- Testing a saved model route opens Playground without a document reload. The
  model handoff also works when Playground was already visited; message drafts
  remain intact. This action does not submit a provider request.
- Provider advanced settings use equal two-column field grids above 1080px and
  one column below that breakpoint. Semantic groups span the panel; single and
  trailing unpaired fields use the full row. Existing settings and save behavior
  are unchanged, and operator-only shared settings remain hidden.

## Verification (2026-09-15)

- Reproduced the empty policy, full-document internal navigation, and narrow
  nested provider inputs with failing browser assertions before each fix.
- `tools/internal_navigation_smoke.py`: 17 navigation/history/keyboard steps,
  zero additional document requests, including cached Playground draft retention.
- `tools/models_ui_smoke.py`: empty, populated, missing, save failure/retry,
  selection/order, and Playground handoff; English/Vietnamese and responsive themes.
- `tools/provider_ownership_smoke.py`: all nine providers, seven advanced forms,
  320/768/1024/1440px in light/dark, field-width assertions, no overflow or console
  errors. Desktop and mobile advanced-form screenshots inspected.
- `tools/browser_smoke.py`: 9/9 critical journeys, 11-route/4-width responsive and
  accessibility sweep, sidebar/provider keyboard checks.
- 45 focused navigation/model/provider unit and contract tests passed.
- Backend/tooling lint, Python compilation, recursive JavaScript syntax,
  test-manifest audit, and all three frontend localization audits passed.
- The full fast gate remains blocked by pre-existing repository formatting
  drift, including `backend/core/google_endpoint_validation.py` and
  `tools/models_ui_smoke.py`. No gate, assertion, or threshold was suppressed;
  unrelated source files were not reformatted.

Browser verification uses disposable localhost runtimes, synthetic data where
needed, and blocks external provider calls. Live operator data is not test data.
