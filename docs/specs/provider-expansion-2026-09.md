# Provider expansion — September 2026

Status: scope and implementation choices delegated to Codex by the user on 2026-09-15.
Product remains Polaris. Existing production plans remain completed historical records.

## Capability map and build order

| Module | Responsibility | Depends on |
| --- | --- | --- |
| provider-boundary | Credential/catalog/runtime hooks and safe management routes | — |
| hosted-api-providers | Kimi Platform, Cloudflare, NVIDIA, Poolside, Kimchi, Kilo | provider-boundary |
| opencode-provider | Zen/Go model-aware protocol dispatch | provider-boundary |
| kiro-provider | API key, discovery, AWS EventStream conversion | provider-boundary |
| provider-console | Onboarding, private settings, logos, localization | preceding contracts |

Order: boundary contracts → three transport groups in parallel → console/integration → gates.

## Objective and scope

Add all eight requested products as real routable providers. Kiro starts with API keys;
browser OAuth, CLI execution and automatic disk-token harvesting are excluded. OpenCode
supports Zen and Go via explicit credential product selection. Provider settings stay
on Providers; account/organization/profile context stays with its credential.

## Boundary contract

Persist provider, credential_type=api_key, api_key, model_ids and provider-specific
connection metadata in the existing credential storage; no schema/dependency changes.
Each transport converts the existing canonical Gemini request/response boundary.
Discovery and inference authorization are distinct: a public catalog does not prove
a key works. Explicit connection tests may call the selected model; never silently
spend on a completion merely to browse a catalog. No invented usage/quota/model claims.

Validate URLs and untrusted catalogs; prohibit credential-bearing redirects, userinfo,
query credentials, unsafe account IDs, unbounded pagination/frames and leaked errors.
Kiro binary decoding checks lengths/CRCs and preserves cancellation/terminal semantics.
OpenCode selects Chat/Responses/Messages/Gemini by supported model metadata/family;
unsupported semantics fail closed. Streaming usage is cumulative, not summed per event.

## Structure and style

Python transport helpers under backend/core; authenticated management under
backend/core/panel/providers; tests under backend/tests. Vanilla JS/CSS/HTML keeps
the existing console design. Example: `async def discover_models(credential: dict) -> list[str]`.
Prefer narrow dispatch hooks over eight new branches in oversized runtime files.

## Commands and verification

- Focused: `.venv/Scripts/python.exe -m unittest backend.tests.test_hosted_providers`
- Core: `.venv/Scripts/python.exe -m backend.tests --suite core`
- Static: `.venv/Scripts/python.exe tools/quality_gate.py fast`
- Locales: `node tools/i18n-audit.mjs` and `.venv/Scripts/python.exe tools/backend-i18n-audit.py`
- Browser: disposable fixture-backed Providers flows, desktop/mobile and light/dark.

Tests precede logic changes. Cover success, invalid key, permissions, limits, malformed
catalog/stream, tools, cancellation, nonstream aggregation and existing-provider regressions.
Live account verification requires user-provided credentials; fixture success is not a live claim.

## Boundaries and acceptance

Always: reuse authorization/audit/storage/diagnostics, preserve secrets and existing data,
normal-weight placeholders, provider-specific descriptions, fifteen locale parity, bounded I/O.
Ask first: dependency/schema/CI changes or additional auth families.
Never: weaken tests, expose incomplete providers as supported, fake client identity,
install vendor CLIs, log credentials, modify reference repos, push/release without instruction.
Done requires actual runtime registration, usable onboarding, model discovery/routing,
truthful capabilities, passing affected and full gates, and documented limitations.

## Sources

- https://platform.kimi.ai/docs/api/chat
- https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/
- https://docs.api.nvidia.com/nim/reference/meta-llama-3_1-8b-infer
- https://docs.poolside.ai/api/openai-api-examples
- https://docs.kimchi.dev/docs/inference-quickstart
- https://kilo.ai/docs/gateway/api-reference
- https://opencode.ai/docs/zen/ and https://opencode.ai/docs/go/
- https://kiro.dev/docs/getting-started/authentication/

Kiro direct HTTP transport and Kimchi metadata discovery are reference-verified, not
promised public interfaces. Reference repositories are read-only; independently implement
protocol facts and retain MIT attribution if substantial source is adapted.
