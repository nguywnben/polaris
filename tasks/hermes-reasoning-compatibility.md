# Hermes Chat Completions reasoning compatibility

## Scope and acceptance

- Reproduce the reported `reasoning_effort` HTTP 400 using deterministic public-route tests.
- Accept the OpenAI effort vocabulary and retain the intent until the actual routed model and
  provider are known. Translate supported Gemini controls; forward OpenAI Platform/Codex controls
  in their native shapes. Other adapters continue to fail explicitly, not silently drop controls.
- Owner decision (2026-09-19): `none` must fail clearly when thinking cannot be disabled. Never
  substitute low/minimal, retry without the control, or penalize a credential for this client error.
- Keep effort in cache identity, remove internal intent from upstream JSON, and trace translation.
- Preserve unrelated installer changes, existing reasoning-history restrictions and the immutable
  R1 corpus; describe the additive Chat extension separately. No deployment or publication.

## Evidence and design

The supplied Hermes log identifies `gemini-3.8-flash-tiered`; both stream and non-stream calls
fail at Polaris input validation, before dispatch. It does not contain the exact effort value.
CLIProxyAPI's Antigravity/OpenAI translator and OmniRoute's OpenAI/Gemini translator under the
user-supplied reference directory map reasoning by provider/model. Their fallback/clamping rules
are not copied: unsupported semantics remain explicit errors here.

Authoritative references checked 2026-09-19:

- https://ai.google.dev/gemini-api/docs/openai (effort-to-budget/level mapping and disabling limits)
- https://ai.google.dev/gemini-api/docs/thinking (model-specific levels)
- https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create

Policy lives in a small separate module. `core/api/primary.py` and the large OpenAI converter get
only intent/transport glue: splitting their unrelated transport/conversion machinery is outside
this fix. This is the required extraction assessment for existing files above 1,500 lines.

## Verification

- Independent reproduction: eight valid-effort cases fail with the reported 400 before the fix;
  twenty malformed-value cases remain rejected.
- GREEN: 155 tests passed across 12 directly affected modules via `tools/quality_gate.py task`:
  Hermes reasoning, reasoning policy/transport, protocol corpus, R1 compatibility guard,
  request normalization, model pool, Muse integration, extended provider runtime, response cache,
  trace contract/service and gateway pipeline. Static lint, formatting, bytecode, test manifest,
  JavaScript/YAML/shell syntax and whitespace checks passed. Git Bash needed sandbox escalation
  because Windows denied its signal pipe; no validation was disabled.
- Public HTTP tests cover both Chat endpoints, both stream modes, low/high success, malformed
  effort rejection and strict `none` rejection. The primary `none` case uses the real preparation
  and dispatch error path and proves no upstream call and no credential health penalty.
- Final payload tests cover Antigravity, AI Studio, OpenAI Platform and Codex. Unit tests cover
  per-attempt model mapping, non-mutation, cache separation, defaults and content-free tracing.
- Review checked the input boundary, actual selected-model dispatch, internal-marker removal,
  cache identity and preservation of the immutable R1/stream-options fingerprints. No new
  dependency, field-ignore relaxation, skipped test or live credential use.
- Coverage package is not installed in the current environment; no numerical changed-line
  coverage claim is made. Full release/browser/container gates and live-provider smoke were not
  run for this backend-only task. Oracle is unchanged; deployment/publication remain separate.

Follow-up: the owner subsequently authorized updating Oracle. The completed private deployment,
backup/rollback references and real-provider checks are recorded in
[Oracle reasoning update](oracle-reasoning-update.md). No public release was made.
