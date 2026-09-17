"""Fictional, internally consistent history for the isolated Polaris preview."""

from datetime import datetime, timezone
from hashlib import sha256

from core.audit import create_audit_event
from core.pricing import calculate_cost_usd
from core.request_trace import RequestDecision, RequestTrace
from core.usage_ledger import UsageLedgerEntry, usd_to_nanos
from core.usage_stats import normalize_token_usage

FINGERPRINT_KEY = b"polaris-public-synthetic-fixture-only-key"
OFFSETS = (60, 300, 3600, 43200, 2 * 86400, 6 * 86400, 14 * 86400, 29 * 86400)


def timestamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def build_activity(records, keys, now):
    """One trace per ledger row; no prompts, provider IO or real identifiers."""
    for index, record in enumerate(records):
        data = record["data"]
        for period, offset in enumerate(OFFSETS):
            request_id = f"demo-request-{index:03}-{period}"
            event_id = sha256(request_id.encode()).hexdigest()[:32]
            status = (200, 200, 200, 200, 200, 429, 200, 502)[(index + period) % 8]
            if period < 2:
                status = {3: 429, 5: 401}.get(record["number"], 200)
            success = status == 200
            occurred = now - offset - index * 2
            # A paused credential's traffic predates its disablement, not a
            # fabricated successful request while it was unavailable to routing.
            if record["state"]["disabled"]:
                occurred -= 2 * 86400
            latency = 210 + (index * 37 + period * 113) % 2200
            input_tokens = (1200 + index * 317 + period * 41) if success else 0
            output_tokens = (180 + index * 29 + period * 17) if success else 0
            compressed = success and index % 3 == 0
            saved = input_tokens // 3 if compressed else 0
            model = data["model_ids"][period % len(data["model_ids"])]
            cached = (
                input_tokens // 5
                if data["provider"]
                in {"openai", "anthropic", "google_ai_studio", "google_antigravity", "deepseek"}
                else 0
            )
            cache_creation = input_tokens // 10 if data["provider"] == "anthropic" else 0
            reasoning = (
                output_tokens // 4
                if ("reason" in model or data["provider"] in {"openai", "muse_code", "meta"})
                else 0
            )
            tokens = normalize_token_usage(
                {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cached_tokens": cached,
                    "cache_creation_tokens": cache_creation,
                    "reasoning_tokens": reasoning,
                    "usage_reported": success,
                }
            )
            cost = usd_to_nanos(
                calculate_cost_usd(
                    model,
                    provider=data["provider"],
                    **{
                        k: tokens[k]
                        for k in (
                            "input_tokens",
                            "output_tokens",
                            "cached_tokens",
                            "cache_creation_tokens",
                            "reasoning_tokens",
                        )
                    },
                )
            )
            # Historical calls predate revocation/expiry; management-only key is never used.
            key = keys[index % 6] if period >= 4 else keys[index % 3]
            usage = UsageLedgerEntry(
                schema_version=1,
                event_id=f"use_{event_id}",
                occurred_at=occurred,
                credential_ref=record["filename"],
                request_id=request_id,
                model=model,
                provider=data["provider"],
                status_code=status,
                success=success,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=tokens["total_tokens"],
                cached_tokens=cached,
                cache_creation_tokens=cache_creation,
                reasoning_tokens=reasoning,
                estimated_input_tokens=input_tokens + saved,
                estimated_tokens_saved=saved,
                compressed_messages=4 if compressed else 0,
                quality_profile="custom",
                quality_policy_revision=3,
                compression_reason="target_reached" if compressed else "below_threshold",
                latency_ms=latency,
                retry_count=0,
                cost_nanos=cost,
                api_key_id=key.id,
                usage_reported=success,
            )
            decisions = [
                RequestDecision(1, 0, "request", "accepted", "allowed", "request_received"),
                RequestDecision(
                    2,
                    3,
                    "routing",
                    "selected",
                    "succeeded",
                    "healthy_candidate",
                    provider=data["provider"],
                    model=model,
                    candidate_count=1,
                ),
                RequestDecision(
                    3,
                    5,
                    "compression",
                    "applied" if compressed else "skipped",
                    "succeeded" if compressed else "skipped",
                    "token_budget" if compressed else "history_within_limit",
                    original_tokens=input_tokens + saved,
                    final_tokens=input_tokens,
                ),
                RequestDecision(
                    4,
                    latency,
                    "upstream",
                    "succeeded" if success else "failed",
                    "succeeded" if success else "failed",
                    "completed" if success else "provider_error",
                    provider=data["provider"],
                    model=model,
                    status_code=status,
                    latency_ms=latency,
                ),
                RequestDecision(
                    5,
                    latency,
                    "usage",
                    "recorded",
                    "succeeded",
                    "usage_recorded",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_tokens=usage.cached_tokens,
                    cost_usd=cost / 1e9,
                ),
                RequestDecision(
                    6,
                    latency,
                    "outcome",
                    "completed",
                    "succeeded" if success else "failed",
                    "completed" if success else "provider_error",
                    status_code=status,
                ),
            ]
            trace = RequestTrace(
                schema_version=1,
                trace_id=event_id,
                request_id=request_id,
                protocol=(
                    "openai_chat",
                    "openai_responses",
                    "anthropic_messages",
                    "gemini_generate",
                )[index % 4],
                started_at=timestamp(occurred),
                completed_at=timestamp(occurred + latency / 1000),
                outcome="succeeded"
                if success
                else ("rate_limited" if status == 429 else "upstream_error"),
                status_code=status,
                duration_ms=latency,
                requested_model=model,
                selected_provider=data["provider"],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=tokens["total_tokens"],
                cost_usd=cost / 1e9,
                decisions=tuple(decisions),
            )
            yield usage, trace


def build_local_traces(now):
    """Requests stopped before an upstream attempt do not create provider usage."""
    scenarios = (
        ("denied", 403, "guardrail", "blocked", "denied", "blocked_keyword"),
        ("denied", 403, "quota", "denied", "denied", "budget_exceeded"),
        ("rate_limited", 429, "quota", "denied", "denied", "quota_exceeded"),
        ("unavailable", 503, "routing", "unavailable", "failed", "no_candidate"),
        ("cancelled", 499, "request", "cancelled", "failed", "cancelled"),
        ("client_error", 400, "request", "failed", "failed", "client_error"),
        ("internal_error", 500, "request", "failed", "failed", "server_error"),
        ("succeeded", 200, "cache", "hit", "hit", "cache_hit"),
    )
    for index, (outcome, status, category, action, result, reason) in enumerate(scenarios):
        request_id = f"demo-local-{index:02}"
        started = now - 90 - index * 35
        yield RequestTrace(
            schema_version=1,
            trace_id=sha256(request_id.encode()).hexdigest()[:32],
            request_id=request_id,
            protocol="openai_chat",
            started_at=timestamp(started),
            completed_at=timestamp(started + 0.025),
            duration_ms=25,
            outcome=outcome,
            status_code=status,
            requested_model="polaris",
            decisions=(
                RequestDecision(1, 0, "request", "accepted", "allowed", "request_received"),
                RequestDecision(2, 12, category, action, result, reason),
                RequestDecision(
                    3,
                    25,
                    "outcome",
                    "completed",
                    "succeeded" if status == 200 else "failed",
                    "completed" if status == 200 else reason,
                    status_code=status,
                ),
            ),
        )


def build_audits(records, now, keys=()):
    actions = (
        ("credential.create", "credential", "created"),
        ("credential.toggle", "credential", "disabled"),
        ("credential.quota", "credential", "no_change"),
        ("virtual_key.create", "virtual_key", "created"),
        ("virtual_key.rotate", "virtual_key", "rotated"),
        ("quality_policy.update", "quality_policy", "policy_changed"),
        ("config.update", "configuration", "settings_changed"),
        ("backup.create", "backup", "created"),
        ("identity.create", "identity", "created"),
        ("session.revoke", "session", "revoked"),
    )
    for index in range(80):
        action, target_type, change = actions[index % len(actions)]
        yield create_audit_event(
            request_id=f"demo-audit-{index:03}",
            actor_type="local_owner",
            actor_identifier="demo-owner",
            action=action,
            target_type=target_type,
            target_identifier=(
                records[index % len(records)]["filename"]
                if target_type == "credential"
                else keys[index % len(keys)].id
                if target_type == "virtual_key" and keys
                else f"demo-{target_type}-{index}"
            ),
            outcome=("denied" if index % 13 == 0 else "failed" if index % 17 == 0 else "succeeded"),
            change_codes=("no_change",) if index % 13 == 0 or index % 17 == 0 else (change,),
            fingerprint_key=FINGERPRINT_KEY,
            occurred_at=datetime.fromtimestamp(now - index * 7200, timezone.utc),
        )
