# Credential email privacy

The credential fleet and ordinary management/usage responses show masked account
emails, including emails embedded in custom labels. Hovering a card does not
reveal the original address. This is display privacy and data minimization, not
encryption: deploy HTTPS to protect traffic, especially explicit secret retrieval.

## Explicit reveal

In **Credentials → Manage**, the eye icon (**Show email**) calls
`GET /api/credentials/email/{filename}?mode=provider` (or `code_assist`).
The existing `credentials.export` permission is required; read/operate permission
alone is insufficient. A successful response is `{"user_email":"..."}`, or null
when there is no valid account address, with `Cache-Control: no-store`.

The eye/eye-slash controls retain localized accessible names and hover labels.
The browser keeps a revealed address only in that dialog's visible text, never
its shared credential cache or browser storage. **Hide email**, closing the
dialog, or cancelling a pending request prevents it from persisting in the UI.
Opening/reopening a dialog never automatically requests the original address.

Credential payload reveal, download/ZIP export, and the existing explicit OAuth
credential-retrieval workflow still carry original credential data so it remains
usable and importable. They are sensitive operations, not ordinary list reads.
This feature does not rewrite saved credentials, historical server logs or
previously exported files/screenshots, and does not anonymize OIDC team identities.

## Opaque inventory references

Console APIs return `credref-v1-<64 lowercase hex characters>.json` in place of
legacy filenames containing `@` and actual filenames using that reserved prefix.
This includes inventory fields, usage dictionary keys, import/OAuth summaries,
and structured credential references in management diagnostics. Free-text errors
mask embedded emails. Internal routing, deduplication, ledger entries, pagination,
and batch selection still use original storage keys. No files are renamed.

Clients must use the returned reference unchanged in credential paths and
single/batch action bodies. Plain filenames without emails remain accepted.
**Raw email filenames are no longer accepted as management targets**: retrieve
the list and use its reference. Invalid/unknown/ambiguous aliases return a generic
404; an explicit batch containing such a reference fails before any mutation.
Inference model IDs and virtual API keys are unaffected.

References are HMACs under a separate domain using the existing durable session
master key, not reversible encodings or unsalted email hashes. They survive
restarts; a restored database/key preserves them. Replacing that master key
invalidates references: reload the inventory before another operation. Missing
or corrupt key material fails closed with 503 rather than exposing filenames.
References confer no permission and resolve only against the requested credential
mode. As with the prior filename IDs, the same filename has the same reference
across modes; the alias does not imply that it exists in another mode.

The response boundary uses FastAPI's documented
[custom APIRoute hook](https://fastapi.tiangolo.com/how-to/custom-request-and-route/)
after handler authorization and serialization. Alias resolution is called inside
authenticated handlers, not as an independently scheduled dependency.

## Rollout

No database migration or credential reimport is required. After updating the
application, reload open dashboard tabs to discard old cached account labels and
raw legacy identifiers. Do not persist console references as storage filenames.
Rolling back this feature restores the old display behavior; it does not change
credentials. Any rollback of a combined image must also follow that image's other
migration/rollback requirements.
