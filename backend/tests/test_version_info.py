"""Tests for build metadata and update discovery."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.panel.version import get_version_info, is_newer_release


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class VersionInfoTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_metadata_is_used_without_a_version_file(self):
        with patch.dict(
            "os.environ",
            {
                "BUILD_REVISION": "abcdef1234567890",
                "BUILD_VERSION": "1.0.0",
                "BUILD_DATE": "2026-07-11T10:00:00Z",
            },
            clear=False,
        ):
            response = await get_version_info()

        body = json.loads(response.body)
        self.assertTrue(body["success"])
        self.assertEqual(body["version"], "1.0.0")
        self.assertEqual(body["full_hash"], "abcdef1234567890")
        self.assertEqual(body["date"], "2026-07-11T10:00:00Z")
        self.assertEqual(body["source"], "container")

    async def test_update_check_uses_the_latest_public_release(self):
        remote = FakeResponse(
            200,
            {
                "tag_name": "v1.1.0",
                "name": "Polaris 1.1.0",
                "body": "Release hardening.\n\nDetails.",
                "published_at": "2026-08-11T12:00:00Z",
                "html_url": "https://github.com/nguywnben/polaris/releases/tag/v1.1.0",
            },
        )
        with (
            patch.dict(
                "os.environ",
                {"BUILD_REVISION": "abcdef1234567890", "BUILD_VERSION": "1.0.0"},
                clear=False,
            ),
            patch("core.httpx_client.get_async", new=AsyncMock(return_value=remote)) as get,
        ):
            response = await get_version_info(check_update=True)

        body = json.loads(response.body)
        self.assertTrue(body["check_update"])
        self.assertTrue(body["has_update"])
        self.assertEqual(body["latest_version"], "1.1.0")
        self.assertEqual(body["latest_message"], "Polaris 1.1.0")
        self.assertEqual(
            body["latest_url"],
            "https://github.com/nguywnben/polaris/releases/tag/v1.1.0",
        )
        requested_url = get.await_args.args[0]
        self.assertEqual(
            requested_url,
            "https://api.github.com/repos/nguywnben/polaris/releases/latest",
        )

    def test_semantic_release_comparison_handles_stable_and_prerelease_versions(self):
        self.assertTrue(is_newer_release("1.0.0", "1.0.0-beta"))
        self.assertTrue(is_newer_release("1.1.0", "1.0.9"))
        self.assertFalse(is_newer_release("1.0.0-beta.2", "1.0.0-beta.10"))
        self.assertFalse(is_newer_release("1.0.0", "1.0.0"))
        self.assertIsNone(is_newer_release("1.0.0", "abcdef1"))

    async def test_branch_builds_display_the_revision_instead_of_main(self):
        with patch.dict(
            "os.environ",
            {
                "BUILD_REVISION": "abcdef1234567890",
                "BUILD_VERSION": "main",
            },
            clear=False,
        ):
            response = await get_version_info()

        self.assertEqual(json.loads(response.body)["version"], "abcdef1")

    async def test_update_errors_are_sanitized(self):
        with (
            patch.dict(
                "os.environ",
                {"BUILD_REVISION": "abcdef1234567890", "BUILD_VERSION": "1.0.0"},
                clear=False,
            ),
            patch(
                "core.httpx_client.get_async",
                new=AsyncMock(side_effect=RuntimeError("proxy password leaked")),
            ),
            patch("core.panel.version.log.debug") as debug,
        ):
            response = await get_version_info(check_update=True)

        body = json.loads(response.body)
        self.assertFalse(body["check_update"])
        self.assertEqual(body["update_error"], "Unable to check for updates.")
        self.assertNotIn("proxy password leaked", response.body.decode())
        self.assertNotIn("proxy password leaked", str(debug.call_args_list))


if __name__ == "__main__":
    unittest.main()
