"""Persistable synthetic accounts using provider-owned credential shapes."""

import hashlib

from tools.demo_catalog import catalog
from tools.demo_upstream import QUOTA_SOURCES, iso, quota_payloads


def quota_snapshot(variant, number, now):
    """Compatibility test helper: production parsers own every display field."""
    from core.anthropic_usage import parse_anthropic_oauth_usage
    from core.antigravity_usage import parse_account_metadata, parse_model_quotas
    from core.codex_usage import parse_codex_usage
    from core.kiro_usage import parse_kiro_usage
    from core.muse_code import quota_view
    from core.xai_billing import parse_xai_monthly_usage, parse_xai_weekly_usage

    models, _ = catalog(variant)
    payload = quota_payloads(variant, number, now, models)
    if variant == "google_antigravity":
        return {
            "models": parse_model_quotas(payload["quota"]),
            "windows": [],
            **parse_account_metadata(payload["account"]),
        }
    if variant == "grok":
        return {
            "quota_type": "account_billing",
            "windows": [],
            "monthly": parse_xai_monthly_usage(payload["quota"]),
            "weekly": parse_xai_weekly_usage(payload["weekly"]),
        }
    if variant == "muse_code":
        record = next(
            r for r in build_records(now) if r["variant"] == variant and r["number"] == number
        )
        return quota_view(record["data"])
    parser = {
        "codex": parse_codex_usage,
        "claude_code": parse_anthropic_oauth_usage,
        "kiro": parse_kiro_usage,
    }.get(variant)
    return parser(payload["quota"]) if parser else None


def build_records(now):
    from core.extended_provider_runtime import normalize_extended_credential
    from core.muse_oauth import API_BASE, subscription_usage
    from core.provider_registry import EXTENDED_PROVIDERS, list_credential_variant_capabilities

    records = []
    for index, variant in enumerate(list_credential_variant_capabilities()):
        variant_id, provider = variant["variant_id"], variant["provider_id"]
        models, source = catalog(variant_id)
        # Exercise all seven quota scenarios without exceeding the production
        # router's total candidate bound. API-key variants need fewer duplicates.
        count = 7 if variant_id in QUOTA_SOURCES else 1 + index % 5
        if variant_id == "openai_platform":
            count = 6  # Preserve a six-card layout alongside the seven-card OAuth sections.
        for number in range(1, count + 1):
            name = f"demo-{variant_id}-{number:02}"
            secret = f"DEMO-NOT-A-REAL-SECRET-{name}"
            identity = hashlib.sha256(name.encode()).hexdigest()
            email = f"{variant_id}.{number:02}@example.invalid"
            kind = "api_key" if variant_id == "kiro" and number >= 6 else variant["credential_type"]
            data = {"provider": provider, "credential_type": kind}
            state = {
                "user_email": None,
                "disabled": number == 4,
                "last_success": None,
                "error_codes": [],
                "error_messages": {},
                "model_cooldowns": {},
                "tier": None,
                "enable_credit": False,
            }
            if number in {3, 5}:
                code = 429 if number == 3 else 401
                state.update(
                    error_codes=[code],
                    error_messages={str(code): f"Provider returned HTTP {code}."},
                    last_success=now - 7200,
                )
                if number == 3:
                    state["model_cooldowns"] = {models[0]: now + 600}
            upstream = quota_payloads(variant_id, number, now, models)
            if variant_id == "google_antigravity" and number == 6:
                upstream["groups"] = {
                    "quotaSummary": {
                        "groups": [
                            {
                                "displayName": "Gemini Models",
                                "buckets": [
                                    {
                                        "bucketId": "weekly",
                                        "displayName": "Weekly",
                                        "remainingFraction": 0.25,
                                        "resetTime": iso(now + 3 * 86400),
                                    }
                                ],
                            }
                        ]
                    }
                }
            if kind == "oauth":
                data.update(
                    access_token=secret,
                    refresh_token=f"DEMO-NOT-A-REAL-REFRESH-{name}",
                    expiry=iso(now + 3600),
                )
                if variant_id in {"codex", "claude_code", "grok"}:
                    data["account_id"] = identity[:32]
                    state["user_email"] = email if number != 7 else None
                if variant_id == "google_antigravity":
                    data.update(
                        client_id="demo-client-not-real",
                        client_secret="DEMO-NOT-A-REAL-CLIENT-SECRET",
                        project_id=f"demo-project-{number:02}",
                    )
                    state["user_email"] = email if number != 7 else None
                    state["enable_credit"] = number == 2
                    state["tier"] = "g1-pro-tier" if number != 7 else None
                elif variant_id == "kiro":
                    data.update(
                        auth_method="idc" if number % 2 == 0 else "social",
                        region="us-east-1",
                        account_fingerprint=identity,
                    )
                    if data["auth_method"] == "idc":
                        data.update(
                            client_id="demo-client-not-real",
                            client_secret="DEMO-NOT-A-REAL-CLIENT-SECRET",
                            token_region="us-east-1",
                        )
                elif variant_id == "muse_code":
                    data.pop("refresh_token")
                    data.pop("expiry")
                    data.update(
                        api_key=secret,
                        base_url=API_BASE,
                        account_id=hashlib.sha256(email.casefold().encode()).hexdigest(),
                        oauth_expires_at=now + 86400 * 30,
                        subscription_plan=upstream["subscription"]["subs_tier_name"],
                    )
                    usage = subscription_usage(upstream["subscription"].get("subs_usage"))
                    if usage is not None:
                        data["subscription_usage"] = {**usage, "observed_at": now}
                    upstream["subscription"].update(
                        user_email=email,
                        api_key=secret,
                        base_url=API_BASE,
                        is_subs_active=True,
                        require_payment=False,
                    )
            elif kind == "api_key":
                data.update(api_key=secret, key_fingerprint=identity[:16])
                if variant_id == "cloudflare":
                    data["account_id"] = identity[:32]
                elif variant_id == "kilo" and number % 2 == 0:
                    data["organization_id"] = f"demo-organization-{number}"
                elif variant_id == "opencode":
                    data["plan"] = "go"
            else:
                data.update(
                    base_url=f"http://ollama-{number}.example.invalid:11434",
                    connection_fingerprint=identity,
                )
            data["model_ids"] = list(models)
            if provider in EXTENDED_PROVIDERS:
                data = normalize_extended_credential(data)
            # Polaris-owned metadata belongs outside vendor normalization.
            data.update(
                model_ids=list(models),
                synthetic=True,
                credential_label=f"DEMO · {variant['display_name']} · {number:02}",
            )
            records.append(
                {
                    "filename": name + ".json",
                    "number": number,
                    "variant": variant_id,
                    "data": data,
                    "state": state,
                    "upstream": upstream,
                    "sources": [
                        source,
                        *([QUOTA_SOURCES[variant_id]] if variant_id in QUOTA_SOURCES else []),
                        *(
                            ["OmniRoute-3.8.49/open-sse/services/usage/antigravityWeeklyQuota.ts"]
                            if variant_id == "google_antigravity"
                            else []
                        ),
                    ],
                }
            )
    return records
