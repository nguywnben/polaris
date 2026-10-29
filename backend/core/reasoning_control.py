"""Translate Chat reasoning intent only after the routed model/provider is selected.

Capability sources and the strict-disable policy are recorded in
docs/protocol-translation-contract.md. Unmapped controls fail closed.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from core.provider_registry import (
    CODEX,
    GOOGLE_AI_STUDIO,
    GOOGLE_ANTIGRAVITY,
    OPENAI,
    OPENAI_PLATFORM,
)
from core.request_trace_service import trace_decision

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
REASONING_EFFORT_KEY = "_polaris_reasoning_effort"
_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})
_BUDGETS = {"none": 0, "minimal": 1024, "low": 1024, "medium": 8192, "high": 24576}
_STANDARD_LEVELS = frozenset({"minimal", "low", "medium", "high"})
_GEMINI_LEVELS = {
    "gemini-3-pro": frozenset({"low", "high"}),
    "gemini-3-flash": _STANDARD_LEVELS,
    "gemini-3.1-pro": frozenset({"low", "medium", "high"}),
    "gemini-3.1-flash-lite": _STANDARD_LEVELS,
    "gemini-3.5-flash": _STANDARD_LEVELS,
    "gemini-3.6-flash": _STANDARD_LEVELS,
    "gemini-3.7-flash": frozenset({"low", "medium", "high"}),
    "gemini-3.8-flash": frozenset({"low", "medium", "high"}),
}


class ReasoningControlError(ValueError):
    """A client option cannot be represented, not a credential/availability failure."""

    status_code = 400


def _matches_family(model: str, family: str) -> bool:
    return model == family or model.startswith(f"{family}-")


def _gemini_control(model: str, effort: str) -> dict[str, Any]:
    name = model.lower().removeprefix("models/")
    # Text-generation mappings must not claim capabilities for image/audio/live models.
    specialized = re.search(r"(?:^|-)(?:image|tts|audio|live)(?:-|$)", name)
    if not specialized:
        is_pro_25 = _matches_family(name, "gemini-2.5-pro")
        if is_pro_25 or _matches_family(name, "gemini-2.5-flash"):
            if effort == "none" and is_pro_25:
                raise ReasoningControlError(
                    f"Model '{model}' does not support disabling reasoning (reasoning_effort='none')."
                )
            if effort in _BUDGETS:
                return {"thinkingBudget": _BUDGETS[effort]}
        for family, levels in _GEMINI_LEVELS.items():
            if not _matches_family(name, family):
                continue
            if effort == "none":
                raise ReasoningControlError(
                    f"Model '{model}' does not support disabling reasoning (reasoning_effort='none')."
                )
            # Google's documented OpenAI compatibility mapping for 3.1 Pro.
            level = "low" if family == "gemini-3.1-pro" and effort == "minimal" else effort
            if level in levels:
                return {"thinkingLevel": level}
            break
    raise ReasoningControlError(
        f"reasoning_effort='{effort}' is not supported for model '{model}' by the Gemini translation."
    )


def prepare_reasoning_request(
    request: dict[str, Any], model: str, provider: str, variant: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an isolated inner request and native outer options, without mutating retries.

    The internal intent remains on the original request for cache identity and model
    fallback. It never reaches an upstream payload, compressor or provider adapter.
    """
    inner = dict(request)
    effort = inner.pop(REASONING_EFFORT_KEY, None)
    if effort is None:
        return inner, {}
    if not isinstance(effort, str) or effort not in _EFFORTS:
        raise ReasoningControlError("Invalid reasoning_effort value.")

    options: dict[str, Any] = {}
    if provider in {GOOGLE_ANTIGRAVITY, GOOGLE_AI_STUDIO, "vertex"}:
        control = _gemini_control(model, effort)
        generation = dict(inner.get("generationConfig") or {})
        thinking = dict(generation.get("thinkingConfig") or {})
        # Explicit client intent overrides normalization defaults; never emit both controls.
        thinking.pop("thinkingLevel", None)
        thinking.pop("thinkingBudget", None)
        thinking.update(control)
        if effort == "none" and "includeThoughts" in thinking:
            thinking["includeThoughts"] = False
        generation["thinkingConfig"] = thinking
        inner["generationConfig"] = generation
    elif provider == OPENAI and variant == OPENAI_PLATFORM:
        options["reasoning_effort"] = effort
    elif provider == OPENAI and variant == CODEX:
        options["reasoning"] = {"effort": effort}
    else:
        raise ReasoningControlError(
            f"reasoning_effort='{effort}' is not supported by provider '{provider}' "
            f"for model '{model}'."
        )

    trace_decision(
        category="request",
        action="applied",
        result="succeeded",
        reason=f"reasoning_effort_{effort}",
        provider=provider,
        model=model,
    )
    return inner, options
