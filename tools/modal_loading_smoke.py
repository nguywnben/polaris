"""Check delayed detail dialogs keep their frame and keyboard exit stable."""

from browser_smoke import PASSWORD, _trace_page, disposable_runtime
from playwright.sync_api import expect, sync_playwright


def frame(page, selector):
    return page.locator(selector).bounding_box()


def assert_stable(before, after, label):
    for key in ("x", "y", "width", "height"):
        assert abs(before[key] - after[key]) <= 2, (label, key, before, after)


def main():
    fixture = _trace_page()
    trace = fixture["traces"][0]
    trace["decisions"] = [{**trace["decisions"][0], "sequence": i + 1} for i in range(12)]
    pending = {}
    credential = {
        "filename": "loading-demo.json",
        "provider": "deepseek",
        "provider_variant": "deepseek",
        "credential_type": "api_key",
        "credential_label": "Loading fixture",
        "model_count": 29,
        "model_count_known": True,
        "disabled": False,
    }

    def credentials(route):
        name = route.request.url.split("/api/credentials/")[1].split("?")[0]
        if name == "status":
            route.fulfill(
                json={
                    "items": [credential],
                    "total": 1,
                    "has_more": False,
                    "stats": {"total": 1, "normal": 1},
                }
            )
        elif "/" in name:
            pending[name.split("/")[0]] = route
        else:
            route.fulfill(json={})

    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.route("https://**", lambda r: r.fulfill(content_type="text/css", body=""))
        context.route("**/api/traces?**", lambda r: r.fulfill(json=fixture))
        context.route("**/api/traces/" + trace["trace_id"], lambda r: pending.update(trace=r))
        context.route("**/api/credentials/**", credentials)
        page = context.new_page()
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            for width in (1440, 1024, 768, 360):
                page.set_viewport_size({"width": width, "height": 900})
                page.goto(base + "/activity", wait_until="networkidle")
                trigger = page.locator('[data-ui-action="view-trace-detail"]').first
                trigger.click()
                dialog = page.locator("#traceDetailDialog")
                expect(dialog).to_have_attribute("aria-busy", "true")
                loading = frame(page, "#traceDetailDialog")
                pending.pop("trace").fulfill(json=trace)
                expect(dialog).to_have_attribute("aria-busy", "false")
                assert_stable(loading, frame(page, "#traceDetailDialog"), f"trace {width}")
                page.keyboard.press("Escape")
                expect(trigger).to_be_focused()
                trigger.click()
                expect(dialog).to_have_attribute("aria-busy", "true")
                pending.pop("trace").fulfill(status=503, json={"error": "fixture"})
                expect(dialog).to_have_attribute("aria-busy", "false")
                assert_stable(loading, frame(page, "#traceDetailDialog"), f"trace error {width}")
                page.keyboard.press("Escape")
                page.goto(base + "/credentials", wait_until="networkidle")
                page.locator('[data-credential-command="manage"]').click()
                expect(page.locator("[data-management-models]")).to_have_attribute(
                    "aria-busy", "true"
                )
                loading = frame(page, ".credential-management-modal")
                pending.pop("models").fulfill(json={"model_ids": [f"model-{i}" for i in range(29)]})
                expect(page.locator("[data-management-models]")).to_have_attribute(
                    "aria-busy", "false"
                )
                assert_stable(
                    loading, frame(page, ".credential-management-modal"), f"models {width}"
                )
                pending.pop("configuration").fulfill(
                    json={
                        "editable": True,
                        "editable_fields": ["credential_label", "api_key"],
                        "credential_label": "Loading fixture",
                        "provider": "deepseek",
                    }
                )
                pending.pop("errors").fulfill(json={"error_codes": [], "error_messages": {}})
                expect(page.locator("[data-management-errors]")).to_have_attribute(
                    "aria-busy", "false"
                )
                assert_stable(
                    loading, frame(page, ".credential-management-modal"), f"complete {width}"
                )
                page.keyboard.press("Escape")
                expect(page.locator(".credential-management-modal")).to_be_visible()
                page.locator(".credential-management-modal [data-dialog-close]").click()
                expect(page.locator(".credential-management-modal")).to_have_count(0)
            print("modal loading stability: PASS (1440, 1024, 768, 360)")
        finally:
            for route in pending.values():
                route.abort()
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
