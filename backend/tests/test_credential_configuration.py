"""Safe provider-pool credential configuration contracts."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.models import CredentialUpdateRequest
from core.panel.credentials import (
    get_credential_configuration,
    update_credential_configuration,
)


class FakeCredentialConfigurationStorage:
    def __init__(self, credential: dict, *, others: dict[str, dict] | None = None):
        self.credential = dict(credential)
        self.others = dict(others or {})
        self.stored = None

    async def get_credential(self, _filename: str, mode: str = "primary"):
        self.requested_mode = mode
        return dict(self.credential)

    async def get_all_credentials(self, mode: str = "primary"):
        return {"current.json": dict(self.credential), **self.others}

    async def store_credential(self, filename: str, data: dict, mode: str = "primary"):
        self.stored = (filename, dict(data), mode)
        return True


class CredentialConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_configuration_read_is_allowlisted_and_never_returns_secrets(self):
        storage = FakeCredentialConfigurationStorage(
            {
                "provider": "ollama",
                "credential_type": "connection",
                "credential_label": "Local models",
                "base_url": "http://host.docker.internal:11434",
                "api_key": "must-not-leak",
                "refresh_token": "also-must-not-leak",
            }
        )
        with patch(
            "core.panel.credentials.get_storage_adapter",
            AsyncMock(return_value=storage),
        ):
            response = await get_credential_configuration(
                "current.json", token="session", mode="provider"
            )

        payload = json.loads(response.body)
        self.assertEqual(payload["credential_label"], "Local models")
        self.assertEqual(payload["base_url"], "http://host.docker.internal:11434")
        self.assertTrue(payload["has_api_key"])
        self.assertNotIn("api_key", payload)
        self.assertNotIn("refresh_token", payload)
        self.assertNotIn("must-not-leak", response.body.decode())

    async def test_environment_configuration_is_explicitly_read_only(self):
        storage = FakeCredentialConfigurationStorage(
            {
                "provider": "openai",
                "credential_type": "api_key",
                "source": "environment",
                "api_key": "environment-secret",
            }
        )
        with patch(
            "core.panel.credentials.get_storage_adapter",
            AsyncMock(return_value=storage),
        ):
            response = await get_credential_configuration(
                "current.json", token="session", mode="provider"
            )

        payload = json.loads(response.body)
        self.assertEqual(payload["source"], "environment")
        self.assertFalse(payload["editable"])
        self.assertEqual(payload["editable_fields"], [])
        self.assertFalse(payload["can_reauthenticate"])

    async def test_api_key_rotation_is_validated_and_keeps_the_stable_filename(self):
        storage = FakeCredentialConfigurationStorage(
            {
                "provider": "openai",
                "credential_type": "api_key",
                "credential_label": "Production key",
                "api_key": "old-secret",
                "key_fingerprint": "old-fingerprint",
                "model_ids": ["gpt-old"],
            }
        )
        validation = SimpleNamespace(model_ids=["gpt-5.4"], model_count=1)
        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credentials.validate_openai_api_key",
                AsyncMock(return_value=validation),
            ) as validate,
        ):
            response = await update_credential_configuration(
                "current.json",
                CredentialUpdateRequest(api_key="new-secret"),
                token="session",
                mode="provider",
            )

        payload = json.loads(response.body)
        self.assertEqual(payload["filename"], "current.json")
        self.assertEqual(payload["changed_fields"], ["api_key"])
        self.assertEqual(storage.stored[0], "current.json")
        self.assertEqual(storage.stored[1]["api_key"], "new-secret")
        self.assertEqual(storage.stored[1]["model_ids"], ["gpt-5.4"])
        self.assertEqual(storage.stored[1]["credential_label"], "Production key")
        validate.assert_awaited_once_with("new-secret")
        self.assertNotIn("new-secret", response.body.decode())

    async def test_api_key_rotation_rejects_a_duplicate_provider_connection(self):
        storage = FakeCredentialConfigurationStorage(
            {
                "provider": "openai",
                "credential_type": "api_key",
                "api_key": "old-secret",
            },
            others={
                "existing.json": {
                    "provider": "openai",
                    "credential_type": "api_key",
                    "api_key": "duplicate-secret",
                }
            },
        )
        validation = SimpleNamespace(model_ids=["gpt-5.4"], model_count=1)
        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credentials.validate_openai_api_key",
                AsyncMock(return_value=validation),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await update_credential_configuration(
                    "current.json",
                    CredentialUpdateRequest(api_key="duplicate-secret"),
                    token="session",
                    mode="provider",
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIsNone(storage.stored)

    async def test_each_remote_api_key_provider_uses_its_native_validator(self):
        cases = (
            ("google_ai_studio", "validate_api_key", "gemini-2.5-pro"),
            ("xai", "validate_xai_api_key", "grok-4"),
            ("anthropic", "validate_anthropic_api_key", "claude-opus-4-1"),
        )
        for provider, validator_name, model_id in cases:
            with self.subTest(provider=provider):
                storage = FakeCredentialConfigurationStorage(
                    {
                        "provider": provider,
                        "credential_type": "api_key",
                        "api_key": "old-secret",
                    }
                )
                validation = SimpleNamespace(model_ids=[model_id], model_count=1)
                with (
                    patch(
                        "core.panel.credentials.get_storage_adapter",
                        AsyncMock(return_value=storage),
                    ),
                    patch(
                        f"core.panel.credentials.{validator_name}",
                        AsyncMock(return_value=validation),
                    ) as validator,
                ):
                    await update_credential_configuration(
                        "current.json",
                        CredentialUpdateRequest(api_key="new-secret"),
                        token="session",
                        mode="provider",
                    )

                validator.assert_awaited_once_with("new-secret")
                self.assertEqual(storage.stored[1]["model_ids"], [model_id])

    async def test_ollama_connection_edit_validates_the_complete_candidate(self):
        storage = FakeCredentialConfigurationStorage(
            {
                "provider": "ollama",
                "credential_type": "connection",
                "credential_label": "Home lab",
                "base_url": "http://old-host:11434",
                "api_key": "old-key",
            }
        )
        validation = SimpleNamespace(model_ids=["qwen3.5"], model_count=1)
        with (
            patch(
                "core.panel.credentials.get_storage_adapter",
                AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.credentials.validate_ollama_connection",
                AsyncMock(return_value=validation),
            ) as validate,
        ):
            response = await update_credential_configuration(
                "current.json",
                CredentialUpdateRequest(base_url="http://new-host:11434/", api_key="new-key"),
                token="session",
                mode="provider",
            )

        payload = json.loads(response.body)
        self.assertEqual(payload["changed_fields"], ["api_key", "base_url"])
        self.assertEqual(storage.stored[1]["base_url"], "http://new-host:11434")
        self.assertEqual(storage.stored[1]["api_key"], "new-key")
        validate.assert_awaited_once_with("http://new-host:11434", "new-key")

    async def test_environment_credentials_are_read_only(self):
        storage = FakeCredentialConfigurationStorage(
            {
                "provider": "openai",
                "credential_type": "api_key",
                "source": "environment",
                "api_key": "environment-secret",
            }
        )
        with patch(
            "core.panel.credentials.get_storage_adapter",
            AsyncMock(return_value=storage),
        ):
            with self.assertRaises(HTTPException) as raised:
                await update_credential_configuration(
                    "current.json",
                    CredentialUpdateRequest(credential_label="Renamed"),
                    token="session",
                    mode="provider",
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("environment", raised.exception.detail.lower())
        self.assertIsNone(storage.stored)

    async def test_oauth_credentials_reject_secret_field_edits(self):
        storage = FakeCredentialConfigurationStorage(
            {
                "provider": "openai",
                "credential_type": "oauth",
                "access_token": "must-not-leak",
            }
        )
        with patch(
            "core.panel.credentials.get_storage_adapter",
            AsyncMock(return_value=storage),
        ):
            with self.assertRaises(HTTPException) as raised:
                await update_credential_configuration(
                    "current.json",
                    CredentialUpdateRequest(api_key="crafted-secret"),
                    token="session",
                    mode="provider",
                )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIsNone(storage.stored)

    async def test_managed_oauth_credentials_allow_label_updates_only(self):
        storage = FakeCredentialConfigurationStorage(
            {
                "provider": "openai",
                "credential_type": "oauth",
                "credential_label": "Old name",
                "access_token": "must-not-leak",
            }
        )
        with patch(
            "core.panel.credentials.get_storage_adapter",
            AsyncMock(return_value=storage),
        ):
            response = await update_credential_configuration(
                "current.json",
                CredentialUpdateRequest(credential_label="Personal Codex"),
                token="session",
                mode="provider",
            )

        payload = json.loads(response.body)
        self.assertEqual(payload["changed_fields"], ["credential_label"])
        self.assertEqual(storage.stored[1]["credential_label"], "Personal Codex")
        self.assertEqual(storage.stored[1]["access_token"], "must-not-leak")
        self.assertNotIn("must-not-leak", response.body.decode())


if __name__ == "__main__":
    unittest.main()
