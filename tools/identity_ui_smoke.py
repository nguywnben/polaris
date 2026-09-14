"""Identity UI coverage against disposable storage and intercepted mutation failures."""

import time
from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright


def main():
    output = Path(__file__).resolve().parents[1] / "temp/identity-ui"
    output.mkdir(parents=True, exist_ok=True)
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/identity", wait_until="networkidle")
            expect(page.locator("#identityPrincipalSummary")).to_have_attribute("aria-busy", "false")
            assert page.locator(".identity-permission-list li").count() > 10
            expect(page.locator('[data-identity-id="local-owner"] select')).to_have_count(0)
            expect(page.locator("#identityPageStatus")).not_to_be_visible()
            expect(page.locator("#identityOidcAdvance")).not_to_be_visible()
            inventory = context.request.get(base + "/api/identity/sessions").json()
            assert inventory["sessions"]
            for session in inventory["sessions"]:
                assert abs(session["issued_at"] - time.time()) < 60
                assert session["issued_at"] <= session["last_seen_at"] < session["idle_expires_at"]
                assert session["idle_expires_at"] <= session["absolute_expires_at"]
            expect(page.locator("#identitySessionList")).not_to_contain_text("1970")
            for width in [320, 360, 768, 1024, 1440]:
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.locator("html").evaluate(
                    "el => el.scrollWidth <= window.innerWidth"
                ), f"Horizontal overflow at {width}"
                if width in [360, 1440]:
                    page.screenshot(path=str(output / f"vi-{width}.png"), full_page=True)
            # Protected actions still require confirmation; cancel never sends a mutation.
            mutations = []
            page.on("request", lambda request: mutations.append(request.url)
                    if request.method == "POST" and "/api/identity/" in request.url else None)
            page.locator('[data-ui-action="identity-session-revoke"]').first.click()
            expect(page.locator("#identityConfirmDialog")).to_be_visible()
            page.locator('[data-ui-action="identity-confirm-cancel"]').click()
            assert not mutations
            page.locator("#identityCreateButton").click()
            page.locator("#identityCreateIssuer").fill("https://idp.example")
            page.locator("#identityCreateSubject").fill("synthetic-operator")
            context.route("**/api/identity/identities", lambda route: route.fulfill(
                status=409, json={"detail": "Synthetic conflict"}))
            page.locator("#identityCreateSubmit").click()
            expect(page.locator("#identityCreateStatus")).not_to_be_empty()
            expect(page.locator("#identityCreateSubject")).to_have_value("synthetic-operator")
            page.locator("#identityCreateSubject").press("Escape")
            expect(page.locator("#identityCreateDialog")).not_to_be_visible()
            page.goto(base + "/config", wait_until="networkidle")
            page.locator("#themePreference").select_option("dark")
            with page.expect_navigation(wait_until="networkidle"):
                page.locator("#consoleLanguage").select_option("en")
            page.goto(base + "/identity", wait_until="networkidle")
            expect(page.locator("#identityTab h1")).to_have_text("Identity and sessions")
            page.screenshot(path=str(output / "en-dark-1440.png"), full_page=True)
            context.route("**/api/identity/sessions?*", lambda route: route.fulfill(
                status=503, json={"detail": "Synthetic unavailable"}))
            page.locator('[data-ui-action="identity-refresh"]').click()
            expect(page.locator("#identitySessionStatus")).not_to_be_empty()
            expect(page.locator("#identitySessionList")).to_have_attribute("aria-busy", "false")
            assert not errors, errors
            print("PASS: five widths, vi/en, light/dark, permission items, read-only owner, "
                  "create conflict draft, Escape, revoke cancel, session error and busy reset")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
