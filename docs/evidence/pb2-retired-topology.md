# PB2 — Retired Distributed Topology

Date: 2026-09-12

PB2 aligns the shipped runtime with the production self-host boundary: one application worker and
one replica. The change removes the unreachable Redis coordination implementation, HA activation,
operator/reconciliation/evidence layers, Helm chart, topology harness, experimental test suite,
activation configuration, Redis dependency, and obsolete HA permission. It replaces the previous
multi-mode lifecycle with one explicit process-local lifecycle and keeps the in-memory coordination
used by sessions, authentication throttling, OIDC/provider/device flows, virtual-key quotas,
credential batches, routing, invalidation, and response caching.

No public inference or management route, durable schema, default Compose volume, provider adapter,
or user data format changed. Startup now rejects non-standalone mode, multiple workers, multiple
replicas, and retired coordination settings with an actionable error.

Measured implementation diff: 115 files, 1,013 additions, 24,366 deletions — a net reduction of
23,353 lines. The lockfile was regenerated from `requirements.txt`; the only
package change is removal of `redis==8.1.0`.

Verification:

- Fast gate passed lint, format, compilation, the 195-module production manifest, recursive
  JavaScript syntax, strict YAML, shell syntax, and whitespace.
- 154 coordination, lifecycle, health, metrics, identity authorization, configuration, and product
  boundary tests passed.
- A second 194-test focused integration run covered sessions, quota lifecycle, routing,
  configuration, Compose, backup wiring, and release-document contracts. Its one stale heading
  assertion was corrected; the affected release/runtime slice then passed 34/34.
- Nine focused runtime/application lifecycle tests passed, including clean shutdown, partial-start
  rollback, singleton initialization, and restoration of process-local fallbacks.
- Repository scans found no active import of a deleted Redis/HA module and no Redis package in the
  regenerated lockfile.

Historical specs, ADRs, and evidence remain as records of earlier work. They no longer define the
current support boundary or quality gates.
