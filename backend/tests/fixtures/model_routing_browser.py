"""Disposable P3.6 browser fixture: real app/SQLite, synthetic discovery, no upstream I/O.

Run from the repository root: python backend/tests/fixtures/model_routing_browser.py
The console listens only on 127.0.0.1:4296. Its temporary state is removed on normal exit.
The fixture passphrase is intentionally public and grants access only to disposable local data.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def serve() -> None:
    backend = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(backend))
    scratch = backend.parent / "temp" / "tests"
    scratch.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="p36-browser-", dir=scratch) as directory:
        os.environ.update(
            PYTHON_DOTENV_DISABLED="1",
            CREDENTIALS_DIR=directory,
            POSTGRESQL_URI="",
            MONGODB_URI="",
            PORT="4296",
            HOST="127.0.0.1",
            PANEL_PASSWORD="p3.6-local-browser-fixture",
            POLARIS_RUNTIME_MODE="standalone",
        )
        for key in (
            "ROUTING_STRATEGY",
            "PREFERRED_PROVIDER",
            "CREDENTIALS_JSON",
            "CODE_ASSIST_CREDENTIALS_JSON",
        ):
            os.environ.pop(key, None)

        from core.model_pool import model_catalog_service
        from main import main

        async def discover() -> dict[str, list[str]]:
            return {
                "codex": ["fixture-model-a", "fixture-model-b"],
                "openai": ["fixture-model-b"],
            }

        model_catalog_service._loader = discover
        main()


if __name__ == "__main__":
    serve()
