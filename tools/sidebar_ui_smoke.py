"""Check readable navigation without enlarging the console's compact controls."""

import argparse
from pathlib import Path

from browser_smoke import disposable_runtime
from localization_ui_smoke import LOCALES, select_locale
from playwright.sync_api import expect, sync_playwright
from provider_ownership_smoke import _complete_setup, _install_network_guard


def main(stage):
    output = Path(__file__).resolve().parents[1] / "temp/sidebar-sizing" / stage
    output.mkdir(parents=True, exist_ok=True)
    with disposable_runtime() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(locale="vi-VN", reduced_motion="reduce")
        page = context.new_page()
        errors, external = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        _install_network_guard(page, external)
        _complete_setup(page, base)
        sidebar = page.locator(".dashboard-sidebar")
        checked = 0
        for locale in ("vi", *(item for item in LOCALES if item != "vi")):
            select_locale(page, locale)
            sizes = ((1440, 900), (320, 800))
            if locale == "vi":
                sizes += ((768, 1024), (844, 390), (1024, 768), (1920, 1080))
            for width, height in sizes:
                page.set_viewport_size({"width": width, "height": height})
                for theme in ("light", "dark"):
                    page.emulate_media(color_scheme=theme)
                    expect(page.locator("html")).to_have_attribute("data-theme", theme)
                    if width <= 960:
                        page.locator(".mobile-menu-btn").click()
                        expect(sidebar).to_have_class("dashboard-sidebar open")
                    if locale == "vi":
                        page.screenshot(path=str(output / f"sidebar-{width}-{theme}.png"))
                    metrics = sidebar.evaluate("""el => ({
                        width: el.getBoundingClientRect().width,
                        overflow: el.scrollWidth > el.clientWidth + 1,
                        rows: [...el.querySelectorAll('.tab')].map(row => ({
                            height: row.getBoundingClientRect().height,
                            font: parseFloat(getComputedStyle(row).fontSize),
                            icon: row.querySelector('svg').getBoundingClientRect().width,
                            clipped: row.scrollWidth > row.clientWidth + 1 || row.scrollHeight > row.clientHeight + 1
                        }))
                    })""")
                    assert abs(metrics["width"] - 248) < 1, metrics
                    assert not metrics["overflow"], (locale, width, metrics)
                    assert all(
                        row["height"] >= 35.5
                        and (locale != "vi" or abs(row["height"] - 36) < 0.5)
                        and abs(row["font"] - 13) < 0.1
                        and abs(row["icon"] - 16) < 0.1
                        and not row["clipped"]
                        for row in metrics["rows"]
                    ), (locale, width, metrics)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    assert abs(page.locator("#usagePeriodSelect").bounding_box()["height"] - 32) < 1
                    footer = sidebar.locator(".sidebar-footer button")
                    footer.focus()
                    expect(footer).to_be_in_viewport()
                    if width <= 960:
                        page.keyboard.press("Tab")
                        expect(sidebar.locator(".tab").first).to_be_focused()
                        page.keyboard.press("Shift+Tab")
                        expect(footer).to_be_focused()
                        page.keyboard.press("Escape")
                        expect(page.locator(".mobile-menu-btn")).to_be_focused()
                        expect(sidebar).not_to_have_class("dashboard-sidebar open")
                    checked += 1
        assert not errors, errors
        assert not external, external
        browser.close()
    print(
        f"PASS: sidebar sizing, text fit, keyboard and scrolling across {checked} size/theme/locale cases"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", default="after")
    main(parser.parse_args().stage)
