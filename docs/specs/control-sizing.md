# Shared control sizing

## Global sizing

Buttons, single-line inputs and selects use the owner-approved Dashboard preview
size: `--control-height: 32px` on both desktop and mobile. The preview-specific
override is removed; compact/small variants keep their typography and horizontal
padding but no longer have a different height. Single-line fields use 5px vertical
padding to keep text readable at this size. Page-header actions use an alias of
the shared token, not another size scale.

Widths retain their existing content, grid or form constraints; fields do not become
square. Icon-only controls use the token for both dimensions. Color, focus, hover,
disabled states, border radii and behavior are unchanged.

Textarea, checkbox/radio, range/color controls, file upload inputs and multi-row
selects retain native/content-appropriate geometry. Buttons acting as provider
cards, upload drop zones, multi-line endpoint content or model-name tiles retain
natural height so their content is not clipped. Field skeletons use the same token.

## Verification of the approved 32px size

Sidebar navigation keeps its compact appearance: 248px width, 13px labels,
16px icons and 3px gaps, with a 36px minimum row height. Long translated labels
can wrap and grow the row; short viewports scroll the sidebar. The brand uses
18px text and a 28px mark. Main-page controls and the sign-out button retain the
shared 32px size.
`tools/sidebar_ui_smoke.py` covers both themes, six viewports, 15 locales and
mobile focus/scroll behavior in 68 bounded combinations.

- The two shared-height contracts fail before the change and pass afterward.
- Chromium validates 4,219 control measurements across 11 pages, 23 providers,
  four widths, light/dark and 15 locales. Desktop and mobile screenshots inspected.
- Credential management operations/focus smoke and 128 header measurements pass.
  Header measurements use a single DOM snapshot so transient loading actions cannot
  disappear between counting buttons and measuring them; height/overflow assertions
  are preserved.
- 31 focused feedback, Playground and textarea tests pass; Ruff and diff checks pass.
- Full core suite passes: 2,222 tests, with 22 existing optional skips
  (`temp/compact-controls-core.log`).
- Native preview 4284 serves the global 32px token without 38/44px overrides, and
  readiness returns 200. No Docker changes or real credential mutations.

Previous verification of the shared-token rollout (38/44px, before compact approval):

- `tools/control_sizing_smoke.py`: regression first failed on 30/32/34px dashboard
  controls; final Chromium matrix passes 4,258 measurements across 11 pages, 23
  provider workspaces, four widths, light/dark themes and 15 locales.
- `tools/header_actions_smoke.py`: 128 header measurements and refresh feedback pass.
- `tools/credential_management_smoke.py`: inline edit/action/quota, responsive
  layouts and focus behavior pass with the shared control size.
- Feedback/asset/navigation/textarea tests pass (44 tests); updated Playground
  contracts and the shared-token contract pass (29 tests). The two old 30px
  Playground expectations are replaced with assertions for the shared token;
  existing width, content and responsive assertions remain.
- Ruff and diff checks pass. No new dependencies, runtime logic, auth, provider
  calls or credential mutations. CSS updates are narrowly scoped sizing changes;
  existing large stylesheets are not reorganized as part of this refinement.
- Full core suite after updating the superseded size contracts: 2,221 tests pass,
  22 existing optional skips (`temp/control-sizing-core-final.log`). Native preview
  4284 was restarted and verified to serve the new versioned CSS. Docker is unchanged.
