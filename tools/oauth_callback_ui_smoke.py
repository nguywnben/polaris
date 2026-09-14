"""Inspect standalone OAuth results without sending an authorization request."""

import sys
from pathlib import Path

from browser_smoke import disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

def main():
    from core.i18n import locale_context, translate
    from core.panel.root import _oauth_callback_page

    output = ROOT / "temp/oauth-callback-ui"
    output.mkdir(parents=True, exist_ok=True)
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for locale, theme in [("vi", "light"), ("en", "dark")]:
                context = browser.new_context(locale=locale, color_scheme=theme)
                context.route("https://**", lambda route: route.abort())
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/callback", wait_until="networkidle")
                assert response.status == 400
                assert response.headers["cache-control"] == "no-store"
                expect(page.locator("html")).to_have_attribute("data-theme", theme)
                expect(page.locator(".oauth-callback-return")).to_have_attribute("href", "/providers")
                for width in [320, 360, 768, 1440]:
                    page.set_viewport_size({"width": width, "height": 900})
                    assert page.locator("html").evaluate("el => el.scrollWidth <= innerWidth")
                    if width in [360, 1440]:
                        page.screenshot(path=str(output / f"{locale}-{theme}-{width}.png"), full_page=True)
                page.locator(".oauth-callback-return").focus()
                expect(page.locator(".oauth-callback-return")).to_be_focused()
                page.locator(".oauth-callback-return").press("Enter")
                expect(page).to_have_url(base + "/providers")
                # Do not race the unauthenticated console's setup redirect against the
                # next fixture navigation; each standalone result owns its own page.
                page.close()
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                # Render the exact production success template, with no callback code/token.
                with locale_context(locale):
                    success = _oauth_callback_page(
                        True, translate("oauth.success_title", provider="OAuth"),
                        translate("oauth.copy_callback"), manual_callback=True,
                    )
                context.route("**/callback", lambda route: route.fulfill(
                    status=success.status_code, headers=dict(success.headers), body=success.body))
                page.goto(base + "/callback", wait_until="networkidle")
                expect(page.locator(".oauth-callback-icon.success")).to_be_visible()
                expect(page.locator(".oauth-callback-return")).to_have_attribute("target", "_blank")
                for width in [320, 360, 768, 1440]:
                    page.set_viewport_size({"width": width, "height": 900})
                    assert page.locator("html").evaluate("el => el.scrollWidth <= innerWidth")
                page.screenshot(path=str(output / f"{locale}-success.png"), full_page=True)
                with page.expect_popup() as popup_info:
                    page.locator(".oauth-callback-return").click()
                popup = popup_info.value
                popup.wait_for_load_state("domcontentloaded")
                assert popup.url.startswith(base + "/")
                expect(page).to_have_url(base + "/callback")
                assert not errors, errors
                popup.close()
                context.close()
            print("PASS: real failure, synthetic success, vi/en, light/dark, four widths, "
                  "keyboard return, new-tab preservation, no-store and no console errors")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
