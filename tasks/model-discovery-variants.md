# Compact model discovery

## Scope

Owner approved removing automatically generated feature variants from model discovery.
Keep concrete provider variants and enabled configured aliases. Preserve explicit prefixed
inference IDs so saved client configurations continue to work. Advanced modes remain manual
model-ID opt-ins; no new UI switch, global default, database migration, or Oracle deployment.

## Implementation

- Primary OpenAI and Gemini discovery share a stable, deduplicated catalog-plus-alias list.
- Removed only synthetic prefix generation; inference routers are unchanged.
- Documented manual opt-in, client-picker impact, and anti-truncation usage/latency costs.

## Verification

- RED: new public-boundary discovery tests failed on unwanted synthetic copies and duplicates.
  Legacy prefixed streaming requests passed before the implementation change.
- GREEN: 47 tests passed across model discovery, model pool, public streaming lifecycle,
  anti-truncation lifecycle, compatibility guard, and Hermes reasoning.
- Task quality gate passed: lint, formatting, compilation, test manifest, JavaScript/YAML/shell
  syntax, whitespace, and the same 47 tests. Git Bash required an approved run outside the
  sandbox after Windows denied signal-pipe creation. Combined tests emitted two SQLite
  unclosed-connection ResourceWarnings; all assertions passed, with no warning suppression.
- Review: only discovery assembly changes at runtime; protocol envelopes, authentication,
  inference routing, provider IDs, and configured-alias eligibility remain unchanged. Stable
  deduplication adds no dependency or upstream call. No blocking findings in this scoped change.
- Upstream responses are stubbed in boundary tests; no live provider calls or Oracle writes.
- Existing unrelated working-tree changes are preserved. No commit or release performed.
