"""Verify permanent Identity navigation without enabling OIDC or changing real data."""

from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright


def main():
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        output = Path(__file__).resolve().parents[1] / "temp/identity-navigation"
        output.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            expected_order = [
                "dashboard",
                "providers",
                "credentials",
                "models",
                "quality",
                "playground",
                "access",
                "identity",
                "activity",
                "config",
                "about",
            ]
            assert (
                page.locator(".sidebar-menu [data-tab]").evaluate_all(
                    "els => els.map(el => el.dataset.tab)"
                )
                == expected_order
            )
            tab = page.locator('[data-tab="identity"]')
            expect(tab).to_be_visible()
            expect(tab).to_have_text("Danh tính và phiên")
            tab.focus()
            tab.press("Enter")
            expect(page).to_have_url(base + "/identity")
            expect(page.locator("#identityModeNotice")).to_contain_text("đang tắt")
            expect(page.locator("#identityTab h1")).to_have_text("Danh tính và phiên")
            expect(page.locator("#identityList")).not_to_contain_text("identity.")
            expect(page.locator("#identitySessionPageNumber")).to_have_text("Trang 1")
            page.locator("#identityCreateButton").click()
            expect(page.locator("#identityCreateTitle")).to_have_text("Tạo danh tính")
            page.locator('#identityCreateDialog [data-i18n="identity.cancel"]').click()
            expect(page.locator("#identityCreateDialog")).not_to_be_visible()
            page.screenshot(path=str(output / "desktop.png"), full_page=True)
            page.set_viewport_size({"width": 360, "height": 800})
            page.locator(".mobile-menu-btn").click()
            expect(tab).to_be_visible()
            tab.scroll_into_view_if_needed()
            assert (
                page.locator(".sidebar-menu [data-tab]").evaluate_all(
                    "els => els.map(el => el.dataset.tab)"
                )
                == expected_order
            )
            page.screenshot(path=str(output / "mobile.png"))
            tab.click()
            expect(page.locator(".dashboard-sidebar")).to_have_attribute("inert", "")
            expect(page).to_have_url(base + "/identity")
            page.screenshot(path=str(output / "mobile-content.png"), full_page=True)
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.goto(base + "/config", wait_until="networkidle")
            with page.expect_navigation(wait_until="networkidle"):
                page.locator("#consoleLanguage").select_option("en")
            page.goto(base + "/identity", wait_until="networkidle")
            expect(page.locator("#identityTab h1")).to_have_text("Identity and sessions")
            expect(page.locator("#identitySessionPageNumber")).to_have_text("Page 1")
            expect(page.locator("#identityList")).not_to_contain_text("identity.")
            page.locator("#identityCreateButton").click()
            expect(page.locator("#identityCreateTitle")).to_have_text("Create identity")
            page.locator('#identityCreateDialog [data-i18n="identity.cancel"]').click()
            context.route(
                "**/api/identity/oidc-policy",
                lambda route: route.fulfill(status=503, json={"detail": "Synthetic unavailable"}),
            )
            page.goto(base + "/dashboard", wait_until="networkidle")
            expect(tab).to_be_visible()
            tab.click()
            expect(page).to_have_url(base + "/identity")
            expect(tab).to_be_visible()
            assert not errors, errors
            print(
                "PASS: fixed sidebar, OIDC disabled/policy unavailable, keyboard/mobile, Vietnamese/English headings, runtime labels, pagination and create/cancel dialog; no OIDC configuration changed"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
