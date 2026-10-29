"""Reject ambiguous/unprepared tag metadata before publishing any release asset."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def release_notes(changelog: str, tag: str, version: str) -> str:
    if tag != f"v{version}":
        raise ValueError("Release tag does not match DEFAULT_APPLICATION_VERSION.")
    lines = changelog.splitlines()
    heading = f"## [{version}]"
    matches = [index for index, line in enumerate(lines) if line.startswith(heading)]
    if len(matches) != 1:
        raise ValueError("The release must have exactly one changelog section.")
    start = matches[0]
    dated = re.fullmatch(re.escape(heading) + r" - (\d{4}-\d{2}-\d{2})", lines[start])
    if dated is None:
        raise ValueError("Release notes are not dated; the candidate is not ready to publish.")
    date.fromisoformat(dated.group(1))
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    notes = "\n".join(lines[start + 1 : end]).strip()
    if not notes:
        raise ValueError("Release notes must not be empty.")
    return notes


def main() -> int:
    from backend.app_version import DEFAULT_APPLICATION_VERSION

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--notes-file", type=Path)
    options = parser.parse_args()
    try:
        notes = release_notes(
            (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"),
            options.tag,
            DEFAULT_APPLICATION_VERSION,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if options.notes_file is not None:
        options.notes_file.write_text(notes + "\n", encoding="utf-8")
    print(f"Release metadata verified for {options.tag}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
