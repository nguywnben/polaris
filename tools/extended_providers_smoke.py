"""Exercise all additional provider forms without external account calls."""

import json
from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime, install_fixtures
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("kimi", "kiro", "cloudflare", "nvidia", "opencode", "poolside", "kimchi", "kilo")


def main():
    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        install_fixtures(page)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        saved = []

        def add_credential(route):
            payload = route.request.post_data_json
            assert payload["api_key"] == "fixture-key-not-a-real-secret"
            saved.append((route.request.url, payload))
            route.fulfill(
                status=201,
                content_type="application/json",
                body=json.dumps(
                    {
                        "success": True,
                        "credential_saved": True,
                        "connection_test_required": True,
                        "filename": "fixture.json",
                        "model_count": 2,
                    }
                ),
            )

        page.route("**/api/providers/extended/*/credentials", add_credential)
        page.goto(base + "/setup", wait_until="networkidle")
        page.locator("#setupPassword").fill(PASSWORD)
        page.locator("#setupPasswordConfirm").fill(PASSWORD)
        page.locator("#setupSubmitButton").click()
        expect(page).to_have_url(base + "/dashboard")
        page.goto(base + "/providers", wait_until="networkidle")
        expect(page.locator('#providerCatalog [role="tab"]')).to_have_count(17)
        shots = ROOT / "temp" / "extended-providers-ui"
        shots.mkdir(parents=True, exist_ok=True)
        for provider in PROVIDERS:
            page.locator("#providerCatalogSearch").fill(provider)
            selector = page.locator(f"#providerSelector-{provider}")
            selector.click()
            workspace = page.locator(f"#providerWorkspace-{provider}")
            expect(workspace).to_be_visible()
            expect(workspace.locator('[type="password"]')).not_to_be_focused()
            toggle = workspace.locator(".setup-secret-toggle")
            expect(toggle).to_be_hidden()
            key = workspace.locator('[name="api_key"]')
            key.fill("fixture-key-not-a-real-secret")
            expect(toggle).to_be_visible()
            toggle.click()
            expect(key).to_have_attribute("type", "text")
            toggle.click()
            if provider == "cloudflare":
                workspace.locator('[name="account_id"]').fill("a" * 32)
            workspace.locator("summary").click()
            if provider == "opencode":
                workspace.locator('[name="plan"]').select_option("go")
                expect(workspace.locator('[name="base_url"]')).to_have_attribute(
                    "placeholder", "https://opencode.ai/zen/go/v1"
                )
            for width, theme in ((1440, "light"), (1440, "dark"), (360, "light"), (360, "dark")):
                page.set_viewport_size({"width": width, "height": 1000})
                page.evaluate("(theme) => document.documentElement.dataset.theme = theme", theme)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
                    provider,
                    width,
                    theme,
                )
                if provider == "kimchi":
                    for logo in page.locator('img[src$="/kimchi-logo.png"]').all():
                        expect(logo).to_have_css("border-radius", "50%")
                    for frame in page.locator(".extended-logo-kimchi").all():
                        expect(frame).to_have_css("background-color", "rgba(0, 0, 0, 0)")
                if provider in ("kimi", "kiro", "cloudflare", "opencode", "kimchi"):
                    page.screenshot(
                        path=str(shots / f"{provider}-{width}-{theme}.png"), full_page=True
                    )
            workspace.locator('[type="submit"]').click()
            expect(key).to_have_value("")
            expect(workspace.locator("[data-extended-saved]")).to_be_visible()
            page.set_viewport_size({"width": 1440, "height": 1000})
        assert len(saved) == 8, saved
        assert not errors, errors
        context.close()
        browser.close()
    print("Extended providers: 8 forms, 32 responsive/theme cases, no page errors.")


if __name__ == "__main__":
    main()
