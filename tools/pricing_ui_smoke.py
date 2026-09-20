"""Real Chromium cost coverage smoke; fresh loopback runtime, synthetic data only."""

import json
from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from localization_ui_smoke import LOCALES, select_locale
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    state = {"priced_calls": 0, "total_cost_usd": 0}
    errors = []
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 1000})
        context.route("https://**", lambda route: route.abort())

        def aggregate(route):
            route.fulfill(
                json={
                    "success": True,
                    "data": {
                        "total_calls": 10,
                        "successful_calls": 10,
                        "failed_calls": 0,
                        "total_files": 1,
                        "active_files": 1,
                        "disabled_files": 0,
                        "input_tokens": 10000,
                        "output_tokens": 100,
                        "total_tokens": 10100,
                        "pricing": {"dynamic_state": "current", "dynamic_model_count": 238},
                        **state,
                    },
                }
            )

        context.route("**/api/usage/aggregated?*", aggregate)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/setup", wait_until="networkidle")
        page.locator("#setupPassword").fill(PASSWORD)
        page.locator("#setupPasswordConfirm").fill(PASSWORD)
        page.locator("#setupSubmitButton").click()
        expect(page).to_have_url(base + "/dashboard")
        target = ROOT / "temp/pricing-ui"
        target.mkdir(parents=True, exist_ok=True)
        for name, priced, cost in (("unknown", 0, 0), ("partial", 4, 1.25), ("free", 10, 0)):
            state.update(priced_calls=priced, total_cost_usd=cost)
            page.reload(wait_until="networkidle")
            metric = page.locator("#totalCostUsd")
            if name == "unknown":
                expect(metric).to_have_text("—")
            else:
                expect(metric).not_to_have_text("—")
            expect(page.locator("#pricingSourceDetail")).to_contain_text(f"{priced}/10")
            for width in (360, 768, 1024, 1440):
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
                if width in (360, 1440):
                    page.screenshot(path=str(target / f"{name}-{width}.png"), full_page=True)
        state.update(priced_calls=4, total_cost_usd=1.25)
        for locale in LOCALES:
            select_locale(page, locale)
            page.reload(wait_until="networkidle")
            coverage = page.evaluate(
                "t('dashboard.cost_coverage', {source: '', priced: formatUsageNumber(4), total: formatUsageNumber(10)})"
            )
            expect(page.locator("#pricingSourceDetail")).to_contain_text(coverage.strip())
            for width, theme in ((360, "dark"), (1440, "light")):
                page.set_viewport_size({"width": width, "height": 1000})
                page.emulate_media(color_scheme=theme)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                    locale,
                    width,
                )
        assert not errors, errors
        print(
            json.dumps(
                {
                    "states": 3,
                    "viewports": 4,
                    "locales": len(LOCALES),
                    "page_errors": errors,
                    "result": "passed",
                }
            )
        )
        browser.close()


if __name__ == "__main__":
    main()
