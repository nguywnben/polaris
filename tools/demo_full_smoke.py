"""Read persisted demo data through real HTTP and Chromium, without API mocks."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse

from design_consistency_smoke import ROUTES
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "Polaris-Demo-Only-2026!"


def verify_data(context, base, directory):
    with closing(sqlite3.connect(directory / "credentials.db")) as database:
        manifest = json.loads(
            database.execute("SELECT value FROM config WHERE key='demo_dataset_v1'").fetchone()[0]
        )
        # The public dashboard contract rounds each credential aggregate to 6 decimals.
        public_cost = round(
            sum(
                round(row[0] / 1e9, 6)
                for row in database.execute(
                    "SELECT SUM(cost_nanos) FROM durable_usage_ledger WHERE kind='usage' GROUP BY credential_ref"
                )
            ),
            6,
        )

    def get(path):
        response = context.request.get(base + path)
        assert response.ok, (path, response.status)
        return response.json()

    fleet = get("/api/credentials/status?mode=provider&limit=100")
    assert fleet["total"] == manifest["credential_count"]
    totals = get("/api/usage/aggregated?period=all")["data"]
    assert totals["total_calls"] == manifest["activity"]["requests"]
    assert totals["successful_calls"] + totals["failed_calls"] == totals["total_calls"]
    assert totals["total_tokens"] == manifest["activity"]["tokens"]
    assert totals["total_cost_usd"] == public_cost
    keys = get("/api/virtual-keys")["data"]
    assert len(keys) == 8
    assert {key["status"] for key in keys} == {"active", "expired", "disabled", "revoked"}
    assert len(get("/api/identity/identities")["identities"]) == 5
    assert len(get("/api/identity/sessions")["sessions"]) >= 3
    catalog = get("/api/model-catalog")
    assert catalog["catalog"] and catalog["blacklist"]
    routing = get("/api/observability/routing?limit=100")
    assert routing["selected_count"] > 0, routing
    assert all(d["reason"] != "candidate_capacity" for d in routing["decisions"])
    for provider in ("google_antigravity", "grok", "codex", "claude_code", "kiro", "muse_code"):
        result = get(f"/api/credentials/quota/demo-{provider}-01.json?mode=provider")
        assert result.get("supported", True) and result["success"], provider
    return {
        "credentials": fleet["total"],
        "requests": totals["total_calls"],
        "tokens": totals["total_tokens"],
        "cost_usd": totals["total_cost_usd"],
        "keys": len(keys),
        "oauth_quota_families": 6,
    }


def main(base, directory, data_only=False):
    parsed = urlparse(base)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
        raise ValueError("Only a loopback demo may be tested.")
    output = directory.parent / "verification"
    output.mkdir(exist_ok=True)
    report = {
        "pages": [],
        "api": {},
        "dialogs": [],
        "playground": [],
        "errors": [],
        "network_errors": [],
        "expected_api_errors": [],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            locale="vi-VN", reduced_motion="reduce", viewport={"width": 1440, "height": 900}
        )
        # Block external resources, never fulfill/mutate application API responses.
        context.route("https://**", lambda route: route.abort())
        probe = context.request.get(base + "/api/auth/setup/status")
        assert probe.headers.get("x-polaris-synthetic-data") == "true", "Not a demo server"
        assert context.request.get(base + "/api/credentials/status?mode=provider").status == 401
        page = context.new_page()
        page.on("pageerror", lambda error: report["errors"].append(str(error)))
        expected_errors = {
            (
                f"/api/credentials/quota/demo-{variant}-05.json?mode=provider",
                502 if variant == "muse_code" else 400,
            )
            for variant in (
                "claude_code",
                "codex",
                "google_antigravity",
                "grok",
                "kiro",
                "muse_code",
            )
        } | {("/api/credentials/quota/demo-grok-07.json?mode=provider", 502)}

        def observe_response(response):
            if response.status >= 400 and response.url.startswith(base + "/api/"):
                url = response.url.removeprefix(base)
                bucket = (
                    "expected_api_errors"
                    if (url, response.status) in expected_errors
                    else "network_errors"
                )
                report[bucket].append({"url": url, "status": response.status})

        page.on("response", observe_response)

        def capture(name):
            for width in (1440, 390):
                page.set_viewport_size({"width": width, "height": 900})
                for theme in ("light", "dark"):
                    page.emulate_media(color_scheme=theme)
                    expect(page.locator("html")).to_have_attribute("data-theme", theme)
                    page.wait_for_timeout(100)
                    report["pages"].append(
                        {
                            "surface": name,
                            "width": width,
                            "theme": theme,
                            "overflow": page.evaluate(
                                "document.documentElement.scrollWidth > innerWidth + 1"
                            ),
                        }
                    )
                    page.screenshot(
                        path=str(output / f"{name}-{width}-{theme}.png"), full_page=True
                    )
            page.set_viewport_size({"width": 1440, "height": 900})

        try:
            if probe.json()["setup_required"]:
                page.goto(base + "/setup", wait_until="networkidle")
                capture("setup")
                page.locator("#setupPassword").fill(PASSWORD)
                page.locator("#setupPasswordConfirm").fill(PASSWORD)
                page.locator("#setupSubmitButton").click()
                expect(page).to_have_url(base + "/dashboard")
            else:
                page.goto(base + "/login", wait_until="networkidle")
                capture("login")
                page.locator("#loginPassword").fill(PASSWORD)
                page.locator('#loginForm button[type="submit"]').click()
                expect(page).to_have_url(base + "/dashboard")

            if data_only:
                report["reconciled"] = verify_data(context, base, directory)
                page.goto(base + "/credentials", wait_until="networkidle")
                page.locator("#primaryPageSizeSelect").select_option("100")
                for provider in (
                    "google_antigravity",
                    "grok",
                    "codex",
                    "claude_code",
                    "kiro",
                    "muse_code",
                    "ollama",
                ):
                    page.locator("#primaryProviderFilter").select_option(provider)
                    selection = page.locator(
                        f'[data-credential-select][data-filename="demo-{provider}-01.json"]'
                    )
                    expect(selection).to_be_visible()
                    selection.locator(
                        'xpath=ancestor::div[contains(@class,"cred-card")][1]'
                    ).locator('[data-credential-command="manage"]').click()
                    expect(page.get_by_role("dialog").last).to_be_visible()
                    expect(page.get_by_role("dialog").last).to_contain_text(
                        f"demo-{provider}-01.json"
                    )
                    expect(
                        page.get_by_role("dialog").last.locator('[aria-busy="true"]')
                    ).to_have_count(0)
                    page.wait_for_load_state("networkidle")
                    page.screenshot(path=str(output / f"{provider}-management.png"))
                    report["dialogs"].append(provider)
                    page.locator(".credential-management-modal [data-dialog-close]").click()
                assert not report["errors"], report["errors"]
                assert not report["network_errors"], report["network_errors"]
                print(json.dumps(report["reconciled"]))
                return

            endpoints = (
                "/api/credentials/status?mode=provider&limit=100",
                "/api/model-catalog",
                "/api/usage/aggregated",
                "/api/virtual-keys",
                "/api/quality-policy",
                "/api/identity/identities",
                "/api/identity/sessions",
                "/api/traces?page_size=6",
                "/api/audit/events?page_size=5",
                "/api/observability/health?window_seconds=900",
                "/api/observability/routing",
            )
            for endpoint in endpoints:
                response = context.request.get(base + endpoint)
                assert response.ok, (endpoint, response.status, response.text()[:250])
                payload = response.json()
                report["api"][endpoint] = {"status": response.status, "fields": list(payload)}

            for route in ROUTES:
                page.goto(base + "/" + route, wait_until="networkidle")
                expect(page.locator(".tab-content.active")).to_be_visible()
                capture(route.replace("?view=", "-"))

            for route, selector, name in (
                ("credentials", '[data-credential-command="manage"]', "credential"),
                ("access", '[data-ui-action="virtual-key-usage"]', "key-usage"),
                ("access", '[data-ui-action="virtual-key-edit"]:not([disabled])', "key-edit"),
                ("activity", '[data-ui-action="view-trace-detail"]', "trace"),
                ("activity?view=audit", '[data-ui-action="view-audit-detail"]', "audit"),
            ):
                page.goto(base + "/" + route, wait_until="networkidle")
                page.locator(selector).first.click()
                expect(page.get_by_role("dialog").last).to_be_visible()
                capture(name + "-dialog")
                if name == "credential":
                    page.locator(".credential-management-modal [data-dialog-close]").click()
                elif name == "key-edit":
                    page.locator("[data-virtual-key-cancel]").click()
                else:
                    page.keyboard.press("Escape")
                report["dialogs"].append(name)

            # The isolated database does not authorize inference or replace its
            # pipeline with success text. Unsupported outbound operations fail.
            requests = {
                "openai_chat": {"messages": [{"role": "user", "content": "DEMO"}]},
                "openai_responses": {"input": "DEMO"},
                "anthropic_messages": {
                    "messages": [{"role": "user", "content": "DEMO"}],
                    "max_tokens": 32,
                },
                "gemini": {"contents": [{"role": "user", "parts": [{"text": "DEMO"}]}]},
            }
            for protocol, body in requests.items():
                for stream in (False, True):
                    response = context.request.post(
                        base + "/api/playground/runs",
                        headers={"Origin": base},
                        data={
                            "protocol": protocol,
                            "model": "polaris",
                            "stream": stream,
                            "request": body,
                        },
                    )
                    assert not response.ok or "error" in response.text().lower(), (
                        protocol,
                        stream,
                        response.text()[:300],
                    )
                    report["playground"].append(
                        {"protocol": protocol, "stream": stream, "status": response.status}
                    )

            with closing(sqlite3.connect(directory / "credentials.db")) as database:
                manifest = json.loads(
                    database.execute(
                        "SELECT value FROM config WHERE key='demo_dataset_v1'"
                    ).fetchone()[0]
                )
            archive = directory.parent / manifest["backup"]["filename"]
            response = context.request.post(
                base + "/api/backups/validate",
                headers={"Origin": base},
                multipart={
                    "passphrase": PASSWORD,
                    "conflict_policy": "replace",
                    "archive": {
                        "name": archive.name,
                        "mimeType": "application/octet-stream",
                        "buffer": archive.read_bytes(),
                    },
                },
            )
            assert response.ok, response.text()[:300]
            report["backup"] = response.json()
            # Separate anonymous context verifies the populated instance's actual login page.
            anonymous = browser.new_context(locale="vi-VN")
            login = anonymous.new_page()
            login.goto(base + "/login", wait_until="networkidle")
            expect(login.locator("#loginPassword")).to_be_visible()
            login.screenshot(path=str(output / "login-populated.png"), full_page=True)
            anonymous.close()
            assert not report["errors"], report["errors"]
            unexpected = [
                r
                for r in report["network_errors"]
                if not r["url"].startswith("/api/playground/runs")
            ]
            assert not unexpected, unexpected
        finally:
            (output / ("data-report.json" if data_only else "report.json")).write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            browser.close()
    print(
        json.dumps(
            {
                "captures": len(report["pages"]),
                "dialogs": report["dialogs"],
                "playground": len(report["playground"]),
                "overflow_cases": [r for r in report["pages"] if r["overflow"]],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:4286")
    parser.add_argument("--directory", type=Path, default=ROOT / "temp/round2-full/credentials")
    parser.add_argument("--data-only", action="store_true")
    args = parser.parse_args()
    main(args.base, args.directory.resolve(), args.data_only)
