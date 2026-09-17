"""Read-only relational/temporal audit of the persisted synthetic corpus."""

import argparse
import json
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def audit_database(directory):
    from core.pricing import calculate_cost_usd
    from core.smart_routing import MAX_ROUTING_CANDIDATES
    from core.usage_ledger import UsageLedgerEntry, usd_to_nanos
    from core.virtual_keys import VirtualKey

    from tools.demo_preview import validate_demo_database

    manifest = validate_demo_database(directory)
    with closing(sqlite3.connect(directory / "credentials.db")) as db:
        db.row_factory = sqlite3.Row
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        configs = {
            r["key"]: json.loads(r["value"]) for r in db.execute("SELECT key,value FROM config")
        }
        credentials = {
            r["filename"]: dict(r) for r in db.execute("SELECT * FROM primary_credentials")
        }
        usage = [
            UsageLedgerEntry(**json.loads(r[0]))
            for r in db.execute("SELECT payload FROM durable_usage_ledger WHERE kind='usage'")
        ]
        traces = {r[0] for r in db.execute("SELECT request_id FROM request_traces")}
        outcomes = dict(db.execute("SELECT outcome,COUNT(*) FROM request_traces GROUP BY outcome"))
    fixtures = configs["demo_upstream_v2"]
    keys = {k["id"]: VirtualKey.from_storage_dict(k) for k in configs["virtual_keys"]}
    assert len(credentials) == manifest["credential_count"]
    assert len(credentials) <= MAX_ROUTING_CANDIDATES, "Corpus exceeds production routing capacity"
    assert len(usage) == manifest["activity"]["requests"]
    assert set(fixtures) == set(credentials)
    assert sum(u.total_tokens for u in usage) == manifest["activity"]["tokens"]
    assert sum(u.cost_nanos for u in usage) == manifest["activity"]["cost_nanos"]
    for filename, row in credentials.items():
        data = json.loads(row["credential_data"])
        calls = [u for u in usage if u.credential_ref == filename]
        assert row["call_count"] == len(calls), f"Counter mismatch: {filename}"
        assert row["last_success"] == max(
            (u.occurred_at for u in calls if u.success), default=None
        ), f"Last success mismatch: {filename}"
        assert all(row["created_at"] <= u.occurred_at for u in calls), (
            f"Calls predate credential: {filename}"
        )
        assert all(u.model in data["model_ids"] for u in calls), f"Unknown model: {filename}"
        assert fixtures[filename]["sources"]
        assert not any("demo-" in model for model in data["model_ids"])
        if data["credential_type"] == "api_key" or data["provider"] in {"kiro", "muse_code"}:
            assert not row["user_email"], f"Invented email: {filename}"
        if data["provider"] != "google_antigravity":
            assert not row["tier"], f"Invented tier: {filename}"
        if row["disabled"]:
            assert all(u.occurred_at < manifest["created_at"] - 86400 for u in calls)
    for entry in usage:
        assert entry.request_id in traces
        assert (
            entry.total_tokens == entry.input_tokens + entry.output_tokens + entry.reasoning_tokens
        )
        assert entry.cached_tokens + entry.cache_creation_tokens <= entry.input_tokens
        assert entry.cost_nanos == usd_to_nanos(
            calculate_cost_usd(
                entry.model,
                provider=entry.provider,
                input_tokens=entry.input_tokens,
                output_tokens=entry.output_tokens,
                cached_tokens=entry.cached_tokens,
                cache_creation_tokens=entry.cache_creation_tokens,
                reasoning_tokens=entry.reasoning_tokens,
            )
        ), "Cost bypassed the production calculator"
        key = keys[entry.api_key_id]
        assert key.created_at <= entry.occurred_at < key.expires_at
        assert not key.revoked_at or entry.occurred_at < key.revoked_at
        assert "inference:openai" in key.scopes
        daily = sum(
            u.cost_nanos
            for u in usage
            if u.api_key_id == key.id
            and entry.occurred_at - 86400 < u.occurred_at <= entry.occurred_at
        )
        assert daily <= usd_to_nanos(key.budget_daily_usd), (
            f"Impossible key budget history: {key.id}"
        )
    return {
        "database": str(directory / "credentials.db"),
        "integrity": "ok",
        "providers": len(manifest["counts"]),
        "credentials": len(credentials),
        "usage": len(usage),
        "traces": len(traces),
        "outcomes": outcomes,
        "authentication_types": dict(
            Counter(
                json.loads(r["credential_data"])["credential_type"] for r in credentials.values()
            )
        ),
        "virtual_keys": len(keys),
        "source_indexed_fixtures": len(fixtures),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    print(json.dumps(audit_database(parser.parse_args().directory.resolve()), indent=2))
