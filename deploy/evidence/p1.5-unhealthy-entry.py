"""Mutate one harmless fixture key, then stay unavailable for rollback rehearsal."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

credentials = Path(os.getenv("CREDENTIALS_DIR", "backend/data/creds"))
with closing(sqlite3.connect(credentials / "credentials.db")) as connection:
    connection.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
        ("p1_5_rehearsal_marker", json.dumps("mutated-by-unhealthy-target")),
    )
    connection.commit()

time.sleep(600)
