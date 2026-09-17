"""Source-shaped, synthetic upstream responses persisted in the demo SQLite DB.

Amounts are scenarios, not claims about a plan's actual price or allowance. No
normalized UI fields are authored here. See docs/audits/synthetic-fidelity-2026-09-17.md.
"""

from datetime import datetime, timezone

QUOTA_SOURCES = {
    "google_antigravity": "cockpit-tools/src-tauri/src/modules/quota.rs",
    "grok": "cockpit-tools/src-tauri/src/modules/grok_account.rs",
    "codex": "OmniRoute-3.8.49/open-sse/services/codexQuotaFetcher.ts",
    "claude_code": "cockpit-tools/src-tauri/src/modules/claude_account_desktop_auth.rs",
    "kiro": "cockpit-tools/src-tauri/src/modules/kiro_oauth.rs",
    "muse_code": "docs/providers/muse-code-research-2026-09-16.md",
}


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def quota_payloads(variant, number, now, models):
    used = (12, 48, 100, 32, 75, 94, None)[number - 1]
    reset, week = now + 7200, now + 3 * 86400
    if variant == "google_antigravity":
        return {
            "quota": {
                "models": {
                    m: {
                        "quotaInfo": {
                            **(
                                {"remainingFraction": max(0, 1 - (used + i * 4) / 100)}
                                if used is not None
                                else {}
                            ),
                            "resetTime": iso(reset),
                        }
                    }
                    for i, m in enumerate(models)
                }
            },
            "account": {}
            if number == 7
            else {
                "paidTier": {
                    "id": "g1-pro-tier",
                    **(
                        {
                            "availableCredits": [
                                {
                                    "creditType": "GOOGLE_ONE_AI",
                                    "creditAmount": 125,
                                    "minimumCreditAmountForUsage": 2,
                                }
                            ]
                        }
                        if number in {2, 4}
                        else {}
                    ),
                }
            },
        }
    if variant == "codex":

        def window(percent, duration, end):
            return {"used_percent": percent, "limit_window_seconds": duration, "reset_at": end}

        return {
            "quota": {
                "plan_type": "plus" if number % 2 else "pro",
                **(
                    {
                        "rate_limit": {
                            "limit_reached": used == 100,
                            "primary_window": window(used, 18000, reset),
                            "secondary_window": window(35 if used != 100 else 100, 604800, week),
                        }
                    }
                    if used is not None
                    else {}
                ),
                **(
                    {
                        "code_review_rate_limit": {"primary_window": window(20, 604800, week)},
                        "credits": {"has_credits": True, "balance": 12.5, "unlimited": False},
                        "rate_limit_reset_credits": {"available_count": 2},
                    }
                    if number == 2
                    else {}
                ),
                **(
                    {
                        "additional_rate_limits": [
                            {
                                "limit_name": "gpt-5.3-codex-spark",
                                "rate_limit": {"primary_window": window(50, 18000, reset)},
                            }
                        ]
                    }
                    if number == 6
                    else {}
                ),
            }
        }
    if variant == "claude_code":
        return {
            "quota": {
                # Claude's subscription is a separate profile response in the
                # reference client, not a guaranteed /api/oauth/usage field.
                **({"extra_usage": {"is_enabled": False}} if number == 7 else {}),
                **(
                    {
                        "five_hour": {"utilization": used, "resets_at": iso(reset)},
                        "seven_day": {
                            "utilization": 100 if used == 100 else 35,
                            "resets_at": iso(week),
                        },
                    }
                    if used is not None
                    else {}
                ),
                **(
                    {
                        "seven_day_sonnet": {"utilization": 64, "resets_at": iso(week)},
                        "extra_usage": {
                            "is_enabled": True,
                            "used_credits": 125,
                            "monthly_limit": 5000,
                            "utilization": 2.5,
                        },
                    }
                    if number == 2
                    else {}
                ),
            }
        }
    if variant == "grok":
        return {
            "quota": {
                "config": {
                    "monthlyLimit": {"val": 80},
                    **({"used": {"val": 80 * used / 100}} if used is not None else {}),
                    "billingPeriodEnd": iso(now + 10 * 86400),
                    **(
                        {
                            "onDemandUsed": 5,
                            "onDemandCap": 20,
                            "prepaidBalance": 12,
                            "subscription_tier": "SUBSCRIPTION_TIER_SUPERGROK",
                            "productUsage": [{"product": "coding", "usagePercent": 12}],
                        }
                        if number == 2
                        else {}
                    ),
                }
            },
            "weekly": {
                "config": {
                    "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY"},
                    "billingPeriodEnd": iso(week),
                    **(
                        {"creditUsagePercent": 100 if used == 100 else 35}
                        if used is not None
                        else {}
                    ),
                }
            },
        }
    if variant == "kiro":
        return {
            "quota": {
                "subscriptionInfo": {
                    "subscriptionTitle": "KIRO FREE",
                    "type": "Q_DEVELOPER_STANDALONE_FREE",
                },
                "nextDateReset": now + 10 * 86400,
                "overageConfiguration": {"overageStatus": "DISABLED"},
                "usageBreakdownList": [
                    {
                        "resourceType": "AGENTIC_REQUEST",
                        "displayName": "Credits",
                        "usageLimitWithPrecision": 50,
                        **({"currentUsageWithPrecision": used / 2} if used is not None else {}),
                        **(
                            {
                                "freeTrialInfo": {
                                    "usageLimit": 500,
                                    "currentUsage": 200,
                                    "freeTrialStatus": "ACTIVE",
                                    "freeTrialExpiry": iso(now + 86400),
                                },
                                "bonuses": [
                                    {
                                        "bonusCode": "WELCOME",
                                        "usageLimit": 100,
                                        "currentUsage": 20,
                                        "status": "ACTIVE",
                                        "expiresAt": iso(week),
                                    }
                                ],
                            }
                            if number == 2
                            else {}
                        ),
                        **(
                            {
                                "freeTrialInfo": {
                                    "usageLimit": 500,
                                    "currentUsage": 500,
                                    "freeTrialStatus": "EXPIRED",
                                    "freeTrialExpiry": iso(now - 86400),
                                }
                            }
                            if number == 6
                            else {}
                        ),
                    }
                ],
            }
        }
    if variant == "muse_code":
        return {
            "subscription": {
                "subs_tier_name": "Muse Code Power Usage",
                **(
                    {
                        "subs_usage": {
                            "window": {
                                "used_percent": used,
                                "resets_at": reset,
                                "window_duration_mins": 300,
                            },
                            "weekly": {
                                "used_percent": 100 if used == 100 else 35,
                                "resets_at": week,
                            },
                        }
                    }
                    if used is not None
                    else {}
                ),
            }
        }
    return {}
