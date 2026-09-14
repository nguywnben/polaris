"""Run the backend test suite with repository-safe defaults."""

from __future__ import annotations

import argparse
import sys
import unittest

from backend.tests.suite_manifest import (
    all_test_modules,
    build_suite,
    core_test_modules,
    validate_suite_partition,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a named Polaris backend test suite.")
    parser.add_argument(
        "--suite",
        choices=("core", "all"),
        default="core",
        help="Suite to run. The default production gate contains every maintained test module.",
    )
    parser.add_argument("--list", action="store_true", help="List modules without importing them.")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Validate that retired topology tests have not been reintroduced.",
    )
    return parser


def _modules_for_suite(name: str) -> tuple[str, ...]:
    if name == "core":
        return core_test_modules()
    return all_test_modules()


def main(arguments: list[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    validate_suite_partition()
    modules = _modules_for_suite(options.suite)
    if options.audit:
        print(f"Backend test manifest valid: core={len(core_test_modules())}.")
        if not options.list:
            return 0
    if options.list:
        print(f"suite={options.suite}; modules={len(modules)}")
        print("\n".join(modules))
        return 0
    suite = build_suite(options.suite)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
