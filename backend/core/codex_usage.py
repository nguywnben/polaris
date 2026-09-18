"""Codex OAuth account rate-limit retrieval and normalization."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from itertools import islice
from typing import Any, Dict, Optional

import httpx
from config import get_codex_usage_url, get_codex_user_agent
from core.codex import CodexError, build_codex_headers
from core.httpx_client import get_async


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _percentage(value: Any) -> Optional[int]:
    number = _finite_number(value)
    if number is None:
        return None
    return max(0, min(100, int(math.floor(number + 0.5))))


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return False


def _reset_time(window: Dict[str, Any]) -> Optional[str]:
    value = window.get("reset_at")
    if value is None:
        value = window.get("resets_at")
    if value is None:
        value = window.get("resetAt")

    number = _finite_number(value)
    if number is not None:
        if number > 1_000_000_000_000:
            number /= 1000
        try:
            return datetime.fromtimestamp(number, timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None

    if isinstance(value, str) and value.strip():
        normalized = value.strip()
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    remaining_value = window.get("reset_after_seconds")
    if remaining_value is None:
        remaining_value = window.get("resets_in_seconds")
    remaining = _finite_number(remaining_value)
    if remaining is None or remaining < 0:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=remaining)).isoformat()


def _rate_limit_body(snapshot: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return None
    nested = snapshot.get("rate_limit")
    return nested if isinstance(nested, dict) else snapshot


def _review_rate_limit(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    direct = payload.get("code_review_rate_limit") or payload.get("review_rate_limit")
    if isinstance(direct, dict):
        return direct

    by_limit_id = payload.get("rate_limits_by_limit_id")
    if isinstance(by_limit_id, dict):
        for key in ("code_review", "codex_review", "review"):
            candidate = by_limit_id.get(key)
            if isinstance(candidate, dict):
                return candidate

    additional = payload.get("additional_rate_limits")
    if isinstance(additional, list):
        for candidate in additional:
            if not isinstance(candidate, dict):
                continue
            identifier = str(
                candidate.get("limit_name")
                or candidate.get("metered_feature")
                or candidate.get("id")
                or ""
            ).lower()
            if "review" in identifier:
                return candidate
    return None


def _duration_label(window: Dict[str, Any], fallback: str) -> str:
    seconds = _finite_number(
        window.get("limit_window_seconds") or window.get("window_seconds") or window.get("seconds")
    )
    if seconds is None or seconds <= 0:
        return fallback
    rounded = int(seconds)
    units = ((86_400, "Day"), (3_600, "Hour"), (60, "Minute"))
    for unit_seconds, unit_name in units:
        if rounded % unit_seconds == 0:
            count = rounded // unit_seconds
            return f"{count}-{unit_name} Limit"
    return fallback


def _normalize_window(
    window: Any,
    window_id: str,
    fallback_label: str,
) -> Optional[Dict[str, Any]]:
    if not isinstance(window, dict) or not window:
        return None
    used = _percentage(window.get("used_percent", window.get("percent_used")))
    if used is None:
        return None
    return {
        "id": window_id,
        "label": _duration_label(window, fallback_label),
        "used_percentage": used,
        "remaining_percentage": 100 - used,
        "reset_time": _reset_time(window),
    }


def _append_windows(
    windows: list[Dict[str, Any]],
    snapshot: Any,
    *,
    prefix: str = "",
) -> bool:
    body = _rate_limit_body(snapshot)
    if not body:
        return False
    primary = body.get("primary_window") or body.get("primary")
    secondary = body.get("secondary_window") or body.get("secondary")
    if isinstance(snapshot, dict):
        primary = primary or snapshot.get("primary_window") or snapshot.get("primary")
        secondary = secondary or snapshot.get("secondary_window") or snapshot.get("secondary")

    descriptors = (
        (
            primary,
            f"{prefix}_session" if prefix else "session",
            "Session Limit",
        ),
        (
            secondary,
            f"{prefix}_weekly" if prefix else "weekly",
            "Weekly Limit",
        ),
    )
    added = False
    for raw_window, window_id, label in descriptors:
        normalized = _normalize_window(raw_window, window_id, label)
        if normalized:
            if prefix:
                normalized["label"] = f"{prefix} · {normalized['label']}"
            windows.append(normalized)
            added = True
    return added


def parse_codex_usage(payload: Any) -> Dict[str, Any]:
    """Normalize the account-scoped usage response returned by Codex."""
    if not isinstance(payload, dict):
        raise CodexError("Codex returned an invalid usage response.", 502)

    by_limit_id = payload.get("rate_limits_by_limit_id")
    normal_rate_limit = payload.get("rate_limit") or payload.get("rate_limits")
    if not normal_rate_limit and isinstance(by_limit_id, dict):
        normal_rate_limit = by_limit_id.get("codex")
    review_rate_limit = _review_rate_limit(payload)
    windows: list[Dict[str, Any]] = []
    _append_windows(windows, normal_rate_limit)
    _append_windows(windows, review_rate_limit, prefix="review")
    additional = payload.get("additional_rate_limits")
    candidates = list(islice(by_limit_id.items(), 32)) if isinstance(by_limit_id, dict) else []
    if isinstance(additional, list):
        candidates.extend(
            (item.get("limit_name") or item.get("metered_feature") or item.get("id"), item)
            for item in additional[:32]
            if isinstance(item, dict)
        )
    seen = set()
    for name, snapshot in candidates[:32]:
        name = str(name or "").strip()[:80]
        if not name or not name.isprintable() or name in seen:
            continue
        seen.add(name)
        if snapshot == normal_rate_limit or snapshot == review_rate_limit:
            continue
        _append_windows(windows, snapshot, prefix=name)
    normal_body = _rate_limit_body(normal_rate_limit) or {}
    review_body = _rate_limit_body(review_rate_limit) or {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    reset_credits = payload.get("rate_limit_reset_credits")
    available_credits = _finite_number(
        reset_credits.get("available_count") if isinstance(reset_credits, dict) else None
    )
    result = {
        "quota_type": "account_rate_limits",
        "windows": windows,
    }
    plan = payload.get("plan_type") or summary.get("plan")
    if isinstance(plan, str) and plan.strip() and plan.isprintable():
        result["plan"] = plan.strip()[:80]
    for key, body in (("limit_reached", normal_body), ("review_limit_reached", review_body)):
        value = body.get("limit_reached")
        if isinstance(value, bool) or value in ("true", "false"):
            result[key] = _boolean(value)
    if available_credits is not None and available_credits >= 0:
        result["reset_credits"] = {"available_count": int(available_credits)}
    credits = payload.get("credits")
    if isinstance(credits, dict):
        safe = {
            key: credits[key]
            for key in ("has_credits", "unlimited")
            if isinstance(credits.get(key), bool)
        }
        balance = _finite_number(credits.get("balance"))
        if balance is not None and balance >= 0:
            safe["balance"] = balance
        if safe:
            result["credits"] = safe
    if not windows:
        if len(result) == 2:
            raise CodexError("Codex usage did not contain valid rate-limit windows.", 502)
        result["quota_status"] = "unavailable"
    return result


async def fetch_codex_usage(access_token: str, account_id: str = "") -> Dict[str, Any]:
    """Fetch account rate limits for one Codex OAuth credential."""
    try:
        headers = build_codex_headers(
            access_token,
            account_id,
            user_agent=await get_codex_user_agent(),
        )
    except ValueError as exc:
        raise CodexError(str(exc), 401) from exc
    headers["Accept"] = "application/json"
    try:
        response = await get_async(
            await get_codex_usage_url(),
            headers=headers,
            timeout=30.0,
        )
    except (httpx.HTTPError, OSError) as exc:
        raise CodexError(
            "Unable to reach Codex usage. Check outbound network and proxy settings.",
            502,
        ) from exc

    if response.status_code in {401, 403}:
        raise CodexError(
            "Codex rejected this OAuth credential while retrieving quota.",
            response.status_code,
        )
    if response.status_code != 200:
        raise CodexError(
            f"Codex usage failed with HTTP {response.status_code}.",
            502 if response.status_code >= 500 else 400,
        )
    try:
        return parse_codex_usage(response.json())
    except ValueError as exc:
        raise CodexError("Codex returned an invalid usage response.", 502) from exc
