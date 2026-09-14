"""Bounded conversation-history compression for Gemini request payloads."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict

from core.token_estimator import estimate_input_tokens


@dataclass(frozen=True)
class CompressionSettings:
    enabled: bool = True
    threshold_tokens: int = 32_000
    target_tokens: int = 24_000
    min_recent_turns: int = 4
    quality_profile: str = ""
    quality_policy_revision: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("Compression enabled must be a boolean.")
        if isinstance(self.threshold_tokens, bool) or not 128 <= self.threshold_tokens <= 2_000_000:
            raise ValueError("Compression threshold must be between 128 and 2000000 tokens.")
        if isinstance(self.target_tokens, bool) or not 64 <= self.target_tokens <= 1_999_999:
            raise ValueError("Compression target must be between 64 and 1999999 tokens.")
        if self.target_tokens >= self.threshold_tokens:
            raise ValueError("Compression target must be lower than the threshold.")
        if isinstance(self.min_recent_turns, bool) or not 1 <= self.min_recent_turns <= 50:
            raise ValueError("Between 1 and 50 recent turns must be preserved.")


@dataclass(frozen=True)
class CompressionResult:
    request: Dict[str, Any]
    original_estimated_tokens: int
    final_estimated_tokens: int
    removed_contents: int
    applied: bool
    reason: str
    quality_profile: str = ""
    quality_policy_revision: int = 0

    @property
    def estimated_tokens_saved(self) -> int:
        return max(0, self.original_estimated_tokens - self.final_estimated_tokens)

    def as_metrics(self) -> Dict[str, Any]:
        return {
            "estimated_input_tokens": self.final_estimated_tokens,
            "estimated_tokens_saved": self.estimated_tokens_saved,
            "compressed_messages": self.removed_contents,
            "quality_profile": self.quality_profile,
            "quality_policy_revision": self.quality_policy_revision,
            "compression_reason": self.reason,
        }


def compression_trace_reason(result: CompressionResult) -> str:
    if result.applied:
        return "token_budget"
    if result.reason == "disabled":
        return "feature_disabled"
    if result.reason == "below_threshold":
        return "history_within_limit"
    return "content_limit"


def _contains_function_response(content: Any) -> bool:
    if not isinstance(content, dict):
        return False
    parts = content.get("parts")
    if not isinstance(parts, list):
        return False
    return any(
        isinstance(part, dict) and ("functionResponse" in part or "function_response" in part)
        for part in parts
    )


def _is_safe_turn_start(content: Any) -> bool:
    return (
        isinstance(content, dict)
        and content.get("role") == "user"
        and not _contains_function_response(content)
    )


def _function_name(part: Dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = part.get(key)
        if isinstance(value, dict):
            name = value.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _analyze_history(contents: list[Any]) -> tuple[str | None, list[int]]:
    """Find cut boundaries that cannot depend on a removed tool call."""
    safe_starts: list[int] = []
    pending_tool_calls: list[str] = []
    for index, content in enumerate(contents):
        if not isinstance(content, dict) or content.get("role") not in {"user", "model"}:
            return "invalid_history", []
        parts = content.get("parts")
        if not isinstance(parts, list) or any(not isinstance(part, dict) for part in parts):
            return "invalid_history", []

        if _is_safe_turn_start(content) and not pending_tool_calls:
            safe_starts.append(index)

        for part in parts:
            call_name = _function_name(part, "functionCall", "function_call")
            response_name = _function_name(part, "functionResponse", "function_response")
            if ("functionCall" in part or "function_call" in part) and call_name is None:
                return "invalid_tool_history", []
            if (
                "functionResponse" in part or "function_response" in part
            ) and response_name is None:
                return "invalid_tool_history", []
            if call_name is not None:
                pending_tool_calls.append(call_name)
            if response_name is not None:
                try:
                    pending_tool_calls.remove(response_name)
                except ValueError:
                    return "invalid_tool_history", []

    return None, safe_starts


def _unchanged_result(
    request: Dict[str, Any], estimated_tokens: int, reason: str, settings: CompressionSettings
) -> CompressionResult:
    return CompressionResult(
        request=request,
        original_estimated_tokens=estimated_tokens,
        final_estimated_tokens=estimated_tokens,
        removed_contents=0,
        applied=False,
        reason=reason,
        quality_profile=settings.quality_profile,
        quality_policy_revision=settings.quality_policy_revision,
    )


def compress_gemini_request(
    request: Dict[str, Any], settings: CompressionSettings
) -> CompressionResult:
    """Prune an old conversation prefix while preserving recent complete turns."""
    try:
        original_estimate = estimate_input_tokens(request)
    except Exception:
        return _unchanged_result(request, 0, "estimation_failed", settings)
    if not settings.enabled:
        return _unchanged_result(request, original_estimate, "disabled", settings)
    if original_estimate <= settings.threshold_tokens:
        return _unchanged_result(request, original_estimate, "below_threshold", settings)

    contents = request.get("contents")
    if not isinstance(contents, list) or len(contents) < 2:
        return _unchanged_result(request, original_estimate, "no_history", settings)

    invalid_reason, safe_starts = _analyze_history(contents)
    if invalid_reason:
        return _unchanged_result(request, original_estimate, invalid_reason, settings)
    if len(safe_starts) <= settings.min_recent_turns:
        return _unchanged_result(request, original_estimate, "minimum_history", settings)

    latest_allowed_cut = safe_starts[-settings.min_recent_turns]
    cut_candidates = [index for index in safe_starts[1:] if index <= latest_allowed_cut]
    if not cut_candidates:
        return _unchanged_result(request, original_estimate, "no_safe_boundary", settings)

    estimate_cache: Dict[int, int] = {}

    def estimate_after_cut(cut_index: int) -> int:
        if cut_index not in estimate_cache:
            candidate = dict(request)
            candidate["contents"] = contents[cut_index:]
            estimate_cache[cut_index] = estimate_input_tokens(candidate)
        return estimate_cache[cut_index]

    try:
        selected_cut = cut_candidates[-1]
        selected_estimate = estimate_after_cut(selected_cut)
        low = 0
        high = len(cut_candidates) - 1
        while low <= high:
            middle = (low + high) // 2
            cut_index = cut_candidates[middle]
            candidate_estimate = estimate_after_cut(cut_index)
            if candidate_estimate <= settings.target_tokens:
                selected_cut = cut_index
                selected_estimate = candidate_estimate
                high = middle - 1
            else:
                low = middle + 1
    except Exception:
        return _unchanged_result(request, original_estimate, "estimation_failed", settings)

    if selected_estimate >= original_estimate:
        return _unchanged_result(request, original_estimate, "no_savings", settings)

    selected_source = dict(request)
    selected_source["contents"] = contents[selected_cut:]
    try:
        selected_request = copy.deepcopy(selected_source)
        selected_contents = selected_request.get("contents")
        preserved_fields = {
            key: value for key, value in selected_request.items() if key != "contents"
        }
        original_fields = {key: value for key, value in request.items() if key != "contents"}
        invariants_hold = (
            selected_request.keys() == request.keys()
            and preserved_fields == original_fields
            and selected_contents == contents[selected_cut:]
            and bool(selected_contents)
            and selected_contents[-1] == contents[-1]
        )
    except Exception:
        invariants_hold = False
    if not invariants_hold:
        return _unchanged_result(request, original_estimate, "invariant_failed", settings)

    return CompressionResult(
        request=selected_request,
        original_estimated_tokens=original_estimate,
        final_estimated_tokens=selected_estimate,
        removed_contents=selected_cut,
        applied=True,
        reason=(
            "target_reached"
            if selected_estimate <= settings.target_tokens
            else "minimum_history_reached"
        ),
        quality_profile=settings.quality_profile,
        quality_policy_revision=settings.quality_policy_revision,
    )
