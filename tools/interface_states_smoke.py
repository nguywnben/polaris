"""Local-only regression journeys for loading and modal interaction contracts."""

from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

OUTPUT = Path(__file__).resolve().parents[1] / "temp/interface-states"


def main():
    failures = []
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", reduced_motion="reduce")
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/setup", wait_until="networkidle")
        page.locator("#setupPassword").fill(PASSWORD)
        page.locator("#setupPasswordConfirm").fill(PASSWORD)
        page.locator("#setupSubmitButton").click()
        expect(page).to_have_url(base + "/dashboard")

        for width, height, theme in ((320, 760, "light"), (844, 390, "dark"), (1440, 900, "light")):
            page.set_viewport_size({"width": width, "height": height})
            page.emulate_media(color_scheme=theme)
            for route_name, pattern, host in (
                ("access", "**/api/virtual-keys", "#virtualKeyList"),
                ("about", "**/api/capabilities", "#aboutSupportTiers"),
                ("identity", "**/api/identity/recovery", "#identityRecoverySummary"),
                ("activity", "**/api/traces?*", "#traceList"),
                ("activity?view=audit", "**/api/audit/events?*", "#auditEventList"),
            ):
                held = []
                page.route(pattern, lambda route: held.append(route))
                page.goto(base + "/" + route_name, wait_until="domcontentloaded")
                for _ in range(100):
                    if held:
                        break
                    page.wait_for_timeout(50)
                assert held, f"Request did not start: {route_name}"
                expect(page.locator(host)).to_have_attribute("aria-busy", "true")
                page.wait_for_timeout(180)
                skeleton = page.locator(host + " .region-skeleton")
                if not skeleton.count():
                    failures.append(f"{width}/{route_name}: initial request has no skeleton")
                else:
                    for item in skeleton.all():
                        if item.locator("dt").count():
                            expect(item.locator("dt")).not_to_be_empty()
                            expect(item.locator("dd .skeleton-line")).to_be_visible()
                        else:
                            assert item.get_attribute("aria-label")
                        box = item.bounding_box()
                        assert box and box["width"] > 0 and box["x"] + box["width"] <= width + 1
                page.screenshot(
                    path=str(
                        OUTPUT
                        / f"loading-{route_name.replace('?', '-').replace('=', '-')}-{width}.png"
                    )
                )
                # An initial failure must finish loading and expose a retry/error,
                # not leave an endless skeleton in an otherwise interactive page.
                for request in held:
                    request.fulfill(status=503, json={"detail": "Synthetic unavailable"})
                expect(page.locator(host)).to_have_attribute("aria-busy", "false")
                expect(skeleton).to_have_count(0)
                page.unroute(pattern)

            page.goto(base + "/about", wait_until="networkidle")
            before = page.locator("#aboutSupportTiers").inner_text()
            held = []
            page.route("**/api/capabilities", lambda route: held.append(route))
            page.evaluate("void loadAboutPage()")
            for _ in range(100):
                if held:
                    break
                page.wait_for_timeout(50)
            assert held
            expect(page.locator("#aboutSupportTiers")).to_have_attribute("aria-busy", "true")
            assert page.locator("#aboutSupportTiers").inner_text() == before
            expect(page.locator("#aboutSupportTiers .region-skeleton")).to_have_count(0)
            page.wait_for_timeout(100)
            for request in held:
                request.fulfill(status=503, json={"detail": "Synthetic unavailable"})
            expect(page.locator("#aboutSupportTiers")).to_have_attribute("aria-busy", "false")
            assert page.locator("#aboutSupportTiers").inner_text() == before
            page.unroute("**/api/capabilities")

            page.evaluate("""() => {
                const trigger = document.createElement('button');
                trigger.id = 'modalRegressionTrigger'; trigger.textContent = 'Open';
                document.body.append(trigger); trigger.focus();
                void showPromptModal('Parent dialog');
            }""")
            expect(page.locator(".message-modal")).to_be_visible()
            page.wait_for_timeout(50)
            if not page.locator("#modalRegressionTrigger").evaluate(
                "el => !!el.closest('[inert]')"
            ):
                failures.append(f"{width}: modal background remains interactive")
            if page.evaluate("getComputedStyle(document.body).overflow") != "hidden":
                failures.append(f"{width}: modal does not lock background scrolling")
            page.evaluate("""() => {
                window.confirmOutcome = null;
                void showConfirmModal('Long detail. '.repeat(500), {title:'Confirm removal', confirmLabel:'Remove'})
                    .then(value => window.confirmOutcome = value);
            }""")
            expect(page.locator(".message-modal")).to_have_count(2)
            page.wait_for_timeout(50)
            if page.locator("[data-dialog-confirm]").last.evaluate(
                "el => el === document.activeElement"
            ):
                failures.append(f"{width}: affirmative action is focused on open")
            body = page.locator(".message-modal-body").last
            assert body.evaluate("el => el.scrollHeight > el.clientHeight"), {
                "width": width,
                "geometry": body.evaluate("el => [el.scrollHeight, el.clientHeight]"),
            }
            footer = page.locator(".message-modal-footer").last.bounding_box()
            assert footer and footer["y"] + footer["height"] <= height
            page.screenshot(path=str(OUTPUT / f"nested-confirmation-{width}.png"))
            page.keyboard.press("Escape")
            expect(page.locator(".message-modal")).to_have_count(2)
            page.locator("[data-dialog-cancel]").last.click()
            page.wait_for_timeout(50)
            if page.locator(".message-modal").count() != 1:
                failures.append(f"{width}: Cancel closed more than the top dialog")
            assert page.evaluate("window.confirmOutcome") is False
            page.keyboard.press("Escape")
            expect(page.locator(".message-modal")).to_have_count(1)
            page.locator("[data-dialog-cancel]").click()
            expect(page.locator(".message-modal")).to_have_count(0)
            expect(page.locator("#modalRegressionTrigger")).to_be_focused()
            assert not page.locator("#modalRegressionTrigger").evaluate("el => el.inert")
            assert page.evaluate("getComputedStyle(document.body).overflow") != "hidden"
            page.locator("#modalRegressionTrigger").evaluate("el => el.remove()")
        browser.close()
    assert not errors, errors
    assert not failures, "\n".join(failures)
    print(
        "PASS: initial loading/error cleanup, refresh retention, nested modal focus/scroll/Escape at 320/844/1440"
    )


if __name__ == "__main__":
    main()
