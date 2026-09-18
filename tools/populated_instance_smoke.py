"""Bounded populated Polaris audit, with a private offline SQLite runtime."""

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from contextlib import closing, contextmanager

from browser_smoke import ROOT, _free_port, _stop_process_tree, _wait_until_ready
from demo_full_smoke import PASSWORD
from design_consistency_smoke import AUDIT, ROUTES, SIZES
from playwright.sync_api import expect, sync_playwright


@contextmanager
def populated_runtime(output):
    runtime = output / f"runtime-{time.time_ns()}"
    directory = runtime / "credentials"
    subprocess.run(
        [sys.executable, "tools/seed_demo_database.py", "--full", "--directory", str(directory)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        timeout=90,
    )
    port = _free_port()
    log_path = runtime / "server-output.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "tools/demo_preview.py",
                "--directory",
                str(directory),
                "--port",
                str(port),
            ],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            _wait_until_ready(base, process, log_path)
            yield base, directory
        finally:
            _stop_process_tree(process)


def expand(page, root):
    for details in page.locator(f"{root} details").all():
        summary = details.locator(":scope > summary")
        if summary.is_visible() and details.get_attribute("open") is None:
            summary.click()


def inspect(page):
    result = page.evaluate(AUDIT)
    result["dialogOverflow"] = (
        page.evaluate("""() => [...document.querySelectorAll('[role=dialog],dialog[open]')]
        .filter(el=>el.checkVisibility()).filter(el=>{const r=el.getBoundingClientRect();
            return r.left < -1 || r.right > innerWidth+1 || r.top < -1 || r.bottom > innerHeight+1;
        }).map(el=>el.id||el.className)""")
    )
    result["providerIdentityWidth"] = page.locator(
        "#usageProviderSummary .usage-provider-identity"
    ).evaluate_all(
        "els=>els.filter(el=>el.checkVisibility()).map(el=>Math.round(el.getBoundingClientRect().width))"
    )
    result["scrollContainers"] = page.evaluate("""() => [...document.querySelectorAll('body *')]
        .filter(el => el.checkVisibility() && !el.closest('[inert]'))
        .flatMap(el => {
            const css = getComputedStyle(el), axes = [];
            if (['auto','scroll'].includes(css.overflowX) && el.scrollWidth > el.clientWidth + 1) axes.push('x');
            if (['auto','scroll'].includes(css.overflowY) && el.scrollHeight > el.clientHeight + 1) axes.push('y');
            return axes.length ? [{element:el.id || el.className, axes, width:el.clientWidth,
                height:el.clientHeight, scrollWidth:el.scrollWidth, scrollHeight:el.scrollHeight}] : [];
        })""")
    return result


def main(stage, strict=False, only=None):
    output = ROOT / "temp/populated-instance" / stage
    output.mkdir(parents=True, exist_ok=True)
    report = {"cases": [], "errors": [], "api_errors": [], "journeys": [], "measurements": {}}
    started = time.monotonic()
    with populated_runtime(output) as (base, directory), sync_playwright() as p:
        with closing(sqlite3.connect(directory / "credentials.db")) as database:
            manifest = json.loads(
                database.execute("SELECT value FROM config WHERE key='demo_dataset_v1'").fetchone()[
                    0
                ]
            )
        browser = p.chromium.launch()
        context = browser.new_context(
            locale="vi-VN", reduced_motion="reduce", viewport={"width": 1440, "height": 900}
        )
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        page.on("pageerror", lambda error: report["errors"].append(str(error)))
        page.on(
            "response",
            lambda response: (
                report["api_errors"].append(
                    {"path": response.url.removeprefix(base), "status": response.status}
                )
                if response.url.startswith(base + "/api/") and response.status >= 400
                else None
            ),
        )

        def capture(name, full=False):
            if only and not any(name.startswith(prefix) for prefix in only):
                return
            if len(report["cases"]) >= 400 or time.monotonic() - started > 18 * 60:
                raise RuntimeError("Bounded audit budget exhausted; report retained.")
            for width, height in SIZES if full else ((360, 800), (1440, 900)):
                page.set_viewport_size({"width": width, "height": height})
                for theme in ("light", "dark"):
                    page.emulate_media(color_scheme=theme)
                    expect(page.locator("html")).to_have_attribute("data-theme", theme)
                    page.wait_for_timeout(100)
                    result = inspect(page)
                    result.update(surface=name, width=width, height=height)
                    report["cases"].append(result)
                    if (width, theme) in ((1440, "light"), (360, "dark")):
                        modal_open = page.get_by_role("dialog").count() > 0
                        page.screenshot(
                            path=str(output / f"{name}-{width}-{theme}.png"),
                            full_page=not modal_open,
                        )
                        if not modal_open:
                            page.screenshot(
                                path=str(output / f"{name}-{width}-{theme}-viewport.png")
                            )
            page.set_viewport_size({"width": 1440, "height": 900})
            print(f"Captured {name}", flush=True)

        try:
            page.goto(base + "/setup", wait_until="networkidle")
            capture("setup", True)
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")

            for route in ROUTES:
                page.goto(base + "/" + route, wait_until="networkidle")
                if route == "dashboard":
                    began = time.perf_counter()
                    page.reload(wait_until="domcontentloaded")
                    expect(page.locator("#totalApiCalls")).not_to_have_text("—")
                    expect(
                        page.locator("#usageProviderSummary .usage-provider-item").first
                    ).to_be_visible()
                    report["measurements"]["warm_dashboard_ms"] = round(
                        (time.perf_counter() - began) * 1000
                    )
                    page.wait_for_load_state("networkidle")
                expand(page, ".tab-content.active")
                capture(route.replace("?view=", "-"), True)

            page.goto(base + "/providers", wait_until="networkidle")
            providers = page.locator("#providerCatalog [data-provider]").evaluate_all(
                "els=>els.map(el=>el.dataset.provider)"
            )
            assert len(providers) == 23
            for provider in providers:
                page.locator("#providerCatalogSearch").fill(provider)
                card = page.locator(f'#providerCatalog [data-provider="{provider}"]')
                card.click()
                panel = "#" + card.get_attribute("aria-controls")
                expect(page.locator(panel)).to_be_visible()
                expand(page, panel)
                for opener in page.locator(panel + " .provider-key-entry-button").all():
                    if opener.is_visible() and opener.get_attribute("aria-expanded") != "true":
                        opener.click()
                capture("provider-" + provider)

            page.goto(base + "/credentials", wait_until="networkidle")
            page.locator("#primaryPageSizeSelect").select_option("100")
            expect(page.locator("[data-credential-select]")).to_have_count(
                manifest["credential_count"]
            )
            files = page.locator("[data-credential-select]").evaluate_all(
                "els=>els.map(el=>el.dataset.filename).filter(name=>name.endsWith('-01.json'))"
            )
            assert len(files) == 23
            for filename in files:
                selection = page.locator(f'[data-credential-select][data-filename="{filename}"]')
                card = selection.locator('xpath=ancestor::div[contains(@class,"cred-card")][1]')
                opener = card.locator('[data-credential-command="manage"]')
                opener.click()
                dialog = page.get_by_role("dialog").last
                expect(dialog).to_contain_text(filename)
                expect(dialog.locator("[data-management-models] .skeleton")).to_have_count(0)
                capture("credential-" + filename[5:-8])
                page.keyboard.press("Escape")
                expect(dialog).not_to_be_visible()
                expect(opener).to_be_focused()

            for route, selector, name in (
                ("access", '[data-ui-action="virtual-key-usage"]', "key-usage"),
                ("access", '[data-ui-action="virtual-key-edit"]:not([disabled])', "key-edit"),
                ("identity", "#identityCreateButton", "identity-create"),
                ("activity", '[data-ui-action="view-trace-detail"]', "trace-detail"),
                ("activity?view=audit", '[data-ui-action="view-audit-detail"]', "audit-detail"),
            ):
                page.goto(base + "/" + route, wait_until="networkidle")
                opener = page.locator(selector).first
                opener.click()
                dialog = page.get_by_role("dialog").last
                expect(dialog).to_be_visible()
                capture(name)
                page.keyboard.press("Escape")
                expect(dialog).not_to_be_visible()
                expect(opener).to_be_focused()

            page.goto(base + "/dashboard", wait_until="networkidle")
            page.set_viewport_size({"width": 360, "height": 800})
            page.locator(".mobile-menu-btn").click()
            expect(page.locator(".dashboard-sidebar")).to_have_class("dashboard-sidebar open")
            assert page.locator("#mainContent").evaluate("el=>el.inert")
            page.keyboard.press("Escape")
            expect(page.locator(".mobile-menu-btn")).to_be_focused()
            report["journeys"].append("mobile-sidebar-focus")
            guest = browser.new_context(locale="vi-VN", reduced_motion="reduce")
            page = guest.new_page()
            page.goto(base + "/login", wait_until="networkidle")
            capture("login", True)
            guest.close()
            assert not report["errors"], report["errors"]
            # Deliberately invalid upstream fixtures must exercise the real
            # error states without hiding unrelated application failures.
            expected = {
                (
                    f"/api/credentials/quota/demo-{variant}-05.json?mode=provider",
                    502 if variant == "muse_code" else 400,
                )
                for variant in (
                    "google_antigravity",
                    "grok",
                    "codex",
                    "claude_code",
                    "kiro",
                    "muse_code",
                )
            } | {("/api/credentials/quota/demo-grok-07.json?mode=provider", 502)}
            unexpected = [
                r for r in report["api_errors"] if (r["path"], r["status"]) not in expected
            ]
            assert not unexpected, unexpected
        finally:
            report["elapsed_seconds"] = round(time.monotonic() - started)
            report["database"] = str(directory)
            (output / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            browser.close()
    findings = [
        r
        for r in report["cases"]
        if any(
            r[k]
            for k in (
                "overflow",
                "dialogOverflow",
                "missingNames",
                "placeholder",
                "contrast",
                "overlaps",
            )
        )
    ]
    print(
        json.dumps(
            {
                "cases": len(report["cases"]),
                "findings": len(findings),
                "measurements": report["measurements"],
            }
        )
    )
    if strict:
        assert not findings, "See report.json for measured findings"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", default="before")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    main(args.stage, args.strict, args.only)
