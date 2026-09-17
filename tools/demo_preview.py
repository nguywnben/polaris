"""Serve a marked synthetic SQLite dataset on loopback, with outbound IO denied.

This developer-only entry point is never imported by the production application.
It supplies stored observations for quota/model discovery; local mutations still
use the real application/database. OAuth and inference are intentionally offline.
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from collections import defaultdict
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate_demo_database(directory):
    path = directory.resolve() / "credentials.db"
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as db:
        row = db.execute("SELECT value FROM config WHERE key = ?", ("demo_dataset_v1",)).fetchone()
        if not row or json.loads(row[0]).get("marker") != "polaris-synthetic-database.v1":
            raise ValueError("Refusing a database without the synthetic dataset marker.")
        for table in ("primary_credentials", "credentials"):
            for (raw,) in db.execute(f"SELECT credential_data FROM {table}"):
                data = json.loads(raw)
                if data.get("synthetic") is not True:
                    raise ValueError("Refusing a database containing non-synthetic credentials.")
                for field in ("api_key", "access_token", "refresh_token", "token", "client_secret"):
                    if data.get(field) and not str(data[field]).startswith("DEMO-NOT-A-REAL-"):
                        raise ValueError("Refusing credentials without fictional secret markers.")
        return json.loads(row[0])


def deny_outbound(event, args):
    """Fail closed, including direct sockets and child-process network clients."""
    if event in {
        "socket.connect",
        "socket.sendto",
        "subprocess.Popen",
        "os.system",
        "os.posix_spawn",
    }:
        raise PermissionError("DEMO: outbound connections and child processes are disabled.")
    if event == "socket.getaddrinfo" and args[0] not in {None, "127.0.0.1", "::1"}:
        raise PermissionError("DEMO: external name resolution is disabled.")


def configure_environment(directory, port):
    # Do not inherit any provider key, proxy, OIDC, database URI or .env setting.
    keep = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATHEXT", "LANG"}
    environment = {key: value for key, value in os.environ.items() if key.upper() in keep}
    os.environ.clear()
    os.environ.update(environment)
    os.environ.update(
        PYTHON_DOTENV_DISABLED="1",
        CREDENTIALS_DIR=str(directory.resolve()),
        LOG_FILE=str(directory.resolve().parent / "demo-runtime.log"),
        POSTGRESQL_URI="",
        MONGODB_URI="",
        HOST="127.0.0.1",
        PORT=str(port),
        WORKERS="1",
        ENABLE_LOG="0",
        PRICING_SYNC_ENABLED="false",
        POLARIS_RUNTIME_MODE="standalone",
    )


def create_demo_app():
    from core.model_pool import model_catalog_service
    from core.provider_registry import get_credential_provider, get_declared_credential_models
    from core.storage_adapter import get_storage_adapter
    from main import app

    from tools.demo_transport import install_transport

    install_transport()

    async def catalog():
        storage = await get_storage_adapter()
        credentials = await storage.get_all_credentials(mode="primary")
        states = await storage.get_all_credential_states(mode="primary")
        result = defaultdict(set)
        for filename, data in credentials.items():
            if data.get("synthetic") is True and not states.get(filename, {}).get("disabled"):
                result[get_credential_provider(data)].update(get_declared_credential_models(data))
        return result

    model_catalog_service._loader = catalog

    @app.middleware("http")
    async def synthetic_response_header(request, call_next):
        response = await call_next(request)
        response.headers["X-Polaris-Synthetic-Data"] = "true"
        return response

    from tools.demo_runtime import install_runtime_fixtures

    install_runtime_fixtures(app)
    return app


async def serve(directory, port):
    from hypercorn.asyncio import serve as hypercorn_serve
    from hypercorn.config import Config

    # Install after asyncio has created its internal Windows wakeup socket pair.
    sys.addaudithook(deny_outbound)
    app = create_demo_app()
    configuration = Config()
    configuration.bind = [f"127.0.0.1:{port}"]
    configuration.accesslog = None
    print(f"SYNTHETIC / OFFLINE preview: http://127.0.0.1:{port}", flush=True)
    await hypercorn_serve(app, configuration)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "temp/round2-demo/credentials")
    parser.add_argument("--port", type=int, default=4285)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use an unprivileged port between 1024 and 65535.")
    validate_demo_database(args.directory)
    configure_environment(args.directory, args.port)
    sys.path.insert(0, str(ROOT / "backend"))
    sys.path.insert(0, str(ROOT))
    asyncio.run(serve(args.directory, args.port))


if __name__ == "__main__":
    main()
