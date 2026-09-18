"""Textarea resizing must preserve column/modal bounds and vertical expansion."""

from browser_smoke import PASSWORD, ROOT, disposable_runtime, install_fixtures
from playwright.sync_api import expect, sync_playwright


def drag_corner(page, field, horizontal_delta=160):
    field.scroll_into_view_if_needed()
    before = field.bounding_box()
    x, y = before["x"] + before["width"] - 3, before["y"] + before["height"] - 3
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + horizontal_delta, y + 60, steps=12)
    page.mouse.up()
    after = field.bounding_box()
    assert abs(after["width"] - before["width"]) <= 1, (before, after)
    assert after["height"] > before["height"] + 20, (before, after)


def main():
    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        install_fixtures(page)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/setup", wait_until="networkidle")
        page.locator("#setupPassword").fill(PASSWORD)
        page.locator("#setupPasswordConfirm").fill(PASSWORD)
        page.locator("#setupSubmitButton").click()
        expect(page).to_have_url(base + "/dashboard")
        page.goto(base + "/playground", wait_until="networkidle")
        system = page.locator("#playgroundSystem")
        system.fill("Long system instruction " * 80)
        drag_corner(page, system)
        drag_corner(page, page.locator("#playgroundMessages textarea").first)

        # Include hidden sections: their styles must already be safe when opened.
        unsafe = page.locator("textarea").evaluate_all("""fields => fields.flatMap(el => {
            const css = getComputedStyle(el);
            return css.resize === 'vertical' && css.maxWidth === '100%' ? [] :
                [{id: el.id, resize: css.resize, maxWidth: css.maxWidth}];
        })""")
        assert not unsafe, unsafe

        shots = ROOT / "temp" / "textarea-resize"
        shots.mkdir(parents=True, exist_ok=True)
        for width in (1440, 1024, 768, 360, 320):
            for theme in ("light", "dark"):
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("value => PolarisTheme.setPreference(value)", theme)
                expect(page.locator("html")).not_to_have_class("theme-switching")
                # A stored/manual pixel width must also be bounded after viewport changes.
                system.evaluate("el => el.style.width = '2000px'")
                assert system.evaluate("""el => el.getBoundingClientRect().width <=
                    el.parentElement.clientWidth + 1"""), (width, theme)
                assert page.locator(".playground-composer").evaluate(
                    "el => el.scrollWidth <= el.clientWidth"
                ), (width, theme)
                system.evaluate("el => el.style.removeProperty('width')")
                if width in (1440, 320):
                    system.scroll_into_view_if_needed()
                    page.screenshot(path=str(shots / f"{width}-{theme}.png"))

        page.set_viewport_size({"width": 1024, "height": 1000})
        page.evaluate("""showMessageModal('Textarea fixture',
            '<label for="resizeModalField">Read-only content</label>' +
            '<textarea id="resizeModalField" readonly rows="3">Synthetic content</textarea>',
            'info', {html: true})""")
        modal_field = page.locator("#resizeModalField")
        expect(modal_field).to_be_visible()
        # Keep the pointer inside the modal; releasing over its backdrop dismisses it.
        expect(modal_field).to_have_css("resize", "vertical")
        expect(modal_field).to_have_css("max-width", "100%")
        drag_corner(page, modal_field, horizontal_delta=0)
        assert not errors, errors
        browser.close()
    print(
        "PASS: textarea horizontal bounds, vertical dragging, dynamic fields, read-only modal, 320–1440px light/dark"
    )


if __name__ == "__main__":
    main()
