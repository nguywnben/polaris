"""W3.6 contracts for versioned, scoped virtual API keys."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core import virtual_keys
from core.virtual_keys import (
    DEFAULT_INFERENCE_SCOPES,
    VIRTUAL_KEY_SCHEMA_VERSION,
    VirtualKey,
    VirtualKeyManager,
    hash_key,
)
from fastapi import HTTPException


class _FakeStorage:
    def __init__(self, records=None):
        self.config = {virtual_keys.VIRTUAL_KEYS_CONFIG_KEY: list(records or [])}
        self.write_count = 0

    async def get_config(self, key, default=None):
        return self.config.get(key, default)

    async def set_config(self, key, value):
        self.write_count += 1
        self.config[key] = value
        return True


class VirtualKeyScopeContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.storage = _FakeStorage()
        self.manager = VirtualKeyManager()
        patcher = patch(
            "core.storage_adapter.get_storage_adapter",
            new=AsyncMock(return_value=self.storage),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_new_key_defaults_to_inference_only_and_deny_unknown_pricing(self):
        record, _ = await self.manager.create_key("least-privilege")

        self.assertEqual(record["schema_version"], VIRTUAL_KEY_SCHEMA_VERSION)
        self.assertEqual(record["scopes"], list(DEFAULT_INFERENCE_SCOPES))
        self.assertNotIn("management:read", record["scopes"])
        self.assertNotIn("management:write", record["scopes"])
        self.assertEqual(record["unknown_pricing_policy"], "deny")
        self.assertIsNone(record["fallback_price_usd_per_million"])
        self.assertEqual(record["status"], "active")
        self.assertIsNone(record["last_used_at"])

    async def test_legacy_record_migrates_with_existing_inference_access(self):
        plaintext = "sk-polaris-vk-legacy-secret"
        self.storage.config[virtual_keys.VIRTUAL_KEYS_CONFIG_KEY] = [
            {
                "id": "vk_legacy",
                "name": "legacy",
                "key_hash": hash_key(plaintext),
                "key_preview": "sk-polaris-vk-...cret",
                "enabled": True,
                "created_at": 1.0,
                "allowed_models": ["gpt-*"],
            }
        ]

        record = await self.manager.verify(plaintext)

        self.assertIsNotNone(record)
        self.assertEqual(record.scopes, DEFAULT_INFERENCE_SCOPES)
        migrated = self.storage.config[virtual_keys.VIRTUAL_KEYS_CONFIG_KEY][0]
        self.assertEqual(migrated["schema_version"], VIRTUAL_KEY_SCHEMA_VERSION)
        self.assertEqual(migrated["scopes"], list(DEFAULT_INFERENCE_SCOPES))
        self.assertEqual(self.storage.write_count, 1)

    async def test_unknown_scope_in_versioned_storage_fails_closed(self):
        plaintext = "sk-polaris-vk-invalid-scope"
        self.storage.config[virtual_keys.VIRTUAL_KEYS_CONFIG_KEY] = [
            {
                "schema_version": VIRTUAL_KEY_SCHEMA_VERSION,
                "id": "vk_invalid",
                "name": "invalid",
                "key_hash": hash_key(plaintext),
                "key_preview": "sk-polaris-vk-...cope",
                "enabled": True,
                "created_at": 1.0,
                "scopes": ["inference:openai", "management:owner"],
                "unknown_pricing_policy": "deny",
                "allowed_models": [],
            }
        ]

        self.assertIsNone(await self.manager.verify(plaintext))

    async def test_unknown_schema_version_fails_closed(self):
        plaintext = "sk-polaris-vk-future-version"
        self.storage.config[virtual_keys.VIRTUAL_KEYS_CONFIG_KEY] = [
            {
                "schema_version": VIRTUAL_KEY_SCHEMA_VERSION + 1,
                "id": "vk_future",
                "name": "future",
                "key_hash": hash_key(plaintext),
                "key_preview": "sk-polaris-vk-...sion",
                "enabled": True,
                "created_at": 1.0,
                "scopes": list(DEFAULT_INFERENCE_SCOPES),
                "unknown_pricing_policy": "deny",
                "allowed_models": [],
            }
        ]

        self.assertIsNone(await self.manager.verify(plaintext))

    async def test_management_write_requires_management_read(self):
        with self.assertRaisesRegex(ValueError, "management:read"):
            await self.manager.create_key("invalid", scopes=["management:write"])

    async def test_fallback_pricing_requires_a_positive_bounded_price(self):
        with self.assertRaisesRegex(ValueError, "fallback price"):
            await self.manager.create_key("missing-price", unknown_pricing_policy="fallback")
        with self.assertRaisesRegex(ValueError, "fallback price"):
            await self.manager.create_key(
                "zero-price",
                unknown_pricing_policy="fallback",
                fallback_price_usd_per_million=0,
            )

        record, _ = await self.manager.create_key(
            "fallback",
            unknown_pricing_policy="fallback",
            fallback_price_usd_per_million=12.5,
        )
        self.assertEqual(record["fallback_price_usd_per_million"], 12.5)

    async def test_model_patterns_reject_character_classes_and_unbounded_lists(self):
        with self.assertRaisesRegex(ValueError, "model pattern"):
            await self.manager.create_key("unsafe-pattern", allowed_models=["gpt-[0-9]*"])
        with self.assertRaisesRegex(ValueError, "model patterns"):
            await self.manager.create_key(
                "too-many-patterns",
                allowed_models=[f"model-{index}" for index in range(65)],
            )

    async def test_protocol_scopes_are_enforced_before_existing_limits(self):
        record = VirtualKey(
            id="vk_scoped",
            name="scoped",
            key_hash="hash",
            key_preview="sk-polaris-vk-...oped",
            enabled=True,
            created_at=time.time(),
            scopes=("inference:openai",),
        )

        await self.manager.enforce(record, protocol="openai", requested_model="gpt-4o")
        with self.assertRaises(HTTPException) as context:
            await self.manager.enforce(
                record,
                protocol="anthropic",
                requested_model="claude-sonnet-4",
            )

        self.assertEqual(context.exception.status_code, 403)

    async def test_last_used_is_persisted_once_per_throttle_window(self):
        _, plaintext = await self.manager.create_key("used")
        record = await self.manager.verify(plaintext)
        writes_after_create = self.storage.write_count

        await self.manager.note_last_used(record, now=100.0)
        await self.manager.note_last_used(record, now=101.0)

        self.assertEqual(record.last_used_at, 100.0)
        self.assertEqual(self.storage.write_count, writes_after_create + 1)
        persisted = self.storage.config[virtual_keys.VIRTUAL_KEYS_CONFIG_KEY][0]
        self.assertEqual(persisted["last_used_at"], 100.0)


if __name__ == "__main__":
    unittest.main()
