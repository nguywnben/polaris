"""Claude Code OAuth subscription usage retrieval and normalization."""

from __future__ import annotations

import copy
import math
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from config import get_claude_user_agent
from core.anthropic import ANTHROPIC_VERSION, AnthropicError
from core.httpx_client import get_async
from core.provider_registry import api_key_fingerprint

ANTHROPIC_OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
ANTHROPIC_USAGE_CACHE_SECONDS = 3 * 60
ANTHROPIC_USAGE_COOLDOWN_SECONDS = 3 * 60
ANTHROPIC_USAGE_CACHE_LIMIT = 256

_usage_cache: dict[str, tuple[float, Dict[str, Any]]] = {}
_rate_limit_cooldowns: dict[str, float] = {}


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


def _reset_time(value: Any) -> Optional[str]:
    number = _finite_number(value)
    if number is not None:
        if number > 1_000_000_000_000:
            number /= 1000
        try:
            return datetime.fromtimestamp(number, timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _safe_label(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text or not text.isprintable():
        return fallback
    return text[:80]


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized[:48] or "scoped"


def _window(window_id: str, label: str, body: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(body, dict):
        return None
    used = _percentage(body.get("percent", body.get("utilization")))
    if used is None:
        return None
    return {
        "id": window_id,
        "label": label,
        "used_percentage": used,
        "remaining_percentage": 100 - used,
        "reset_time": _reset_time(body.get("resets_at", body.get("reset_at"))),
    }


def _current_limit_descriptor(body: Dict[str, Any]) -> Optional[tuple[str, str]]:
    kind = str(body.get("kind") or "").strip().lower()
    if kind == "session":
        return "session", "5-Hour Limit"
    if kind == "weekly_all":
        return "weekly", "7-Day All Models"
    if kind != "weekly_scoped":
        return None

    scope = body.get("scope")
    model = scope.get("model") if isinstance(scope, dict) else None
    display_name = _safe_label(
        model.get("display_name") if isinstance(model, dict) else None,
        "Scoped Models",
    )
    return f"weekly_{_slug(display_name)}", f"7-Day {display_name}"


def parse_anthropic_oauth_usage(payload: Any) -> Dict[str, Any]:
    """Normalize both known Claude Code subscription usage response shapes."""
    if not isinstance(payload, dict):
        raise AnthropicError("Claude Code returned an invalid usage response.", 502)

    windows: list[Dict[str, Any]] = []
    seen: set[str] = set()
    limits = payload.get("limits")
    if isinstance(limits, list):
        for body in limits:
            if not isinstance(body, dict):
                continue
            descriptor = _current_limit_descriptor(body)
            if not descriptor or descriptor[0] in seen:
                continue
            normalized = _window(*descriptor, body)
            if normalized:
                windows.append(normalized)
                seen.add(descriptor[0])

    legacy_descriptors = (
        ("five_hour", "session", "5-Hour Limit"),
        ("seven_day", "weekly", "7-Day All Models"),
    )
    for key, window_id, label in legacy_descriptors:
        if window_id in seen:
            continue
        normalized = _window(window_id, label, payload.get(key))
        if normalized:
            windows.append(normalized)
            seen.add(window_id)

    for key, body in payload.items():
        if not isinstance(key, str) or not key.startswith("seven_day_"):
            continue
        suffix = _safe_label(key.removeprefix("seven_day_").replace("_", " "), "scoped")
        window_id = f"weekly_{_slug(suffix)}"
        if window_id in seen:
            continue
        normalized = _window(window_id, f"7-Day {suffix.title()}", body)
        if normalized:
            windows.append(normalized)
            seen.add(window_id)

    if not windows:
        raise AnthropicError("Claude Code usage did not contain valid usage windows.", 502)

    plan = _safe_label(
        payload.get("tier") or payload.get("plan") or payload.get("subscription_type"),
        "Claude Code",
    )
    return {
        "quota_type": "account_rate_limits",
        "plan": plan,
        "windows": windows,
    }


def _prune_cache(now: float) -> None:
    expired = [key for key, (expires_at, _) in _usage_cache.items() if expires_at <= now]
    for key in expired:
        _usage_cache.pop(key, None)
    expired_cooldowns = [
        key for key, cooldown_until in _rate_limit_cooldowns.items() if cooldown_until <= now
    ]
    for key in expired_cooldowns:
        _rate_limit_cooldowns.pop(key, None)
    while len(_usage_cache) > ANTHROPIC_USAGE_CACHE_LIMIT:
        _usage_cache.pop(next(iter(_usage_cache)))
    while len(_rate_limit_cooldowns) > ANTHROPIC_USAGE_CACHE_LIMIT:
        _rate_limit_cooldowns.pop(next(iter(_rate_limit_cooldowns)))


async def fetch_anthropic_oauth_usage(access_token: str) -> Dict[str, Any]:
    """Fetch account-scoped Claude Code usage with a short rate-limit cache."""
    token = str(access_token or "").strip()
    if not token:
        raise AnthropicError("Claude Code credential does not contain an access token.", 401)

    cache_key = api_key_fingerprint(token)
    now = time.monotonic()
    _prune_cache(now)
    cached = _usage_cache.get(cache_key)
    if cached and cached[0] > now:
        return copy.deepcopy(cached[1])
    if _rate_limit_cooldowns.get(cache_key, 0) > now:
        raise AnthropicError(
            "Claude Code usage is temporarily rate limited. Try again in a few minutes.",
            429,
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "anthropic-beta": "oauth-2025-04-20",
        "anthropic-version": ANTHROPIC_VERSION,
    }
    user_agent = str(await get_claude_user_agent() or "").strip()
    if user_agent:
        headers["User-Agent"] = user_agent

    try:
        response = await get_async(
            ANTHROPIC_OAUTH_USAGE_URL,
            headers=headers,
            timeout=10.0,
        )
    except (httpx.HTTPError, OSError) as exc:
        raise AnthropicError(
            "Unable to reach Claude Code usage. Check outbound network and proxy settings.",
            502,
        ) from exc

    if response.status_code in {401, 403}:
        raise AnthropicError(
            "Claude Code rejected this OAuth credential while retrieving quota.",
            response.status_code,
        )
    if response.status_code == 429:
        _rate_limit_cooldowns[cache_key] = now + ANTHROPIC_USAGE_COOLDOWN_SECONDS
        raise AnthropicError(
            "Claude Code usage is temporarily rate limited. Try again in a few minutes.",
            429,
        )
    if response.status_code != 200:
        raise AnthropicError(
            f"Claude Code usage failed with HTTP {response.status_code}.",
            502 if response.status_code >= 500 else 400,
        )

    try:
        usage = parse_anthropic_oauth_usage(response.json())
    except ValueError as exc:
        raise AnthropicError("Claude Code returned an invalid usage response.", 502) from exc
    _usage_cache[cache_key] = (now + ANTHROPIC_USAGE_CACHE_SECONDS, copy.deepcopy(usage))
    _rate_limit_cooldowns.pop(cache_key, None)
    _prune_cache(now)
    return usage


def _reset_anthropic_usage_cache_for_testing() -> None:
    _usage_cache.clear()
    _rate_limit_cooldowns.clear()
