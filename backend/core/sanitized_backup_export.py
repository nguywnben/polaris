"""Build the non-restorable, secret-free backup inventory."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.configuration_schema import CONFIGURATION_FIELDS, ConfigValueType

SANITIZED_EXPORT_FORMAT = "polaris-sanitized-state"
SANITIZED_EXPORT_VERSION = 1

_INVENTORY_CONFIG_KEYS = {
    "quality_policy_document",
    "virtual_keys",
    "virtual_model_pool",
    "model_route_blacklist",
}


def _database_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_sanitized_inventory(database_path: Path, application_version: str) -> dict[str, Any]:
    """Project only non-secret values and aggregate counts from a trusted snapshot."""

    safe_types = {
        ConfigValueType.BOOLEAN,
        ConfigValueType.INTEGER,
        ConfigValueType.NUMBER,
        ConfigValueType.INTEGER_LIST,
    }
    safe_fields = {
        field.config_key: field
        for field in CONFIGURATION_FIELDS
        if field.config_key and not field.secret
    }
    selected_keys = sorted(set(safe_fields) | _INVENTORY_CONFIG_KEYS)
    placeholders = ",".join("?" for _ in selected_keys)

    with closing(sqlite3.connect(_database_uri(database_path), uri=True)) as connection:
        raw_config = {
            str(key): json.loads(value)
            for key, value in connection.execute(
                f"SELECT key, value FROM config WHERE key IN ({placeholders})",
                selected_keys,
            ).fetchall()
        }
        configuration: dict[str, Any] = {}
        for key, field in safe_fields.items():
            if key not in raw_config:
                continue
            value = raw_config[key]
            if field.value_type in safe_types:
                configuration[key] = value
            elif field.choices and type(value) is str and value in field.choices:
                configuration[key] = value

        virtual_keys = raw_config.get("virtual_keys")
        key_records = virtual_keys if isinstance(virtual_keys, list) else []
        quality = raw_config.get("quality_policy_document")
        pool = raw_config.get("virtual_model_pool")
        blacklist = raw_config.get("model_route_blacklist")
        role_counts = {
            str(role): int(count)
            for role, count in connection.execute(
                "SELECT role, COUNT(*) FROM management_role_bindings GROUP BY role"
            ).fetchall()
        }

        def count(table: str) -> int:
            return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])

        return {
            "format": SANITIZED_EXPORT_FORMAT,
            "version": SANITIZED_EXPORT_VERSION,
            "application_version": application_version,
            "created_at": _timestamp(),
            "backend": "sqlite",
            "configuration": configuration,
            "credentials": {
                "code_assist": count("credentials"),
                "primary": count("primary_credentials"),
            },
            "routing": {
                "virtual_pool_configured": isinstance(pool, dict),
                "selected_model_count": (
                    len(pool.get("selected_models", []))
                    if isinstance(pool, dict) and isinstance(pool.get("selected_models"), list)
                    else 0
                ),
                "blacklist_entry_count": (
                    len(blacklist.get("entries", []))
                    if isinstance(blacklist, dict) and isinstance(blacklist.get("entries"), list)
                    else 0
                ),
            },
            "quality_policy": {
                "configured": isinstance(quality, dict),
                "profile": (
                    quality.get("profile")
                    if isinstance(quality, dict)
                    and quality.get("profile") in {"quality", "balanced", "capacity", "custom"}
                    else None
                ),
                "revision": (
                    quality.get("revision")
                    if isinstance(quality, dict) and type(quality.get("revision")) is int
                    else None
                ),
            },
            "virtual_keys": {
                "configured": len(key_records),
                "enabled": sum(
                    1
                    for record in key_records
                    if isinstance(record, dict) and record.get("enabled") is True
                ),
            },
            "identity": {
                "identities": count("management_identities"),
                "roles": role_counts,
            },
            "records": {
                "audit_events": count("audit_events"),
                "request_traces": count("request_traces"),
                "usage_ledger": count("durable_usage_ledger"),
            },
            "excluded": [
                "access_secrets",
                "credential_payloads",
                "raw_logs",
                "restorable_key_material",
            ],
            "restorable": False,
        }
