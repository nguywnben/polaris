# Full-application synthetic data — 2026-09-16

Preview: http://127.0.0.1:4285

Demo-only owner password and backup passphrase: `Polaris-Demo-Only-2026!`.
Database: `temp/round2-full-ready/credentials/credentials.db` (Git-ignored).
Earlier `round2-demo` and `round2-full` candidates are preserved. Operator storage
is untouched. Production code, Docker and Git history were not changed by this task.

## Coverage

| Surface | Dataset / runtime coverage |
| --- | --- |
| Dashboard | 696 calls spanning 30 days, successes/failures, latency, tokens, illustrative costs, provider health and timeline |
| Providers | All 23 variants; real forms and advanced defaults; external login/verification remain offline |
| Credentials | 87 records, 1–7 per provider; healthy, disabled, 401, 429, cooldown, long-name and missing-identity cases |
| Credential management | Six OAuth quota families, plan/model/credit/resource/window facts; API-key and local connection variants |
| Models | Catalog derived from the same records, ordered virtual route, blacklist; demo runtime routing decisions |
| AI Quality | Valid custom revision 3; compression, guardrails, response cache; related history/audit events |
| Playground | Explicit offline JSON/SSE samples for all four UI protocols; normal auth, validation and admission limits |
| Access | Eight keys: active/disabled/expired/revoked, scope/model/budget/limit examples, linked spend and last-used dates |
| Identity | Owner plus four fictional OIDC identities/role bindings, including disabled; two extra runtime owner sessions |
| Activity / traces | 696 domain-validated trace records, linked one-to-one to seeded usage request IDs and decisions |
| Activity / audit | 80 redacted synthetic management events and outcomes; local demo operations append real audit events |
| Activity / runtime | 696 fictional log lines linked to request IDs, usable through normal log filtering |
| Settings | Real local config, normal controls, encrypted archive of the fake database; restore dry-run validated |
| About, setup, login | Real static/status/auth surfaces; no meaningless database records invented |

Seed totals: 7,160,680 tokens; 2,627,206,400 nano-USD of **illustrative** cost.
The public dashboard returns 2.627207 USD under its per-credential six-decimal
rounding contract. Ledger sums, key IDs, credential references, request IDs and
last-used timestamps reconcile. Mixed failures are deliberate, not provider evidence.

## Safety and limitations

- The generator refuses every existing directory. It never copies live data.
- All provider secrets have fictional markers. Virtual-key secrets are random and
  discarded, so seeded keys cannot authenticate. Extra session tokens are discarded.
- The launcher validates the dataset, clears inherited secrets/config and ignores
  `.env`; loopback only. Outbound socket connects, datagrams, external DNS and child
  processes are blocked. This is not an OS sandbox for running untrusted Python.
- External OIDC remains disabled. Real OAuth, provider verification/inference and
  telemetry export are unavailable. Playground has explicitly labelled `DEMO`
  protocol responses, not a production inference/provider compatibility test.
- History, quota and logs remain fixed at generation time. Quota refresh rereads
  stored facts. Sessions and routing decisions are recreated at preview startup.
- Actual CRUD/settings use the isolated DB. Restore was validated but not applied
  over the populated preview. Optional PostgreSQL/MongoDB/OIDC/export services are
  not falsely presented as running external systems.

## Reproduce

```powershell
.venv/Scripts/python.exe tools/seed_demo_database.py --full --directory temp/my-full-demo/credentials
.venv/Scripts/python.exe tools/demo_preview.py --directory temp/my-full-demo/credentials --port 4285
```

Choose an unused port or stop the existing demo first. Fresh data uses normal
setup, with no authentication bypass. Do not enter real credentials in the demo.

## Verification

- Eleven focused tests passed. The two full-demo tests passed again after adding
  last-used timestamp reconciliation. Ruff passes. Coverage tooling is not installed;
  changed-line coverage percentage was not measured.
- `temp/round2-full/verification/report.json`: 80 desktop/mobile light/dark captures;
  13 page views, five modal flows, all eight Playground protocol/stream combinations,
  authenticated backup validation. No captured page errors, API failures or viewport
  overflow. Setup was also captured in the initial fresh run.
- `temp/round2-full-ready/verification/data-report.json`: final DB/API totals and
  exact credential modal checks for six OAuth families plus Ollama.
- Browser API responses are not mocked; UI reads the real synthetic SQLite records.

```powershell
.venv/Scripts/python.exe -m unittest backend.tests.test_demo_application backend.tests.test_demo_database backend.tests.test_demo_preview
.venv/Scripts/python.exe tools/demo_full_smoke.py --base http://127.0.0.1:4285 --directory temp/round2-full-ready/credentials
.venv/Scripts/python.exe tools/demo_full_smoke.py --base http://127.0.0.1:4285 --directory temp/round2-full-ready/credentials --data-only
```

## Findings for round 2 — not an all-clear UI audit

1. Credential provider filter has a fixed allowlist missing Muse Code, Meta, Groq,
   DeepSeek, Mistral and Cerebras. Reproduced Kiro → Muse Code retaining Kiro
   results. Records/API are present; full-list modal checks work. Source:
   `frontend/js/core/credential-manager.js`, `getFilterDefinitions()`.
2. Dashboard provider summaries become crowded with 23 providers. Review wrapping,
   density and layout in the populated UI audit.

These findings are recorded, not silently fixed as part of database preparation.

Follow-up: both findings and the provider-specific quota presets were corrected
in the subsequent UI audit. See `populated-instance-round-2-2026-09-16.md` for
the fixes, bounded browser/workflow evidence and unchanged-data safeguards.
