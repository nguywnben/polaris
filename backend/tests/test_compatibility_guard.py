"""Backward-compatibility contracts captured before the R1 simplification work."""

from __future__ import annotations

import copy
import json
import os
import shutil
import sqlite3
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from tools.compatibility_snapshot import build_snapshot, compare_snapshots

BASELINE_PATH = ROOT / "docs" / "compatibility" / "r1-compatibility-v1.json"
UPGRADE_FIXTURE_PATH = ROOT / "backend" / "tests" / "fixtures" / "pre-r1-sqlite-v1.json"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


class CompatibilitySnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = _load_json(BASELINE_PATH)
        cls.current = build_snapshot()

    def test_versioned_fixture_matches_the_fixed_r1_profile(self) -> None:
        self.assertEqual(self.baseline["schema_version"], 1)
        self.assertEqual(self.baseline["profile"], "production-self-hosted-r1")
        self.assertEqual(self.baseline["contract_version"], "r1-v1")

    def test_public_and_management_routes_remain_compatible(self) -> None:
        differences = compare_snapshots(self.baseline, self.current)

        self.assertEqual(differences, [])
        self.assertEqual(len(self.baseline["public_inference_operations"]), 18)
        self.assertGreaterEqual(len(self.baseline["management_operations"]), 100)

    def test_additive_compatibility_surfaces_do_not_break_the_r1_baseline(self) -> None:
        current = copy.deepcopy(self.current)
        current["config_compatibility"]["stored_key_renames"]["new_legacy_key"] = "new_key"

        self.assertEqual(compare_snapshots(self.baseline, current), [])

    def test_route_removal_and_semantic_change_are_reported(self) -> None:
        missing = copy.deepcopy(self.current)
        missing["public_inference_operations"] = missing["public_inference_operations"][1:]
        changed = copy.deepcopy(self.current)
        changed["management_operations"][0]["semantic_sha256"] = "0" * 64

        self.assertRegex(compare_snapshots(self.baseline, missing)[0], r"^removed ")
        self.assertTrue(
            any(
                difference.startswith("changed management_operations:")
                for difference in compare_snapshots(self.baseline, changed)
            )
        )

    def test_console_urls_and_generated_client_examples_remain_valid(self) -> None:
        self.assertEqual(self.baseline["console_routes"]["tab_map"]["dashboard"], "/dashboard")
        self.assertIn("/code_assist", self.baseline["console_routes"]["server_paths"])
        public_operations = {
            (entry["method"], entry["path"])
            for entry in self.current["public_inference_operations"]
        }
        sources: dict[str, str] = {}
        for example in self.baseline["generated_client_examples"]:
            self.assertIn((example["method"], example["operation_path"]), public_operations)
            for marker in example["source_markers"]:
                source_path = marker["path"]
                sources.setdefault(
                    source_path,
                    (ROOT / source_path).read_text(encoding="utf-8"),
                )
                self.assertIn(marker["contains"], sources[source_path])

        route_map = self.current["console_routes"]["route_map"]
        for alias, canonical in self.baseline["console_routes"]["compatibility_aliases"].items():
            self.assertEqual(route_map[alias], route_map[canonical])


class PreR1SQLiteUpgradeTests(unittest.IsolatedAsyncioTestCase):
    async def test_pre_r1_fixture_upgrades_without_losing_credentials_or_config(self) -> None:
        import config
        from core.storage.sqlite_manager import SQLiteManager

        fixture = _load_json(UPGRADE_FIXTURE_PATH)
        self.assertEqual(fixture["fixture_version"], 1)

        original_cache = dict(config._config_cache)
        original_initialized = config._config_initialized
        directory = ROOT / "temp" / "tests" / f"p0-6-upgrade-{uuid.uuid4().hex}"
        directory.mkdir(parents=True)
        try:
            database = directory / "credentials.db"
            self._create_pre_r1_database(database, fixture)
            manager = SQLiteManager()

            with patch.dict(
                os.environ,
                {"CREDENTIALS_DIR": str(directory), "PASSWORD": "", "PANEL_PASSWORD": ""},
            ):
                await manager.initialize()
                config._config_cache = {}
                config._config_initialized = False
                with patch(
                    "core.storage_adapter.get_storage_adapter",
                    new=AsyncMock(return_value=manager),
                ):
                    await config.init_config()

            values = await manager.get_all_config()
            self.assertEqual(values["antigravity_client_id"], fixture["legacy_config"]["client_id"])
            self.assertEqual(values["antigravity_api_url"], fixture["legacy_config"]["api_url"])
            self.assertEqual(values["panel_password"], fixture["legacy_config"]["password"])
            for legacy_key in fixture["legacy_config"]:
                self.assertNotIn(legacy_key, values)

            self.assertTrue(
                await manager.store_credential(
                    "new-account.json", {"type": "fixture"}, mode="code_assist"
                )
            )
            with sqlite3.connect(database) as connection:
                credential_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(credentials)").fetchall()
                }
                primary_columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(primary_credentials)"
                    ).fetchall()
                }
                credential_filenames = {
                    row[0] for row in connection.execute("SELECT filename FROM credentials")
                }
                primary_filenames = {
                    row[0] for row in connection.execute("SELECT filename FROM primary_credentials")
                }
                new_timestamps = connection.execute(
                    "SELECT created_at, updated_at FROM credentials WHERE filename = ?",
                    ("new-account.json",),
                ).fetchone()
            self.assertTrue(
                {column[0] for column in manager.REQUIRED_COLUMNS["credentials"]}.issubset(
                    credential_columns
                )
            )
            self.assertTrue(
                {column[0] for column in manager.REQUIRED_COLUMNS["primary_credentials"]}.issubset(
                    primary_columns
                )
            )
            self.assertEqual(credential_filenames, {"legacy-account.json", "new-account.json"})
            self.assertEqual(primary_filenames, {"legacy-primary.json"})
            self.assertTrue(all(value and value > 0 for value in new_timestamps))
            await manager.close()
        finally:
            config._config_cache = original_cache
            config._config_initialized = original_initialized
            shutil.rmtree(directory, ignore_errors=True)

    @staticmethod
    def _create_pre_r1_database(database: Path, fixture: dict[str, object]) -> None:
        with sqlite3.connect(database) as connection:
            connection.executescript(
                """
                CREATE TABLE credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT UNIQUE NOT NULL,
                    credential_data TEXT NOT NULL
                );
                CREATE TABLE primary_credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT UNIQUE NOT NULL,
                    credential_data TEXT NOT NULL
                );
                CREATE TABLE config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL DEFAULT (unixepoch())
                );
                """
            )
            connection.executemany(
                "INSERT INTO credentials (filename, credential_data) VALUES (?, ?)",
                [
                    (record["filename"], json.dumps(record["credential_data"]))
                    for record in fixture["credentials"]
                ],
            )
            connection.executemany(
                "INSERT INTO primary_credentials (filename, credential_data) VALUES (?, ?)",
                [
                    (record["filename"], json.dumps(record["credential_data"]))
                    for record in fixture["primary_credentials"]
                ],
            )
            connection.executemany(
                "INSERT INTO config (key, value) VALUES (?, ?)",
                [(key, json.dumps(value)) for key, value in fixture["legacy_config"].items()],
            )
            connection.commit()


if __name__ == "__main__":
    unittest.main()
