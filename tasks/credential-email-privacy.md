# Credential email privacy

## Approved scope

Default-mask account email in the credential list and ordinary management views.
Only an explicit per-credential action may retrieve the original email; reuse
the existing credential-export permission. Forget the revealed value on hide or
dialog close. No hover reveal, no hidden original email in HTML or list data.
Do not modify stored credentials, upstream authentication, pricing or Oracle.

## Implementation slices

1. Shared email projection at management API boundaries; preserve internal raw
   identities for deduplication/routing. Protect the reveal endpoint with existing
   authorization and no-store caching.
2. Management-only reveal/hide control, abort late responses after close, masked
   labels and translated actions in all 15 locales.
3. Regression tests (mask edge cases, API minimization, permissions, DOM lifecycle),
   real Chromium smoke, full backend suite and task quality gate.

## Commands and constraints

Python/FastAPI code under `backend/core`, unittest under `backend/tests`, vanilla
JS under `frontend/js/ui`. Use `mask_account_email(value)` at response boundaries,
not in storage. Run `.venv/Scripts/python.exe -m unittest
backend.tests.test_credential_email_privacy`, then `-m backend.tests --suite core`.
Existing CONSTRAINTS.md applies; do not weaken tests or change authentication roles.

## Boundaries

Full credential payload/download remains an explicit, authorized sensitive-data
operation. Existing filenames are inventory identifiers; never rename stored
credentials as a side effect. No automatic HTTPS/firewall/deployment change.

## Approved extension: opaque legacy inventory references

The user approved hiding email-shaped inventory IDs as well. Ordinary console
JSON projects filename fields and usage dictionary keys to `credref-v1-<HMAC>.json`.
The existing persisted, high-entropy session master key supplies domain-separated
HMAC material; no password, unkeyed email hash, process-local registry or storage
rename is used. Missing/corrupt key fails closed. Key replacement invalidates
references; reload inventory to obtain new ones. Backup/restore preserves the key.

Resolution runs explicitly after route authorization, against the selected mode.
Plain non-email filenames remain compatible; raw email filenames and malformed,
unknown or ambiguous aliases return a generic 404. This intentionally prevents
ordinary read APIs from acting as an email-guessing existence oracle. Uploads and
authorized payload/ZIP exports retain original storage names. Internal routing,
selection, ledger, sorting and batch idempotency continue using real storage keys.
References identify filenames across modes, like the prior public identifiers;
they confer no permission and are resolved only within the requested mode.

Explicit OAuth credential-file retrieval remains a sensitive payload workflow;
its summary filename/email fields are projected but its importable credential
payload is retained. OAuth status polling contains only flow status, not credentials.

## Extraction assessment

Large existing panel route/operation files received only import/wiring and boundary
calls. Masking/projection, durable-key/reference resolution, and the final response
hook are extracted into three small modules. No unrelated refactoring of the large
files or changes to storage schemas are needed.

## Review reconciliation

- Legacy filename leak: actionable; extended scope approved by the user, now opaque.
- Coverage of OAuth file_path and selected_filename: actionable; added projection
  fields and OAuth router hook with regression tests.
- Structured HTTPException projection: actionable; shares the key-aware projector
  so a safe 4xx does not become an accidental 500.
- Mode-separated HMACs: retained filename-scoped references for mixed/historical
  usage compatibility; requested-mode resolution and unchanged authorization are
  tested. References are identities, never capabilities.
- OAuth payload: explicit existing credential-file retrieval remains sensitive;
  preserving importability is documented separately from ordinary list privacy.

## Verification (2026-09-20, local only)

- RED confirmed original full-email list/config leaks, missing reveal endpoint,
  legacy filename exposure, missing OAuth/selected-reference projection, structured
  error failure, and replay lookup occurring too late after deletion. Each is now
  covered by a passing regression; stored raw email/filename is explicitly checked.
- Core suite: 2,497 tests, no failures, 22 optional PostgreSQL/MongoDB skips
  (`temp/email-privacy-core-verified.log`). The last batch replay ordering delta
  is additionally covered by the final focused gate and coverage run below.
- Final task quality gate: passed lint/format (587 files), compile, manifest (272
  core modules), recursive JS syntax, YAML/shell checks, whitespace and 115 affected
  tests (`temp/email-privacy-quality-final.log`).
- Final coverage run: 218 tests passed. Changed statements in the email-related
  core/panel files plus the already-modified usage_stats file: 189/198 (95.45%).
  New privacy/resolver/response-hook modules: 98.04%, 98.08%, 94.74% respectively
  (`temp/email-privacy-coverage-final.json`).
- Chromium synthetic-loopback smoke passed with opaque IDs: no automatic reveal,
  keyboard reveal/hide, forget on close/reopen, failed/late-response protection,
  360/768/1024/1440 layouts, 15 locales; inspected mobile screenshot.
- Independent review findings were reconciled above; no dependency, stored
  credential, production deployment, version publication, or Oracle change.
- Existing dirty pricing/installer/routing work was preserved; no mixed commit made.

## Subsequent owner-authorized deployment — 2026-09-20

The owner subsequently requested updating Oracle. The isolated email-only overlay
is now deployed and healthy; the local-only `oracle-email-privacy-update.md` records the exact image,
153 passing candidate tests, live-data masking checks, streaming smoke, backup,
and rollback details. Pending pricing/installer/model-discovery work was excluded;
no public release was published.

## Shared modal refinement — 2026-09-20

- Replaced email reveal/hide text buttons with the existing eye SVG style,
  localized accessible names/tooltips, and unchanged reveal/forget lifecycle.
- Overview actions use compact text buttons aligned with status badges on desktop;
  filename/email keep the full row width. Mobile stacks actions after the facts.
  The shared capability-based renderer remains provider-independent.
- Chromium regression failed before the icon change and passed afterward: reveal,
  hide, reopen, failed/delayed requests, four viewport widths and 15 locales.
- Management smoke passed with OAuth, API-key, and environment-managed fixtures,
  light/dark themes, toolbar geometry and keyboard/confirmation/action checks.
  Screenshots remain local under `temp/credential-email-privacy/` and
  `temp/credential-management/`. No production deployment in this refinement.
