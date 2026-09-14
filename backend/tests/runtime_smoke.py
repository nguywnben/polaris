"""Runtime smoke test shared by local CI and the container build."""

from __future__ import annotations

import argparse
import sys

import httpx

SMOKE_PASSWORD = "Polaris-Smoke-2026"


def require_status(response: httpx.Response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(
            f"{label} returned HTTP {response.status_code}; expected {expected}. "
            f"Response: {response.text[:500]}"
        )


def run_smoke(base_url: str, expect_fresh_setup: bool, setup_token: str = "") -> None:
    with httpx.Client(
        base_url=base_url.rstrip("/"), timeout=10.0, follow_redirects=False
    ) as client:
        health = client.get("/health")
        require_status(health, 200, "Liveness check")

        ready = client.get("/ready")
        require_status(ready, 200, "Readiness check")

        dashboard = client.get("/dashboard", headers={"Accept-Encoding": "gzip"})
        require_status(dashboard, 200, "Management console")
        if "Content-Security-Policy" not in dashboard.headers:
            raise RuntimeError("Management console response is missing Content-Security-Policy.")
        if "/frontend/console.js" not in dashboard.text:
            raise RuntimeError("Management console does not reference the JavaScript bundle.")
        if "/frontend/console.css" not in dashboard.text:
            raise RuntimeError("Management console does not reference the stylesheet bundle.")
        script_bundle = client.get("/frontend/console.js?v=smoke")
        require_status(script_bundle, 200, "Frontend JavaScript bundle")
        if "function toggleMobileMenu" not in script_bundle.text:
            raise RuntimeError("Frontend JavaScript bundle is incomplete.")
        style_bundle = client.get("/frontend/console.css?v=smoke")
        require_status(style_bundle, 200, "Frontend stylesheet bundle")
        if "@media" not in style_bundle.text:
            raise RuntimeError("Frontend stylesheet bundle is incomplete.")
        setup_status = client.get("/api/auth/setup/status")
        require_status(setup_status, 200, "Setup status")
        setup_payload = setup_status.json()
        setup_required = bool(setup_payload.get("setup_required"))
        if expect_fresh_setup and not setup_required:
            raise RuntimeError("Smoke environment was expected to require initial setup.")

        if setup_required:
            token_required = bool(setup_payload.get("setup_token_required"))
            if token_required and not setup_token:
                raise RuntimeError("Remote smoke setup requires --setup-token.")
            setup_body = {
                "password": SMOKE_PASSWORD,
                "confirm_password": SMOKE_PASSWORD,
            }
            if setup_token:
                setup_body["setup_token"] = setup_token
            setup = client.post(
                "/api/auth/setup",
                json=setup_body,
            )
            require_status(setup, 200, "Initial setup")
        else:
            login = client.post("/api/auth/login", json={"password": SMOKE_PASSWORD})
            require_status(login, 200, "Smoke login")

        config = client.get("/api/config/get")
        require_status(config, 200, "Authenticated configuration request")

        canonical_credentials = client.get("/api/credentials/status?mode=provider")
        require_status(canonical_credentials, 200, "Canonical credential route")

        legacy_credentials = client.get("/api/creds/status?mode=provider")
        require_status(legacy_credentials, 404, "Removed beta credential route")

        invalid_inference = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-polaris-invalid"},
            json={
                "model": "polaris",
                "messages": [{"role": "user", "content": "smoke test"}],
            },
        )
        require_status(invalid_inference, 401, "Invalid API key rejection")
        invalid_payload = invalid_inference.json()
        if invalid_payload.get("error", {}).get("type") != "authentication_error":
            raise RuntimeError("OpenAI authentication errors do not use the stable SDK schema.")
        if not invalid_inference.headers.get("x-request-id"):
            raise RuntimeError("Inference responses must include X-Request-ID.")

        logout = client.post("/api/auth/logout")
        require_status(logout, 200, "Logout")
        require_status(client.get("/api/config/get"), 401, "Logged-out configuration request")

        login = client.post("/api/auth/login", json={"password": SMOKE_PASSWORD})
        require_status(login, 200, "Login after logout")
        require_status(client.get("/api/config/get"), 200, "Restored authenticated session")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:4283")
    parser.add_argument("--expect-fresh-setup", action="store_true")
    parser.add_argument("--setup-token", default="")
    args = parser.parse_args()

    try:
        run_smoke(args.base_url, args.expect_fresh_setup, args.setup_token)
    except Exception as exc:
        print(f"Runtime smoke test failed: {exc}", file=sys.stderr)
        return 1

    print("Runtime smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
