"""Reproduce the P0.4 static maintainability inventory without third-party packages."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

INVENTORY_CATEGORIES = (
    "large_modules",
    "storage_families",
    "pydantic_deprecations",
    "broad_exception_handlers",
    "skipped_and_live_tests",
    "frontend_test_gaps",
)
LARGE_MODULE_LINES = 1_500
PYDANTIC_V1_METHODS = frozenset({"dict", "parse_obj", "parse_raw", "from_orm"})
STORAGE_VARIANT = re.compile(r"^(?P<family>.+)_(?P<backend>sqlite|postgresql|mongodb)$")
MANAGER_VARIANT = re.compile(r"^(?P<backend>sqlite|postgresql|mongodb)_manager$")


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _line_count(path: Path) -> int:
    return len(_text(path).splitlines())


def _runtime_python_files(root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted((root / "backend").rglob("*.py"))
        if "tests" not in path.parts
        and "data" not in path.parts
        and "__pycache__" not in path.parts
    )


def _large_modules(root: Path) -> dict[str, Any]:
    candidates = list(_runtime_python_files(root))
    candidates.extend(sorted((root / "frontend" / "js").rglob("*.js")))
    modules = []
    for path in candidates:
        lines = _line_count(path)
        if lines >= LARGE_MODULE_LINES:
            modules.append({"path": _relative(root, path), "lines": lines})
    modules.sort(key=lambda item: (-item["lines"], item["path"]))
    return {"threshold_lines": LARGE_MODULE_LINES, "modules": modules}


def _storage_families(root: Path) -> list[dict[str, Any]]:
    families: dict[str, list[dict[str, Any]]] = {}
    for path in sorted((root / "backend" / "core" / "storage").glob("*.py")):
        match = STORAGE_VARIANT.fullmatch(path.stem)
        manager_match = MANAGER_VARIANT.fullmatch(path.stem)
        if match:
            family, backend = match.group("family"), match.group("backend")
        elif manager_match:
            family, backend = "state_manager", manager_match.group("backend")
        else:
            continue
        families.setdefault(family, []).append(
            {"backend": backend, "path": _relative(root, path), "lines": _line_count(path)}
        )
    return [
        {"family": family, "implementations": sorted(items, key=lambda item: item["backend"])}
        for family, items in sorted(families.items())
        if len(items) >= 2
    ]


def _pydantic_deprecations(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in _runtime_python_files(root):
        tree = ast.parse(_text(path), filename=str(path))
        for node in ast.walk(tree):
            kind = None
            if isinstance(node, ast.ClassDef) and node.name == "Config":
                kind = "class_based_config"
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in PYDANTIC_V1_METHODS:
                    kind = f"legacy_{node.func.attr}_call"
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorators = {
                    decorator.id
                    for decorator in node.decorator_list
                    if isinstance(decorator, ast.Name)
                }
                legacy = decorators.intersection({"validator", "root_validator"})
                if legacy:
                    kind = f"legacy_{sorted(legacy)[0]}_decorator"
            if kind:
                findings.append({"path": _relative(root, path), "line": node.lineno, "kind": kind})
    return sorted(findings, key=lambda item: (item["path"], item["line"], item["kind"]))


def _exception_area(path: str) -> str:
    if "/storage/" in path or path.endswith(("state_store.py", "storage_adapter.py")):
        return "storage"
    if any(token in path for token in ("/identity/", "/auth", "virtual_keys.py")):
        return "access_security"
    if any(token in path for token in ("/api/", "/converter/", "/router/", "gateway_pipeline.py")):
        return "protocol_routing"
    if any(token in path for token in ("credential", "/providers/", "provider_")):
        return "provider_credentials"
    if "coordination" in path:
        return "runtime_coordination"
    return "runtime_operations"


def _broad_exception_handlers(root: Path) -> dict[str, Any]:
    by_file: Counter[str] = Counter()
    suppressing_by_file: Counter[str] = Counter()
    by_area: Counter[str] = Counter()
    suppressing_total = 0
    for path in _runtime_python_files(root):
        relative = _relative(root, path)
        tree = ast.parse(_text(path), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            broad = node.type is None or (
                isinstance(node.type, ast.Name) and node.type.id == "Exception"
            )
            if not broad:
                continue
            by_file[relative] += 1
            by_area[_exception_area(relative)] += 1
            reraises = any(
                isinstance(child, ast.Raise) for child in node.body for child in ast.walk(child)
            )
            if not reraises:
                suppressing_by_file[relative] += 1
                suppressing_total += 1
    hotspots = [
        {"path": path, "handlers": count, "without_reraise": suppressing_by_file[path]}
        for path, count in by_file.items()
    ]
    hotspots.sort(key=lambda item: (-item["without_reraise"], -item["handlers"], item["path"]))
    return {
        "handlers": sum(by_file.values()),
        "without_reraise": suppressing_total,
        "files": len(by_file),
        "by_area": dict(sorted(by_area.items())),
        "top_hotspots": hotspots[:15],
    }


def _skipped_and_live_tests(root: Path) -> dict[str, Any]:
    skip_sites: list[dict[str, Any]] = []
    live_modules: set[str] = set()
    for path in sorted((root / "backend" / "tests").glob("test_*.py")):
        source = _text(path)
        relative = _relative(root, path)
        if path.stem.endswith("_live") or "POLARIS_TEST_" in source:
            live_modules.add(relative)
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"skip", "skipIf", "skipUnless", "skipTest"}:
                continue
            skip_sites.append({"path": relative, "line": node.lineno, "kind": node.func.attr})
    return {
        "skip_sites": sorted(skip_sites, key=lambda item: (item["path"], item["line"])),
        "live_modules": sorted(live_modules),
    }


def _frontend_test_gaps(root: Path) -> dict[str, Any]:
    javascript_modules = sorted((root / "frontend" / "js").rglob("*.js"))
    native_tests = sorted((root / "frontend").rglob("*.test.js"))
    native_tests.extend(sorted((root / "frontend").rglob("*.spec.js")))
    backend_contracts = []
    for path in sorted((root / "backend" / "tests").glob("test_*.py")):
        source = _text(path).lower()
        if "frontend" in path.stem or ("node" in source and "frontend" in source):
            backend_contracts.append(_relative(root, path))
    browser_configs = [
        path
        for pattern in ("playwright.config.*", "cypress.config.*")
        for path in root.glob(pattern)
    ]
    return {
        "javascript_modules": len(javascript_modules),
        "package_manifest_present": (root / "package.json").exists()
        or (root / "frontend" / "package.json").exists(),
        "native_javascript_tests": [_relative(root, path) for path in sorted(set(native_tests))],
        "backend_dom_contract_modules": backend_contracts,
        "browser_harness_configs": [_relative(root, path) for path in sorted(browser_configs)],
    }


def build_inventory(root: Path) -> dict[str, Any]:
    """Return the deterministic repository measurements stored by the P0.4 baseline."""

    root = root.resolve()
    return {
        "large_modules": _large_modules(root),
        "storage_families": _storage_families(root),
        "pydantic_deprecations": _pydantic_deprecations(root),
        "broad_exception_handlers": _broad_exception_handlers(root),
        "skipped_and_live_tests": _skipped_and_live_tests(root),
        "frontend_test_gaps": _frontend_test_gaps(root),
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", type=Path, help="Compare with the inventory in a baseline JSON file."
    )
    options = parser.parse_args(arguments)
    root = Path(__file__).resolve().parents[1]
    inventory = build_inventory(root)
    if options.check:
        baseline = json.loads(options.check.read_text(encoding="utf-8"))
        if baseline.get("inventory") != inventory:
            print("Maintainability inventory is stale.", file=sys.stderr)
            return 1
        print(f"Maintainability inventory matches {options.check}.")
        return 0
    print(json.dumps(inventory, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
