# Synthetic database fidelity repair — 2026-09-17

## Scope and evidence boundary

This repair changes the **persisted SQLite demo corpus**, its generator, isolated upstream
fixtures, and verification tools. It does not edit frontend pages, labels, provider parsers,
or production API responses to make the demo look populated.

The corpus is structurally checked against Polaris's current storage/domain contracts and
the reference clients below. Account identities, secrets, balances, traffic and timestamps
are synthetic scenarios, not observations of real accounts. A matching response schema
does not certify every future provider response, actual plan allowance, model entitlement,
or live integration. Missing/unsupported data remains missing/unsupported.

Reference checkout root: `C:/Users/nben6/Downloads/repo`.

| Source | What it establishes |
| --- | --- |
| `cockpit-tools/src-tauri/src/modules/quota.rs` | Antigravity model quota and account metadata response shapes |
| `OmniRoute-3.8.49/open-sse/services/usage/antigravityWeeklyQuota.ts` | Optional Antigravity grouped quota response |
| `OmniRoute-3.8.49/open-sse/services/codexQuotaFetcher.ts` | Codex account/review/additional limit windows and credit fields |
| `cockpit-tools/src-tauri/src/modules/claude_account_desktop_auth.rs` | Claude OAuth usage windows and optional extra usage; profile information is separate |
| `cockpit-tools/src-tauri/src/modules/grok_account.rs` | Grok monthly/weekly billing response fields and optional credit/product usage |
| `cockpit-tools/src-tauri/src/modules/kiro_oauth.rs` | Kiro subscription, credit resources, trial and bonus shapes |
| `docs/providers/muse-code-research-2026-09-16.md` | Previously recorded official Muse CLI/live-probe response contract, public model namespace and subscription fields |
| `9router-0.5.35/open-sse/providers/registry/*.js` | Pinned model IDs for the provider families listed in `tools/demo_catalog.py` |
| [Kilo models](https://kilo.ai/docs/gateway/models-and-providers), [Poolside API](https://docs.poolside.ai/api/openai-api-examples), [Ollama model library](https://ollama.com/library/llama3.2) | Model IDs absent from the corresponding local reference catalog |

Every stored credential has a corresponding source index in `demo_upstream_v2`.
Catalog IDs are reference-backed examples, not an assertion that all are available to
every synthetic account today. Polaris's own price resolver determines estimated costs;
an unknown model price is not invented, and estimates are not provider invoices.

## Removed misleading data

- Universal `pro` plans, generic Google OAuth fields applied to unrelated providers,
  fabricated account emails for API keys, and invented `*-demo-fast/reasoning` model IDs.
- Hand-authored normalized quota/UI snapshots and demo API route overrides. Quota/model
  requests now traverse the actual production routes and parsers.
- Claimed Claude subscription metadata in a usage response that does not establish it;
  an invented Muse opaque tier code (`POWER`).
- Arbitrary credential counters, flat token pricing, zero-cost assumptions for all OAuth,
  retries without trace evidence, and successful calls after credential/key disablement.
- Fake successful Playground dispatches and manually inserted routing diagnostics.

## Persisted coverage

| Surface | Actual demo data and expected behavior |
| --- | --- |
| Providers / credentials | 23 variants, 89 credentials; all section sizes 1–7; 45 API-key, 40 OAuth and 4 connection records |
| Credential states | Enabled, disabled, exhausted/cooling down, upstream authorization failure, absent optional metadata; counters and last-success dates derive from ledger records |
| Antigravity | Per-model remaining fractions/reset times, optional grouped quota, account tier/credits; the Polaris credit switch remains a separate setting |
| Codex | Primary/weekly windows, review quota, optional additional model limits, credit balance and reset-credit counts |
| Claude Code | Five-hour/weekly and model-specific windows, extra usage enabled/disabled; no invented plan fallback |
| Grok Build | Monthly/weekly billing, optional on-demand/prepaid/product usage; incomplete upstream data is an error/unavailable case |
| Kiro | Social OAuth, IDC OAuth and API-key records; subscription, resource credits, active/expired trial, bonus and overage metadata |
| Muse Code | Officially observed plan-name shape, short/weekly usage windows, missing-usage case; native model IDs are converted by the real parser to the `muse-code/` public namespace |
| API-key providers / Ollama | Provider-owned configuration and declared models; no fabricated OAuth email, plan or quota when unsupported |
| Dashboard / usage | 712 provider-call ledger rows across 30 days, recent requests, real aggregation and pricing/token normalization; failed calls have no invented billable tokens |
| Request activity | 720 traces: provider successes/failures plus local guardrail, budget, rate-limit, unavailable, cancellation, client/internal error and cache-hit scenarios |
| Audit activity | 80 redacted synthetic events using the production event schema and known action names; no prompt/token contents |
| Models / routing | Real stored virtual-model configuration, eligible declared catalog, failed-model blacklist; runtime diagnostic decisions generated by the actual selector without inference |
| AI Quality | Production policy document with compression, guardrails and response-cache settings; runtime cache counters are not fabricated database values |
| Access | 8 real virtual-key records with active/disabled/expired/revoked states, budgets, scopes, model restrictions, compression policy and consistent usage history |
| Identity / settings | Real identity/role repositories, 5 identities including the local owner, enabled/disabled examples, existing local-owner login preserved |
| Sessions | Issued through the real in-memory session service; sessions are runtime data, not fictitious SQLite rows, and do not survive restart |
| Backup / logs | Real encrypted `.ogb` artifact validated by the production backup service; synthetic log file separate from SQLite |
| Playground | Real request/error path with network blocked; no successful model response is invented merely to fill a screen |

These scenarios cover the currently targeted persisted surfaces, not every combination
of provider features or every possible retry/fallback chain. Empty first-run setup and
live inference success cannot simultaneously be represented by this populated offline DB.
All credentials are marked synthetic and use nonfunctional demo secrets. Outbound network,
DNS and subprocess attempts are denied by the preview. No live account or VPS is used.

## Consistency and replacement checks

`tools/audit_demo_database.py` checks SQLite integrity/foreign keys, source indexes, model
references, credential creation and success dates, status/counters, usage-to-trace references,
token equations, production price calculations, key lifetimes/scopes and daily budgets.
The initial 109-record candidate exposed the real router's 100-candidate safety bound.
The final corpus contains 89 records; the production bound is unchanged. Regression
checks cover the bound and actual credential selection for every provider family.

`tools/update_demo_database.py` accepts only explicitly marked synthetic databases. It
validates the source, creates a complete SQLite backup, and replaces the corpus in one
transaction. A regression test forces replacement failure and verifies a complete rollback.
Unrelated target configuration, local-owner login and management identities are preserved.

Active preview target:
`temp/current-preview-20260917-102745/credentials/credentials.db` on port `4285`.
Replacement source:
`temp/fidelity-20260917-verified/credentials/credentials.db`.

Backups use `credentials.before-fidelity-<UTC timestamp>.db` beside the target database.
Stop the preview before restoring a backup. Do not apply these tools to a live-account DB.

The original pre-repair database is preserved at
`temp/current-preview-20260917-102745/credentials/credentials.before-fidelity-20260917T050740439421Z.db`.
An additional backup was made before the final capacity-corrected replacement at
`credentials.before-fidelity-20260917T051718309657Z.db` in the same directory.

Dates are anchored to corpus generation, not continuously manufactured traffic. The real
15-minute health panel will correctly become empty after that interval without new calls.
To move this isolated scenario to the current time, use `tools/refresh_demo_dates.py`;
it shifts the actual persisted activity, credential cooldowns and upstream reset timestamps
together, retaining durations and cross-record relationships.

## Verification evidence

- Focused tests cover provider credential normalization, quota parsers, pricing/history,
  seed/preview isolation, timestamp movement, replacement refusal and rollback.
- Production HTTP checks reconcile stored credential count, requests, tokens and costs;
  all six OAuth quota families are exercised without frontend API mocks.
- Chromium verification on the staging corpus: 76 page/dialog captures across desktop/mobile
  and light/dark, five management/detail dialogs, eight offline Playground error paths;
  no horizontal overflow. Loaded provider management dialogs are checked separately.
- Frontend changes already present in the working tree belong to earlier work, not this repair.

Final port-4285 verification:

- SQLite audit: 89 credentials, 712 ledger calls, 720 traces; integrity and relational checks pass.
- Real API reconciliation: 8,985,184 tokens and USD 27.469160 after the API's documented
  per-credential rounding; exact ledger amount is 27,469,164,220 nanodollars.
- Six OAuth quota families and seven loaded provider management dialogs checked through
  the production endpoints. Missing Muse usage stays unavailable; API-key quota stays unsupported.
- Recent health snapshot: 164 requests; routing snapshot: 20 selected, 0 unavailable.
- Latest portable backup validates 89 primary credentials / 712 ledger rows / 720 traces,
  not an older archive accidentally selected from the same directory.
- 75 combined demo/provider tests passed initially. After the capacity/layout correction,
  all 23 focused demo tests passed again, including real provider selection and rollback.
- Ruff checks, formatting checks and tracked diff whitespace checks pass. This is a
  focused data-tool verification, not a full release-gate or live-provider certification.
