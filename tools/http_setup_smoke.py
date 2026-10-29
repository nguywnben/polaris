"""Verify remote HTTP opt-in against fresh, isolated runtimes with synthetic secrets."""

from __future__ import annotations

from unittest.mock import patch

import httpx
from browser_smoke import disposable_runtime
from runtime_isolation import isolated_runtime_environment

TOKEN = "synthetic-http-setup-token-for-smoke-2026"
PASSWORD = "Synthetic-HTTP-Owner-2026"


def check_runtime(*, allowed: bool) -> None:
    def environment(runtime, port):
        values = isolated_runtime_environment(runtime, port)
        values.update(SETUP_TOKEN=TOKEN, SETUP_ALLOW_INSECURE_HTTP=str(allowed).lower())
        return values

    with (
        patch("browser_smoke.isolated_runtime_environment", side_effect=environment),
        disposable_runtime() as base_url,
        httpx.Client(
            base_url=base_url,
            # The connection stays loopback-only; Host/Origin exercise remote ingress policy.
            headers={"Host": "192.0.2.10:4283", "Origin": "http://192.0.2.10:4283"},
            timeout=10,
            trust_env=False,
        ) as client,
    ):
        status = client.get("/api/auth/setup/status")
        assert status.status_code == 200
        transport = status.json()["checks"]["transport"]
        assert transport["code"] == ("transport_insecure_allowed" if allowed else "https_required")
        for token in (None, "wrong-token"):
            response = client.post("/api/auth/setup/preflight", json={"setup_token": token})
            assert response.status_code == 403
        preflight = client.post("/api/auth/setup/preflight", json={"setup_token": TOKEN})
        assert preflight.status_code == (200 if allowed else 409)
        payload = {"password": PASSWORD, "confirm_password": PASSWORD, "setup_token": TOKEN}
        if allowed:
            rejected = client.post("/api/auth/setup", json={**payload, "setup_token": "wrong"})
            assert rejected.status_code == 403
        created = client.post("/api/auth/setup", json=payload)
        assert created.status_code == (200 if allowed else 409)
        if not allowed:
            assert client.get("/api/auth/setup/status").json()["setup_required"] is True
            return
        cookie = created.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie and "; secure" not in cookie
        assert client.get("/api/auth/keys").status_code == 200
        assert client.post("/api/auth/logout").status_code == 200
        assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
        assert client.get("/api/auth/keys").status_code == 200
        assert client.post("/api/auth/setup", json=payload).status_code == 409


if __name__ == "__main__":
    check_runtime(allowed=False)
    check_runtime(allowed=True)
    print("HTTP setup smoke passed: default denial, opt-in setup, cookies, logout and login.")
