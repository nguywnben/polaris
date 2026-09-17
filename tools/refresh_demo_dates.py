"""Move a marked synthetic demo database's relative timeline to the current day."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MARKER = "polaris-synthetic-database.v1"
DATE_KEYS = {
    "created_at",
    "updated_at",
    "last_success",
    "expires_at",
    "expiry",
    "oauth_expires_at",
    "reset_time",
    "resettime",
    "resets_at",
    "observed_at",
    "occurred_at",
    "started_at",
    "completed_at",
    "transitioned_at",
    "revoked_at",
    "issued_at",
    "first_seen_at",
    "last_seen_at",
    "last_used_at",
    "nextdatereset",
    "resetdate",
    "freetrialexpiry",
    "expiresat",
    "billingperiodend",
}


def _date_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in DATE_KEYS or normalized.endswith("_at")


def _shift_value(value: Any, delta: float) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value + delta
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return (parsed + timedelta(seconds=delta)).isoformat()
    return value


def _shift_json(value: Any, delta: float, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        if parent_key == "model_cooldowns":
            return {key: _shift_value(item, delta) for key, item in value.items()}
        return {
            key: _shift_value(_shift_json(item, delta, key), delta)
            if _date_key(key)
            else _shift_json(item, delta, key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_shift_json(item, delta, parent_key) for item in value]
    return value


def _shift_json_text(raw: str, delta: float) -> str:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw
    return json.dumps(_shift_json(value, delta), ensure_ascii=False, separators=(",", ":"))


def _shift_text(raw: str | None, delta: float) -> str | None:
    if raw is None:
        return None
    return _shift_value(raw, delta)


def refresh_log(log_file: Path, database: Path) -> float:
    """Align the synthetic text log with the latest usage record in the DB."""
    if not log_file.is_file():
        return 0.0
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT MAX(occurred_at) FROM durable_usage_ledger").fetchone()
    if not row or row[0] is None:
        return 0.0
    content = log_file.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^(?P<stamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))(?= \[)",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(content))
    if not matches:
        return 0.0
    latest_log = max(
        datetime.fromisoformat(match.group("stamp").replace("Z", "+00:00")) for match in matches
    )
    latest_db = datetime.fromtimestamp(float(row[0]), timezone.utc)
    delta = (latest_db - latest_log).total_seconds()
    if abs(delta) < 0.5:
        return 0.0

    def replace(match: re.Match[str]) -> str:
        shifted = datetime.fromisoformat(match.group("stamp").replace("Z", "+00:00"))
        return (shifted + timedelta(seconds=delta)).isoformat()

    log_file.write_text(pattern.sub(replace, content), encoding="utf-8")
    return delta


def refresh_database(database: Path, *, target_now: int | None = None) -> dict[str, Any]:
    database = database.resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    from tools.demo_preview import validate_demo_database

    validate_demo_database(database.parent)

    target_now = int(time.time()) if target_now is None else int(target_now)
    connection = sqlite3.connect(database, timeout=30)
    try:
        connection.execute("PRAGMA busy_timeout = 30000")
        row = connection.execute(
            "SELECT value FROM config WHERE key = ?", ("demo_dataset_v1",)
        ).fetchone()
        if not row:
            raise ValueError("Database is missing the synthetic dataset metadata.")
        report = json.loads(row[0])
        if report.get("marker") != MARKER:
            raise ValueError("Refusing to modify a database without the synthetic marker.")
        source_now = int(report["created_at"])
        delta = target_now - source_now
        if delta == 0:
            return {
                "database": str(database),
                "source": source_now,
                "target": target_now,
                "shift_seconds": 0,
            }

        connection.execute("BEGIN IMMEDIATE")
        # Rewrite credential JSON while retaining all provider-specific fields.
        rows = connection.execute(
            "SELECT id, credential_data, model_cooldowns FROM primary_credentials"
        ).fetchall()
        for row_id, raw, cooldowns in rows:
            connection.execute(
                "UPDATE primary_credentials SET credential_data = ?, model_cooldowns = ? WHERE id = ?",
                (
                    _shift_json_text(raw, delta),
                    json.dumps(
                        _shift_json(json.loads(cooldowns or "{}"), delta, "model_cooldowns")
                    ),
                    row_id,
                ),
            )
        connection.execute(
            "UPDATE primary_credentials SET last_success = CASE WHEN last_success IS NULL THEN NULL ELSE last_success + ? END, "
            "created_at = created_at + ?, updated_at = updated_at + ?",
            (delta, delta, delta),
        )

        for table, json_column in (("durable_usage_ledger", "payload"),):
            rows = connection.execute(f"SELECT rowid, {json_column} FROM {table}").fetchall()
            for row_id, raw in rows:
                connection.execute(
                    f"UPDATE {table} SET {json_column} = ? WHERE rowid = ?",
                    (_shift_json_text(raw, delta), row_id),
                )
        connection.execute(
            "UPDATE durable_usage_ledger SET created_at = created_at + ?, "
            "expires_at = CASE WHEN expires_at IS NULL THEN NULL ELSE expires_at + ? END, "
            "transitioned_at = CASE WHEN transitioned_at IS NULL THEN NULL ELSE transitioned_at + ? END, "
            "occurred_at = CASE WHEN occurred_at IS NULL THEN NULL ELSE occurred_at + ? END",
            (delta, delta, delta, delta),
        )
        rows = connection.execute(
            "SELECT sequence, started_at, completed_at FROM request_traces"
        ).fetchall()
        for sequence, started_at, completed_at in rows:
            connection.execute(
                "UPDATE request_traces SET started_at = ?, completed_at = ? WHERE sequence = ?",
                (_shift_text(started_at, delta), _shift_text(completed_at, delta), sequence),
            )
        rows = connection.execute("SELECT sequence, occurred_at FROM audit_events").fetchall()
        for sequence, occurred_at in rows:
            connection.execute(
                "UPDATE audit_events SET occurred_at = ? WHERE sequence = ?",
                (_shift_text(occurred_at, delta), sequence),
            )
        for table in ("management_identities", "management_role_bindings"):
            rows = connection.execute(
                f"SELECT rowid, created_at, updated_at FROM {table}"
            ).fetchall()
            for row_id, created_at, updated_at in rows:
                connection.execute(
                    f"UPDATE {table} SET created_at = ?, updated_at = ? WHERE rowid = ?",
                    (_shift_text(created_at, delta), _shift_text(updated_at, delta), row_id),
                )
        rows = connection.execute(
            "SELECT singleton_id, updated_at FROM oidc_policy_revision"
        ).fetchall()
        for singleton_id, updated_at in rows:
            connection.execute(
                "UPDATE oidc_policy_revision SET updated_at = ? WHERE singleton_id = ?",
                (_shift_text(updated_at, delta), singleton_id),
            )
        row = connection.execute(
            "SELECT value FROM config WHERE key = ?", ("demo_dataset_v1",)
        ).fetchone()
        connection.execute(
            "UPDATE config SET value = ?, updated_at = updated_at + ? WHERE key = ?",
            (_shift_json_text(row[0], delta), delta, "demo_dataset_v1"),
        )
        rows = connection.execute("SELECT key, value FROM config").fetchall()
        for key, value in rows:
            if key == "demo_dataset_v1":
                continue
            connection.execute(
                "UPDATE config SET value = ?, updated_at = updated_at + ? WHERE key = ?",
                (_shift_json_text(value, delta), delta, key),
            )
        connection.commit()
        return {
            "database": str(database),
            "source": source_now,
            "target": target_now,
            "shift_seconds": delta,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=ROOT / "temp/round2-full-ready/credentials/credentials.db"
    )
    parser.add_argument("--log-file", type=Path, default=None)
    args = parser.parse_args()
    result = refresh_database(args.database)
    log_file = args.log_file or args.database.resolve().parent.parent / "demo-runtime.log"
    result["log_shift_seconds"] = refresh_log(log_file.resolve(), args.database.resolve())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
