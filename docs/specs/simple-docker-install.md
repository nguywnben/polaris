# Simple Docker installation

Status: implementation approved by the owner on 2026-09-18.
Version target: 1.0.0, local preparation only. No publication or VPS migration authorized.

## Objective

A non-specialist with Docker installed can install Polaris using one prepared command,
open the displayed address, enter a generated setup code, and create an owner password
in the browser. Cloning the repository, editing environment files, and learning Compose
must not be prerequisites for the basic path.

## Assumptions for review

- The first supported guided path targets the user's Linux x86_64 VPS. Other hosts must
  retain their documented paths; do not claim untested Windows or ARM64 support.
- One short terminal interaction to choose local access or VPS access and acknowledge
  HTTP risks is acceptable. No manual secret generation or configuration editing.
- A setup code displayed by the installer is acceptable. The owner copies it into the
  existing web setup form; their password is created on the web, not in the terminal.
- The installer uses Docker directly. The existing Compose path remains available for
  advanced installations; its update/rollback tool must not be advertised for Docker-run
  installations until a compatible path is implemented and verified.

## Proposed user flow

1. Run one documented installer command with Docker already installed and running.
2. Choose local access or VPS access. Local access binds to loopback. VPS HTTP access
   requires explicit informed consent before starting the publicly bound container:
   passwords, setup codes, cookies, and API traffic are not encrypted over HTTP.
   Recommend HTTPS without requiring purchase of a domain. Declining must not silently
   expose the service or enable insecure HTTP.
3. The installer pulls the version-pinned image, creates persistent storage and a strong
   random setup code, and starts the single-worker container with a restart policy.
4. After readiness succeeds, display the correct URL and setup code in the invoking
   terminal, not application logs. Do not put the code in a URL or shell command history.
5. Open the URL, paste the code, and create the owner password in the existing setup UI.
6. If external access fails, explain cloud firewall checks in plain language. Do not
   modify cloud rules, disable host firewalls, or claim automatic public-IP discovery
   always works; ask for the public address when it cannot be established reliably.

## Technology and project structure

Use the existing Docker image and application setup endpoints. No new application
dependencies or database schema changes. Proposed installer location:
`deploy/scripts/docker-install.sh`; regression tests: `backend/tests/test_docker_install.py`.
Update `docs/installation.md`, installation support contracts, and the 15 README
translations only after the new path is tested. Keep native compatibility installers.

## Code style

Use explicit failures and quote shell variables; never enable shell tracing around secrets.
For example, match the existing fail-fast shell convention:

```sh
set -eu
command -v docker >/dev/null 2>&1 || {
    printf '%s\n' 'Install and start Docker, then run this installer again.' >&2
    exit 1
}
```

## Verification commands and testing strategy

Commands below are for implementation verification, not end-user installation:

```text
bash -n deploy/scripts/docker-install.sh
python -m unittest backend.tests.test_docker_install backend.tests.test_install_support
python -m unittest backend.tests.test_setup_preflight backend.tests.test_setup_console
python tools/http_setup_smoke.py
python tools/quality_gate.py fast
python -m backend.tests --suite core
```

Add subprocess tests with a fake Docker executable before implementing installer behavior.
Cover missing Docker, unsupported engine/architecture, declined HTTP, image pull failure,
existing containers/volumes, occupied ports, readiness timeout, reruns, and secret handling.
Then test with an isolated locally built image and fresh explicitly named test storage:
setup, wrong-token rejection, login, restart, data persistence, and documented recovery.
Do not use the published 1.0.0 image to claim the unpublished HTTP option works.

## Boundaries and success criteria

- Always preserve existing deployments and data. Refuse collisions with actionable
  guidance; never delete or replace containers/volumes automatically.
- Always retain setup-token verification, password validation, and session protections.
  Anonymous visitors must not be able to claim the owner account.
- Always make a rerun safe and explain how to resume an interrupted installation.
- Always verify readiness before reporting success, and distinguish Docker restart
  policy from the requirement that Docker itself starts on host boot.
- Always document backup and a verified manual update/recovery path for this deployment
  type before advertising it as the default. Do not imply Compose rollback supports it.
- Ask before changing authentication architecture, adding dependencies, or migrating
  an existing installation. This proposal automates the existing configuration policy.
- Never publish, push, retag, change the version, or modify the user's VPS in this task.
- Never remove failing tests. The prior HTTP change has three known inventory/contract
  failures to reconcile and rerun before claiming the full suite passes.

## Approval

The owner approved the guided installer, retaining manual Docker/Compose and source-checkout
paths. A fully browser-only consent flow would be a different authentication design and
is not included. Implementation checkpoints are in `tasks/simple-docker-install.md`.
