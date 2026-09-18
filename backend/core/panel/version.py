"""Runtime build metadata and release update discovery."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass

from core.i18n import LocalizedJSONResponse as JSONResponse
from fastapi import APIRouter
from log import log
from paths import PROJECT_ROOT

router = APIRouter(prefix="/api/version", tags=["version"])
LATEST_RELEASE_URL = "https://api.github.com/repos/nguywnben/polaris/releases/latest"
_SEMVER_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class BuildMetadata:
    version: str
    full_hash: str
    message: str
    date: str
    source: str


def _run_git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
        text=True,
        timeout=2,
    )
    return result.stdout.strip()


def get_build_metadata() -> BuildMetadata:
    """Resolve immutable container metadata, then source-checkout metadata."""
    revision = os.getenv("BUILD_REVISION", "").strip()
    version = os.getenv("BUILD_VERSION", "").strip()
    build_date = os.getenv("BUILD_DATE", "").strip()
    if revision or version:
        display_version = version
        if version.lower() in {"", "dev", "latest", "main"} and revision:
            display_version = revision[:7]
        return BuildMetadata(
            version=display_version or "development",
            full_hash="" if revision == "unknown" else revision,
            message="Container build",
            date=build_date,
            source="container",
        )

    try:
        revision = _run_git("rev-parse", "HEAD")
        return BuildMetadata(
            version=revision[:7],
            full_hash=revision,
            message=_run_git("log", "-1", "--pretty=%s"),
            date=_run_git("log", "-1", "--pretty=%cI"),
            source="git",
        )
    except (OSError, subprocess.SubprocessError):
        return BuildMetadata(
            version="development",
            full_hash="",
            message="Development build",
            date="",
            source="development",
        )


def _release_metadata(payload: dict) -> BuildMetadata:
    version = str(payload.get("tag_name") or "").strip().removeprefix("v")
    name = str(payload.get("name") or "").strip()
    body_line = next(
        (line.strip() for line in str(payload.get("body") or "").splitlines() if line.strip()),
        "",
    )
    return BuildMetadata(
        version=version or "unknown",
        full_hash="",
        message=name or body_line or "Release available",
        date=str(payload.get("published_at") or ""),
        source="release",
    )


def _parse_semver(value: str) -> tuple[tuple[int, int, int], tuple[str, ...] | None] | None:
    match = _SEMVER_PATTERN.fullmatch(value.strip())
    if not match:
        return None
    core = tuple(int(part) for part in match.groups()[:3])
    prerelease = tuple(match.group(4).split(".")) if match.group(4) else None
    return core, prerelease


def _compare_prerelease(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    for left_part, right_part in zip(left, right):
        if left_part == right_part:
            continue
        left_numeric = left_part.isdigit()
        right_numeric = right_part.isdigit()
        if left_numeric and right_numeric:
            return 1 if int(left_part) > int(right_part) else -1
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return 1 if left_part > right_part else -1
    if len(left) == len(right):
        return 0
    return 1 if len(left) > len(right) else -1


def is_newer_release(latest: str, current: str) -> bool | None:
    """Compare semantic release versions, returning None for development builds."""
    latest_version = _parse_semver(latest)
    current_version = _parse_semver(current)
    if latest_version is None or current_version is None:
        return None
    latest_core, latest_prerelease = latest_version
    current_core, current_prerelease = current_version
    if latest_core != current_core:
        return latest_core > current_core
    if latest_prerelease is None:
        return current_prerelease is not None
    if current_prerelease is None:
        return False
    return _compare_prerelease(latest_prerelease, current_prerelease) > 0


@router.get("/info")
async def get_version_info(check_update: bool = False):
    current = get_build_metadata()
    response_data = {"success": True, **asdict(current)}

    if not check_update:
        return JSONResponse(response_data)

    try:
        from core.httpx_client import get_async

        response = await get_async(
            LATEST_RELEASE_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10.0,
        )
        if response.status_code != 200:
            raise RuntimeError(f"GitHub returned HTTP {response.status_code}")

        latest = _release_metadata(response.json())
        response_data.update(
            {
                "check_update": True,
                "has_update": is_newer_release(latest.version, current.version),
                "latest_version": latest.version,
                "latest_url": str(response.json().get("html_url") or ""),
                "latest_message": latest.message,
                "latest_date": latest.date,
            }
        )
    except Exception:
        log.debug("Update check failed; remote error details omitted.")
        response_data.update(
            {
                "check_update": False,
                "update_error": "Unable to check for updates.",
            }
        )

    return JSONResponse(response_data)
