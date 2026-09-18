"""Build and verify the versioned R1 backward-compatibility baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
BASELINE_PATH = ROOT / "docs" / "compatibility" / "r1-compatibility-v1.json"
HTTP_METHODS = frozenset({"delete", "get", "head", "options", "patch", "post", "put"})
PUBLIC_PREFIXES = ("/v1/", "/v1beta/", "/vertex/")
NON_SEMANTIC_OPENAPI_KEYS = frozenset(
    {"description", "example", "examples", "externalDocs", "operationId", "summary", "title"}
)
# Adding the optional bounded timezone offset preserves every existing request shape. Keep the
# exact before/after fingerprints explicit so unrelated changes to these operations still fail.
COMPATIBLE_OPERATION_EVOLUTIONS = {
    # ADR-014 adds a separate native Meta branch while retaining the exact legacy
    # Responses schema. HTTP/legacy regression tests cover dispatch and rejection;
    # the fixed pair still detects every subsequent contract change.
    ("POST", "/v1/responses"): {
        (
            "250ef7feb1b25caf10b5dc22fbb7fd3c078c7a3f61cec725ee8909b9d29c2f1a",
            "c97da5d6f21619854cde9d63bfff79aa7c6a96cc7fa70208baffe2d7adcf0247",
        )
    },
    # Optional scope defaults to the original reset. Exact evolution, not a route exemption:
    # test_config_reset proves default behavior and secret/environment preservation;
    # docs/audits/page-completion-2026-09-15.md records the approved Settings ownership change.
    ("POST", "/api/config/reset"): {
        (
            "d65b29bf9cea9ec3ea65a5946b9bbcac8f273f58af3fa5aee1d00f120dfe55cd",
            "f487b1e95130ad2170997da96ec23e6f4c3dec11400c74582751d657a1d4f87f",
        )
    },
    ("GET", "/api/usage/aggregated"): {
        (
            "64b2af52f77a274f4829f1f395e8102884f6024e10a743a0bc0a01f37619e871",
            "15b43529ff0bb94c39e18ac82729d0806d9abc82ae6deda02fb3d08057ce1cb0",
        )
    },
    ("GET", "/api/usage/stats"): {
        (
            "64b2af52f77a274f4829f1f395e8102884f6024e10a743a0bc0a01f37619e871",
            "15b43529ff0bb94c39e18ac82729d0806d9abc82ae6deda02fb3d08057ce1cb0",
        )
    },
}

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


CLIENT_EXAMPLES = (
    {
        "id": "python-openai-chat",
        "method": "POST",
        "operation_path": "/v1/chat/completions",
        "base_path": "/v1",
        "source_markers": (
            {"path": "README.md", "contains": 'OpenAI(base_url="http://127.0.0.1:4283/v1"'},
            {
                "path": "frontend/fragments/pages/access.html",
                "contains": "OpenAI(base_url, api_key)",
            },
            {
                "path": "frontend/js/ui/api-integration.js",
                "contains": "openaiEl.textContent = `${origin}/v1`",
            },
        ),
    },
    {
        "id": "python-openai-responses",
        "method": "POST",
        "operation_path": "/v1/responses",
        "base_path": "/v1",
        "source_markers": ({"path": "README.md", "contains": "client.responses.create("},),
    },
    {
        "id": "python-anthropic-messages",
        "method": "POST",
        "operation_path": "/v1/messages",
        "base_path": "/",
        "source_markers": (
            {"path": "README.md", "contains": 'Anthropic(base_url="http://127.0.0.1:4283"'},
            {
                "path": "frontend/fragments/pages/access.html",
                "contains": "Anthropic(base_url, api_key)",
            },
            {
                "path": "frontend/js/ui/api-integration.js",
                "contains": "anthropicEl.textContent = origin",
            },
        ),
    },
    {
        "id": "python-google-genai",
        "method": "POST",
        "operation_path": "/v1beta/models/{model}:generateContent",
        "base_path": "/",
        "source_markers": (
            {"path": "README.md", "contains": '"base_url": "http://127.0.0.1:4283"'},
            {
                "path": "frontend/fragments/pages/access.html",
                "contains": "genai.Client(api_key, http_options)",
            },
            {
                "path": "frontend/js/ui/api-integration.js",
                "contains": "googleGenaiEl.textContent = origin",
            },
        ),
    },
    {
        "id": "node-openai-chat",
        "method": "POST",
        "operation_path": "/v1/chat/completions",
        "base_path": "/v1",
        "source_markers": (
            {
                "path": "frontend/fragments/pages/access.html",
                "contains": "new OpenAI({ baseURL, apiKey })",
            },
        ),
    },
    {
        "id": "node-anthropic-messages",
        "method": "POST",
        "operation_path": "/v1/messages",
        "base_path": "/",
        "source_markers": (
            {
                "path": "frontend/fragments/pages/access.html",
                "contains": "new Anthropic({ baseURL, apiKey })",
            },
        ),
    },
    {
        "id": "node-google-genai",
        "method": "POST",
        "operation_path": "/v1beta/models/{model}:generateContent",
        "base_path": "/",
        "source_markers": (
            {
                "path": "frontend/fragments/pages/access.html",
                "contains": "new GoogleGenAI({ apiKey, httpOptions })",
            },
        ),
    },
)


def _resolve_reference(document: dict[str, Any], reference: str) -> Any:
    if not reference.startswith("#/"):
        return {"$external_ref": reference}
    value: Any = document
    for part in reference[2:].split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    return value


def _semantic_value(
    value: Any, document: dict[str, Any], trail: frozenset[str] = frozenset()
) -> Any:
    if isinstance(value, list):
        return [_semantic_value(item, document, trail) for item in value]
    if not isinstance(value, dict):
        return value
    reference = value.get("$ref")
    if isinstance(reference, str):
        if reference in trail:
            return {"$recursive_ref": reference}
        resolved = _semantic_value(
            _resolve_reference(document, reference), document, trail | {reference}
        )
        siblings = {
            key: _semantic_value(item, document, trail)
            for key, item in value.items()
            if key != "$ref" and key not in NON_SEMANTIC_OPENAPI_KEYS
        }
        return {"$resolved_ref": reference, "schema": resolved, **siblings}
    return {
        key: _semantic_value(item, document, trail)
        for key, item in sorted(value.items())
        if key not in NON_SEMANTIC_OPENAPI_KEYS
    }


def _operation_snapshot(document: dict[str, Any], method: str, path: str) -> dict[str, str]:
    operation = document["paths"][path][method.lower()]
    semantic = _semantic_value(operation, document)
    encoded = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "method": method.upper(),
        "path": path,
        "semantic_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }


def _operations(document: dict[str, Any], predicate) -> list[dict[str, str]]:
    return [
        _operation_snapshot(document, method, path)
        for path, path_item in sorted(document["paths"].items())
        if predicate(path)
        for method in sorted(path_item)
        if method in HTTP_METHODS
    ]


def _javascript_map(source: str, constant: str) -> dict[str, str]:
    match = re.search(rf"const\s+{re.escape(constant)}\s*=\s*\{{(?P<body>.*?)\}};", source, re.S)
    if match is None:
        raise RuntimeError(f"Could not locate {constant} in frontend navigation.")
    pairs = re.findall(
        r"(?:['\"]([^'\"]+)['\"]|([A-Za-z_$][\w$]*))\s*:\s*['\"]([^'\"]+)['\"]",
        match["body"],
    )
    return {quoted or bare: value for quoted, bare, value in pairs}


def _database_versions() -> dict[str, int]:
    from core.audit import AUDIT_SCHEMA_VERSION
    from core.durable_migration import MIGRATION_SCHEMA_VERSION
    from core.identity.oidc_policy import OIDC_POLICY_SCHEMA_VERSION
    from core.identity.repository import IDENTITY_SCHEMA_VERSION
    from core.identity.sessions import SESSION_SCHEMA_VERSION
    from core.quality_policy import POLICY_SCHEMA_VERSION
    from core.request_trace import REQUEST_TRACE_SCHEMA_VERSION
    from core.usage_ledger import USAGE_LEDGER_SCHEMA_VERSION
    from core.virtual_keys import VIRTUAL_KEY_SCHEMA_VERSION

    return {
        "audit_event": AUDIT_SCHEMA_VERSION,
        "durable_migration_checkpoint": MIGRATION_SCHEMA_VERSION,
        "identity_and_role_binding": IDENTITY_SCHEMA_VERSION,
        "management_session": SESSION_SCHEMA_VERSION,
        "oidc_policy": OIDC_POLICY_SCHEMA_VERSION,
        "quality_policy": POLICY_SCHEMA_VERSION,
        "request_trace": REQUEST_TRACE_SCHEMA_VERSION,
        "usage_ledger": USAGE_LEDGER_SCHEMA_VERSION,
        "virtual_key": VIRTUAL_KEY_SCHEMA_VERSION,
    }


def build_snapshot() -> dict[str, object]:
    """Return the deterministic compatibility surface implemented by the current checkout."""

    import config
    from core.panel.root import router as root_router
    from core.panel.root import serve_control_panel
    from main import app

    document = app.openapi()
    navigation = (ROOT / "frontend" / "js" / "core" / "navigation.js").read_text(encoding="utf-8")
    server_paths = sorted(
        route.path
        for route in root_router.routes
        if getattr(route, "endpoint", None) is serve_control_panel
    )
    return {
        "schema_version": 1,
        "profile": "production-self-hosted-r1",
        "contract_version": "r1-v1",
        "public_inference_operations": _operations(
            document, lambda path: path.startswith(PUBLIC_PREFIXES)
        ),
        "management_operations": _operations(document, lambda path: path.startswith("/api/")),
        "config_compatibility": {
            "removed_environment_errors": dict(sorted(config.REMOVED_ENVIRONMENT_ERRORS.items())),
            "removed_environment_renames": dict(sorted(config.LEGACY_ENV_RENAMES.items())),
            "stored_key_renames": dict(sorted(config.LEGACY_STORED_KEY_RENAMES.items())),
            "removed_stored_keys": sorted(config.REMOVED_STORED_KEYS),
        },
        "database_schema_versions": _database_versions(),
        "console_routes": {
            "server_paths": server_paths,
            "route_map": _javascript_map(navigation, "ROUTE_MAP"),
            "tab_map": _javascript_map(navigation, "TAB_MAP"),
            "compatibility_aliases": {
                "/oauth": "/providers",
                "/provider": "/credentials",
                "/upload": "/providers",
            },
        },
        "generated_client_examples": json.loads(json.dumps(CLIENT_EXAMPLES)),
    }


def _operation_index(snapshot: dict[str, object], name: str) -> dict[tuple[str, str], str]:
    return {(entry["method"], entry["path"]): entry["semantic_sha256"] for entry in snapshot[name]}


def compare_snapshots(baseline: dict[str, object], current: dict[str, object]) -> list[str]:
    """Return compatibility violations; additive current surfaces are accepted."""

    differences: list[str] = []
    for name in ("public_inference_operations", "management_operations"):
        expected = _operation_index(baseline, name)
        actual = _operation_index(current, name)
        for operation, fingerprint in expected.items():
            if operation not in actual:
                differences.append(f"removed {name}: {operation[0]} {operation[1]}")
            elif actual[operation] != fingerprint and (
                fingerprint,
                actual[operation],
            ) not in COMPATIBLE_OPERATION_EVOLUTIONS.get(operation, set()):
                differences.append(f"changed {name}: {operation[0]} {operation[1]}")

    expected_config = baseline["config_compatibility"]
    actual_config = current["config_compatibility"]
    for name in (
        "removed_environment_errors",
        "removed_environment_renames",
        "stored_key_renames",
    ):
        changed = sorted(
            key
            for key, value in expected_config[name].items()
            if actual_config[name].get(key) != value
        )
        if changed:
            differences.append(f"changed config_compatibility.{name}: {changed}")
    removed_stored_keys = sorted(
        set(expected_config["removed_stored_keys"]) - set(actual_config["removed_stored_keys"])
    )
    if removed_stored_keys:
        differences.append(
            f"removed config_compatibility.removed_stored_keys: {removed_stored_keys}"
        )

    if baseline["database_schema_versions"] != current["database_schema_versions"]:
        differences.append("changed database_schema_versions")

    # User-approved page rename (2026-09-16), deliberately without a /pool alias.
    # Keep the historical R1 fixture intact and require the entire replacement contract.
    expected_routes = json.loads(json.dumps(baseline["console_routes"]))
    expected_routes["server_paths"] = [
        "/credentials" if path == "/pool" else path for path in expected_routes["server_paths"]
    ]
    expected_routes["route_map"] = {
        ("/credentials" if path == "/pool" else path): ("credentials" if tab == "pool" else tab)
        for path, tab in expected_routes["route_map"].items()
    }
    expected_routes["tab_map"] = {
        ("credentials" if tab == "pool" else tab): ("/credentials" if path == "/pool" else path)
        for tab, path in expected_routes["tab_map"].items()
    }
    expected_routes["compatibility_aliases"] = {
        alias: "/credentials" if path == "/pool" else path
        for alias, path in expected_routes["compatibility_aliases"].items()
    }
    actual_routes = current["console_routes"]
    for name in ("server_paths", "route_map", "tab_map", "compatibility_aliases"):
        expected = expected_routes[name]
        actual = actual_routes[name]
        if isinstance(expected, list):
            missing = sorted(set(expected) - set(actual))
            if missing:
                differences.append(f"removed console_routes.{name}: {missing}")
        else:
            changed = sorted(key for key, value in expected.items() if actual.get(key) != value)
            if changed:
                differences.append(f"changed console_routes.{name}: {changed}")

    expected_examples = {entry["id"]: entry for entry in baseline["generated_client_examples"]}
    actual_examples = {entry["id"]: entry for entry in current["generated_client_examples"]}
    changed_examples = sorted(
        identifier
        for identifier, example in expected_examples.items()
        if actual_examples.get(identifier) != example
    )
    if changed_examples:
        differences.append(f"changed generated_client_examples: {changed_examples}")
    return differences


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="Check current code against baseline.")
    action.add_argument("--print", action="store_true", dest="print_snapshot")
    options = parser.parse_args(arguments)
    current = build_snapshot()
    if options.print_snapshot:
        print(json.dumps(current, indent=2, ensure_ascii=False))
        return 0
    if not BASELINE_PATH.is_file():
        print(f"Compatibility baseline is missing: {BASELINE_PATH}", file=sys.stderr)
        return 2
    differences = compare_snapshots(
        json.loads(BASELINE_PATH.read_text(encoding="utf-8")),
        current,
    )
    if differences:
        print("Compatibility guard failed:", file=sys.stderr)
        for difference in differences:
            print(f"- {difference}", file=sys.stderr)
        return 1
    print(
        "Compatibility guard passed: "
        f"{len(current['public_inference_operations'])} public inference operations, "
        f"{len(current['management_operations'])} management operations."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
