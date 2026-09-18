# Claude Platform private advanced settings

Verified on 2026-09-15.

## Scope

Claude Platform now exposes an API base URL and HTTP User-Agent on Providers.
They use private stored keys and environment overrides, not the legacy Claude
Code values. The `platform` reset scope only deletes Platform overrides and
preserves environment locks. Model discovery (including key validation/import)
and both streaming and non-streaming inference select the same connection
settings based on credential type. Claude Code OAuth and usage remain unchanged.

The existing responsive provider field grid, translated descriptions, small
action buttons, placeholders, validation and modal conventions are reused.
No shared settings are exposed on System Settings or other provider editors.

See `../provider-capabilities.md` for the explicit transition from legacy shared
endpoint overrides: custom Platform endpoints must now be configured separately.

## Checks

- New isolation tests failed before implementation (missing private getters and
  rejected private config keys), then passed after implementation.
- 54 focused backend/contract tests passed, covering save/reset/locks, invalid
  endpoint/header rejection, schema inventory, provider onboarding and Claude
  discovery/inference/usage behavior.
- Five Anthropic JavaScript runtime contracts passed, including Platform-only
  POST payloads, scoped reset, sibling draft retention and failed-load behavior.
- `tools/provider_ownership_smoke.py` passed real save/reset against a disposable
  backend, confirming that persisted Claude Code values and its unsaved client
  draft are preserved. Opening the section does not focus a text control.
- All nine providers tested at 320/768/1024/1440px, light and dark, without browser
  errors or overflow. Desktop/mobile Claude Platform screenshots visually checked.
- Frontend/backend locale audits, configuration-reference check, lint, Python
  compilation, changed-JavaScript syntax and changed-Python formatting passed.
- Full backend run: 1,859 tests executed, 22 skipped by existing conditions. It
  initially reported five failures: two missing new environment inventory entries
  were fixed and the affected inventory test rerun successfully. Three unrelated
  existing failures remain: backup navigation's VM fixture lacks `URL`; the
  management audit matrix lacks the existing Google config POST/reset routes;
  the System Settings inventory still lists moved Code Assist fields instead of
  the shared stream/retry controls. No test or gate was suppressed.
- The fast gate still stops on 23 pre-existing unformatted files outside this
  change. This is not a claim that the repository-wide gate is green.

Browser evidence is local in `temp/claude-platform-private-settings/`. Tests use
synthetic credentials and disposable storage; no live provider request is sent.
