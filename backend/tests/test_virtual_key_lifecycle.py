"""Safe virtual-key lifecycle contracts for W3.8."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.management_audit import classify_management_mutation
from core.panel.virtual_keys import (
    RevokeVirtualKeyRequest,
    RotateVirtualKeyRequest,
    UpdateVirtualKeyRequest,
)
from core.virtual_keys import VirtualKeyConflictError, VirtualKeyManager
from main import app


class _FakeStorage:
    def __init__(self) -> None:
        self.config = {}

    async def get_config(self, key, default=None):
        return self.config.get(key, default)

    async def set_config(self, key, value):
        self.config[key] = value
        return True


class VirtualKeyLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.storage = _FakeStorage()
        self.manager = VirtualKeyManager()
        self.storage_patch = patch(
            "core.storage_adapter.get_storage_adapter",
            new=AsyncMock(return_value=self.storage),
        )
        self.storage_patch.start()

    async def asyncTearDown(self) -> None:
        self.storage_patch.stop()

    async def test_rotate_replaces_secret_without_persisting_plaintext(self):
        created, old_plaintext = await self.manager.create_key("automation")

        rotated, new_plaintext = await self.manager.rotate_key(
            created["id"], expected_revision=created["revision"]
        )

        self.assertNotEqual(old_plaintext, new_plaintext)
        self.assertIsNone(await self.manager.verify(old_plaintext))
        self.assertEqual((await self.manager.verify(new_plaintext)).id, created["id"])
        self.assertEqual(rotated["revision"], created["revision"] + 1)
        self.assertNotIn(old_plaintext, str(self.storage.config))
        self.assertNotIn(new_plaintext, str(self.storage.config))

    async def test_concurrent_rotate_with_same_revision_has_one_winner(self):
        created, _ = await self.manager.create_key("automation")

        async def rotate():
            try:
                return await self.manager.rotate_key(
                    created["id"], expected_revision=created["revision"]
                )
            except VirtualKeyConflictError as exc:
                return exc

        outcomes = await asyncio.gather(rotate(), rotate())

        self.assertEqual(sum(isinstance(item, tuple) for item in outcomes), 1)
        self.assertEqual(sum(isinstance(item, VirtualKeyConflictError) for item in outcomes), 1)

    async def test_revoke_is_terminal_and_replay_safe(self):
        created, plaintext = await self.manager.create_key("automation")

        revoked = await self.manager.revoke_key(
            created["id"], expected_revision=created["revision"]
        )

        self.assertEqual(revoked["status"], "revoked")
        self.assertIsNotNone(revoked["revoked_at"])
        with self.assertRaises(VirtualKeyConflictError):
            await self.manager.revoke_key(created["id"], expected_revision=created["revision"])
        with self.assertRaises(ValueError):
            await self.manager.rotate_key(created["id"], expected_revision=revoked["revision"])
        record = await self.manager.verify(plaintext)
        with self.assertRaises(Exception) as raised:
            await self.manager.enforce(record)
        self.assertEqual(raised.exception.status_code, 401)

    async def test_stale_update_conflicts_without_mutating_record(self):
        created, _ = await self.manager.create_key("automation")
        updated = await self.manager.update_key(
            created["id"],
            {"name": "first-writer"},
            expected_revision=created["revision"],
        )

        with self.assertRaises(VirtualKeyConflictError):
            await self.manager.update_key(
                created["id"],
                {"name": "stale-writer"},
                expected_revision=created["revision"],
            )

        records = await self.manager.list_keys()
        self.assertEqual(records[0]["name"], "first-writer")
        self.assertEqual(records[0]["revision"], updated["revision"])

    async def test_plaintext_is_absent_from_all_non_reveal_records(self):
        created, plaintext = await self.manager.create_key("automation")
        listed = await self.manager.list_keys()
        with patch(
            "core.usage_stats.get_spend_since",
            new=AsyncMock(
                return_value={
                    "cost_usd": 0.0,
                    "total_tokens": 0,
                    "calls": 0,
                    "available": True,
                }
            ),
        ):
            usage = await self.manager.get_key_usage(created["id"])

        self.assertNotIn(plaintext, str(created))
        self.assertNotIn(plaintext, str(listed))
        self.assertNotIn(plaintext, str(usage))


class VirtualKeyLifecycleContractTests(unittest.TestCase):
    def test_openapi_preserves_legacy_update_and_requires_revision_for_new_mutations(self):
        schema = app.openapi()
        paths = schema["paths"]

        self.assertIn("/api/virtual-keys/{key_id}/rotate", paths)
        self.assertIn("/api/virtual-keys/{key_id}/revoke", paths)
        self.assertFalse(UpdateVirtualKeyRequest.model_fields["expected_revision"].is_required())
        self.assertEqual(
            RotateVirtualKeyRequest.model_fields["expected_revision"].is_required(), True
        )
        self.assertEqual(
            RevokeVirtualKeyRequest.model_fields["expected_revision"].is_required(), True
        )

    def test_rotate_and_revoke_are_classified_for_audit(self):
        rotate = classify_management_mutation("POST", "/api/virtual-keys/vk_example/rotate")
        revoke = classify_management_mutation("POST", "/api/virtual-keys/vk_example/revoke")

        self.assertEqual(rotate.action, "virtual_key.rotate")
        self.assertEqual(rotate.target_identifier, "vk_example")
        self.assertEqual(revoke.action, "virtual_key.revoke")
        self.assertEqual(revoke.target_identifier, "vk_example")


if __name__ == "__main__":
    unittest.main()
