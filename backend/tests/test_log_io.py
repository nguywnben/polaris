"""Tests for non-blocking log-file helper behavior."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from core.panel.logs import (
    MAX_LOG_DOWNLOAD_BYTES,
    _clear_log_file,
    _log_file_size,
    _read_bounded_log_export,
    _read_log_chunk,
    _read_recent_log_lines,
)
from support import workspace_temp_directory


class LogFileHelperTests(unittest.TestCase):
    def test_clear_log_file_truncates_existing_file(self):
        with workspace_temp_directory() as temp_dir:
            path = Path(temp_dir) / "runtime.log"
            path.write_text("sensitive line\n", encoding="utf-8")

            self.assertTrue(_clear_log_file(str(path)))
            self.assertEqual(_log_file_size(str(path)), 0)
            self.assertEqual(path.read_text(encoding="utf-8"), "")

    def test_missing_log_file_is_reported_without_creation(self):
        with workspace_temp_directory() as temp_dir:
            path = Path(temp_dir) / "missing.log"

            self.assertFalse(_clear_log_file(str(path)))
            self.assertIsNone(_log_file_size(str(path)))
            self.assertEqual(_read_recent_log_lines(str(path), 50), [])

    def test_recent_lines_and_binary_offsets_are_stable(self):
        with workspace_temp_directory() as temp_dir:
            path = Path(temp_dir) / "runtime.log"
            path.write_bytes(b"first\nsecond\nthird\n")

            self.assertEqual(_read_recent_log_lines(str(path), 2), ["second\n", "third\n"])
            content, bytes_read = _read_log_chunk(str(path), len("first\n"), len("second\n"))
            self.assertEqual(content, "second\n")
            self.assertEqual(bytes_read, len("second\n"))

    def test_download_export_keeps_latest_complete_redacted_lines_within_limit(self):
        with workspace_temp_directory() as temp_dir:
            path = Path(temp_dir) / "runtime.log"
            path.write_text(
                "old line that must be dropped\n"
                "[2026-09-10 08:00:00] [ERROR] token=secret-value\n"
                "[2026-09-10 08:00:01] [INFO] request_id=req-safe\n",
                encoding="utf-8",
            )

            export, truncated = _read_bounded_log_export(str(path), max_bytes=110)

            self.assertTrue(truncated)
            self.assertLessEqual(len(export), 110)
            self.assertNotIn(b"secret-value", export)
            self.assertIn(b"token=<redacted>", export)
            self.assertIn(b"request_id=req-safe", export)
            self.assertFalse(export.startswith(b"must be dropped"))
            self.assertEqual(MAX_LOG_DOWNLOAD_BYTES, 16 * 1024 * 1024)

    def test_download_export_keeps_first_line_when_limit_starts_on_line_boundary(self):
        with workspace_temp_directory() as temp_dir:
            path = Path(temp_dir) / "runtime.log"
            latest_lines = b"request_id=req-boundary\nstatus=failed\n"
            path.write_bytes(b"discarded\n" + latest_lines)

            export, truncated = _read_bounded_log_export(
                str(path),
                max_bytes=len(latest_lines),
            )

            self.assertTrue(truncated)
            self.assertEqual(export, latest_lines)


if __name__ == "__main__":
    unittest.main()
