# Meta Model API integration

Status: implemented and locally verified on 2026-09-15; live vendor validation pending.

## Objective

Add Meta Model API as an API-key provider in Polaris, distinct from Muse Code
subscriptions and unofficial Meta web-session integrations. Integrate with existing
credential, routing, diagnostics, import/export and console workflows.

## Scope and acceptance

- Provider ID `meta`, display name `Meta Model API`, homepage https://dev.meta.ai.
- Rename the supplied `frontend/assets/providers/meta-color.png` to
  `meta-model-api-logo.png`; preserve the supplied artwork.
- Authenticate against https://api.meta.ai/v1 using an API key. Discover hosted
  models using authenticated model-list requests, without generating paid content.
- Expose supported Muse Spark models, including explicit Contributor variants;
  never silently choose a Contributor variant or replace a Standard model with one.
  Explain that Contributor prompts/completions may be used for training.
- Prefer stateless Responses transport (`store: false`). Preserve tool-call IDs,
  intermediate message phase, encrypted reasoning replay and usage through the
  supported canonical request/response boundary. Do not advertise reasoning replay
  unless round-trip tests demonstrate preservation.
- Support existing Polaris client entry points, including Responses and Anthropic
  Messages, with truthful capability validation. Provider-side protocol selection
  must follow documented semantics, not assume every OpenAI field is implemented.
- Include key onboarding, connection tests, JSON/ZIP credential import, editing,
  export and pool identity. Advanced settings belong only to this provider.
- Match current catalog sizing, responsive layouts, light/dark appearance,
  placeholder and focus rules, and all fifteen console locales.
- Do not add image-generation, speech-transcription, background-job or hosted-file
  management APIs as an incidental expansion of this coding-provider integration.
  Do not list incompatible model families as routable text models.
- After integration, recommend 3–6 absent providers grounded in the read-only
  reference repositories under C:/Users/nben6/Downloads/repo; do not implement them.

## Structure and style

Existing Python/FastAPI/httpx runtime and vanilla JS/CSS console; no new dependencies
or database schema. Transport under backend/core, management hooks under
backend/core/panel/providers, regression tests under backend/tests, console in
frontend/js/features and provider locale overlays. Follow existing interfaces such
as `async def discover_models(credential: dict) -> list[str]`.

## Verification commands

- `.venv/Scripts/python.exe -m backend.tests --suite core`
- `.venv/Scripts/python.exe tools/quality_gate.py fast`
- `node tools/i18n-audit.mjs`
- `.venv/Scripts/python.exe tools/backend-i18n-audit.py`
- `.venv/Scripts/python.exe tools/extended_providers_smoke.py --capture`

Write focused transport and management tests before implementation: invalid keys,
catalog bounds, malformed streams, function-call history, reasoning replay,
cancellation, usage accounting and isolation from other providers. Extend disposable
browser tests to the eighteenth provider. Fixture success is not live Meta validation;
no live key was supplied, and no paid request is authorized by merely reading docs.

## Boundaries

Always: preserve existing credentials/data, reuse permission/audit checks, sanitize
errors, bound external payloads, allow only verified HTTPS origins, prohibit
credential-bearing redirects, and document unsupported semantics.
Ask first: new dependencies/schema, wider provider features or deployment changes.
Never: use web cookies, harvest tokens, enable training-tier models implicitly,
change the reference repos, weaken tests, or claim untested live compatibility.

## Sources inspected on 2026-09-15

- https://dev.meta.ai/docs/getting-started/overview/ (legacy overview examples use 1.1)
- https://dev.meta.ai/docs/models (current 1.3 and Contributor model IDs and tiers)
- https://dev.meta.ai/docs/protocols/responses (stateless replay, phase, streaming,
  unsupported parameters and storage semantics)

Read authentication, Messages, reasoning and API-reference contracts before coding
their respective behaviors. Browser-rendered documentation is accessible even though
the initial web-text fetch returned a login-only page.

## Implementation evidence

The native Responses boundary and its trade-offs are recorded in ADR-014. The
provider guide distinguishes supported Responses replay from the narrower existing
Messages/Chat translation subset; it does not claim full Claude Code tool-search
or adaptive-thinking compatibility.

- Final full core run: 2,072 tests, 22 optional skips, no failures.
- Latest focused run: 113 tests passed, including the additional Messages HTTP
  default/tool/error cases, native replay, boundary, capability and compatibility tests.
- Fast quality gate passed; both locale audits passed (1,330 frontend keys across
  all 15 locales); dependency audit found no known vulnerabilities.
- Disposable browser run passed: 18 cards, 54 responsive/theme form cases and
  27 real fixture import/rejection cases; no JavaScript page errors.
- No live Meta key or paid inference request was used.
