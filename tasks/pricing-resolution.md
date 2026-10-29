# Provider-aware pricing and honest cost coverage

## Approved objective
Implement the common pricing plan accepted in chat on 2026-09-20. Repair the
Antigravity `gemini-3.8-flash-tiered` mismatch without guessing prices for other
models. Unknown prices are not free usage. No production deployment or historical
cost rewrite is part of this task.

## Contract and scope
- Resolve provider-qualified exact prices, explicit provider-scoped aliases and
  operator prices; preserve existing plain manual overrides. Alias resolution is
  one hop, never an arbitrary suffix/fuzzy match.
- Import valid token prices across catalog providers. Unsupported pricing units
  or conditional tiers must not silently become a flat/free estimate.
- Retain the numeric cost compatibility API; add provenance and coverage to new
  ledger payloads and dashboard aggregates. Old rows remain unchanged and have
  unknown coverage, even after a catalog refresh.
- Explicit provider-reported cost overrides take precedence. Do not infer a
  billing amount from an arbitrary upstream field or subscription quota.
- Calculate disjoint normal input/cache-read/cache-write/output/reasoning token
  classes. Multimedia-only costs without normalized measurements stay unpriced;
  no new media endpoint or fabricated tariff is included.
- Budget checks keep using the same resolver; unknown hard-budget prices remain
  fail-closed. API-equivalent estimates are not subscription invoices.

## Implementation order and acceptance
1. Resolver: regression tests first; exact/alias/manual/unknown isolation and
   provenance, catalog prefix canonicalization, bounded configuration.
2. Ledger: additive payload fields, strict validation, backward-compatible old
   records, SQLite/PostgreSQL/MongoDB coverage parity, no SQL schema migration.
3. Console: known subtotal plus missing-cost coverage; all-unpriced does not show
   a misleading monetary zero. Translations in all existing locales.
4. Docs and verification: focused Python and DOM tests, affected budget tests,
   full backend suite and runtime browser check where available.

## Structure / style / commands
Python dataclasses and explicit optional values in `backend/core/pricing.py`;
durable payloads in `backend/core/usage_ledger.py`; tests in `backend/tests`;
existing vanilla-JS dashboard and locales under `frontend/js`.
Example contract: `resolution = resolve_model_pricing(model, provider=provider)`;
`None` rates mean unpriced, never a zero rate.

Focused: `.venv/Scripts/python.exe -m unittest backend.tests.test_pricing backend.tests.test_pricing_resolution`
Full: `.venv/Scripts/python.exe -m backend.tests --suite core`
Task gate: `.venv/Scripts/python.exe tools/quality_gate.py task --test-module test_pricing`
Existing CONSTRAINTS.md quality thresholds remain unchanged. Preserve unrelated
working-tree edits; do not commit those edits, publish, deploy, or change budgets.

## Evidence
- LiteLLM model_prices_and_context_window.json and Google Gemini API pricing,
  checked 2026-09-20: gemini-3.8-flash input/output/cache 0.75/3.75/0.075 USD/M.
- Runtime reproduction: 238 accepted catalog entries; base name resolves, tiered
  name does not. Alias changes pricing identity only, never the inference model.
- Reference implementations inspected: LiteLLM base_model/custom prices,
  OmniRoute scoped Antigravity prices, 9router provider overrides, Langfuse
  supplied-versus-computed cost handling. Their prices are not copied as authority.

## Progress
- [x] Resolver and catalog
- [x] Ledger and coverage
- [x] Dashboard and locales
- [x] Documentation and final checks

## Verification and review

- Independent regression tests cover provider isolation, one-hop alias target
  precedence, conservative pre-routing budget estimates and unknown-price denial.
- Ledger tests cover unchanged legacy serialization, strict status/source pairs,
  provider-reported cost priority and preservation of matching virtual-key estimates.
- Dashboard checks cover unknown / partial / free cost states at 360, 768, 1024
  and 1440 px; Chromium layout checks pass in all 15 locales, with zero page errors.
- Cross-model review identified and corrected missing alias budget admission,
  target fallback precedence, virtual-key provenance and legacy metadata validation.
  SQLite committed-reservation coverage was reproduced RED (0 instead of 2
  priced calls), corrected with kind-aware payload lookup, and verified GREEN.
- Full backend regression: 2,463 tests passed with 22 optional live-backend skips
  (12 PostgreSQL, 10 MongoDB; services not configured). After the final SQLite
  correction and two added integration tests, the task gate passed all 65 pricing
  tests, lint/format, compilation, JS/YAML/shell syntax and whitespace checks.
- The last focused coverage run includes ledger, pricing, statistics and dashboard
  aggregation: changed executable lines are 89/92 in pricing, 22/25 in usage
  recording, 24/26 in ledger validation, and 100% in the other changed backend
  logic. The changed SQL string is exercised by direct and reserved-use tests;
  coverage.py does not count its interior SQL lines as Python executable lines.
- Browser evidence: `temp/pricing-ui/`; cost state matrix and all 15 locales pass
  in Chromium, no page errors or horizontal overflow. Full test logs:
  `temp/pricing-core-tests-final.log`; coverage: `temp/pricing-coverage.json`.
- This is a local implementation, not a deployment or release gate. Oracle,
  recorded historical amounts, credentials and budgets have not been changed.

## Extraction assessment

The existing `frontend/js/core/page-locales.js` exceeds 1,500 lines. This task adds
only the two cost-status messages in the existing EN/VI dictionaries; splitting
the locale loading architecture would scatter ownership and expand this patch.
The other touched locale dictionaries retain their current per-language ownership.
Runtime pricing, storage and dashboard modules remain below the threshold. No
runtime dependency, service or framework was added; coverage tooling is temporary.
