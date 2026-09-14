from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel.quality_policy import (
    QualityPolicyPreviewRequest,
    QualityPolicyUpdateRequest,
    get_quality_policy,
    preview_quality_policy,
    update_quality_policy,
)
from core.quality_policy import POLICY_STORAGE_KEY, build_policy_document


def balanced_legacy() -> dict:
    return {
        "compatibility_mode_enabled": False,
        "return_thoughts_to_frontend": True,
        "anti_truncation_max_attempts": 3,
        "token_compression_enabled": True,
        "token_compression_threshold": 32_000,
        "token_compression_target": 24_000,
        "token_compression_min_recent_turns": 4,
        "guardrails_enabled": False,
        "guardrails_pii_masking_enabled": True,
        "guardrails_injection_detection_enabled": True,
        "guardrails_blocked_keywords": [],
        "response_cache_enabled": False,
        "response_cache_ttl_seconds": 300,
        "response_cache_max_entries": 1_000,
    }


class FakePolicyStorage:
    def __init__(self, stored=None):
        self.values = {}
        if stored is not None:
            self.values[POLICY_STORAGE_KEY] = stored

    async def get_config(self, key, default=None):
        return self.values.get(key, default)

    async def set_config(self, key, value):
        self.values[key] = value
        return True


def response_json(response) -> dict:
    return json.loads(response.body)


class QualityPolicyRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_projects_legacy_without_writing_storage(self):
        storage = FakePolicyStorage()
        with (
            patch(
                "core.panel.quality_policy.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.quality_policy.read_legacy_quality_settings",
                new=AsyncMock(return_value=balanced_legacy()),
            ),
            patch("core.panel.quality_policy.get_env_locked_keys", return_value=set()),
        ):
            response = await get_quality_policy(token="session")

        body = response_json(response)
        self.assertEqual(body["policy"]["source"], "legacy_projection")
        self.assertEqual(body["policy"]["revision"], 0)
        self.assertTrue(body["runtime_active"])
        self.assertEqual(body["runtime_source"], "legacy_projection")
        self.assertEqual(body["effective_settings"], body["policy"]["settings"])
        self.assertEqual(set(body["profile_defaults"]), {"quality", "balanced", "capacity"})
        self.assertFalse(body["profile_defaults"]["quality"]["compression"]["enabled"])
        self.assertEqual(body["application"]["mode"], "live")
        self.assertFalse(body["application"]["restart_required"])
        self.assertEqual(
            body["application"]["precedence"],
            ["environment", "global_policy", "virtual_key", "request"],
        )
        self.assertEqual(body["warnings"], [])
        self.assertEqual(storage.values, {})

    async def test_update_uses_optimistic_revision_and_preserves_legacy_keys(self):
        storage = FakePolicyStorage()
        request = QualityPolicyUpdateRequest(revision=0, profile="quality")
        with (
            patch(
                "core.panel.quality_policy.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.quality_policy.read_legacy_quality_settings",
                new=AsyncMock(return_value=balanced_legacy()),
            ),
            patch("core.panel.quality_policy.get_env_locked_keys", return_value=set()),
            patch("core.panel.quality_policy.config.set_cached_config_value"),
        ):
            response = await update_quality_policy(request, token="session")

        body = response_json(response)
        self.assertEqual(body["policy"]["revision"], 1)
        self.assertEqual(body["policy"]["profile"], "quality")
        self.assertEqual(set(storage.values), {POLICY_STORAGE_KEY})

    async def test_update_returns_stable_conflict_error_code(self):
        storage = FakePolicyStorage(build_policy_document(profile="balanced", revision=3))
        request = QualityPolicyUpdateRequest(revision=2, profile="quality")
        with (
            patch(
                "core.panel.quality_policy.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.quality_policy.read_legacy_quality_settings",
                new=AsyncMock(return_value=balanced_legacy()),
            ),
            patch("core.panel.quality_policy.get_env_locked_keys", return_value=set()),
        ):
            response = await update_quality_policy(request, token="session")

        body = response_json(response)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(body["error"]["code"], "quality_policy_revision_conflict")
        self.assertEqual(body["error"]["current_revision"], 3)

    async def test_update_rejects_changes_to_environment_locked_policy_fields(self):
        storage = FakePolicyStorage()
        custom = build_policy_document(profile="balanced", revision=0)["settings"]
        custom["compression"]["enabled"] = False
        request = QualityPolicyUpdateRequest(revision=0, profile="custom", settings=custom)
        with (
            patch(
                "core.panel.quality_policy.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.quality_policy.read_legacy_quality_settings",
                new=AsyncMock(return_value=balanced_legacy()),
            ),
            patch(
                "core.panel.quality_policy.get_env_locked_keys",
                return_value={"token_compression_enabled"},
            ),
        ):
            response = await update_quality_policy(request, token="session")

        body = response_json(response)
        self.assertEqual(response.status_code, 423)
        self.assertEqual(body["error"]["code"], "quality_policy_environment_locked")
        self.assertEqual(body["error"]["fields"], ["token_compression_enabled"])
        self.assertEqual(storage.values, {})

    async def test_preset_can_be_saved_while_environment_retains_effective_precedence(self):
        storage = FakePolicyStorage()
        request = QualityPolicyUpdateRequest(revision=0, profile="quality")
        with (
            patch(
                "core.panel.quality_policy.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.quality_policy.read_legacy_quality_settings",
                new=AsyncMock(return_value=balanced_legacy()),
            ),
            patch(
                "core.panel.quality_policy.get_env_locked_keys",
                return_value={"token_compression_enabled"},
            ),
            patch("core.panel.quality_policy.config.set_cached_config_value"),
        ):
            response = await update_quality_policy(request, token="session")

        body = response_json(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["policy"]["profile"], "quality")
        self.assertEqual(body["environment_overrides"], ["token_compression_enabled"])

    async def test_preview_does_not_write_policy(self):
        storage = FakePolicyStorage()
        request = QualityPolicyPreviewRequest(
            revision=0,
            profile="balanced",
            estimated_input_tokens=40_000,
            message_count=20,
            tool_count=2,
            has_system_instruction=True,
            has_tool_pairs=True,
        )
        with (
            patch(
                "core.panel.quality_policy.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.quality_policy.read_legacy_quality_settings",
                new=AsyncMock(return_value=balanced_legacy()),
            ),
            patch("core.panel.quality_policy.get_env_locked_keys", return_value=set()),
        ):
            response = await preview_quality_policy(request, token="session")

        body = response_json(response)
        self.assertEqual(body["preview"]["decision"]["reason"], "structural_compression_candidate")
        self.assertTrue(body["can_apply"])
        self.assertEqual(body["environment_conflicts"], [])
        self.assertTrue(body["preview"]["transformation"]["will_transform"])
        self.assertEqual(body["preview"]["warnings"], [])
        self.assertEqual(storage.values, {})

    async def test_preview_reports_environment_locked_conflicts_without_writing(self):
        storage = FakePolicyStorage()
        request = QualityPolicyPreviewRequest(
            revision=0,
            profile="quality",
            estimated_input_tokens=40_000,
            message_count=20,
            tool_count=2,
            has_system_instruction=True,
            has_tool_pairs=True,
        )
        with (
            patch(
                "core.panel.quality_policy.get_storage_adapter",
                new=AsyncMock(return_value=storage),
            ),
            patch(
                "core.panel.quality_policy.read_legacy_quality_settings",
                new=AsyncMock(return_value=balanced_legacy()),
            ),
            patch(
                "core.panel.quality_policy.get_env_locked_keys",
                return_value={"token_compression_enabled"},
            ),
        ):
            response = await preview_quality_policy(request, token="session")

        body = response_json(response)
        self.assertTrue(body["can_apply"])
        self.assertTrue(body["applies_with_environment_overrides"])
        self.assertEqual(body["environment_conflicts"], ["token_compression_enabled"])
        self.assertEqual(body["preview"]["decision"]["reason"], "structural_compression_candidate")
        self.assertEqual(body["preview"]["decision"]["estimated_tokens_after"], 24_000)
        self.assertEqual(storage.values, {})

    async def test_get_returns_stable_sanitized_error_when_storage_is_unavailable(self):
        with patch(
            "core.panel.quality_policy.get_storage_adapter",
            new=AsyncMock(side_effect=RuntimeError("database secret must not leak")),
        ):
            response = await get_quality_policy(token="session")

        body = response_json(response)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(body["error"]["code"], "quality_policy_unavailable")
        self.assertNotIn("database secret", response.body.decode())


if __name__ == "__main__":
    unittest.main()
