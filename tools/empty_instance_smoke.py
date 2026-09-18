"""Round-one audit: no provider credentials, models, traffic or virtual keys.

One bounded sweep of expanded pages, 23 provider workspaces and creation dialogs.
Only owner bootstrap writes to disposable storage; never start OAuth or inference.
"""

from __future__ import annotations

import argparse
import json

from browser_smoke import PASSWORD, ROOT, disposable_runtime
from design_consistency_smoke import AUDIT, ROUTES
from playwright.sync_api import expect, sync_playwright


def expand_disclosures(page, root):
    for disclosure in page.locator(f"{root} details").all():
        summary = disclosure.locator(":scope > summary")
        if summary.is_visible() and disclosure.get_attribute("open") is None:
            summary.click()


def main(stage, strict):
    output = ROOT / "temp/empty-instance" / stage
    output.mkdir(parents=True, exist_ok=True)
    results, errors, writes = [], [], []
    with disposable_runtime() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="vi-VN", reduced_motion="reduce")
        context.route("https://**", lambda route: route.abort())
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/setup", wait_until="networkidle")
        page.locator("#setupPassword").fill(PASSWORD)
        page.locator("#setupPasswordConfirm").fill(PASSWORD)
        page.locator("#setupSubmitButton").click()
        expect(page).to_have_url(base + "/dashboard")

        def guard_write(route):
            if route.request.method in ("POST", "PUT", "PATCH", "DELETE"):
                writes.append(route.request.url.removeprefix(base))
                route.fulfill(status=503, json={"detail": "Audit blocked an unexpected write"})
            else:
                route.fallback()

        context.route("**/api/**", guard_write)

        def capture(name):
            for width in (360, 1440):
                page.set_viewport_size({"width": width, "height": 900})
                for theme in ("light", "dark"):
                    page.emulate_media(color_scheme=theme)
                    expect(page.locator("html")).to_have_attribute("data-theme", theme)
                    page.evaluate("window.scrollTo(0, 0)")
                    page.wait_for_timeout(180)
                    result = page.evaluate(AUDIT)
                    result.update(surface=name, width=width)
                    results.append(result)
                    page.screenshot(
                        path=str(output / f"{name}-{width}-{theme}.png"), full_page=True
                    )
            print(f"Captured expanded {name}", flush=True)

        try:
            for route in ROUTES:
                page.set_viewport_size({"width": 1440, "height": 900})
                page.goto(base + "/" + route, wait_until="networkidle")
                expand_disclosures(page, ".tab-content.active")
                capture(route.replace("?view=", "-"))

            page.goto(base + "/providers", wait_until="networkidle")
            provider_ids = page.locator("#providerCatalog [data-provider]").evaluate_all(
                "els => els.map(el => el.dataset.provider)"
            )
            assert len(provider_ids) == 23, provider_ids
            for provider in provider_ids:
                page.set_viewport_size({"width": 1440, "height": 900})
                page.locator("#providerCatalogSearch").fill(provider)
                selector = page.locator(f'#providerCatalog [data-provider="{provider}"]')
                selector.click()
                panel = "#" + selector.get_attribute("aria-controls")
                expect(page.locator(panel)).to_be_visible()
                expand_disclosures(page, panel)
                for opener in page.locator(panel + " .provider-key-entry-button").all():
                    if opener.is_visible() and opener.get_attribute("aria-expanded") != "true":
                        opener.click()
                for form in page.locator(panel + " form").all():
                    key = form.locator('input[type="password"][required]')
                    submit = form.locator('button[type="submit"]')
                    if key.count() and key.first.is_visible() and submit.count():
                        submit.click()
                        assert not writes, (provider, writes)
                        expect(key.first).to_have_value("")
                capture(provider)
            page.locator("#providerCatalogSearch").fill("no-such-provider-round-one")
            expect(page.locator("#providerCatalogEmpty")).to_be_visible()
            expect(page.locator("#providerCatalogPagination")).to_be_hidden()

            for route, trigger, form in (
                ("access", '[data-ui-action="virtual-key-create"]', "#virtualKeyForm"),
                ("identity", "#identityCreateButton", "#identityCreateForm"),
            ):
                page.set_viewport_size({"width": 1440, "height": 900})
                page.goto(base + "/" + route, wait_until="networkidle")
                page.locator(trigger).click()
                expect(page.locator(form)).to_be_visible()
                capture(route + "-create")
                page.keyboard.press("Escape")
                expect(page.locator(form)).not_to_be_visible()
                expect(page.locator(trigger)).to_be_focused()

            assert not errors, errors
            assert not writes, writes
        finally:
            (output / "report.json").write_text(
                json.dumps(
                    {"results": results, "errors": errors, "writes": writes},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            browser.close()
    findings = [
        r
        for r in results
        if any(
            r[key] for key in ("overflow", "missingNames", "placeholder", "contrast", "overlaps")
        )
    ]
    print(json.dumps({"cases": len(results), "findings": findings}, ensure_ascii=False))
    if strict:
        assert not findings, "See report.json for expanded-surface defects"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", default="before")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    main(args.stage, args.strict)
