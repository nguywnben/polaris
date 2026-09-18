"""A persisted, synthetic dataset must never overwrite operator storage."""

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from collections import Counter
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.provider_registry import (
    get_credential_provider_variant,
    list_credential_variant_capabilities,
)

from tools.demo_credentials import build_records, quota_snapshot
from tools.seed_demo_database import seed_database


class DemoDatabaseTests(unittest.IsolatedAsyncioTestCase):
    def test_quota_presets_keep_provider_specific_shapes(self):
        now = int(time.time())
        antigravity = quota_snapshot("google_antigravity", 1, now)
        self.assertNotEqual(antigravity.get("quota_type"), "account_rate_limits")
        self.assertTrue(antigravity["models"])
        self.assertFalse(antigravity["windows"])
        grok = quota_snapshot("grok", 1, now)
        self.assertEqual(grok["quota_type"], "account_billing")
        self.assertTrue(grok["monthly"])
        self.assertFalse(grok["windows"])
        kiro = quota_snapshot("kiro", 1, now)
        for window in kiro["windows"]:
            self.assertNotIn("window_duration_mins", window)
            self.assertIn(window["kind"], {"resource", "trial"})
        for provider in ("codex", "claude_code", "muse_code"):
            self.assertTrue(quota_snapshot(provider, 1, now)["windows"])

    def test_extended_records_pass_real_provider_normalizers(self):
        from core.extended_provider_runtime import normalize_extended_credential
        from core.provider_registry import EXTENDED_PROVIDERS

        for record in build_records(int(time.time())):
            if record["variant"] in EXTENDED_PROVIDERS:
                with self.subTest(filename=record["filename"]):
                    normalized = normalize_extended_credential(record["data"])
                    self.assertEqual(normalized["provider"], record["data"]["provider"])

    async def test_persists_all_variants_with_one_to_seven_credentials(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch) / "demo"
            report = await seed_database(target)
            with closing(sqlite3.connect(target / "credentials.db")) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                rows = db.execute(
                    "SELECT filename, credential_data, user_email, disabled, error_codes "
                    "FROM primary_credentials"
                ).fetchall()
                configs = dict(db.execute("SELECT key, value FROM config"))
            counts = Counter()
            for filename, raw, email, disabled, errors in rows:
                data = json.loads(raw)
                counts[get_credential_provider_variant(data)] += 1
                self.assertTrue(filename.startswith("demo-"))
                self.assertTrue(data["synthetic"])
                self.assertTrue(data["credential_label"].startswith("DEMO"))
                self.assertTrue(data["model_ids"])
                for key in ("api_key", "access_token", "refresh_token"):
                    if data.get(key):
                        self.assertTrue(data[key].startswith("DEMO-NOT-A-REAL-"))
                if data["credential_type"] == "api_key":
                    self.assertIsNone(email)
                elif email:
                    self.assertTrue(email.endswith("@example.invalid"))
            expected = {item["variant_id"] for item in list_credential_variant_capabilities()}
            self.assertEqual(set(counts), expected)
            self.assertTrue(all(1 <= count <= 7 for count in counts.values()))
            self.assertEqual(set(counts.values()), set(range(1, 8)))
            self.assertEqual(report["credential_count"], len(rows))
            self.assertTrue(any(row[3] for row in rows))
            self.assertTrue(any(json.loads(row[4]) for row in rows))
            fixtures = json.loads(configs["demo_upstream_v2"])
            self.assertEqual(set(fixtures), {row[0] for row in rows})
            self.assertTrue(all(item["sources"] for item in fixtures.values()))
            self.assertNotIn("demo_quota_snapshots_v1", configs)

    async def test_refuses_existing_target_without_changing_a_byte(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch) / "demo"
            await seed_database(target)
            before = (target / "credentials.db").read_bytes()
            with self.assertRaises(FileExistsError):
                await seed_database(target)
            self.assertEqual((target / "credentials.db").read_bytes(), before)

    async def test_refuses_even_an_existing_empty_directory(self):
        with tempfile.TemporaryDirectory() as scratch:
            with self.assertRaises(FileExistsError):
                await seed_database(Path(scratch))
            self.assertEqual(await asyncio.to_thread(os.listdir, scratch), [])


if __name__ == "__main__":
    unittest.main()
