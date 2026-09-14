"""Tests for request-scoped telemetry metadata."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.request_context import (
    get_api_key_id,
    get_key_compression_policy,
    get_request_compression_policy,
    get_request_elapsed_ms,
    get_request_id,
    get_virtual_key_reservation_id,
    request_scope,
    set_api_key_id,
    set_key_compression_policy,
    set_request_compression_policy,
    set_virtual_key_reservation_id,
)


class RequestContextTests(unittest.TestCase):
    def test_scope_exposes_and_resets_request_metadata(self):
        self.assertEqual(get_request_id(), "")

    def test_scope_resets_virtual_key_attribution(self):
        with request_scope("request-virtual-key"):
            set_api_key_id("vk_example")
            set_virtual_key_reservation_id("reservation-example")
            set_key_compression_policy("disabled")
            set_request_compression_policy("disabled")
            self.assertEqual(get_api_key_id(), "vk_example")
            self.assertEqual(get_virtual_key_reservation_id(), "reservation-example")
            self.assertEqual(get_key_compression_policy(), "disabled")
            self.assertEqual(get_request_compression_policy(), "disabled")

        self.assertEqual(get_api_key_id(), "")
        self.assertEqual(get_virtual_key_reservation_id(), "")
        self.assertEqual(get_key_compression_policy(), "inherit")
        self.assertEqual(get_request_compression_policy(), "inherit")
        with request_scope("request-123"):
            self.assertEqual(get_request_id(), "request-123")
            self.assertGreaterEqual(get_request_elapsed_ms(), 0)
        self.assertEqual(get_request_id(), "")


if __name__ == "__main__":
    unittest.main()
