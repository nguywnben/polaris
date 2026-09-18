"""AI Quality UI journeys against a disposable local runtime, never the user's policy."""

from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        screenshots = ROOT / "temp/quality-ui"
        screenshots.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/ai-quality", wait_until="networkidle")
            expect(page.locator("#qualityForm")).to_be_visible()
            expect(page.locator("#qualityControlsHint")).to_contain_text("Chọn Tùy chỉnh")
            for profile in ("quality", "capacity", "balanced", "custom"):
                page.locator(f'input[name="qualityProfile"][value="{profile}"]').check()
                if profile != "custom":
                    expect(page.locator("#antiTruncationMaxAttempts")).to_be_disabled()
                else:
                    expect(page.locator("#antiTruncationMaxAttempts")).to_be_enabled()
            page.locator("#tokenCompressionEnabled").uncheck()
            expect(page.locator("#tokenCompressionThreshold")).to_be_disabled()
            expect(page.locator("#qualityTransformationSummary")).to_contain_text("không")
            page.locator("#qualityPreviewButton").click()
            expect(page.locator("#qualityPreviewResult")).to_be_visible()
            assert (
                page.locator("#qualityPreviewBefore").inner_text()
                == page.locator("#qualityPreviewAfter").inner_text()
            )
            page.locator("#qualityPreviewTokens").fill("50000")
            expect(page.locator("#qualityPreviewResult")).to_be_hidden()
            page.locator("#tokenCompressionEnabled").check()
            page.locator("#qualityGuardrailsEnabled").check()
            expect(page.locator("#qualityBlockedKeywords")).to_be_enabled()
            page.locator("#qualityResponseCacheEnabled").check()
            expect(page.locator("#qualityResponseCacheTtl")).to_be_enabled()
            page.locator("#tokenCompressionTarget").fill("40000")
            page.locator("#qualityPreviewButton").click()
            expect(page.locator("#qualityPreviewResult")).to_be_hidden()
            page.locator("#tokenCompressionTarget").fill("24000")
            page.locator("#qualityPreviewButton").click()
            expect(page.locator("#qualityPreviewResult")).to_be_visible()
            page.locator("#qualityPreviewSystem").uncheck()
            expect(page.locator("#qualityPreviewResult")).to_be_hidden()

            failure = {"save": True, "load": False, "locked": False}

            def policy_response(route):
                if route.request.method == "PUT" and failure["save"]:
                    route.fulfill(
                        status=503, json={"error": {"code": "quality_policy_unavailable"}}
                    )
                elif route.request.method == "GET" and failure["load"]:
                    route.fulfill(
                        status=503, json={"error": {"code": "quality_policy_unavailable"}}
                    )
                elif route.request.method == "GET" and failure["locked"]:
                    response = route.fetch()
                    data = response.json()
                    data["env_locked"] = ["token_compression_threshold"]
                    route.fulfill(response=response, json=data)
                else:
                    route.fallback()

            page.route("**/api/quality-policy", policy_response)
            page.locator("#qualitySaveButton").click()
            expect(page.locator("#qualitySaveButton")).to_be_enabled()
            expect(page.locator('input[name="qualityProfile"][value="custom"]')).to_be_checked()
            failure["save"] = False
            with page.expect_response(
                lambda response: (
                    response.url.endswith("/api/quality-policy")
                    and response.request.method == "PUT"
                )
            ) as saved:
                page.locator("#qualitySaveButton").click()
            assert saved.value.ok
            expect(page.locator("#qualityRevision")).not_to_have_text("0")
            for profile in ("balanced", "custom"):
                page.locator(f'input[name="qualityProfile"][value="{profile}"]').check()
                page.locator("#qualityPreviewButton").click()
                expect(page.locator("#qualityPreviewResult")).to_be_visible()
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
                    page.evaluate("window.scrollTo(0, 0)")
                    page.mouse.move(2, 2)
                    assert not page.locator("body").evaluate("el => el.scrollWidth > innerWidth"), (
                        profile,
                        width,
                    )
                    assert not page.locator("#qualityTab").evaluate(
                        "el => el.scrollWidth > el.clientWidth"
                    ), (profile, width)
                    page.screenshot(
                        path=str(screenshots / f"{profile}-{width}-{theme}.png"),
                        full_page=True,
                        animations="disabled",
                    )
            failure["locked"] = True
            page.reload(wait_until="networkidle")
            page.locator('input[name="qualityProfile"][value="custom"]').check()
            expect(page.locator("#tokenCompressionThreshold")).to_be_disabled()
            expect(page.locator("#qualityControlsHint")).to_contain_text("môi trường quản lý")
            page.evaluate("AppState.lang = 'en'; applyLanguage(); syncQualityPolicyControls()")
            expect(page.locator("#qualityControlsHint")).to_contain_text("remain locked")
            failure["load"] = True
            page.reload(wait_until="networkidle")
            expect(page.locator("#qualityState")).to_be_visible()
            expect(page.locator("#qualityForm")).to_be_hidden()
            failure["load"] = False
            page.locator("#qualityState button").click()
            expect(page.locator("#qualityForm")).to_be_visible()
            assert not errors, errors
            print(
                "PASS: Four profiles, dependent/locked controls, preview invalidation, validation, failed/successful save, load/retry, en/vi, 320–1440px light/dark"
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
