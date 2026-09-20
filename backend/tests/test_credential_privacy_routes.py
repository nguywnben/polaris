"""Regression coverage for privacy response boundaries outside the fleet page."""

import base64
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import APIRouter, FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.credential_privacy import credential_reference, project_credential_references
from core.models import CredFileBatchActionRequest
from core.panel import auth, credentials
from core.panel.credential_privacy_route import CredentialPrivacyRoute
from core.utils import verify_panel_token

EMAIL = "someone42@example.test"
FILENAME = EMAIL + ".json"
KEY = b"k" * 32


class CredentialPrivacyRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_batch_replay_does_not_need_the_deleted_credential_to_resolve_again(self):
        reference = credential_reference(FILENAME, KEY)
        cached = {"results": [{"filename": FILENAME, "status": "succeeded"}]}
        with (
            patch.object(
                credentials, "get_idempotent_response", AsyncMock(return_value=(200, cached))
            ) as replay,
            patch.object(
                credentials,
                "resolve_credential_references",
                AsyncMock(side_effect=HTTPException(404)),
            ) as resolve,
        ):
            response = await credentials.creds_batch_action(
                CredFileBatchActionRequest(
                    action="delete", filenames=[reference], idempotency_key="retry-after-delete"
                ),
                token="owner",
                mode="provider",
            )
        self.assertEqual(response.status_code, 200)
        replay.assert_awaited_once()
        resolve.assert_not_awaited()

    def test_selected_route_and_nested_error_references_are_private(self):
        data = {
            "selected_filename": FILENAME,
            "error_messages": {"500": f"Error reading {FILENAME}"},
            "model": "unrelated@provider.json",
        }
        result = project_credential_references(data, KEY)
        self.assertEqual(result["selected_filename"], credential_reference(FILENAME, KEY))
        self.assertNotIn(EMAIL, str(result))
        self.assertEqual(result["model"], data["model"])

    async def test_structured_http_exception_keeps_its_status_and_safe_detail(self):
        app = FastAPI()
        router = APIRouter(route_class=CredentialPrivacyRoute)

        @router.get("/failure")
        async def failure():
            raise HTTPException(status_code=409, detail={"filename": FILENAME})

        app.include_router(router)
        with patch(
            "core.panel.credential_privacy_route.credential_reference_key",
            AsyncMock(return_value=KEY),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/failure")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["filename"], credential_reference(FILENAME, KEY))
        self.assertNotIn(EMAIL, response.text)

    async def test_oauth_completion_masks_saved_reference_but_keeps_explicit_export_payload(self):
        app = FastAPI()
        app.include_router(auth.router)
        app.dependency_overrides[verify_panel_token] = lambda: "owner"
        original_credential = {"project_id": "test", "token": "fixture-secret", "email": EMAIL}
        result = {
            "success": True,
            "file_path": FILENAME,
            "email": EMAIL,
            "credentials": original_credential,
            "deleted_duplicates": [FILENAME],
        }
        storage = AsyncMock()
        storage.get_config.return_value = base64.urlsafe_b64encode(KEY).decode()
        with (
            patch.object(auth, "_management_auth_reference", return_value="ref"),
            patch.object(auth, "asyncio_complete_auth_flow", AsyncMock(return_value=result)),
            patch("core.storage_adapter.get_storage_adapter", return_value=storage),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/auth/callback", json={"project_id": "test", "mode": "provider"}
                )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.pop("credentials"), original_credential)
        self.assertNotIn(EMAIL, str(data))
        self.assertEqual(data["file_path"], credential_reference(FILENAME, KEY))
        self.assertEqual(data["deleted_duplicates"], [credential_reference(FILENAME, KEY)])
        self.assertEqual(result["credentials"], original_credential)
