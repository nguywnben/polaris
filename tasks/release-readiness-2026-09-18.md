# Polaris 1.0.0 preparation — 2026-09-18

Status: local audit and repairs complete; publication blocked pending owner actions.
User-authorized whole-product verification and repair, not publication.
Baseline commit: `1596650` on `develop`; tracked working tree initially clean.
R1 (36/36) and R2 (7/7) remain historical completed plans, not reopened denominators.

Subsequent authorization on 2026-09-18 covered historical tag/release names only:
14 Omni Gateway tags were archived under `omni-gateway/`, and the existing Polaris
beta became `v0.1.0-beta` at the same commit. See the
[migration record](../docs/releases/tag-migration-2026-09-18.md). The audit guardrails
below describe the original audit; no new 1.0.0 publication is authorized.

## Guardrails

- Preserve standalone / one worker / one replica / SQLite Core / canonical Compose.
- No commit, push, tag, release, remote change, real provider call or operator-data deletion.
- User confirmed preparation of the new Polaris version line as `1.0.0`. Existing legacy
  `v1.0.0` is immutable during this task. The owner chose to keep `v1.0.0` / `1.0.0`
  naming and explicitly resolve legacy tag/image collisions before publication. This
  preparation does not authorize overwriting those artifacts.
- Test only new disposable synthetic storage. Keep current previews and their databases intact.
- No weaker tests, suppressed failures, speculative features or architectural rewrite.
- Each behavior fix starts with a reproduction/regression; use existing gates and thresholds.

## Ordered slices

| ID | Goal / acceptance | Expected owners | Depends on | Verification |
| --- | --- | --- | --- | --- |
| RR1 | Record source/evidence baseline, inventory and capability map; distinguish stale evidence from current results | `docs/audits/release-readiness-2026-09-18.md`, this plan, existing inventories | None | Git, source inventory, required documents, reference source/license checks, fast baseline |
| RR2 | Restore reliable verification; fix reproduced safety/correctness failures without hiding them | affected test/tool or runtime owner, normally <=5 production files per fix | RR1 | RED/GREEN focused tests, fast; review test isolation and exact-source benchmark provenance |
| RR3 | Verify all current provider/auth families and workflow boundaries; unknown quota stays unknown, capabilities and permissions remain authoritative | registry/adapters, credentials/routing/protocol/auth/storage tests, provider evidence map | RR2 | core/compatibility/provider contracts, deterministic failure fixtures; no live upstream |
| RR4 | Audit populated/empty console, auth/callback, all provider workspaces and modal families; repair measured defects | existing browser harnesses, affected HTML/CSS/JS and focused tests | RR2 | Chromium 360/768/1024/1440, both themes, keyboard/focus, runtime errors, loading/error/confirmation, 15 locales; bounded baseline and confirmation |
| RR5 | Prepare coherent 1.0.0 metadata and truthful current docs while preserving legacy history | app version, Compose defaults, release contracts, maintained docs/15 READMEs, changelog | RR3, RR4 | version parity, links, locale audits, release-notes ambiguity tests, owner tag-collision record |
| RR6 | Run required final gates and record exact verdict, limitations and remaining owner actions | existing quality gate, smoke/reliability tools, audit report | RR2–RR5 | fast, core, compatibility, i18n, DOM/browser, app/container, dependency audit, routine 120s/5RPS/8; no claiming unrun CI/live evidence |

## Progress

- [x] User scope, authoritative constraints, current/plan/todo, README, changelog,
  architecture, quality-gate and self-hosted spec read; initial Git status and history checked.
- [x] Initial fast gate: lint passed; formatter reports three files (recorded in baseline).
- [x] Complete current inventory and source/evidence comparison.
- [x] RR2 verification/correctness repairs, each with focused RED/GREEN evidence.
- [x] RR3 workflow/provider audit; deterministic coverage mapped, live boundaries excluded.
- [x] RR4 console audit and measured tooltip accessibility repair.
- [x] RR5 prepare 1.0.0 metadata/docs; tag/image collision intentionally blocks publication.
- [x] RR6 final verification and handoff: local release gate passed (2,308 core tests,
  22 optional live-storage skips), nine browser journeys, 600/600 reliability requests,
  independent application and Docker persistence/restart/shutdown checks.

Final results and known limits: `docs/audits/release-readiness-2026-09-18.md`.
HEAD is unchanged and not ready to tag: review/commit, immutable-commit CI and separately
authorized legacy tag/image collision resolution remain owner release actions.

Historical evidence is not current evidence. A green local check does not certify live
provider accounts, external storage, Linux CI or container publication.

## Authorized candidate closure — 2026-09-18

The owner now authorizes commits, pushing a preparation branch and running GitHub CI.
Do not merge main, create `v1.0.0`, publish a release/image, use real provider credentials,
or mutate existing operator storage. This continues RR5/RR6; no product scope is added.
Branch: `codex/release-1.0.0-readiness`.

- [x] RR5: inspect both target registries and record immutable beta rollback digests;
  accept only confirmed absence, never infer absence from authentication/network errors.
- [x] RR5: make manual CI verification-only, explicitly select latest for future stable
  releases, and complete dated candidate notes. Add failing workflow contracts first;
  verify focused release/quality tests and fast gate before committing.
  The owner-authorized tag archive also requires a narrowly scoped historical-doc
  exception to the brand scan; runtime/UI identifiers and old deployment aliases remain
  forbidden, with a regression asserting that boundary.
  Both publication regressions failed before the fix and passed afterwards. A bounded
  independent release-pipeline review found no Critical/Required issues. Fast gate and
  focused contracts passed after distinguishing Windows sandbox permission failures.
- [ ] RR6: review and commit the existing audited repairs in coherent groups, then run
  the canonical local release gate on the committed candidate (not a working-tree snapshot).
- [ ] RR6: push only this branch and dispatch CI on it. Require both Python versions,
  application, browser and container jobs to pass for the exact candidate SHA, with
  both publication jobs skipped. Fix actual failures; do not lower quality gates.
- [ ] RR6: record final SHA, CI run, local evidence, registry inventory and remaining
  operator publication steps. No claim of publication or live-provider certification.
