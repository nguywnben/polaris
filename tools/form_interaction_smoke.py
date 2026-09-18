"""Verify label, pointer and keyboard behavior without real credentials or clipboard writes."""

from __future__ import annotations

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright


def colors(control):
    return control.evaluate(
        "el => { const s=getComputedStyle(el); return [s.backgroundColor,s.borderTopColor,s.boxShadow]; }"
    )


def check_hover(page, label, control):
    control.scroll_into_view_if_needed()
    if page.locator(".message-modal:visible").count():
        page.locator(".message-modal-header h3").click()
    else:
        page.mouse.click(0, 0)
    page.wait_for_timeout(180)
    idle = colors(control)
    label.hover()
    page.wait_for_timeout(180)
    assert colors(control) == idle, "Hovering label must not paint its control"
    control.hover()
    page.wait_for_timeout(180)
    assert colors(control) != idle, "Direct control hover must remain visible"
    label.hover()
    page.wait_for_timeout(180)
    assert colors(control) == idle, "Hover must clear when returning to label"


def main():
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.add_init_script("""window.__copies = 0;
            Object.defineProperty(navigator, 'clipboard', {value: {
                writeText: async () => { window.__copies++; }
            }});
        """)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("https://**", lambda route: route.abort())
        page.route(
            "**/api/auth/keys",
            lambda route: route.fulfill(json={"success": True, "api_key": "synthetic-ui-key"}),
        )
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            expect(page.locator("#setupOwnerFields")).to_be_enabled()
            check_hover(page, page.locator("#setupPasswordLabel"), page.locator("#setupPassword"))
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            for theme in ("light", "dark"):
                page.emulate_media(color_scheme=theme)
                page.goto(base + "/playground", wait_until="networkidle")
                for field in (
                    "playgroundModel",
                    "playgroundProtocol",
                    "playgroundSystem",
                    "playgroundTimeout",
                ):
                    label, control = (
                        page.locator(f'label[for="{field}"]'),
                        page.locator(f"#{field}"),
                    )
                    check_hover(page, label, control)
                    label.click()
                    expect(control).not_to_be_focused()
                    control.click()
                    expect(control).to_be_focused()
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(180)
                    focused = colors(control)
                    page.mouse.move(0, 0)
                    page.wait_for_timeout(180)
                    assert colors(control) == focused, (
                        "Direct control focus must survive pointer exit"
                    )
                checkbox = page.locator("#playgroundStream")
                checkbox.locator("..").locator("span").first.click()
                expect(checkbox).to_be_checked()
                checkbox.locator("..").locator("span").first.click()
                expect(checkbox).not_to_be_checked()
            page.goto(base + "/access", wait_until="networkidle")
            key = page.locator("#apiKey")
            label = page.locator('label[for="apiKey"]')
            check_hover(page, label, key)
            label.click()
            expect(key).not_to_be_focused()
            assert page.evaluate("window.__copies") == 0, "Label must not copy a secret"
            key.click()
            assert page.evaluate("window.__copies") == 1, "Direct key click must still copy"
            key.focus()
            key.press("Enter")
            assert page.evaluate("window.__copies") == 2, "Explicit keyboard copy must work"
            expect(key).to_be_focused()
            page.get_by_role("button", name="Tạo khóa", exact=True).first.click()
            modal = page.locator(".virtual-key-form-modal")
            # Modal controls are created after the event bindings; labels wrap them.
            for name in ("rpm_limit", "allowed_models", "unknown_pricing_policy"):
                control = modal.locator(f'[name="{name}"]')
                check_hover(page, control.locator("..").locator("span").first, control)
                control.locator("..").locator("span").first.click()
                expect(control).not_to_be_focused()
                control.click()
                expect(control).to_be_focused()
            page.keyboard.press("Escape")
            modal.locator('button[type="submit"]').click()
            expect(page.locator("#statusSection .error")).to_contain_text(
                "Vui lòng nhập hoặc chọn giá trị"
            )
            assert page.locator("#statusSection .error").evaluate("""el => {
                const r=el.getBoundingClientRect();
                return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));
            }"""), "Validation toast must be above the modal overlay"
            modal.locator('[name="name"]').fill("Synthetic validation test")
            modal.locator('[name="rpm_limit"]').fill("0")
            modal.locator('button[type="submit"]').click()
            expect(page.locator("#statusSection .error")).to_contain_text("từ 1 trở lên")
            modal.locator('[name="rpm_limit"]').fill("1.5")
            modal.locator('button[type="submit"]').click()
            expect(page.locator("#statusSection .error")).to_contain_text("theo bước 1")
            modal.locator('[name="rpm_limit"]').fill("3")
            expect(modal.locator('[name="rpm_limit"]')).not_to_have_attribute(
                "aria-invalid", "true"
            )
            page.keyboard.press("Escape")
            page.goto(base + "/ai-quality", wait_until="networkidle")
            disabled = page.locator("input:disabled:visible").first
            if disabled.count():
                idle = colors(disabled)
                disabled.hover(force=True)
                page.wait_for_timeout(180)
                assert colors(disabled) == idle, "Disabled controls must not react to hover"
            custom = page.locator('.quality-profile-card input[value="custom"]')
            custom.locator("..").click()
            expect(custom).to_be_checked()
            # A separate mobile session verifies only direct touch focuses the input.
            mobile = browser.new_context(has_touch=True, viewport={"width": 390, "height": 844})
            phone = mobile.new_page()
            phone.route("https://**", lambda route: route.abort())
            phone.goto(base + "/login", wait_until="networkidle")
            phone.locator('label[for="loginPassword"]').tap()
            expect(phone.locator("#loginPassword")).not_to_be_focused()
            assert phone.locator("[data-pointer-hover]").count() == 0
            phone.locator("#loginPassword").tap()
            expect(phone.locator("#loginPassword")).to_be_focused()
            assert phone.locator("[data-pointer-hover]").count() == 0
            mobile.close()
            assert not errors, errors
            print(
                "PASS: direct hover, explicit/nested labels, dynamic modal, focus, checkbox/radio, disabled, touch and safe copy; light/dark"
            )
        finally:
            browser.close()


if __name__ == "__main__":
    main()
