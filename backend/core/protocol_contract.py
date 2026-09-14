"""Versioned semantic contract for advertised public inference conversions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

PROTOCOL_CONTRACT_SCHEMA_VERSION = 1

FeatureDisposition = Literal["supported", "translated", "rejected"]


class ProtocolTranslationError(ValueError):
    """Raised when translation would otherwise discard response semantics."""


def validate_gemini_response_part(part: Any) -> None:
    """Reject response parts that cannot be represented by translated protocols."""
    if not isinstance(part, dict):
        raise ProtocolTranslationError("Gemini response parts must be objects.")

    variants = (
        ("text", {"text", "thought", "thoughtSignature"}),
        ("functionCall", {"functionCall", "thoughtSignature"}),
        ("inlineData", {"inlineData"}),
        ("executableCode", {"executableCode"}),
        ("codeExecutionResult", {"codeExecutionResult"}),
    )
    for discriminator, allowed in variants:
        if discriminator in part:
            unknown = set(part) - allowed
            if unknown:
                raise ProtocolTranslationError(
                    f"Unsupported Gemini response part fields: {', '.join(sorted(unknown))}."
                )
            return
    raise ProtocolTranslationError("Unsupported Gemini response part type.")


PROTOCOL_FEATURE_VOCABULARY = (
    "text_input",
    "multimodal_input",
    "system_messages",
    "tools",
    "structured_output",
    "reasoning_control",
    "reasoning_output",
    "usage",
    "finish_reasons",
    "normalized_errors",
)

_TRANSLATED_FEATURES: dict[str, FeatureDisposition] = {
    feature: "translated" for feature in PROTOCOL_FEATURE_VOCABULARY
}
_TRANSLATED_FEATURES["normalized_errors"] = "supported"

_OPENAI_TRANSLATED_FEATURES = {
    **_TRANSLATED_FEATURES,
    "reasoning_control": "rejected",
}

_NATIVE_FEATURES: dict[str, FeatureDisposition] = {
    feature: "supported" for feature in PROTOCOL_FEATURE_VOCABULARY
}

_PROTOCOL_CONVERSIONS: dict[str, dict[str, Any]] = {
    "anthropic_messages_to_gemini": {
        "family": "anthropic_messages",
        "features": _TRANSLATED_FEATURES,
    },
    "gemini_native": {
        "family": "gemini_native",
        "features": _NATIVE_FEATURES,
    },
    "openai_chat_to_gemini": {
        "family": "openai_chat_completions",
        "features": _OPENAI_TRANSLATED_FEATURES,
    },
    "openai_responses_to_chat": {
        "family": "openai_responses",
        "features": _OPENAI_TRANSLATED_FEATURES,
    },
    "vertex_gemini": {
        "family": "vertex",
        "features": _NATIVE_FEATURES,
    },
    "vertex_openai_to_gemini": {
        "family": "vertex",
        "features": _OPENAI_TRANSLATED_FEATURES,
    },
}


def list_protocol_conversions() -> dict[str, dict[str, Any]]:
    """Return an isolated copy of the immutable R1 protocol conversion matrix."""
    return deepcopy(_PROTOCOL_CONVERSIONS)
