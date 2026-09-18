"""Verify consistent, localized save feedback using synthetic responses only."""

import json

from browser_smoke import PASSWORD, ROOT, disposable_runtime, install_fixtures
from extended_providers_smoke import PROVIDERS
from playwright.sync_api import expect, sync_playwright


def main():
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
        response = {
            "credential_saved": True,
            "credential_action": "created",
            "model_count": 41,
            "message": "ENGLISH_BACKEND_COPY secret-must-not-render",
        }
        failure = {"enabled": False}

        def respond(route):
            route.fulfill(
                status=400 if failure["enabled"] else 201,
                content_type="application/json",
                body=json.dumps({"detail": "invalid-key"} if failure["enabled"] else response),
            )

        page.route("**/api/providers/**/credentials", respond)
        cases = [
            ("xai_console", "xaiApiKey", "addXaiKeyBtn", "xaiApiKey"),
            ("ollama", "ollamaApiKey", "addOllamaBtn", "ollama"),
            (
                "google_ai_studio",
                "googleAiStudioApiKey",
                "addGoogleAiStudioKeyBtn",
                "googleAiStudio",
            ),
            (
                "openai_platform",
                "openaiPlatformApiKey",
                "addOpenaiPlatformKeyBtn",
                "openaiPlatform",
            ),
            (
                "claude_platform",
                "claudePlatformApiKey",
                "addClaudePlatformKeyBtn",
                "claudePlatform",
            ),
        ]
        for provider, input_id, button_id, prefix in cases:
            select(page, provider)
            form_id = page.locator("#" + input_id).evaluate("el => el.closest('form').id")
            opener = page.locator(f'.provider-key-entry-button[aria-controls="{form_id}"]')
            if opener.count():
                opener.click()
            page.locator("#" + input_id).fill("synthetic-key-only")
            page.locator("#" + button_id).click()
            verify_result(page, prefix)
        for provider, expression, prefix in (
            ("grok", "showXaiCredentialSaveResult('oauth', data)", "xaiOauth"),
            ("codex", "showOpenAICredentialSaveResult('codex', data)", "codexOauth"),
            ("claude_code", "showAnthropicCredentialSaveResult('code', data)", "claudeOauth"),
            ("google_antigravity", "completePrimaryCredentialSave(data)", "primary"),
        ):
            select(page, provider)
            # Exercise existing completion presenters with the same synthetic response.
            page.evaluate("data => " + expression, response)
            # Some legacy results live inside a hidden authorization form before login.
            result = page.locator(f"#{prefix}SaveResult")
            expect(result.locator("p")).to_contain_text("41")
            assert "ENGLISH_BACKEND_COPY" not in result.text_content()
        for provider in PROVIDERS:
            select(page, provider)
            form = page.locator(f"#extended-{provider}-credential-form")
            if provider == "kiro":
                page.locator("#providerWorkspace-kiro summary", has_text="API Key").click()
            page.locator(
                f'.provider-key-entry-button[aria-controls="extended-{provider}-credential-form"]'
            ).click()
            form.locator('[name="api_key"]').fill("synthetic-key-only")
            if provider == "cloudflare":
                form.locator('[name="account_id"]').fill("a" * 32)
            form.locator('[type="submit"]').click()
            verify_result(page, f"extended-{provider}")
            expect(form.locator('[name="api_key"]')).to_have_value("")
        # Saved metadata should update with the locale, not remain in the old language.
        for locale in (
            "en",
            "zh-CN",
            "zh-TW",
            "de",
            "es",
            "fr",
            "id",
            "it",
            "ja",
            "ko",
            "pt",
            "ru",
            "th",
            "tr",
            "vi",
        ):
            page.evaluate("locale => { setLanguage(locale, true); applyLanguage(); }", locale)
            expected = page.evaluate("providerCredentialResultCopy({model_count: 41})")
            expect(page.locator("#extended-cerebrasSaveResultText")).to_have_text(expected["body"])
            expect(page.locator("#extended-cerebrasSaveResultTitle")).to_have_text(
                expected["title"]
            )
        # A failed retry must not leave a stale success visible.
        form = page.locator("#extended-cerebras-credential-form")
        failure["enabled"] = True
        page.locator(
            '.provider-key-entry-button[aria-controls="extended-cerebras-credential-form"]'
        ).click()
        form.locator('[name="api_key"]').fill("synthetic-invalid-key")
        form.locator('[type="submit"]').click()
        expect(page.locator("#extended-cerebrasSaveResult")).to_be_hidden()
        expect(form.locator('[name="api_key"]')).to_have_value("synthetic-invalid-key")
        expect(form.locator('[type="submit"]')).to_be_enabled()
        failure["enabled"] = False
        response["credential_action"] = "updated"
        form.locator('[type="submit"]').click()
        expect(page.locator("#extended-cerebrasSaveResultTitle")).to_have_text(
            page.evaluate("t('runtime.credential_updated_title')")
        )
        shots = ROOT / "temp" / "provider-save-results"
        shots.mkdir(parents=True, exist_ok=True)
        for width, theme in ((1440, "light"), (320, "dark")):
            page.set_viewport_size({"width": width, "height": 1000})
            page.evaluate("theme => PolarisTheme.setPreference(theme)", theme)
            expect(page.locator("html")).not_to_have_class("theme-switching")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert page.locator('#extended-cerebrasSaveResult [data-tab="credentials"]').evaluate(
                "button => getComputedStyle(button).whiteSpace === 'nowrap'"
            )
            page.locator("#providerWorkspace-cerebras").screenshot(
                path=str(shots / f"{width}-{theme}.png")
            )
        documents = []
        page.on(
            "request",
            lambda request: (
                documents.append(request.url) if request.is_navigation_request() else None
            ),
        )
        page.locator('#extended-cerebrasSaveResult [data-tab="credentials"]').click()
        expect(page).to_have_url(base + "/credentials")
        assert not documents, documents
        assert not errors, errors
        browser.close()
    print(
        "Provider save results: legacy/new API-key flows, 15 locales, retry, responsive themes and SPA View passed."
    )


def select(page, provider):
    page.locator("#providerCatalogSearch").fill(provider)
    page.locator(f'#providerCatalog [data-provider="{provider}"]').click()


def verify_result(page, prefix):
    result = page.locator(f"#{prefix}SaveResult")
    expect(result).to_be_visible()
    expect(result.locator("strong")).to_have_text("Đã thêm thông tin xác thực vào kho")
    expect(result.locator("p")).to_contain_text("41")
    expect(result.locator('[data-tab="credentials"]')).to_have_text("Xem")
    assert "ENGLISH_BACKEND_COPY" not in result.inner_text()
    assert "secret-must-not-render" not in result.inner_text()


if __name__ == "__main__":
    main()
