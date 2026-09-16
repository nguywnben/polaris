"""Fresh subscription observations, including Muse's post-completion SSE frame."""

import asyncio
import json
import os
import sys
import time
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import extended_provider_runtime as runtime
from core.credential_pool_mutation import CredentialPoolRecord

ACCOUNT = {
    "provider": "muse_code",
    "credential_type": "oauth",
    "account_id": "a" * 64,
    "access_token": "fixture-oauth",
    "api_key": "fixture-inference",
}
USAGE = {
    "tier": "fixture-tier",
    "window": {"used_percent": 7, "window_duration_mins": 300, "resets_at": 1800000000},
    "weekly": {"used_percent": 3, "resets_at": 1800600000},
}
COMPLETE = {"type": "response.completed", "response": {"status": "completed", "output": []}}


class MuseQuotaStreamTests(unittest.IsolatedAsyncioTestCase):
    async def run_stream(self, events, observer, *, native=False, credential=None):
        wire = "".join("data: " + json.dumps(e) + "\n\n" for e in events).encode()

        @asynccontextmanager
        async def client(**kwargs):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(200, content=wire))
            ) as session:
                yield session

        with patch.object(runtime.http_client, "get_streaming_client", client):
            return [
                chunk
                async for chunk in runtime.stream_extended_request(
                    credential or ACCOUNT,
                    "muse-code/muse-spark-1.3" if credential is None else "muse-spark-1.3",
                    url="https://api.meta.ai/v1/responses",
                    body={},
                    headers={},
                    timeout=2,
                    native_responses=native,
                    subscription_observer=observer,
                )
            ]

    async def test_post_completion_quota_is_recorded_but_never_forwarded(self):
        for native in (False, True):
            observer = AsyncMock()
            chunks = await self.run_stream(
                [COMPLETE, {"type": "response.subscription_usage", "subscription": USAGE}],
                observer,
                native=native,
            )
            observer.assert_awaited_once()
            usage = observer.await_args.args[0]
            self.assertEqual(usage["window"]["used_percent"], 7)
            self.assertIsInstance(usage["observed_at"], int)
            self.assertNotIn("subscription", "".join(chunks))
            self.assertNotIn("fixture-tier", "".join(chunks))
            self.assertIn('"finishReason": "STOP"', chunks[-1])

    async def test_malformed_frame_does_not_erase_valid_observation_or_fail_response(self):
        observer = AsyncMock()
        await self.run_stream(
            [
                {"type": "response.subscription_usage", "subscription": USAGE},
                COMPLETE,
                {
                    "type": "response.subscription_usage",
                    "subscription": {"token": "not-for-storage"},
                },
            ],
            observer,
        )
        observer.assert_awaited_once()
        self.assertNotIn("token", str(observer.await_args))

    async def test_optional_observation_failure_does_not_retry_a_completed_generation(self):
        observer = AsyncMock(side_effect=RuntimeError("fixture-secret-must-not-be-logged"))
        with patch.object(runtime.log, "warning") as warning:
            chunks = await self.run_stream(
                [COMPLETE, {"type": "response.subscription_usage", "subscription": USAGE}], observer
            )
        self.assertIn('"finishReason": "STOP"', chunks[-1])
        observer.assert_awaited_once()
        warning.assert_called_once_with("Muse Code quota observation could not be saved.")

    async def test_no_quota_frame_does_not_invent_an_observation(self):
        observer = AsyncMock()
        await self.run_stream([COMPLETE], observer)
        observer.assert_not_awaited()

    async def test_cancellation_during_observation_propagates(self):
        observer = AsyncMock(side_effect=asyncio.CancelledError)
        with self.assertRaises(asyncio.CancelledError):
            await self.run_stream(
                [COMPLETE, {"type": "response.subscription_usage", "subscription": USAGE}], observer
            )

    async def test_only_last_valid_observation_is_saved_once(self):
        observer = AsyncMock()
        latest = {**USAGE, "window": {**USAGE["window"], "used_percent": 9}}
        await self.run_stream(
            [
                {"type": "response.subscription_usage", "subscription": USAGE},
                COMPLETE,
                {"type": "response.subscription_usage", "subscription": latest},
            ],
            observer,
        )
        observer.assert_awaited_once()
        self.assertEqual(observer.await_args.args[0]["window"]["used_percent"], 9)

    async def test_meta_api_key_response_does_not_record_subscription_usage(self):
        observer = AsyncMock()
        await self.run_stream(
            [{"type": "response.subscription_usage", "subscription": USAGE}, COMPLETE],
            observer,
            credential={"provider": "meta", "api_key": "fixture"},
        )
        observer.assert_not_awaited()


class MuseQuotaPersistenceTests(unittest.IsolatedAsyncioTestCase):
    def test_non_muse_and_incomplete_identity_have_no_observer(self):
        from core.muse_quota import subscription_observer

        for credential in (
            {"provider": "meta"},
            {"provider": "muse_code"},
            {**ACCOUNT, "access_token": ""},
        ):
            self.assertIsNone(subscription_observer("muse.json", credential))
        self.assertIsNone(subscription_observer("muse.json", ACCOUNT, mode="code_assist"))

    async def test_real_sqlite_updates_only_quota_and_preserves_disabled_state(self):
        from core.muse_quota import subscription_observer
        from core.storage.sqlite_manager import SQLiteManager

        from backend.tests.support import workspace_temp_directory

        with (
            workspace_temp_directory() as temp_dir,
            patch.dict(os.environ, {"CREDENTIALS_DIR": temp_dir}),
        ):
            storage = SQLiteManager()
            await storage.initialize()
            try:
                await storage.store_credential(
                    "muse.json", {**ACCOUNT, "credential_label": "Work"}, mode="primary"
                )
                await storage.update_credential_state(
                    "muse.json", {"disabled": True}, mode="primary"
                )
                with patch("core.muse_quota.get_storage_adapter", AsyncMock(return_value=storage)):
                    await subscription_observer("muse.json", ACCOUNT)(
                        {**USAGE, "observed_at": int(time.time())}
                    )
                saved = await storage.get_credential("muse.json", mode="primary")
                state = await storage.get_credential_state("muse.json", mode="primary")
                self.assertEqual(saved["subscription_usage"]["weekly"]["used_percent"], 3)
                self.assertEqual(saved["credential_label"], "Work")
                self.assertTrue(state["disabled"])
            finally:
                await storage.close()

    async def record(self, records, observation=None, source=None):
        from core.muse_quota import subscription_observer

        self.mutation = None

        async def mutate(mode, planner):
            self.assertEqual(mode, "primary")
            self.mutation = planner(tuple(records))
            return self.mutation.result

        storage = SimpleNamespace(mutate_credential_pool=mutate)
        with patch("core.muse_quota.get_storage_adapter", AsyncMock(return_value=storage)):
            await subscription_observer("muse.json", source or ACCOUNT)(
                observation or {**USAGE, "observed_at": int(time.time())}
            )

    async def test_patch_only_quota_preserves_concurrent_edits_and_does_not_store_extra_fields(
        self,
    ):
        current = {
            **ACCOUNT,
            "credential_label": "Renamed during generation",
            "api_key": "rotated-key",
        }
        await self.record([CredentialPoolRecord("muse.json", current, None, 0)])
        saved = self.mutation.writes[0].credential_data
        self.assertEqual(saved["credential_label"], current["credential_label"])
        self.assertEqual(saved["api_key"], "rotated-key")
        self.assertEqual(saved["subscription_usage"]["window"]["used_percent"], 7)
        self.assertEqual(self.mutation.deletes, ())

    async def test_deleted_or_reauthenticated_account_is_not_recreated_or_overwritten(self):
        for records in (
            [],
            [CredentialPoolRecord("muse.json", {**ACCOUNT, "account_id": "b" * 64}, None, 0)],
            [
                CredentialPoolRecord(
                    "muse.json", {**ACCOUNT, "access_token": "reauthorized"}, None, 0
                )
            ],
            [CredentialPoolRecord("muse.json", {**ACCOUNT, "provider": "meta"}, None, 0)],
        ):
            with self.subTest(records=len(records)):
                await self.record(records)
                self.assertEqual(self.mutation.writes, ())

    async def test_older_observation_cannot_replace_newer_one(self):
        now = int(time.time())
        current = {**ACCOUNT, "subscription_usage": {**USAGE, "observed_at": now}}
        await self.record(
            [CredentialPoolRecord("muse.json", current, None, 0)],
            {**USAGE, "observed_at": now - 2},
        )
        self.assertEqual(self.mutation.writes, ())

    async def test_invalid_metadata_does_not_touch_storage(self):
        for observation in ({"token": "not-for-storage"}, {**USAGE, "observed_at": True}):
            await self.record([], observation)
            self.assertIsNone(self.mutation)


class MuseQuotaDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_primary_nonstream_dispatch_binds_the_selected_credential(self):
        from core.api import primary

        from backend.tests.test_extended_provider_runtime import (
            CANONICAL,
            PrimaryExtendedIntegrationTests,
        )

        observer = AsyncMock()

        async def transport(*args, **kwargs):
            self.assertIs(kwargs.get("subscription_observer"), observer)
            yield CANONICAL

        stack, _ = PrimaryExtendedIntegrationTests().fixtures(
            [("muse-code/muse-spark-1.3", "muse.json", ACCOUNT)]
        )
        with (
            stack,
            patch.object(
                primary, "subscription_observer", return_value=observer, create=True
            ) as bind,
            patch.object(primary, "stream_extended_request", transport),
        ):
            response = await primary._non_stream_request_upstream(
                {"model": "muse-code/muse-spark-1.3"}
            )
            # Success accounting owns lease release; this fixture mocks that boundary.
            primary.record_api_call_success.assert_awaited_once()
        self.assertEqual(response.status_code, 200)
        bind.assert_called_once_with("muse.json", ACCOUNT)

    async def test_explicit_model_test_binds_the_freshly_prepared_credential(self):
        from core.models import CredentialModelTestRequest
        from core.panel import credentials

        model = "muse-code/muse-spark-1.3"
        fresh = {**ACCOUNT, "api_key": "new-key", "model_ids": [model]}
        storage = SimpleNamespace(
            get_credential=AsyncMock(return_value=ACCOUNT),
            update_credential_state=AsyncMock(),
        )
        observer = AsyncMock()
        with (
            patch.object(credentials, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(
                credentials, "_get_available_credential_models", AsyncMock(return_value=[model])
            ),
            patch.object(credentials, "_prepare_extended_oauth", AsyncMock(return_value=fresh)),
            patch.object(
                credentials, "subscription_observer", return_value=observer, create=True
            ) as bind,
            patch.object(
                credentials, "test_extended_credential", AsyncMock(return_value=httpx.Response(200))
            ) as test,
        ):
            response = await credentials.test_credential(
                "muse.json",
                CredentialModelTestRequest(model=model),
                mode="primary",
                _token="fixture",
            )
        self.assertEqual(response.status_code, 200)
        bind.assert_called_once_with("muse.json", fresh)
        test.assert_awaited_once_with(fresh, model, subscription_observer=observer)

    async def test_refresh_with_no_usage_does_not_return_old_usage_or_trigger_inference(self):
        from core import muse_code
        from core.panel import credentials

        stored = {**ACCOUNT, "subscription_usage": {**USAGE, "observed_at": int(time.time()) - 60}}
        fresh = {
            **ACCOUNT,
            "subscription_usage": None,
            "subscription_plan": "Muse Code Power Usage",
        }
        storage = SimpleNamespace(
            get_credential=AsyncMock(return_value=stored),
            store_credential=AsyncMock(return_value=True),
        )
        with (
            patch.object(credentials, "get_storage_adapter", AsyncMock(return_value=storage)),
            patch.object(muse_code, "refresh_credential", AsyncMock(return_value=fresh)) as refresh,
            patch.object(
                runtime,
                "stream_extended_request",
                side_effect=AssertionError("No implicit inference"),
            ) as inference,
            patch.object(
                credentials,
                "test_extended_credential",
                side_effect=AssertionError("No implicit test"),
            ) as test,
        ):
            response = await credentials.get_credential_quota(
                "muse.json", "fixture", mode="primary"
            )
        payload = json.loads(response.body)
        self.assertEqual(payload["quota_status"], "unavailable")
        self.assertEqual(payload["windows"], [])
        self.assertEqual(payload["plan"], "Muse Code Power Usage")
        refresh.assert_awaited_once_with(stored)
        inference.assert_not_called()
        test.assert_not_called()
