"""Full demo data uses real domain validators and durable repositories."""

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from tools.seed_demo_database import seed_database


class FullDemoTests(unittest.TestCase):
    async def _verify_routable_providers(self, target):
        from core.provider_registry import get_credential_provider
        from core.smart_routing import SmartCredentialRouter
        from core.storage.sqlite_manager import SQLiteManager

        storage = SQLiteManager()
        with patch.dict(os.environ, {"CREDENTIALS_DIR": str(target)}):
            await storage.initialize()
        try:
            records = await storage.get_all_credentials(mode="primary")
            router = SmartCredentialRouter()
            checked = set()
            for record in records.values():
                provider = get_credential_provider(record)
                if provider in checked:
                    continue
                result, decision = await router.acquire_with_decision(
                    storage,
                    mode="primary",
                    provider_id=provider,
                    model_name=record["model_ids"][0],
                )
                self.assertIsNotNone(result, (provider, decision.reason))
                await router.release(result[0], mode="primary")
                checked.add(provider)
            self.assertGreaterEqual(len(checked), 20)
        finally:
            await storage.close()

    def test_unrecorded_inference_fails_instead_of_fabricating_a_completion(self):
        import httpx

        from tools.demo_transport import fixture_response

        with self.assertRaises(httpx.ConnectError):
            fixture_response(
                httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
                {"variant": "openai_platform", "responses": {}, "models": []},
            )

    def test_full_dataset_has_linked_activity_governance_and_backup(self):
        from core.quality_policy import load_policy_document
        from core.virtual_keys import VirtualKey

        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch) / "credentials"
            report = asyncio.run(seed_database(target, full=True))
            asyncio.run(self._verify_routable_providers(target))
            with closing(sqlite3.connect(target / "credentials.db")) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                configs = {k: json.loads(v) for k, v in db.execute("SELECT key,value FROM config")}
                filenames = {r[0] for r in db.execute("SELECT filename FROM primary_credentials")}
                usage = [
                    json.loads(r[0])
                    for r in db.execute(
                        "SELECT payload FROM durable_usage_ledger WHERE kind='usage'"
                    )
                ]
                trace_ids = {r[0] for r in db.execute("SELECT request_id FROM request_traces")}
                identities = db.execute("SELECT COUNT(*) FROM management_identities").fetchone()[0]
                audits = db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
            keys = [VirtualKey.from_storage_dict(k) for k in configs["virtual_keys"]]
            self.assertEqual(len(keys), 8)
            self.assertTrue(all(keys))
            self.assertEqual({k.status for k in keys}, {"active", "disabled", "expired", "revoked"})
            key_ids = {k.id for k in keys}
            self.assertEqual(len(usage), report["credential_count"] * 8)
            self.assertEqual({u["credential_ref"] for u in usage}, filenames)
            self.assertTrue(all(u["api_key_id"] in key_ids for u in usage))
            for key in keys:
                calls = [u["occurred_at"] for u in usage if u["api_key_id"] == key.id]
                self.assertEqual(key.last_used_at, max(calls) if calls else None)
            self.assertEqual(
                trace_ids - {u["request_id"] for u in usage},
                {f"demo-local-{index:02}" for index in range(8)},
            )
            self.assertEqual(sum(u["cost_nanos"] for u in usage), report["activity"]["cost_nanos"])
            self.assertEqual(sum(u["total_tokens"] for u in usage), report["activity"]["tokens"])
            self.assertGreater(
                max(u["occurred_at"] for u in usage) - min(u["occurred_at"] for u in usage),
                28 * 86400,
            )
            self.assertGreaterEqual(identities, 5)
            self.assertGreaterEqual(audits, 50)
            self.assertTrue(configs["virtual_model_pool"]["selected_models"])
            self.assertTrue(configs["model_route_blacklist"]["entries"])
            self.assertEqual(
                load_policy_document(configs["quality_policy_document"], {})["profile"], "custom"
            )
            self.assertTrue(report["backup"]["validated"])
            self.assertTrue((target.parent / report["backup"]["filename"]).is_file())
            self.assertIn("DEMO", (target.parent / "demo-runtime.log").read_text())


if __name__ == "__main__":
    unittest.main()
