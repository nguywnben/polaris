"""Credential layout contracts against a disposable, source-shaped demo database."""

import json

from browser_smoke import ROOT
from playwright.sync_api import expect, sync_playwright
from populated_instance_smoke import PASSWORD, populated_runtime


def main():
    output = ROOT / "temp/prerelease-credentials"
    output.mkdir(parents=True, exist_ok=True)
    measurements = []
    with populated_runtime(output) as (base, _), sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", viewport={"width": 1440, "height": 900})
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        try:
            page.goto(base + "/setup", wait_until="networkidle")
            page.locator("#setupPassword").fill(PASSWORD)
            page.locator("#setupPasswordConfirm").fill(PASSWORD)
            page.locator("#setupSubmitButton").click()
            expect(page).to_have_url(base + "/dashboard")
            page.goto(base + "/credentials", wait_until="networkidle")
            page.locator("#primaryProviderFilter").select_option("google_antigravity")
            expect(page.locator(".cred-card")).to_have_count(7)
            page.wait_for_load_state("networkidle")
            badge = page.locator(".subscription-badge:visible").first
            tooltip = badge.locator(".credential-badge-tooltip")
            badge.focus()
            expect(tooltip).to_be_visible()
            page.keyboard.press("Escape")
            expect(tooltip).to_be_hidden()
            expect(badge).to_be_focused()
            page.keyboard.press("Tab")
            page.keyboard.press("Shift+Tab")
            expect(tooltip).to_be_visible()
            page.keyboard.press("Escape")
            page.locator("#primaryProviderFilter").focus()
            badge.hover()
            expect(tooltip).to_be_visible()
            tooltip.hover()
            expect(tooltip).to_be_visible()
            page.keyboard.press("Escape")
            expect(tooltip).to_be_hidden()
            card = page.locator('[data-filename="demo-google_antigravity-01.json"]').locator(
                "xpath=ancestor::div[contains(@class,'cred-card')][1]"
            )
            card.locator('[data-credential-command="manage"]').click()
            dialog = page.locator(".credential-management-modal")
            expect(
                dialog.locator("[data-management-quota] .modal-quota-card").first
            ).to_be_visible()
            expect(dialog.locator("[data-management-configuration] input").first).to_be_visible()
            for width, height in ((1440, 900), (768, 1024), (360, 800), (844, 390)):
                page.set_viewport_size({"width": width, "height": height})
                result = dialog.evaluate("""el => {
                    const regions = [...el.querySelectorAll('.modal-quota-grid, .credential-model-list')];
                    return {width:innerWidth,
                        overflow:el.scrollWidth > el.clientWidth + 1,
                        nested:regions.filter(node => node.scrollHeight > node.clientHeight + 1
                            && ['auto','scroll'].includes(getComputedStyle(node).overflowY)).map(node => node.className),
                        quotaWidth:el.querySelector('[data-management-quota]').getBoundingClientRect().width,
                        bodyWidth:el.querySelector('.credential-management-content').getBoundingClientRect().width};
                }""")
                measurements.append(result)
            failures = [m for m in measurements if m["overflow"] or m["nested"]]
            assert not failures, failures
            wide = measurements[0]
            assert abs(wide["quotaWidth"] - wide["bodyWidth"]) <= 1, wide
            measurements.append({"badgeHint": "focus, hover, Escape, reopen"})
            page.locator(".credential-management-modal [data-dialog-close]").click()
            page.set_viewport_size({"width": 1440, "height": 900})
            page.locator("#primaryProviderFilter").select_option("muse_code")
            page.locator('[data-filename="demo-muse_code-01.json"]').locator(
                "xpath=ancestor::div[contains(@class,'cred-card')][1]"
            ).locator('[data-credential-command="manage"]').click()
            facts = page.locator("[data-management-quota] .credential-management-facts")
            expect(facts.locator("dd")).to_have_count(2)
            spacing = facts.evaluate("""el => {
                const [first, second] = el.querySelectorAll('dd');
                const range = document.createRange();
                range.selectNodeContents(first);
                const a = range.getBoundingClientRect(), b = second.getBoundingClientRect();
                return {horizontal: b.left - a.right, vertical: b.top - a.bottom,
                    display: getComputedStyle(el).display, gap: getComputedStyle(el).gap,
                    marginBottom: parseFloat(getComputedStyle(el).marginBottom)};
            }""")
            measurements.append({"quotaFactSpacing": spacing})
            assert spacing["horizontal"] >= 12 or spacing["vertical"] >= 12, spacing
            assert spacing["marginBottom"] >= 12, spacing
            expect(page.locator("[data-management-model-select]")).to_be_visible()
            test_alignment = page.locator(".credential-management-test").evaluate("""el => {
                const select = el.querySelector('select').getBoundingClientRect();
                const button = el.querySelector('button').getBoundingClientRect();
                return Math.abs(select.bottom - button.bottom);
            }""")
            assert test_alignment <= 1, test_alignment
            page.screenshot(path=str(output / "muse-code-desktop.png"))
            page.set_viewport_size({"width": 360, "height": 800})
            page.emulate_media(color_scheme="dark")
            page.screenshot(path=str(output / "muse-code-mobile-dark.png"))
            page.locator(".credential-management-modal [data-dialog-close]").click()
            page.set_viewport_size({"width": 1440, "height": 900})
            for theme in ("dark", "light"):
                page.emulate_media(color_scheme=theme)
                for provider in ("codex", "xai_console", "deepseek", "ollama"):
                    page.locator("#primaryProviderFilter").select_option(provider)
                    selection = page.locator(f'[data-filename="demo-{provider}-01.json"]')
                    card = selection.locator("xpath=ancestor::div[contains(@class,'cred-card')][1]")
                    card.locator('[data-credential-command="manage"]').click()
                    logo = page.locator(".credential-management-identity img")
                    expect(logo).to_be_visible()
                    expected = "invert(1)" if theme == "dark" else "none"
                    assert logo.evaluate("el => getComputedStyle(el).filter") == expected, (
                        provider,
                        theme,
                    )
                    page.locator(".credential-management-modal [data-dialog-close]").click()
            for role, permissions in (
                ("viewer", ["credentials.read"]),
                ("operator", ["credentials.read", "credentials.operate"]),
                (
                    "security_admin",
                    [
                        "credentials.read",
                        "credentials.operate",
                        "credentials.manage",
                        "credentials.export",
                    ],
                ),
                ("unavailable", None),
            ):

                def session_response(route, _request, granted=permissions):
                    if granted is None:
                        route.fulfill(status=503, json={"detail": "Synthetic session unavailable"})
                    else:
                        route.fulfill(json={"principal": {"permissions": granted}})

                page.route("**/api/identity/session", session_response)
                page.reload(wait_until="networkidle")
                page.locator("#primaryProviderFilter").select_option("muse_code")
                card = page.locator('[data-filename="demo-muse_code-01.json"]').locator(
                    "xpath=ancestor::div[contains(@class,'cred-card')][1]"
                )
                expect(card).to_be_visible()
                card.locator('[data-credential-command="manage"]').click()
                dialog = page.locator(".credential-management-modal")
                expect(dialog).to_be_visible()
                can_manage = role == "security_admin"
                can_operate = role in ("operator", "security_admin")
                expect(dialog.locator("[data-management-sensitive]")).to_have_count(int(can_manage))
                expect(dialog.locator('[data-management-action="delete"]')).to_have_count(
                    int(can_manage)
                )
                expect(dialog.locator('[data-management-action="toggle"]')).to_have_count(
                    int(can_operate)
                )
                expect(dialog.locator("[data-management-configuration]")).to_have_count(
                    int(can_manage)
                )
                page.locator(".credential-management-modal [data-dialog-close]").click()
                for control in page.locator('[data-ui-action="select-credentials-archive"]').all():
                    expect(control).to_be_enabled(enabled=can_manage)
                expect(page.locator('[data-ui-action="download-credentials"]')).to_be_enabled(
                    enabled=can_manage
                )
                page.unroute("**/api/identity/session", session_response)
        finally:
            (output / "report.json").write_text(
                json.dumps(measurements, indent=2), encoding="utf-8"
            )
            browser.close()
    print("Credential layout: four widths, no nested content scrollbars, full-width quota.")


if __name__ == "__main__":
    main()
