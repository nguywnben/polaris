import asyncio

from core.i18n import LocalizedJSONResponse as JSONResponse
from core.pricing import get_pricing_table_status
from core.usage_stats import (
    UNASSIGNED_USAGE_FILENAME,
    get_credential_counts,
    get_stats_for_period,
    get_time_series_stats,
    get_usage_period_metadata,
    normalize_usage_period,
)
from core.utils import verify_panel_token
from fastapi import APIRouter, Depends, Query
from log import log

from .utils import INTERNAL_SERVER_ERROR_DETAIL

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/stats")
async def get_usage_stats(
    period: str = Query("1d"),
    timezone_offset_minutes: int = Query(0, ge=-840, le=840),
    token: str = Depends(verify_panel_token),
):
    try:
        normalized_period = normalize_usage_period(period)
        data = await get_stats_for_period(normalized_period, timezone_offset_minutes)
        return {
            "success": True,
            "period": get_usage_period_metadata(normalized_period),
            "data": data,
        }
    except Exception as exc:
        log.error(f"Failed to retrieve usage statistics: {exc}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": INTERNAL_SERVER_ERROR_DETAIL},
        )


@router.get("/stats/page")
async def get_usage_stats_page(
    period: str = Query("1d"),
    timezone_offset_minutes: int = Query(0, ge=-840, le=840),
    page_size: int = Query(100, ge=1, le=200),
    token: str = Depends(verify_panel_token),
):
    result = await get_usage_stats(
        period=period,
        timezone_offset_minutes=timezone_offset_minutes,
        token=token,
    )
    if isinstance(result, JSONResponse):
        return result
    ordered = sorted(
        result["data"].items(),
        key=lambda item: (-int(item[1].get("calls", 0)), item[0]),
    )
    return {
        **result,
        "data": dict(ordered[:page_size]),
        "page_size": page_size,
        "total_items": len(ordered),
        "has_more": len(ordered) > page_size,
    }


@router.get("/aggregated")
async def get_aggregated_stats(
    period: str = Query("1d"),
    timezone_offset_minutes: int = Query(0, ge=-840, le=840),
    token: str = Depends(verify_panel_token),
):
    try:
        normalized_period = normalize_usage_period(period)
        usage_data = await get_stats_for_period(normalized_period, timezone_offset_minutes)
        credential_counts, timeline = await asyncio.gather(
            get_credential_counts(),
            get_time_series_stats(
                normalized_period,
                timezone_offset_minutes=timezone_offset_minutes,
            ),
        )
        total_calls = sum(item["calls"] for item in usage_data.values())
        successful_calls = sum(item.get("successful_calls", 0) for item in usage_data.values())
        failed_calls = sum(item.get("failed_calls", 0) for item in usage_data.values())
        assigned_usage_data = {
            filename: item
            for filename, item in usage_data.items()
            if filename != UNASSIGNED_USAGE_FILENAME
        }
        assigned_calls = sum(item["calls"] for item in assigned_usage_data.values())
        input_tokens = sum(item.get("input_tokens", 0) for item in usage_data.values())
        output_tokens = sum(item.get("output_tokens", 0) for item in usage_data.values())
        total_tokens = sum(item.get("total_tokens", 0) for item in usage_data.values())
        cached_tokens = sum(item.get("cached_tokens", 0) for item in usage_data.values())
        cache_creation_tokens = sum(
            item.get("cache_creation_tokens", 0) for item in usage_data.values()
        )
        reasoning_tokens = sum(item.get("reasoning_tokens", 0) for item in usage_data.values())
        reported_usage_calls = sum(
            item.get("reported_usage_calls", 0) for item in usage_data.values()
        )
        estimated_input_tokens = sum(
            item.get("estimated_input_tokens", 0) for item in usage_data.values()
        )
        estimated_tokens_saved = sum(
            item.get("estimated_tokens_saved", 0) for item in usage_data.values()
        )
        compressed_messages = sum(
            item.get("compressed_messages", 0) for item in usage_data.values()
        )
        total_cost_usd = round(sum(item.get("cost_usd", 0.0) for item in usage_data.values()), 6)
        total_files = credential_counts["total"]
        active_files = credential_counts["active"]
        disabled_files = credential_counts["disabled"]
        avg_calls = assigned_calls / active_files if active_files > 0 else 0.0
        avg_tokens = total_tokens / reported_usage_calls if reported_usage_calls > 0 else 0.0

        return {
            "success": True,
            "data": {
                "period": get_usage_period_metadata(normalized_period),
                "total_calls": total_calls,
                "assigned_calls": assigned_calls,
                "successful_calls": successful_calls,
                "failed_calls": failed_calls,
                "total_upstream_attempts": total_calls,
                "successful_upstream_attempts": successful_calls,
                "failed_upstream_attempts": failed_calls,
                "total_calls_24h": total_calls,
                "assigned_calls_24h": assigned_calls,
                "successful_calls_24h": successful_calls,
                "failed_calls_24h": failed_calls,
                "total_files": total_files,
                "active_files": active_files,
                "disabled_files": disabled_files,
                "avg_calls_per_file": avg_calls,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cached_tokens": cached_tokens,
                "cache_creation_tokens": cache_creation_tokens,
                "reasoning_tokens": reasoning_tokens,
                "reported_usage_calls": reported_usage_calls,
                "unreported_successful_calls": max(0, successful_calls - reported_usage_calls),
                "estimated_input_tokens": estimated_input_tokens,
                "estimated_tokens_saved": estimated_tokens_saved,
                "compressed_messages": compressed_messages,
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
                "avg_tokens_per_successful_request": avg_tokens,
                "total_cost_usd": total_cost_usd,
                "pricing": get_pricing_table_status(),
                "timeline": timeline,
            },
        }
    except Exception as exc:
        log.error(f"Failed to aggregate usage statistics: {exc}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": INTERNAL_SERVER_ERROR_DETAIL},
        )
