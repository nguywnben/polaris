"""Small, validated HTTP metadata allowed across untrusted provider boundaries."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import timezone
from email.utils import format_datetime, parsedate_to_datetime


def retry_after_headers(headers: Mapping[str, str]) -> dict[str, str]:
    value = headers.get("retry-after") or headers.get("Retry-After")
    if not isinstance(value, str) or len(value) > 128:
        return {}
    if re.fullmatch(r"[0-9]{1,10}", value):
        return {"Retry-After": value}
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return {}
        normalized = format_datetime(parsed.astimezone(timezone.utc), usegmt=True)
    except (TypeError, ValueError, OverflowError):
        return {}
    return {"Retry-After": normalized}
