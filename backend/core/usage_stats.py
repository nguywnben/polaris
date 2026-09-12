import asyncio
import json
import math
import os
import secrets
import time
from typing import Any, Dict, List, Optional

from core.pricing import calculate_cost_usd
from core.provider_registry import (
    GOOGLE_ANTIGRAVITY,
    get_credential_provider,
    get_credential_provider_display_name,
    get_credential_provider_variant,
    get_provider_display_name,
    normalize_provider_id,
)
from core.quality_decision import normalize_quality_decision
from core.usage_ledger import (
    USAGE_LEDGER_SCHEMA_VERSION,
    UsageLedgerEntry,
    nanos_to_usd,
    usd_to_nanos,
)
from core.usage_ledger_service import get_usage_ledger_service
from log import log

UNASSIGNED_USAGE_FILENAME = "__gateway_unassigned__.json"
DELETED_USAGE_PREFIX = "__deleted_credential__"
USAGE_PERIODS = {
    "1d": {"seconds": 86400, "label": "Last 24 hours"},
    "7d": {"seconds": 7 * 86400, "label": "Last 7 days"},
    "30d": {"seconds": 30 * 86400, "label": "Last 30 days"},
    "all": {"seconds": None, "label": "All time"},
}
_stats_inflight: Dict[str, asyncio.Task[Dict[str, Dict[str, Any]]]] = {}


def _int_value(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _provider_display_name(value: Any) -> str:
    return get_provider_display_name(normalize_provider_id(value or GOOGLE_ANTIGRAVITY))


def _credential_provider_display_name(provider: Any, credential_type: Any = "") -> str:
    return get_credential_provider_display_name(
        {
            "provider": provider or GOOGLE_ANTIGRAVITY,
            "credential_type": credential_type or "",
        }
    )


def deleted_usage_filename(provider: Any, credential_type: Any = "") -> str:
    """Return the anonymous history bucket for a deleted provider credential."""
    provider_id = get_credential_provider_variant(
        {
            "provider": provider or GOOGLE_ANTIGRAVITY,
            "credential_type": credential_type or "",
        }
    )
    safe_provider_id = "".join(
        character if character.isalnum() or character == "_" else "_" for character in provider_id
    ).strip("_")
    return f"{DELETED_USAGE_PREFIX}{safe_provider_id or 'unknown'}.json"


def is_deleted_usage_filename(filename: Any) -> bool:
    return os.path.basename(str(filename or "")).startswith(DELETED_USAGE_PREFIX)


def normalize_usage_period(period: str = "1d") -> str:
    normalized = str(period or "1d").strip().lower()
    return normalized if normalized in USAGE_PERIODS else "1d"


def get_usage_period_metadata(period: str = "1d") -> Dict[str, str]:
    normalized = normalize_usage_period(period)
    return {
        "value": normalized,
        "label": str(USAGE_PERIODS[normalized]["label"]),
    }


def _empty_usage_record(metadata: Dict[str, Any]) -> Dict[str, Any]:
    provider_id = normalize_provider_id(metadata.get("provider") or GOOGLE_ANTIGRAVITY)
    return {
        "user_email": metadata.get("user_email", ""),
        "credential_label": metadata.get("credential_label", ""),
        "credential_type": metadata.get("credential_type", ""),
        "provider": provider_id,
        "provider_name": metadata.get("provider_name")
        or _credential_provider_display_name(provider_id, metadata.get("credential_type")),
        "is_deleted": bool(metadata.get("is_deleted", False)),
        "is_historical": bool(metadata.get("is_historical", False)),
        "calls": 0,
        "successful_calls": 0,
        "failed_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
        "reasoning_tokens": 0,
        "reported_usage_calls": 0,
        "estimated_input_tokens": 0,
        "estimated_tokens_saved": 0,
        "compressed_messages": 0,
        "average_latency_ms": 0,
        "retry_count": 0,
        "cost_usd": 0.0,
        "calls_24h": 0,
        "successful_calls_24h": 0,
        "failed_calls_24h": 0,
        "input_tokens_24h": 0,
        "output_tokens_24h": 0,
        "total_tokens_24h": 0,
        "cached_tokens_24h": 0,
        "cache_creation_tokens_24h": 0,
        "reasoning_tokens_24h": 0,
        "reported_usage_calls_24h": 0,
        "estimated_input_tokens_24h": 0,
        "estimated_tokens_saved_24h": 0,
        "compressed_messages_24h": 0,
        "average_latency_ms_24h": 0,
        "retry_count_24h": 0,
        "cost_usd_24h": 0.0,
    }


def _usage_record(
    *,
    existing: Dict[str, Any],
    provider: Any,
    calls: int,
    successful_calls: int,
    failed_calls: int,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    cached_tokens: int,
    cache_creation_tokens: int,
    reasoning_tokens: int,
    reported_usage_calls: int,
    estimated_input_tokens: int,
    estimated_tokens_saved: int,
    compressed_messages: int,
    total_latency_ms: int,
    retry_count: int,
    cost_usd: float = 0.0,
) -> Dict[str, Any]:
    provider_id = normalize_provider_id(existing.get("provider") or provider or GOOGLE_ANTIGRAVITY)
    record = {
        "user_email": existing.get("user_email", ""),
        "credential_label": existing.get("credential_label", ""),
        "credential_type": existing.get("credential_type", ""),
        "provider": provider_id,
        "provider_name": existing.get("provider_name")
        or _credential_provider_display_name(provider_id, existing.get("credential_type")),
        "is_deleted": bool(existing.get("is_deleted", False)),
        "is_historical": bool(existing.get("is_historical", False)),
        "calls": calls,
        "successful_calls": successful_calls,
        "failed_calls": failed_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "reasoning_tokens": reasoning_tokens,
        "reported_usage_calls": reported_usage_calls,
        "estimated_input_tokens": estimated_input_tokens,
        "estimated_tokens_saved": estimated_tokens_saved,
        "compressed_messages": compressed_messages,
        "average_latency_ms": round(total_latency_ms / successful_calls) if successful_calls else 0,
        "retry_count": retry_count,
        "cost_usd": round(float(cost_usd or 0.0), 6),
    }
    record.update(
        {
            "calls_24h": calls,
            "successful_calls_24h": successful_calls,
            "failed_calls_24h": failed_calls,
            "input_tokens_24h": input_tokens,
            "output_tokens_24h": output_tokens,
            "total_tokens_24h": total_tokens,
            "cached_tokens_24h": cached_tokens,
            "cache_creation_tokens_24h": cache_creation_tokens,
            "reasoning_tokens_24h": reasoning_tokens,
            "reported_usage_calls_24h": reported_usage_calls,
            "estimated_input_tokens_24h": estimated_input_tokens,
            "estimated_tokens_saved_24h": estimated_tokens_saved,
            "compressed_messages_24h": compressed_messages,
            "average_latency_ms_24h": record["average_latency_ms"],
            "retry_count_24h": retry_count,
            "cost_usd_24h": record["cost_usd"],
        }
    )
    return record


_TOKEN_USAGE_KEYS = frozenset(
    {
        "promptTokenCount",
        "candidatesTokenCount",
        "totalTokenCount",
        "cachedContentTokenCount",
        "cacheCreationTokenCount",
        "thoughtsTokenCount",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "prompt_tokens_details",
        "completion_tokens_details",
    }
)


def normalize_token_usage(usage: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    usage = usage or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    completion_details = usage.get("completion_tokens_details") or {}

    input_tokens = _int_value(
        usage.get("promptTokenCount", usage.get("input_tokens", usage.get("prompt_tokens")))
    )
    output_tokens = _int_value(
        usage.get(
            "candidatesTokenCount", usage.get("output_tokens", usage.get("completion_tokens"))
        )
    )
    cached_tokens = _int_value(
        usage.get(
            "cachedContentTokenCount",
            usage.get(
                "cached_tokens",
                usage.get("cache_read_input_tokens", prompt_details.get("cached_tokens")),
            ),
        )
    )
    cache_creation_tokens = _int_value(
        usage.get(
            "cacheCreationTokenCount",
            usage.get("cache_creation_tokens", usage.get("cache_creation_input_tokens")),
        )
    )
    reasoning_tokens = _int_value(
        usage.get(
            "thoughtsTokenCount",
            usage.get("reasoning_tokens", completion_details.get("reasoning_tokens")),
        )
    )
    total_tokens = _int_value(usage.get("totalTokenCount", usage.get("total_tokens")))
    usage_reported = bool(
        usage.get("usage_reported", any(key in usage for key in _TOKEN_USAGE_KEYS))
    )

    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens + reasoning_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "reasoning_tokens": reasoning_tokens,
        "usage_reported": usage_reported,
    }


def merge_token_usage(
    current: Optional[Dict[str, Any]], update: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Merge cumulative usage snapshots emitted across an SSE response."""
    existing = normalize_token_usage(current)
    incoming = normalize_token_usage(update)
    merged = {
        field: max(existing[field], incoming[field])
        for field in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_tokens",
            "cache_creation_tokens",
            "reasoning_tokens",
        )
    }
    merged["total_tokens"] = max(
        merged["total_tokens"],
        merged["input_tokens"] + merged["output_tokens"] + merged["reasoning_tokens"],
    )
    merged["usage_reported"] = bool(existing["usage_reported"] or incoming["usage_reported"])
    return merged


def extract_token_usage_from_response(value: Any) -> Dict[str, Any]:
    if value is None:
        return normalize_token_usage(None)

    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return normalize_token_usage(None)

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return normalize_token_usage(None)

    if not isinstance(value, dict):
        return normalize_token_usage(None)

    response_value = value.get("response") if isinstance(value.get("response"), dict) else value
    candidate = {}
    candidates = response_value.get("candidates") if isinstance(response_value, dict) else None
    if isinstance(candidates, list) and candidates:
        candidate = candidates[0] if isinstance(candidates[0], dict) else {}

    usage = (
        response_value.get("usageMetadata")
        or candidate.get("usageMetadata")
        or value.get("usage")
        or {}
    )
    return normalize_token_usage(usage if isinstance(usage, dict) else {})


def extract_token_usage_from_stream_chunk(chunk: Any) -> Dict[str, Any]:
    if isinstance(chunk, bytes):
        try:
            chunk = chunk.decode("utf-8")
        except UnicodeDecodeError:
            return normalize_token_usage(None)

    if not isinstance(chunk, str):
        return normalize_token_usage(None)

    text = chunk.strip()
    if not text:
        return normalize_token_usage(None)

    if text.startswith("data:"):
        text = text[5:].strip()

    if not text or text == "[DONE]":
        return normalize_token_usage(None)

    try:
        payload = json.loads(text)
    except Exception:
        return normalize_token_usage(None)

    return extract_token_usage_from_response(payload)


async def record_call(
    filename: str,
    *,
    model: str = "",
    provider: str = GOOGLE_ANTIGRAVITY,
    status_code: int = 200,
    success: bool = True,
    token_usage: Optional[Dict[str, Any]] = None,
    request_metrics: Optional[Dict[str, Any]] = None,
    request_id: str = "",
    api_key_id: str = "",
    cost_override_usd: Optional[float] = None,
    durable_reservation_id: str = "",
) -> bool:
    filename = os.path.basename(filename)
    if not filename:
        return False

    tokens = normalize_token_usage(token_usage)
    request_metrics = request_metrics or {}
    quality_decision = normalize_quality_decision(request_metrics)
    if cost_override_usd is None:
        cost_usd = calculate_cost_usd(
            model,
            input_tokens=tokens["input_tokens"],
            output_tokens=tokens["output_tokens"],
            cached_tokens=tokens["cached_tokens"],
            cache_creation_tokens=tokens["cache_creation_tokens"],
            reasoning_tokens=tokens["reasoning_tokens"],
            provider=provider,
        )
    else:
        cost_usd = float(cost_override_usd)
        if not math.isfinite(cost_usd) or cost_usd < 0:
            raise ValueError("Cost override must be a finite non-negative amount.")
    try:
        occurred_at = time.time()
        reservation_id = str(durable_reservation_id or "")
        event_id = (
            f"use_{reservation_id[4:]}"
            if reservation_id.startswith("qrs_") and len(reservation_id) == 36
            else f"use_{secrets.token_hex(16)}"
        )
        entry = UsageLedgerEntry(
            schema_version=USAGE_LEDGER_SCHEMA_VERSION,
            event_id=event_id,
            occurred_at=occurred_at,
            credential_ref=filename,
            request_id=str(request_id or "")[:128],
            model=model or "",
            provider=provider or "",
            status_code=_int_value(status_code or 200),
            success=bool(success),
            input_tokens=tokens["input_tokens"],
            output_tokens=tokens["output_tokens"],
            total_tokens=tokens["total_tokens"],
            cached_tokens=tokens["cached_tokens"],
            reasoning_tokens=tokens["reasoning_tokens"],
            estimated_input_tokens=_int_value(request_metrics.get("estimated_input_tokens")),
            estimated_tokens_saved=_int_value(request_metrics.get("estimated_tokens_saved")),
            compressed_messages=_int_value(request_metrics.get("compressed_messages")),
            quality_profile=str(quality_decision["quality_profile"]),
            quality_policy_revision=int(quality_decision["quality_policy_revision"]),
            compression_reason=str(quality_decision["compression_reason"]),
            latency_ms=_int_value(request_metrics.get("latency_ms")),
            retry_count=_int_value(request_metrics.get("retry_count")),
            cost_nanos=usd_to_nanos(cost_usd),
            api_key_id=str(api_key_id or "")[:64],
            cache_creation_tokens=tokens["cache_creation_tokens"],
            usage_reported=bool(success and tokens["usage_reported"]),
        )
        service = get_usage_ledger_service()
        if reservation_id:
            result = await service.commit_reservation(
                reservation_id,
                entry,
                transitioned_at=max(occurred_at, time.time()),
            )
            if result.overspent:
                log.warning("Durable budget settlement exceeded its reserved estimate.")
            return result.committed or result.idempotent
        appended = await service.append_usage(entry)
        return appended.inserted or appended.idempotent
    except Exception as exc:
        log.error(f"Failed to record usage call: {type(exc).__name__}")
        return False


async def retire_credential_usage(
    filename: str, provider: Any, *, credential_type: Any = ""
) -> int:
    """Detach historical usage from a deleted credential without losing totals."""
    source_filename = os.path.basename(str(filename or ""))
    if (
        not source_filename
        or source_filename == UNASSIGNED_USAGE_FILENAME
        or is_deleted_usage_filename(source_filename)
    ):
        return 0

    provider_id = get_credential_provider_variant(
        {
            "provider": provider or GOOGLE_ANTIGRAVITY,
            "credential_type": credential_type or "",
        }
    )
    anonymous_filename = deleted_usage_filename(provider_id, credential_type)
    changed = 0
    while True:
        batch = await get_usage_ledger_service().retire_credential(
            source_filename,
            anonymous_filename,
            provider=provider_id,
            limit=1_000,
        )
        changed += batch
        if batch < 1_000:
            return changed


async def get_credential_counts() -> Dict[str, int]:
    try:
        from core.storage_adapter import get_storage_adapter

        storage_adapter = await get_storage_adapter()
        provider_summary = await storage_adapter._backend.get_credentials_summary(
            limit=None, mode="primary"
        )
        summary_stats = provider_summary.get("stats") or {}

        filenames = set()
        for item in provider_summary.get("items", []):
            filenames.add(os.path.basename(item["filename"]))

        total = _int_value(summary_stats.get("total")) or len(filenames)
        active = _int_value(summary_stats.get("normal"))
        disabled = _int_value(summary_stats.get("disabled"))
        if active == 0 and total > disabled:
            active = total - disabled

        return {
            "total": total,
            "active": active,
            "disabled": disabled,
        }
    except Exception as e:
        log.error(f"Error counting credentials for usage aggregation: {e}")
        return {"total": 0, "active": 0, "disabled": 0}


async def get_total_files_count() -> int:
    counts = await get_credential_counts()
    return counts["total"]


async def get_credential_usage_metadata() -> Dict[str, Dict[str, str]]:
    try:
        from core.storage_adapter import get_storage_adapter

        storage_adapter = await get_storage_adapter()
        provider_summary = await storage_adapter._backend.get_credentials_summary(
            limit=None, mode="primary"
        )

        metadata: Dict[str, Dict[str, str]] = {}
        for item in provider_summary.get("items", []):
            filename = os.path.basename(item.get("filename") or "")
            if not filename:
                continue

            credential_data = await storage_adapter.get_credential(filename, mode="primary") or {}
            provider_id = get_credential_provider(credential_data)

            metadata[filename] = {
                "user_email": str(item.get("user_email") or ""),
                "credential_label": str(credential_data.get("credential_label") or ""),
                "credential_type": str(credential_data.get("credential_type") or ""),
                "provider": provider_id,
                "provider_name": get_credential_provider_display_name(credential_data),
            }

        return metadata
    except Exception as e:
        log.error(f"Error getting credential metadata for usage: {e}")
        return {}


async def get_all_credential_filenames() -> List[str]:
    try:
        from core.storage_adapter import get_storage_adapter

        storage_adapter = await get_storage_adapter()
        provider_summary = await storage_adapter._backend.get_credentials_summary(
            limit=None, mode="primary"
        )

        filenames = set()
        for item in provider_summary.get("items", []):
            filenames.add(os.path.basename(item["filename"]))

        return sorted(list(filenames))
    except Exception as e:
        log.error(f"Error getting credential filenames for usage: {e}")
        return []


async def _load_stats_for_period(normalized_period: str) -> Dict[str, Dict[str, Any]]:
    seconds = USAGE_PERIODS[normalized_period]["seconds"]
    since = time.time() - int(seconds) if seconds is not None else None
    res = {}

    metadata_by_filename = await get_credential_usage_metadata()
    filenames = await get_all_credential_filenames()
    active_filenames = set(filenames)
    for name in filenames:
        metadata = metadata_by_filename.get(name, {})
        res[name] = _empty_usage_record(metadata)

    rows = await get_usage_ledger_service().aggregate_credentials(since=since)
    for row in rows:
        filename = row.credential_ref
        existing = res.get(filename, {})
        is_deleted = is_deleted_usage_filename(filename)
        is_historical = filename != UNASSIGNED_USAGE_FILENAME and filename not in active_filenames
        if is_historical:
            raw_provider = row.provider or GOOGLE_ANTIGRAVITY
            credential_type = (
                "api_key"
                if raw_provider in {"google_ai_studio", "openai_platform", "xai_console"}
                else "oauth"
                if raw_provider in {"grok", "openai"}
                else ""
            )
            provider_id = normalize_provider_id(raw_provider)
            existing = {
                "user_email": "",
                "credential_label": "Deleted credential"
                if is_deleted
                else "Unavailable credential",
                "provider": provider_id,
                "provider_name": _credential_provider_display_name(raw_provider, credential_type),
                "credential_type": credential_type,
                "is_deleted": is_deleted,
                "is_historical": True,
            }
        res[filename] = _usage_record(
            existing=existing,
            provider=row.provider,
            calls=row.calls,
            successful_calls=row.successful_calls,
            failed_calls=row.failed_calls,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            total_tokens=row.total_tokens,
            cached_tokens=row.cached_tokens,
            cache_creation_tokens=row.cache_creation_tokens,
            reasoning_tokens=row.reasoning_tokens,
            reported_usage_calls=row.reported_usage_calls,
            estimated_input_tokens=row.estimated_input_tokens,
            estimated_tokens_saved=row.estimated_tokens_saved,
            compressed_messages=row.compressed_messages,
            total_latency_ms=row.total_latency_ms,
            retry_count=row.retry_count,
            cost_usd=nanos_to_usd(row.cost_nanos),
        )

    return res


async def get_stats_for_period(period: str = "1d") -> Dict[str, Dict[str, Any]]:
    """Share an in-flight period scan across concurrent dashboard consumers."""

    normalized_period = normalize_usage_period(period)
    task = _stats_inflight.get(normalized_period)
    if task is None:
        task = asyncio.create_task(_load_stats_for_period(normalized_period))
        _stats_inflight[normalized_period] = task
        task.add_done_callback(
            lambda completed, key=normalized_period: (
                _stats_inflight.pop(key, None) if _stats_inflight.get(key) is completed else None
            )
        )
    return await asyncio.shield(task)


async def get_time_series_stats(period: str = "1d", points: int = 24) -> List[Dict[str, Any]]:
    """Return time-series aggregated request counts and token volume for charts."""
    normalized_period = normalize_usage_period(period)
    seconds = USAGE_PERIODS[normalized_period]["seconds"]
    if seconds is None:
        seconds = 30 * 86400  # default to 30 days window if 'all'

    now = time.time()
    since = now - int(seconds)
    rows = await get_usage_ledger_service().aggregate_time_series(
        since=since,
        until=now,
        points=max(1, points),
    )
    return [
        {
            "timestamp": row.started_at,
            "end_timestamp": row.ended_at,
            "requests": row.requests,
            "upstream_attempts": row.requests,
            "successful_requests": row.successful_requests,
            "successful_attempts": row.successful_requests,
            "failed_requests": row.failed_requests,
            "failed_attempts": row.failed_requests,
            "tokens": row.tokens,
            "cached_tokens": row.cached_tokens,
            "cost_usd": round(nanos_to_usd(row.cost_nanos), 6),
        }
        for row in rows
    ]


async def get_stats_24h() -> Dict[str, Dict[str, Any]]:
    return await get_stats_for_period("1d")


async def get_provider_metrics() -> List[Dict[str, Any]]:
    """Return all-time selected-backend per-provider aggregates."""
    rows = await get_usage_ledger_service().aggregate_providers()
    return [
        {
            "provider": row.provider,
            "calls": row.calls,
            "successful_calls": row.successful_calls,
            "failed_calls": row.failed_calls,
            "total_tokens": row.total_tokens,
            "cost_usd": round(nanos_to_usd(row.cost_nanos), 6),
            "total_latency_ms": row.total_latency_ms,
        }
        for row in rows
    ]


async def get_spend_since(since: float, api_key_id: Optional[str] = None) -> Dict[str, Any]:
    """Return the total USD spend and token volume recorded after ``since``.

    Used by budget enforcement (per virtual key when ``api_key_id`` is given,
    gateway-wide otherwise). Ledger failures propagate instead of becoming zero spend.
    """
    snapshot = await get_usage_ledger_service().get_spend(
        since=float(since),
        api_key_id=str(api_key_id or ""),
    )
    return {
        "cost_usd": round(nanos_to_usd(snapshot.cost_nanos), 6),
        "total_tokens": snapshot.total_tokens,
        "calls": snapshot.calls,
        "available": snapshot.available,
    }
