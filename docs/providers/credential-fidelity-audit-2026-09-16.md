# Provider and credential fidelity follow-up — 2026-09-16

## Scope and verdict

Sequential self-review of all **23 provider workspaces**, six OAuth families,
credential facts/actions and provider-owned advanced settings. This extends the
[transport conformance audit](conformance-audit-2026-09-16.md), not a claim of live
certification or complete feature parity with every upstream client.

Confirmed omissions and misleading quota defaults were repaired. No real account,
inference, subscription purchase, Docker deployment, commit or push was used for
this audit. Browser verification uses disposable runtimes and synthetic credentials.
No subagents or new dependencies were used.

## Provider and advanced-setting inventory

Reference root: `C:/Users/nben6/Downloads/repo`. Abbreviations below:

- **R9**: `9router-0.5.35/open-sse/providers/registry/`.
- **CP**: `cockpit-tools/src-tauri/src/modules/`.
- **CLI**: `CLIProxyAPI-7.2.137/internal/runtime/executor/`.
- **OR**: `OmniRoute-3.8.49/open-sse/`.
- **GW**: `gateway-1.15.2/src/providers/`.

“Retained” means identity, transport and relevant settings agree with the inspected
source/contracts. It does not assert all models accept all generation options.
Model generation options belong to request/routing configuration, not credential
advanced settings; unsupported options must fail explicitly.

| Workspace | Authentication / transport retained | Relevant advanced settings / evidence |
| --- | --- | --- |
| Google Antigravity | Google OAuth / wrapped Gemini | OAuth client, API and user-agent settings; shared Google/legacy compatibility settings have one owner. R9 `antigravity.js`, CP `oauth.rs`, `quota.rs`. Credit policy belongs to credential management. |
| Google AI Studio | API key / Generative Language API | API endpoint; shared Google transport settings are not duplicated. R9 `gemini.js`. No invented per-key quota endpoint. |
| Grok Build | xAI OAuth / CLI Chat transport | OAuth API endpoint, issuer, client and shared user agent. CP `grok_oauth.rs`, `grok_account.rs`; R9 `xai.js`. Separate from xAI Platform billing. |
| SpaceXAI Console | xAI API key / Chat | Platform endpoint and shared user agent. R9 `xai.js`. No OAuth subscription facts for a Platform key. |
| Codex | ChatGPT OAuth / Codex Responses SSE | API, usage and auth endpoints, client and user agent. R9 `codex.js`; CLI `codex_executor.go`. Not the OpenAI Platform endpoint. |
| OpenAI Platform | API key / Chat adapter | Platform API endpoint. R9 `openai.js`. Subscription usage is not inferred from a key. |
| Claude Code | OAuth bearer + OAuth beta / Messages | Authorize/token endpoints and client; shared Anthropic transport has one owner. R9 `claude.js`; CLI `claude_executor.go`. |
| Claude Platform | `x-api-key` + version / Messages | Platform endpoint and user agent. Same executor distinguishes auth types. No Claude Code quota action. |
| Ollama | Local connection, optional bearer key / native Chat | Base URL and optional key per connection. R9 `ollama-local.js`. Local HTTP is intentional. |
| Kimi API Platform | Moonshot key / Chat | Allowed vendor endpoint, including China/international origins. GW `moonshot/api.ts`, OR `config/providers/registry/kimi/index.ts`. Not Kimi Coding OAuth. |
| Kiro | Browser PKCE / AWS device OAuth; separate optional API key / AWS EventStream | OAuth, AWS device and API-key fields have separate form ownership. Runtime region and profile ARN; no arbitrary inference origin. CP `kiro_oauth.rs`, OR `executors/kiro.ts`, `services/usage/kiro.ts`. |
| Cloudflare Workers AI | API token + Account ID / account-scoped Chat | Required Account ID, vendor endpoint. OR `executors/cloudflare-ai.ts`. No OAuth controls. |
| NVIDIA NIM | Hosted NVIDIA API key / Chat | Hosted vendor endpoint. R9 `nvidia.js`. This integration is not arbitrary self-hosted NIM. |
| OpenCode | User API key / Zen or Go; model-family transport | Explicit plan and endpoint, changed together. R9 `opencode-go.js`, OR `config/providers/registry/opencode/`, official Zen docs. R9's anonymous/free variant is a different product. |
| Poolside Platform | API key / Chat with reasoning replay | Vendor endpoint. No matching direct adapter found locally; official OpenAI-compatible examples used instead. |
| Kimchi Coding | API key or service key / Chat | Vendor endpoint. R9 `kimchi.js` and official service-key docs. Browser key handoff does not make the resulting credential an OAuth refresh-token account. |
| Kilo | Gateway API key / Chat | Vendor endpoint, optional organization ID/header. OR `config/providers/registry/kilo-gateway/index.ts`. Not the older device-login/OpenRouter connector. |
| Muse Code | Meta device OAuth → subscription-bound inference key / Responses | Credential name only; auth/inference origins remain fixed. No local reference adapter found. Existing approved CLI research and `muse-code-verification-2026-09-16.md` are the evidence; no new live probe here. |
| Meta Model API | Model API key / stateless Responses | Fixed endpoint is now read-only during onboarding and is not offered as an editable credential field. `litellm-1.97.0/tests/test_litellm/llms/openai_like/test_meta_provider.py` and existing Meta contract. Separate from Muse Code subscription. |
| GroqCloud | Groq API key / Chat | Vendor endpoint. GW `groq/api.ts`. Groq usage-envelope handling retained. |
| DeepSeek Platform | Platform API key / Chat | Vendor endpoint. GW `deepseek/api.ts`. Base `/v1` plus `/chat/completions` is equivalent to the reference's split. |
| Mistral AI Studio | Studio API key / Chat | Vendor endpoint. GW `mistral-ai/api.ts`. Vendor-specific seed, paired tool IDs and thinking representation retained. |
| Cerebras Cloud | Cloud API key / Chat | Vendor endpoint. GW `cerebras/api.ts`. No invented OAuth workflow. |

Hosted endpoint editing remains bounded by backend trusted-origin validation; it
does not authorize arbitrary proxies. Environment-managed values remain locked.
The reference `langfuse-4.15.0` is observability software, not provider-auth authority.

Official fallback sources checked:
[Kimchi service keys](https://docs.kimchi.dev/docs/service-keys),
[Poolside OpenAI examples](https://docs.poolside.ai/api/openai-api-examples),
[OpenCode Zen](https://opencode.ai/docs/zen/),
[Kilo Gateway authentication](https://kilo.ai/docs/gateway/authentication).

## Credential facts and actions

OAuth is an authentication mechanism, not a promise of a universal account API.
Facts below are shown only if returned and valid. Provider identifiers remain
identifiers; opaque tier codes are not renamed to speculative retail plans.

| Family | Facts retained in management modal | Provider-specific action / behavior |
| --- | --- | --- |
| Antigravity | Per-model remaining quota and reset; optional named group/bucket windows; returned tier; all valid credit balances and minimum credit amounts | Explicit inline confirmation for Polaris' per-credential credit-use policy. Does not buy credits. New optional account RPCs never call `onboardUser`. |
| Grok Build | Monthly allocation/use/reset, optional weekly percentage/reset, returned product usage windows, subscription tier and on-demand/prepaid facts when present in billing | No subscription/credit-purchase action is invented. Unknown units remain provider numeric facts, not guessed currency. |
| Codex | Session/weekly/review and additional model-specific windows, plan, returned reached flags, reset-credit count and credit balance/availability/unlimited flags | Read-only account facts; no implicit reset-credit redemption or purchase. |
| Claude Code | Session, weekly and model-scoped windows; returned plan; extra-usage enabled state, spend, monthly cap, utilization and reset | Extra-usage spend/cap values are cents and formatted as currency. No unsupported upstream billing-setting mutation. |
| Kiro | Subscription title; resource allocation/use, trial and bonus separately, status/expiry/reset; overage flag | Quota retrieval now uses Kiro's regional `getUsageLimits`, not Google handling. Reauthentication is offered only for OAuth credentials, never API keys. |
| Muse Code | Returned subscription plan/tier, session duration, session/weekly usage/reset and observation timestamp | Existing fresh mint/eligibility flow retained. Missing fresh usage is not replaced with an old full-quota value. No billing-family fallback. |

API-key credentials retain the shared safe management surface: display identity,
enabled state, declared models, provider-relevant connection editor, explicit test,
diagnostics, import/export/delete. They do not require an email and do not acquire
OAuth quota/reauthentication controls. Kiro keys can use the Kiro usage capability;
this does not change their authentication type.

Secrets remain behind explicit reveal/download controls. Opening a modal fetches
safe configuration/models/quota/diagnostics, not the raw credential payload.
Bulk actions retain the existing provider and selection scoping.

### Correctness repairs

- Missing/invalid Codex usage is no longer treated as 0% used / 100% remaining.
  Missing plan, reached flags and reset-credit count are not synthesized.
- The modal no longer discards provider account facts while extracting quota cards.
  Codex/Claude valid plan or credit facts survive even if rate windows are absent.
- Grok missing weekly percentage is unknown; a zero monthly allocation is not 100%
  remaining. Optional product windows and billing facts are retained.
- Kiro card summary combines known active resource/trial/bonus balances; it does not
  use the minimum percentage of an expired trial. Incomplete active allocations
  produce an unknown summary. Overage enabled does not imply unlimited/full quota.
- Antigravity reset timestamps remain UTC on the wire and are formatted by the
  browser, replacing a fixed UTC+8 conversion. Unknown model fractions stay unknown.
  Optional group windows constrain the card summary; they do not overwrite model
  quotas. Failure to load optional account details does not discard model quotas.
- Muse's actual session duration is preserved; the UI does not assume every session
  is a fixed duration. Observation time is visible.
- New Kiro and optional Antigravity response reads have size/time bounds, no
  redirects and allowlisted display fields. Upstream bodies/tokens are not emitted
  as management errors or quota logs.

Additional source details: CP `grok_account.rs` (`quota_from_payload`),
`kiro_oauth.rs` (`getUsageLimits`), `quota.rs` (`availableCredits`),
`claude_account_desktop_auth.rs` (extra-usage field semantics);
OR `services/codexQuotaFetcher.ts`, `services/usage/kiro.ts`,
`services/usage/antigravityWeeklyQuota.ts`. Desktop-only client controls from these
projects are not automatically appropriate for a browser gateway.

## Verification

- Focused quota/credential tests: **75 passed** (six OAuth families, configuration,
  route dispatch, invalid/partial data and bounded read-only RPCs).
- `provider_quota_smoke.py`: **28** family/theme/viewport combinations, all 15
  locales, missing values, inline credit confirmation/cancellation, error and
  retry. No automatic payload reveal or inference. Inspected desktop light and
  mobile dark captures under `temp/provider-fidelity/`.
- `extended_providers_smoke.py`: **23** catalog cards in 15 locales, **13** extended
  forms, **130** responsive/theme cases, **39** JSON/ZIP/rejection imports against
  disposable storage, plus actual connection editing. Meta fixed-origin form and
  editor contracts are covered.
- `provider_ownership_smoke.py`: older provider workspaces at 320/768/1024/1440px,
  light/dark, single-owner settings, Claude Platform save/reset isolation.
- `muse_provider_smoke.py`: explicit device start/check/save/restart, no polling,
  offline import, advanced name, 15 locales, five widths and both themes.
- Strict frontend i18n: **1,357 referenced keys**, all 15 locales. Backend management
  message audit passed. These checks are not native-speaker certification.
- Fast quality gate passed: backend/tool lint and formatting, bytecode, test
  manifest, JavaScript/YAML/shell syntax and whitespace.
- Standard-library trace **with missing-line accounting** on the focused suite:
  new `antigravity_usage` **92.2%**, new `kiro_usage` **92.4%** statement coverage;
  `codex_usage` 84.2%, `anthropic_usage` 87.0%, `xai_billing` 86.8%, `muse_code` 93.5%.
  These are module statement measurements, not branch or total-repository coverage.
- Initial full core run: 2,243 tests, 22 existing optional database skips, two
  obsolete contract assertions (Codex-only plan gate and Kiro-without-quota).
  Updated them to assert the expanded capability gates, not skip or relax provider
  isolation; the affected 57-test slice passed.
- Final full core run after all fixes and the two additional regressions:
  **2,245 tests, OK, 22 existing optional PostgreSQL/MongoDB live-test skips**.
  No new skipped test or suppression. Final fast and both locale audits passed.

Large-file assessment: provider RPC/parsing lives in focused new modules; shared
panel/API files receive narrow dispatch/allowlist hooks only. Quota display facts
and translations are extracted into dedicated frontend helpers. Existing large
registry/management files are not expanded with new provider-specific protocols.

## Limits and operational notes

- This is source comparison, deterministic protocol regression and synthetic browser
  verification. No live claims about provider uptime, every subscription tier or
  every model are made. The unpublished OAuth account endpoints can change upstream.
- Antigravity group windows require a project and a successful optional RPC; absent
  groups are not fabricated as daily/weekly limits. The UI preserves returned names
  instead of guessing bucket durations.
- No speculative controls were added for payment methods, plan upgrades, credit
  purchases or unknown upstream settings. Full vendor-console parity is outside the
  gateway's credential-management scope.
- Existing protocol limits from the previous conformance audit still apply (e.g.
  supported generation options and native reasoning replay). A source match or
  successful catalog fetch alone is not a successful inference test.
- Existing cookies, credential database, tokens and deployed containers were not
  changed. Backend additions require the normal project restart/deployment to be
  loaded; this turn does not restart or deploy the user's running instance.

Design decision: retain the established compact management modal and provider
workspaces, add capability-driven facts/actions, and fix incorrect data semantics
rather than flattening unlike OAuth providers into one generic quota representation.
