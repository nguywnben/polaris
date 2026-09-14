"""Behavior tests for credential routing."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.credential_manager import CredentialManager
from core.request_context import request_scope
from core.routing_coordination import RoutingCoordinationAdapter
from core.smart_routing import SmartCredentialRouter
from core.state_store import InMemoryStateStore


class FakeStorageAdapter:
    def __init__(self, states: Dict[str, Dict[str, Any]]) -> None:
        self.states = states
        self.state_reads = 0
        self.credential_reads = 0
        self.credentials = {
            filename: {"token": f"token-{filename}", "project_id": filename} for filename in states
        }

    async def get_all_credential_states(self, mode: str = "primary"):
        self.state_reads += 1
        return self.states

    async def get_credential(self, filename: str, mode: str = "primary"):
        self.credential_reads += 1
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


class SmartCredentialRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_acquisitions_do_not_serialize_coordination_io(self):
        storage = FakeStorageAdapter({"shared.json": credential_state()})
        router = SmartCredentialRouter(clock=lambda: 100.0)
        original = router._coordination.read_credential
        both_started = asyncio.Event()
        started = 0

        async def concurrent_read(*args, **kwargs):
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.25)
            return await original(*args, **kwargs)

        router._coordination.read_credential = concurrent_read
        first, second = await asyncio.gather(
            router.acquire(storage, mode="primary", model_name="model-a"),
            router.acquire(storage, mode="primary", model_name="model-a"),
        )

        self.assertEqual((first[0], second[0]), ("shared.json", "shared.json"))

    async def test_candidate_capacity_exhaustion_fails_closed_before_provider_reads(self):
        storage = FakeStorageAdapter(
            {f"credential-{index:03d}.json": credential_state() for index in range(101)}
        )
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result, decision = await router.acquire_with_decision(
            storage,
            mode="primary",
            model_name="model-a",
        )

        self.assertIsNone(result)
        self.assertIsNone(decision.selected_filename)
        self.assertEqual(decision.candidates, ())
        self.assertEqual(storage.state_reads, 1)

    async def test_shared_adapter_prevents_duplicate_exclusive_selection(self):
        now = [100.0]
        storage = FakeStorageAdapter({"exclusive.json": credential_state(max_concurrency=1)})
        store = InMemoryStateStore(clock=lambda: now[0])
        first = SmartCredentialRouter(
            clock=lambda: now[0],
            coordination=RoutingCoordinationAdapter(
                store, identifier_key=b"r" * 32, fencing_epoch=1
            ),
        )
        second = SmartCredentialRouter(
            clock=lambda: now[0],
            coordination=RoutingCoordinationAdapter(
                store, identifier_key=b"r" * 32, fencing_epoch=1
            ),
        )

        selected = await first.acquire(storage, mode="primary", model_name="model-a")
        duplicate = await second.acquire(storage, mode="primary", model_name="model-a")

        self.assertEqual(selected[0], "exclusive.json")
        self.assertIsNone(duplicate)

    async def test_shared_adapter_propagates_route_cooldown_between_routers(self):
        now = [100.0]
        storage = FakeStorageAdapter({"shared.json": credential_state()})
        store = InMemoryStateStore(clock=lambda: now[0])
        first = SmartCredentialRouter(
            clock=lambda: now[0],
            coordination=RoutingCoordinationAdapter(
                store, identifier_key=b"r" * 32, fencing_epoch=1
            ),
            base_backoff_seconds=5,
        )
        second = SmartCredentialRouter(
            clock=lambda: now[0],
            coordination=RoutingCoordinationAdapter(
                store, identifier_key=b"r" * 32, fencing_epoch=1
            ),
            base_backoff_seconds=5,
        )

        selected = await first.acquire(storage, mode="primary", model_name="model-a")
        await first.complete(
            selected[0],
            mode="primary",
            model_name="model-a",
            success=False,
            error_code=429,
        )

        self.assertIsNone(await second.acquire(storage, mode="primary", model_name="model-a"))

    async def test_decision_explains_selected_and_rejected_candidates(self):
        storage = FakeStorageAdapter(
            {
                "disabled.json": credential_state(disabled=True),
                "ready.json": credential_state(rotation_order=1),
            }
        )
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result, decision = await router.acquire_with_decision(
            storage,
            mode="primary",
            model_name="model-a",
        )

        self.assertEqual(result[0], "ready.json")
        self.assertEqual(decision.selected_filename, "ready.json")
        candidates = {candidate.filename: candidate for candidate in decision.candidates}
        self.assertEqual(candidates["disabled.json"].reason, "disabled")
        self.assertEqual(candidates["ready.json"].state, "selected")
        self.assertEqual(decision.reason, "healthy_candidate")

    async def test_recent_decision_limit_zero_returns_no_records(self):
        storage = FakeStorageAdapter({"ready.json": credential_state()})
        router = SmartCredentialRouter(clock=lambda: 100.0)
        await router.acquire(storage, mode="primary", model_name="model-a")

        self.assertEqual(await router.recent_decisions(limit=0), ())

    async def test_unavailable_decision_explains_cooldown_and_recovery_time(self):
        now = [100.0]
        storage = FakeStorageAdapter({"cooldown.json": credential_state()})
        router = SmartCredentialRouter(clock=lambda: now[0], base_backoff_seconds=5.0)
        selected = await router.acquire(storage, mode="primary", model_name="model-a")
        await router.complete(
            selected[0],
            mode="primary",
            model_name="model-a",
            success=False,
            error_code=429,
        )

        result, decision = await router.acquire_with_decision(
            storage,
            mode="primary",
            model_name="model-a",
        )

        self.assertIsNone(result)
        self.assertEqual(decision.reason, "cooldown_active")
        self.assertEqual(decision.retry_after_seconds, 5.0)
        self.assertEqual(decision.candidates[0].retry_after_seconds, 5.0)
        self.assertIn("Retry in 5 seconds", decision.message)

        public = decision.to_public_dict()
        self.assertEqual(public["candidate_reasons"], {"backoff_rate_limited": 1})
        self.assertNotIn("cooldown.json", repr(public))
        self.assertNotIn("request_id", public)

    async def test_failure_backoff_is_bounded_and_success_resets_health(self):
        now = [100.0]
        storage = FakeStorageAdapter({"route.json": credential_state()})
        router = SmartCredentialRouter(
            clock=lambda: now[0],
            base_backoff_seconds=2.0,
            max_backoff_seconds=5.0,
        )

        for expected_delay in (2.0, 4.0, 5.0):
            selected = await router.acquire(storage, mode="primary", model_name="model-a")
            await router.complete(
                selected[0],
                mode="primary",
                model_name="model-a",
                success=False,
                error_code=503,
            )
            outcome = await router._coordination.read_route_outcome(
                "primary", "route.json", "model-a"
            )
            self.assertEqual(outcome.retry_after_seconds, expected_delay)
            now[0] += expected_delay

        recovered = await router.acquire(storage, mode="primary", model_name="model-a")
        await router.complete(
            recovered[0],
            mode="primary",
            model_name="model-a",
            success=True,
        )
        outcome = await router._coordination.read_route_outcome("primary", "route.json", "model-a")
        self.assertEqual(outcome.failure_count, 0)
        self.assertEqual(outcome.retry_after_seconds, 0.0)

    async def test_concurrent_acquisitions_spread_across_available_credentials(self):
        now = [100.0]
        storage = FakeStorageAdapter(
            {
                "a.json": credential_state(rotation_order=0),
                "b.json": credential_state(rotation_order=1),
            }
        )
        router = SmartCredentialRouter(clock=lambda: now[0])

        first = await router.acquire(storage, mode="primary", model_name="model-a")
        second = await router.acquire(storage, mode="primary", model_name="model-a")

        self.assertEqual(first[0], "a.json")
        self.assertEqual(second[0], "b.json")
        self.assertEqual(storage.state_reads, 1)

    async def test_recent_failure_temporarily_routes_to_a_healthy_alternative(self):
        now = [100.0]
        storage = FakeStorageAdapter(
            {
                "a.json": credential_state(rotation_order=0),
                "b.json": credential_state(rotation_order=1),
            }
        )
        router = SmartCredentialRouter(
            clock=lambda: now[0],
            base_backoff_seconds=5.0,
            max_backoff_seconds=30.0,
        )

        first = await router.acquire(storage, mode="primary", model_name="model-a")
        await router.complete(first[0], mode="primary", success=False)
        second = await router.acquire(storage, mode="primary", model_name="model-a")

        self.assertEqual(first[0], "a.json")
        self.assertEqual(second[0], "b.json")

    async def test_client_request_failure_does_not_penalize_the_credential(self):
        storage = FakeStorageAdapter({"a.json": credential_state()})
        router = SmartCredentialRouter(clock=lambda: 100.0)

        first = await router.acquire(storage, mode="primary", model_name="model-a")
        await router.complete(
            first[0],
            mode="primary",
            success=False,
            model_name="model-a",
            error_code=400,
        )

        self.assertIsNotNone(await router.acquire(storage, mode="primary", model_name="model-a"))

    async def test_model_not_found_only_penalizes_the_affected_model(self):
        storage = FakeStorageAdapter({"a.json": credential_state()})
        router = SmartCredentialRouter(clock=lambda: 100.0)

        first = await router.acquire(storage, mode="primary", model_name="model-a")
        await router.complete(
            first[0],
            mode="primary",
            success=False,
            model_name="model-a",
            error_code=404,
        )

        self.assertIsNone(await router.acquire(storage, mode="primary", model_name="model-a"))
        self.assertIsNotNone(await router.acquire(storage, mode="primary", model_name="model-b"))

        _, decision = await router.acquire_with_decision(
            storage,
            mode="primary",
            model_name="model-a",
        )
        self.assertEqual(decision.candidates[0].reason, "backoff_model_unavailable")

    async def test_routing_decision_includes_the_request_context_id(self):
        storage = FakeStorageAdapter({"a.json": credential_state()})
        router = SmartCredentialRouter(clock=lambda: 100.0)

        with request_scope("request-123"):
            _, decision = await router.acquire_with_decision(
                storage,
                mode="primary",
                model_name="model-a",
            )

        self.assertEqual(decision.request_id, "request-123")

    async def test_all_credentials_in_backoff_are_not_reused_immediately(self):
        now = [100.0]
        storage = FakeStorageAdapter(
            {
                "a.json": credential_state(rotation_order=0),
                "b.json": credential_state(rotation_order=1),
            }
        )
        router = SmartCredentialRouter(
            clock=lambda: now[0],
            base_backoff_seconds=5.0,
            max_backoff_seconds=30.0,
        )

        first = await router.acquire(storage, mode="primary", model_name="model-a")
        await router.complete(first[0], mode="primary", success=False)
        second = await router.acquire(storage, mode="primary", model_name="model-a")
        await router.complete(second[0], mode="primary", success=False)

        self.assertIsNone(await router.acquire(storage, mode="primary", model_name="model-a"))

        now[0] = 105.0
        self.assertIsNotNone(await router.acquire(storage, mode="primary", model_name="model-a"))

    async def test_historical_call_count_does_not_flood_a_new_credential(self):
        storage = FakeStorageAdapter(
            {
                "established.json": credential_state(
                    call_count=1000, last_success=10.0, rotation_order=0
                ),
                "new.json": credential_state(call_count=0, last_success=20.0, rotation_order=1),
            }
        )
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result = await router.acquire(storage, mode="primary", model_name="model-a")

        self.assertEqual(result[0], "established.json")

    async def test_sequential_requests_rotate_by_last_selection(self):
        storage = FakeStorageAdapter(
            {
                "a.json": credential_state(last_success=0.0, rotation_order=0),
                "b.json": credential_state(last_success=0.0, rotation_order=1),
            }
        )
        now = [100.0]
        router = SmartCredentialRouter(clock=lambda: now[0])

        first = await router.acquire(storage, mode="primary", model_name="model-a")
        await router.complete(first[0], mode="primary", success=True)
        second = await router.acquire(storage, mode="primary", model_name="model-a")

        self.assertEqual((first[0], second[0]), ("a.json", "b.json"))
        self.assertEqual(storage.state_reads, 1)
        self.assertEqual(storage.credential_reads, 2)

    async def test_disabled_and_model_cooldown_credentials_are_not_selected(self):
        now = [100.0]
        storage = FakeStorageAdapter(
            {
                "disabled.json": credential_state(disabled=True),
                "cooldown.json": credential_state(
                    model_cooldowns={"model-a": 200.0}, rotation_order=1
                ),
                "ready.json": credential_state(rotation_order=2),
            }
        )
        router = SmartCredentialRouter(clock=lambda: now[0])

        result = await router.acquire(storage, mode="primary", model_name="model-a")

        self.assertEqual(result[0], "ready.json")

    async def test_preview_models_only_use_preview_compatible_credentials(self):
        storage = FakeStorageAdapter(
            {
                "standard.json": credential_state(preview=False, rotation_order=0),
                "preview.json": credential_state(preview=True, rotation_order=1),
            }
        )
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result = await router.acquire(storage, mode="code_assist", model_name="model-preview")

        self.assertEqual(result[0], "preview.json")

    async def test_provider_capabilities_exclude_ai_studio_for_claude(self):
        storage = FakeStorageAdapter(
            {
                "ai-studio.json": credential_state(rotation_order=0),
                "antigravity.json": credential_state(rotation_order=1),
            }
        )
        storage.credentials["ai-studio.json"] = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "example-key",
        }
        storage.credentials["antigravity.json"] = {
            "provider": "google_antigravity",
            "token": "access-token",
            "project_id": "project",
        }
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result = await router.acquire(storage, mode="primary", model_name="claude-sonnet-4-6")

        self.assertEqual(result[0], "antigravity.json")

    async def test_explicit_provider_filter_selects_matching_credential(self):
        storage = FakeStorageAdapter(
            {
                "antigravity.json": credential_state(rotation_order=0),
                "ai-studio.json": credential_state(rotation_order=1),
            }
        )
        storage.credentials["antigravity.json"]["provider"] = "google_antigravity"
        storage.credentials["ai-studio.json"] = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "example-key",
        }
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result = await router.acquire(
            storage,
            mode="primary",
            model_name="gemini-2.5-flash",
            provider_id="google_ai_studio",
        )

        self.assertEqual(result[0], "ai-studio.json")

    async def test_priority_strategy_prefers_the_configured_provider(self):
        storage = FakeStorageAdapter(
            {
                "antigravity.json": credential_state(rotation_order=0),
                "ai-studio.json": credential_state(rotation_order=1),
            }
        )
        storage.credentials["antigravity.json"]["provider"] = "google_antigravity"
        storage.credentials["ai-studio.json"] = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "example-key",
        }
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result = await router.acquire(
            storage,
            mode="primary",
            model_name="gemini-2.5-flash",
            routing_strategy="priority",
            preferred_provider="google_ai_studio",
        )

        self.assertEqual(result[0], "ai-studio.json")

    async def test_confirmed_model_support_precedes_unknown_provider_support(self):
        storage = FakeStorageAdapter(
            {
                "antigravity.json": credential_state(rotation_order=0),
                "ai-studio.json": credential_state(rotation_order=1),
            }
        )
        storage.credentials["antigravity.json"] = {
            "provider": "google_antigravity",
            "token": "access-token",
            "project_id": "project",
        }
        storage.credentials["ai-studio.json"] = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "example-key",
            "model_ids": ["gemini-2.5-flash"],
        }
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result = await router.acquire(
            storage,
            mode="primary",
            model_name="gemini-2.5-flash",
        )

        self.assertEqual(result[0], "ai-studio.json")

    async def test_priority_strategy_falls_back_when_preferred_provider_is_unavailable(self):
        storage = FakeStorageAdapter(
            {
                "antigravity.json": credential_state(rotation_order=0),
                "ai-studio.json": credential_state(disabled=True, rotation_order=1),
            }
        )
        storage.credentials["antigravity.json"]["provider"] = "google_antigravity"
        storage.credentials["ai-studio.json"] = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "example-key",
        }
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result = await router.acquire(
            storage,
            mode="primary",
            model_name="gemini-2.5-flash",
            routing_strategy="priority",
            preferred_provider="google_ai_studio",
        )

        self.assertEqual(result[0], "antigravity.json")

    async def test_model_candidate_selection_falls_back_to_the_next_routable_model(self):
        storage = FakeStorageAdapter(
            {
                "ai-studio.json": credential_state(rotation_order=0),
            }
        )
        storage.credentials["ai-studio.json"] = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "example-key",
        }
        router = SmartCredentialRouter(clock=lambda: 100.0)

        first = await router.acquire(
            storage,
            mode="primary",
            model_name="claude-sonnet-4-6",
        )
        second = await router.acquire(
            storage,
            mode="primary",
            model_name="gemini-2.5-flash",
        )

        self.assertIsNone(first)
        self.assertEqual(second[0], "ai-studio.json")

    async def test_provider_model_blacklist_keeps_other_provider_routes_available(self):
        storage = FakeStorageAdapter(
            {
                "ai-studio.json": credential_state(rotation_order=0),
                "antigravity.json": credential_state(rotation_order=1),
            }
        )
        storage.credentials["ai-studio.json"] = {
            "provider": "google_ai_studio",
            "credential_type": "api_key",
            "api_key": "example-key",
        }
        storage.credentials["antigravity.json"] = {
            "provider": "google_antigravity",
            "token": "access-token",
            "project_id": "project",
        }
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result = await router.acquire(
            storage,
            mode="primary",
            model_name="gemini-2.5-flash",
            excluded_provider_models={
                ("google_ai_studio", "gemini-2.5-flash"),
            },
        )

        self.assertEqual(result[0], "antigravity.json")

    async def test_credential_model_exclusion_keeps_other_accounts_available(self):
        storage = FakeStorageAdapter(
            {
                "first.json": credential_state(rotation_order=0),
                "second.json": credential_state(rotation_order=1),
            }
        )
        for filename in storage.credentials:
            storage.credentials[filename] = {
                "provider": "google_ai_studio",
                "credential_type": "api_key",
                "api_key": f"key-{filename}",
                "model_ids": ["gemini-2.5-flash"],
            }
        router = SmartCredentialRouter(clock=lambda: 100.0)

        result = await router.acquire(
            storage,
            mode="primary",
            model_name="gemini-2.5-flash",
            excluded_credential_models={
                ("first.json", "gemini-2.5-flash"),
            },
        )

        self.assertEqual(result[0], "second.json")


class CredentialSuccessLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_hints_are_batched_exactly_and_flushed_on_close(self):
        manager = CredentialManager()
        manager._initialized = True
        backend = Mock(record_success=AsyncMock())
        manager._storage_adapter = Mock(_backend=backend)
        manager._routing = Mock(complete=AsyncMock(), reset=AsyncMock())

        with patch(
            "core.credential_manager.time.monotonic",
            side_effect=[100.0, 100.0, 106.0, 106.0],
        ):
            for _ in range(4):
                await manager.record_api_call_result(
                    "credential.json",
                    True,
                    mode="primary",
                    model_name="model-a",
                )

        self.assertEqual(
            [call.kwargs["call_increment"] for call in backend.record_success.await_args_list],
            [1, 2],
        )
        self.assertEqual(manager._routing.complete.await_count, 4)

        await manager.close()

        self.assertEqual(
            [call.kwargs["call_increment"] for call in backend.record_success.await_args_list],
            [1, 2, 1],
        )


if __name__ == "__main__":
    unittest.main()
