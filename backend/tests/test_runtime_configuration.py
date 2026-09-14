"""Runtime configuration safety contracts."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.http_server import (
    HYPERCORN_KEEP_ALIVE_MAX_REQUESTS,
    configure_hypercorn,
)
from hypercorn.config import Config
from main import _get_worker_count


class WorkerConfigurationTests(unittest.TestCase):
    def test_single_worker_is_supported(self):
        with patch.dict(os.environ, {"WORKERS": "1"}):
            self.assertEqual(_get_worker_count(), 1)

    def test_multiple_workers_fail_with_an_actionable_message(self):
        with patch.dict(os.environ, {"WORKERS": "2"}):
            with self.assertRaisesRegex(RuntimeError, "supports WORKERS=1 only"):
                _get_worker_count()

    def test_non_numeric_workers_are_rejected(self):
        with patch.dict(os.environ, {"WORKERS": "many"}):
            with self.assertRaisesRegex(RuntimeError, "must be the integer 1"):
                _get_worker_count()


class HttpServerConfigurationTests(unittest.TestCase):
    def test_keep_alive_rollover_exceeds_the_longest_frozen_load_phase(self):
        config = configure_hypercorn(Config())

        self.assertEqual(
            config.keep_alive_max_requests,
            HYPERCORN_KEEP_ALIVE_MAX_REQUESTS,
        )
        self.assertGreater(config.keep_alive_max_requests, 4096)
        self.assertLessEqual(config.keep_alive_max_requests, 10_000)

    def test_production_entrypoint_uses_the_managed_hypercorn_configuration(self):
        source = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")

        self.assertIn("configure_hypercorn(config)", source)


if __name__ == "__main__":
    unittest.main()
