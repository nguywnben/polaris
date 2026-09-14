"""Activity UI with synthetic traces, audit events and a synthetic log stream."""

from pathlib import Path
from urllib.parse import urlparse

from browser_smoke import PASSWORD, _trace_page, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    state = {"error": False, "empty": True, "requests": []}
    trace_page = _trace_page()
    trace = trace_page["traces"][0]
    audit = {
        "schema_version": 1, "event_id": "2" * 32, "occurred_at": trace["started_at"],
        "request_id": trace["request_id"], "actor_type": "local_owner", "actor_fingerprint": "a" * 20,
        "action": "config.update", "target_type": "configuration", "target_fingerprint": "b" * 20,
        "outcome": "succeeded", "change_codes": ["updated"],
    }

    def evidence(route):
        state["requests"].append(route.request.url)
        path = urlparse(route.request.url).path
        if state["error"]:
            route.fulfill(status=503, json={"detail": "Synthetic unavailable"})
        elif path.endswith("/export"):
            route.fulfill(content_type="text/plain", body="synthetic-export-only")
        elif path == "/api/traces":
            route.fulfill(json={**trace_page, "traces": [] if state["empty"] else [trace]})
        elif path == "/api/audit/events":
            route.fulfill(json={"events": [] if state["empty"] else [audit], "page_size": 25, "has_more": False, "next_cursor": None})
        elif path.endswith(trace["trace_id"]):
            route.fulfill(json=trace)
        else:
            route.fulfill(json=audit)

    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        context.route("https://**", lambda route: route.abort())
        context.route("**/api/traces**", evidence)
        context.route("**/api/audit/events**", evidence)
        context.route_web_socket("**/api/logs/stream", lambda ws: ws.send("[2026-09-14 20:00:00] [INFO] synthetic completed req-fixture"))
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        output = ROOT / "temp/activity-ui"
        output.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/activity", wait_until="networkidle")
            expect(page.locator(".trace-empty")).to_be_visible()
            page.locator("#activityRequestId").fill("req-fixture")
            page.locator("#activityFilterForm button[type=submit]").click()
            expect(page.locator("#traceList")).to_have_attribute("aria-busy", "false")
            assert any("request_id=req-fixture" in url for url in state["requests"])
            page.locator("#activityTracesTab").focus()
            page.keyboard.press("ArrowRight")
            expect(page.locator("#activityAuditPanel")).to_be_visible()
            expect(page.locator("#activityFilterHint")).to_contain_text("Nhà cung cấp")
            expect(page.locator("#activityRequestId")).to_have_value("req-fixture")
            page.locator('[data-ui-action="clear-activity-filters"]').click()
            expect(page.locator("#activityRequestId")).to_have_value("")
            for tab, panel, refresh, empty in (
                ("activityTracesTab", "traceStatus", "refresh-traces", ".trace-empty"),
                ("activityAuditTab", "auditEventStatus", "refresh-audit", ".audit-empty-state"),
            ):
                page.locator("#" + tab).click()
                expect(page.locator(empty)).to_be_visible()
                state["error"] = True
                page.locator(f'[data-ui-action="{refresh}"]').click()
                expect(page.locator("#" + panel)).not_to_have_text("")
                expect(page.locator(empty)).to_have_count(0)
                state["error"] = False
                state["empty"] = False
                page.locator(f'[data-ui-action="{refresh}"]').click()
                expect(page.locator("#" + panel)).to_have_text("")
                state["empty"] = True
            page.locator("#activityTracesTab").click()
            page.locator('[data-ui-action="view-trace-detail"]').click()
            expect(page.locator("#traceDetailDialog")).to_be_visible()
            expect(page.locator("#traceDetailRequestId")).to_have_text(trace["request_id"])
            page.locator('[data-ui-action="related-audit-request"]').click()
            expect(page.locator("#activityAuditPanel")).to_be_visible()
            expect(page.locator("#activityRequestId")).to_have_value(trace["request_id"])
            page.locator('[data-ui-action="clear-activity-filters"]').click()
            for view in ("traces", "audit", "runtime"):
                page.locator(f'[data-activity-view="{view}"]').click()
                for width in (1440, 1024, 768, 360, 320):
                    page.set_viewport_size({"width": width, "height": 1000})
                    page.evaluate("window.scrollTo(0,0)")
                    page.mouse.move(2, 2)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (view, width)
                    assert page.locator(".activity-tabs").evaluate("el => el.scrollWidth <= el.clientWidth"), (view, width)
                    if width in (1440, 360):
                        page.screenshot(path=str(output / f"{view}-{width}.png"), full_page=True, animations="disabled")
            page.emulate_media(color_scheme="dark")
            page.locator("#activityTracesTab").click()
            page.evaluate("AppState.lang = 'en'; applyLanguage(); window.scrollTo(0,0)")
            expect(page.locator("#activityFilterHint")).to_contain_text("Actor type")
            page.screenshot(path=str(output / "dark-en-mobile.png"), full_page=True, animations="disabled")
            assert not errors, errors
            print("PASS: shared filters, keyboard tabs, failed/empty/populated responses, retry, trace detail and audit pivot, runtime, en/vi, 320–1440px")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
