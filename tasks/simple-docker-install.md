# Simple Docker installation — 2026-09-18

Owner approved implementation and this separate plan location. Existing plans stay intact.
Contract: `docs/specs/simple-docker-install.md`. Local work only; no push or release.

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
Linux/VPS interactive installation and public reachability remain pre-publication checks,
not permission to modify the existing VPS. See the evidence document for exact scope.
