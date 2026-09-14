"""Contracts for the authoritative typed configuration schema."""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config
from core.configuration_schema import (
    CONFIGURATION_FIELDS,
    ConfigGroup,
    ConfigurationError,
    environment_reference,
    field_by_config_key,
    parse_environment,
    settings_metadata,
    validate_config_updates,
)


def _example_variables() -> set[str]:
    pattern = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=")
    return {
        match.group(1)
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if (match := pattern.match(line))
    }


def _compose_environment_defaults() -> dict[str, str]:
    defaults: dict[str, str] = {}
    for filename in ("docker-compose.yml", "compose.advanced.yml"):
        compose = yaml.safe_load((ROOT / "deploy" / filename).read_text(encoding="utf-8"))
        environment = compose["services"]["app"]["environment"]
        for name, raw_value in environment.items():
            value = str(raw_value)
            interpolation = re.fullmatch(rf"\$\{{{re.escape(name)}:-(.*)}}", value)
            defaults[name] = interpolation.group(1) if interpolation else value
    return defaults


class ConfigurationSchemaTests(unittest.TestCase):
    def test_schema_covers_every_documented_environment_variable_exactly_once(self):
        names = [field.env_name for field in CONFIGURATION_FIELDS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), _example_variables())
        self.assertEqual(
            {field.group for field in CONFIGURATION_FIELDS},
            {ConfigGroup.BASIC, ConfigGroup.ADVANCED},
        )

    def test_compose_environment_defaults_match_schema(self):
        compose_defaults = _compose_environment_defaults()
        schema = {field.env_name: field for field in CONFIGURATION_FIELDS}
        self.assertTrue(compose_defaults)
        self.assertFalse(set(compose_defaults) - set(schema))
        for name, default in compose_defaults.items():
            self.assertEqual(
                schema[name].environment_default,
                default,
                f"Compose default for {name} drifted from the runtime schema",
            )

    def test_invalid_values_fail_with_actionable_field_names(self):
        cases = (
            ({"PORT": "zero"}, "PORT", "integer"),
            ({"PORT": "70000"}, "PORT", "between 1 and 65535"),
            ({"TRUST_PROXY_HEADERS": "sometimes"}, "TRUST_PROXY_HEADERS", "boolean"),
            ({"ROUTING_STRATEGY": "random"}, "ROUTING_STRATEGY", "one of"),
        )
        for environ, name, guidance in cases:
            with self.subTest(name=name, value=environ[name]):
                with self.assertRaises(ConfigurationError) as context:
                    parse_environment(environ)
                self.assertIn(name, str(context.exception))
                self.assertIn(guidance, str(context.exception))

    def test_unknown_polaris_variables_warn_without_rejecting_unrelated_process_variables(self):
        result = parse_environment({"POLARIS_TYPO_MODE": "true", "PATH": "ignored"})
        self.assertEqual(result.values, {})
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("POLARIS_TYPO_MODE", result.warnings[0])
        self.assertNotIn("PATH", result.warnings[0])

    def test_settings_metadata_is_schema_derived_and_does_not_expose_secret_defaults(self):
        metadata = settings_metadata({"HOST": "127.0.0.1", "PANEL_PASSWORD": "secret"})
        by_key = {item["config_key"]: item for item in metadata}
        self.assertEqual(by_key["host"]["apply"], "restart")
        self.assertTrue(by_key["host"]["environment_locked"])
        self.assertEqual(by_key["routing_strategy"]["group"], "basic")
        self.assertNotIn("default", by_key["panel_password"])
        self.assertNotIn("PANEL_PASSWORD=secret", repr(metadata))

    def test_console_updates_use_the_same_type_and_range_contract(self):
        normalized = validate_config_updates(
            {"port": 8080, "retry_429_interval": "0.5"},
            surface="system",
        )
        self.assertEqual(normalized, {"port": 8080, "retry_429_interval": 0.5})
        with self.assertRaisesRegex(ConfigurationError, "port.*between 1 and 65535"):
            validate_config_updates({"port": 0}, surface="system")

    def test_compression_relationship_is_checked_against_effective_defaults(self):
        with self.assertRaisesRegex(
            ConfigurationError,
            "TOKEN_COMPRESSION_TARGET.*lower than TOKEN_COMPRESSION_THRESHOLD",
        ):
            parse_environment({"TOKEN_COMPRESSION_THRESHOLD": "1000"})
        with self.assertRaisesRegex(
            ConfigurationError,
            "token_compression_target.*lower than token_compression_threshold",
        ):
            validate_config_updates(
                {"token_compression_target": 40_000},
                surface="quality",
            )

    def test_generated_reference_is_current(self):
        expected = (ROOT / "docs/reference/configuration.md").read_text(encoding="utf-8")
        self.assertEqual(expected, environment_reference())

    def test_config_mappings_are_derived_from_the_schema(self):
        expected = {
            field.env_name: field.config_key
            for field in CONFIGURATION_FIELDS
            if field.config_key is not None
        }
        self.assertEqual(config.ENV_MAPPINGS, expected)
        self.assertIsNotNone(field_by_config_key("host"))


class ConfigurationStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_environment_fails_before_storage_initialization(self):
        storage_factory = AsyncMock()
        with (
            patch.object(config, "_config_cache", {}),
            patch.object(config, "_config_initialized", False),
            patch.dict(os.environ, {"PORT": "invalid"}, clear=True),
            patch("core.storage_adapter.get_storage_adapter", new=storage_factory),
        ):
            with self.assertRaisesRegex(RuntimeError, "PORT.*integer"):
                await config.init_config()
        storage_factory.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
