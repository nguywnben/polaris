# Provider conformance audit — 2026-09-16

## Verdict and scope

Reviewed the authentication/transport identities of all **22 console provider
variants**, then inspected shared catalog, tool-history, stream, import and
connection-setting boundaries. Repaired reproducible defects below. This is a
source-and-contract audit, **not live certification of 22 upstream services**.
No real key, login, paid inference, production database or reference repository
was modified. No provider, authentication family, dependency or Docker release
was added. Existing uncommitted work was preserved.

Reference implementations are evidence, not specifications to copy blindly.
In particular, Kimi Coding is not Kimi API Platform, and a reference project's
browser-login option does not make an officially supported API key incorrect.

## Evidence map

Reference root: `C:/Users/nben6/Downloads/repo`. Paths in the evidence column are
relative to that root. Polaris implementation paths are under `backend/core`.
“Retained” means the checked identity/transport agrees with the cited evidence;
it does not mean every model or native feature has been live-tested.

| Console provider | Authentication and upstream shape retained | Reference evidence / audit result |
| --- | --- | --- |
| Google Antigravity | Google OAuth; Code Assist internal Gemini envelope; account refresh | `9router-0.5.35/open-sse/providers/registry/antigravity.js`, `cockpit-tools/src-tauri/src/modules/oauth.rs`; inspected `antigravity.py`. Private service, not the AI Studio key API. |
| Google AI Studio | `x-goog-api-key`; native Gemini `generateContent` / SSE | `9router-0.5.35/open-sse/providers/registry/gemini.js`; `google_ai_studio.py`. **Fixed catalog pagination.** |
| Grok Build | xAI OAuth access/refresh tokens; Chat-compatible inference | `cockpit-tools/src-tauri/src/modules/grok_oauth.rs`, `9router-0.5.35/open-sse/providers/registry/xai.js`; `xai.py`. **Fixed implicit tool IDs.** |
| SpaceXAI Console | xAI API key / Bearer; Chat | Same xAI registry; `xai.py`. Kept separate from OAuth credentials. **Fixed implicit tool IDs.** |
| Codex | ChatGPT OAuth; Codex Responses backend; upstream SSE even for non-stream clients | `9router-0.5.35/open-sse/providers/registry/codex.js`, `CLIProxyAPI-7.2.137/internal/runtime/executor/codex_executor.go`; `codex.py`. **Fixed implicit tool IDs.** |
| OpenAI Platform | Platform API key / Bearer; Chat adapter | `9router-0.5.35/open-sse/providers/registry/openai.js`; `openai_platform.py` delegates conversion to `xai.py`. **Fixed malformed catalog IDs and implicit tool IDs.** |
| Claude Code | OAuth Bearer plus OAuth beta header; Messages | `CLIProxyAPI-7.2.137/internal/runtime/executor/claude_executor.go`; `anthropic.py`. **Fixed catalog pagination and implicit tool IDs.** |
| Claude Platform | `x-api-key`, Anthropic version header; Messages | Same executor distinguishes API key/OAuth; `anthropic.py` selects separate Platform settings. **Fixed catalog pagination, malformed IDs and implicit tool IDs.** |
| Ollama | Local connection, optional cloud Bearer key; `/api/tags` and `/api/chat` | `9router-0.5.35/open-sse/providers/registry/ollama-local.js`, `open-sse/executors/ollama-local.js`; `ollama.py`. Local HTTP is intentional, not an OAuth provider. |
| Kimi API Platform | Moonshot platform key / Bearer; Chat | `OmniRoute-3.8.49/open-sse/config/providers/registry/kimi/index.ts`, `gateway-1.15.2/src/providers/moonshot/api.ts`; `hosted_providers.py`. International default plus explicit China endpoint, not `api.kimi.com/coding`. **Added option-loss guard.** |
| Kiro | Browser PKCE OAuth / AWS device OAuth; optional API key; binary AWS EventStream | `cockpit-tools/src-tauri/src/modules/kiro_oauth.rs`, `OmniRoute-3.8.49/open-sse/executors/kiro.ts`; `kiro*.py`. Runtime region and AWS token region are distinct. API keys alone use `tokentype: API_KEY`. No automatic login completion was restored. |
| Cloudflare Workers AI | Bearer API token plus Account ID; account-scoped Chat endpoint | `OmniRoute-3.8.49/open-sse/executors/cloudflare-ai.ts`; `hosted_providers.py`. Catalog uses paginated management search. Text-only parts already flatten to strings, so no speculative converter replacement. **Added option-loss guard.** |
| NVIDIA NIM | Hosted NVIDIA API key / Bearer; Chat | `9router-0.5.35/open-sse/providers/registry/nvidia.js`; `hosted_providers.py`. Hosted integration, not arbitrary self-hosted NIM endpoints. **Added option-loss guard.** |
| OpenCode | API key, explicit Zen/Go plan; family-specific Chat / Responses / Messages / Gemini | `9router-0.5.35/open-sse/providers/registry/opencode.js`, `opencode-go.js`; `opencode.py` and official endpoint tables. Public catalog discovery does not authenticate the key. |
| Poolside Platform | Platform API key / Bearer; hosted Chat with reasoning replay | No direct `inference.poolside.ai` implementation found in the searched reference source files. Verified against official Poolside examples instead; `hosted_providers.py`. **Added option-loss guard.** |
| Kimchi Coding | API/service key / Bearer; Chat, separate model metadata endpoint | `9router-0.5.35/open-sse/providers/registry/kimchi.js`, `open-sse/executors/kimchi.js`; `hosted_providers.py`. Official docs confirm keys; reference browser login is not required. **Added option-loss guard.** |
| Kilo | Gateway API key / Bearer; optional organization header; Chat | `OmniRoute-3.8.49/open-sse/config/providers/registry/kilo-gateway/index.ts`; `hosted_providers.py`. This is the public Gateway product, not 9router's older device-login/OpenRouter route. **Added option-loss guard.** |
| Meta Model API | Model API key / Bearer; stateless Responses | `litellm-1.97.0/tests/test_litellm/llms/openai_like/test_meta_provider.py`; `meta_model_api.py`, native boundary/stream tests. Not a Muse Code subscription. Contributor models remain an explicit choice. |
| GroqCloud | Groq API key / Bearer; Chat | `gateway-1.15.2/src/providers/groq/api.ts`, `litellm-1.97.0/litellm/llms/groq/chat/transformation.py`; `hosted_providers.py`, `_platform_stream_event`. Non-chat/compound catalog entries filtered; Groq-specific usage envelope retained. |
| DeepSeek Platform | Platform API key / Bearer; Chat | `gateway-1.15.2/src/providers/deepseek/api.ts`; `hosted_providers.py`. Unsupported seed rejected; reasoning replay has gateway limits below. |
| Mistral AI Studio | Studio API key / Bearer; Chat | `gateway-1.15.2/src/providers/mistral-ai/api.ts`; `hosted_providers.py`. `random_seed`, paired nine-character tool IDs and thinking chunks kept distinct from generic Chat. |
| Cerebras Cloud | Cloud API key / Bearer; Chat | `gateway-1.15.2/src/providers/cerebras/api.ts`, `9router-0.5.35/open-sse/providers/registry/cerebras.js`; `hosted_providers.py`. Kept vendor-specific base URL; no OAuth invented. |

`langfuse-4.15.0` was inventoried but not treated as upstream protocol authority:
it is an observability reference, not a replacement for vendor auth contracts.
9router's `opencode` entry is an anonymous/free variant; it is not a reason to
replace Polaris' user-owned Zen/Go keys with a public key or forged client identity.

## Confirmed defects repaired

1. **Missing catalog pages.** Google read only the first `models.list` page;
   Claude read only the first `/models` page. Both now follow their own cursor
   format, deduplicate, reject cycles/invalid cursors, cap traversal at 20 pages
   and enforce a 30-second total deadline. The accumulated catalog remains
   bounded by the existing 500-model limit. No upstream-supplied next URL is
   followed, and keys remain in headers. Partial-page failures are not success.
2. **Invented model identifiers.** `str(None)` and numeric IDs could become
   catalog entries in Claude/OpenAI. Only string IDs are now accepted there.
3. **Mismatched function call/result IDs.** Legacy converters derived fallback
   IDs independently from part indexes (Claude sometimes used a function name
   on one side). Text preceding a call or reversed result order broke pairing.
   `tool_history.py` reuses the existing hosted history algorithm across Chat,
   Responses and Messages. Caller data remains unchanged; ambiguous name-only
   matches fail rather than guessing. Hosted reasoning is preserved while
   converting the entire conversation, not disconnected messages.
4. **Silently ignored generation options.** Only Groq/DeepSeek/Mistral/Cerebras
   rejected unrepresented canonical settings. Kimi/Cloudflare/NVIDIA/Poolside/
   Kimchi/Kilo now reject those settings too, rather than ignoring a requested
   thinking configuration or unsupported output MIME type. This does not claim
   every vendor model accepts every representable parameter.
5. **Stale documentation.** Removed the inaccurate statement that all additional
   providers are API-key-only; Kiro OAuth and renewal are explicitly documented.

Regression tests failed before repairs: six catalog tests, three legacy tool
converter subcases, and twelve hosted option-loss subcases. Existing hosted
history tests also caught the per-message conversion interaction during repair;
those tests were retained and the implementation corrected.

## Shared boundaries and remaining limits

- JSON/ZIP imports are provider-scoped, offline and not proof of access. Existing
  onboarding deliberately distinguishes catalog availability from an explicit
  inference test. Advanced account/organization/plan/region fields remain scoped
  to the relevant provider and credential, not global settings for every vendor.
- Kiro refresh, browser callback ownership/PKCE, AWS device grants, binary CRCs,
  tool argument buffering and terminal-event handling have automated coverage.
  Its direct inference API and Antigravity's internal service can still change
  without a public compatibility promise. Matching another client is not a
  vendor stability guarantee.
- OpenCode protocol selection is deliberately limited to known families. Meta
  coding-model allowlisting is deliberately finite. A future upstream model may
  require an adapter/catalog update rather than being guessed into a protocol.
- DeepSeek/Mistral default reasoning behavior follows the existing gateway's
  replay-safe Chat boundary, not full native-client parity. OpenCode non-Gemini
  signed reasoning history remains unsupported. See [API platform limits](api-platforms.md)
  and [Meta's native boundary](meta-model-api.md).
- Cloudflare multimodal support, vendor-specific generation parameters outside
  Polaris' canonical representation, quota accuracy and every model's tool/image
  support have **not** been certified by this audit. No capability was added on
  the assumption that all OpenAI-compatible servers behave identically.
- Still required before declaring live stability: for each actual account/region/
  plan, explicitly test discovery, a non-stream completion, a streaming completion,
  a tool-call/result round trip, and OAuth renewal where applicable. Use user-owned
  keys through the console; do not place them in source or chat. These calls may
  cost money and were not performed here.

## Official sources checked

- [Google model pagination](https://ai.google.dev/api/models)
- [Claude model pagination](https://platform.claude.com/docs/en/api/models/list)
- [Mistral Chat API](https://docs.mistral.ai/api/endpoint/chat)
- [Cloudflare OpenAI compatibility](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)
- [OpenCode Zen](https://opencode.ai/docs/zen/)
- [Poolside hosted examples](https://docs.poolside.ai/api/openai-api-examples)
- [Kimchi API/service keys](https://docs.kimchi.dev/docs/service-keys)
- [Kilo Gateway authentication](https://kilo.ai/docs/gateway/authentication)

## Verification

- Focused catalog suite: 39 tests passed after the catalog repair.
- Legacy/hosted/OpenCode/platform suite: 103 tests passed after the tool repair.
- Hosted/platform option validation: 37 tests passed after the final guard change.
- `tools/provider_workspace_smoke.py`: passed on a disposable runtime.
- `tools/extended_providers_smoke.py`: 22 cards / 15 locales; 13 forms;
  130 responsive/theme cases; 39 real JSON/ZIP/rejection imports; no page errors.
- Fast quality gate passed (Git Bash required execution outside the Windows
  sandbox to create its signal pipe).
- Full backend run: initial run exercised 2,129 tests with 22 optional skips and
  one file-enumeration error: an unstaged, previously deleted credit-panel test
  remained in `git ls-files`. Final verification used a disposable Git index
  describing the current source snapshot, without modifying the real index or
  restoring retired files. **Final result: 2,130 tests in 317.447 seconds,
  OK (22 existing optional skips): 2,108 passed, no failures or errors.**
