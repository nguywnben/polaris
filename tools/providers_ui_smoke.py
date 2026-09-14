"""Provider catalog and onboarding UI checks in an isolated, synthetic runtime."""

from pathlib import Path

from browser_smoke import PASSWORD, PROVIDER_SECRET, disposable_runtime, install_fixtures
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        install_fixtures(page)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        screenshots = ROOT / "temp/providers-ui"
        screenshots.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/providers", wait_until="networkidle")
            expect(page.locator("#providerCapabilityStatus")).to_be_hidden()
            expect(page.locator("#providersTab > #providerCatalogPagination")).to_be_visible()
            page.locator("#providerCatalogSearch").fill("Ollama")
            expect(
                page.locator('#providerCatalog [role="tab"][tabindex="0"]:visible')
            ).to_have_count(1)
            page.locator("#providerCatalogSearch").fill("not-a-real-provider-123")
            expect(page.locator("#providerCatalogEmpty")).to_be_visible()
            expect(page.locator("#providerCatalogPagination")).to_be_hidden()
            page.locator("#providerCatalogSearch").fill("")
            page.locator("#providerCatalogNextBtn").click()
            expect(
                page.locator('#providerCatalog [role="tab"][tabindex="0"]:visible')
            ).to_have_count(1)
            page.locator("#providerSelectorOllama").click()
            page.locator("#ollamaBaseUrl").fill("http://127.0.0.1:11434")
            page.locator("#ollamaApiKey").fill(PROVIDER_SECRET)
            page.locator("#addOllamaBtn").click()
            expect(page.locator("#ollamaSaveResult")).to_be_visible()
            page.locator("#providerCatalogPrevBtn").click()
            page.locator("#providerSelectorGoogleAntigravity").focus()
            page.keyboard.press("ArrowRight")
            expect(page.locator("#providerSelectorGoogleAiStudio")).to_be_focused()
            expect(page.locator("#providerWorkspaceGoogleAiStudio")).to_be_visible()
            page.keyboard.press("Home")
            expect(page.locator("#providerWorkspaceGoogleAntigravity")).to_be_visible()
            expect(
                page.locator(
                    '#providerWorkspaceGoogleAntigravity [data-i18n="providers.oauth_intro"]'
                )
            ).to_contain_text("Lấy liên kết")

            # Check every credential variant; settings are read, never saved.
            for variant in (
                "google_antigravity",
                "google_ai_studio",
                "grok",
                "xai_console",
                "codex",
                "openai_platform",
                "claude_code",
                "claude_platform",
                "ollama",
            ):
                page.locator("#providerCatalogSearch").fill(variant)
                selector = page.locator(f'#providerCatalog [data-provider="{variant}"]')
                expect(selector).to_be_visible()
                selector.click()
                panel_id = selector.get_attribute("aria-controls")
                panel = page.locator("#" + panel_id)
                expect(panel).to_be_visible()
                expect(page.locator("#providersTab > #providerCatalogPagination")).to_have_count(1)
                details = panel.locator("details.provider-secondary-disclosure")
                if details.count():
                    details.locator("summary").click()
                    expect(panel.locator('[id$="SettingsForm"]').first).to_be_visible()
                for width, theme in (
                    (320, "light"),
                    (360, "light"),
                    (768, "light"),
                    (1024, "light"),
                    (1440, "light"),
                    (1440, "dark"),
                ):
                    page.set_viewport_size({"width": width, "height": 1000})
                    page.emulate_media(color_scheme=theme)
                    page.mouse.move(0, 0)
                    assert not page.locator("body").evaluate("el => el.scrollWidth > innerWidth"), (
                        variant,
                        width,
                    )
                    assert not panel.evaluate("el => el.scrollWidth > el.clientWidth"), (
                        variant,
                        width,
                    )
                    if variant in ("google_antigravity", "openai_platform", "ollama"):
                        page.screenshot(
                            path=str(screenshots / f"{variant}-{width}-{theme}.png"),
                            full_page=True,
                            animations="disabled",
                        )
            page.locator("#providerCatalogSearch").fill("")
            page.locator("#providerSelectorGoogleAntigravity").click()
            for width, theme in (
                (320, "light"),
                (768, "light"),
                (1024, "light"),
                (1440, "light"),
                (1440, "dark"),
            ):
                page.set_viewport_size({"width": width, "height": 1000})
                page.emulate_media(color_scheme=theme)
                assert not page.locator("body").evaluate("el => el.scrollWidth > innerWidth"), (
                    "catalog",
                    width,
                )
                page.screenshot(
                    path=str(screenshots / f"catalog-{width}-{theme}.png"),
                    full_page=True,
                    animations="disabled",
                )
                if theme == "dark":
                    assert (
                        page.locator("#providerSelectorCodex img").evaluate(
                            "el => getComputedStyle(el).filter"
                        )
                        == "invert(1)"
                    )
            page.evaluate("AppState.lang = 'en'; applyLanguage()")
            expect(page.locator('[data-i18n="providers.oauth_intro"]')).to_contain_text(
                "Generate an authorization link"
            )
            page.evaluate("AppState.lang = 'vi'; applyLanguage()")
            expect(page.locator('[data-i18n="providers.oauth_intro"]')).to_contain_text(
                "Lấy liên kết"
            )
            capability_failure = {"active": True}
            page.route(
                "**/api/providers/capabilities",
                lambda route: (
                    route.fulfill(status=503, json={"detail": "Synthetic catalog unavailable"})
                    if capability_failure["active"]
                    else route.fallback()
                ),
            )
            page.reload(wait_until="networkidle")
            expect(page.locator("#providerCapabilityStatus")).to_have_attribute(
                "data-state", "failed"
            )
            expect(page.locator("#providerCapabilityRetryBtn")).to_be_visible()
            capability_failure["active"] = False
            page.locator("#providerCapabilityRetryBtn").click()
            expect(page.locator("#providerCapabilityStatus")).to_be_hidden()
            assert not errors, errors
            print(
                "PASS: Nine provider variants, search/paging/keyboard, synthetic connection, light/dark, 320–1440px"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
