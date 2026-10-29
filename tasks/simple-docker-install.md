# Simple Docker installation — 2026-09-18

## One-command platform extension — 2026-09-19

Owner approved Docker underneath the unified installer. Contract:
`docs/specs/one-command-install.md`. No host dependency installation, Oracle update,
push or publication in this follow-up. Existing native compatibility scripts stay.

- [x] Add parity regressions and a self-contained PowerShell guided Docker installer.
  Verify local/public consent, arguments, collision/race protection, secure setup
  token transport, health failures and environment restoration using fake Docker.
- [x] Improve Bash prerequisite guidance and unify documented one-command entry
  points. Keep the current amd64 boundary and macOS evidence gap explicit.
  Verify Bash regressions, syntax, support-matrix and documentation contracts.
- [x] Rehearse the PowerShell path on isolated Docker storage if the local engine
  is available: setup/login, restart persistence and recovery; no real data.
- [x] Review security boundaries, run affected gates and record evidence.
  Final task gate: 36 tests passed, no failures/skips; static checks passed.
  Real Docker smoke passed on Windows PowerShell 5.1 and 7, including restart,
  backup/restore and rollback. One independent review's cleanup-ownership and
  volume-only recovery findings were fixed and covered by regressions.
  Evidence: `docs/evidence/one-command-install-2026-09-19.md`.
- [ ] Commit at the next authorized release-level checkpoint. Source changes stay
  uncommitted here: the full pre-commit gate in `docs/quality-gates.md` has not been
  run for this installer-only task. No push, tag, publication or Oracle update.

Threat boundaries: downloaded release code, CLI arguments, local Docker context,
existing container/volume names and setup tokens. Do not trust a remote daemon,
mount a volume claimed by another install, print secrets in diagnostic commands,
or execute partially downloaded scripts. Source distribution stays on official
GitHub HTTPS URLs until a separately authorized domain/release is available.

Owner approved implementation and this separate plan location. Existing plans stay intact.
Contract: `docs/specs/simple-docker-install.md`. Local work and the subsequently authorized
test-VPS rehearsal only; no push or release.

## Design and risks

Use a standalone Bash installer as a transparent wrapper around Docker. No new backend
auth mechanism or host dependencies beyond the normal Linux shell utilities and Docker.
Use Docker environment inheritance for the generated code (not a command-line secret).
Keep persistent data in a named volume, app filesystem read-only, and bounded logs.
Public HTTP requires an explicit choice; local is the default. Never alter firewalls.
Reject existing resources instead of guessing whether they are safe to replace.
Docker administrative access is trusted; protect against accidental collisions, not a
malicious administrator who already controls the daemon. No secrets in application logs.

## Ordered tasks

- [x] Reconcile HTTP opt-in configuration inventory and README/Compose expectations.
  Verify: install-support and product-surface inventory tests (17 passed).
- [x] Test-first installer slice: prerequisites, consent, creation, readiness, failure
  handling and rerun guidance. Files: installer and its unittest module.
  Verify: fake-Docker subprocess tests and Bash syntax check.
- [x] Isolated Docker integration: fresh local image, setup/login, persistence after
  restart, backup/restore and manual image replacement without changing real data.
  Files: dedicated smoke tool and evidence document. Verify runtime assertions.
- [x] Publishable documentation: one-command Linux guide, direct Docker example,
  backup/update/recovery, existing Compose/source paths. Update support matrix/contracts.
  Verify: support tests and link/contracts checks. No published availability claims yet.
- [x] Add short localized guided-install pointers to the 15 README variants in batches.
  Verify: all language/README contracts; preserve existing source-run instructions.
- [x] Final review and regression checks, local commits. No push/version/tag changes.
  Verify: fast quality gate, affected tests, full core suite, clean scoped diff.

## Checkpoints

After installer tests: inspect secret transport, refusal paths and restart/volume settings.
After integration: confirm tested commands match the user guide and report host limitations.
Before completion: no unverified claim of published installer, native Linux host coverage,
automatic cloud firewall changes, or Compose updater support for Docker-run deployments.

Verified: 2,327-test core run OK (22 existing conditional skips), latest 11 installer and
18 support/inventory tests passed, fast quality gate passed, isolated Docker smoke and
HTTP runtime smoke passed. Independent rereview found no remaining blockers. Fresh native
Linux/VPS interactive installation and public reachability were still pending at that
checkpoint. The owner subsequently authorized the selected test VPS; see the latest
evidence below rather than treating that earlier limitation as current.

## Final verification checkpoint

- [x] Harden setup transport against remote clients spoofing a loopback Host header;
  preserve guided local Docker with explicit opt-in coupled to a loopback-only bind.
- [x] Verify `fec0388`: full release gate, 2,330 core tests (22 optional skips),
  9/9 browser journeys, 600/600 routine requests, setup UI and Docker recovery smoke.
- [x] Update the authorized native Ubuntu VPS from copied data, retain original
  container/volume/archive, preserve setup code and leave owner creation to the user.
- [x] Independent final code review: no unresolved blocking findings.
- [x] Owner confirms the two reported interactions on the physical Android device.
- [ ] After renewed push/publication approval: run CI on the exact final source,
  recheck existing tag/image ownership and verify installation from the published digest.

The owner subsequently approved push, CI and refreshed 1.0.0 publication on 2026-09-18;
complete the remaining exact-source checks before replacing the version. Evidence:
`docs/evidence/guided-docker-install-2026-09-18.md` and
`docs/releases/1.0.0-readiness.md`.
