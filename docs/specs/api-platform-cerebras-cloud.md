# Cerebras Cloud integration

Status: implementation approved by the owner on 2026-09-15. Module: `cerebras-cloud` in [the approved capability map](api-platforms-map.md).

## Objective and acceptance

Add `cerebras` as an API-key provider named **Cerebras Cloud**, linked to https://cloud.cerebras.ai/.
Use https://api.cerebras.ai/v1 as the official default API root, with Bearer authentication.
Logo source: https://cloud.cerebras.ai/images/logo/cb-fav-144.png

- Add keys, validate model discovery, explicitly test inference, edit/disable/delete credentials, and import/export JSON/ZIP through existing Polaris workflows.
- Discover usable chat models dynamically; do not invent model availability, quota, pricing, or authentication success.
- Support streaming and non-streaming text and documented function tools through the existing primary routing, quality, retry and usage pipeline.
- Keep the supplied raster logo resolution; verify supported generation fields and streaming usage.
- Keep advanced settings local to this provider's credential form: API endpoint only unless official documentation proves another connection field necessary.
- Preserve equal catalog-card sizing, responsive layouts, both themes, conditional in-input visibility controls, toast/focus rules, and normal-weight placeholders.
- Add complete contextual descriptions in all 15 console locales; keep the exact provider name untranslated.

## Structure and stack

Python/FastAPI 0.139.0, Pydantic 2.13.4, httpx 0.28.1 from `requirements.lock`; existing vanilla JavaScript/CSS console.
Registration: `backend/core/provider_registry.py`; transport: existing hosted-provider module or a narrowly scoped adapter when the documented protocol requires one.
Console: `frontend/js/features/extended-providers.js`, locale overlay and `frontend/assets/providers/`.
Tests: `backend/tests/test_*.py`; browser slice: `tools/extended_providers_smoke.py`.
No public route/schema changes are planned.

## Code style

Follow existing snake_case backend interfaces, for example:

```python
async def discover_models(data: dict) -> list[str]:
    """Return validated chat model IDs without generating paid content."""
```

Reuse existing credential normalization and bounded HTTP helpers. Do not duplicate authentication/storage logic or refactor unrelated providers.

## Commands and verification

- Focused tests: `.venv/Scripts/python.exe -m unittest backend.tests.test_hosted_providers` plus the new provider-specific module.
- Core gate: `.venv/Scripts/python.exe -m backend.tests --suite core`.
- Static gate: `.venv/Scripts/python.exe tools/quality_gate.py fast`.
- Locales: `node tools/i18n-audit.mjs` and `.venv/Scripts/python.exe tools/backend-i18n-audit.py`.
- Browser: `.venv/Scripts/python.exe tools/extended_providers_smoke.py --capture`.

Write failing contract tests first. Cover key/endpoint validation, trusted HTTPS origins, redirect refusal, safe upstream errors, bounded catalogs, tool history and fragmented streaming/usage. Add selected-provider import rejection and management tests using a disposable store.
Verify all four additions in one bounded browser matrix at 360/768/1024/1440 CSS pixels, light/dark, and all locales; never use production credentials for fixtures.
Live vendor compatibility remains unverified without a key. Discovery does not authorize paid inference tests.

## Boundaries

Always: preserve existing data, permissions, secret redaction, network restrictions, existing provider behavior and `CONSTRAINTS.md`.
Ask first: new dependencies/schema, materially broader API support, changes to global configuration, Docker deployment or remote publication.
Never: OAuth/token scraping, hardcoded real keys, arbitrary proxy destinations, invented quota values, silent loss of required reasoning/tool state, or claims of untested compatibility.
Out of scope: embeddings, speech, image generation, hosted files/jobs, batch, fine-tuning and vendor-hosted agents/tools.

## Sources

- https://inference-docs.cerebras.ai/resources/openai
- https://cloud.cerebras.ai/

Consult the official chat/tool/streaming references before implementing their fields. Reference repositories may corroborate behavior, but are not permission to execute their code.
