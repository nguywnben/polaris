# Provider ownership and import repair — CR-001

## Scope

Compared Polaris with the local reference snapshots under `C:\Users\nben6\Downloads\repo`:
CLIProxyAPI 7.2.137, 9router 0.5.35, OmniRoute 3.8.49, gateway 1.15.2,
LiteLLM 1.97.0 and Langfuse 4.15.0. This is not a claim of parity with newer live upstreams.
The approved repair retains nine advertised provider variants and fourteen console pages.

- Provider-owned and shared Google/Claude/xAI settings have explicit, nonduplicated editors.
- Legacy Code Assist settings moved from System Settings to Providers without renaming stored keys.
- Routing-wide stream conversion and retry credential switching remain in System Settings.
- Antigravity credit mutations moved from Pool to its provider workspace; Pool retains status.
- Native OAuth imports are bounded and provider-specific. Offline imports clearly separate
  storage from verification, with an import-provenance notice rather than an invented live status.
- Google OAuth destinations, Claude transient errors and explicit provider-request NO_PROXY
  behavior are covered by regression tests. Google transport diagnostics redact proxy secrets.

## Verification

- 349 focused backend/frontend contract tests passed, including 17 Node VM cases for provider
  form drafts, loading failures, scoped resets, visible secrets and malformed reset responses.
- All 13 changed application JavaScript files passed syntax checks.
- Ruff passed on changed Python files. Whitespace and generated configuration-reference checks passed.
- All 1,318 referenced interface keys resolve in all 15 locales. HTML, JavaScript and backend
  localization audits passed. New messages use normal-weight incumbent placeholder styling.
- `tools/provider_ownership_smoke.py` passed in isolated Chromium with disposable SQLite:
  360, 768, 1024 and 1440 pixels, in both light and dark themes. All nine provider selectors,
  shared Google forms, credit ownership and System Settings boundaries were checked.
- Sixteen local screenshots were inspected. The new credit panel was moved out of the wrong
  workspace, disclosure spacing was corrected, and the Settings save bar no longer overlays content.
- Existing asset assertions for paginated dashboard rendering and split Grok/Console filters
  were updated to their current contracts; neither implementation was weakened to satisfy a test.

Independent agent reviews covered backend security/scoping and frontend draft behavior.
No dependency or test threshold was changed; no test was skipped to make the repair pass.

## Boundaries

No Docker container, real credentials, `.env`, live provider account, remote branch or release
was changed. Actual OAuth completion and billed inference against each provider still require
operator-owned accounts and a separately authorized live smoke. The pricing-catalog raw HTTP
manager caller is outside the provider-wrapper NO_PROXY change.

Existing configuration values and environment locks are retained. See the migration note in
`docs/provider-capabilities.md` for previously customized Google OAuth origins.
