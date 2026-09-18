# Provider authentication and onboarding consistency

Approved scope: user requested implementation of the five findings from the provider review.
Work is sequential on develop, without subagents. Existing API keys and data remain valid.

## Capability map and build order

1. `kiro-auth`: OAuth credentials, refresh, import, device/social authorization and UI.
2. `provider-import`: consistent offline import with explicit unverified state and retryable files.
3. `provider-onboarding`: shared wording, pending/results, advanced-setting scope and provider-specific help.

## Contracts

- Kiro OAuth is the default connection method; API key remains a separate secondary method.
- OAuth uses AWS Builder ID/Identity Center and Google/GitHub device authorization.
  OmniRoute's social device flow avoids desktop-only redirect URIs on Docker/VPS; no manual PKCE
  callback endpoint is needed for these four sign-in methods.
  Import supports canonical and cockpit snake/camel-case token fields, with conflict rejection.
- Secrets stay server-side in the existing credential store. Authorization flows are bounded,
  expiring, single-consumer and tied to the initiating management session. A different session,
  wrong provider, invalid state, duplicate completion or expired flow cannot save credentials.
- Use fixed HTTPS auth endpoints and validated AWS regions; no arbitrary issuer/proxy URL from imports.
- Persist the account fingerprint across access/refresh token rotation. Imports prefer the refresh
  token as identity material; access-only exports cannot be deduplicated across unrelated token exports.
- Imported credentials are unverified and do not make paid inference calls. Catalog discovery is
  separate from permission to run inference. Never advertise successful authentication from a public catalog.
- Retain failed upload files and show per-file results; make the same input behave consistently
  at provider-scoped and mixed-pool entry points.
- Advanced provider defaults and per-credential connection overrides retain their distinct scope.
  Shared presentation must not change configuration ownership or migrate secrets into Settings.
- Preserve all supported locales, custom validation, secret toggles, small desktop buttons and
  mobile targets, light/dark tokens, keyboard access and no automatic input focus.

## Implementation / verification

Python modules live in backend/core; FastAPI routes in backend/core/panel/providers;
unittest tests in backend/tests; browser code in frontend/js/features and locale modules.
Follow existing snake_case Python, typed boundaries, safe ValueError messages and DOM textContent.

Focused: `.venv/Scripts/python.exe -m unittest backend.tests.test_kiro backend.tests.test_kiro_oauth`
Regression: `.venv/Scripts/python.exe -m backend.tests --suite core`.
Lint: `.venv/Scripts/ruff.exe check backend/core backend/tests`
UI: existing frontend build/check scripts plus disposable authenticated browser smoke.

First tests cover malformed/conflicting imports, refresh metadata and key/OAuth header separation;
then flow owner/expiry/replay/cancel, upstream failures, offline import parity and UI contracts.
Vendor boundaries use fixtures; live login/inference requires the user's account and is reported separately.
No new dependency, schema migration, Docker deployment, remote push or merge is included automatically.

## Threat model

Untrusted inputs: admin form/import data, device grants and vendor responses. Assets: access/refresh
tokens, dynamic OIDC client secrets, account identity and management session. Protect with bounded
schemas, authenticated routes, existing CSRF/permission checks, owner-bound device-flow claims,
no redirect following, fixed endpoints, safe errors and secret-free audit output. Cancellation and
expiry invalidate outstanding grants locally; transient upstream errors must remain retryable.

## User workflow and evidence boundaries

Kiro defaults to the cockpit-tools portal/PKCE flow: open the sign-in portal, choose Google
or GitHub, then return to Polaris. A localhost callback captures the code; authenticated
polling completes and saves the account automatically. The fallback disclosure accepts the
full callback URL, checks its origin/path/state, and never fetches it. The code/verifier and
tokens stay in the encrypted, expiring server-side flow store; only the initiating session
can complete or cancel the flow. Callback parameters are removed by a fixed, no-store redirect.

When Polaris is opened via localhost (including Docker on the same machine), its existing
HTTP port receives the callback; no extra port is opened. For a remote instance, Kiro returns
to localhost:4283 on the browser's machine: copy that complete URL from the sign-in tab and
paste it in Polaris, even if localhost shows a connection error. Custom local TLS must be
trusted by the browser. Reverse proxies must preserve the callback scheme and host, must not
rewrite its path, and should omit callback query strings from access logs.

The reference portal flow does not return a usable authorization code for every AWS method.
AWS Builder ID and IAM Identity Center therefore retain the device-code flow in a separate,
collapsed section: generate a device code, open the vendor link, approve access, then check
authorization in Polaris. The existing device API remains available for compatibility.
Identity Center requires the organization's AWS start URL and token region. No login page is
embedded and no token or dynamic client secret is returned to the browser. API keys remain in
a secondary disclosure, including their own runtime region/profile settings. Supported paid
accounts can obtain keys from `https://app.kiro.dev/` → API Keys.

Imports accept JSON/ZIP without upstream authentication/inference calls and retain failed files.
Existing matching imported credentials are skipped, not overwritten. Discover models and explicitly
test a model in the credential pool afterward. Loading a catalog is not proof of inference access.
Provider-specific connection settings remain in Providers or the corresponding credential editor.

References: `https://kiro.dev/docs/getting-started/authentication/`; local OmniRoute 3.8.49,
9router 0.5.35 and cockpit-tools under `C:/Users/nben6/Downloads/repo`.
Portal protocol details follow `cockpit-tools/crates/cockpit-core/src/modules/kiro_oauth.rs`
(`build_portal_auth_url`, callback parsing and `complete_login`). The public sign-in portal
allows localhost return origins; the PKCE exchange targets Kiro's fixed desktop auth endpoint.
Direct Kiro HTTP compatibility is based on reference implementations, not a guarantee of a
documented public HTTP API. Live OAuth and inference were not exercised with a user's account.

Review: synthetic tests cover token alias conflicts, nested cockpit imports, runtime/token-region
separation, rotating-token identity, response bounds, owner/provider isolation, expiry, denial,
poll throttling, cancellation, replay, concurrent completion and storage retry without re-exchange.
Browser checks cover 22 cards, 15 locales, 13 additional-provider forms, 130 responsive/theme cases,
39 JSON/ZIP/rejected imports, and all four Kiro method UI states. No new dependency or schema change.

Final checks (2026-09-15): core suite ran 2,106 tests successfully (22 pre-existing conditional
skips); the final access-only-token adjustment and import refinements passed the 84-test focused
set afterward. Fast gate passed lint, formatting, compilation, the 238-module test manifest,
JavaScript/YAML/shell syntax and whitespace. All four locale audits passed, including 1,341 keys
across 15 locales. Browser smoke passed with no page errors. Screenshots were inspected at desktop
dark and mobile light sizes. The UI reuses existing Impeccable-aligned spacing, disclosures and tokens.
Self-review was used as explicitly requested; no subagent or cross-model review was performed.

Portal-flow follow-up (2026-09-15): focused checks cover PKCE hashing, callback origin/path/state,
session binding, replay, cancellation, expiry, busy claims, code-exchange failure, storage retries,
public redirects and successful-save-only auditing. Browser tests cover automatic completion,
popup blocking, retained invalid callback input, manual fallback, cancellation, real local
authenticated endpoints and callback landing, plus light/dark layouts at 320–1440 px. All 15
languages have the new instructions. The existing provider/import browser suite also passes.
These checks use synthetic grants; live vendor login and inference still require an actual account.
