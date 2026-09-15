"""Verify the three audited first-run pages with disposable SQLite and Chromium.

Bounded matrix: Models, Activity and Identity at four widths in both themes.
Policy failure/retry and filter/disclosure interaction run once; no provider calls.
"""

from __future__ import annotations

import json

from browser_smoke import PASSWORD, ROOT, disposable_runtime
from playwright.sync_api import expect, sync_playwright


def main() -> None:
    output = ROOT / "temp/empty-state-fixes"
    output.mkdir(parents=True, exist_ok=True)
    evidence = []
    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        context.route_web_socket("**/api/logs/stream", lambda _socket: None)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/config", wait_until="networkidle")
            page.locator('#configTab a[href="/models"]').click()
            expect(page.locator("#modelFirstRun")).to_be_visible()
            expect(page.locator("#modelRoutingStrategy")).to_be_visible()
            page.locator("#modelRoutingStrategy").select_option("weighted")
            context.route(
                "**/api/config/save",
                lambda route: route.fulfill(
                    status=503, json={"detail": "Synthetic policy save failure"}
                ),
            )
            page.locator("#saveModelRoutingPolicyBtn").click()
            expect(page.locator("#saveModelRoutingPolicyBtn")).to_be_enabled()
            expect(page.locator("#modelRoutingStrategy")).to_have_value("weighted")
            context.unroute("**/api/config/save")
            route_writes = []
            page.on(
                "request",
                lambda request: (
                    route_writes.append(request.url)
                    if "/api/model-routes/" in request.url
                    else None
                ),
            )
            page.locator("#saveModelRoutingPolicyBtn").click()
            expect(page.locator("#saveModelRoutingPolicyBtn")).to_be_disabled()
            page.reload(wait_until="networkidle")
            expect(page.locator("#modelRoutingStrategy")).to_have_value("weighted")
            expect(page.locator("#modelFirstRun")).to_be_visible()
            assert not route_writes, route_writes

            page.goto(base + "/activity", wait_until="networkidle")
            expect(page.locator(".trace-empty")).to_have_text("Chưa ghi nhận yêu cầu nào.")
            page.locator("#activityRequestId").fill("req-no-match")
            expect(page.locator(".trace-empty")).to_have_text("Chưa ghi nhận yêu cầu nào.")
            page.locator('#activityFilterForm button[type="submit"]').click()
            expect(page.locator(".trace-empty")).to_contain_text("bộ lọc")
            page.locator('[data-ui-action="clear-activity-filters"]').click()
            expect(page.locator(".trace-empty")).to_have_text("Chưa ghi nhận yêu cầu nào.")
            page.locator("#activityRuntimeTab").click()
            expect(page.locator("#connectionStatusText")).to_have_text("Đã kết nối")
            expect(page.locator("#logContent")).to_have_text("Chưa có nhật ký nào.")

            page.goto(base + "/identity", wait_until="networkidle")
            disclosure = page.locator("details.identity-permissions")
            expect(disclosure).to_be_visible()
            expect(page.locator(".identity-permission-list")).to_be_hidden()
            page.locator(".identity-permissions summary").focus()
            page.keyboard.press("Enter")
            expect(page.locator(".identity-permission-list")).to_be_visible()
            expect(page.locator(".identity-permission-list li")).to_have_count(32)
            page.keyboard.press("Enter")
            expect(page.locator(".identity-permission-list")).to_be_hidden()
            for pagination in page.locator(".identity-pagination").all():
                expect(pagination).to_be_hidden()

            for theme in ("light", "dark"):
                page.emulate_media(color_scheme=theme, reduced_motion="reduce")
                for width in (360, 768, 1024, 1440):
                    page.set_viewport_size({"width": width, "height": 960})
                    for route_name in ("models", "activity", "identity"):
                        page.goto(base + "/" + route_name, wait_until="networkidle")
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth"
                        ), (route_name, width, theme)
                        if route_name == "identity":
                            expect(page.locator(".identity-permission-list")).to_be_hidden()
                        if route_name == "models":
                            expect(page.locator("#modelRoutingPolicyPanel")).to_be_visible()
                        page.screenshot(
                            path=str(output / f"{route_name}-{width}-{theme}.png"), full_page=True
                        )
                        evidence.append({"page": route_name, "width": width, "theme": theme})
            assert not errors, errors
            (output / "results.json").write_text(
                json.dumps(
                    {
                        "cases": evidence,
                        "page_errors": errors,
                        "policy_failure_retry_persisted": True,
                        "route_writes": route_writes,
                        "applied_filters_distinguished": True,
                        "permissions_keyboard": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(
                f"PASS: {len(evidence)} visual cases; policy, activity and permissions regressions"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
