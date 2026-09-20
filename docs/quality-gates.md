# Quality Gates

Polaris uses one gate runner with increasing scope. Run commands from the repository root with
the active project virtual environment.

The maintained installer contract tests require Bash and PowerShell (`pwsh`, or
`powershell.exe` on Windows) on PATH. Docker is replaced by a subprocess fake in those
tests; they do not install dependencies or mutate the real daemon. Windows exercises both
shells when available. The separate `tools/docker_install_smoke.py --installer powershell`
or `--installer pwsh` rehearsal requires a running local Linux/amd64 Docker engine and
uses only isolated temporary resources.

## Gate Selection

| Situation | Command | Scope |
| --- | --- | --- |
| While editing | `python tools/quality_gate.py fast` | Lint, format, compile, suite partition, recursive JavaScript syntax, YAML, shell syntax, whitespace |
| End of one task | `python tools/quality_gate.py task --test-module backend.tests.test_config_security` | Fast gate plus only explicitly affected core test modules |
| Broader integration checkpoint | `python tools/quality_gate.py phase --test-module backend.tests.test_product_surface_inventory` | Fast gate, config contracts, translation audits, and the affected integration/DOM slice |
| Release candidate | `python tools/quality_gate.py release` | One complete required core, dependency, routine reliability, application, browser, and container gate |

Repeat `--test-module` for every directly affected module. Task and phase commands reject empty
test selections. Use `--dry-run` or `--list` to inspect a gate without executing it.

Before a commit is authorized, use `python tools/quality_gate.py release --working-tree`.
Its reliability step freezes tracked and non-ignored source files into an isolated snapshot,
records per-file and combined SHA-256 hashes, and saves the result to
`temp/release-reliability-working-tree.json`. This is working-tree evidence, not a tagged
candidate certification. The normal release command still measures the immutable Git candidate.
Never edit source while a snapshot is being collected. Ignored `.env`, databases and preview
artifacts are not copied. The browser runtime keeps only OS launch variables, disables dotenv
and price synchronization, and never inherits operator keys, proxies or telemetry settings.

The required Chromium harness is `python tools/browser_smoke.py`. Install its isolated dependency
with `python -m pip install -r requirements-browser.txt` and its browser with
`python -m playwright install chromium`. It starts a fresh loopback-only runtime, uses disposable
SQLite state, blocks real provider traffic with deterministic in-browser fixtures, and exercises
all nine critical journeys plus an 11-route accessibility/overflow sweep at 360, 768, 1024, and
1440 pixels and a keyboard-navigation smoke. The release runner executes it locally; CI installs
Chromium with its Linux system dependencies in a dedicated required job.

The release-blocking reliability profile is a 120-second, 5 RPS, eight-concurrency routine signal
that retains the established latency, error, memory, dashboard, shutdown, and restart thresholds.
Run it directly with `python tools/reliability_profile.py --profile routine --verify`. The original
600-second, 10 RPS profile remains available as an optional major-release soak.

The application and container smokes remain required CI evidence; the release runner labels them
as CI-owned instead of pretending to execute them locally. The release checklist requires the
application, browser, and container jobs to pass for the same candidate commit.

Manual `workflow_dispatch` runs are verification-only, including when dispatched on
`main` or a tag. Container publication is restricted to push events on `main` or
`v*` tags; release creation requires a `v*` tag push and all required jobs. Use manual
dispatch on the preparation branch to collect CI evidence without publishing anything.

The phase/release configuration contracts also run the versioned R1 compatibility guard and load
the pre-R1 SQLite upgrade fixture. See [Compatibility and deprecation](compatibility.md).

## Required Versus Non-Required

CI names production-blocking verification jobs and steps with `Required:`. The production release
plan never contains any of these separately reported suites:

| Suite | Classification | Command/evidence | Owner |
| --- | --- | --- | --- |
| External storage contracts (PostgreSQL Advanced; MongoDB Compatibility) | Optional | `python -m unittest backend.tests.test_durable_family_migration backend.tests.test_identity_repository_live backend.tests.test_usage_ledger_live -v` | P5.1 |
| Live provider checks | Optional/manual | `docs/release-checklist.md#manual-provider-checks` | P2.1/P2.2 |
| Ten-minute reliability soak | Optional | `python tools/reliability_profile.py --profile soak --verify` | PB6 |

List the canonical classifications at any time:

```text
python tools/quality_gate.py --list-suites
```

Skipping or failing an optional suite must be reported under that classification, but
cannot change the Core production verdict. Conversely, no skipped test may cover a Core production
journey.

## Fixed Cadence

- Task: one fast gate plus focused modules after the final relevant edit.
- Broader integration change: one affected integration/DOM/browser slice through the retained
  `phase` CLI alias; it does not create a planning phase or a second progress denominator.
- Release: one complete required gate on the immutable candidate. After failure, rerun only the
  failed slice until corrected, then repeat the complete gate once.
- Redis coordination, multi-replica, and Kubernetes verification were retired with those product
  surfaces. Live providers, optional external storage, and the ten-minute soak remain outside the
  required cadence.
