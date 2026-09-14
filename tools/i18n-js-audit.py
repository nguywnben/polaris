"""Report direct user-facing JavaScript literals that bypass the locale catalog."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVASCRIPT = ROOT / "frontend" / "js"
CALL_PATTERN = re.compile(
    r"\b(?:showStatus|showMessageModal|showConfirmationModal|showModelTestModal|Error)"
    r"\(\s*(['\"])(?P<value>[A-Za-z][^'\"\n]{3,})\1"
)
DEVELOPER_ERRORS = {
    "Confirmation modals require a contextual title and confirmation label.",
}


def main() -> int:
    issues: list[tuple[Path, int, str]] = []
    for path in sorted(JAVASCRIPT.rglob("*.js")):
        source = path.read_text(encoding="utf-8")
        for match in CALL_PATTERN.finditer(source):
            value = match.group("value").strip()
            if value in DEVELOPER_ERRORS or re.fullmatch(
                r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)*", value
            ):
                continue
            line = source.count("\n", 0, match.start()) + 1
            issues.append((path, line, value))

    if issues:
        for path, line, value in issues:
            print(f"{path.relative_to(ROOT)}:{line}: {value}")
        print(f"Found {len(issues)} direct JavaScript UI literals.", file=sys.stderr)
        return 1

    print("All audited JavaScript UI messages use the locale catalog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
