"""Verify completed Settings/OIDC journeys against a disposable SQLite instance only."""

from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PASSPHRASE = "Disposable-backup-2026-only"
LOCALES = (
    "en",
    "vi",
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
    "zh-CN",
    "zh-TW",
)


def check_layout(page, name, screenshots):
    # Bounded 45-state locale sweep across the three affected surfaces.
    page.set_viewport_size({"width": 360, "height": 1000})
    for index, locale in enumerate(LOCALES):
        page.emulate_media(color_scheme="dark" if index % 2 else "light")
        page.evaluate("locale => setLanguage(locale, false)", locale)
        assert not page.locator("body").evaluate("el => el.scrollWidth > innerWidth"), (
            name,
            locale,
        )
        if name == "settings":
            assert page.locator("#backupSelectedArchive").evaluate(
                "el => el.scrollWidth <= el.clientWidth + 1"
            ), locale
        invalid = page.locator('input:not([type="file"]), textarea').evaluate_all("""inputs => inputs
            .filter(el => el.getBoundingClientRect().width && !['checkbox', 'radio', 'hidden'].includes(el.type))
            .filter(el => !el.placeholder || getComputedStyle(el, '::placeholder').fontWeight !== '400')
            .map(el => el.id)""")
        assert not invalid, (name, locale, invalid)
    page.evaluate("setLanguage('vi', false)")
    for width, theme in ((360, "light"), (768, "dark"), (1440, "light"), (1440, "dark")):
        page.set_viewport_size({"width": width, "height": 1000})
        page.emulate_media(color_scheme=theme)
        assert not page.locator("body").evaluate("el => el.scrollWidth > innerWidth"), (
            name,
            width,
            theme,
        )
        page.screenshot(path=str(screenshots / f"{name}-{width}-{theme}.png"), full_page=True)


def main():
    screenshots = ROOT / "temp" / "page-completion"
    screenshots.mkdir(parents=True, exist_ok=True)
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
            page.goto(base + "/config", wait_until="networkidle")
            expect(page.locator("#backupCreate")).to_be_enabled()
            expect(page.locator("#backupRestore")).to_be_disabled()
            assert page.locator("select#routingStrategy, select#preferredProvider").count() == 0
            expect(page.locator('#configTab a[href="/models"]')).to_be_visible()
            with page.expect_response("**/api/config/save") as saved:
                page.locator('[data-ui-action="save-config"]').first.click()
            assert saved.value.ok
            page.locator("#backupCreate").click()
            expect(page.locator("#backupCreatePassphrase")).to_have_attribute(
                "aria-invalid", "true"
            )
            assert page.evaluate("document.activeElement.id") != "backupCreatePassphrase"
            page.locator("#backupCreatePassphrase").fill(PASSPHRASE)
            page.locator("#backupConfirmPassphrase").fill(PASSPHRASE)
            expect(page.locator("#backupCreatePassphraseToggle")).to_be_visible()
            page.locator("#backupCreatePassphraseToggle").click()
            expect(page.locator("#backupCreatePassphrase")).to_have_attribute("type", "text")
            page.locator("#backupCreatePassphraseToggle").click()
            with page.expect_download() as download:
                page.locator("#backupCreate").click()
            archive = download.value.path()
            expect(page.locator("#backupCreatePassphrase")).to_have_value("")
            expect(page.locator("#backupCreatePassphraseToggle")).to_be_hidden()
            page.locator("#backupArchive").set_input_files(archive)
            page.locator("#backupRestorePassphrase").fill("Wrong-backup-password")
            page.locator("#backupConflictPolicy").select_option("replace")
            page.locator("#backupValidate").click()
            expect(page.locator("#backupStatus")).to_contain_text("không hợp lệ")
            expect(page.locator("#backupRestorePassphrase")).to_have_value("Wrong-backup-password")
            expect(page.locator("#backupRestore")).to_be_disabled()
            page.locator("#backupRestorePassphrase").fill(PASSPHRASE)
            page.locator("#backupValidate").click()
            expect(page.locator("#backupRestore")).to_be_enabled()
            expect(page.locator("#backupPlan")).to_contain_text("Số bản ghi")
            page.locator("#backupConflictPolicy").select_option("abort_if_configured")
            expect(page.locator("#backupRestore")).to_be_disabled()
            page.locator("#backupValidate").click()
            expect(page.locator("#backupStatus")).to_contain_text("đã có dữ liệu")
            page.locator("#backupConflictPolicy").select_option("replace")
            page.locator("#backupValidate").click()
            expect(page.locator("#backupRestore")).to_be_enabled()
            page.locator("#backupRestore").click()
            expect(page.locator("[data-dialog-cancel]")).to_be_visible()
            assert page.evaluate("document.activeElement.tagName") not in (
                "INPUT",
                "TEXTAREA",
                "SELECT",
            )
            page.locator("[data-dialog-cancel]").click()
            expect(page.locator("#backupRestore")).to_be_enabled()
            page.locator("#backupRestorePassphrase").fill("Changed-to-invalidate")
            expect(page.locator("#backupRestore")).to_be_disabled()
            # Leave using SPA navigation, not a reload: transient secrets must disappear.
            page.evaluate("navigate('/about')")
            expect(page.locator("#backupRestorePassphrase")).to_have_value("")
            assert page.locator("#backupArchive").evaluate("el => el.files.length") == 0
            page.evaluate("navigate('/config')")
            expect(page.locator("#backupCreate")).to_be_enabled()
            page.locator("#backupArchive").set_input_files(
                {
                    "name": "long-backup-" + "x" * 180 + ".ogb",
                    "mimeType": "application/octet-stream",
                    "buffer": b"test",
                }
            )
            check_layout(page, "settings", screenshots)
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.locator("#backupArchive").set_input_files(archive)
            page.locator("#backupRestorePassphrase").fill(PASSPHRASE)
            page.locator("#backupConflictPolicy").select_option("replace")
            page.locator("#backupValidate").click()
            expect(page.locator("#backupRestore")).to_be_enabled()
            page.locator("#backupRestore").click()
            page.locator("[data-dialog-confirm]").click()
            expect(page.locator("#backupReauthenticate")).to_be_visible(timeout=20000)
            expect(page.locator("#backupStatus")).to_contain_text("Đã khôi phục")
            expect(page.locator("#backupRestorePassphrase")).to_have_value("")
            expect(page.locator("#backupRestore")).to_be_disabled()
            page.locator("#backupReauthenticate").click()
            expect(page.locator("#loginSection")).to_be_visible()
            expect(page.locator("#loginOidcEntry")).to_be_hidden()

            # Only readiness is synthetic; no external identity-provider request is made.
            def enabled_oidc(route):
                response = route.fetch()
                payload = response.json()
                payload["oidc_enabled"] = True
                route.fulfill(response=response, json=payload)

            context.route("**/api/auth/setup/status", enabled_oidc)
            page.reload(wait_until="networkidle")
            expect(page.locator("#loginOidcEntry")).to_be_visible()
            expect(page.locator("#loginOidcEntry a")).to_have_attribute(
                "href", "/api/identity/oidc/start"
            )
            check_layout(page, "login-oidc", screenshots)
            page.locator("#loginPassword").fill(PASSWORD)
            page.locator("#loginSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/identity", wait_until="networkidle")
            page.locator("[data-i18n='oidc_entry.setup_title']").click()
            expect(page.locator("[data-i18n='oidc_entry.setup_help']")).to_be_visible()
            check_layout(page, "identity-guide", screenshots)
            assert not errors, errors
            print(
                "PASS: encrypted download, invalid/valid dry run, conflict, invalidation, cancel, isolated restore and reauthentication; OIDC entry; responsive light/dark."
            )
        finally:
            browser.close()


if __name__ == "__main__":
    main()
