# Provider expansion — implementation checklist

Approved direction: user delegated technical choices and approved parallel agents.
Scope/spec: docs/specs/provider-expansion-2026-09.md. No historical task counts changed.

- [x] Boundary: registry, credential identity and bounded transport dispatch; regression tests.
- [x] Hosted APIs: six named providers, dynamic catalogs and correct JSON/SSE; focused tests.
- [x] OpenCode: explicit Zen/Go and native protocol choice; focused tests.
- [x] Kiro: API-key request/discovery and bounded binary decoder; focused tests.
- [x] Management: add/verify/test/import/export/edit and secret-safe authorization/audit.
- [x] Console: provider cards, scoped advanced settings, supplied logos and fifteen locales.
- [x] Integration: routing/stream lifecycle and browser responsive/theme evidence.
- [x] Handoff: core/static gates and source/limitations documentation prepared for scoped commit.

Verification on 2026-09-15: core suite ran 1,983 tests with 1,961 passing and
22 optional skips, zero failures. Final onboarding/store regressions: 9 passing.
Fast quality gate passed. Browser smoke exercised all eight forms across 32
viewport/theme cases without JavaScript errors or horizontal overflow. A second
visual batch confirmed corrected logo backgrounds, title interpolation and eye
button dimensions. All 1,330 referenced locale keys passed the locale audit.

Independent review blockers were fixed: tool IDs/allowlists, context-aware
deduplication, usage accounting, cancellation cleanup, small streaming deltas,
candidate-count handling and unsupported reasoning-history rejection. The frozen
legacy variant catalog remains unchanged; additions use the versioned matrix.
No real provider credentials, paid calls, dependency additions, schema migrations,
Docker replacement, remote push or release were performed.

Threat model: untrusted console fields and vendor replies cross authenticated management,
credential storage and outbound HTTP boundaries. Protect keys, existing pool contents,
request integrity and bounded resource usage. No automatic inference during discovery.
