"""Create a NEW SQLite directory containing fictional credentials, without network IO."""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MARKER = "polaris-synthetic-database.v1"


def _new_target(target):
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=False)
    return target


async def seed_database(target: Path, *, full: bool = False) -> dict:
    """Refuse every existing destination; never reset or import operator data."""
    target = await asyncio.to_thread(_new_target, target)
    if str(ROOT / "backend") not in sys.path:
        sys.path.insert(0, str(ROOT / "backend"))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from core.storage.sqlite_manager import SQLiteManager

    from tools.demo_credentials import build_records

    now = int(time.time())
    records = build_records(now)
    storage = SQLiteManager()
    # Use the local backend explicitly; ambient PostgreSQL/MongoDB settings are irrelevant.
    with patch.dict(os.environ, {"CREDENTIALS_DIR": str(target)}):
        await storage.initialize()
    try:
        for record in records:
            if not await storage.store_credential(
                record["filename"], record["data"], mode="primary"
            ):
                raise RuntimeError("Failed to persist a synthetic credential.")
            if not await storage.update_credential_state(
                record["filename"], record["state"], mode="primary"
            ):
                raise RuntimeError("Failed to persist a synthetic credential state.")
        counts = dict(Counter(record["variant"] for record in records))
        report = {
            "marker": MARKER,
            "fidelity_version": 2,
            "created_at": now,
            "provider_count": len(counts),
            "credential_count": len(records),
            "counts": counts,
        }
        if full:
            from tools.demo_application import seed_application

            report.update(await seed_application(storage, records, target, now))
        fixtures = {
            record["filename"]: {
                "variant": record["variant"],
                "sources": record["sources"],
                "models": record["data"]["model_ids"],
                "responses": record["upstream"],
                "status": 403 if record["number"] == 5 else 200,
            }
            for record in records
        }
        for key, value in (("demo_dataset_v1", report), ("demo_upstream_v2", fixtures)):
            if not await storage.set_config(key, value):
                raise RuntimeError("Failed to persist synthetic dataset metadata.")
        # The application writes insertion time, while this isolated corpus
        # represents imported history. No operator DB is accepted by this seeder.
        with closing(sqlite3.connect(target / "credentials.db")) as database:
            database.execute("UPDATE primary_credentials SET created_at = ?", (now - 40 * 86400,))
            database.commit()
        if full:
            from tools.demo_application import create_demo_backup

            report["backup"] = await create_demo_backup(target)
            if not await storage.set_config("demo_dataset_v1", report):
                raise RuntimeError("Failed to persist demo backup metadata.")
        return report
    finally:
        await storage.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "temp/round2-demo/credentials")
    parser.add_argument("--full", action="store_true", help="Include all application data families")
    args = parser.parse_args()
    report = asyncio.run(seed_database(args.directory, full=args.full))
    print(
        json.dumps(
            {"database": str(args.directory.resolve() / "credentials.db"), **report}, indent=2
        )
    )


if __name__ == "__main__":
    main()
