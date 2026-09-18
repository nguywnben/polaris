"""Transactionally replace only the marked demo corpus, preserving login settings.

Stop the demo server first to avoid stale runtime caches. A complete SQLite backup
is created before any write; real/unmarked credentials or unknown schemas fail closed.
"""

import argparse
import json
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from tools.demo_preview import validate_demo_database

TABLES = ("primary_credentials", "durable_usage_ledger", "request_traces", "audit_events")
CONFIGS = (
    "demo_dataset_v1",
    "demo_upstream_v2",
    "virtual_keys",
    "quality_policy_document",
    "virtual_model_pool",
    "model_route_blacklist",
    "language",
)


def update_database(database: Path, source: Path):
    database, source = database.resolve(), source.resolve()
    if database == source or database.name != "credentials.db" or source.name != "credentials.db":
        raise ValueError("Use distinct demo credentials.db files.")
    validate_demo_database(database.parent)
    metadata = validate_demo_database(source.parent)
    if metadata.get("fidelity_version") != 2 or metadata.get("coverage") != "full-application":
        raise ValueError("Source must be a verified, full v2 synthetic corpus.")
    from tools.audit_demo_database import audit_database

    audit_database(source.parent)
    source_root, target_root = source.parent.parent, database.parent.parent
    archive = metadata["backup"]["filename"]
    if Path(archive).name != archive or not (source_root / archive).is_file():
        raise ValueError("Invalid or missing demo backup artifact.")
    if not (source_root / "demo-runtime.log").is_file():
        raise ValueError("Missing demo log artifact.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = database.with_name(f"credentials.before-fidelity-{stamp}.db")
    with closing(sqlite3.connect(database)) as db, closing(sqlite3.connect(source)) as staged:
        for connection in (db, staged):
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Database integrity check failed.")
        columns = {}
        for table in TABLES:
            columns[table] = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]
            if not columns[table] or columns[table] != [
                r[1] for r in staged.execute(f"PRAGMA table_info({table})")
            ]:
                raise ValueError("Source/target demo schemas differ.")
        with closing(sqlite3.connect(backup)) as saved:
            db.backup(saved)
        db.execute("ATTACH DATABASE ? AS fixture", (str(source),))
        try:
            db.execute("BEGIN IMMEDIATE")
            for table in TABLES:
                names = ",".join(f'"{name}"' for name in columns[table])
                db.execute(f"DELETE FROM main.{table}")
                db.execute(
                    f"INSERT INTO main.{table} ({names}) SELECT {names} FROM fixture.{table}"
                )
            for key in CONFIGS:
                row = staged.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
                if row is None:
                    raise ValueError("Source corpus is incomplete.")
                db.execute("DELETE FROM main.config WHERE key=?", (key,))
                db.execute(
                    "INSERT INTO main.config (key,value,updated_at) VALUES (?,?,unixepoch())",
                    (key, row[0]),
                )
            db.execute("DELETE FROM main.config WHERE key='demo_quota_snapshots_v1'")
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("Demo references failed integrity validation.")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.execute("DETACH DATABASE fixture")
    # Logs and the sample portable backup are demo artifacts, not database tables.
    log = target_root / "demo-runtime.log"
    if log.exists():
        shutil.copy2(log, target_root / f"demo-runtime.before-fidelity-{stamp}.log")
    shutil.copy2(source_root / "demo-runtime.log", log)
    shutil.copy2(source_root / archive, target_root / archive)
    return {
        "database": str(database),
        "backup": str(backup),
        "credentials": metadata["credential_count"],
        "activity": metadata["activity"],
        "login_preserved": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(update_database(args.database, args.source), indent=2))
