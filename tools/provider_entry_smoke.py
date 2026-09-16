"""Provider entry/success transitions with disposable data and synthetic secrets."""

from browser_smoke import PASSWORD, ROOT, disposable_runtime, install_fixtures
from playwright.sync_api import expect, sync_playwright

CANARY = "SYNTHETIC_CREDENTIAL_MUST_NOT_RENDER"
SAVED = {
    "credential_saved": True,
    "credential_action": "created",
    "model_count": 5,
    "credentials": {"token": CANARY},
    "message": "UNTRANSLATED_BACKEND_MESSAGE",
}


def select(page, provider):
    page.locator("#providerCatalogSearch").fill(provider)
    card = page.locator(f'#providerCatalog [data-provider="{provider}"]')
    card.click()
    return page.locator("#" + card.get_attribute("aria-controls"))


def verify_oauth(page):
    cases = (
        (
            "google_antigravity",
            "primary",
            "getPrimaryAuthBtn",
            "getPrimaryCredsBtn",
            "primaryAuthUrlSection",
            None,
            "/api/auth/start",
            "/api/auth/callback",
        ),
        (
            "grok",
            "xaiOauth",
            "startXaiOauthBtn",
            "saveXaiOauthBtn",
            "xaiOauthFields",
            "xaiAuthorizationCode",
            "/api/providers/xai/oauth/start",
            "/api/providers/xai/oauth/complete",
        ),
        (
            "claude_code",
            "claudeOauth",
            "startClaudeOauthBtn",
            "saveClaudeOauthBtn",
            "claudeOauthFields",
            "claudeAuthorizationCode",
            "/api/providers/anthropic/claude-code/oauth/start",
            "/api/providers/anthropic/claude-code/oauth/complete",
        ),
        (
            "codex",
            "codexOauth",
            "startCodexOauthBtn",
            "completeCodexOauthBtn",
            "codexOauthFields",
            None,
            "/api/providers/openai/codex/oauth/start",
            "/api/providers/openai/codex/oauth/complete",
        ),
    )
    page.route("**/api/auth/status?*", lambda route: route.fulfill(json={"status": "completed"}))
    for provider, prefix, start_id, save_id, fields_id, input_id, start_url, save_url in cases:
        state = {"fail": True, "calls": 0}

        def save(route):
            state["calls"] += 1
            route.fulfill(
                status=503 if state["fail"] else 200,
                json={"error": "temporary_unavailable"} if state["fail"] else SAVED,
            )

        page.route(
            "**" + start_url,
            lambda route: route.fulfill(
                json={
                    "state": "synthetic",
                    "flow_id": "synthetic",
                    "auth_url": "https://example.invalid/auth",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://example.invalid/device",
                }
            ),
        )
        page.route("**" + save_url, save)
        workspace = select(page, provider)
        start, submit = page.locator("#" + start_id), page.locator("#" + save_id)
        fields, result = page.locator("#" + fields_id), page.locator(f"#{prefix}SaveResult")
        start.click()
        expect(fields).to_be_visible()
        if input_id:
            page.locator("#" + input_id).fill("synthetic-code")
        submit.click()
        expect(submit).to_be_enabled()
        expect(fields).to_be_visible()
        expect(result).to_be_hidden()
        assert state["calls"] == 1
        state["fail"] = False
        if input_id:
            page.locator("#" + input_id).fill("synthetic-code")
        submit.click()
        expect(result).to_be_visible()
        expect(fields).to_be_hidden()
        expect(start).to_be_visible()
        assert not fields.locator("input,textarea").evaluate_all(
            "items => items.some(item => item.value)"
        )
        assert not fields.locator("a").evaluate_all(
            "items => items.some(item => item.getAttribute('href') || item.textContent)"
        )
        assert CANARY not in page.content()
        assert "UNTRANSLATED_BACKEND_MESSAGE" not in workspace.inner_text()
        assert state["calls"] == 2
        for width, theme in ((1440, "light"), (360, "dark")):
            page.set_viewport_size({"width": width, "height": 1000})
            page.evaluate("theme => PolarisTheme.setPreference(theme)", theme)
            expect(page.locator("html")).not_to_have_class("theme-switching")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            workspace.screenshot(
                path=str(ROOT / "temp" / "provider-entry" / f"{provider}-{theme}.png")
            )
        start.click()
        expect(fields).to_be_visible()
        expect(result).to_be_hidden()
        page.unroute("**" + save_url, save)


def verify_keys(page):
    cases = (
        ("xai_console", "xaiCredentialForm", "xaiApiKey", "/api/providers/xai/credentials"),
        (
            "google_ai_studio",
            "googleAiStudioCredentialForm",
            "googleAiStudio",
            "/api/providers/google-ai-studio/credentials",
        ),
        (
            "openai_platform",
            "openaiPlatformCredentialForm",
            "openaiPlatform",
            "/api/providers/openai/platform/credentials",
        ),
        (
            "claude_platform",
            "claudePlatformCredentialForm",
            "claudePlatform",
            "/api/providers/anthropic/platform/credentials",
        ),
    )
    for provider, form_id, prefix, endpoint in cases:
        workspace = select(page, provider)
        form = page.locator("#" + form_id)
        opener = workspace.locator(".provider-key-entry-button")
        result = page.locator(f"#{prefix}SaveResult")
        expect(form).to_be_hidden()
        expect(opener).to_have_text("Nhập khóa API")
        opener.click()
        key = form.locator('input[type="password"]')
        expect(key).not_to_be_focused()
        key.fill("fixture-api-key-not-a-real-secret")
        page.route("**" + endpoint, lambda route: route.fulfill(json=SAVED))
        form.locator('button[type="submit"]').click()
        expect(result).to_be_visible()
        expect(form).to_be_hidden()
        expect(key).to_have_value("")
        expect(opener).to_have_attribute("aria-expanded", "false")
        assert CANARY not in page.content()
        for width, theme in ((1440, "light"), (360, "dark")):
            page.set_viewport_size({"width": width, "height": 1000})
            page.evaluate("theme => PolarisTheme.setPreference(theme)", theme)
            expect(page.locator("html")).not_to_have_class("theme-switching")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            workspace.screenshot(
                path=str(ROOT / "temp" / "provider-entry" / f"{provider}-{theme}.png")
            )
        opener.click()
        expect(form).to_be_visible()
        expect(result).to_be_hidden()
        expect(key).to_have_value("")


def main():
    (ROOT / "temp" / "provider-entry").mkdir(parents=True, exist_ok=True)
    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
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
        verify_oauth(page)
        verify_keys(page)
        for locale in page.evaluate("Object.keys(PROVIDER_PRODUCT_COPY)"):
            page.evaluate("locale => {setLanguage(locale, true); applyLanguage();}", locale)
            translations = page.evaluate("PROVIDER_DESCRIPTION_KEYS.map(key => t(key))")
            assert len(translations) == 23
            assert len(set(translations)) == 23
            assert translations == page.evaluate("locale => PROVIDER_PRODUCT_COPY[locale]", locale)
            assert all(
                "{provider}" not in copy and not copy.startswith("provider")
                for copy in translations
            )
            assert all("OAuth" not in copy and "API Key" not in copy for copy in translations)
            expect(page.locator(".provider-key-entry-button").first).to_have_text(
                page.evaluate("t('provider.ui.enter_key')")
            )
            assert page.evaluate("""Object.values(PROVIDER_WORKSPACES).every(definition => {
                const card = document.getElementById(definition.selectorId);
                const panel = document.getElementById(definition.panelId);
                const description = card.querySelector('.provider-summary p');
                return description.textContent === t(description.dataset.i18n)
                    && panel.querySelector('.provider-workspace-heading p').textContent === description.textContent;
            })""")
        assert not errors, errors
        browser.close()
    print("Provider entry transitions passed: old OAuth, API keys, 15 locales, responsive themes.")


if __name__ == "__main__":
    main()
