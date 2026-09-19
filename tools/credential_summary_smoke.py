"""Credential counts and uniform plan badges using synthetic Chromium responses only."""

from pathlib import Path

from browser_smoke import PASSWORD, disposable_runtime
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    items = [
        {
            "filename": "ag.json",
            "provider": "google_antigravity",
            "provider_variant": "google_antigravity",
            "credential_type": "oauth",
            "user_email": "account@example.test",
            "quota_cache_scope": "a" * 64,
            "model_count": 0,
            "model_count_known": False,
        },
        {
            "filename": "muse.json",
            "provider": "muse_code",
            "provider_variant": "muse_code",
            "credential_type": "oauth",
            "user_email": "muse@example.test",
            "quota_cache_scope": "b" * 64,
            "model_count": 5,
            "model_count_known": True,
        },
    ]
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 900})
        context.route("https://**", lambda route: route.abort())
        context.route(
            "**/api/credentials/status?**",
            lambda route: route.fulfill(
                json={"items": items, "total": 2, "stats": {"total": 2, "normal": 2, "disabled": 0}}
            ),
        )
        context.route(
            "**/api/credentials/quota/**",
            lambda route: route.fulfill(
                json={
                    "success": True,
                    "supported": True,
                    "plan": "Muse Code Power Usage"
                    if "muse.json" in route.request.url
                    else "g1-pro-tier",
                    "models": {},
                }
            ),
        )
        context.route(
            "**/api/credentials/models/**",
            lambda route: route.fulfill(
                json={"success": True, "model_ids": ["fixture-a", "fixture-b", "fixture-c"]}
            ),
        )
        context.route("**/api/credentials/errors/**", lambda route: route.fulfill(json={}))
        context.route("**/api/credentials/configuration/**", lambda route: route.fulfill(json={}))
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        output = ROOT / "temp/credential-summary"
        output.mkdir(parents=True, exist_ok=True)
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.locator('#primaryNavigation [data-tab="credentials"]').click()
            ag = page.locator("#credentialProviderGroup-google_antigravity").locator("..")
            ag = ag.locator("..").locator(".cred-card")
            metric = ag.locator('[id^="credential-model-count-"]')
            expect(metric).to_have_text("— mô hình")
            refresh = page.locator('[data-ui-action="refresh-credentials"]')
            items[0].update(model_count=29, model_count_known=True)
            refresh.click()
            expect(metric).to_have_text("29 mô hình")
            items[0].update(model_count=0, model_count_known=False)
            refresh.click()
            expect(metric).to_have_text("29 mô hình")
            ag.locator('[data-credential-command="manage"]').click()
            expect(page.locator("[data-management-model]")).to_have_count(3)
            expect(metric).to_have_text("3 mô hình")
            page.locator("[data-dialog-close]").click()
            refresh.click()
            expect(metric).to_have_text("3 mô hình")
            items[0]["quota_cache_scope"] = "c" * 64
            refresh.click()
            expect(metric).to_have_text("— mô hình")
            items[0]["model_count_known"] = True
            refresh.click()
            expect(metric).to_have_text("0 mô hình")
            items[0]["model_count"] = 29
            refresh.click()
            expect(metric).to_have_text("29 mô hình")
            badges = page.locator(".cred-card .subscription-badge:visible")
            expect(badges).to_have_count(2)
            for width, height, theme in ((1440, 900, "light"), (360, 800, "dark")):
                page.set_viewport_size({"width": width, "height": height})
                page.emulate_media(color_scheme=theme)
                styles = badges.evaluate_all("""nodes => nodes.map(el => {
                    const s = getComputedStyle(el);
                    return [s.color, s.backgroundColor, s.borderColor];
                })""")
                assert styles[0] == styles[1], styles
                assert badges.evaluate_all("nodes => nodes.every(el => !el.hasAttribute('title'))")
                assert not page.locator("body").evaluate("el => el.scrollWidth > innerWidth + 1")
                page.screenshot(path=str(output / f"summary-{width}-{theme}.png"), full_page=True)
            assert not errors, errors
        finally:
            browser.close()
    print(
        "Credential summary: unknown/retained/empty/replaced counts, discovery sync, uniform badge color; desktop/mobile passed."
    )


if __name__ == "__main__":
    main()
