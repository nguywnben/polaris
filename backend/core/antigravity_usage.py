"""Allowlisted Antigravity quota and account display metadata (no onboarding)."""

import asyncio
import json
import math
from datetime import datetime, timezone
from itertools import islice

import httpx
from core.httpx_client import http_client


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except ValueError:
        return None


def parse_model_quotas(payload):
    models = payload.get("models") if isinstance(payload, dict) else None
    result = {}
    for name, model in islice(models.items(), 500) if isinstance(models, dict) else []:
        if (
            not isinstance(name, str)
            or not name.isprintable()
            or len(name) > 256
            or not isinstance(model, dict)
        ):
            continue
        quota = model.get("quotaInfo")
        if not isinstance(quota, dict):
            continue
        remaining = _number(quota.get("remainingFraction"))
        reset = None
        raw = quota.get("resetTime")
        if isinstance(raw, str):
            try:
                date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                reset = (
                    date.replace(tzinfo=date.tzinfo or timezone.utc)
                    .astimezone(timezone.utc)
                    .isoformat()
                )
            except ValueError:
                pass
        result[name] = {
            "remaining": min(1, remaining) if remaining is not None else None,
            "resetTime": reset,
            "resetTimeRaw": reset,
        }
    return result


def parse_account_metadata(payload):
    if not isinstance(payload, dict):
        return {}
    tier = payload.get("paidTier") or payload.get("currentTier")
    if not isinstance(tier, dict):
        return {}
    result = {}
    name = tier.get("id")
    if isinstance(name, str) and name.isprintable() and name.strip():
        result["plan"] = name.strip()[:100]
    credits = tier.get("availableCredits")
    balances = []
    for credit in credits[:20] if isinstance(credits, list) else []:
        if not isinstance(credit, dict):
            continue
        kind = credit.get("creditType")
        amount = _number(credit.get("creditAmount"))
        if not isinstance(kind, str) or not kind.isprintable() or amount is None:
            continue
        item = {"type": kind[:100], "balance": amount}
        minimum = _number(credit.get("minimumCreditAmountForUsage"))
        if minimum is not None:
            item["minimum"] = minimum
        balances.append(item)
    if balances:
        result["credit_balances"] = balances
    return result


def parse_group_quotas(payload):
    root = payload.get("quotaSummary", payload) if isinstance(payload, dict) else {}
    groups = root.get("groups") if isinstance(root, dict) else None
    windows = []
    for group_index, group in enumerate(groups[:30] if isinstance(groups, list) else []):
        if not isinstance(group, dict) or not isinstance(group.get("displayName"), str):
            continue
        buckets = group.get("buckets")
        for bucket_index, bucket in enumerate(buckets[:10] if isinstance(buckets, list) else []):
            if not isinstance(bucket, dict) or bucket.get("disabled") is True:
                continue
            label = bucket.get("displayName") or bucket.get("bucketId")
            if not isinstance(label, str) or not label.isprintable():
                continue
            quota = parse_model_quotas({"models": {"bucket": {"quotaInfo": bucket}}})["bucket"]
            remaining = quota["remaining"]
            windows.append(
                {
                    "id": f"group_{group_index}_{bucket_index}",
                    "label": f"{group['displayName'][:100]} · {label[:100]}",
                    "remaining_percentage": remaining * 100 if remaining is not None else None,
                    "used_percentage": (1 - remaining) * 100 if remaining is not None else None,
                    "reset_time": quota["resetTime"],
                }
            )
    return windows


async def _optional_rpc(base_url, headers, method, body):
    url = f"{base_url.rstrip('/')}/v1internal:{method}"
    try:
        async with http_client.get_client(
            timeout=15.0, destination_url=url, follow_redirects=False
        ) as client:
            async with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code != 200:
                    return None
                data = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if len(data) + len(chunk) > 2 * 1024 * 1024:
                        return None
                    data.extend(chunk)
                return json.loads(data)
    except (ValueError, OSError, RecursionError, httpx.HTTPError):
        pass
    return None


async def fetch_account_metadata(base_url, headers, project_id=""):
    # Unlike fetch_project_id_and_tier, this never falls back to onboardUser.
    requests = [
        _optional_rpc(base_url, headers, "loadCodeAssist", {"metadata": {"ideType": "ANTIGRAVITY"}})
    ]
    if project_id:
        requests.append(
            _optional_rpc(base_url, headers, "retrieveUserQuotaSummary", {"project": project_id})
        )
    results = await asyncio.gather(*requests)
    metadata = (
        parse_account_metadata(results[0])
        if isinstance(results[0], dict)
        else {"account_metadata_status": "unavailable"}
    )
    if len(results) > 1:
        metadata["windows"] = parse_group_quotas(results[1])
    return metadata
