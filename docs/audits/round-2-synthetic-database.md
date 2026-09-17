# Round-2 synthetic credential database

Historical credential-only preparation. The active preview now uses the
[full-application dataset](round-2-full-synthetic-data.md); this earlier DB is preserved.

This is a real SQLite dataset for the populated credential-console review, not
browser-intercepted credential cards. All accounts, secrets, health events and
quota observations are fictional. It does not prove provider connectivity,
actual subscriptions, model availability, or billing accuracy.

## Local dataset

- Database: `temp/round2-demo/credentials/credentials.db` (Git-ignored).
- 23 console provider variants; 87 persisted credentials, 1–7 per provider.
- OAuth accounts use `example.invalid` addresses, including a missing-identity case.
- API keys and Ollama connections do not receive invented account emails.
- Labels begin with `DEMO`; secret fields begin with `DEMO-NOT-A-REAL-`.
- Includes enabled, disabled, cooldown/429, unauthorized/401 and long-label cases.
- Stored quota observations cover Antigravity model balances/credit, Grok billing,
  Codex session/week/credits, Claude model windows/extra usage, Kiro resource/trial
  balances and Muse Code subscription windows. Amounts are illustrative only.
- Most model identifiers deliberately contain `demo`; Meta/Muse use identifiers
  accepted by their strict existing parser. None can be called in offline preview.

| Provider | Credentials | Provider | Credentials |
| --- | ---: | --- | ---: |
| Cerebras Cloud | 1 | Claude Code | 2 |
| Claude Platform | 3 | Cloudflare Workers AI | 4 |
| Codex | 5 | DeepSeek Platform | 6 |
| Google AI Studio | 7 | Google Antigravity | 1 |
| Grok Build | 2 | GroqCloud | 3 |
| Kilo | 4 | Kimchi Coding | 5 |
| Kimi API Platform | 6 | Kiro | 7 |
| Meta Model API | 1 | Mistral AI Studio | 2 |
| Muse Code | 3 | NVIDIA NIM | 4 |
| Ollama | 5 | OpenAI Platform | 6 |
| OpenCode | 7 | Poolside Platform | 1 |
| SpaceXAI Console | 2 | | |

## Create a separate copy

From the repository root:

```powershell
.venv/Scripts/python.exe tools/seed_demo_database.py --directory temp/my-demo/credentials
```

The destination must not exist, even if empty. There is deliberately no `--force`
or reset option. It uses the application's SQLite schema/storage manager, never
copies operator records, and never calls provider APIs. Setup/login remain normal
Polaris workflows; a freshly generated dataset has no owner password yet.

## Offline preview

```powershell
.venv/Scripts/python.exe tools/demo_preview.py --port 4285
```

Open `http://127.0.0.1:4285`. Use `--directory` for another generated dataset.
The prepared local database has a **demo-only**, loopback owner password:
`Polaris-Demo-Only-2026!`. Never reuse that public test password outside this dataset.

The launcher refuses unmarked databases and non-synthetic credential secrets.
It discards inherited provider keys/passwords/proxies/external database settings
and ignores `.env`. It binds only to loopback and denies outgoing socket connects,
datagrams, external DNS and child processes, including local Ollama connections.
This developer helper is not a security sandbox for executing untrusted Python.

Credential lists, filters, local edits, toggles and deletes use the real database
and application. Authenticated model/quota reads use the stored demo observations;
the model catalog is derived from the same persisted records. Quota refresh reads
the same fixed snapshot, not a provider. Responses identify synthetic mode with
`X-Polaris-Synthetic-Data: true`. Real OAuth, verification, inference and external
integrations are intentionally unavailable. Do not enter real credentials here or
run this dataset via the production launcher.

This preparation does not seed request traffic, billing history, virtual keys or
activity traces. Those pages are not a populated round-2 audit result. No audit,
Docker deployment, commit, or operator-database migration is performed here.

## Verification

- Nine focused tests: SQLite persistence/integrity/counts, non-overwrite protection,
  existing provider normalizers, environment isolation, fail-closed dataset checks,
  and an installed audit hook rejecting an actual socket connection.
- Runtime HTTP check: authenticated fleet returns 87 records / 23 variants; all
  six OAuth quota/model families load; unauthenticated quota access returns 401.
- Python lint and formatting checks pass for the five new implementation/test files.

```powershell
.venv/Scripts/python.exe -m unittest backend.tests.test_demo_database backend.tests.test_demo_preview
```
