"""File import is offline; authorization checks belong to explicit pool actions."""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import pool_import


class OfflineImportTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_provider_keys_import_without_catalog_or_inference(self):
        cases = [
            ("google_ai_studio", pool_import._restore_ai_studio),
            ("xai", pool_import.restore_xai_credential),
            ("openai", pool_import.restore_openai_credential),
            ("anthropic", pool_import.restore_anthropic_credential),
            ("ollama", pool_import.restore_ollama_credential),
        ]
        for provider, restore in cases:
            with (
                self.subTest(provider=provider),
                patch(
                    "core.provider_store.credential_manager.add_primary_credential",
                    AsyncMock(return_value={"action": "created", "filename": "safe.json"}),
                ) as save,
            ):
                payload = {
                    "provider": provider,
                    "credential_type": "api_key",
                    "api_key": "synthetic-key",
                    "base_url": "http://localhost:11434",
                    "model_ids": ["untrusted"],
                    "validation_status": "verified",
                }
                # Every network boundary is a hard failure, not a permissive mock.
                with patch(
                    "core.httpx_client.http_client.get_client",
                    side_effect=AssertionError("Unexpected network"),
                ):
                    result = await restore({"payload": payload, "filename": "input.json"})
                self.assertEqual(result["validation_status"], "unverified")
                self.assertEqual(save.call_args.args[1]["model_ids"], [])
                self.assertTrue(save.call_args.kwargs["skip_existing"])
