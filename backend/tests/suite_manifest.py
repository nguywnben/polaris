"""Production backend test-suite manifest."""

from __future__ import annotations

import unittest
from pathlib import Path

TESTS_DIRECTORY = Path(__file__).resolve().parent


def all_test_modules() -> tuple[str, ...]:
    """Return every discoverable backend unittest module in deterministic order."""

    return tuple(sorted(path.stem for path in TESTS_DIRECTORY.glob("test_*.py")))


def core_test_modules() -> tuple[str, ...]:
    """Return every production test module."""

    return all_test_modules()


def validate_suite_partition() -> None:
    """Fail when a retired topology test is accidentally reintroduced."""

    retired = sorted(
        name
        for name in all_test_modules()
        if name.startswith("test_ha_")
        or name.endswith("_redis_live")
        or name == "test_redis_state_store"
    )
    if retired:
        raise RuntimeError(f"Retired topology tests are present: {retired}.")


def build_suite(name: str) -> unittest.TestSuite:
    """Load one named suite without importing modules assigned to another suite."""

    validate_suite_partition()
    if name == "core":
        modules = core_test_modules()
    elif name == "all":
        modules = all_test_modules()
    else:
        raise ValueError(f"Unknown backend test suite: {name}")
    loader = unittest.defaultTestLoader
    return unittest.TestSuite(
        loader.loadTestsFromName(f"backend.tests.{module}") for module in modules
    )
