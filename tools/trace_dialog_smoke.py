"""Isolated trace dialog and shared scrollbar regression; no real provider traffic."""

import argparse
from pathlib import Path

from browser_smoke import PASSWORD, _trace_page, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    fixture = _trace_page()
    trace = fixture["traces"][0]
    trace["requested_model"] = "muse-code/muse-spark-1.3-contributor"
    trace["selected_provider"] = "muse_code"
    trace["decisions"] = [
        {**trace["decisions"][0], "sequence": index + 1, "elapsed_ms": index * 3}
        for index in range(12)
    ]
    state = {"failed": False}
    output = ROOT / "temp/trace-dialog"
    output.mkdir(parents=True, exist_ok=True)
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", reduced_motion="reduce")
        context.route("https://**", lambda r: r.fulfill(body="", content_type="text/css"))
        context.route("**/api/traces?**", lambda r: r.fulfill(json=fixture))
        context.route(
            "**/api/traces/" + trace["trace_id"],
            lambda r: r.fulfill(status=503, json={}) if state["failed"] else r.fulfill(json=trace),
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/activity", wait_until="networkidle")
            opener = page.locator('[data-ui-action="view-trace-detail"]')
            dialog = page.locator("#traceDetailDialog")
            for theme, width in (
                ("light", 1440),
                ("dark", 360),
                ("light", 320),
                ("dark", 768),
                ("light", 1024),
            ):
                page.emulate_media(color_scheme=theme)
                page.set_viewport_size({"width": width, "height": 900})
                opener.click()
                expect(page.locator("#traceDetailTitle")).to_have_text(trace["trace_id"])
                if not args.baseline:
                    assert dialog.locator(".trace-detail-body").evaluate("el => el.scrollTop") == 0
                if width in (1440, 360):
                    page.screenshot(
                        path=str(
                            output / f"{'before' if args.baseline else 'after'}-{theme}-{width}.png"
                        )
                    )
                if not args.baseline:
                    expect(dialog).to_have_accessible_name("Chi tiết dấu vết")
                    close = dialog.locator('[data-ui-action="close-trace-detail"]')
                    expect(close).to_have_text("Đóng")
                    expect(close.locator("svg")).to_have_count(0)
                    expect(dialog.locator(".trace-detail-header button")).to_have_count(0)
                    expect(
                        dialog.locator(
                            '.trace-detail-actions [data-ui-action="close-trace-detail"]'
                        )
                    ).to_have_count(1)
                    assert close.bounding_box()["width"] >= 32
                    body = dialog.locator(".trace-detail-body")
                    assert body.evaluate("el => el.scrollHeight > el.clientHeight")
                    assert body.evaluate("el => getComputedStyle(el).scrollbarWidth") == "thin"
                    assert (
                        page.locator("html").evaluate("el => getComputedStyle(el).scrollbarWidth")
                        == "thin"
                    )
                    assert dialog.evaluate("el => el.scrollWidth <= el.clientWidth")
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    header_y = dialog.locator(".trace-detail-header").bounding_box()["y"]
                    box = body.bounding_box()
                    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    page.mouse.wheel(0, 2000)
                    page.wait_for_function(
                        "() => document.querySelector('.trace-detail-body').scrollTop > 0"
                    )
                    assert dialog.locator(".trace-detail-header").bounding_box()["y"] == header_y
                    close.focus()
                    page.keyboard.press("Shift+Tab")
                    assert dialog.evaluate("el => el.contains(document.activeElement)")
                    page.keyboard.press("Tab")
                    assert dialog.evaluate("el => el.contains(document.activeElement)")
                    close.click()
                    expect(dialog).not_to_be_visible()
                    expect(opener).to_be_focused()
                    opener.click()
                    expect(dialog).to_be_visible()
                    # Dragging text out of the dialog must not count as a backdrop tap.
                    heading = dialog.locator("#traceDetailHeading").bounding_box()
                    page.mouse.move(heading["x"] + 8, heading["y"] + 8)
                    page.mouse.down()
                    page.mouse.move(2, 2)
                    page.mouse.up()
                    expect(dialog).to_be_visible()
                    page.mouse.click(2, 2)
                    expect(dialog).not_to_be_visible()
                    expect(opener).to_be_focused()
                    opener.click()
                page.keyboard.press("Escape")
                expect(dialog).not_to_be_visible()
                expect(opener).to_be_focused()
            if not args.baseline:
                state["failed"] = True
                opener.click()
                expect(page.locator("#traceDetailStatus")).not_to_have_text("")
                # The requested ID is known before fetching; old response data is not.
                expect(page.locator("#traceDetailTitle")).to_have_text(trace["trace_id"])
                expect(page.locator("#traceDetailModel")).to_have_text("")
                expect(page.locator("#traceDetailRequestId")).to_have_text("")
                page.keyboard.press("Escape")
                state["failed"] = False
                trace["decisions"] = []
                opener.click()
                expect(page.locator("#traceDecisionCount")).to_have_text("0")
                expect(page.locator("#traceDecisionList li")).to_have_count(0)
                page.emulate_media(forced_colors="active")
                assert (
                    page.locator("html").evaluate("el => getComputedStyle(el).scrollbarWidth")
                    == "auto"
                )
                page.keyboard.press("Escape")
                context.route(
                    "**/__scroll_fixture",
                    lambda r: r.fulfill(
                        content_type="text/html",
                        body="""<!doctype html>
                        <link rel="stylesheet" href="/frontend/console.css">
                        <div id="scroll" tabindex="0" style="width:280px;height:160px;overflow:auto">
                        <div style="width:1000px;height:1000px">Synthetic two-axis scroll</div></div>""",
                    ),
                )
                page.goto(base + "/__scroll_fixture", wait_until="networkidle")
                surface = page.locator("#scroll")
                page.emulate_media(forced_colors="none")
                assert surface.evaluate("el => getComputedStyle(el).scrollbarWidth") == "thin"
                surface.hover()
                page.mouse.wheel(200, 200)
                page.wait_for_function(
                    "() => { const el = document.querySelector('#scroll'); return el.scrollLeft > 0 && el.scrollTop > 0; }"
                )
            assert not errors, errors
            print(
                "PASS: trace dialog matrix, keyboard/focus, scroll, themes, empty/error and forced colors"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
