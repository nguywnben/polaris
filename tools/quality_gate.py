"""Run the production self-hosted quality-gate layers."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = "{python}"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class GateStep:
    id: str
    label: str
    commands: tuple[tuple[str, ...], ...] = ()
    status: str = "active"
    owner: str = ""


@dataclass(frozen=True)
class OptionalSuite:
    classification: str
    mode: str
    command: str
    owner: str


BACKEND_LINT = GateStep(
    "backend-lint",
    "Backend and tooling lint",
    ((PYTHON, "-m", "ruff", "check", "backend", "tools"),),
)
BACKEND_FORMAT = GateStep(
    "backend-format",
    "Backend and tooling format",
    ((PYTHON, "-m", "ruff", "format", "--check", "backend", "tools"),),
)
PYTHON_COMPILE = GateStep(
    "python-compile",
    "Python bytecode compilation",
    ((PYTHON, "-m", "compileall", "-q", "backend", "tools"),),
)
TEST_PARTITION = GateStep(
    "test-partition",
    "Production test manifest audit",
    ((PYTHON, "-m", "backend.tests", "--audit"),),
)
JAVASCRIPT_SYNTAX = GateStep("javascript-syntax", "Recursive frontend JavaScript syntax")
YAML_SYNTAX = GateStep(
    "yaml-syntax",
    "Strict deployment and workflow YAML lint",
    ((PYTHON, "-m", "yamllint", "--strict", ".github", "deploy", ".yamllint.yml"),),
)
SHELL_SYNTAX = GateStep("shell-syntax", "Deployment shell syntax")
WHITESPACE = GateStep(
    "whitespace",
    "Working-tree and staged whitespace",
    (("git", "diff", "--check"), ("git", "diff", "--cached", "--check")),
)
CONFIGURATION_CONTRACTS = GateStep(
    "configuration-contracts",
    "Configuration and inventory contracts",
    (
        (
            PYTHON,
            "-m",
            "unittest",
            "backend.tests.test_configuration_schema",
            "backend.tests.test_compose_profile",
            "backend.tests.test_config_initialization",
            "backend.tests.test_config_security",
            "backend.tests.test_runtime_configuration",
            "backend.tests.test_product_surface_inventory",
            "backend.tests.test_compatibility_guard",
            "-v",
        ),
    ),
)
TRANSLATION_AUDIT = GateStep(
    "translation-audit",
    "Frontend and backend translation audits",
    (
        (PYTHON, "tools/i18n-static-audit.py"),
        (PYTHON, "tools/i18n-js-audit.py"),
        ("node", "tools/i18n-audit.mjs"),
        (PYTHON, "tools/backend-i18n-audit.py"),
    ),
)
DEPENDENCY_COMPATIBILITY = GateStep(
    "dependency-compatibility",
    "Installed dependency compatibility",
    ((PYTHON, "-m", "pip", "check"),),
)
DEPENDENCY_AUDIT = GateStep(
    "dependency-audit",
    "Runtime dependency vulnerability audit",
    ((PYTHON, "-m", "pip_audit", "--local", "--progress-spinner", "off"),),
)
CORE_SUITE = GateStep(
    "core-suite",
    "Complete production core suite",
    ((PYTHON, "-m", "backend.tests", "--suite", "core"),),
)
APPLICATION_SMOKE = GateStep(
    "application-smoke",
    "Authenticated application runtime smoke",
    status="ci",
)
BROWSER_SMOKE = GateStep(
    "browser-smoke",
    "Critical-journey browser smoke",
    ((PYTHON, "tools/browser_smoke.py"),),
    owner="P5.4",
)
RELIABILITY_PROFILE = GateStep(
    "reliability-profile",
    "Routine production reliability and performance profile",
    ((PYTHON, "tools/reliability_profile.py", "--profile", "routine", "--verify"),),
    owner="PB6",
)
CONTAINER_SMOKE = GateStep(
    "container-smoke",
    "Fresh image and container runtime smoke",
    status="ci",
)

FAST_STEPS = (
    BACKEND_LINT,
    BACKEND_FORMAT,
    PYTHON_COMPILE,
    TEST_PARTITION,
    JAVASCRIPT_SYNTAX,
    YAML_SYNTAX,
    SHELL_SYNTAX,
    WHITESPACE,
)

OPTIONAL_SUITES = {
    "storage-live": OptionalSuite(
        classification="optional",
        mode="automated",
        command=(
            "python -m unittest backend.tests.test_durable_family_migration "
            "backend.tests.test_identity_repository_live backend.tests.test_usage_ledger_live -v"
        ),
        owner="P5.1",
    ),
    "provider-live": OptionalSuite(
        classification="optional",
        mode="manual",
        command="docs/release-checklist.md#manual-provider-checks",
        owner="P2.1/P2.2",
    ),
    "reliability-soak": OptionalSuite(
        classification="optional",
        mode="automated",
        command="python tools/reliability_profile.py --profile soak --verify",
        owner="PB6",
    ),
}


def _focused_step(modules: tuple[str, ...]) -> GateStep:
    if not modules:
        raise ValueError("The task/phase gate requires at least one focused test module.")
    from backend.tests.suite_manifest import core_test_modules

    core = set(core_test_modules())
    normalized = []
    for module in modules:
        stem = module.removeprefix("backend.tests.")
        if stem not in core:
            raise ValueError(f"Focused module is not part of the production core suite: {module}")
        normalized.append(f"backend.tests.{stem}")
    return GateStep(
        "focused-tests",
        "Explicitly selected affected tests",
        ((PYTHON, "-m", "unittest", *normalized, "-v"),),
    )


def _unique(steps: tuple[GateStep, ...]) -> tuple[GateStep, ...]:
    return tuple({step.id: step for step in steps}.values())


def build_gate_plan(
    gate: str,
    focused_modules: tuple[str, ...] = (),
) -> tuple[GateStep, ...]:
    """Return a deterministic plan without executing commands."""

    if gate == "fast":
        return FAST_STEPS
    if gate == "task":
        return (*FAST_STEPS, _focused_step(focused_modules))
    if gate == "phase":
        return _unique(
            (
                *FAST_STEPS,
                CONFIGURATION_CONTRACTS,
                TRANSLATION_AUDIT,
                _focused_step(focused_modules),
            )
        )
    if gate == "release":
        return _unique(
            (
                *FAST_STEPS,
                CONFIGURATION_CONTRACTS,
                TRANSLATION_AUDIT,
                DEPENDENCY_COMPATIBILITY,
                DEPENDENCY_AUDIT,
                CORE_SUITE,
                APPLICATION_SMOKE,
                BROWSER_SMOKE,
                RELIABILITY_PROFILE,
                CONTAINER_SMOKE,
            )
        )
    raise ValueError(f"Unknown quality gate: {gate}")


def _bash_executable() -> str:
    if sys.platform == "win32":
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        if git_bash.exists():
            return str(git_bash)
    executable = shutil.which("bash")
    if executable is None:
        raise RuntimeError("bash is required to validate deploy/scripts/*.sh")
    return executable


def _commands_for(step: GateStep) -> tuple[tuple[str, ...], ...]:
    if step.id == "javascript-syntax":
        scripts = sorted((ROOT / "frontend" / "js").rglob("*.js"))
        return tuple(("node", "--check", str(script.relative_to(ROOT))) for script in scripts)
    if step.id == "shell-syntax":
        scripts = sorted((ROOT / "deploy" / "scripts").glob("*.sh"))
        bash = _bash_executable()
        return tuple((bash, "-n", str(script.relative_to(ROOT))) for script in scripts)
    return tuple(
        tuple(sys.executable if token == PYTHON else token for token in command)
        for command in step.commands
    )


def _display_step(step: GateStep) -> None:
    suffix = f"; owner={step.owner}" if step.owner else ""
    print(f"- {step.id} [{step.status}{suffix}]: {step.label}")
    if step.status != "active":
        return
    commands = _commands_for(step)
    if step.id in {"javascript-syntax", "shell-syntax"}:
        print(f"    {step.id}: {len(commands)} files")
        return
    for command in commands:
        print("    " + subprocess.list2cmdline(command))


def _run_plan(plan: tuple[GateStep, ...]) -> int:
    pending = [step for step in plan if step.status == "pending"]
    if pending:
        for step in pending:
            _display_step(step)
        print(
            "Gate cannot run until every pending required check is implemented.",
            file=sys.stderr,
        )
        return 2
    for step in plan:
        if step.status == "ci":
            print(f"==> {step.label} [required CI evidence]", flush=True)
            continue
        print(f"==> {step.label}", flush=True)
        for command in _commands_for(step):
            completed = subprocess.run(command, cwd=ROOT, check=False)
            if completed.returncode:
                return completed.returncode
    print("Quality gate passed.")
    return 0


def _list_optional_suites() -> None:
    for name, suite in OPTIONAL_SUITES.items():
        mode = f"; {suite.mode}" if suite.mode == "manual" else ""
        print(f"{name} [{suite.classification}{mode}] owner={suite.owner}")
        print(f"    {suite.command}")


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", nargs="?", choices=("fast", "task", "phase", "release"))
    parser.add_argument("--test-module", action="append", default=[])
    parser.add_argument("--list", action="store_true", help="List a gate without executing it.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print exact gate steps and commands."
    )
    parser.add_argument("--list-suites", action="store_true", help="List non-required suites.")
    options = parser.parse_args(arguments)
    if options.list_suites:
        _list_optional_suites()
        return 0
    if options.gate is None:
        parser.error("a gate is required unless --list-suites is used")
    try:
        plan = build_gate_plan(options.gate, tuple(options.test_module))
    except ValueError as exc:
        parser.error(str(exc))
    if options.list or options.dry_run:
        print(f"{options.gate} gate ({len(plan)} steps)")
        for step in plan:
            _display_step(step)
        return 0
    return _run_plan(plan)


if __name__ == "__main__":
    raise SystemExit(main())
