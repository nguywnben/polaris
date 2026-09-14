"""About UI in a disposable runtime; version/update responses are synthetic."""

from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    state = {"fail": False, "empty": False, "known": False, "update": False}

    def version(route):
        route.fulfill(json={
            "success": True, "version": "0.1.0-beta" if state["known"] else "unknown",
            "source": "container", "full_hash": "a" * 128 if state["known"] else "",
            "date": "2026-09-14" if state["known"] else "", "check_update": True,
            "has_update": state["update"], "latest_version": "0.2.0-beta",
        })

    def capabilities(route):
        if state["fail"]:
            route.fulfill(status=503, json={"detail": "Synthetic unavailable"})
        elif state["empty"]:
            route.fulfill(json={"schema_version": 1, "profile": "self_hosted", "capabilities": []})
        else:
            route.continue_()

    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        context.route("https://**", lambda route: route.abort())
        context.route("**/api/version/info*", version)
        context.route("**/api/capabilities", capabilities)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        output = ROOT / "temp/about-ui"
        output.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/about", wait_until="networkidle")
            expect(page.locator("#aboutBuildFacts")).to_contain_text("Phiên bản không xác định")
            assert page.locator(".support-tier-status dt").count() >= 12
            for link in ("updateGuideLink", "backupGuideLink", "sponsorLink"):
                expect(page.locator("#" + link)).to_have_attribute("target", "_blank")
                expect(page.locator("#" + link)).to_have_attribute("rel", "noopener noreferrer")
                page.locator("#" + link).focus()
                expect(page.locator("#" + link)).to_be_focused()
            for theme in ("light", "dark"):
                page.goto(base + "/config", wait_until="networkidle")
                page.locator("#themePreference").select_option(theme)
                page.goto(base + "/about", wait_until="networkidle")
                for width in (1440, 1024, 768, 360, 320):
                    page.set_viewport_size({"width": width, "height": 1000})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (theme, width)
                    if width in (1440, 360):
                        page.screenshot(path=str(output / f"about-{width}-{theme}.png"), full_page=True, animations="disabled")
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.locator("#checkUpdateBtn").click()
            expect(page.locator("#checkUpdateBtn")).to_have_class("btn btn-secondary update-current")
            state["update"] = True
            page.locator("#checkUpdateBtn").click()
            expect(page.locator("#checkUpdateBtn")).to_have_class("btn btn-secondary update-available")
            state["known"] = True
            page.reload(wait_until="networkidle")
            expect(page.locator("#aboutBuildFacts")).to_contain_text("v0.1.0-beta")
            page.set_viewport_size({"width": 320, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            state["empty"] = True
            page.reload(wait_until="networkidle")
            expect(page.locator("#aboutSupportTiers")).to_contain_text("chưa cung cấp thông tin")
            state["fail"] = True
            page.reload(wait_until="networkidle")
            expect(page.locator("#aboutState")).to_be_visible()
            expect(page.locator("#aboutSupportTiers")).to_have_attribute("aria-busy", "false")
            state["fail"] = False
            state["empty"] = False
            page.locator("#aboutState button").click()
            expect(page.locator("#aboutState")).to_be_hidden()
            expect(page.locator(".support-tier-status").first).to_be_visible()
            page.goto(base + "/config", wait_until="networkidle")
            with page.expect_navigation(wait_until="networkidle"):
                page.locator("#consoleLanguage").select_option("en")
            page.goto(base + "/about", wait_until="networkidle")
            expect(page.locator(".support-tier-status").first).to_contain_text("Available")
            assert not errors, errors
            print("PASS: support counts, missing/long build metadata, links/focus, update states, empty/error/retry, en/vi, 5 widths light/dark")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
