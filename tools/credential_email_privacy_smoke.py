"""Email reveal lifecycle and locale layout, on a synthetic loopback console."""

from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from localization_ui_smoke import LOCALES, check_layout, select_locale
from playwright.sync_api import Error, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EMAIL = "someone42@example.test"
MASKED = "so***42@example.test"
REFERENCE = "credref-v1-" + "a" * 64 + ".json"


def main():
    calls = []
    pending = []
    hold = False
    fail = False
    item = {
        "filename": REFERENCE,
        "provider": "google_antigravity",
        "provider_variant": "google_antigravity",
        "credential_type": "oauth",
        "user_email": MASKED,
        "model_count": 1,
        "disabled": False,
    }

    def api(route):
        path = route.request.url.split("/api/credentials/", 1)[1].split("?", 1)[0]
        calls.append(path)
        assert EMAIL not in route.request.url
        if path == "status":
            return route.fulfill(
                json={
                    "items": [item],
                    "total": 1,
                    "has_more": False,
                    "stats": {"total": 1, "normal": 1},
                }
            )
        if path.startswith("email/"):
            if hold:
                pending.append(route)
                return
            if fail:
                return route.fulfill(status=503, json={"detail": "Synthetic email unavailable"})
            return route.fulfill(json={"user_email": EMAIL}, headers={"Cache-Control": "no-store"})
        if path.startswith("configuration/"):
            return route.fulfill(
                json={
                    "editable": True,
                    "editable_fields": ["credential_label"],
                    "credential_label": "",
                    "provider": item["provider"],
                }
            )
        if path.startswith("models/"):
            return route.fulfill(json={"model_ids": ["fixture-model"]})
        if path.startswith("errors/"):
            return route.fulfill(json={"error_codes": [], "error_messages": {}})
        return route.fulfill(json={"success": True, "models": {}})

    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        context.route("**/api/credentials/**", api)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/setup", wait_until="networkidle")
        page.locator("#setupPassword").fill(PASSWORD)
        page.locator("#setupPasswordConfirm").fill(PASSWORD)
        page.locator("#setupSubmitButton").click()
        expect(page).to_have_url(base + "/dashboard")
        page.goto(base + "/credentials", wait_until="networkidle")
        opener = page.locator('[data-credential-command="manage"]').first
        expect(page.locator(".cred-account-name")).to_have_text(MASKED)
        opener.click()
        dialog = page.locator(".credential-management-modal")
        email = dialog.locator("[data-management-email]")
        reveal = dialog.locator('[data-management-action="reveal-email"]')
        hide = dialog.locator('[data-management-action="hide-email"]')
        close = dialog.locator("[data-dialog-close]")
        expect(email).to_have_text(MASKED)
        expect(reveal).to_be_enabled()
        expect(reveal.locator('svg[aria-hidden="true"]')).to_have_count(1)
        expect(reveal).to_have_attribute(
            "aria-label", page.evaluate("t('credentials.management.reveal_email')")
        )
        assert not reveal.inner_text().strip(), "Email toggle must be icon-only"
        assert not any(path.startswith(("email/", "detail/")) for path in calls)
        assert EMAIL not in page.content()
        assert EMAIL not in page.evaluate("JSON.stringify(AppState.primaryCreds.data)")
        assert (
            page.locator("[data-credential-select]").first.get_attribute("data-filename")
            == REFERENCE
        )
        reveal.focus()
        page.keyboard.press("Enter")
        expect(email).to_have_text(EMAIL)
        expect(hide.locator('svg[aria-hidden="true"]')).to_have_count(1)
        expect(hide).to_have_attribute(
            "aria-label", page.evaluate("t('credentials.management.hide_email')")
        )
        assert not hide.inner_text().strip(), "Email toggle must be icon-only"
        assert EMAIL not in page.evaluate("JSON.stringify(AppState.primaryCreds.data)")
        hide.hover()
        hover_styles = hide.evaluate(
            """el => { const style = getComputedStyle(el); return [style.backgroundColor, style.borderTopColor]; }"""
        )
        assert hover_styles == ["rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"], hover_styles
        hide.click()
        expect(email).to_have_text(MASKED)
        assert EMAIL not in page.content()
        reveal.click()
        expect(email).to_have_text(EMAIL)
        close.click()
        expect(dialog).to_have_count(0)
        assert EMAIL not in page.content()
        opener.click()
        expect(email).to_have_text(MASKED)
        expect(reveal).to_be_enabled()
        fail = True
        reveal.click()
        expect(dialog.locator("[data-management-result]")).to_contain_text(
            "Synthetic email unavailable"
        )
        expect(email).to_have_text(MASKED)
        fail = False
        hold = True
        other_action = dialog.locator('[data-management-action="toggle"]')
        expect(other_action).to_be_enabled()
        reveal.click()
        expect(reveal).to_be_disabled()
        page.wait_for_timeout(100)
        assert pending, "The delayed request was not started"
        expect(other_action).to_be_enabled()
        close.click()
        expect(dialog).to_have_count(0)
        for route in pending:
            try:
                route.fulfill(json={"user_email": EMAIL})
            except Error:
                pass  # The modal's AbortController cancels this request.
        hold = False
        opener.click()
        expect(email).to_have_text(MASKED)
        assert EMAIL not in page.content()
        output = ROOT / "temp/credential-email-privacy"
        output.mkdir(parents=True, exist_ok=True)
        for width in (360, 768, 1024, 1440):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
            if width in (360, 1440):
                page.screenshot(path=str(output / f"masked-{width}.png"), full_page=True)
        close.click()
        for locale in LOCALES:
            select_locale(page, locale)
            page.reload(wait_until="networkidle")
            opener.click()
            expect(reveal).to_have_attribute(
                "aria-label", page.evaluate("t('credentials.management.reveal_email')")
            )
            check_layout(page, locale)
            close.click()
        assert not errors, errors
        browser.close()
        print("PASS: mask/reveal/hide/reopen/failure/late-response; 4 viewports; 15 locales")


if __name__ == "__main__":
    main()
