"""Muse management routes are authenticated, manual and secret-free."""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.panel.providers import muse_code as panel
from core.utils import verify_panel_token


class MusePanelTests(unittest.IsolatedAsyncioTestCase):
    async def test_authorized_start_cancel_and_safe_failures(self):
        from core.device_authorization_coordination import DeviceAuthorizationError
        from core.muse_oauth import MuseOAuthError

        self.app.dependency_overrides[verify_panel_token] = lambda: "owner"
        with patch.object(
            panel, "start_login", AsyncMock(return_value={"status": "pending"})
        ) as start:
            response = await self.post("start", {"credential_label": "Work"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            start.assert_awaited_once_with("owner", credential_label="Work")
        with patch.object(panel, "cancel_login", AsyncMock(return_value={"status": "cancelled"})):
            self.assertEqual(
                (await self.post("cancel", {"flow_id": "muse_code_" + "a" * 43})).status_code, 200
            )
        for error, status in (
            (MuseOAuthError("An active Muse Code subscription is required.", 403), 403),
            (DeviceAuthorizationError(), 409),
        ):
            with patch.object(panel, "start_login", AsyncMock(side_effect=error)):
                response = await self.post("start", {})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.headers["cache-control"], "no-store")

    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(panel.router)

    async def post(self, action, body):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        ) as client:
            return await client.post("/api/providers/muse-code/oauth/" + action, json=body)

    async def test_missing_auth_cannot_start_grant(self):
        with patch.object(panel, "start_login", AsyncMock()) as start:
            response = await self.post("start", {})
        self.assertIn(response.status_code, (401, 403))
        start.assert_not_awaited()

    async def test_manual_completion_and_pending_do_not_record_false_creation(self):
        self.app.dependency_overrides[verify_panel_token] = lambda: "owner"
        with (
            patch.object(
                panel,
                "complete_login",
                AsyncMock(return_value={"status": "pending", "interval": 5}),
            ) as complete,
            patch.object(panel, "record_classified_management_response", AsyncMock()) as audit,
        ):
            response = await self.post("complete", {"flow_id": "muse_code_" + "a" * 43})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        complete.assert_awaited_once_with("owner", "muse_code_" + "a" * 43)
        audit.assert_not_awaited()

    async def test_rejects_foreign_flow_and_extra_fields(self):
        self.app.dependency_overrides[verify_panel_token] = lambda: "owner"
        with patch.object(panel, "complete_login", AsyncMock()) as complete:
            for body in (
                {"flow_id": "kiro_" + "a" * 43},
                {"flow_id": "muse_code_" + "a" * 43, "access_token": "secret"},
            ):
                self.assertEqual((await self.post("complete", body)).status_code, 422)
        complete.assert_not_awaited()

    async def test_saved_account_records_audit(self):
        self.app.dependency_overrides[verify_panel_token] = lambda: "owner"
        with (
            patch.object(
                panel, "complete_login", AsyncMock(return_value={"credential_saved": True})
            ),
            patch.object(panel, "record_classified_management_response", AsyncMock()) as audit,
        ):
            response = await self.post("complete", {"flow_id": "muse_code_" + "a" * 43})
        self.assertEqual(response.status_code, 200)
        audit.assert_awaited_once()
