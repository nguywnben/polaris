"""Credentials UI regression checks with synthetic data in an isolated runtime."""

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    state = {"mode": "empty"}

    def credentials(route):
        if state["mode"] == "error":
            route.fulfill(status=503, json={"detail": "Synthetic load failure"})
            return
        query = parse_qs(urlparse(route.request.url).query)
        filtered = query.get("status_filter", ["all"])[0] != "all"
        items = []
        if state["mode"] == "populated" and not filtered:
            for index, (provider, variant) in enumerate(
                (("openai", "openai_platform"), ("anthropic", "claude_platform"))
            ):
                items.append(
                    {
                        "filename": f"synthetic-{index}.json",
                        "provider": provider,
                        "provider_variant": variant,
                        "credential_type": "api_key",
                        "credential_label": f"Development account {index + 1}",
                        "disabled": False,
                        "health": "healthy",
                        "model_count": 3,
                    }
                )
        route.fulfill(
            json={
                "items": items,
                "total": len(items),
                "has_more": False,
                "stats": {"total": len(items), "normal": len(items), "disabled": 0},
            }
        )

    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        context.route("**/api/credentials/status?**", credentials)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        screenshots = ROOT / "temp/credentials-ui"
        screenshots.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/credentials", wait_until="networkidle")
            assert context.request.get(base + "/pool").status == 404
            expect(page.locator('#primaryNavigation [data-tab="credentials"]')).to_have_attribute(
                "aria-current", "page"
            )
            page.reload(wait_until="networkidle")
            expect(page).to_have_url(base + "/credentials")
            expect(page.locator("#credentialsFirstRun")).to_be_visible()
            expect(page.locator("#credentialsImportArchiveBtn")).to_be_hidden()
            expect(page.locator("#credentialsFirstRun h2")).to_have_text(
                "Chưa có thông tin xác thực"
            )
            with page.expect_file_chooser():
                page.locator(
                    '#credentialsFirstRun [data-ui-action="select-credentials-archive"]'
                ).click()
            page.evaluate("AppState.lang = 'en'; applyLanguage()")
            expect(page.locator("#credentialsFirstRun h2")).to_have_text("No credentials yet")
            page.evaluate("AppState.lang = 'vi'; applyLanguage()")

            for mode in ("empty", "populated"):
                state["mode"] = mode
                page.locator('#credentialsTab [data-ui-action="refresh-credentials"]').click()
                if mode == "populated":
                    expect(page.locator("#primaryCredsList .cred-card")).to_have_count(2)
                    expect(page.locator("#credentialsFirstRun")).to_be_hidden()
                    page.locator("#primarySelectAllCheckbox").check()
                    expect(page.locator("#primaryBatchDeleteBtn")).to_be_enabled()
                    page.locator("#primarySelectAllCheckbox").uncheck()
                    expect(page.locator("#primaryBatchDeleteBtn")).to_be_disabled()
                    page.locator("#primaryAdvancedFilters summary").click()
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
                        mode,
                        width,
                    )
                    assert not page.locator("#credentialsTab").evaluate(
                        "el => el.scrollWidth > el.clientWidth"
                    ), (mode, width)
                    page.screenshot(
                        path=str(screenshots / f"{mode}-{width}-{theme}.png"),
                        full_page=True,
                        animations="disabled",
                    )

            page.locator("#primaryStatusFilter").select_option("disabled")
            expect(page.locator("#primaryCredsList .creds-empty-state")).to_be_visible()
            expect(page.locator("#credentialsFirstRun")).to_be_hidden()
            expect(page.locator("#primaryStatusFilter")).to_be_visible()
            page.locator('[data-ui-action="reset-primary-filters"]').click()
            expect(page.locator("#primaryCredsList .cred-card")).to_have_count(2)
            state["mode"] = "empty"
            page.locator('#credentialsTab [data-ui-action="refresh-credentials"]').click()
            expect(page.locator("#credentialsFirstRun")).to_be_visible()
            state["mode"] = "error"
            page.locator('#credentialsTab [data-ui-action="refresh-credentials"]').click()
            expect(page.locator("#primaryCredsState")).to_be_visible()
            state["mode"] = "populated"
            page.locator("#primaryCredsState button").click()
            expect(page.locator("#primaryCredsList .cred-card")).to_have_count(2)
            expect(page.locator("#primaryCredsState")).to_be_hidden()
            assert not errors, errors
            print(
                "PASS: Empty/populated credentials, selection, filtered zero/reset, error/retry, ZIP chooser, en/vi, 320–1440px light/dark"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
