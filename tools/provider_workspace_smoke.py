"""Regression checks for consistent provider onboarding, with disposable data only."""

import json
import sys

from browser_smoke import PASSWORD, ROOT, disposable_runtime, install_fixtures
from playwright.sync_api import expect, sync_playwright


def main():
    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.grant_permissions(["clipboard-read", "clipboard-write"])
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
        page.goto(base + "/providers", wait_until="networkidle")
        for provider in ("openai_platform", "xai_console", "kimi", "poolside"):
            page.locator("#providerCatalogSearch").fill(provider)
            selector = page.locator(f'#providerCatalog [data-provider="{provider}"]')
            selector.click()
            workspace = page.locator("#" + selector.get_attribute("aria-controls"))
            expect(workspace.get_by_role("button", name="Thêm khóa", exact=True)).to_be_visible()
            key = workspace.locator('input[data-secret-lifetime="submit"], input[name="api_key"]')
            expect(key).to_have_attribute("placeholder", "Dán khóa API của bạn")
            expect(workspace.locator(".upload-title")).to_have_text("Thả tệp khóa API vào đây")
            assert workspace.locator(".provider-import-panel > .page-actions").count() == 0
        if "--quick" not in sys.argv:
            verify_kiro(page)
            verify_layout(page)
        assert not errors, errors
        browser.close()
    print("Provider workspace consistency passed.")


def verify_kiro(page):
    calls = []

    def respond(route):
        action = route.request.url.rsplit("/", 1)[-1]
        calls.append(action)
        payload = {"status": "cancelled"}
        if action == "start":
            payload = {
                "flow_id": "synthetic",
                "user_code": "TEST-CODE",
                "interval": 0,
                "expires_in": 300,
                "verification_uri": "https://app.kiro.dev/device",
            }
        if action == "complete":
            payload = {"status": "pending", "interval": 0}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/providers/kiro/oauth/*", respond)
    page.locator("#providerCatalogSearch").fill("kiro")
    page.locator("#providerSelector-kiro").click()
    workspace = page.locator("#providerWorkspace-kiro")
    form = workspace.locator("#kiroOAuthForm")
    form.locator('[type="submit"]').click()
    pending = workspace.locator(".provider-device-flow")
    expect(pending).to_be_visible()
    expect(form).to_be_hidden()
    expect(pending.locator(".provider-device-code")).to_have_text("TEST-CODE")
    expect(pending.locator('[data-i18n="btn_cancel"]')).to_have_text("Hủy")
    expect(pending.locator('[data-i18n="provider.ui.open_login"]')).to_have_attribute(
        "href", "https://app.kiro.dev/device"
    )
    expect(pending.locator('[data-i18n="provider.ui.copy_code"]')).to_be_visible()
    pending.locator('[data-i18n="provider.ui.copy_code"]').click()
    assert page.evaluate("navigator.clipboard.readText()") == "TEST-CODE"
    expect(pending.locator(".provider-device-expiry")).to_contain_text("Hết hạn lúc")
    expect(workspace.locator("#extended-kiro-oauth-region")).to_be_disabled()
    shots = ROOT / "temp" / "provider-workspace-consistency"
    shots.mkdir(parents=True, exist_ok=True)
    for width, theme in ((1440, "light"), (320, "dark")):
        page.set_viewport_size({"width": width, "height": 1000})
        page.evaluate("theme => PolarisTheme.setPreference(theme)", theme)
        expect(page.locator("html")).not_to_have_class("theme-switching")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        workspace.screenshot(path=str(shots / f"kiro-pending-{width}-{theme}.png"))
    pending.locator('[data-i18n="runtime.check_authorization"]').click()
    expect(pending).to_be_visible()
    pending.locator('[data-i18n="btn_cancel"]').click()
    expect(pending).to_be_hidden()
    expect(form).to_be_visible()
    expect(form.locator('[type="submit"]')).to_be_focused()
    expect(workspace.locator("#extended-kiro-oauth-region")).to_be_enabled()
    assert calls == ["start", "complete", "cancel"]
    expect(workspace.locator(':scope > details[data-disclosure-kind="settings"]')).to_have_count(1)
    expect(form.locator('[name="region"]')).to_have_count(0)
    workspace.locator(".extended-provider-advanced > summary").click()
    page.set_viewport_size({"width": 1440, "height": 1000})
    workspace.screenshot(path=str(shots / "kiro-settings-1440-dark.png"))
    workspace.locator(".extended-provider-advanced > summary").click()


def verify_layout(page):
    shots = ROOT / "temp" / "provider-workspace-consistency"
    shots.mkdir(parents=True, exist_ok=True)
    for provider in (
        "google_antigravity",
        "claude_code",
        "openai_platform",
        "kimi",
        "poolside",
        "kiro",
    ):
        page.locator("#providerCatalogSearch").fill(provider)
        selector = page.locator(f'#providerCatalog [data-provider="{provider}"]')
        selector.click()
        workspace = page.locator("#" + selector.get_attribute("aria-controls"))
        for width, theme in ((1440, "light"), (1440, "dark"), (768, "light"), (320, "dark")):
            page.set_viewport_size({"width": width, "height": 1000})
            page.evaluate("theme => PolarisTheme.setPreference(theme)", theme)
            expect(page.locator("html")).not_to_have_class("theme-switching")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                provider,
                width,
            )
            workspace.screenshot(path=str(shots / f"{provider}-{width}-{theme}.png"))


if __name__ == "__main__":
    main()
