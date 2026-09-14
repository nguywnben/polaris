"""Provider identity and capability helpers for the shared credential pool."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

GOOGLE_ANTIGRAVITY = "google_antigravity"
GOOGLE_AI_STUDIO = "google_ai_studio"
XAI = "xai"
GROK = "grok"
XAI_CONSOLE = "xai_console"
OPENAI = "openai"
CODEX = "codex"
OPENAI_PLATFORM = "openai_platform"
ANTHROPIC = "anthropic"
CLAUDE_CODE = "claude_code"
CLAUDE_PLATFORM = "claude_platform"
OLLAMA = "ollama"
MAX_DECLARED_MODELS = 500
MAX_MODEL_ID_LENGTH = 256
MODEL_SUPPORT_UNSUPPORTED = 0
MODEL_SUPPORT_INFERRED = 1
MODEL_SUPPORT_DECLARED = 2
CREDENTIAL_OPERATIONS = frozenset(
    {
        "add",
        "verify",
        "test",
        "refresh",
        "quota",
        "model_discovery",
        "disable",
        "edit",
        "reauthenticate",
        "refresh_identity",
        "toggle",
        "delete",
        "export",
        "credit_mode",
        "preview_channel",
    }
)
_LEGACY_OPERATION_ORDER = (
    "verify",
    "test",
    "toggle",
    "delete",
    "export",
    "quota",
    "credit_mode",
    "refresh_identity",
    "preview_channel",
)
LEGACY_CREDENTIAL_OPERATIONS = frozenset(_LEGACY_OPERATION_ORDER)
_LEGACY_VARIANT_OPERATION_SNAPSHOT = {
    GOOGLE_ANTIGRAVITY: frozenset(
        {"verify", "test", "toggle", "delete", "export", "quota", "credit_mode"}
    ),
    GOOGLE_AI_STUDIO: frozenset({"verify", "test", "toggle", "delete", "export"}),
    GROK: frozenset({"verify", "test", "toggle", "delete", "export", "quota"}),
    XAI_CONSOLE: frozenset({"verify", "test", "toggle", "delete", "export"}),
    CODEX: frozenset({"verify", "test", "toggle", "delete", "export", "quota"}),
    OPENAI_PLATFORM: frozenset({"verify", "test", "toggle", "delete", "export"}),
    CLAUDE_CODE: frozenset({"verify", "test", "toggle", "delete", "export"}),
    CLAUDE_PLATFORM: frozenset({"verify", "test", "toggle", "delete", "export"}),
    OLLAMA: frozenset({"verify", "test", "toggle", "delete", "export"}),
}
INFERENCE_PROTOCOLS = frozenset(
    {
        "anthropic_messages",
        "gemini_native",
        "openai_chat_completions",
        "openai_responses",
        "vertex",
    }
)
_COMMON_CREDENTIAL_OPERATIONS = (
    "add",
    "verify",
    "test",
    "model_discovery",
    "disable",
    "edit",
    "export",
    "delete",
    "toggle",
)
_COMMON_INFERENCE_PROTOCOLS = tuple(sorted(INFERENCE_PROTOCOLS))

_PROVIDER_ALIASES = {
    "primary": GOOGLE_ANTIGRAVITY,
    "provider": GOOGLE_ANTIGRAVITY,
    "antigravity": GOOGLE_ANTIGRAVITY,
    "google-antigravity": GOOGLE_ANTIGRAVITY,
    "google_antigravity": GOOGLE_ANTIGRAVITY,
    "ai-studio": GOOGLE_AI_STUDIO,
    "aistudio": GOOGLE_AI_STUDIO,
    "gemini": GOOGLE_AI_STUDIO,
    "google-ai-studio": GOOGLE_AI_STUDIO,
    "google_ai_studio": GOOGLE_AI_STUDIO,
    "grok": XAI,
    "xai-oauth": XAI,
    "xai_oauth": XAI,
    "x-ai": XAI,
    "xai": XAI,
    "xai-grok": XAI,
    "xai-api-key": XAI,
    "xai_api_key": XAI,
    "xai-console": XAI,
    "xai_console": XAI,
    "openai": OPENAI,
    "openai-api": OPENAI,
    "openai_api": OPENAI,
    "openai-platform": OPENAI,
    "openai_platform": OPENAI,
    "openai-api-key": OPENAI,
    "openai_api_key": OPENAI,
    "codex": OPENAI,
    "openai-codex": OPENAI,
    "openai_codex": OPENAI,
    "anthropic": ANTHROPIC,
    "claude": ANTHROPIC,
    "claude-code": ANTHROPIC,
    "claude_code": ANTHROPIC,
    "claude-platform": ANTHROPIC,
    "claude_platform": ANTHROPIC,
    "ollama": OLLAMA,
    "ollama-cloud": OLLAMA,
    "ollama_cloud": OLLAMA,
    "ollama-local": OLLAMA,
    "ollama_local": OLLAMA,
}

_PROVIDER_NAMES = {
    GOOGLE_ANTIGRAVITY: "Google Antigravity",
    GOOGLE_AI_STUDIO: "Google AI Studio",
    XAI: "Grok Build",
    OPENAI: "OpenAI",
    ANTHROPIC: "Anthropic",
    OLLAMA: "Ollama",
}

_CREDENTIAL_PROVIDER_NAMES = {
    GROK: "Grok Build",
    XAI_CONSOLE: "SpaceXAI Console",
    CODEX: "Codex",
    OPENAI_PLATFORM: "OpenAI Platform",
    CLAUDE_CODE: "Claude Code",
    CLAUDE_PLATFORM: "Claude Platform",
}


@dataclass(frozen=True)
class ProviderCapabilities:
    """Stable provider contract used by routing and the management API."""

    provider_id: str
    display_name: str
    credential_types: tuple[str, ...]
    model_prefixes: tuple[str, ...]
    supports_streaming: bool = True
    supports_tools: bool = True

    def supports_model(self, model_name: Optional[str]) -> bool:
        if not model_name or not self.model_prefixes:
            return True
        normalized = str(model_name).strip().lower().split("/")[-1]
        return normalized.startswith(self.model_prefixes)

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["credential_types"] = list(self.credential_types)
        value["model_prefixes"] = list(self.model_prefixes)
        return value


@dataclass(frozen=True)
class CredentialVariantCapabilities:
    """Server-authoritative operations for one console credential variant."""

    variant_id: str
    provider_id: str
    display_name: str
    credential_type: str
    operations: tuple[str, ...]
    inference_protocols: tuple[str, ...] = _COMMON_INFERENCE_PROTOCOLS

    def supports_operation(self, operation: Any) -> bool:
        return isinstance(operation, str) and operation in self.operations

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["operations"] = list(self.operations)
        value["inference_protocols"] = list(self.inference_protocols)
        return value


_PROVIDER_CAPABILITIES = {
    GOOGLE_ANTIGRAVITY: ProviderCapabilities(
        provider_id=GOOGLE_ANTIGRAVITY,
        display_name=_PROVIDER_NAMES[GOOGLE_ANTIGRAVITY],
        credential_types=("oauth",),
        model_prefixes=(),
    ),
    GOOGLE_AI_STUDIO: ProviderCapabilities(
        provider_id=GOOGLE_AI_STUDIO,
        display_name=_PROVIDER_NAMES[GOOGLE_AI_STUDIO],
        credential_types=("api_key",),
        model_prefixes=("gemini-", "gemma-"),
    ),
    XAI: ProviderCapabilities(
        provider_id=XAI,
        display_name=_PROVIDER_NAMES[XAI],
        credential_types=("oauth", "api_key"),
        model_prefixes=("grok-",),
    ),
    ANTHROPIC: ProviderCapabilities(
        provider_id=ANTHROPIC,
        display_name=_PROVIDER_NAMES[ANTHROPIC],
        credential_types=("oauth", "api_key"),
        model_prefixes=("claude-",),
    ),
    OLLAMA: ProviderCapabilities(
        provider_id=OLLAMA,
        display_name=_PROVIDER_NAMES[OLLAMA],
        credential_types=("connection",),
        model_prefixes=(),
    ),
    OPENAI: ProviderCapabilities(
        provider_id=OPENAI,
        display_name=_PROVIDER_NAMES[OPENAI],
        credential_types=("oauth", "api_key"),
        model_prefixes=(),
    ),
}

_CREDENTIAL_VARIANT_CAPABILITIES = {
    GOOGLE_ANTIGRAVITY: CredentialVariantCapabilities(
        variant_id=GOOGLE_ANTIGRAVITY,
        provider_id=GOOGLE_ANTIGRAVITY,
        display_name=_PROVIDER_NAMES[GOOGLE_ANTIGRAVITY],
        credential_type="oauth",
        operations=(
            *_COMMON_CREDENTIAL_OPERATIONS,
            "refresh",
            "reauthenticate",
            "quota",
            "credit_mode",
        ),
    ),
    GOOGLE_AI_STUDIO: CredentialVariantCapabilities(
        variant_id=GOOGLE_AI_STUDIO,
        provider_id=GOOGLE_AI_STUDIO,
        display_name=_PROVIDER_NAMES[GOOGLE_AI_STUDIO],
        credential_type="api_key",
        operations=_COMMON_CREDENTIAL_OPERATIONS,
    ),
    GROK: CredentialVariantCapabilities(
        variant_id=GROK,
        provider_id=XAI,
        display_name=_CREDENTIAL_PROVIDER_NAMES[GROK],
        credential_type="oauth",
        operations=(*_COMMON_CREDENTIAL_OPERATIONS, "refresh", "reauthenticate", "quota"),
    ),
    XAI_CONSOLE: CredentialVariantCapabilities(
        variant_id=XAI_CONSOLE,
        provider_id=XAI,
        display_name=_CREDENTIAL_PROVIDER_NAMES[XAI_CONSOLE],
        credential_type="api_key",
        operations=_COMMON_CREDENTIAL_OPERATIONS,
    ),
    CODEX: CredentialVariantCapabilities(
        variant_id=CODEX,
        provider_id=OPENAI,
        display_name=_CREDENTIAL_PROVIDER_NAMES[CODEX],
        credential_type="oauth",
        operations=(*_COMMON_CREDENTIAL_OPERATIONS, "refresh", "reauthenticate", "quota"),
    ),
    OPENAI_PLATFORM: CredentialVariantCapabilities(
        variant_id=OPENAI_PLATFORM,
        provider_id=OPENAI,
        display_name=_CREDENTIAL_PROVIDER_NAMES[OPENAI_PLATFORM],
        credential_type="api_key",
        operations=_COMMON_CREDENTIAL_OPERATIONS,
    ),
    CLAUDE_CODE: CredentialVariantCapabilities(
        variant_id=CLAUDE_CODE,
        provider_id=ANTHROPIC,
        display_name=_CREDENTIAL_PROVIDER_NAMES[CLAUDE_CODE],
        credential_type="oauth",
        operations=(*_COMMON_CREDENTIAL_OPERATIONS, "refresh", "reauthenticate", "quota"),
    ),
    CLAUDE_PLATFORM: CredentialVariantCapabilities(
        variant_id=CLAUDE_PLATFORM,
        provider_id=ANTHROPIC,
        display_name=_CREDENTIAL_PROVIDER_NAMES[CLAUDE_PLATFORM],
        credential_type="api_key",
        operations=_COMMON_CREDENTIAL_OPERATIONS,
    ),
    OLLAMA: CredentialVariantCapabilities(
        variant_id=OLLAMA,
        provider_id=OLLAMA,
        display_name=_PROVIDER_NAMES[OLLAMA],
        credential_type="connection",
        operations=_COMMON_CREDENTIAL_OPERATIONS,
    ),
}


def _short_fingerprint(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def antigravity_account_fingerprint(
    credential_data: Optional[Dict[str, Any]] = None,
    *,
    email: Any = None,
) -> str:
    """Create a stable, non-reversible Antigravity account identifier."""
    data = credential_data or {}
    normalized_email = (
        str(email or data.get("user_email") or data.get("email") or data.get("account_email") or "")
        .strip()
        .lower()
    )
    if normalized_email:
        return _short_fingerprint(normalized_email)

    token_identity = data.get("refresh_token") or data.get("token")
    if token_identity:
        return _short_fingerprint(token_identity)

    project_identity = data.get("project_id") or data.get("quota_project_id")
    return _short_fingerprint(project_identity)


def build_antigravity_credential_filename(
    credential_data: Optional[Dict[str, Any]] = None,
    *,
    email: Any = None,
) -> str:
    """Build the canonical filename for a Google Antigravity credential."""
    fingerprint = antigravity_account_fingerprint(credential_data, email=email)
    return f"google-antigravity-{fingerprint or 'unknown'}.json"


def canonicalize_antigravity_credential_filename(
    filename: Any,
    credential_data: Optional[Dict[str, Any]] = None,
    *,
    email: Any = None,
) -> str:
    """Normalize current, legacy, and imported Antigravity credential names."""
    data = credential_data or {}
    fingerprint = antigravity_account_fingerprint(data, email=email)
    if fingerprint:
        return f"google-antigravity-{fingerprint}.json"

    basename = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if basename.startswith("google-antigravity-") and basename.endswith(".json"):
        suffix = basename[len("google-antigravity-") : -5]
        if len(suffix) == 16 and all(character in "0123456789abcdef" for character in suffix):
            return basename
    return build_antigravity_credential_filename(data)


def normalize_provider_id(value: Any) -> str:
    """Normalize a provider identifier to its stable internal value."""
    normalized = str(value or "").strip().lower().replace(" ", "-")
    return _PROVIDER_ALIASES.get(normalized, normalized.replace("-", "_"))


def get_credential_provider(credential_data: Optional[Dict[str, Any]]) -> str:
    """Return the provider for new and legacy credential payloads."""
    data = credential_data or {}
    explicit = data.get("provider") or data.get("provider_id")
    if explicit:
        return normalize_provider_id(explicit)
    if data.get("credential_type") == "api_key" and data.get("api_key"):
        return GOOGLE_AI_STUDIO
    return GOOGLE_ANTIGRAVITY


def get_provider_routing_id(provider_id: Any) -> str:
    """Return the routing provider shared by one user-facing provider product."""
    normalized = str(provider_id or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {CLAUDE_CODE, CLAUDE_PLATFORM}:
        return ANTHROPIC
    if normalized in {CODEX, OPENAI_PLATFORM}:
        return OPENAI
    if normalized in {GROK, XAI_CONSOLE}:
        return XAI
    return normalize_provider_id(normalized)


def get_provider_display_name(provider_id: Any) -> str:
    normalized = str(provider_id or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in _CREDENTIAL_PROVIDER_NAMES:
        return _CREDENTIAL_PROVIDER_NAMES[normalized]
    routing_provider = get_provider_routing_id(normalized)
    return _PROVIDER_NAMES.get(routing_provider, str(provider_id or "Provider"))


def get_credential_provider_variant(credential_data: Optional[Dict[str, Any]]) -> str:
    """Return the user-facing provider variant for a credential payload."""
    data = credential_data or {}
    provider_id = get_credential_provider(data)
    if provider_id == ANTHROPIC:
        explicit_provider = (
            str(data.get("provider") or data.get("provider_id") or "")
            .strip()
            .lower()
            .replace("-", "_")
        )
        credential_type = str(data.get("credential_type") or "").strip().lower()
        if credential_type == "oauth" or explicit_provider in {"claude_code", "claude"}:
            return CLAUDE_CODE
        return CLAUDE_PLATFORM

    if provider_id != XAI:
        if provider_id != OPENAI:
            return provider_id

        explicit_provider = (
            str(data.get("provider") or data.get("provider_id") or "")
            .strip()
            .lower()
            .replace("-", "_")
        )
        credential_type = str(data.get("credential_type") or "").strip().lower()
        if credential_type == "oauth" or explicit_provider in {
            "codex",
            "openai_codex",
        }:
            return CODEX
        return OPENAI_PLATFORM

    explicit_provider = str(data.get("provider") or data.get("provider_id") or "").strip().lower()
    credential_type = str(data.get("credential_type") or "").strip().lower()
    if (
        credential_type == "api_key"
        or data.get("api_key")
        or explicit_provider
        in {
            "xai_console",
            "xai-console",
            "xai_api_key",
            "xai-api-key",
        }
    ):
        return XAI_CONSOLE
    return GROK


def get_credential_provider_display_name(
    credential_data: Optional[Dict[str, Any]],
) -> str:
    """Return the precise provider name shown for one credential."""
    variant = get_credential_provider_variant(credential_data)
    return _CREDENTIAL_PROVIDER_NAMES.get(variant, get_provider_display_name(variant))


def get_provider_capabilities(provider_id: Any) -> Optional[ProviderCapabilities]:
    """Return the declared contract for a known provider."""
    return _PROVIDER_CAPABILITIES.get(normalize_provider_id(provider_id))


def list_provider_capabilities() -> list[Dict[str, Any]]:
    """Return deterministic provider metadata for management clients."""
    return [
        _PROVIDER_CAPABILITIES[provider_id].to_dict()
        for provider_id in sorted(_PROVIDER_CAPABILITIES)
    ]


def get_credential_variant_capabilities(
    variant_id: Any,
) -> Optional[CredentialVariantCapabilities]:
    """Return the operation contract for one exact console variant."""
    normalized = str(variant_id or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _CREDENTIAL_VARIANT_CAPABILITIES.get(normalized)


def list_credential_variant_capabilities() -> list[Dict[str, Any]]:
    """Return deterministic credential variant metadata for management clients."""
    return [
        _CREDENTIAL_VARIANT_CAPABILITIES[variant_id].to_dict()
        for variant_id in sorted(_CREDENTIAL_VARIANT_CAPABILITIES)
    ]


def list_legacy_credential_variant_capabilities() -> list[Dict[str, Any]]:
    """Project the pre-R1 catalog shape for clients pinned to ``/api/providers``."""
    variants = []
    for item in list_credential_variant_capabilities():
        operations = _LEGACY_VARIANT_OPERATION_SNAPSHOT.get(
            item["variant_id"], frozenset(item["operations"])
        )
        variants.append(
            {
                "variant_id": item["variant_id"],
                "provider_id": item["provider_id"],
                "display_name": item["display_name"],
                "credential_type": item["credential_type"],
                "operations": [
                    operation for operation in _LEGACY_OPERATION_ORDER if operation in operations
                ],
            }
        )
    return variants


def credential_supports_operation(
    credential_data: Optional[Dict[str, Any]], operation: Any
) -> bool:
    """Fail closed unless the inferred credential variant declares the operation."""
    capabilities = get_credential_variant_capabilities(
        get_credential_provider_variant(credential_data)
    )
    return bool(capabilities and capabilities.supports_operation(operation))


def api_key_fingerprint(api_key: str) -> str:
    """Create a stable, non-reversible identifier for an API key."""
    return _short_fingerprint(api_key)


def get_static_credential_identity(credential_data: Dict[str, Any]) -> str:
    """Return a deduplication identity that does not require a network lookup."""
    provider_id = get_credential_provider(credential_data)
    if provider_id == OLLAMA:
        fingerprint = str(credential_data.get("connection_fingerprint") or "").strip()
        return f"{provider_id}:{fingerprint}" if fingerprint else ""
    if not is_api_key_credential(credential_data):
        return ""
    fingerprint = str(credential_data.get("key_fingerprint") or "").strip()
    if not fingerprint:
        fingerprint = api_key_fingerprint(str(credential_data.get("api_key") or ""))
    return f"{provider_id}:{fingerprint}" if fingerprint else ""


def is_api_key_credential(credential_data: Optional[Dict[str, Any]]) -> bool:
    data = credential_data or {}
    return bool(data.get("credential_type") == "api_key" and data.get("api_key"))


def get_declared_credential_models(
    credential_data: Optional[Dict[str, Any]],
) -> list[str]:
    """Return safe, normalized model IDs declared by a credential."""
    declared_models = (credential_data or {}).get("model_ids")
    if not isinstance(declared_models, list):
        return []

    normalized_models = []
    seen = set()
    for value in declared_models:
        if not isinstance(value, str):
            continue
        model_id = value.strip().removeprefix("models/")
        if (
            not model_id
            or len(model_id) > MAX_MODEL_ID_LENGTH
            or not model_id.isprintable()
            or model_id in seen
        ):
            continue
        seen.add(model_id)
        normalized_models.append(model_id)
        if len(normalized_models) >= MAX_DECLARED_MODELS:
            break
    return normalized_models


def credential_supports_model(
    credential_data: Dict[str, Any],
    model_name: Optional[str],
    required_provider: Optional[str] = None,
) -> bool:
    """Return whether a credential can serve the requested provider and model."""
    return (
        credential_model_support_level(
            credential_data,
            model_name,
            required_provider=required_provider,
        )
        > MODEL_SUPPORT_UNSUPPORTED
    )


def credential_model_support_level(
    credential_data: Dict[str, Any],
    model_name: Optional[str],
    required_provider: Optional[str] = None,
) -> int:
    """Return the strength of the evidence that a credential supports a model."""
    provider_id = get_credential_provider(credential_data)
    if required_provider and provider_id != normalize_provider_id(required_provider):
        return MODEL_SUPPORT_UNSUPPORTED
    capabilities = get_provider_capabilities(provider_id)
    if not capabilities or not capabilities.supports_model(model_name):
        return MODEL_SUPPORT_UNSUPPORTED
    declared_models = get_declared_credential_models(credential_data)
    if model_name and declared_models:
        normalized_model = str(model_name).strip().removeprefix("models/")
        return (
            MODEL_SUPPORT_DECLARED
            if normalized_model in declared_models
            else MODEL_SUPPORT_UNSUPPORTED
        )
    return MODEL_SUPPORT_INFERRED
