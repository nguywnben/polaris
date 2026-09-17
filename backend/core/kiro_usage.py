"""Read-only Kiro account usage, based on cockpit-tools and OmniRoute snapshots.

No quota is inferred from a successful login, and overage never means 100% left.
Only display facts are returned; upstream identity/token fields are discarded.
"""

import json
import math
from datetime import datetime, timezone

import httpx
from core.httpx_client import http_client
from core.kiro import KiroError, normalize_credential


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except ValueError:
        return None


def _text(value):
    return value.strip()[:100] if isinstance(value, str) and value.isprintable() else ""


def _time(value):
    try:
        if (number := _number(value)) is not None:
            return datetime.fromtimestamp(
                number / 1000 if number > 1e12 else number, timezone.utc
            ).isoformat()
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        pass
    return None


def _window(body, identifier, label, reset, kind):
    used = _number(body.get("currentUsageWithPrecision"))
    if used is None:
        used = _number(body.get("currentUsage"))
    limit = _number(body.get("usageLimitWithPrecision"))
    if limit is None:
        limit = _number(body.get("usageLimit"))
    percentage = min(100, max(0, used / limit * 100)) if used is not None and limit else None
    result = {
        "id": identifier,
        "label": label,
        "kind": kind,
        "used": used,
        "limit": limit,
        "used_percentage": percentage,
        "remaining_percentage": 100 - percentage if percentage is not None else None,
        "reset_time": _time(body.get("resetDate")) or reset,
    }
    status = _text(body.get("freeTrialStatus") or body.get("status"))
    if status:
        result["status"] = status
    expires = _time(body.get("freeTrialExpiry") or body.get("expiresAt"))
    if expires:
        result["expires_at"] = expires
    return result


def parse_kiro_usage(payload):
    if not isinstance(payload, dict):
        raise KiroError("Kiro returned an invalid usage response.", 502)
    result = {
        "supported": True,
        "quota_type": "account_rate_limits",
        "windows": [],
        "summary_mode": "resource_balances",
        "summary_remaining_percentage": None,
    }
    resource_percentages = []
    subscription = payload.get("subscriptionInfo")
    if isinstance(subscription, dict):
        plan = _text(subscription.get("subscriptionTitle") or subscription.get("subscriptionName"))
        if plan:
            result["plan"] = plan
    overage = payload.get("overageConfiguration")
    if isinstance(overage, dict) and overage.get("overageStatus") in ("ENABLED", "DISABLED"):
        result["overage_enabled"] = overage["overageStatus"] == "ENABLED"
    elif isinstance(payload.get("overageEnabled"), bool):
        result["overage_enabled"] = payload["overageEnabled"]
    reset = _time(payload.get("nextDateReset") or payload.get("resetDate"))
    breakdowns = payload.get("usageBreakdownList")
    for index, body in enumerate(breakdowns[:50] if isinstance(breakdowns, list) else []):
        if not isinstance(body, dict):
            continue
        label = _text(body.get("displayName") or body.get("resourceType"))
        if not label:
            continue
        start = len(result["windows"])
        result["windows"].append(_window(body, f"resource_{index}", label, reset, "resource"))
        trial = body.get("freeTrialInfo")
        if isinstance(trial, dict):
            result["windows"].append(_window(trial, f"trial_{index}", label, reset, "trial"))
        bonuses = body.get("bonuses")
        for n, bonus in enumerate(bonuses[:20] if isinstance(bonuses, list) else []):
            if isinstance(bonus, dict):
                result["windows"].append(
                    _window(
                        bonus,
                        f"bonus_{index}_{n}",
                        _text(bonus.get("displayName") or bonus.get("bonusCode")) or label,
                        reset,
                        "bonus",
                    )
                )
        active = [
            window
            for window in result["windows"][start:]
            if window.get("status", "ACTIVE").upper() not in {"EXPIRED", "INACTIVE", "DISABLED"}
            and (
                not window.get("expires_at")
                or datetime.fromisoformat(window["expires_at"]) > datetime.now(timezone.utc)
            )
        ]
        if active and all(
            window["used"] is not None and window["limit"] is not None for window in active
        ):
            total = sum(window["limit"] for window in active)
            remaining = sum(max(0, window["limit"] - window["used"]) for window in active)
            resource_percentages.append(remaining / total * 100 if total else 0)
        else:
            resource_percentages.append(None)
    if resource_percentages and all(value is not None for value in resource_percentages):
        result["summary_remaining_percentage"] = round(min(resource_percentages))
    if not result["windows"]:
        result["quota_status"] = "unavailable"
    return result


async def fetch_kiro_usage(data):
    credential = normalize_credential(data)
    url = f"https://q.{credential['region']}.amazonaws.com/getUsageLimits"
    token = credential.get("api_key") or credential.get("access_token")
    if not token:
        raise KiroError("Renew the Kiro OAuth session before making a request.", 401)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if credential["credential_type"] == "api_key":
        headers["tokentype"] = "API_KEY"
    params = {"origin": "AI_EDITOR", "resourceType": "AGENTIC_REQUEST"}
    if credential.get("profile_arn"):
        params["profileArn"] = credential["profile_arn"]
    try:
        async with http_client.get_client(
            timeout=30.0, destination_url=url, follow_redirects=False
        ) as client:
            async with client.stream("GET", url, headers=headers, params=params) as response:
                if response.status_code != 200:
                    raise KiroError(
                        "Unable to retrieve Kiro usage.",
                        response.status_code if response.status_code in {401, 403, 429} else 502,
                    )
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if len(body) + len(chunk) > 2 * 1024 * 1024:
                        raise KiroError("Kiro usage exceeds the size limit.", 502)
                    body.extend(chunk)
                return parse_kiro_usage(json.loads(body))
    except KiroError:
        raise
    except (ValueError, RecursionError, httpx.HTTPError, OSError):
        raise KiroError("Unable to retrieve Kiro usage.", 502) from None
