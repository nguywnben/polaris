"""Versioned, provider-neutral AI quality policy domain.

The domain is deliberately pure and dependency-free. It projects legacy runtime switches without
writing them, validates stored documents, and previews only bounded metadata. Request content is
never accepted by this layer.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

POLICY_SCHEMA_VERSION = 1
POLICY_STORAGE_KEY = "quality_policy_document"
SUPPORTED_PROFILES = {"quality", "balanced", "capacity", "custom"}
COMPRESSION_RESTRICTION_INHERIT = "inherit"
COMPRESSION_RESTRICTION_DISABLED = "disabled"
COMPRESSION_RESTRICTIONS = frozenset(
    {COMPRESSION_RESTRICTION_INHERIT, COMPRESSION_RESTRICTION_DISABLED}
)


class QualityPolicyError(ValueError):
    def __init__(self, message: str, code: str = "quality_policy_invalid"):
        super().__init__(message)
        self.code = code


def normalize_compression_restriction(value: Any, *, layer: str) -> str:
    """Validate the intentionally small lower-layer compression policy surface."""
    normalized = str(value or COMPRESSION_RESTRICTION_INHERIT).strip().lower()
    if normalized not in COMPRESSION_RESTRICTIONS:
        raise QualityPolicyError(
            f"{layer} compression policy must be inherit or disabled.",
            code="quality_policy_override_invalid",
        )
    return normalized


BALANCED_SETTINGS: dict[str, Any] = {
    "compatibility_mode": False,
    "return_reasoning": True,
    "anti_truncation_max_attempts": 3,
    "compression": {
        "enabled": True,
        "mode": "structural",
        "threshold_tokens": 32_000,
        "target_tokens": 24_000,
        "min_recent_turns": 4,
    },
    "guardrails": {
        "enabled": False,
        "pii_masking_enabled": True,
        "injection_detection_enabled": True,
        "blocked_keywords": [],
    },
    "response_cache": {
        "enabled": False,
        "ttl_seconds": 300,
        "max_entries": 1_000,
    },
}

PROFILE_SETTINGS: dict[str, dict[str, Any]] = {
    "balanced": BALANCED_SETTINGS,
    "quality": {
        **BALANCED_SETTINGS,
        "anti_truncation_max_attempts": 5,
        "compression": {
            **BALANCED_SETTINGS["compression"],
            "enabled": False,
        },
    },
    "capacity": {
        **BALANCED_SETTINGS,
        "return_reasoning": False,
        "anti_truncation_max_attempts": 2,
        "compression": {
            **BALANCED_SETTINGS["compression"],
            "threshold_tokens": 16_000,
            "target_tokens": 10_000,
            "min_recent_turns": 3,
        },
        "response_cache": {
            **BALANCED_SETTINGS["response_cache"],
            "enabled": True,
        },
    },
}

LOCKED_SETTING_PATHS = {
    "compatibility_mode_enabled": ("compatibility_mode",),
    "return_thoughts_to_frontend": ("return_reasoning",),
    "anti_truncation_max_attempts": ("anti_truncation_max_attempts",),
    "token_compression_enabled": ("compression", "enabled"),
    "token_compression_threshold": ("compression", "threshold_tokens"),
    "token_compression_target": ("compression", "target_tokens"),
    "token_compression_min_recent_turns": ("compression", "min_recent_turns"),
    "guardrails_enabled": ("guardrails", "enabled"),
    "guardrails_pii_masking_enabled": ("guardrails", "pii_masking_enabled"),
    "guardrails_injection_detection_enabled": (
        "guardrails",
        "injection_detection_enabled",
    ),
    "guardrails_blocked_keywords": ("guardrails", "blocked_keywords"),
    "response_cache_enabled": ("response_cache", "enabled"),
    "response_cache_ttl_seconds": ("response_cache", "ttl_seconds"),
    "response_cache_max_entries": ("response_cache", "max_entries"),
}


def _bounded_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise QualityPolicyError(f"{name} must be an integer between {minimum} and {maximum}.")
    return value


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise QualityPolicyError(f"{name} must be a boolean.")
    return value


def validate_settings(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise QualityPolicyError("Policy settings must be an object.")
    expected = {
        "compatibility_mode",
        "return_reasoning",
        "anti_truncation_max_attempts",
        "compression",
        "guardrails",
        "response_cache",
    }
    unknown = set(raw) - expected
    missing = expected - set(raw)
    if unknown or missing:
        raise QualityPolicyError(
            "Policy settings contain unsupported or missing fields: "
            + ", ".join(sorted(unknown | missing))
        )

    compression = raw["compression"]
    guardrails = raw["guardrails"]
    response_cache = raw["response_cache"]
    if not all(isinstance(value, Mapping) for value in (compression, guardrails, response_cache)):
        raise QualityPolicyError("Compression, guardrails, and response_cache must be objects.")

    if set(compression) != {
        "enabled",
        "mode",
        "threshold_tokens",
        "target_tokens",
        "min_recent_turns",
    }:
        raise QualityPolicyError("Compression settings are incomplete or unsupported.")
    if compression.get("mode") != "structural":
        raise QualityPolicyError("Only structural compression is supported.")
    threshold = _bounded_int(
        compression.get("threshold_tokens"), "compression.threshold_tokens", 128, 2_000_000
    )
    target = _bounded_int(
        compression.get("target_tokens"), "compression.target_tokens", 64, 1_999_999
    )
    if target >= threshold:
        raise QualityPolicyError("compression.target_tokens must be below threshold_tokens.")

    if set(guardrails) != {
        "enabled",
        "pii_masking_enabled",
        "injection_detection_enabled",
        "blocked_keywords",
    }:
        raise QualityPolicyError("Guardrail settings are incomplete or unsupported.")
    keywords = guardrails.get("blocked_keywords")
    if not isinstance(keywords, list) or len(keywords) > 100:
        raise QualityPolicyError("guardrails.blocked_keywords must contain at most 100 items.")
    normalized_keywords = []
    for keyword in keywords:
        if not isinstance(keyword, str) or not keyword.strip() or len(keyword.strip()) > 128:
            raise QualityPolicyError("Each blocked keyword must contain 1 to 128 characters.")
        normalized_keywords.append(keyword.strip())

    if set(response_cache) != {"enabled", "ttl_seconds", "max_entries"}:
        raise QualityPolicyError("Response-cache settings are incomplete or unsupported.")

    return {
        "compatibility_mode": _boolean(raw.get("compatibility_mode"), "compatibility_mode"),
        "return_reasoning": _boolean(raw.get("return_reasoning"), "return_reasoning"),
        "anti_truncation_max_attempts": _bounded_int(
            raw.get("anti_truncation_max_attempts"),
            "anti_truncation_max_attempts",
            1,
            10,
        ),
        "compression": {
            "enabled": _boolean(compression.get("enabled"), "compression.enabled"),
            "mode": "structural",
            "threshold_tokens": threshold,
            "target_tokens": target,
            "min_recent_turns": _bounded_int(
                compression.get("min_recent_turns"),
                "compression.min_recent_turns",
                1,
                50,
            ),
        },
        "guardrails": {
            "enabled": _boolean(guardrails.get("enabled"), "guardrails.enabled"),
            "pii_masking_enabled": _boolean(
                guardrails.get("pii_masking_enabled"), "guardrails.pii_masking_enabled"
            ),
            "injection_detection_enabled": _boolean(
                guardrails.get("injection_detection_enabled"),
                "guardrails.injection_detection_enabled",
            ),
            "blocked_keywords": normalized_keywords,
        },
        "response_cache": {
            "enabled": _boolean(response_cache.get("enabled"), "response_cache.enabled"),
            "ttl_seconds": _bounded_int(
                response_cache.get("ttl_seconds"), "response_cache.ttl_seconds", 1, 86_400
            ),
            "max_entries": _bounded_int(
                response_cache.get("max_entries"),
                "response_cache.max_entries",
                1,
                100_000,
            ),
        },
    }


def settings_from_legacy(legacy: Mapping[str, Any]) -> dict[str, Any]:
    return validate_settings(
        {
            "compatibility_mode": legacy["compatibility_mode_enabled"],
            "return_reasoning": legacy["return_thoughts_to_frontend"],
            "anti_truncation_max_attempts": legacy["anti_truncation_max_attempts"],
            "compression": {
                "enabled": legacy["token_compression_enabled"],
                "mode": "structural",
                "threshold_tokens": legacy["token_compression_threshold"],
                "target_tokens": legacy["token_compression_target"],
                "min_recent_turns": legacy["token_compression_min_recent_turns"],
            },
            "guardrails": {
                "enabled": legacy["guardrails_enabled"],
                "pii_masking_enabled": legacy["guardrails_pii_masking_enabled"],
                "injection_detection_enabled": legacy["guardrails_injection_detection_enabled"],
                "blocked_keywords": legacy["guardrails_blocked_keywords"],
            },
            "response_cache": {
                "enabled": legacy["response_cache_enabled"],
                "ttl_seconds": legacy["response_cache_ttl_seconds"],
                "max_entries": legacy["response_cache_max_entries"],
            },
        }
    )


def build_policy_document(
    *,
    profile: str,
    revision: int,
    settings: Mapping[str, Any] | None = None,
    source: str = "stored",
    updated_at: str | None = None,
) -> dict[str, Any]:
    if profile not in SUPPORTED_PROFILES:
        raise QualityPolicyError(f"Unsupported quality profile: {profile}.")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise QualityPolicyError("Policy revision must be a non-negative integer.")
    if profile == "custom":
        if settings is None:
            raise QualityPolicyError("Custom policies require explicit settings.")
        resolved_settings = validate_settings(settings)
    else:
        if settings is not None:
            raise QualityPolicyError("Preset profiles do not accept custom settings.")
        resolved_settings = validate_settings(deepcopy(PROFILE_SETTINGS[profile]))

    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "revision": revision,
        "profile": profile,
        "settings": resolved_settings,
        "source": source,
        "updated_at": updated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def get_profile_defaults() -> dict[str, dict[str, Any]]:
    """Return validated copies of every operator-selectable preset."""
    return {
        profile: build_policy_document(profile=profile, revision=0)["settings"]
        for profile in ("quality", "balanced", "capacity")
    }


def project_legacy_policy(legacy: Mapping[str, Any]) -> dict[str, Any]:
    settings = settings_from_legacy(legacy)
    profile = "balanced" if settings == validate_settings(BALANCED_SETTINGS) else "custom"
    return build_policy_document(
        profile=profile,
        revision=0,
        settings=settings if profile == "custom" else None,
        source="legacy_projection",
    )


def load_policy_document(stored: Any, legacy: Mapping[str, Any]) -> dict[str, Any]:
    if stored is None:
        return project_legacy_policy(legacy)
    if not isinstance(stored, Mapping):
        raise QualityPolicyError("Stored quality policy is not an object.")
    if stored.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise QualityPolicyError("Stored quality policy schema version is unsupported.")
    profile = stored.get("profile")
    if profile not in SUPPORTED_PROFILES:
        raise QualityPolicyError("Stored quality policy profile is unsupported.")
    revision = stored.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise QualityPolicyError("Stored quality policy revision is invalid.")
    settings = validate_settings(stored.get("settings"))
    if profile != "custom" and settings != validate_settings(PROFILE_SETTINGS[profile]):
        raise QualityPolicyError("Stored preset settings do not match the policy schema.")
    updated_at = stored.get("updated_at")
    if not isinstance(updated_at, str) or not 1 <= len(updated_at) <= 64:
        raise QualityPolicyError("Stored quality policy update time is invalid.")
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "revision": revision,
        "profile": profile,
        "settings": settings,
        "source": "stored",
        "updated_at": updated_at,
    }


def changed_locked_fields(
    current_settings: Mapping[str, Any],
    desired_settings: Mapping[str, Any],
    env_locked_fields: set[str],
) -> list[str]:
    changed = []
    for field in sorted(env_locked_fields & set(LOCKED_SETTING_PATHS)):
        path = LOCKED_SETTING_PATHS[field]
        current: Any = current_settings
        desired: Any = desired_settings
        for part in path:
            current = current[part]
            desired = desired[part]
        if current != desired:
            changed.append(field)
    return changed


def assess_policy_warnings(raw_settings: Mapping[str, Any]) -> list[str]:
    """Return stable operator-facing warning codes for risky policy combinations."""
    settings = validate_settings(raw_settings)
    warnings: list[str] = []
    compression = settings["compression"]
    guardrails = settings["guardrails"]
    response_cache = settings["response_cache"]

    if settings["compatibility_mode"]:
        warnings.append("compatibility_changes_instruction_shape")
    if compression["enabled"] and compression["min_recent_turns"] < 3:
        warnings.append("low_recent_turn_retention")
    if (
        guardrails["enabled"]
        and not guardrails["pii_masking_enabled"]
        and not guardrails["injection_detection_enabled"]
        and not guardrails["blocked_keywords"]
    ):
        warnings.append("guardrails_without_checks")
    if response_cache["enabled"] and settings["return_reasoning"]:
        warnings.append("cache_with_reasoning")
    if settings["anti_truncation_max_attempts"] > 5:
        warnings.append("high_recovery_attempts")
    return warnings


def preview_policy(policy: Mapping[str, Any], descriptor: Mapping[str, Any]) -> dict[str, Any]:
    estimated_tokens = _bounded_int(
        descriptor.get("estimated_input_tokens"), "estimated_input_tokens", 0, 2_000_000
    )
    message_count = _bounded_int(descriptor.get("message_count"), "message_count", 0, 100_000)
    tool_count = _bounded_int(descriptor.get("tool_count"), "tool_count", 0, 10_000)
    has_system = _boolean(descriptor.get("has_system_instruction"), "has_system_instruction")
    has_tool_pairs = _boolean(descriptor.get("has_tool_pairs"), "has_tool_pairs")
    settings = validate_settings(policy["settings"])
    compression = settings["compression"]

    if not compression["enabled"]:
        reason = "compression_disabled"
        estimated_after = estimated_tokens
    elif estimated_tokens <= compression["threshold_tokens"]:
        reason = "below_compression_threshold"
        estimated_after = estimated_tokens
    else:
        reason = "structural_compression_candidate"
        estimated_after = min(estimated_tokens, compression["target_tokens"])

    estimated_saved = estimated_tokens - estimated_after
    estimated_removed_messages = (
        min(message_count, (message_count * estimated_saved) // estimated_tokens)
        if estimated_tokens and estimated_saved
        else 0
    )
    will_transform = reason == "structural_compression_candidate"

    return {
        "policy": {
            "schema_version": policy["schema_version"],
            "revision": policy["revision"],
            "profile": policy["profile"],
        },
        "request_shape": {
            "estimated_input_tokens": estimated_tokens,
            "message_count": message_count,
            "tool_count": tool_count,
            "has_system_instruction": has_system,
            "has_tool_pairs": has_tool_pairs,
        },
        "decision": {
            "compression_mode": compression["mode"],
            "reason": reason,
            "estimated_tokens_before": estimated_tokens,
            "estimated_tokens_after": estimated_after,
            "estimated_tokens_saved": estimated_saved,
            "protected_structures": [
                name
                for name, present in (
                    ("system_instruction", has_system),
                    ("tool_call_result_pairs", has_tool_pairs),
                    ("recent_complete_turns", message_count > 0),
                )
                if present
            ],
        },
        "transformation": {
            "will_transform": will_transform,
            "scope": "history_prefix_only" if will_transform else "none",
            "estimated_removed_messages": estimated_removed_messages,
            "failure_behavior": "forward_unchanged",
        },
        "warnings": assess_policy_warnings(settings),
        "provider_call": False,
        "persisted": False,
    }
