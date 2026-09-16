"""Muse Code OAuth accounts, separate from pay-as-you-go Meta API credentials."""

import hashlib
import hmac
import re
import time
from datetime import datetime, timezone

from core import meta_model_api as meta
from core.muse_oauth import (
    API_BASE,
    USER_AGENT,
    MuseOAuthError,
    _secret,
    mint_key,
    subscription_label,
    subscription_usage,
)

_MODEL_ID = re.compile(r"^muse-spark-1\.(?:1|[23](?:-contributor)?)$")
MODEL_PREFIX = "muse-code/"


def upstream_model(model: str) -> str:
    """Public OAuth model IDs cannot share a route with pay-as-you-go keys."""
    if not isinstance(model, str) or not model.startswith(MODEL_PREFIX):
        raise MuseOAuthError("Select a Muse Code model from the provider catalog.", 400)
    result = model.removeprefix(MODEL_PREFIX)
    if not _MODEL_ID.fullmatch(result):
        raise MuseOAuthError("Unsupported Muse Code model.", 400)
    return result


def normalize_credential(data: dict) -> dict:
    if (
        not isinstance(data, dict)
        or data.get("provider", "muse_code") != "muse_code"
        or data.get("credential_type", "oauth") != "oauth"
    ):
        raise MuseOAuthError("Import a Muse Code OAuth credential.", 400)
    if data.get("base_url", API_BASE) != API_BASE:
        raise MuseOAuthError("Unsupported Muse Code API endpoint.", 400)
    account = data.get("account_id")
    if not account:
        email = data.get("user_email")
        if (
            isinstance(email, str)
            and 3 <= len(email) <= 320
            and "@" in email
            and all(c.isprintable() and not c.isspace() for c in email)
        ):
            account = hashlib.sha256(email.casefold().encode()).hexdigest()
    if not isinstance(account, str) or not re.fullmatch(r"[a-f0-9]{64}", account):
        raise MuseOAuthError("Muse Code credential is missing a valid account identity.", 400)
    models = data.get("model_ids", [])
    if (
        not isinstance(models, list)
        or len(models) > 500
        or any(
            not isinstance(model, str) or not _MODEL_ID.fullmatch(model.removeprefix(MODEL_PREFIX))
            for model in models
        )
    ):
        raise MuseOAuthError("Invalid Muse Code model list.", 400)
    result = {
        "provider": "muse_code",
        "credential_type": "oauth",
        "access_token": _secret(data.get("access_token")),
        "account_id": account,
        "base_url": API_BASE,
        "model_ids": list(
            dict.fromkeys(MODEL_PREFIX + model.removeprefix(MODEL_PREFIX) for model in models)
        ),
    }
    if data.get("api_key"):
        result["api_key"] = _secret(data["api_key"])
    if "oauth_expires_at" in data:
        expiry = data["oauth_expires_at"]
        if type(expiry) is not int or not 1 <= expiry <= 253402300799:
            raise MuseOAuthError("Invalid Muse Code OAuth expiration time.", 400)
        result["oauth_expires_at"] = expiry
    plan = subscription_label(data.get("subscription_plan"))
    if plan:
        result["subscription_plan"] = plan
    usage = subscription_usage(data.get("subscription_usage"))
    if usage is not None:
        # Normalization must not make an old quota observation appear fresh.
        observed = data["subscription_usage"].get("observed_at")
        if type(observed) is int and 0 <= observed <= int(time.time()):
            usage["observed_at"] = observed
            result["subscription_usage"] = usage
    return result


async def refresh_credential(data: dict) -> dict:
    """Check subscription eligibility and re-mint; never invent token refresh."""
    normalized = normalize_credential(data)
    expiry = normalized.get("oauth_expires_at")
    if expiry is not None and expiry <= time.time():
        raise MuseOAuthError(
            "Muse Code session is no longer valid. Sign in again.", 401, "reauthorization_required"
        )
    minted = await mint_key(normalized["access_token"])
    if not hmac.compare_digest(minted["account_id"], normalized["account_id"]):
        raise MuseOAuthError(
            "Muse Code credential belongs to a different account.", 401, "reauthorization_required"
        )
    return {**data, **normalized, **minted, "model_ids": normalized["model_ids"]}


def _inference_credential(data: dict) -> dict:
    normalized = normalize_credential(data)
    return {
        "api_key": _secret(normalized.get("api_key")),
        "base_url": API_BASE,
        "model_ids": [upstream_model(model) for model in normalized["model_ids"]],
    }


async def discover_models(data: dict) -> list[str]:
    fresh = await refresh_credential(data)
    return await discover_minted_models(fresh)


async def discover_minted_models(data: dict) -> list[str]:
    """Read the catalog after eligibility was checked by the caller."""
    return [
        MODEL_PREFIX + model for model in await meta.discover_models(_inference_credential(data))
    ]


def quota_view(data: dict) -> dict:
    normalized = normalize_credential(data)
    metadata = (
        {"plan": normalized["subscription_plan"]} if normalized.get("subscription_plan") else {}
    )
    usage = normalized.get("subscription_usage")
    if usage is None:
        return {
            "supported": True,
            "quota_type": "account_rate_limits",
            "quota_status": "unavailable",
            "windows": [],
            **metadata,
        }
    tier = usage.get("tier", "")
    tier_metadata = (
        {"subscription_tier": tier}
        if tier and tier.casefold() not in {"unknown", "not_applicable", "n/a", "none"}
        else {}
    )
    windows = []
    for name, label in (("window", "Session Limit"), ("weekly", "Weekly Limit")):
        source = usage[name]
        windows.append(
            {
                "id": "session" if name == "window" else name,
                "label": label,
                "used_percentage": source["used_percent"],
                "remaining_percentage": max(0, 100 - source["used_percent"]),
                "reset_time": datetime.fromtimestamp(source["resets_at"], timezone.utc).isoformat(),
            }
        )
    return {
        "supported": True,
        "quota_type": "account_rate_limits",
        "windows": windows,
        "observed_at": usage["observed_at"],
        **metadata,
        # This is an opaque upstream tier, not a verified retail plan name.
        **tier_metadata,
    }


def protocol_for_model(data: dict, model: str) -> str:
    return meta.protocol_for_model(_inference_credential(data), upstream_model(model))


def prepare_request(data: dict, request: dict, model: str, streaming: bool):
    url, headers, body = meta.prepare_request(
        _inference_credential(data),
        request,
        upstream_model(model),
        streaming,
        native_provider="muse_code",
    )
    # Live Standard-model test: only auto is accepted. Preserve client intent by
    # rejecting unsupported choices, never by silently replacing them with auto.
    if body.get("tool_choice", "auto") != "auto":
        raise MuseOAuthError("Muse Code currently supports automatic tool choice only.", 400)
    headers["User-Agent"] = USER_AGENT
    return url, headers, body
