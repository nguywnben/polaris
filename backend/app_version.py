"""Application release metadata shared by runtime interfaces."""

from __future__ import annotations

import os
import re

DEFAULT_APPLICATION_VERSION = "1.0.0"
_SEMANTIC_VERSION = re.compile(r"^v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$")


def get_application_version() -> str:
    """Return a semantic build version, falling back to the current release."""
    configured = os.getenv("BUILD_VERSION", "").strip()
    match = _SEMANTIC_VERSION.fullmatch(configured)
    return match.group(1) if match else DEFAULT_APPLICATION_VERSION
