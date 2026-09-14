"""Tests for the weighted / least-latency / lowest-cost routing strategies."""

from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path
from typing import Any, Dict

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.advanced_routing import provider_cost_rank, weighted_order
from core.smart_routing import SmartCredentialRouter


class FakeStorageAdapter:
    def __init__(self, states: Dict[str, Dict[str, Any]], providers: Dict[str, str] = None):
        self.states = states
        providers = providers or {}
        self.credentials = {
            filename: {
                "token": f"token-{filename}",
                "project_id": filename,
                "provider": providers.get(filename, ""),
            }
            for filename in states
        }

    async def get_all_credential_states(self, mode: str = "primary"):
        return self.states

    async def get_credential(self, filename: str, mode: str = "primary"):
        value = self.credentials.get(filename)
        return dict(value) if value else None


def credential_state(**overrides: Any) -> Dict[str, Any]:
    state = {
        "disabled": False,
        "error_codes": [],
        "last_success": 0.0,
        "model_cooldowns": {},
        "call_count": 0,
        "rotation_order": 0,
        "preview": False,
        "enable_credit": False,
    }
    state.update(overrides)
    return state


class WeightedOrderHelperTests(unittest.TestCase):
    def test_orders_every_item_exactly_once(self):
        rng = random.Random(42)
        items = [("a", 1.0), ("b", 2.0), ("c", 3.0)]
        ordered = weighted_order(items, rng=rng)
        self.assertEqual(sorted(ordered), ["a", "b", "c"])

    def test_extreme_weight_dominates_first_position(self):
        rng = random.Random(7)
        wins = 0
        for _ in range(50):
            ordered = weighted_order([("heavy", 1e9), ("light", 1e-6)], rng=rng)
            if ordered[0] == "heavy":
                wins += 1
        self.assertEqual(wins, 50)

    def test_non_positive_weights_are_clamped(self):
        ordered = weighted_order([("a", 0.0), ("b", -5.0)])
        self.assertEqual(sorted(ordered), ["a", "b"])


class ProviderCostRankTests(unittest.TestCase):
    def test_local_and_oauth_providers_rank_before_paid_platforms(self):
        self.assertLess(provider_cost_rank("ollama"), provider_cost_rank("google_ai_studio"))
        self.assertLess(
            provider_cost_rank("google_antigravity"), provider_cost_rank("openai_platform")
        )
        self.assertLess(provider_cost_rank("openai"), provider_cost_rank("claude_platform"))

    def test_unknown_provider_gets_middle_rank(self):
        self.assertEqual(provider_cost_rank("mystery"), 2)
        self.assertEqual(provider_cost_rank(None), 2)


class RoutingStrategyTests(unittest.IsolatedAsyncioTestCase):
    async def test_weighted_strategy_is_reproducible_with_seeded_routers(self):
        states = {
            "a.json": credential_state(weight=1.0),
            "b.json": credential_state(weight=2.0),
            "c.json": credential_state(weight=3.0),
        }
        first_router = SmartCredentialRouter(clock=lambda: 100.0, rng=random.Random(73))
        second_router = SmartCredentialRouter(clock=lambda: 100.0, rng=random.Random(73))

        first = await first_router.acquire(
            FakeStorageAdapter(states),
            mode="primary",
            model_name="model-a",
            routing_strategy="weighted",
        )
        second = await second_router.acquire(
            FakeStorageAdapter(states),
            mode="primary",
            model_name="model-a",
            routing_strategy="weighted",
        )

        self.assertEqual(first[0], second[0])

    async def test_least_latency_prefers_faster_credential(self):
        storage = FakeStorageAdapter(
            {
                "slow.json": credential_state(rotation_order=0),
                "fast.json": credential_state(rotation_order=1),
            }
        )
        router = SmartCredentialRouter(clock=lambda: 100.0)
        await router._coordination.record_route_outcome(
            "primary",
            "slow.json",
            "model-a",
            success=True,
            failure_kind="",
            retry_after_seconds=0,
            latency_ms=2_000.0,
        )
        await router._coordination.record_route_outcome(
            "primary",
            "fast.json",
            "model-a",
            success=True,
            failure_kind="",
            retry_after_seconds=0,
            latency_ms=150.0,
        )

        result = await router.acquire(
            storage, mode="primary", model_name="model-a", routing_strategy="least_latency"
        )
        self.assertEqual(result[0], "fast.json")

    async def test_least_latency_gives_unknown_credentials_a_chance(self):
        storage = FakeStorageAdapter(
            {
                "measured.json": credential_state(rotation_order=0),
                "new.json": credential_state(rotation_order=1),
            }
        )
        router = SmartCredentialRouter(clock=lambda: 100.0)
        await router._coordination.record_route_outcome(
            "primary",
            "measured.json",
            "model-a",
            success=True,
            failure_kind="",
            retry_after_seconds=0,
            latency_ms=900.0,
        )

        result = await router.acquire(
            storage, mode="primary", model_name="model-a", routing_strategy="least_latency"
        )
        # Unknown latency ranks first (bucket 0) so the new credential wins.
        self.assertEqual(result[0], "new.json")

    async def test_lowest_cost_prefers_oauth_over_paid_platform(self):
        storage = FakeStorageAdapter(
            {
                "paid.json": credential_state(rotation_order=0),
                "oauth.json": credential_state(rotation_order=1),
            },
            providers={
                "paid.json": "openai_platform",
                "oauth.json": "google_antigravity",
            },
        )
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result = await router.acquire(
            storage, mode="primary", model_name="model-a", routing_strategy="lowest_cost"
        )
        self.assertEqual(result[0], "oauth.json")

    async def test_weighted_strategy_respects_extreme_weights(self):
        storage = FakeStorageAdapter(
            {
                "heavy.json": credential_state(rotation_order=1, weight=1e9),
                "light.json": credential_state(rotation_order=0, weight=1e-6),
            }
        )
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result = await router.acquire(
            storage, mode="primary", model_name="model-a", routing_strategy="weighted"
        )
        self.assertEqual(result[0], "heavy.json")

    async def test_unknown_strategy_falls_back_to_balanced(self):
        storage = FakeStorageAdapter(
            {
                "a.json": credential_state(rotation_order=0),
                "b.json": credential_state(rotation_order=1),
            }
        )
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result, decision = await router.acquire_with_decision(
            storage, mode="primary", model_name="model-a", routing_strategy="turbo-mode"
        )
        self.assertEqual(result[0], "a.json")
        self.assertEqual(decision.routing_strategy, "balanced")

    async def test_latency_window_is_bounded(self):
        router = SmartCredentialRouter(clock=lambda: 100.0)
        for value in range(20):
            await router._coordination.record_route_outcome(
                "primary",
                "x.json",
                "model-a",
                success=True,
                failure_kind="",
                retry_after_seconds=0,
                latency_ms=float(value + 1),
            )
        outcome = await router._coordination.read_route_outcome("primary", "x.json", "model-a")
        self.assertEqual(len(outcome.latency_samples_ms), 10)


if __name__ == "__main__":
    unittest.main()
