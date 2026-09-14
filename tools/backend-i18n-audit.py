"""Audit literal user-facing messages returned by management API modules."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PANEL = BACKEND / "core" / "panel"
sys.path.insert(0, str(BACKEND))

from core.i18n import can_localize_text  # noqa: E402

USER_MESSAGE_KEYS = {"detail", "error", "message", "title", "restart_notice"}
TECHNICAL_VALUES = {
    "success",
    "error",
    "warning",
    "pending",
    "ready",
    "oauth",
    "api_key",
}


def _literal_text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip()
    return None


def _is_user_copy(value: str) -> bool:
    return (
        bool(value)
        and any(character.isalpha() for character in value)
        and value.lower() not in TECHNICAL_VALUES
        and not value.startswith(("http://", "https://"))
    )


class MessageVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.issues: list[tuple[int, str]] = []

    def _check(self, node: ast.AST) -> None:
        value = _literal_text(node)
        if value and _is_user_copy(value) and not can_localize_text(value):
            self.issues.append((getattr(node, "lineno", 0), value))

    def visit_Dict(self, node: ast.Dict) -> None:
        for key_node, value_node in zip(node.keys, node.values):
            key = _literal_text(key_node) if key_node else None
            if key in USER_MESSAGE_KEYS:
                self._check(value_node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        function_name = ""
        if isinstance(node.func, ast.Name):
            function_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            function_name = node.func.attr
        if function_name == "HTTPException":
            for keyword in node.keywords:
                if keyword.arg == "detail":
                    self._check(keyword.value)
        self.generic_visit(node)


def main() -> int:
    issues: list[tuple[Path, int, str]] = []
    for path in sorted(PANEL.rglob("*.py")):
        visitor = MessageVisitor(path)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        issues.extend((path, line, value) for line, value in visitor.issues)

    if issues:
        for path, line, value in issues:
            print(f"{path.relative_to(ROOT)}:{line}: {value}")
        print(f"Found {len(issues)} backend messages outside the locale catalog.", file=sys.stderr)
        return 1

    print("All literal management API messages are connected to the locale catalog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
