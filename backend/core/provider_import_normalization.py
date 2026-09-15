"""Normalize known OAuth export formats without contacting a provider.

JWT claims are unverified hints for account labels and expiry, never authorization.
Unknown formats remain the responsibility of the existing pool classifier.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from typing import Any

from core.provider_registry import EXTENDED_PROVIDERS, normalize_provider_id

_OAUTH_FAMILIES = {"openai", "anthropic", "xai"}
_OAUTH_VARIANTS = {"codex", "claude_code", "grok"}
_API_VARIANTS = {"openai_platform", "claude_platform", "xai_console"}
_SUPPORTED_FAMILIES = (
    _OAUTH_FAMILIES
    | {"google_antigravity", "google_ai_studio", "ollama"}
    | EXTENDED_PROVIDERS.keys()
)
_EXTENDED_IMPORT_FIELDS = {
    "groq": ("base_url",),
    "deepseek": ("base_url",),
    "mistral": ("base_url",),
    "cerebras": ("base_url",),
    "meta": ("base_url",),
    "kimi": ("base_url",),
    "cloudflare": ("base_url", "account_id"),
    "nvidia": ("base_url",),
    "poolside": ("base_url",),
    "kimchi": ("base_url",),
    "kilo": ("base_url", "organization_id"),
    "opencode": ("base_url", "plan"),
    "kiro": ("region", "profile_arn"),
}
_GROK_ACCOUNT = re.compile(
    r"^https://(?:auth\.x\.ai|api\.x\.ai|cli-chat-proxy\.grok\.com)"
    r"(?:::[^\s]{1,512})?/?$"
)
_TOKEN_FIELDS = {
    "access_token": ("access_token", "accessToken", "token", "key"),
    "refresh_token": ("refresh_token", "refreshToken"),
    "id_token": ("id_token", "idToken"),
}
_TEXT_FIELDS = {
    "account_id": ("account_id", "accountId"),
    "user_email": ("user_email", "email", "account_email"),
    "credential_label": ("credential_label",),
    "client_id": ("client_id",),
    "token_uri": ("token_uri", "token_endpoint"),
    "token_type": ("token_type", "tokenType"),
    "created_at": ("created_at",),
    "account_fingerprint": ("account_fingerprint",),
}


def _text(value: Any, *, token: bool = False) -> str:
    if not isinstance(value, str) or len(value) > (32768 if token else 2048):
        raise ValueError("Credential field has an invalid type or length.")
    if not value.isprintable() or (
        token and (not value.isascii() or any(c.isspace() for c in value))
    ):
        raise ValueError("Credential field contains unsupported characters.")
    return value.strip()


def _alias(source: dict, names: tuple[str, ...], *, token: bool = False) -> str:
    values = {
        _text(source[name], token=token) for name in names if source.get(name) not in (None, "")
    }
    if len(values) > 1:
        raise ValueError("Credential contains conflicting values for the same field.")
    return next(iter(values), "")


def _expiry(value: Any) -> str:
    try:
        if type(value) in (int, float):
            parsed = datetime.fromtimestamp(value / 1000 if value >= 1e12 else value, timezone.utc)
        elif isinstance(value, str) and len(value) <= 64:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            raise ValueError
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        raise ValueError("Credential expiration time is invalid.") from None


def _claims(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        return payload if isinstance(payload, dict) else {}
    except (ValueError, UnicodeError, RecursionError):
        return {}


def _native_source(data: dict) -> tuple[str | None, dict]:
    markers: list[tuple[str, Any]] = []
    if "tokens" in data:
        if data.get("OPENAI_API_KEY"):
            raise ValueError("Import one credential type at a time.")
        markers.append(("openai", data["tokens"]))
    if "claudeAiOauth" in data:
        markers.append(("anthropic", data["claudeAiOauth"]))
    accounts = [
        value
        for key, value in data.items()
        if isinstance(key, str) and _GROK_ACCOUNT.fullmatch(key)
    ]
    markers.extend(("xai", value) for value in accounts)
    if data.get("type") == "xai":
        if data.get("auth_kind") not in (None, "", "oauth"):
            raise ValueError("Unsupported xAI export authentication type.")
        markers.append(("xai", data))
    if len(markers) > 1:
        raise ValueError("Import one unambiguous provider account at a time.")
    if not markers:
        return None, data
    family, source = markers[0]
    if not isinstance(source, dict) or len(source) > 64:
        raise ValueError("OAuth token container is invalid or too large.")
    if source is not data and any(
        data.get(key) for names in _TOKEN_FIELDS.values() for key in names
    ):
        raise ValueError("Credential contains both nested and top-level tokens.")
    return family, source


def normalize_provider_import(data: Any, variant: str | None = None) -> dict:
    """Return canonical fields for a known native/canonical OAuth credential.

    ``variant`` can constrain an import to codex, claude_code, grok, their API-key
    variants, or a provider family. Omit it for mixed ZIP format detection.
    """
    if not isinstance(data, dict) or len(data) > 64:
        raise ValueError("Import one bounded credential object.")
    native_family, source = _native_source(data)
    expected = normalize_provider_id(variant) if variant else None
    declared = []
    declared_variants = set()
    containers = [data] if source is data else [data, source]
    for container in containers:
        for key in ("provider", "provider_id"):
            if container.get(key) is not None:
                identifier = _text(container[key]).lower().replace("-", "_")
                declared_variants.add(identifier)
                declared.append(normalize_provider_id(identifier))
    if any(provider not in _SUPPORTED_FAMILIES for provider in declared):
        raise ValueError("Credential provider is not supported by this pool.")
    if len(set(declared)) > 1:
        raise ValueError("Credential provider identifiers conflict.")
    family = native_family or (declared[0] if declared else expected)
    if any(value != family for value in declared) or (expected and family != expected):
        raise ValueError("Credential belongs to a different provider.")
    types = {
        _text(container["credential_type"]).lower()
        for container in containers
        if container.get("credential_type")
    }
    if len(types) > 1:
        raise ValueError("Credential authentication types conflict.")
    credential_type = next(iter(types), "")
    oauth_declared = bool(declared_variants & _OAUTH_VARIANTS)
    api_declared = bool(declared_variants & _API_VARIANTS)
    if (
        (oauth_declared and api_declared)
        or (oauth_declared and variant in _API_VARIANTS)
        or (api_declared and variant in _OAUTH_VARIANTS)
        or (oauth_declared and credential_type == "api_key")
        or (api_declared and (native_family or credential_type == "oauth"))
    ):
        raise ValueError("Credential provider product conflicts with its authentication type.")
    if native_family and credential_type not in ("", "oauth"):
        raise ValueError("Native OAuth data conflicts with the declared credential type.")
    if family in EXTENDED_PROVIDERS:
        from core.extended_provider_runtime import normalize_extended_credential

        if (
            native_family
            or credential_type not in ("", "api_key")
            or any(data.get(field) not in (None, "", "api_key") for field in ("type", "auth_kind"))
            or any(data.get(field) for names in _TOKEN_FIELDS.values() for field in names)
        ):
            raise ValueError("Import an API key credential for this provider.")
        # Import connection details only: archive-provided authorization state and
        # cached catalogs are not trustworthy and must not bypass discovery.
        clean = {"provider": family, "api_key": data.get("api_key")}
        for field in _EXTENDED_IMPORT_FIELDS[family]:
            if field in data:
                clean[field] = data[field]
        result = normalize_extended_credential(clean)
        result.pop("model_ids", None)
        if data.get("credential_label") not in (None, ""):
            label = _text(data["credential_label"])
            if len(label) > 128:
                raise ValueError("Credential label is too long.")
            result["credential_label"] = label
        return result
    if variant in _API_VARIANTS:
        if native_family or credential_type not in ("", "api_key"):
            raise ValueError("Import an API key credential for this provider.")
        return dict(data)
    if variant in _OAUTH_VARIANTS and (credential_type not in ("", "oauth") or data.get("api_key")):
        raise ValueError("Import an OAuth credential for this provider.")
    if family not in _OAUTH_FAMILIES or (not native_family and credential_type == "api_key"):
        return dict(data)
    if not native_family and not credential_type and variant not in _OAUTH_VARIANTS:
        return dict(data)
    if credential_type not in ("", "oauth") or any(
        container.get("api_key") for container in containers
    ):
        raise ValueError("Unsupported OAuth credential type.")

    result: dict[str, Any] = {"provider": family, "credential_type": "oauth"}
    for name, aliases in _TOKEN_FIELDS.items():
        value = _alias(source, aliases, token=True)
        if value:
            result[name] = value
    if not (result.get("access_token") or result.get("refresh_token")):
        raise ValueError("OAuth credential is missing an access or refresh token.")
    for name, aliases in _TEXT_FIELDS.items():
        value = _alias(source, aliases)
        if value:
            result[name] = value
    for name, limit in (("model_ids", 500), ("scopes", 64)):
        values = source.get(name, source.get("models") if name == "model_ids" else None)
        if values is not None:
            if not isinstance(values, list) or len(values) > limit:
                raise ValueError("Credential metadata list is invalid or too large.")
            result[name] = [_text(value) for value in values]

    claims = _claims(result.get("id_token") or result.get("access_token") or "")
    if family == "openai":
        account = claims.get("https://api.openai.com/auth")
        account_id = account.get("chatgpt_account_id") if isinstance(account, dict) else None
        if account_id:
            account_id = _text(account_id)
            if result.get("account_id") and result["account_id"] != account_id:
                raise ValueError("Credential account identity fields conflict.")
            result["account_id"] = account_id
    if not result.get("user_email") and claims.get("email"):
        result["user_email"] = _text(claims["email"])
    expiries = {
        _expiry(source[key])
        for key in ("expiry", "expired", "expiresAt", "expires_at")
        if source.get(key) not in (None, "")
    }
    if len(expiries) > 1:
        raise ValueError("Credential expiration fields conflict.")
    if expiries:
        result["expiry"] = expiries.pop()
    else:
        access_claims = _claims(result.get("access_token") or "")
        if access_claims.get("exp") is not None:
            result["expiry"] = _expiry(access_claims["exp"])
    return result
