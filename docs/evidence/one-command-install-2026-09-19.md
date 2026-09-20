# One-command Docker installer extension — 2026-09-19

Scope: source preparation only. No GitHub publication, image/tag replacement, or Oracle
deployment. Existing native installers and the canonical Compose path are unchanged.

## Environment and runtime evidence

- Host: Windows x86_64, Docker Desktop with Docker Engine 29.8.0, Linux/amd64.
- Real installer subprocesses: Windows PowerShell 5.1 and PowerShell 7 (`pwsh`).
- Local test image: `polaris-private:session-expiry-20260919`.
- Resolved image: `sha256:c7ab2349c85f9bab5896c72a42c1af0f5b895c89df64529d1539fe727a9332d3`.
  This is an existing private local image with the guided setup flow, not a newly
  published image or certification of a future release artifact.

Both commands passed against separately generated container/volume names and loopback ports:

```text
python tools/docker_install_smoke.py --installer powershell --image polaris-private:session-expiry-20260919
python tools/docker_install_smoke.py --installer pwsh --image polaris-private:session-expiry-20260919
```

Assertions: read-only container and loopback bind; generated 256-bit setup token;
wrong-token rejection; successful setup, authenticated owner login and key-list retrieval;
rerun refusal with unchanged data; restart persistence; stopped-volume backup; restoration
to a fresh volume; replacement login/data verification; original-volume rollback; setup token
absent from application logs. Each successful run removed only resources recorded after
successful creation, with identity checked again before cleanup. The archive remained in process memory. No production
credentials, API calls, volumes or containers were used.

## Regression coverage

The final task gate passed 36 tests, zero failures/skips, plus repository lint, format,
Python compilation, manifest audit, JavaScript/YAML/Bash syntax and whitespace checks:

```text
python tools/quality_gate.py task --test-module backend.tests.test_docker_install --test-module backend.tests.test_docker_install_powershell --test-module backend.tests.test_install_support --test-module backend.tests.test_docker_install_smoke
```

PowerShell subprocess fixtures exercise both available shells with fake Docker, including
local/public binding and HTTP consent, malformed parameters, missing/stopped Docker,
unsupported engines, remote contexts, pull/capability failures, existing resources, a volume
ownership race, partial create/start failure, unhealthy/timeout recovery, token environment
restoration, local images, help, guided local/VPS questions (including declined consent),
and complete-download scriptblock execution.

The argument regression caught .NET `$` allowing a final newline; `\z` now requires the
actual end of the string. Tests run valid local mode so an unrelated interactive prompt
cannot hide an argument-validation failure. No negative fixture mutates a real daemon.

The existing Bash tests additionally check official prerequisite guidance. Support contracts
classify the new entry point and prevent documentation from advertising a nonexistent
PowerShell script at the old `v1.0.0` tag.

## Independent review corrections

One independent review identified two issues that were corrected before final verification:

- The smoke tool previously accepted a generic guided-install label during cleanup. It now
  refuses occupied target names before entering cleanup, records identities only after
  successful creation, validates exact run labels for clones, rechecks identity before removal,
  and removes containers by immutable ID. Failed/unrecorded partial installs are preserved.
  Six unit regressions cover collision, unrecorded resources, replaced container/volume
  identities, immutable-ID deletion, and clone label mismatch.
- Failed container creation or a volume ownership race no longer tells the user to start a
  container that this installer did not create. Volume-only recovery is distinguished from
  start/log guidance; negative-path tests verify this behavior.

Both real Docker rehearsals (PowerShell 5.1 and 7) passed again after these corrections.
Each reported four recorded resources removed, with no production data touched.
Source remains uncommitted pending the separate full pre-commit/release checkpoint.

## Boundaries and remaining release checks

- Published image scope remains Linux/amd64; native ARM64 is rejected.
- No physical Mac was available: macOS Intel remains manual-check-pending.
- Download URLs for the new PowerShell file are release templates until separately published.
  Verify the exact released script/image pair again at that point.
- Fake tests require PowerShell and Bash on PATH; no silent skip when a required shell is absent.
- No dependency, execution-policy, privilege or firewall changes are made by the installer.
- The Windows installer is not an updater. Maintenance documentation distinguishes Bash-only
  archive/update commands from portable lifecycle commands and warns about binary redirection
  in Windows PowerShell 5.1.
