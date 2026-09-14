# Contributing to Polaris

Thank you for improving Polaris. Contributions should keep the public API predictable, provider behavior isolated, and deployment defaults safe for operators.

## Before You Start

- Search existing issues before opening a new one.
- Discuss large API, storage, or routing changes before implementation.
- Report security issues privately according to [SECURITY.md](SECURITY.md).
- Keep pull requests focused. Separate mechanical refactors from behavioral changes whenever possible.

## Development Setup

Polaris supports Python 3.12 and newer versions covered by CI.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
cp .env.example .env
python backend/main.py
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.lock
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python backend/main.py
```

The console is available at `http://127.0.0.1:4283`. Runtime credentials, databases, logs, and `.env` files must remain untracked.

## Required Checks

Use the smallest gate matching the work. During implementation, run the fast gate and only the
affected test modules:

```bash
python tools/quality_gate.py fast
python tools/quality_gate.py task --test-module backend.tests.test_config_security
```

At a phase boundary, pass the affected integration/contract modules once:

```bash
python tools/quality_gate.py phase --test-module backend.tests.test_product_surface_inventory
```

Do not run the complete core suite after every edit. The single release command, its CI-owned
prerequisites, and separately classified optional suites can be inspected with:

```bash
python tools/quality_gate.py release --dry-run
python tools/quality_gate.py --list-suites
```

For frontend journey changes, install the isolated browser harness once and run it directly:

```bash
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
python tools/browser_smoke.py
```

CI labels production-blocking jobs and steps as `Required`. Live storage/provider checks and the
ten-minute soak are optional; retired Redis/HA/Kubernetes surfaces have no executable gate. See
[Quality gates](docs/quality-gates.md) for the exact cadence and suite classifications.

When `requirements.txt` changes, regenerate the production lock with Python 3.12:

```bash
pip-compile \
  --generate-hashes \
  --resolver=backtracking \
  --strip-extras \
  --no-header \
  --quiet \
  --output-file=requirements.lock \
  requirements.txt
```

Container publication starts only after the verification matrix, required Chromium browser smoke,
and container smoke succeed.

## Architecture Rules

- Keep HTTP parsing in `backend/core/router/` and provider orchestration in `backend/core/api/`.
- Keep format conversion deterministic and independent from storage or network access.
- Put provider metadata and capability decisions behind `provider_registry.py` and provider-specific adapters.
- Access persistence through `storage_adapter.py`; do not couple routes directly to a database driver.
- Keep presentation text in the frontend and return structured, sanitized errors from the backend.
- Preserve the `sk-ogw-` prefix for generated API keys.
- Add regression tests for every bug fix and contract tests for public route changes.

More detail is available in [docs/architecture.md](docs/architecture.md).

## Naming and Style

- Python modules and variables use `snake_case`; classes use `PascalCase`; constants use `UPPER_SNAKE_CASE`.
- Repository directories and non-Python asset names use lowercase `kebab-case` where practical.
- Use complete, natural English in UI text, logs, errors, comments, and documentation.
- Comments should explain constraints or intent rather than restating the code.
- Avoid branded namespaces in technical routes and configuration. Product branding belongs in presentation and documentation; `sk-ogw-` API keys are the intentional exception.

## Pull Requests

Describe the problem, the chosen solution, compatibility impact, verification performed, and any follow-up work. Screenshots are expected for visible interface changes. A pull request is ready when its tests pass, documentation is current, no secrets are present, and rollback implications are understood.

By contributing, you agree that your contribution is licensed under the repository's MIT License and that project interactions follow the [Code of Conduct](CODE_OF_CONDUCT.md).
