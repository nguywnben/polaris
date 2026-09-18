"""Grok Build OAuth account quota retrieval and normalization."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from core.httpx_client import get_async
from core.xai import XaiError

XAI_BILLING_API_URL = "https://cli-chat-proxy.grok.com/v1"


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _display_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _percentage(value: float) -> int:
    return max(0, min(100, int(math.floor(value + 0.5))))


def _valid_timestamp(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    return normalized


def parse_xai_monthly_usage(payload: Any) -> Dict[str, Any]:
    """Normalize the required monthly billing response from Grok Build."""
    config = payload.get("config") if isinstance(payload, dict) else None
    if not isinstance(config, dict):
        raise XaiError("Grok Build returned an invalid billing response.", 502)

    limit_container = config.get("monthlyLimit")
    used_container = config.get("used")
    limit = _finite_number(
        limit_container.get("val") if isinstance(limit_container, dict) else None
    )
    used = _finite_number(used_container.get("val") if isinstance(used_container, dict) else None)
    reset_time = _valid_timestamp(config.get("billingPeriodEnd"))
    if limit is None or used is None or limit < 0 or used < 0 or reset_time is None:
        raise XaiError("Grok Build returned an invalid billing response.", 502)

    remaining = max(0.0, limit - used)
    used_percentage = _percentage((used / limit) * 100) if limit > 0 else 100
    return {
        "limit": _display_number(limit),
        "used": _display_number(used),
        "remaining": _display_number(remaining),
        "used_percentage": used_percentage,
        "remaining_percentage": 100 - used_percentage,
        "reset_time": reset_time,
    }


def parse_xai_weekly_usage(payload: Any) -> Optional[Dict[str, Any]]:
    """Normalize the optional weekly usage response from Grok Build."""
    config = payload.get("config") if isinstance(payload, dict) else None
    if not isinstance(config, dict):
        return None
    current_period = config.get("currentPeriod")
    if not isinstance(current_period, dict) or current_period.get("type") != (
        "USAGE_PERIOD_TYPE_WEEKLY"
    ):
        return None
    reset_time = _valid_timestamp(config.get("billingPeriodEnd"))
    if reset_time is None:
        return None
    raw_percentage = config.get("creditUsagePercent")
    used_percentage = _finite_number(raw_percentage)
    if used_percentage is None or used_percentage < 0:
        return None
    normalized_percentage = _percentage(used_percentage)
    return {
        "used_percentage": normalized_percentage,
        "remaining_percentage": 100 - normalized_percentage,
        "reset_time": reset_time,
    }


def _billing_headers(access_token: str) -> Dict[str, str]:
    token = str(access_token or "").strip()
    if not token:
        raise XaiError("Grok Build OAuth credential does not contain an access token.")
    return {
        "Authorization": f"Bearer {token}",
        "x-xai-token-auth": "xai-grok-cli",
        "Accept": "application/json",
    }


def parse_xai_billing_facts(payload: Any) -> Dict[str, Any]:
    """Optional facts already returned by billing; never infer a subscription."""
    config = payload.get("config") if isinstance(payload, dict) else None
    if not isinstance(config, dict):
        return {}
    result = {}
    plan = config.get("subscriptionTier") or config.get("subscription_tier")
    if isinstance(plan, str) and plan.strip() and plan.isprintable():
        result["plan"] = plan.strip()[:100]
    for source, target in (
        ("onDemandUsed", "on_demand_used"),
        ("onDemandCap", "on_demand_cap"),
        ("prepaidBalance", "prepaid_balance"),
    ):
        value = _finite_number(config.get(source))
        if value is not None and value >= 0:
            result[target] = value
    products = config.get("productUsage")
    windows = []
    for index, product in enumerate(products[:50] if isinstance(products, list) else []):
        if not isinstance(product, dict):
            continue
        label = product.get("product") or product.get("name") or product.get("productName")
        if not isinstance(label, str) or not label.isprintable():
            continue
        used = _finite_number(product.get("usagePercent", product.get("usedPercent")))
        percentage = _percentage(used) if used is not None and used >= 0 else None
        windows.append(
            {
                "id": f"product_{index}",
                "label": label[:100],
                "used_percentage": percentage,
                "remaining_percentage": 100 - percentage if percentage is not None else None,
            }
        )
    if windows:
        result["windows"] = windows
    return result


async def _fetch_optional_weekly_usage(headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    try:
        response = await get_async(
            f"{XAI_BILLING_API_URL}/billing?format=credits",
            headers=headers,
            timeout=30.0,
        )
        if response.status_code != 200:
            return None
        payload = response.json()
        weekly = parse_xai_weekly_usage(payload)
        facts = parse_xai_billing_facts(payload)
        return {**(weekly or {}), **facts} if weekly or facts else None
    except (httpx.HTTPError, OSError, ValueError, XaiError):
        return None


async def fetch_xai_billing_usage(access_token: str) -> Dict[str, Any]:
    """Fetch required monthly and optional weekly quota for Grok Build OAuth."""
    headers = _billing_headers(access_token)
    try:
        response = await get_async(
            f"{XAI_BILLING_API_URL}/billing",
            headers=headers,
            timeout=30.0,
        )
    except (httpx.HTTPError, OSError) as exc:
        raise XaiError(
            "Unable to reach Grok Build billing. Check outbound network and proxy settings.",
            502,
        ) from exc

    if response.status_code in {401, 403}:
        raise XaiError(
            "Grok Build rejected this OAuth credential while retrieving quota.",
            response.status_code,
        )
    if response.status_code != 200:
        raise XaiError(
            f"Grok Build billing failed with HTTP {response.status_code}.",
            502 if response.status_code >= 500 else 400,
        )
    try:
        payload = response.json()
        monthly = parse_xai_monthly_usage(payload)
    except ValueError as exc:
        raise XaiError("Grok Build returned an invalid billing response.", 502) from exc

    weekly = await _fetch_optional_weekly_usage(headers)
    facts = parse_xai_billing_facts(payload)
    if weekly:
        facts.update(
            {
                key: weekly[key]
                for key in ("plan", "on_demand_used", "on_demand_cap", "prepaid_balance", "windows")
                if key in weekly
            }
        )
    return {
        "quota_type": "account_billing",
        "monthly": monthly,
        "weekly": weekly if weekly and "used_percentage" in weekly else None,
        **facts,
    }
