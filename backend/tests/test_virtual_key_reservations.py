"""Reservation-aware virtual-key enforcement contracts for W3.7."""

from __future__ import annotations

import asyncio
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core import usage_stats
from core.state_store import InMemoryStateStore
from core.storage.usage_ledger_sqlite import SQLiteUsageLedgerRepository
from core.token_estimator import estimate_input_tokens
from core.usage_ledger import (
    BudgetReleaseResult,
    BudgetReservationDecision,
    UsageLedgerError,
)
from core.usage_ledger_service import UsageLedgerService
from core.virtual_keys import (
    RESERVATION_TTL_SECONDS,
    QuotaReservationHandle,
    VirtualKey,
    VirtualKeyManager,
)
from fastapi import HTTPException

from backend.tests.support import workspace_temp_directory


class VirtualKeyReservationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.ledger = AsyncMock()

        async def reserve(request):
            return BudgetReservationDecision(True, request.reservation_id)

        self.ledger.reserve_budget.side_effect = reserve
        self.ledger.release_reservation.return_value = BudgetReleaseResult(True)
        self.manager = VirtualKeyManager(
            state_store=InMemoryStateStore(), usage_ledger_service=self.ledger
        )
        self.manager._loaded = True

    @staticmethod
    def _key(**overrides) -> VirtualKey:
        values = {
            "id": "vk_reservation",
            "name": "reservation",
            "key_hash": "hash",
            "key_preview": "sk-polaris-vk-...tion",
            "enabled": True,
            "created_at": time.time(),
        }
        values.update(overrides)
        return VirtualKey(**values)

    @staticmethod
    def _body(*, model: str = "gpt-4o-mini", max_tokens: int = 20) -> dict:
        return {
            "model": model,
            "messages": [{"role": "user", "content": "Explain atomic reservations."}],
            "max_tokens": max_tokens,
        }

    async def test_concurrent_requests_cannot_cross_rpm_limit(self):
        record = self._key(rpm_limit=1)

        async def reserve(reservation_id: str):
            try:
                return await self.manager.enforce(
                    record,
                    requested_model="gpt-4o-mini",
                    request_body=self._body(),
                    reservation_id=reservation_id,
                    now=1000.0,
                )
            except HTTPException as exc:
                return exc

        results = await asyncio.gather(reserve("request-a"), reserve("request-b"))

        self.assertEqual(sum(isinstance(item, str) for item in results), 1)
        rejection = next(item for item in results if isinstance(item, HTTPException))
        self.assertEqual(rejection.status_code, 429)
        self.assertIn("Retry-After", rejection.headers)

    async def test_release_after_provider_failure_returns_reserved_capacity(self):
        record = self._key(rpm_limit=1)
        reservation_id = await self.manager.enforce(
            record,
            request_body=self._body(),
            reservation_id="failed-request",
            now=1000.0,
        )

        self.assertTrue(await self.manager.release_reservation(reservation_id, now=1001.0))
        replacement = await self.manager.enforce(
            record,
            request_body=self._body(),
            reservation_id="replacement-request",
            now=1001.0,
        )

        self.assertEqual(replacement, "replacement-request")

    async def test_tpm_is_reserved_from_estimated_input_and_output(self):
        record = self._key(tpm_limit=5)

        with self.assertRaises(HTTPException) as raised:
            await self.manager.enforce(
                record,
                request_body=self._body(max_tokens=20),
                reservation_id="too-large",
                now=1000.0,
            )

        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn("Token rate limit", raised.exception.detail)

    def test_estimator_excludes_openai_transport_and_generation_controls(self):
        prompt = {
            "messages": [{"role": "user", "content": "synthetic-evidence-operation-00080000"}]
        }
        request = {
            "model": "polaris-evidence-model",
            **prompt,
            "max_tokens": 4,
            "temperature": 0.0,
            "generationConfig": {"temperature": 0.0},
            "stream": False,
        }

        input_tokens, output_tokens = self.manager._estimate_tokens(request)

        self.assertEqual(input_tokens, estimate_input_tokens(prompt))
        self.assertEqual(output_tokens, 4)

    def test_estimator_unwraps_internal_protocol_request(self):
        prompt = {
            "contents": [{"role": "user", "parts": [{"text": "Explain durable reservations."}]}]
        }
        request = {
            "model": "gemini-enterprise",
            "request": {
                **prompt,
                "generationConfig": {"maxOutputTokens": 7, "temperature": 0.0},
            },
        }

        input_tokens, output_tokens = self.manager._estimate_tokens(request)

        self.assertEqual(input_tokens, estimate_input_tokens(prompt))
        self.assertEqual(output_tokens, 7)

    def test_estimator_keeps_unknown_payloads_conservative(self):
        request = {"custom_prompt": "opaque provider request"}

        input_tokens, output_tokens = self.manager._estimate_tokens(request)

        self.assertEqual(input_tokens, estimate_input_tokens(request))
        self.assertEqual(output_tokens, 4096)

    async def test_deny_unknown_pricing_fails_closed_for_hard_budget(self):
        record = self._key(budget_daily_usd=1.0, unknown_pricing_policy="deny")

        with self.assertRaises(HTTPException) as raised:
            await self.manager.enforce(
                record,
                requested_model="unpriced-enterprise-model",
                candidate_models=["unpriced-enterprise-model"],
                request_body=self._body(model="unpriced-enterprise-model"),
                reservation_id="unpriced-denied",
                now=1000.0,
            )

        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn("pricing", raised.exception.detail.lower())

    async def test_warn_unknown_pricing_warns_and_fails_closed_for_hard_budget(self):
        record = self._key(budget_daily_usd=1.0, unknown_pricing_policy="warn")
        with self.assertRaises(HTTPException) as raised:
            await self.manager.enforce(
                record,
                requested_model="unpriced-enterprise-model",
                candidate_models=["unpriced-enterprise-model"],
                request_body=self._body(model="unpriced-enterprise-model"),
                reservation_id="unpriced-warning",
                now=1000.0,
            )

        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn("pricing", raised.exception.detail.lower())
        self.ledger.reserve_budget.assert_not_awaited()

    async def test_rate_coordination_never_receives_cost_authority(self):
        record = self._key(rpm_limit=100)
        reservation_id = await self.manager.enforce(
            record,
            requested_model="gpt-4o-mini",
            request_body=self._body(),
            reservation_id="rate-only",
            now=1000.0,
        )

        state_request = self.manager._state_store._quota_records[reservation_id].request
        self.assertEqual(state_request.estimated_cost_usd, 0.0)
        self.assertIsNone(state_request.daily_budget_usd)
        self.assertIsNone(state_request.monthly_budget_usd)
        self.assertEqual(
            (state_request.daily_spend_usd, state_request.monthly_spend_usd), (0.0, 0.0)
        )

    async def test_fallback_pricing_reserves_cost_for_unknown_model(self):
        record = self._key(
            budget_daily_usd=0.000001,
            unknown_pricing_policy="fallback",
            fallback_price_usd_per_million=10.0,
        )

        async def reject(request):
            return BudgetReservationDecision(False, request.reservation_id, reason="daily_budget")

        self.ledger.reserve_budget.side_effect = reject
        with self.assertRaises(HTTPException) as raised:
            await self.manager.enforce(
                record,
                requested_model="unpriced-enterprise-model",
                candidate_models=["unpriced-enterprise-model"],
                request_body=self._body(model="unpriced-enterprise-model"),
                reservation_id="fallback-priced",
                now=1000.0,
            )

        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn("Budget", raised.exception.detail)

    async def test_hard_budget_fails_closed_when_ledger_is_unavailable(self):
        record = self._key(budget_daily_usd=10.0)
        self.ledger.reserve_budget.side_effect = UsageLedgerError("offline")
        with self.assertRaises(HTTPException) as raised:
            await self.manager.enforce(
                record,
                requested_model="gpt-4o-mini",
                request_body=self._body(),
                reservation_id="ledger-unavailable",
                now=1000.0,
            )

        self.assertEqual(raised.exception.status_code, 503)

    async def test_rate_rejection_releases_durable_budget_reservation(self):
        record = self._key(budget_daily_usd=10.0, tpm_limit=1)

        with self.assertRaises(HTTPException) as raised:
            await self.manager.enforce(
                record,
                requested_model="gpt-4o-mini",
                request_body=self._body(),
                now=1000.0,
            )

        self.assertEqual(raised.exception.status_code, 429)
        durable_request = self.ledger.reserve_budget.await_args.args[0]
        self.ledger.release_reservation.assert_awaited_once_with(
            durable_request.reservation_id,
            transitioned_at=1000.0,
        )

    async def test_release_finalizes_both_rate_and_durable_reservations(self):
        record = self._key(budget_daily_usd=10.0, rpm_limit=10)
        reservation_id = await self.manager.enforce(
            record,
            requested_model="gpt-4o-mini",
            request_body=self._body(),
            now=1000.0,
        )

        released = await self.manager.release_reservation(reservation_id, now=1001.0)

        self.assertTrue(released)
        self.ledger.release_reservation.assert_awaited_once_with(
            reservation_id,
            transitioned_at=1001.0,
        )

    async def test_failed_success_settlement_never_releases_durable_reservation(self):
        record = self._key(budget_daily_usd=10.0, rpm_limit=10)
        reservation_id = await self.manager.enforce(
            record,
            requested_model="gpt-4o-mini",
            request_body=self._body(),
            now=1000.0,
        )

        await self.manager.commit_reservation(
            reservation_id,
            actual_tokens=120,
            actual_cost_usd=0.25,
            durable_cost_recorded=False,
            now=1001.0,
        )
        released = await self.manager.release_reservation(reservation_id, now=1002.0)

        self.assertFalse(released)
        self.ledger.release_reservation.assert_not_awaited()
        self.assertTrue(self.manager.is_durable_reservation(reservation_id))

    async def test_expired_pending_settlement_ids_are_pruned_locally(self):
        record = self._key(budget_daily_usd=100.0, rpm_limit=10)
        first_id = await self.manager.enforce(
            record,
            requested_model="gpt-4o-mini",
            request_body=self._body(),
            now=1000.0,
        )
        await self.manager.commit_reservation(
            first_id,
            actual_tokens=120,
            actual_cost_usd=0.25,
            durable_cost_recorded=False,
            now=1001.0,
        )

        second_id = await self.manager.enforce(
            record,
            requested_model="gpt-4o-mini",
            request_body=self._body(),
            now=1000.0 + RESERVATION_TTL_SECONDS + 1,
        )

        self.assertNotIn(first_id, self.manager._durable_reservation_ids)
        self.assertNotIn(first_id, self.manager._pending_durable_settlement_ids)
        self.assertEqual(self.manager._durable_reservation_ids, {second_id})

    async def test_pending_settlement_tracking_has_a_hard_capacity_bound(self):
        record = self._key(budget_daily_usd=100.0, rpm_limit=10)
        first_id = await self.manager.enforce(
            record,
            requested_model="gpt-4o-mini",
            request_body=self._body(),
            now=1000.0,
        )
        await self.manager.commit_reservation(
            first_id,
            actual_tokens=120,
            actual_cost_usd=0.25,
            durable_cost_recorded=False,
            now=1001.0,
        )

        with (
            patch("core.virtual_keys.MAX_LOCAL_DURABLE_RESERVATIONS", 1),
            self.assertRaises(HTTPException) as raised,
        ):
            await self.manager.enforce(
                record,
                requested_model="gpt-4o-mini",
                request_body=self._body(),
                now=1002.0,
            )

        self.assertEqual(raised.exception.status_code, 503)

    async def test_committed_delivery_replay_skips_hot_quota_reservation(self):
        record = self._key(budget_daily_usd=100.0, rpm_limit=1)

        async def replay(request):
            return BudgetReservationDecision(
                True,
                request.reservation_id,
                idempotent=True,
                replayed=True,
            )

        self.ledger.reserve_budget.side_effect = replay
        handle = await self.manager.enforce(
            record,
            requested_model="gpt-4o-mini",
            request_body=self._body(),
            operation_id="operation-replay",
            now=1000.0,
        )

        self.assertIsInstance(handle, QuotaReservationHandle)
        self.assertTrue(handle.replayed)
        self.assertNotIn(str(handle), self.manager._durable_reservation_ids)
        self.assertFalse(self.manager._state_store._quota_records)

    async def test_pending_capacity_claim_is_atomic_across_concurrent_admission(self):
        record = self._key(budget_daily_usd=100.0, rpm_limit=10)
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        reserve_calls = 0

        async def reserve(request):
            nonlocal reserve_calls
            reserve_calls += 1
            if reserve_calls == 1:
                first_started.set()
                await release_first.wait()
            return BudgetReservationDecision(True, request.reservation_id)

        self.ledger.reserve_budget.side_effect = reserve
        with patch("core.virtual_keys.MAX_LOCAL_DURABLE_RESERVATIONS", 1):
            first = asyncio.create_task(
                self.manager.enforce(
                    record,
                    requested_model="gpt-4o-mini",
                    request_body=self._body(),
                    now=1000.0,
                )
            )
            await first_started.wait()
            with self.assertRaises(HTTPException) as raised:
                await self.manager.enforce(
                    record,
                    requested_model="gpt-4o-mini",
                    request_body=self._body(),
                    now=1001.0,
                )
            release_first.set()
            await first

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(reserve_calls, 1)

    async def test_durable_release_still_runs_when_rate_state_is_unavailable(self):
        record = self._key(budget_daily_usd=10.0, rpm_limit=10)
        reservation_id = await self.manager.enforce(
            record,
            requested_model="gpt-4o-mini",
            request_body=self._body(),
            now=1000.0,
        )
        self.manager._state_store.release_quota = AsyncMock(
            side_effect=RuntimeError("state unavailable")
        )

        with self.assertRaisesRegex(RuntimeError, "state unavailable"):
            await self.manager.release_reservation(reservation_id, now=1001.0)

        self.ledger.release_reservation.assert_awaited_once_with(
            reservation_id,
            transitioned_at=1001.0,
        )

    async def test_commit_replaces_estimate_with_actual_usage(self):
        record = self._key(tpm_limit=100)
        reservation_id = await self.manager.enforce(
            record,
            request_body=self._body(max_tokens=20),
            reservation_id="completed-request",
            now=1000.0,
        )

        result = await self.manager.commit_reservation(
            reservation_id,
            actual_tokens=150,
            actual_cost_usd=0.25,
            durable_cost_recorded=True,
            now=1001.0,
        )

        self.assertTrue(result.committed)
        self.assertTrue(result.overspent)


class DurableVirtualKeyRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = workspace_temp_directory()
        self.database_path = str(Path(self.temp_dir.__enter__()) / "usage.db")
        repository = SQLiteUsageLedgerRepository(self.database_path)
        await repository.initialize()
        self.service = UsageLedgerService(repository)
        self.services = [self.service]
        self.manager = VirtualKeyManager(
            state_store=InMemoryStateStore(),
            usage_ledger_service=self.service,
        )
        self.manager._loaded = True

    async def asyncTearDown(self):
        for service in reversed(self.services):
            await service.close()
        self.temp_dir.__exit__(None, None, None)

    async def test_committed_budget_survives_restart_without_double_counting(self):
        now = time.time()
        record = VirtualKeyReservationTests._key(
            id="vk_restart_budget",
            budget_daily_usd=0.15,
            unknown_pricing_policy="fallback",
            fallback_price_usd_per_million=1_000.0,
        )
        body = {
            "model": "private-unpriced-model",
            "messages": [],
            "max_tokens": 100,
        }
        reservation_id = await self.manager.enforce(
            record,
            requested_model="private-unpriced-model",
            request_body=body,
            now=now,
        )
        with patch.object(usage_stats, "get_usage_ledger_service", return_value=self.service):
            recorded = await usage_stats.record_call(
                "credential.json",
                provider="openai",
                token_usage={"input_tokens": 0, "output_tokens": 100, "total_tokens": 100},
                api_key_id=record.id,
                cost_override_usd=0.1,
                durable_reservation_id=reservation_id,
            )
        self.assertTrue(recorded)
        await self.manager.commit_reservation(
            reservation_id,
            actual_tokens=100,
            actual_cost_usd=0.1,
            durable_cost_recorded=True,
            now=now + 1,
        )

        restarted_repository = SQLiteUsageLedgerRepository(self.database_path)
        await restarted_repository.initialize()
        restarted_service = UsageLedgerService(restarted_repository)
        self.services.append(restarted_service)
        restarted_manager = VirtualKeyManager(
            state_store=InMemoryStateStore(),
            usage_ledger_service=restarted_service,
        )
        restarted_manager._loaded = True
        with self.assertRaises(HTTPException) as raised:
            await restarted_manager.enforce(
                record,
                requested_model="private-unpriced-model",
                request_body=body,
                now=now + 2,
            )

        self.assertEqual(raised.exception.status_code, 429)
        spend = await restarted_repository.get_spend(since=0, api_key_id=record.id)
        self.assertEqual((spend.calls, spend.cost_nanos), (1, 100_000_000))

    async def test_unsettled_success_estimate_survives_restart_fail_closed(self):
        now = time.time()
        record = VirtualKeyReservationTests._key(
            id="vk_unsettled_budget",
            budget_daily_usd=0.15,
            unknown_pricing_policy="fallback",
            fallback_price_usd_per_million=1_000.0,
        )
        body = {
            "model": "private-unpriced-model",
            "messages": [],
            "max_tokens": 100,
        }
        reservation_id = await self.manager.enforce(
            record,
            requested_model="private-unpriced-model",
            request_body=body,
            now=now,
        )
        await self.manager.commit_reservation(
            reservation_id,
            actual_tokens=100,
            actual_cost_usd=0.1,
            durable_cost_recorded=False,
            now=now + 1,
        )
        await self.manager.release_reservation(reservation_id, now=now + 2)

        restarted_repository = SQLiteUsageLedgerRepository(self.database_path)
        await restarted_repository.initialize()
        restarted_service = UsageLedgerService(restarted_repository)
        self.services.append(restarted_service)
        restarted_manager = VirtualKeyManager(
            state_store=InMemoryStateStore(),
            usage_ledger_service=restarted_service,
        )
        restarted_manager._loaded = True
        with self.assertRaises(HTTPException) as raised:
            await restarted_manager.enforce(
                record,
                requested_model="private-unpriced-model",
                request_body=body,
                now=now + 61,
            )

        self.assertEqual(raised.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
