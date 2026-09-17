"""Populate real domain repositories, exclusively inside a newly created demo DB."""

import asyncio
import secrets
from hashlib import sha256

from core.identity.authorization import ManagementRole
from core.model_blacklist import _normalize_blacklist
from core.portable_backup import PortableBackupService, RestoreConflictPolicy
from core.quality_policy import build_policy_document, get_profile_defaults
from core.virtual_keys import VirtualKey

from tools.demo_activity import (
    FINGERPRINT_KEY,
    build_activity,
    build_audits,
    build_local_traces,
    timestamp,
)

DEMO_PASSWORD = "Polaris-Demo-Only-2026!"


def build_keys(now, records):
    labels = (
        "Ứng dụng nội bộ",
        "Nhóm nghiên cứu",
        "Ngân sách thấp",
        "Đã tạm tắt",
        "Đã hết hạn",
        "Đã thu hồi",
        "Chỉ đọc quản trị",
        "Không nén ngữ cảnh",
    )
    keys = []
    for index, label in enumerate(labels):
        keys.append(
            VirtualKey(
                id=f"vk_demo_{index + 1:02}",
                name=f"DEMO · {label}",
                # Discard the random secret: seeded virtual keys cannot be used to log in.
                key_hash=sha256(secrets.token_bytes(32)).hexdigest(),
                key_preview="DEMO…FAKE",
                created_at=now - 40 * 86400,
                last_used_at=None,
                enabled=index != 3,
                expires_at=now - 86400 if index == 4 else now + 30 * 86400,
                revoked_at=now - 86400 if index == 5 else None,
                budget_daily_usd=5 if index == 2 else 10,
                budget_monthly_usd=50 if index == 2 else 100,
                rpm_limit=30 + index * 10,
                tpm_limit=500000 + index * 100000,
                allowed_models=[] if index < 6 else records[0]["data"]["model_ids"],
                scopes=("management:read",)
                if index == 6
                else ("inference:openai", "inference:anthropic", "inference:gemini"),
                compression_policy="disabled" if index == 7 else "inherit",
            )
        )
    return keys


async def seed_application(storage, records, target, now):
    keys = build_keys(now, records)
    activity = list(build_activity(records, keys, now))
    for key in keys:
        calls = [usage.occurred_at for usage, _ in activity if usage.api_key_id == key.id]
        key.last_used_at = max(calls) if calls else None
    settings = get_profile_defaults()["balanced"]
    settings["guardrails"].update(
        enabled=True,
        pii_masking_enabled=True,
        injection_detection_enabled=True,
        blocked_keywords=["DEMO_BLOCKED_TEST_ONLY"],
    )
    settings["response_cache"].update(enabled=True, ttl_seconds=300, max_entries=100)
    policy = build_policy_document(
        profile="custom", revision=3, settings=settings, updated_at=timestamp(now - 40 * 86400)
    )
    chosen = [
        r["data"]["model_ids"][0]
        for r in records
        if r["variant"] in {"openai_platform", "muse_code", "ollama"}
    ]
    excluded = _normalize_blacklist(
        [
            {
                "provider_id": r["data"]["provider"],
                "model_id": r["data"]["model_ids"][-1],
                "credential_name": r["filename"],
                "first_seen_at": now - 7200,
                "last_seen_at": now - 600,
                "failure_count": 2 + index,
            }
            for index, r in enumerate([r for r in records if r["number"] == 5][:3])
        ]
    )
    for key, value in {
        "virtual_keys": [k.to_storage_dict() for k in keys],
        "quality_policy_document": policy,
        "virtual_model_pool": {
            "alias": "polaris",
            "strategy": "priority_fallback",
            "selected_models": list(dict.fromkeys(chosen)),
            "enabled": True,
        },
        "model_route_blacklist": {"entries": excluded},
        "language": "vi",
    }.items():
        if not await storage.set_config(key, value):
            raise RuntimeError(f"Could not store demo configuration: {key}")

    identities = await storage.create_identity_repository()
    for index, role in enumerate(
        (
            ManagementRole.VIEWER,
            ManagementRole.OPERATOR,
            ManagementRole.SECURITY_ADMIN,
            ManagementRole.VIEWER,
        )
    ):
        managed = await identities.create_oidc_identity(
            issuer="https://identity.example.invalid", subject=f"DEMO-member-{index + 1}", role=role
        )
        if index == 3:
            await identities.set_identity_enabled(
                identity_id=managed.identity.identity_id, enabled=False, expected_revision=1
            )
    ledger = await storage.create_usage_ledger_repository()
    traces = await storage.create_request_trace_repository(cursor_signing_key=FINGERPRINT_KEY)
    audits = await storage.create_audit_repository(cursor_signing_key=FINGERPRINT_KEY)
    totals = {"requests": 0, "traces": 0, "audit_events": 0, "tokens": 0, "cost_nanos": 0}
    log_lines = []
    try:
        for usage, trace in activity:
            await ledger.append_usage(usage)
            await traces.append(trace)
            totals["requests"] += 1
            totals["traces"] += 1
            totals["tokens"] += usage.total_tokens
            totals["cost_nanos"] += usage.cost_nanos
            level = "INFO" if usage.success else "WARNING"
            log_lines.append(
                (
                    usage.occurred_at,
                    f"{timestamp(usage.occurred_at)} [{level}] DEMO {usage.request_id} "
                    f"provider={usage.provider} status={usage.status_code} latency_ms={usage.latency_ms}\n",
                )
            )
        for trace in build_local_traces(now):
            await traces.append(trace)
            totals["traces"] += 1
        for event in build_audits(records, now, keys):
            await audits.append(event)
            totals["audit_events"] += 1
    finally:
        await ledger.close()
    for record in records:
        calls = sorted(
            (usage for usage, _ in activity if usage.credential_ref == record["filename"]),
            key=lambda usage: usage.occurred_at,
        )
        successes = [usage for usage in calls if usage.success]
        if successes:
            await storage.record_success(
                record["filename"], mode="primary", call_increment=len(successes)
            )
        for _ in range(len(calls) - len(successes)):
            await storage.record_failure(record["filename"], mode="primary")
        state = {
            **record["state"],
            "last_success": max((usage.occurred_at for usage in successes), default=None),
            "error_codes": [],
            "error_messages": {},
            "model_cooldowns": {},
        }
        if calls and not calls[-1].success:
            latest = calls[-1]
            state.update(
                error_codes=[latest.status_code],
                error_messages={
                    str(latest.status_code): f"Provider returned HTTP {latest.status_code}."
                },
            )
            if latest.status_code == 429:
                state["model_cooldowns"] = {latest.model: now + 600}
        if not await storage.update_credential_state(record["filename"], state, mode="primary"):
            raise RuntimeError("Failed to restore the demo credential health state.")
    log_text = "".join(line for _, line in sorted(log_lines))
    await asyncio.to_thread(_write_exclusive, target.parent / "demo-runtime.log", log_text.encode())
    return {
        "activity": totals,
        "virtual_keys": len(keys),
        "identities": 5,
        "coverage": "full-application",
        "history_days": 30,
    }


def _write_exclusive(path, content):
    with path.open("xb") as output:
        output.write(content)


async def create_demo_backup(target):
    service = PortableBackupService(database_path=target / "credentials.db", credentials_dir=target)
    artifact = await service.create_backup(DEMO_PASSWORD)
    plan = await service.validate_restore(
        artifact.content, DEMO_PASSWORD, conflict_policy=RestoreConflictPolicy.REPLACE
    )
    await asyncio.to_thread(_write_exclusive, target.parent / artifact.filename, artifact.content)
    return {
        "filename": artifact.filename,
        "validated": plan.compatible,
        "table_counts": plan.table_counts,
    }
