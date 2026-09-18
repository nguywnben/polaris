"""Verify login polish with synthetic credentials, without touching the real owner."""

from pathlib import Path

from browser_smoke import disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 900})
        context.route("https://**", lambda route: route.abort())
        context.route(
            "**/api/auth/setup/status",
            lambda route: route.fulfill(
                json={
                    "state": "configured",
                    "setup_required": False,
                    "authenticated": False,
                    "next_action": "sign_in",
                    "setup_token_required": False,
                }
            ),
        )
        pending = []
        context.route("**/api/auth/login", lambda route: pending.append(route))
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(base + "/login", wait_until="networkidle")
            password = page.locator("#loginPassword")
            toggle = page.locator("#loginPasswordToggle")
            submit = page.locator("#loginSubmitButton")
            expect(toggle).to_be_hidden()
            expect(submit).to_have_text("Đăng nhập")
            submit.click()
            expect(page.locator("#statusSection .error")).to_be_visible()
            assert not pending
            password.fill("synthetic-wrong-password")
            expect(password).not_to_have_attribute("aria-invalid", "true")
            expect(toggle).to_be_visible()
            toggle.click()
            expect(password).to_have_attribute("type", "text")
            toggle.press("Space")
            expect(password).to_have_attribute("type", "password")
            password.fill("")
            expect(toggle).to_be_hidden()
            password.fill("synthetic-wrong-password")
            password.press("Enter")
            expect(submit).to_have_text("Đang đăng nhập…")
            expect(submit).to_be_disabled()
            expect(toggle).to_be_disabled()
            expect(password).to_have_attribute("readonly", "")
            password.press("Enter")
            assert len(pending) == 1, "Only one login may be in flight"
            pending.pop().fulfill(status=401, json={"detail": "Unauthorized"})
            expect(submit).to_be_enabled()
            expect(password).to_have_value("synthetic-wrong-password")
            expect(password).to_have_attribute("type", "password")
            expect(password).to_have_attribute("aria-invalid", "true")
            password.fill("synthetic-corrected-password")
            expect(password).not_to_have_attribute("aria-invalid", "true")
            password.press("Enter")
            expect(submit).to_be_disabled()
            pending.pop().abort("failed")
            expect(submit).to_be_enabled()
            expect(password).to_have_value("synthetic-corrected-password")
            expect(password).not_to_have_attribute("readonly", "")
            page.reload(wait_until="networkidle")
            screenshots = ROOT / "temp/login-ui"
            screenshots.mkdir(parents=True, exist_ok=True)
            for width, theme in ((1440, "light"), (768, "light"), (320, "light"), (1440, "dark")):
                page.set_viewport_size({"width": width, "height": 900})
                page.emulate_media(color_scheme=theme)
                password.fill("synthetic-layout-password")
                field_box, toggle_box = password.bounding_box(), toggle.bounding_box()
                assert toggle_box["x"] >= field_box["x"]
                assert (
                    toggle_box["x"] + toggle_box["width"] <= field_box["x"] + field_box["width"] + 1
                )
                assert not page.locator("#loginSection").evaluate(
                    "el => el.scrollWidth > el.clientWidth"
                )
                page.screenshot(
                    path=str(screenshots / f"login-{width}-{theme}.png"),
                    full_page=True,
                    animations="disabled",
                )
            password.press("Enter")
            expect(submit).to_be_disabled()
            pending.pop().fulfill(status=200, json={"success": True})
            expect(page).to_have_url(base + "/dashboard")
            expect(password).to_have_value("")
            assert not errors, errors
            print(
                "PASS: login empty/error/network/success, eye toggle, pending guard, autofill semantics; desktop/mobile/light/dark"
            )
        finally:
            browser.close()


if __name__ == "__main__":
    main()
