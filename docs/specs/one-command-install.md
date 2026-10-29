# One-command installation — approved extension

Status: owner selected the recommended Docker runtime, 2026-09-19.
Implementation authorized; publication and Oracle deployment remain out of scope.
Extends the guided-install user experience, not the existing production topology.

## Objective

A new user selects their operating system, copies one documented command, follows
any prerequisite prompts, and reaches Polaris's existing browser setup screen.
No repository clone, manual secret generation, or manual environment-file editing
should be required for the basic path.

## Approved runtime decision

- Recommended: retain Docker as the runtime and build consistent entry points for
  Bash and Windows PowerShell. If Docker is missing/not running, provide actionable
  official installation instructions; do not silently install privileged software.
- Alternative: native installation without Docker. This requires a separate
  runtime/dependency, background-service and maintenance design before coding.

The first option does not promise a prerequisite-free installation on a clean
computer. Neither option implies desktop `.exe`/`.dmg` packaging.

## Acceptance criteria

- Clearly distinguish Linux, Windows, macOS and CPU-architecture requirements.
  Do not label macOS/ARM64 supported merely because a script exists; current
  published Docker scope is Linux/amd64 and macOS lacks native-host evidence.
- Use official HTTPS sources and explicit versions; do not execute failed or
  incomplete downloads. Keep inspect-before-run instructions available.
- Validate arguments and prerequisites before creating application resources.
- Preserve existing installations and data on reruns and errors. Installing is
  not upgrading; link the matching backup/update/uninstall procedures.
- Default to loopback access; public HTTP needs explicit informed consent.
  Preserve the existing setup code, owner-password flow and security settings.
- Wait for readiness before reporting success. Show the URL and setup guidance;
  optionally open the local URL only when appropriate for the host.
- Documentation must distinguish source-ready commands from actually published
  artifacts. No invented domain or command pointing to an unavailable release.

## Structure and conventions

Existing guided installer: `deploy/scripts/docker-install.sh`.
Existing native compatibility scripts: `deploy/scripts/install.ps1`, `install.sh`,
and `macos-install.sh`; preserve them rather than silently changing their meaning.
Tests belong in `backend/tests`, isolated integration tools in `tools`, and user
documentation in `docs`. Reuse the current fail-fast, quoted-argument convention:

```sh
command -v docker >/dev/null 2>&1 || fail 'Install and start Docker, then retry.'
```

## Verification strategy and commands

Begin with failing subprocess tests for invalid arguments, missing/stopped runtime,
unsupported platforms, remote Docker contexts, existing resources, download failure,
secret handling and readiness failure. Use fake command executables rather than
changing the developer's real Docker installation in negative-path tests.

Existing verification commands:

```text
python -m unittest backend.tests.test_docker_install backend.tests.test_install_support
bash -n deploy/scripts/docker-install.sh
python tools/quality_gate.py fast
```

Add tests for the approved platform entry points and rehearse against disposable
local storage. Record actual OS/architecture evidence separately from simulated
tests. A macOS test gap must remain explicit if no Mac is available.

## Boundaries

- Always preserve working deployments, data, authentication and manual installation.
- Ask before privilege elevation, host dependency installation, or a runtime change.
- Never alter firewalls, reset data, publish/tag/push, or update Oracle in this task.
- No new application framework, auth mechanism, cloud service or desktop shell.

Implementation slices are recorded in the existing owner-designated
`tasks/simple-docker-install.md`; unrelated historical plan files remain intact.
