"""Tests for application release metadata."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app_version import DEFAULT_APPLICATION_VERSION, get_application_version


class ApplicationVersionTests(unittest.TestCase):
    def test_default_version_matches_stable_release(self):
        self.assertEqual(DEFAULT_APPLICATION_VERSION, "1.5.0")

    def test_release_tag_is_normalized(self):
        with patch.dict(os.environ, {"BUILD_VERSION": "v1.2.3-beta.1"}):
            self.assertEqual(get_application_version(), "1.2.3-beta.1")

    def test_branch_metadata_uses_release_fallback(self):
        with patch.dict(os.environ, {"BUILD_VERSION": "main"}):
            self.assertEqual(get_application_version(), DEFAULT_APPLICATION_VERSION)


if __name__ == "__main__":
    unittest.main()
