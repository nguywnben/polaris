"""Tests for virtual API keys: CRUD, verification, and enforcement."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import asyncio

from core import virtual_keys
from core.state_store import InMemoryStateStore
from core.usage_ledger import BudgetReleaseResult, BudgetReservationDecision
from core.virtual_keys import (
    VirtualKey,
    VirtualKeyManager,
    extract_requested_model,
    hash_key,
)
from fastapi import HTTPException


class _FakeStorage:
    def __init__(self):
        self.config = {}
        self.reload_count = 0

    async def get_config(self, key, default=None):
        return self.config.get(key, default)

    async def set_config(self, key, value):
        self.config[key] = value
        return True

    async def reload_config_cache(self):
        self.reload_count += 1


class _FalseValuedQuotaStore(InMemoryStateStore):
    def __init__(self) -> None:
        super().__init__(clock=lambda: 1_000.0)
        self.reserve_epochs: list[int] = []
        self.commit_epochs: list[int] = []
        self.release_epochs: list[int] = []

    def __bool__(self) -> bool:
        return False

    async def reserve_quota(self, request):
        self.reserve_epochs.append(request.fencing_epoch)
        return await super().reserve_quota(request)

    async def commit_quota(self, request):
        self.commit_epochs.append(request.fencing_epoch)
        return await super().commit_quota(request)

    async def release_quota(self, reservation_id, **kwargs):
        self.release_epochs.append(kwargs.get("fencing_epoch"))
        return await super().release_quota(reservation_id, **kwargs)


def _patched_manager(storage: _FakeStorage) -> VirtualKeyManager:
    ledger = AsyncMock()

    async def reserve(request):
        return BudgetReservationDecision(True, request.reservation_id)

    ledger.reserve_budget.side_effect = reserve
    ledger.release_reservation.return_value = BudgetReleaseResult(True)
    manager = VirtualKeyManager(usage_ledger_service=ledger)
    manager._test_usage_ledger = ledger
    return manager


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


class VirtualKeyCrudTests(unittest.TestCase):
    def setUp(self):
        self.storage = _FakeStorage()
        self.manager = _patched_manager(self.storage)
        patcher = patch(
            "core.storage_adapter.get_storage_adapter",
            new=AsyncMock(return_value=self.storage),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_create_key_returns_plaintext_once_and_persists_hash_only(self):
        async def scenario():
            record, plaintext = await self.manager.create_key(
                "team-frontend", budget_daily_usd=5.0, rpm_limit=10
            )
            return record, plaintext

        record, plaintext = _run(scenario())
        self.assertTrue(plaintext.startswith("sk-polaris-vk-"))
        self.assertNotIn("key_hash", record)
        stored = self.storage.config[virtual_keys.VIRTUAL_KEYS_CONFIG_KEY]
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["key_hash"], hash_key(plaintext))
        self.assertNotIn(plaintext, str(stored))
        self.assertEqual(record["budget_daily_usd"], 5.0)
        self.assertEqual(record["rpm_limit"], 10)

    def test_create_key_requires_name(self):
        async def scenario():
            await self.manager.create_key("   ")

        with self.assertRaises(ValueError):
            _run(scenario())

    def test_update_and_delete_key(self):
        async def scenario():
            record, _ = await self.manager.create_key("temp-key")
            updated = await self.manager.update_key(
                record["id"],
                {"enabled": False, "budget_monthly_usd": 100, "allowed_models": ["gpt-*"]},
            )
            deleted = await self.manager.delete_key(record["id"])
            missing = await self.manager.update_key(record["id"], {"enabled": True})
            return updated, deleted, missing

        updated, deleted, missing = _run(scenario())
        self.assertFalse(updated["enabled"])
        self.assertEqual(updated["budget_monthly_usd"], 100.0)
        self.assertEqual(updated["allowed_models"], ["gpt-*"])
        self.assertTrue(deleted)
        self.assertIsNone(missing)

    def test_verify_matches_only_correct_secret(self):
        async def scenario():
            _, plaintext = await self.manager.create_key("verify-me")
            good = await self.manager.verify(plaintext)
            bad = await self.manager.verify("sk-polaris-vk-wrong")
            return good, bad

        good, bad = _run(scenario())
        self.assertIsNotNone(good)
        self.assertEqual(good.name, "verify-me")
        self.assertIsNone(bad)

    def test_keys_reload_from_storage(self):
        async def scenario():
            _, plaintext = await self.manager.create_key("persisted")
            fresh_manager = _patched_manager(self.storage)
            record = await fresh_manager.verify(plaintext)
            return record

        record = _run(scenario())
        self.assertIsNotNone(record)
        self.assertEqual(record.name, "persisted")

    def test_compression_restriction_round_trips_storage(self):
        async def scenario():
            created, plaintext = await self.manager.create_key("quality-restricted")
            updated = await self.manager.update_key(
                created["id"],
                {"compression_policy": "disabled"},
                expected_revision=created["revision"],
            )
            fresh_manager = _patched_manager(self.storage)
            reloaded = await fresh_manager.verify(plaintext)
            return updated, reloaded

        updated, reloaded = _run(scenario())
        self.assertEqual(updated["compression_policy"], "disabled")
        self.assertEqual(reloaded.compression_policy, "disabled")

    def test_cache_miss_forces_generation_refresh_before_rejecting_key(self):
        plaintext = "synthetic-cross-replica-token"
        record = VirtualKey(
            id="vk_cross_replica",
            name="cross-replica",
            key_hash=hash_key(plaintext),
            key_preview="synthetic...token",
            enabled=True,
            created_at=1_000.0,
        )
        self.storage.config[virtual_keys.VIRTUAL_KEYS_CONFIG_KEY] = [record.to_storage_dict()]
        self.manager._loaded = True
        self.manager._keys_by_hash = {}
        generation = AsyncMock()

        async def synchronize(invalidate, *, force=False):
            if force:
                await invalidate()
                return True
            return False

        generation.synchronize.side_effect = synchronize
        self.manager._generation = generation

        matched = _run(self.manager.verify(plaintext))

        self.assertIsNotNone(matched)
        self.assertEqual(matched.id, "vk_cross_replica")
        self.assertEqual(self.storage.reload_count, 1)
        self.assertEqual(generation.synchronize.await_count, 2)
        self.assertTrue(generation.synchronize.await_args_list[1].kwargs["force"])


class VirtualKeyEnforcementTests(unittest.TestCase):
    def _make_key(self, **kwargs) -> VirtualKey:
        defaults = dict(
            id="vk_test",
            name="test",
            key_hash="hash",
            key_preview="sk-polaris-vk-...abcd",
            enabled=True,
            created_at=time.time(),
        )
        defaults.update(kwargs)
        return VirtualKey(**defaults)

    def setUp(self):
        self.manager = _patched_manager(_FakeStorage())
        self.manager._loaded = True

    def test_disabled_key_rejected_401(self):
        record = self._make_key(enabled=False)
        with self.assertRaises(HTTPException) as ctx:
            _run(self.manager.enforce(record))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_expired_key_rejected_401(self):
        record = self._make_key(expires_at=time.time() - 10)
        with self.assertRaises(HTTPException) as ctx:
            _run(self.manager.enforce(record))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_model_allowlist_supports_glob_patterns(self):
        record = self._make_key(allowed_models=["gemini-2.5-*", "gpt-4o"])
        self.assertTrue(record.allows_model("gemini-2.5-flash"))
        self.assertTrue(record.allows_model("GPT-4O"))
        self.assertFalse(record.allows_model("claude-sonnet-4"))
        # Empty model (e.g. GET /v1/models) is allowed.
        self.assertTrue(record.allows_model(""))

    def test_disallowed_model_rejected_403(self):
        record = self._make_key(allowed_models=["gemini-*"])
        with self.assertRaises(HTTPException) as ctx:
            _run(self.manager.enforce(record, requested_model="gpt-4o"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_rpm_limit_enforced_with_retry_after(self):
        record = self._make_key(rpm_limit=2)

        async def scenario():
            await self.manager.enforce(record)
            await self.manager.enforce(record)
            await self.manager.enforce(record)

        with self.assertRaises(HTTPException) as ctx:
            _run(scenario())
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("Retry-After", ctx.exception.headers)

    def test_tpm_limit_enforced_from_active_reservations(self):
        record = self._make_key(tpm_limit=1000)

        async def scenario():
            body = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 600,
            }
            await self.manager.enforce(record, request_body=body)
            await self.manager.enforce(record, request_body=body)

        with self.assertRaises(HTTPException) as ctx:
            _run(scenario())
        self.assertEqual(ctx.exception.status_code, 429)

    def test_budget_exceeded_rejected_429(self):
        record = self._make_key(budget_daily_usd=1.0)

        async def reject(request):
            return BudgetReservationDecision(False, request.reservation_id, reason="daily_budget")

        self.manager._test_usage_ledger.reserve_budget.side_effect = reject
        with self.assertRaises(HTTPException) as ctx:
            _run(self.manager.enforce(record))
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("Budget exceeded", ctx.exception.detail)

    def test_budget_under_limit_allows_request(self):
        record = self._make_key(budget_daily_usd=10.0)
        _run(self.manager.enforce(record))

    def test_each_budget_admission_uses_atomic_ledger(self):
        record = self._make_key(budget_daily_usd=10.0)

        async def scenario():
            await self.manager.enforce(record)
            await self.manager.enforce(record)

        _run(scenario())
        self.assertEqual(self.manager._test_usage_ledger.reserve_budget.await_count, 2)

    def test_operation_identity_derives_same_durable_reservation_across_replicas(self):
        record = self._make_key(budget_daily_usd=10.0)
        other = _patched_manager(_FakeStorage())
        other._loaded = True

        async def scenario():
            first_id = await self.manager.enforce(
                record,
                operation_id="w4e-0123456789abcdef0123456789abcdef",
                now=1_000.0,
            )
            second_id = await other.enforce(
                record,
                operation_id="w4e-0123456789abcdef0123456789abcdef",
                now=1_000.0,
            )
            return first_id, second_id

        first_id, second_id = _run(scenario())
        self.assertEqual(first_id, second_id)
        self.assertRegex(first_id, r"^qrs_[0-9a-f]{32}$")

    def test_operation_identity_is_bound_to_virtual_key(self):
        first = self._make_key(budget_daily_usd=10.0)
        second = VirtualKey(**{**first.__dict__, "id": "vk_other"})
        other = _patched_manager(_FakeStorage())
        other._loaded = True

        async def scenario():
            return (
                await self.manager.enforce(first, operation_id="request-1", now=1_000.0),
                await other.enforce(second, operation_id="request-1", now=1_000.0),
            )

        first_id, second_id = _run(scenario())
        self.assertNotEqual(first_id, second_id)


class VirtualKeyCoordinationTests(unittest.TestCase):
    @staticmethod
    def _record() -> VirtualKey:
        return VirtualKey(
            id="vk_shared",
            name="shared",
            key_hash="hash",
            key_preview="preview",
            enabled=True,
            created_at=1_000.0,
            rpm_limit=1,
        )

    def test_false_valued_store_and_epoch_are_preserved_for_every_transition(self):
        store = _FalseValuedQuotaStore()
        manager = VirtualKeyManager(state_store=store, fencing_epoch=1)
        manager._loaded = True
        record = self._record()

        async def scenario():
            reservation = await manager.enforce(record, now=1_000.0)
            await manager.commit_reservation(
                reservation,
                actual_tokens=1,
                actual_cost_usd=0.0,
                durable_cost_recorded=False,
                now=1_000.1,
            )
            second = VirtualKeyManager(state_store=store, fencing_epoch=1)
            second._loaded = True
            other = VirtualKey(**{**record.__dict__, "id": "vk_other", "rpm_limit": 2})
            released = await second.enforce(other, now=1_000.2)
            await second.release_reservation(released, now=1_000.3)

        _run(scenario())
        self.assertIs(manager._state_store, store)
        self.assertEqual(store.reserve_epochs, [1, 1])
        self.assertEqual(store.commit_epochs, [1])
        self.assertEqual(store.release_epochs, [1])

    def test_two_managers_share_atomic_rate_admission(self):
        store = InMemoryStateStore(clock=lambda: 1_000.0)
        first = VirtualKeyManager(state_store=store, fencing_epoch=1)
        second = VirtualKeyManager(state_store=store, fencing_epoch=1)
        record = self._record()

        async def scenario():
            return await asyncio.gather(
                first.enforce(record, reservation_id="quota-first", now=1_000.0),
                second.enforce(record, reservation_id="quota-second", now=1_000.0),
                return_exceptions=True,
            )

        results = _run(scenario())
        self.assertEqual(sum(isinstance(result, str) for result in results), 1)
        rejection = next(result for result in results if isinstance(result, HTTPException))
        self.assertEqual(rejection.status_code, 429)

    def test_invalid_or_stale_epoch_fails_before_or_closes_admission(self):
        with self.assertRaises(ValueError):
            VirtualKeyManager(fencing_epoch=True)
        manager = VirtualKeyManager(
            state_store=InMemoryStateStore(clock=lambda: 1_000.0),
            fencing_epoch=2,
        )
        with self.assertRaises(HTTPException) as caught:
            _run(manager.enforce(self._record(), now=1_000.0))
        self.assertEqual(caught.exception.status_code, 503)


class ExtractRequestedModelTests(unittest.TestCase):
    def test_extracts_model_from_gemini_path(self):
        self.assertEqual(
            extract_requested_model("/v1beta/models/gemini-2.5-pro:generateContent", None),
            "gemini-2.5-pro",
        )

    def test_extracts_model_from_openai_body(self):
        self.assertEqual(
            extract_requested_model("/v1/chat/completions", {"model": "gpt-4o"}),
            "gpt-4o",
        )

    def test_returns_empty_for_unknown_shapes(self):
        self.assertEqual(extract_requested_model("/v1/models", None), "")
        self.assertEqual(extract_requested_model("/v1/chat/completions", "junk"), "")


if __name__ == "__main__":
    unittest.main()
