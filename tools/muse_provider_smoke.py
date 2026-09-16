"""Isolated Muse OAuth UI, imports, localization and responsive/theme regression.

Only synthetic grants are used. External browser traffic is blocked; no model runs.
"""

import json
from pathlib import Path

from browser_smoke import PASSWORD, ROOT, disposable_runtime, install_fixtures
from playwright.sync_api import expect, sync_playwright


def main():
    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1100})
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        install_fixtures(page)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        calls = []
        state = {"complete": False, "unsafe": False}

        def oauth(route):
            action = route.request.url.rsplit("/", 1)[-1]
            calls.append(action)
            if action == "start":
                assert route.request.post_data_json == {"credential_label": "Muse smoke account"}
                body = {
                    "flow_id": "muse_code_" + "a" * 43,
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://auth.meta.com/oauth/device/?code=ABCD-EFGH",
                    "expires_in": 600,
                    "interval": 1,
                    "status": "pending",
                }
                if state["unsafe"]:
                    body["verification_uri"] = "https://evil.invalid/oauth/device/?code=ABCD-EFGH"
            elif action == "complete":
                body = (
                    {
                        "success": True,
                        "status": "complete",
                        "credential_saved": True,
                        "provider": "muse_code",
                        "provider_variant": "muse_code",
                        "credential_action": "created",
                        "filename": "muse_code-fixture.json",
                        "model_count": 3,
                        "connection_test_required": True,
                        "message": "UNTRUSTED_BACKEND_TEXT",
                    }
                    if state["complete"]
                    else {"status": "pending", "interval": 1}
                )
            else:
                body = {"status": "cancelled", "success": True}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

        page.route("**/api/providers/muse-code/oauth/*", oauth)
        page.goto(base + "/setup", wait_until="networkidle")
        page.locator("#setupPassword").fill(PASSWORD)
        page.locator("#setupPasswordConfirm").fill(PASSWORD)
        page.locator("#setupSubmitButton").click()
        expect(page).to_have_url(base + "/dashboard")
        page.goto(base + "/providers", wait_until="networkidle")
        cards = page.locator("#providerCatalog [data-provider]").evaluate_all(
            "els => els.map(el => el.dataset.provider)"
        )
        assert cards.index("muse_code") + 1 == cards.index("meta"), cards
        assert page.locator("#providerCatalog .provider-capabilities").evaluate_all(
            "els => els.every(el => el.children.length === 1)"
        )
        page.locator("#providerCatalogSearch").fill("Muse Code")
        page.locator("#providerSelector-muse_code").click()
        workspace = page.locator("#providerWorkspace-muse_code")
        expect(workspace).to_be_visible()
        expect(workspace.locator('input[name="api_key"]')).to_have_count(0)
        expect(workspace.locator(".provider-settings-panel")).to_have_count(1)
        workspace.locator(".provider-settings-panel summary").click()
        workspace.locator('input[name="credential_label"]').fill("Muse smoke account")
        expect(workspace.locator('[data-i18n="provider.muse.notice"]')).to_have_count(0)
        expect(workspace.locator("#museCancelLogin")).to_have_count(0)
        expect(workspace.locator('[data-i18n="provider.ui.open_login"]')).to_have_count(0)
        expect(page.locator("#providerSelector-muse_code .provider-capabilities")).to_contain_text(
            "OAuth"
        )
        page.locator("#museStartLogin").focus()
        page.keyboard.press("Enter")
        expect(page.locator("#musePending")).to_be_visible()
        expect(page.locator("#museStartLogin")).to_be_visible()
        expect(page.locator("#museDeviceCode")).to_have_text("ABCD-EFGH")
        assert page.locator("#museDeviceCode").evaluate(
            "el => parseFloat(getComputedStyle(el).fontSize) <= 16"
        )
        expect(page.locator("#museLoginLink")).not_to_be_focused()
        expect(workspace.locator(".endpoint-code-card.auth-link-card > a")).to_have_attribute(
            "href", "https://auth.meta.com/oauth/device/?code=ABCD-EFGH"
        )
        expect(workspace.locator("#musePending .page-actions .btn")).to_have_count(1)
        expect(page).to_have_url(base + "/providers")
        page.wait_for_timeout(2100)
        assert calls == ["start"], calls
        page.locator("#museCompleteLogin").click()
        expect(page.locator("#museCompleteLogin")).to_be_enabled()
        assert calls == ["start", "complete"], calls
        page.wait_for_timeout(2100)
        assert calls == ["start", "complete"], calls

        shots = ROOT / "temp" / "muse-provider-ui"
        shots.mkdir(parents=True, exist_ok=True)
        for theme in ("light", "dark"):
            page.evaluate("theme => PolarisTheme.setPreference(theme)", theme)
            for width in (1440, 1024, 768, 360, 320):
                page.set_viewport_size({"width": width, "height": 1100})
                expect(page.locator("html")).not_to_have_class("theme-switching")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                    theme,
                    width,
                )
                assert (
                    workspace.locator("#museLoginLink").evaluate(
                        "el => getComputedStyle(el).fontWeight"
                    )
                    == "400"
                )
                if width in (1440, 320):
                    page.screenshot(path=str(shots / f"{theme}-{width}.png"), full_page=True)

        state["complete"] = True
        page.locator("#museCompleteLogin").click()
        expect(page.locator("#museOAuthSaveResult")).to_be_visible()
        expect(page.locator("#museOAuthSaveResult")).not_to_contain_text("UNTRUSTED_BACKEND_TEXT")
        expect(page.locator("#musePending")).to_be_hidden()
        for locale in (
            "en",
            "vi",
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
        ):
            page.evaluate("locale => { setLanguage(locale, false); applyLanguage(); }", locale)
            assert (
                not workspace.locator('[data-i18n="provider.muse.help"]')
                .text_content()
                .startswith("provider.")
            )
            assert not workspace.locator("#museSettingsHelp").text_content().startswith("provider.")
        page.evaluate("setLanguage('vi', false); applyLanguage()")

        # Downloaded example is synthetic; real import uses only an isolated DB.
        with page.expect_download() as download:
            workspace.locator('[data-provider-example="muse_code"]').click()
        sample = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
        assert "refresh_token" not in sample and "api_key" not in sample
        sample["access_token"] = "synthetic-only-oauth"
        sample["user_email"] = "smoke@example.test"
        workspace.locator('input[type="file"]').set_input_files(
            {
                "name": "muse.json",
                "mimeType": "application/json",
                "buffer": json.dumps(sample).encode(),
            }
        )
        with page.expect_response(
            "**/api/providers/extended/muse_code/credentials/import"
        ) as imported:
            workspace.locator(".provider-import-panel .page-actions .btn").first.click()
        assert imported.value.status == 200, imported.value.text()
        assert imported.value.json()["uploaded_count"] == 1, imported.value.json()

        page.locator("#museStartLogin").click()
        expect(page.locator("#musePending")).to_be_visible()
        before_restart = len(calls)
        page.locator("#museStartLogin").click()
        expect(page.locator("#museStartLogin")).to_be_enabled()
        assert calls[before_restart:] == ["cancel", "start"], calls
        expect(page.locator("#musePending")).to_be_visible()
        state["unsafe"] = True
        page.locator("#museStartLogin").click()
        expect(page.locator("#museStartLogin")).to_be_enabled()
        expect(page.locator("#musePending")).to_be_hidden()
        assert not errors, errors
        context.close()
        browser.close()
        print(
            "Muse UI: catalog order, shared OAuth link card, manual start/check/save/restart, no polling, safe URL, offline import, 15 locales, 5 widths, 2 themes passed."
        )


if __name__ == "__main__":
    main()
