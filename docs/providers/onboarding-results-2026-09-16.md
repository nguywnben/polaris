# Provider onboarding result consistency

## UI contract

- Successful OAuth saves collapse and clear transient authorization links, codes and callback inputs. The start action and shared localized result remain visible. Antigravity no longer renders or offers a download of the returned credential payload in onboarding; credential management stays in the pool.
- API key entry uses an explicit **Enter API key** opener (**Enter API token** for Cloudflare). Success clears the submitted secret and collapses the form. Reopening hides the previous result without automatically focusing an input. Failed saves keep the form available.
- All 23 provider card/workspace descriptions introduce the product and its purpose across 15 locales. Authentication methods remain in badges and forms. See [product description scope](provider-descriptions-2026-09-16.md). This does not change provider protocols, verification guarantees or server authentication.
- No polling, automatic login completion, real provider calls or Docker deployment are introduced.

## Verification

- `backend.tests.test_provider_onboarding`: regression for transient UI cleanup and removal of raw Antigravity payload rendering.
- `tools/provider_entry_smoke.py`: actual button-driven success/error/restart flows for four legacy OAuth providers; four legacy API key forms; localized descriptions and openers; desktop/light and mobile/dark screenshots; synthetic returned credential canary must never reach the DOM.
- `tools/extended_providers_smoke.py`: all 13 extended API key forms, failure/success transitions, advanced fields, 130 responsive/theme cases and 39 JSON/ZIP/rejection imports.
- `tools/provider_workspace_smoke.py`: all 23 JSON examples, Kiro manual browser/device flows, responsive layout and API key disclosure spacing.
- Locale audits: referenced keys, static HTML and JavaScript messages.
- Full core regression: 2,194 tests completed successfully (22 existing optional-backend skips). The focused entry, extended-provider, workspace and Muse browser checks all passed; JavaScript syntax, Python lint/format and diff whitespace checks passed.

Browser checks use disposable storage and mocked provider responses. They verify UI behavior, not live vendor authorization or model access.
