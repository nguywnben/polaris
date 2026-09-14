# PB3 — Bounded Compatibility and Optional Dependencies

Date: 2026-09-12

PB3 keeps SQLite as the no-service default, PostgreSQL as an explicit Advanced selection, MongoDB
as a Compatibility selection, and OIDC as an opt-in identity feature. Storage selection remains
fail-closed: configuring both external database URIs is rejected, and failure of an explicitly
selected backend never falls through to a blank SQLite database.

The MongoDB driver no longer initializes, reads, writes, rebuilds, or closes a Redis cache. It now
queries MongoDB directly for credential routing and keeps its configuration cache in process. The
retired coordinated-only transaction branch and write-gate collection are also gone; credential
pool mutations use the process-local lock that matches the supported one-worker runtime. Three
obsolete operational runbooks for an unavailable HA/migration workflow were removed, while
historical specifications, decisions, and evidence remain available as records.

Implementation diff before this evidence/checklist update: 12 files, 61 additions and 840
deletions, a net reduction of 779 lines.

Verification:

- 94 focused storage, SQLite, MongoDB, PostgreSQL repository, OIDC, application lifecycle, runtime,
  and capability tests passed.
- 27 release-document, capability, gate, and configuration contracts passed.
- A default-storage regression test proves SQLite selection does not import either optional
  external database driver.
- Selected external-backend failures now name the selected setting and locked dependency install
  path without exposing connection details.
- The fast quality gate passed lint, format, compilation, the 195-module Core manifest, recursive
  JavaScript syntax, strict YAML, shell syntax, and whitespace.

