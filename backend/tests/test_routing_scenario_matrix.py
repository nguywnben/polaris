"""Production routing scenario matrix for the five supported strategies."""

from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.smart_routing import SmartCredentialRouter


def credential_state(**overrides: Any) -> dict[str, Any]:
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


class ScenarioStorage:
    def __init__(
        self,
        states: dict[str, dict[str, Any]],
        credentials: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.states = states
        self.credentials = credentials or {
            filename: {
                "provider": "google_antigravity",
                "token": f"token-{filename}",
                "project_id": filename,
            }
            for filename in states
        }

    async def get_all_credential_states(self, mode: str = "primary"):
        return self.states

    async def get_credential(self, filename: str, mode: str = "primary"):
        credential = self.credentials.get(filename)
        return dict(credential) if credential else None


class RoutingScenarioMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def _select(
        self,
        *,
        strategy: str,
        states: dict[str, dict[str, Any]],
        credentials: dict[str, dict[str, Any]] | None = None,
        preferred_provider: str | None = None,
        latency: dict[str, float] | None = None,
        seed: int = 73,
    ) -> tuple[str, str]:
        router = SmartCredentialRouter(clock=lambda: 100.0, rng=random.Random(seed))
        for filename, latency_ms in (latency or {}).items():
            await router._coordination.record_route_outcome(
                "primary",
                filename,
                "model-a",
                success=True,
                failure_kind="",
                retry_after_seconds=0,
                latency_ms=latency_ms,
            )
        result, decision = await router.acquire_with_decision(
            ScenarioStorage(states, credentials),
            mode="primary",
            model_name="model-a",
            routing_strategy=strategy,
            preferred_provider=preferred_provider,
        )
        self.assertIsNotNone(result)
        self.assertEqual(decision.reason, "healthy_candidate")
        self.assertEqual(decision.routing_strategy, strategy)
        return result[0], decision.selected_provider

    async def test_supported_strategy_matrix_selects_expected_route(self):
        default_credentials = {
            "a.json": {
                "provider": "google_antigravity",
                "token": "token-a",
                "project_id": "a",
            },
            "b.json": {
                "provider": "openai",
                "credential_type": "oauth",
                "token": "token-b",
            },
            "c.json": {
                "provider": "openai_platform",
                "credential_type": "api_key",
                "api_key": "key-c",
            },
        }
        scenarios = (
            {
                "name": "balanced",
                "strategy": "balanced",
                "states": {
                    "a.json": credential_state(rotation_order=0),
                    "b.json": credential_state(rotation_order=1),
                },
                "credentials": default_credentials,
                "expected": "a.json",
            },
            {
                "name": "priority",
                "strategy": "priority",
                "states": {
                    "a.json": credential_state(rotation_order=0),
                    "b.json": credential_state(rotation_order=1),
                },
                "credentials": default_credentials,
                "preferred_provider": "openai",
                "expected": "b.json",
            },
            {
                "name": "weighted_seeded",
                "strategy": "weighted",
                "states": {
                    "a.json": credential_state(weight=1.0),
                    "b.json": credential_state(weight=4.0),
                    "c.json": credential_state(weight=2.0),
                },
                "credentials": default_credentials,
                "expected": "b.json",
            },
            {
                "name": "least_latency",
                "strategy": "least_latency",
                "states": {
                    "a.json": credential_state(),
                    "b.json": credential_state(),
                },
                "credentials": default_credentials,
                "latency": {"a.json": 900.0, "b.json": 120.0},
                "expected": "b.json",
            },
            {
                "name": "lowest_cost",
                "strategy": "lowest_cost",
                "states": {
                    "a.json": credential_state(),
                    "c.json": credential_state(),
                },
                "credentials": default_credentials,
                "expected": "a.json",
            },
        )

        for scenario in scenarios:
            with self.subTest(scenario=scenario["name"]):
                selected, _ = await self._select(
                    strategy=scenario["strategy"],
                    states=scenario["states"],
                    credentials=scenario["credentials"],
                    preferred_provider=scenario.get("preferred_provider"),
                    latency=scenario.get("latency"),
                )
                self.assertEqual(selected, scenario["expected"])

    async def test_transient_failure_falls_back_then_recovers_after_bound(self):
        now = [100.0]
        storage = ScenarioStorage(
            {
                "a.json": credential_state(rotation_order=0),
                "b.json": credential_state(rotation_order=1),
            }
        )
        router = SmartCredentialRouter(
            clock=lambda: now[0],
            base_backoff_seconds=2.0,
            max_backoff_seconds=5.0,
        )

        first = await router.acquire(storage, model_name="model-a")
        self.assertEqual(first[0], "a.json")
        await router.complete(
            first[0],
            mode="primary",
            model_name="model-a",
            success=False,
            error_code=429,
        )

        fallback = await router.acquire(storage, model_name="model-a")
        self.assertEqual(fallback[0], "b.json")
        await router.release(fallback[0], mode="primary")

        now[0] += 2.0
        single_route = ScenarioStorage({"a.json": credential_state()})
        recovered, decision = await router.acquire_with_decision(
            single_route,
            model_name="model-a",
        )
        self.assertEqual(recovered[0], "a.json")
        self.assertEqual(decision.reason, "healthy_candidate")

    async def test_unavailable_route_matrix_returns_actionable_reason(self):
        now = [100.0]
        scenarios = (
            (
                "no_credentials",
                ScenarioStorage({}),
                {},
            ),
            (
                "credentials_disabled",
                ScenarioStorage({"disabled.json": credential_state(disabled=True)}),
                {},
            ),
            (
                "cooldown_active",
                ScenarioStorage(
                    {"cooling.json": credential_state(model_cooldowns={"model-a": 104.0})}
                ),
                {},
            ),
            (
                "model_unavailable",
                ScenarioStorage({"google.json": credential_state()}),
                {"provider_id": "openai"},
            ),
        )

        for expected_reason, storage, options in scenarios:
            with self.subTest(reason=expected_reason):
                router = SmartCredentialRouter(clock=lambda: now[0])
                result, decision = await router.acquire_with_decision(
                    storage,
                    model_name="model-a",
                    **options,
                )
                self.assertIsNone(result)
                self.assertEqual(decision.reason, expected_reason)
                self.assertGreater(len(decision.message), 20)
                self.assertNotIn(".json", decision.message)


if __name__ == "__main__":
    unittest.main()
