"""Authoritative typed configuration contract for runtime and operator surfaces.

Specialized owners such as OIDC and telemetry still enforce cross-field security rules. This
module owns field names, scalar parsing, defaults, mutability, grouping, and safe public metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class ConfigurationError(ValueError):
    """Raised when configuration cannot be interpreted safely."""


class ConfigGroup(StrEnum):
    BASIC = "basic"
    ADVANCED = "advanced"
    EXPERIMENTAL = "experimental"


class ConfigValueType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    CSV = "csv"
    SPACE_LIST = "space_list"
    INTEGER_LIST = "integer_list"
    JSON = "json"


class ApplyMode(StrEnum):
    LIVE = "live"
    RESTART = "restart"
    READ_ONLY = "read_only"


@dataclass(frozen=True, slots=True)
class ConfigField:
    env_name: str
    config_key: str | None
    group: ConfigGroup
    value_type: ConfigValueType
    default: Any
    environment_default: str
    apply: ApplyMode
    surface: str
    secret: bool = False
    minimum: int | float | None = None
    maximum: int | float | None = None
    choices: tuple[str, ...] = ()
    allow_empty: bool = True
    max_length: int | None = None

    def parse(self, value: Any, *, label: str | None = None) -> Any:
        name = label or self.env_name
        if isinstance(value, str):
            value = value.strip()
        if value == "" and self.allow_empty:
            return "" if self.value_type is ConfigValueType.STRING else self.default

        try:
            parsed = self._parse_type(value)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            expected = self.value_type.value.replace("_", " ")
            raise ConfigurationError(f"{name} must be a valid {expected}.") from exc

        if self.choices and parsed not in self.choices:
            raise ConfigurationError(f"{name} must be one of: {', '.join(self.choices)}.")
        if (
            self.max_length is not None
            and isinstance(parsed, str)
            and len(parsed) > self.max_length
        ):
            raise ConfigurationError(f"{name} must contain at most {self.max_length} characters.")
        if self.minimum is not None and parsed < self.minimum:
            if self.maximum is not None:
                raise ConfigurationError(
                    f"{name} must be between {self.minimum:g} and {self.maximum:g}."
                )
            raise ConfigurationError(f"{name} must be at least {self.minimum:g}.")
        if self.maximum is not None and parsed > self.maximum:
            if self.minimum is not None:
                raise ConfigurationError(
                    f"{name} must be between {self.minimum:g} and {self.maximum:g}."
                )
            raise ConfigurationError(f"{name} must be at most {self.maximum:g}.")
        return parsed

    def _parse_type(self, value: Any) -> Any:
        if self.value_type is ConfigValueType.STRING:
            if not isinstance(value, str):
                raise TypeError
            if not self.allow_empty and not value:
                raise ValueError
            return value
        if self.value_type is ConfigValueType.BOOLEAN:
            if isinstance(value, bool):
                return value
            if not isinstance(value, str):
                raise TypeError
            normalized = value.lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
            raise ValueError
        if self.value_type is ConfigValueType.INTEGER:
            if isinstance(value, bool) or isinstance(value, float):
                raise TypeError
            return int(value)
        if self.value_type is ConfigValueType.NUMBER:
            if isinstance(value, bool):
                raise TypeError
            return float(value)
        if self.value_type is ConfigValueType.CSV:
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if not isinstance(value, str):
                raise TypeError
            return [item.strip() for item in value.split(",") if item.strip()]
        if self.value_type is ConfigValueType.SPACE_LIST:
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if not isinstance(value, str):
                raise TypeError
            return value.split()
        if self.value_type is ConfigValueType.INTEGER_LIST:
            items = value if isinstance(value, list) else str(value).split(",")
            return [int(item) for item in items if str(item).strip()]
        if self.value_type is ConfigValueType.JSON:
            if isinstance(value, (dict, list)):
                return value
            if not isinstance(value, str):
                raise TypeError
            return json.loads(value)
        raise TypeError


@dataclass(frozen=True, slots=True)
class ParsedEnvironment:
    values: dict[str, Any]
    warnings: tuple[str, ...]


# The declaration is intentionally independent from .env.example. Tests make drift fail loudly.
_DECLARATIONS = """
HOST=0.0.0.0
PORT=4283
HOST_PORT=4283
POLARIS_RUNTIME_MODE=standalone
POLARIS_REPLICA_COUNT=1
WORKERS=1
CORS_ORIGINS=
CORS_ORIGIN_REGEX=
API_KEY=
PANEL_PASSWORD=
SETUP_TOKEN=
PANEL_SESSION_TTL_SECONDS=86400
PANEL_COOKIE_SECURE=
PANEL_LOGIN_WINDOW_SECONDS=300
PANEL_LOGIN_MAX_ATTEMPTS=10
PANEL_LOGIN_MAX_TRACKED_CLIENTS=10000
MAX_REQUEST_BODY_MB=64
TRUST_PROXY_HEADERS=false
OIDC_ENABLED=false
OIDC_ISSUER=
OIDC_CLIENT_ID=
OIDC_CLIENT_SECRET=
OIDC_CLIENT_SECRET_FILE=
OIDC_REDIRECT_URI=
OIDC_SCOPES=openid profile email
OIDC_ID_TOKEN_SIGNING_ALGORITHMS=RS256
OIDC_SUBJECT_CLAIM=sub
OIDC_USERNAME_CLAIM=preferred_username
OIDC_DISPLAY_NAME_CLAIM=name
OIDC_EMAIL_CLAIM=email
OIDC_GROUPS_CLAIM=groups
OIDC_ROLE_MAPPINGS={}
OIDC_ALLOWED_ENDPOINT_ORIGINS=
OIDC_ALLOWED_PRIVATE_HOSTS=
OIDC_CONNECT_TIMEOUT_SECONDS=5
OIDC_READ_TIMEOUT_SECONDS=10
OIDC_MAX_RESPONSE_BYTES=262144
OIDC_JWKS_TTL_SECONDS=300
OIDC_START_WINDOW_SECONDS=300
OIDC_START_MAX_ATTEMPTS=20
OIDC_START_MAX_TRACKED_CLIENTS=10000
CREDENTIALS_DIR=./backend/data/creds
MONGODB_URI=
MONGODB_DATABASE=polaris
POSTGRESQL_URI=
CODE_ASSIST_CREDENTIALS_JSON={}
CREDENTIALS_JSON={}
CODE_ASSIST_CLIENT_ID=
CODE_ASSIST_CLIENT_SECRET=
ANTIGRAVITY_CLIENT_ID=
ANTIGRAVITY_CLIENT_SECRET=
ANTIGRAVITY_USER_AGENT=antigravity/cli/1.0.1 windows/amd64
ANTIGRAVITY_PAYLOAD_USER_AGENT=antigravity
PROXY=
CODE_ASSIST_ENDPOINT=https://cloudcode-pa.googleapis.com
ANTIGRAVITY_API_URL=https://daily-cloudcode-pa.googleapis.com
GOOGLE_AI_STUDIO_API_URL=https://generativelanguage.googleapis.com
XAI_API_URL=https://api.x.ai/v1
XAI_OAUTH_API_URL=https://cli-chat-proxy.grok.com/v1
XAI_OAUTH_ISSUER=https://auth.x.ai
XAI_CLIENT_ID=
XAI_USER_AGENT=grok-cli/polaris
OAUTH_URL=https://oauth2.googleapis.com
GOOGLE_APIS_URL=https://www.googleapis.com
RESOURCE_MANAGER_URL=https://cloudresourcemanager.googleapis.com
SERVICE_USAGE_URL=https://serviceusage.googleapis.com
OPENAI_API_URL=https://api.openai.com/v1
CODEX_API_URL=https://chatgpt.com/backend-api/codex
CODEX_USAGE_URL=https://chatgpt.com/backend-api/wham/usage
CODEX_AUTH_BASE=https://auth.openai.com
CODEX_CLIENT_ID=app_EMoamEEZ73f0CkXaXp7hrann
CODEX_USER_AGENT=codex_cli_rs/0.0.0 (Unknown 0; unknown)
ANTHROPIC_API_URL=https://api.anthropic.com/v1
CLAUDE_OAUTH_AUTHORIZE_URL=https://claude.ai/oauth/authorize
CLAUDE_OAUTH_TOKEN_URL=https://api.anthropic.com/v1/oauth/token
CLAUDE_CLIENT_ID=9d1c250a-e61b-44d9-88ed-5944d1962f5e
CLAUDE_USER_AGENT=claude-cli/polaris
CLAUDE_PLATFORM_API_URL=https://api.anthropic.com/v1
CLAUDE_PLATFORM_USER_AGENT=polaris/claude-platform
VERTEX_ANON_API_KEY=
AUTO_DISABLE=false
AUTO_DISABLE_ERROR_CODES=403
RETRY_429_ENABLED=true
RETRY_429_MAX_RETRIES=5
RETRY_429_INTERVAL=1
SWITCH_CREDENTIAL_ENABLED=true
ROUTING_STRATEGY=balanced
PREFERRED_PROVIDER=
UPSTREAM_TIMEOUT_SECONDS=300
RESPONSE_CACHE_ENABLED=false
RESPONSE_CACHE_TTL_SECONDS=300
RESPONSE_CACHE_MAX_ENTRIES=1000
GUARDRAILS_ENABLED=false
GUARDRAILS_PII_MASKING_ENABLED=true
GUARDRAILS_INJECTION_DETECTION_ENABLED=true
GUARDRAILS_BLOCKED_KEYWORDS=
PRICING_SYNC_ENABLED=true
PRICING_SYNC_INTERVAL_HOURS=24
COMPATIBILITY_MODE=false
RETURN_THOUGHTS_TO_FRONTEND=true
STREAM_TO_NONSTREAM=true
ANTI_TRUNCATION_MAX_ATTEMPTS=3
TOKEN_COMPRESSION_ENABLED=true
TOKEN_COMPRESSION_THRESHOLD=32000
TOKEN_COMPRESSION_TARGET=24000
TOKEN_COMPRESSION_MIN_RECENT_TURNS=4
LOG_LEVEL=info
LOG_MAX_MB=10
LOG_BACKUP_COUNT=3
PROMETHEUS_EXPORT_ENABLED=false
METRICS_TOKEN=
OTEL_EXPORT_ENABLED=false
OTEL_EXPORTER_OTLP_ENDPOINT=
OTEL_EXPORTER_OTLP_PROTOCOL=http/json
OTEL_EXPORT_INTERVAL_SECONDS=60
OTEL_EXPORTER_OTLP_HEADERS=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
LOG_FILE=./backend/data/logs/polaris.log
KEEPALIVE_URL=
KEEPALIVE_INTERVAL=60
""".strip()

_DECLARED_DEFAULTS = dict(line.split("=", 1) for line in _DECLARATIONS.splitlines())

_STORED_ENV_NAMES = frozenset(
    """CODE_ASSIST_ENDPOINT CREDENTIALS_DIR PROXY OAUTH_URL GOOGLE_APIS_URL
    RESOURCE_MANAGER_URL SERVICE_USAGE_URL ANTIGRAVITY_API_URL GOOGLE_AI_STUDIO_API_URL
    XAI_API_URL XAI_OAUTH_API_URL XAI_OAUTH_ISSUER XAI_CLIENT_ID XAI_USER_AGENT OPENAI_API_URL
    CODEX_API_URL CODEX_USAGE_URL CODEX_AUTH_BASE CODEX_CLIENT_ID CODEX_USER_AGENT
    ANTHROPIC_API_URL CLAUDE_OAUTH_AUTHORIZE_URL CLAUDE_OAUTH_TOKEN_URL CLAUDE_CLIENT_ID
    CLAUDE_USER_AGENT CLAUDE_PLATFORM_API_URL CLAUDE_PLATFORM_USER_AGENT
    CODE_ASSIST_CLIENT_ID CODE_ASSIST_CLIENT_SECRET ANTIGRAVITY_CLIENT_ID
    ANTIGRAVITY_CLIENT_SECRET ANTIGRAVITY_USER_AGENT ANTIGRAVITY_PAYLOAD_USER_AGENT AUTO_DISABLE
    AUTO_DISABLE_ERROR_CODES RETRY_429_MAX_RETRIES RETRY_429_ENABLED RETRY_429_INTERVAL
    ANTI_TRUNCATION_MAX_ATTEMPTS TOKEN_COMPRESSION_ENABLED TOKEN_COMPRESSION_THRESHOLD
    TOKEN_COMPRESSION_TARGET TOKEN_COMPRESSION_MIN_RECENT_TURNS RESPONSE_CACHE_ENABLED
    RESPONSE_CACHE_TTL_SECONDS RESPONSE_CACHE_MAX_ENTRIES GUARDRAILS_ENABLED
    GUARDRAILS_PII_MASKING_ENABLED GUARDRAILS_INJECTION_DETECTION_ENABLED
    GUARDRAILS_BLOCKED_KEYWORDS ROUTING_STRATEGY PREFERRED_PROVIDER UPSTREAM_TIMEOUT_SECONDS
    LOG_LEVEL LOG_MAX_MB LOG_BACKUP_COUNT COMPATIBILITY_MODE RETURN_THOUGHTS_TO_FRONTEND
    STREAM_TO_NONSTREAM SWITCH_CREDENTIAL_ENABLED HOST PORT API_KEY PANEL_PASSWORD KEEPALIVE_URL
    KEEPALIVE_INTERVAL""".split()
)

_CONFIG_KEY_OVERRIDES = {
    "AUTO_DISABLE": "auto_disable_enabled",
    "COMPATIBILITY_MODE": "compatibility_mode_enabled",
}

_BOOLEAN_NAMES = frozenset(
    """PANEL_COOKIE_SECURE TRUST_PROXY_HEADERS OIDC_ENABLED
    AUTO_DISABLE RETRY_429_ENABLED SWITCH_CREDENTIAL_ENABLED RESPONSE_CACHE_ENABLED
    GUARDRAILS_ENABLED GUARDRAILS_PII_MASKING_ENABLED GUARDRAILS_INJECTION_DETECTION_ENABLED
    COMPATIBILITY_MODE RETURN_THOUGHTS_TO_FRONTEND STREAM_TO_NONSTREAM
    TOKEN_COMPRESSION_ENABLED PRICING_SYNC_ENABLED PROMETHEUS_EXPORT_ENABLED
    OTEL_EXPORT_ENABLED""".split()
)
_INTEGER_NAMES = frozenset(
    """PORT HOST_PORT POLARIS_REPLICA_COUNT WORKERS
    PANEL_SESSION_TTL_SECONDS PANEL_LOGIN_WINDOW_SECONDS PANEL_LOGIN_MAX_ATTEMPTS
    PANEL_LOGIN_MAX_TRACKED_CLIENTS MAX_REQUEST_BODY_MB OIDC_CONNECT_TIMEOUT_SECONDS
    OIDC_READ_TIMEOUT_SECONDS OIDC_MAX_RESPONSE_BYTES OIDC_JWKS_TTL_SECONDS
    OIDC_START_WINDOW_SECONDS OIDC_START_MAX_ATTEMPTS OIDC_START_MAX_TRACKED_CLIENTS
    RETRY_429_MAX_RETRIES RESPONSE_CACHE_TTL_SECONDS RESPONSE_CACHE_MAX_ENTRIES
    ANTI_TRUNCATION_MAX_ATTEMPTS TOKEN_COMPRESSION_THRESHOLD TOKEN_COMPRESSION_TARGET
    TOKEN_COMPRESSION_MIN_RECENT_TURNS LOG_MAX_MB LOG_BACKUP_COUNT OTEL_EXPORT_INTERVAL_SECONDS
    PRICING_SYNC_INTERVAL_HOURS KEEPALIVE_INTERVAL""".split()
)
_NUMBER_NAMES = frozenset("RETRY_429_INTERVAL UPSTREAM_TIMEOUT_SECONDS".split())
_CSV_NAMES = frozenset(
    """CORS_ORIGINS OIDC_ID_TOKEN_SIGNING_ALGORITHMS
    OIDC_ALLOWED_ENDPOINT_ORIGINS OIDC_ALLOWED_PRIVATE_HOSTS GUARDRAILS_BLOCKED_KEYWORDS""".split()
)
_JSON_NAMES = frozenset("OIDC_ROLE_MAPPINGS CODE_ASSIST_CREDENTIALS_JSON CREDENTIALS_JSON".split())
_SECRET_NAMES = frozenset(
    """API_KEY PANEL_PASSWORD SETUP_TOKEN OIDC_CLIENT_SECRET OIDC_CLIENT_SECRET_FILE
    MONGODB_URI POSTGRESQL_URI CODE_ASSIST_CREDENTIALS_JSON
    CREDENTIALS_JSON CODE_ASSIST_CLIENT_SECRET ANTIGRAVITY_CLIENT_SECRET VERTEX_ANON_API_KEY
    METRICS_TOKEN OTEL_EXPORTER_OTLP_HEADERS LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY""".split()
)
_EXPERIMENTAL_NAMES = frozenset()
_BASIC_NAMES = frozenset(
    """HOST PORT HOST_PORT POLARIS_RUNTIME_MODE POLARIS_REPLICA_COUNT WORKERS CORS_ORIGINS
    CORS_ORIGIN_REGEX API_KEY PANEL_PASSWORD SETUP_TOKEN
    PANEL_SESSION_TTL_SECONDS PANEL_COOKIE_SECURE PANEL_LOGIN_WINDOW_SECONDS
    PANEL_LOGIN_MAX_ATTEMPTS PANEL_LOGIN_MAX_TRACKED_CLIENTS MAX_REQUEST_BODY_MB
    TRUST_PROXY_HEADERS CREDENTIALS_DIR PROXY ROUTING_STRATEGY PREFERRED_PROVIDER LOG_LEVEL""".split()
)
_PROVIDER_NAMES = frozenset(
    name
    for name in _DECLARED_DEFAULTS
    if name.startswith(("ANTIGRAVITY_", "XAI_", "CODEX_", "CLAUDE_", "CODE_ASSIST_"))
    or name
    in {
        "OAUTH_URL",
        "GOOGLE_APIS_URL",
        "RESOURCE_MANAGER_URL",
        "SERVICE_USAGE_URL",
        "GOOGLE_AI_STUDIO_API_URL",
        "OPENAI_API_URL",
        "ANTHROPIC_API_URL",
        "VERTEX_ANON_API_KEY",
    }
)
_QUALITY_NAMES = frozenset(
    name
    for name in _DECLARED_DEFAULTS
    if name.startswith(("TOKEN_COMPRESSION_", "RESPONSE_CACHE_", "GUARDRAILS_"))
    or name
    in {
        "COMPATIBILITY_MODE",
        "RETURN_THOUGHTS_TO_FRONTEND",
        "ANTI_TRUNCATION_MAX_ATTEMPTS",
    }
)

_LIMITS: dict[str, tuple[int | float | None, int | float | None]] = {
    "PORT": (1, 65_535),
    "HOST_PORT": (1, 65_535),
    "POLARIS_REPLICA_COUNT": (1, 1_000_000_000),
    "WORKERS": (1, 1_000_000_000),
    "PANEL_SESSION_TTL_SECONDS": (300, 2_592_000),
    "PANEL_LOGIN_WINDOW_SECONDS": (10, 3_600),
    "PANEL_LOGIN_MAX_ATTEMPTS": (1, 1_000),
    "PANEL_LOGIN_MAX_TRACKED_CLIENTS": (100, 1_000_000),
    "MAX_REQUEST_BODY_MB": (1, 512),
    "OIDC_CONNECT_TIMEOUT_SECONDS": (1, 30),
    "OIDC_READ_TIMEOUT_SECONDS": (1, 60),
    "OIDC_MAX_RESPONSE_BYTES": (4_096, 1_048_576),
    "OIDC_JWKS_TTL_SECONDS": (30, 3_600),
    "OIDC_START_WINDOW_SECONDS": (10, 3_600),
    "OIDC_START_MAX_ATTEMPTS": (1, 1_000),
    "OIDC_START_MAX_TRACKED_CLIENTS": (100, 1_000_000),
    "RETRY_429_MAX_RETRIES": (0, 100),
    "RETRY_429_INTERVAL": (0.01, 10),
    "UPSTREAM_TIMEOUT_SECONDS": (5, 900),
    "RESPONSE_CACHE_TTL_SECONDS": (1, 86_400),
    "RESPONSE_CACHE_MAX_ENTRIES": (1, 100_000),
    "ANTI_TRUNCATION_MAX_ATTEMPTS": (1, 10),
    "TOKEN_COMPRESSION_THRESHOLD": (128, 2_000_000),
    "TOKEN_COMPRESSION_TARGET": (64, 1_999_999),
    "TOKEN_COMPRESSION_MIN_RECENT_TURNS": (1, 50),
    "PRICING_SYNC_INTERVAL_HOURS": (1, 168),
    "LOG_MAX_MB": (1, 1_024),
    "LOG_BACKUP_COUNT": (1, 20),
    "OTEL_EXPORT_INTERVAL_SECONDS": (15, 300),
    "KEEPALIVE_INTERVAL": (5, 86_400),
}
_CHOICES = {
    "POLARIS_RUNTIME_MODE": ("standalone",),
    "ROUTING_STRATEGY": (
        "balanced",
        "priority",
        "weighted",
        "least_latency",
        "lowest_cost",
    ),
    "LOG_LEVEL": ("debug", "info", "warning", "error", "critical"),
    "OTEL_EXPORTER_OTLP_PROTOCOL": ("http/json",),
}


def _value_type(name: str) -> ConfigValueType:
    if name == "AUTO_DISABLE_ERROR_CODES":
        return ConfigValueType.INTEGER_LIST
    if name in _BOOLEAN_NAMES:
        return ConfigValueType.BOOLEAN
    if name in _INTEGER_NAMES:
        return ConfigValueType.INTEGER
    if name in _NUMBER_NAMES:
        return ConfigValueType.NUMBER
    if name in _CSV_NAMES:
        return ConfigValueType.CSV
    if name == "OIDC_SCOPES":
        return ConfigValueType.SPACE_LIST
    if name in _JSON_NAMES:
        return ConfigValueType.JSON
    return ConfigValueType.STRING


def _surface(name: str, config_key: str | None) -> str:
    if config_key is None:
        return "environment"
    if name in {"API_KEY", "PANEL_PASSWORD"}:
        return "access"
    if name in _PROVIDER_NAMES:
        return "provider"
    if name in _QUALITY_NAMES:
        return "quality"
    return "system"


def _build_field(name: str, raw_default: str) -> ConfigField:
    value_type = _value_type(name)
    config_key = None
    if name in _STORED_ENV_NAMES:
        config_key = _CONFIG_KEY_OVERRIDES.get(name, name.lower())
    group = (
        ConfigGroup.EXPERIMENTAL
        if name in _EXPERIMENTAL_NAMES
        else ConfigGroup.BASIC
        if name in _BASIC_NAMES
        else ConfigGroup.ADVANCED
    )
    minimum, maximum = _LIMITS.get(name, (None, None))
    apply = (
        ApplyMode.RESTART
        if config_key in {"host", "port", "credentials_dir"}
        else ApplyMode.READ_ONLY
        if config_key is None
        else ApplyMode.LIVE
    )
    provisional = ConfigField(
        env_name=name,
        config_key=config_key,
        group=group,
        value_type=value_type,
        default=raw_default,
        environment_default=raw_default,
        apply=apply,
        surface=_surface(name, config_key),
        secret=name in _SECRET_NAMES,
        minimum=minimum,
        maximum=maximum,
        choices=_CHOICES.get(name, ()),
        allow_empty=raw_default == "" or name in {"PREFERRED_PROVIDER", "KEEPALIVE_URL"},
        max_length=80 if name == "PREFERRED_PROVIDER" else None,
    )
    default = provisional.parse(raw_default) if raw_default else ""
    return ConfigField(
        env_name=name,
        config_key=config_key,
        group=group,
        value_type=value_type,
        default=default,
        environment_default=raw_default,
        apply=apply,
        surface=provisional.surface,
        secret=provisional.secret,
        minimum=minimum,
        maximum=maximum,
        choices=provisional.choices,
        allow_empty=provisional.allow_empty,
        max_length=provisional.max_length,
    )


CONFIGURATION_FIELDS = tuple(
    _build_field(name, default) for name, default in _DECLARED_DEFAULTS.items()
)
_BY_ENV = {field.env_name: field for field in CONFIGURATION_FIELDS}
_BY_CONFIG_KEY = {
    field.config_key: field for field in CONFIGURATION_FIELDS if field.config_key is not None
}


def field_by_environment(name: str) -> ConfigField | None:
    return _BY_ENV.get(name)


def field_by_config_key(key: str) -> ConfigField | None:
    return _BY_CONFIG_KEY.get(key)


def parse_environment(environ: Mapping[str, str]) -> ParsedEnvironment:
    """Validate known non-empty values and report likely misspelled Polaris controls."""
    values: dict[str, Any] = {}
    warnings = []
    for name, raw_value in environ.items():
        field = _BY_ENV.get(name)
        if field is None:
            if name.startswith("POLARIS_"):
                warnings.append(f"Unknown Polaris environment variable {name}; check its spelling.")
            continue
        if not isinstance(raw_value, str):
            raise ConfigurationError(f"{name} must be text in the process environment.")
        if not raw_value.strip() and field.allow_empty:
            continue
        values[name] = field.parse(raw_value)
    if {"TOKEN_COMPRESSION_THRESHOLD", "TOKEN_COMPRESSION_TARGET"} & values.keys():
        threshold = values.get(
            "TOKEN_COMPRESSION_THRESHOLD",
            _BY_ENV["TOKEN_COMPRESSION_THRESHOLD"].default,
        )
        target = values.get(
            "TOKEN_COMPRESSION_TARGET",
            _BY_ENV["TOKEN_COMPRESSION_TARGET"].default,
        )
        if target >= threshold:
            raise ConfigurationError(
                "TOKEN_COMPRESSION_TARGET must be lower than TOKEN_COMPRESSION_THRESHOLD."
            )
    return ParsedEnvironment(values, tuple(sorted(warnings)))


def validate_stored_configuration(values: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(values)
    for key, value in values.items():
        field = _BY_CONFIG_KEY.get(key)
        if field is not None:
            normalized[key] = field.parse(value, label=key)
    _validate_compression_relationship(normalized)
    return normalized


def validate_config_updates(
    updates: Mapping[str, Any],
    *,
    surface: str,
    current: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = {}
    for key, value in updates.items():
        field = _BY_CONFIG_KEY.get(key)
        if field is None or field.surface != surface:
            raise ConfigurationError(f"Unsupported {surface} configuration key: {key}.")
        normalized[key] = field.parse(value, label=key)
    combined = {**(current or {}), **normalized}
    _validate_compression_relationship(combined)
    return normalized


def _validate_compression_relationship(values: Mapping[str, Any]) -> None:
    keys = {"token_compression_threshold", "token_compression_target"}
    if not keys & values.keys():
        return
    threshold = values.get(
        "token_compression_threshold",
        _BY_CONFIG_KEY["token_compression_threshold"].default,
    )
    target = values.get(
        "token_compression_target",
        _BY_CONFIG_KEY["token_compression_target"].default,
    )
    if target >= threshold:
        raise ConfigurationError(
            "token_compression_target must be lower than token_compression_threshold."
        )


def settings_metadata(environ: Mapping[str, str]) -> list[dict[str, Any]]:
    """Return safe schema metadata; values and reusable secret defaults are never included."""
    metadata = []
    for field in CONFIGURATION_FIELDS:
        if field.config_key is None:
            continue
        item: dict[str, Any] = {
            "config_key": field.config_key,
            "environment": field.env_name,
            "group": field.group.value,
            "value_type": field.value_type.value,
            "apply": field.apply.value,
            "surface": field.surface,
            "environment_locked": bool(str(environ.get(field.env_name, "")).strip()),
            "secret": field.secret,
        }
        if not field.secret:
            item["default"] = field.default
        if field.minimum is not None:
            item["minimum"] = field.minimum
        if field.maximum is not None:
            item["maximum"] = field.maximum
        if field.choices:
            item["choices"] = list(field.choices)
        if field.max_length is not None:
            item["max_length"] = field.max_length
        metadata.append(item)
    return metadata


def environment_reference() -> str:
    """Generate the committed environment reference from the runtime schema."""
    lines = [
        "# Configuration Reference",
        "",
        "> Generated from `backend/core/configuration_schema.py`; do not edit manually.",
        "",
        "Values marked `secret` never expose a default through the Settings API.",
        "",
        "| Variable | Group | Type | Default | Apply | Settings owner |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for field in CONFIGURATION_FIELDS:
        default = (
            "(empty)"
            if field.secret or field.environment_default == ""
            else field.environment_default
        )
        default = default.replace("|", "\\|")
        lines.append(
            f"| `{field.env_name}` | {field.group.value} | {field.value_type.value}"
            f"{' / secret' if field.secret else ''} | `{default}` | {field.apply.value} |"
            f" {field.surface} |"
        )
    return "\n".join(lines) + "\n"
